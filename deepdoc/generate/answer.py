"""Answer a question from retrieved chunks, with numbered citations.

With an LLM (Ollama): the model must answer only from the numbered sources and cite them.
Without an LLM: "quote mode" returns the best matching sentences or table rows word
for word. It never invents anything, so it is a safe fallback on weak machines.
"""
from __future__ import annotations

import re
import time

from ..retrieve.search import STOP, search
from . import llm

SYSTEM = """You answer questions about documents using ONLY the numbered sources given.
Rules:
- Use only facts found in the sources. Do not guess.
- Copy numbers exactly as written in the sources.
- Put the source number in square brackets after each fact, like [2].
- Tables are given as Markdown or as "column: value" rows. Read the column names carefully.
- Chart sources contain values read from the chart image or drawing. Pick the line whose label matches the question.
- A [0] calculator or lookup result is exact: use its value and cite [0].
- For "which is highest / most / lowest" questions, list the value from each source, then compare them.
- If the sources do not contain the answer, say: "The document does not say."
- Answer in 1 to 3 short sentences."""

KIND_LABEL = {"text": "text", "table": "table", "table_row": "table row", "figure": "chart/figure", "box": "side box"}


def _key_sentences(text: str, terms: set[str], keep: int = 2) -> str:
    """Only the sentences that share words with the question (keeps 14 sources inside a small model's context)."""
    sents = re.split(r"(?<=[.!?])\s+", text)
    scored = sorted(sents, key=lambda s: -len(terms & {w.lower().strip(".,;:") for w in s.split()}))
    best = set(scored[:keep])
    return " ".join(s for s in sents if s in best)


MAX_RE = re.compile(r"\b(highest|most|largest|biggest|greatest|top|maximum)\b", re.I)
MIN_RE = re.compile(r"\b(lowest|least|smallest|fewest|minimum|bottom)\b", re.I)
TOTAL_RE = re.compile(r"^(all|total|sum|overall|average)\b", re.I)


def _num(v: str):
    m = re.fullmatch(r"\s*[-+]?[\d,]*\.?\d+\s*%?\s*", v or "")
    return float(v.replace(",", "").replace("%", "")) if m else None


def table_extreme(question: str, hits: list[dict]) -> dict | None:
    """Tiny calculator tool: for "which X has the highest Y" questions, read the
    retrieved table and find the max/min in Python. Small LLMs are bad at this."""
    want = "max" if MAX_RE.search(question) else "min" if MIN_RE.search(question) else None
    if not want:
        return None
    terms = {t.lower() for t in re.findall(r"[A-Za-z]+", question) if t.lower() not in STOP}
    for h in hits:
        if h["kind"] != "table":
            continue
        lines = [l for l in h["text"].splitlines() if l.startswith("|")]
        if len(lines) < 3:
            continue
        header = [c.strip() for c in lines[0].strip("|").split("|")]
        rows = [[c.strip() for c in l.strip("|").split("|")] for l in lines[2:]]
        for ci, name in enumerate(header):
            if ci == 0 or not terms & {w.lower() for w in re.findall(r"[A-Za-z]+", name)}:
                continue
            vals = [(r[0], _num(r[ci])) for r in rows if len(r) > ci and not TOTAL_RE.match(r[0])]
            vals = [(k, v) for k, v in vals if v is not None]
            if len(vals) < 2:
                continue
            k, v = (max if want == "max" else min)(vals, key=lambda x: x[1])
            caption = h["text"].splitlines()[0]
            return {"text": f"Computed from {caption}: the {'highest' if want == 'max' else 'lowest'} "
                            f"{name} is {k} ({r_fmt(v)}), out of {len(vals)} rows.",
                    "pages": h["pages"], "row": k}
    return None


