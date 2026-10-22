"""Ingest one PDF: parse every page, fix document-level structure, chunk, embed, store."""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import fitz

from .. import config
from ..generate import llm
from ..index import models, store
from .chunker import build_chunks
from .layout import parse_page
from .structure import assign_sections, body_font_size, drop_running_lines, join_continued_tables


def _set_status(name: str, status: str, message: str = "", **extra) -> None:
    with store.db() as con:
        con.execute("UPDATE documents SET status=?, message=? WHERE name=?", (status, message, name))
        for k, v in extra.items():
            con.execute(f"UPDATE documents SET {k}=? WHERE name=?", (v, name))


def ingest_pdf(path: str, progress=print) -> dict:
    path = str(path)
    name = Path(path).name
    t0 = time.time()
    doc = fitz.open(path)
    title = (doc.metadata or {}).get("title") or Path(path).stem.replace("-", " ").title()
    with store.db() as con:
        old = con.execute("SELECT id FROM documents WHERE name=?", (name,)).fetchone()
        if old:
            con.execute("DELETE FROM chunks WHERE doc_id=?", (old["id"],))
            con.execute("DELETE FROM elements WHERE doc_id=?", (old["id"],))
            con.execute("DELETE FROM documents WHERE id=?", (old["id"],))
        con.execute("INSERT INTO documents(name, path, title, pages, status) VALUES (?,?,?,?,?)",
                    (name, path, title, len(doc), "parsing"))
        doc_id = con.execute("SELECT id FROM documents WHERE name=?", (name,)).fetchone()["id"]
    store.invalidate_cache()

    try:
        body = body_font_size(doc)
        pages = []
        for i, page in enumerate(doc):
            pages.append(parse_page(page, body_size=body))
            if (i + 1) % 10 == 0 or i + 1 == len(doc):
                progress(f"{name}: parsed {i + 1}/{len(doc)} pages")
                _set_status(name, "parsing", f"Parsed {i + 1} of {len(doc)} pages")
        removed = drop_running_lines(pages)
        assign_sections(pages, doc.get_toc())
        join_continued_tables(pages)

        if config.VLM_MODEL:
            figs = [(p, e) for p in pages for e in p.elements if e.kind == "figure"]
            for n, (p, e) in enumerate(figs, 1):
                png = doc[p.number - 1].get_pixmap(clip=fitz.Rect(e.bbox), matrix=fitz.Matrix(2, 2)).tobytes("png")
                e.meta["vlm"] = llm.describe_image(png, e.meta.get("caption", ""))
                _set_status(name, "parsing", f"Vision model read figure {n} of {len(figs)}")

        chunks = build_chunks(pages, title)
        _set_status(name, "embedding", f"Embedding {len(chunks)} chunks")
        progress(f"{name}: embedding {len(chunks)} chunks")
        vecs = models.embed_passages([c.embed_text for c in chunks])

        kinds = Counter(e.kind for p in pages for e in p.elements)
        with store.db() as con:
            con.executemany(
                "INSERT INTO elements(doc_id, page, ord, kind, col, bbox, text, section, meta) VALUES (?,?,?,?,?,?,?,?,?)",
                [(doc_id, e.page, e.order, e.kind, e.column, json.dumps([round(v, 1) for v in e.bbox]), e.text,
                  e.meta.get("section", ""),
                  json.dumps({k: v for k, v in e.meta.items() if k in ("caption", "source", "pairs", "header", "rows", "part", "group", "vlm")}))
                 for p in pages for e in p.elements])
            con.executemany(
                "INSERT INTO chunks(doc_id, seq, kind, section, pages, boxes, text, embed_text, meta, vector) VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(doc_id, i, c.kind, c.section, json.dumps(c.pages), json.dumps(c.boxes), c.text, c.embed_text,
                  json.dumps(c.meta), vecs[i].tobytes()) for i, c in enumerate(chunks)])
        stats = {"elements": dict(kinds), "chunks": dict(Counter(c.kind for c in chunks)),
                 "running_lines_removed": removed, "body_font": body, "seconds": round(time.time() - t0, 1)}
        _set_status(name, "ready", f"Ready in {stats['seconds']} s", stats=json.dumps(stats))
        store.invalidate_cache()
        progress(f"{name}: ready — {json.dumps(stats)}")
        return stats
    except Exception as exc:
        _set_status(name, "failed", f"{type(exc).__name__}: {exc}")
        raise
