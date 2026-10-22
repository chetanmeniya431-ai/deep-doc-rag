"""Score the system on the answer key that was made with the demo PDF.

Retrieval metrics (fast, no LLM):
- page hit@1 / hit@k: a top chunk comes from the page that holds the answer
- MRR: 1 / rank of the first chunk from a right page
- fact recall@k: every expected answer string appears in the top-k chunk text.
  This is the strictest check of parsing: if OCR or table reading lost the
  number, it cannot be found, whatever the page.
Answer metric (with --llm): every expected answer string appears in the answer.
"""
from __future__ import annotations

import json
import re
import time
from collections import defaultdict

from .. import config
from ..generate.answer import answer
from ..retrieve.search import search

MONTH_FULL = {m[:3].lower(): m.lower() for m in ["January", "February", "March", "April", "May", "June", "July",
                                                 "August", "September", "October", "November", "December"]}


def _n(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().replace(",", "")).strip()


def contains(hay: str, needle: str) -> bool:
    h, n = _n(hay), _n(needle)
    if n in h:
        return True
    return n in MONTH_FULL and MONTH_FULL[n] in h


def load_gold() -> list[dict]:
    return json.loads((config.PDF_DIR / config.DEMO_GOLD_NAME).read_text())


def run_eval(use_llm: bool = False, limit: int = 0, types: list[str] | None = None, progress=None) -> dict:
    gold = load_gold()
    if types:
        gold = [g for g in gold if g["type"] in types]
    if limit:
        # spread the sample over all question types
        by = defaultdict(list)
        for g in gold:
            by[g["type"]].append(g)
        gold, i = [], 0
        while len(gold) < limit and any(by.values()):
            for t in list(by):
                if by[t] and len(gold) < limit:
                    gold.append(by[t].pop(0))
    rows = []
    t0 = time.time()
    for n, g in enumerate(gold, 1):
        if use_llm:
            res = answer(g["q"])
            hits = [{"pages": s["pages"], "text": s["text"]} for s in res["sources"]]
            ans = res["answer"]
        else:
            hits = search(g["q"])["hits"]
            ans = ""
        rank = next((i + 1 for i, h in enumerate(hits) if set(h["pages"]) & set(g["pages"])), None)
        ctx = "\n".join(h["text"] for h in hits)
        row = {"id": g["id"], "type": g["type"], "q": g["q"], "answers": g["answers"], "pages": g["pages"],
               "rank": rank, "fact_in_context": all(contains(ctx, a) for a in g["answers"]),
               "top_pages": [h["pages"] for h in hits[:3]]}
        if use_llm:
            row["answer"] = ans
            row["answer_correct"] = all(contains(ans, a) for a in g["answers"])
        rows.append(row)
        if progress:
            progress(n, len(gold))
    return {"summary": summarise(rows, use_llm, time.time() - t0), "rows": rows}


def summarise(rows: list[dict], use_llm: bool, seconds: float) -> dict:
    def block(rs):
        n = len(rs) or 1
        out = {"n": len(rs),
               "hit@1": round(sum(r["rank"] == 1 for r in rs) / n, 3),
               f"hit@{config.TOP_K}": round(sum(r["rank"] is not None for r in rs) / n, 3),
               "mrr": round(sum(1 / r["rank"] for r in rs if r["rank"]) / n, 3),
               "fact_recall": round(sum(r["fact_in_context"] for r in rs) / n, 3)}
        if use_llm:
            out["answer_accuracy"] = round(sum(r.get("answer_correct", False) for r in rs) / n, 3)
        return out

    by = defaultdict(list)
    for r in rows:
        by[r["type"]].append(r)
    return {"overall": block(rows), "by_type": {t: block(rs) for t, rs in sorted(by.items())},
            "seconds": round(seconds, 1), "llm": use_llm}