def chart_lookup(question: str, hits: list[dict]) -> dict | None:
    """Exact lookup tool: the question names a label ("Q3", "March") that the top chart has."""
    for h in hits[:3]:
        if h["kind"] != "figure" or "Chart values: " not in h["text"]:
            continue
        vals = h["text"].split("Chart values: ", 1)[1].split("\n", 1)[0]
        pairs = [p.split(":", 1) for p in vals.split(";") if ":" in p]
        found = [(k.strip(), v.strip()) for k, v in pairs if re.search(rf"\b{re.escape(k.strip())}\b", question, re.I)]
        if len(found) == 1:
            caption = h["text"].splitlines()[0]
            # "row" is what a correct answer must contain: the value, not the label.
            return {"text": f"Looked up in {caption}: {found[0][0]} = {found[0][1]}.", "pages": h["pages"], "row": found[0][1]}
    return None


GENERIC = {"which", "region", "regions", "highest", "most", "largest", "biggest", "greatest", "top", "maximum",
           "lowest", "least", "smallest", "fewest", "minimum", "bottom", "one", "all"}
NUM_IN_TEXT = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?")


def text_extreme(question: str, hits: list[dict]) -> dict | None:
    """Comparison tool for facts spread over many chapters: take the best-matching
    sentence from each chapter, read its number, and compare in Python."""
    want = "max" if MAX_RE.search(question) else "min" if MIN_RE.search(question) else None
    if not want:
        return None
    keys = [t.lower() for t in re.findall(r"[A-Za-z]+", question) if t.lower() not in STOP and t.lower() not in GENERIC]
    if not keys:
        return None
    stems = {k[:5] for k in keys}
    per_section: dict[str, tuple[int, float, list]] = {}
    for h in hits:
        if h["kind"] != "text":
            continue
        top = (h["section"] or "").split(" > ")[0]
        label = re.sub(r"^(chapter|section|part)\s+\S+\s*[—:-]\s*", "", top, flags=re.I).replace(" Region", "").strip()
        for sent in re.split(r"(?<=[.!?])\s+", h["text"]):
            score = len(stems & {w.lower()[:5] for w in re.findall(r"[A-Za-z]+", sent)})
            nums = [float(n.replace(",", "")) for n in NUM_IN_TEXT.findall(sent)]
            nums = [n for n in nums if not 1900 <= n <= 2100]  # skip years
            if score and nums and score > per_section.get(label, (0,))[0]:
                per_section[label] = (score, max(nums), h["pages"])
    best_score = max((v[0] for v in per_section.values()), default=0)
    vals = {k: v for k, v in per_section.items() if v[0] == best_score and k}
    if len(vals) < 3:
        return None
    k = (max if want == "max" else min)(vals, key=lambda x: vals[x][1])
    listing = ", ".join(f"{name}: {r_fmt(v[1])}" for name, v in sorted(vals.items(), key=lambda x: -x[1][1]))
    return {"text": f"Compared {len(vals)} sections. The {'highest' if want == 'max' else 'lowest'} is {k} "
                    f"({r_fmt(vals[k][1])}). All values: {listing}.", "pages": vals[k][2], "row": k}


def table_cell_lookup(question: str, hits: list[dict]) -> dict | None:
    """Exact lookup tool for wide tables: the question names one row (its first cell)
    and one column header, e.g. "Brenvale" + "June" -> the cell under "Jun"."""
    qwords = {w.lower() for w in re.findall(r"[A-Za-z0-9]+", question)}
    ql = question.lower()
    for h in hits[:4]:
        if h["kind"] != "table_row" or " — row: " not in h["text"]:
            continue
        caption, row = h["text"].split(" — row: ", 1)
        pairs = [p.split(": ", 1) for p in row.split("; ") if ": " in p]
        if len(pairs) < 3 or pairs[0][1].lower() not in ql:
            continue
        cols = []
        for name, val in pairs[1:]:
            words = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", name)]
            exact = words and all(w in qwords for w in words)
            prefix = len(words) == 1 and len(words[0]) >= 3 and any(q.startswith(words[0]) for q in qwords)
            if exact or prefix:
                cols.append((name, val))
        if len(cols) == 1:
            return {"text": f"Looked up in {caption}: {pairs[0][1]}, {cols[0][0]} = {cols[0][1]}.",
                    "pages": h["pages"], "row": cols[0][1]}
    return None


def r_fmt(v: float) -> str:
    return f"{v:,.1f}".rstrip("0").rstrip(".") if v % 1 else f"{int(v):,}"


