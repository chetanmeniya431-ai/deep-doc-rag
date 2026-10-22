"""Web app: upload PDFs, ask questions with page-level citations, inspect how a page
was parsed, and run the evaluation. FastAPI + Jinja templates, all Python."""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path

import fitz
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import config
from ..generate import llm
from ..index import store

app = FastAPI(title="DeepDoc RAG")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals.update(public_demo=config.PUBLIC_DEMO, max_upload_mb=config.MAX_UPLOAD_MB,
                             max_upload_pages=config.MAX_UPLOAD_PAGES)
KIND_COLOURS = {"heading": "#4f46e5", "text": "#64748b", "table": "#059669", "figure": "#d97706",
                "box": "#db2777", "caption": "#0284c7", "footnote": "#7c3aed"}
_jobs: dict[str, dict] = {}
_eval_state: dict = {"running": False, "done": 0, "total": 0, "report": None}
# LLM answers run as background jobs. The browser polls for the result, so a slow CPU answer
# never hits a proxy timeout (Cloudflare drops requests that are silent for 100 s).
_ask_jobs: dict[str, dict] = {}
_ask_lock = threading.Lock()
MAX_ASK_JOBS = 4
# Only one PDF is indexed at a time, so uploads cannot pile up and use all the RAM.
_ingest_lock = threading.Lock()


def _docs() -> list[dict]:
    with store.db() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()]
    for r in rows:
        r["stats"] = json.loads(r["stats"] or "{}")
    return rows


def _doc(doc_id: int) -> dict:
    with store.db() as con:
        r = con.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Document not found")
    return dict(r)


def _render(request: Request, name: str, **ctx) -> HTMLResponse:
    ctx.setdefault("active", name.split(".")[0])
    return templates.TemplateResponse(request, name, ctx)


@app.on_event("startup")
def mark_interrupted_jobs():
    """A restart kills running ingest jobs. Say so instead of showing 'embedding' forever."""
    with store.db() as con:
        con.execute("UPDATE documents SET status='failed', message='Interrupted by a restart. Click Index again.' "
                    "WHERE status IN ('parsing', 'embedding')")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return RedirectResponse("/ask" if any(d["status"] == "ready" for d in _docs()) else "/documents")


@app.get("/health")
def health():
    return {"ok": True, "llm": llm.available(), "docs": len(_docs())}


# ───────────── documents ─────────────

@app.get("/documents", response_class=HTMLResponse)
def documents(request: Request):
    config.ensure_dirs()
    indexed = {d["name"] for d in _docs()}
    waiting = [p.name for p in sorted(config.PDF_DIR.glob("*.pdf")) if p.name not in indexed]
    return _render(request, "documents.html", docs=_docs(), waiting=waiting)


def _ingest_job(path: str) -> None:
    from ..ingest.pipeline import ingest_pdf
    try:
        ingest_pdf(path, progress=lambda m: None)
    except Exception:
        pass
    finally:
        _ingest_lock.release()


def _start_ingest(background: BackgroundTasks, path: Path) -> None:
    if not _ingest_lock.acquire(blocking=False):
        raise HTTPException(429, "Another PDF is being indexed. Please try again in a few minutes.")
    background.add_task(_ingest_job, str(path))


@app.post("/documents/upload")
async def upload(background: BackgroundTasks, file: UploadFile = File(...)):
    config.ensure_dirs()
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(file.filename or "upload.pdf").name)
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")
    if len(_docs()) >= config.MAX_DOCS:
        raise HTTPException(400, f"This demo holds at most {config.MAX_DOCS} documents. Delete one first.")
    dest = config.PDF_DIR / name
    data = await file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"The file is too big (max {config.MAX_UPLOAD_MB} MB)")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "This file is not a valid PDF")
    try:
        pages = fitz.open(stream=data, filetype="pdf").page_count
    except Exception:
        raise HTTPException(400, "This file is not a valid PDF")
    if pages > config.MAX_UPLOAD_PAGES:
        raise HTTPException(400, f"The PDF has {pages} pages (max {config.MAX_UPLOAD_PAGES})")
    dest.write_bytes(data)
    _start_ingest(background, dest)
    return RedirectResponse("/documents", status_code=303)


@app.post("/documents/ingest")
def ingest_existing(background: BackgroundTasks, name: str = Form(...)):
    path = config.PDF_DIR / Path(name).name
    if not path.exists():
        raise HTTPException(404, "File not found")
    _start_ingest(background, path)
    return RedirectResponse("/documents", status_code=303)


@app.post("/documents/{doc_id}/delete")
def delete_doc(doc_id: int):
    d = _doc(doc_id)
    if config.PUBLIC_DEMO and d["name"] == config.DEMO_PDF_NAME:
        raise HTTPException(403, "The demo PDF cannot be deleted on the public demo")
    for img in config.PAGE_IMG_DIR.glob(f"{doc_id}-*.png"):
        img.unlink(missing_ok=True)
    # Uploaded files go too; the demo PDF stays so it can be indexed again.
    if d["name"] != config.DEMO_PDF_NAME:
        Path(d["path"]).unlink(missing_ok=True)
    with store.db() as con:
        con.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
        con.execute("DELETE FROM elements WHERE doc_id=?", (doc_id,))
        con.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    store.invalidate_cache()
    return RedirectResponse("/documents", status_code=303)


@app.get("/api/documents")
def api_documents():
    return [{k: d[k] for k in ("id", "name", "pages", "status", "message")} for d in _docs()]


@app.get("/documents/{doc_id}/file")
def doc_file(doc_id: int):
    d = _doc(doc_id)
    return FileResponse(d["path"], media_type="application/pdf", filename=d["name"])