def _source_block(hits: list[dict], question: str = "", compact: bool = False) -> str:
    terms = {t.lower() for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]*", question) if t.lower() not in STOP}
    parts = []
    for n, h in enumerate(hits, 1):
        pages = ", ".join(str(p) for p in h["pages"])
        text = _key_sentences(h["text"], terms) if compact and h["kind"] == "text" else h["text"]
        if h["kind"] == "figure" and "Chart values: " in text:
            # one value per line: small models misread long "a: 1; b: 2; ..." lists
            head, _, rest = text.partition("Chart values: ")
            vals, _, tail = rest.partition("\n")
            # The raw label dump stays in the search index, but it only confuses the LLM once
            # clean value pairs exist.
            tail = "\n".join(l for l in tail.splitlines() if not l.startswith("Text in chart:"))
            text = head + "Chart values:\n" + "\n".join("- " + v.strip() for v in vals.split(";")) + ("\n" + tail if tail else "")
        parts.append(f"[{n}] ({KIND_LABEL.get(h['kind'], h['kind'])}, page {pages}, section: {h['section'] or '-'})\n{text}")
    return "\n\n".join(parts)


def _quote_answer(question: str, hits: list[dict]) -> str:
    terms = {t.lower() for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9,.\-]*", question) if t.lower() not in STOP}
    best = []
    for n, h in enumerate(hits[:4], 1):
        if h["kind"] in ("table_row", "box", "figure"):
            units = [h["text"]]
        else:
            units = re.split(r"(?<=[.!?])\s+", h["text"])
        for u in units:
            words = {w.lower().strip(".,;:") for w in u.split()}
            overlap = len(terms & words) / (len(terms) or 1)
            best.append((overlap - 0.03 * (n - 1), u.strip(), n))
    best.sort(key=lambda x: -x[0])
    picked, seen = [], set()
    for _, u, n in best:
        if u not in seen:
            picked.append(f"{u} [{n}]")
            seen.add(u)
        if len(picked) == 2:
            break
    return "Quote mode (no LLM): " + " … ".join(picked) if picked else "The document does not say."


def answer(question: str, use_llm: bool = True, top_k: int | None = None) -> dict:
    t0 = time.time()
    res = search(question, top_k=top_k)
    hits = res["hits"]
    mode = "quote"
    text = ""
    if use_llm and hits:
        try:
            block = _source_block(hits, question, compact=res["analysis"].get("aggregate", False))
            calc = table_extreme(question, hits) or chart_lookup(question, hits) or table_cell_lookup(question, hits)
            if not calc and res["analysis"].get("aggregate"):
                calc = text_extreme(question, hits)
            if calc:
                block = f"[0] (calculator result, page {', '.join(map(str, calc['pages']))})\n{calc['text']}\n\n" + block
                res["calculator"] = calc
            text = llm.chat(SYSTEM, f"Sources:\n\n{block}\n\nQuestion: {question}\nAnswer:")
            mode = "llm"
            # Output check: a small model may ignore the exact tool result. If its answer does not
            # name what the tool found, show the tool result instead.
            if calc and calc["row"].lower() not in text.lower():
                text = f"{calc['text']} [0]\n(The language model's answer did not match this exact result, so the exact result is shown.)"
                mode = "llm+check"
        except llm.LLMUnavailable as exc:
            text = ""
            res["llm_error"] = str(exc)
    if not text:
        text = _quote_answer(question, hits)
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
    sources = [{"n": n, "id": h["id"], "page": h["pages"][0], "pages": h["pages"], "kind": h["kind"],
                "section": h["section"], "text": h["text"], "boxes": h["boxes"], "score": h["score"],
                "doc": h["doc_name"], "cited": n in cited}
               for n, h in enumerate(hits, 1)]
    return {"question": question, "answer": text, "mode": mode, "sources": sources,
            "timing": dict(res["timing"], total_ms=round((time.time() - t0) * 1000)),
            "analysis": res["analysis"], "llm_error": res.get("llm_error"), "calculator": res.get("calculator")}