# ───────────── ask ─────────────

@app.get("/ask", response_class=HTMLResponse)
def ask_page(request: Request):
    gold = []
    gold_file = config.PDF_DIR / config.DEMO_GOLD_NAME
    if gold_file.exists():
        all_q = json.loads(gold_file.read_text())
        seen = set()
        for g in all_q:
            if g["type"] not in seen:
                seen.add(g["type"])
                gold.append(g)
    return _render(request, "ask.html", examples=gold, llm_on=llm.available(), model=config.LLM_MODEL)


@app.post("/api/ask")
async def api_ask(payload: dict):
    from ..generate.answer import answer
    q = (payload.get("question") or "").strip()
    if not q:
        raise HTTPException(400, "Question is empty")
    if len(q) > 1000:
        raise HTTPException(400, "Question is too long (max 1000 characters)")
    use_llm = bool(payload.get("use_llm", True))
    if not use_llm:
        return JSONResponse(await _run_in_thread(answer, q, False))
    # The LLM step is slow on a CPU: start a job and let the browser poll /api/ask/{job}.
    with _ask_lock:
        now = time.time()
        for k in [k for k, j in _ask_jobs.items() if now - j["started"] > 1800]:
            del _ask_jobs[k]
        if sum(1 for j in _ask_jobs.values() if j["status"] == "running") >= MAX_ASK_JOBS:
            raise HTTPException(429, "The model is busy with other questions. Please try again in a minute.")
        job_id = uuid.uuid4().hex
        _ask_jobs[job_id] = {"status": "running", "started": now, "result": None}

    def run():
        try:
            _ask_jobs[job_id].update(status="done", result=answer(q, True))
        except Exception as exc:
            _ask_jobs[job_id].update(status="failed", error=str(exc))

    threading.Thread(target=run, daemon=True).start()
    return {"job": job_id}


@app.get("/api/ask/{job_id}")
def api_ask_job(job_id: str):
    job = _ask_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown or expired question")
    if job["status"] == "failed":
        raise HTTPException(500, job.get("error") or "The answer failed")
    return {"status": job["status"], "result": job["result"]}


async def _run_in_thread(fn, *args):
    import asyncio
    return await asyncio.get_running_loop().run_in_executor(None, fn, *args)


# ───────────── inspect ─────────────

@app.get("/inspect/{doc_id}/{page}", response_class=HTMLResponse)
def inspect(request: Request, doc_id: int, page: int):
    d = _doc(doc_id)
    page = max(1, min(page, d["pages"] or 1))
    with store.db() as con:
        els = [dict(r) for r in con.execute("SELECT * FROM elements WHERE doc_id=? AND page=? ORDER BY ord",
                                            (doc_id, page)).fetchall()]
        chunks = [dict(r) for r in con.execute("SELECT id, kind, section, text, pages FROM chunks WHERE doc_id=? AND pages LIKE ?",
                                               (doc_id, f"%{page}%")).fetchall()]
    chunks = [c for c in chunks if page in json.loads(c["pages"])]
    for e in els:
        e["bbox"] = json.loads(e["bbox"])
        e["meta"] = json.loads(e["meta"] or "{}")
    pdf = fitz.open(d["path"])
    w, h = pdf[page - 1].rect.width, pdf[page - 1].rect.height
    return _render(request, "inspect.html", doc=d, page=page, elements=els, chunks=chunks, w=w, h=h,
                   colours=KIND_COLOURS, active="documents")


@app.get("/page-image/{doc_id}/{page}.png")
def page_image(doc_id: int, page: int):
    d = _doc(doc_id)
    config.ensure_dirs()
    out = config.PAGE_IMG_DIR / f"{doc_id}-{page}.png"
    if not out.exists():
        pdf = fitz.open(d["path"])
        if not 1 <= page <= len(pdf):
            raise HTTPException(404, "No such page")
        pdf[page - 1].get_pixmap(dpi=110).save(str(out))
    return FileResponse(out, media_type="image/png")


# ───────────── evaluation ─────────────

@app.get("/evaluate", response_class=HTMLResponse)
def evaluate_page(request: Request):
    has_gold = (config.PDF_DIR / config.DEMO_GOLD_NAME).exists()
    report = _eval_state["report"]
    saved = config.DATA_DIR / "last_eval.json"
    if report is None and saved.exists():
        report = json.loads(saved.read_text())
    return _render(request, "evaluate.html", state=_eval_state, report=report, has_gold=has_gold, top_k=config.TOP_K)


@app.post("/evaluate/run")
def evaluate_run(use_llm: str = Form(""), limit: int = Form(0)):
    # On the public demo the LLM eval (187 questions) would block the shared model for hours.
    if config.PUBLIC_DEMO:
        use_llm = ""
    if _eval_state["running"]:
        return RedirectResponse("/evaluate", status_code=303)

    def job():
        from ..eval.run import run_eval
        _eval_state.update(running=True, done=0, total=0)
        try:
            rep = run_eval(use_llm=bool(use_llm), limit=limit,
                           progress=lambda n, t: _eval_state.update(done=n, total=t))
            _eval_state["report"] = rep
            (config.DATA_DIR / "last_eval.json").write_text(json.dumps(rep))
        finally:
            _eval_state["running"] = False

    threading.Thread(target=job, daemon=True).start()
    return RedirectResponse("/evaluate", status_code=303)


@app.get("/api/evaluate/status")
def evaluate_status():
    return {k: _eval_state[k] for k in ("running", "done", "total")}
