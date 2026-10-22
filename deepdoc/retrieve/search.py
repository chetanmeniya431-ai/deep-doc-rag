"""Hybrid retrieval: keyword (BM25) + meaning (vectors), fused, then re-ranked.

1. Query analysis: spot "table 3.2", "figure 5.1" or "page 40" and use them.
2. BM25 through SQLite FTS5 — exact names and numbers ("ASH-104", "Q3").
3. Dense search with bge-small embeddings — wording that differs from the text.
4. Reciprocal Rank Fusion merges both lists without tuning weights.
5. A cross-encoder reads (question, chunk) pairs and orders the final list.
"""
from __future__ import annotations

import json
import re
import time

import numpy as np

from .. import config
from ..index import models, store

STOP = set("""a an and are as at be by did do does for from had has have how in is it its of on or that the
their there this to was were what when where which who whom why with during according much many""".split())
REF_RE = re.compile(r"\b(table|figure|fig\.?|chart)\s+([a-z]?\d+(?:\.\d+)?)", re.I)
PAGE_RE = re.compile(r"\bpage\s+(\d{1,4})\b", re.I)


AGG_RE = re.compile(r"\b(most|highest|lowest|largest|smallest|least|fewest|biggest|best|worst|rank|compare|"
                    r"which (region|one|project|area|country|department|year)|all (regions|projects))\b", re.I)


def analyse(query: str) -> dict:
    aggregate = bool(AGG_RE.search(query))
    refs = [(m.group(1).lower().rstrip("."), m.group(2).upper()) for m in REF_RE.finditer(query)]
    pages = [int(p) for p in PAGE_RE.findall(query)]
    terms = [t for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]*", query) if t.lower() not in STOP]
    return {"refs": refs, "pages": pages, "terms": terms, "aggregate": aggregate}


def _fts(terms: list[str], limit: int) -> list[int]:
    if not terms:
        return []
    q = " OR ".join('"' + t.replace('"', "") + '"' for t in terms)
    with store.db() as con:
        try:
            rows = con.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?",
                               (q, limit)).fetchall()
        except Exception:
            return []
    return [r["rowid"] for r in rows]


def _dense(query: str, limit: int) -> list[int]:
    m, ids = store.vectors()
    if not ids:
        return []
    scores = m @ models.embed_query(query)
    top = np.argsort(-scores)[:limit]
    return [ids[i] for i in top]


def _ref_hits(refs, pages) -> list[int]:
    if not refs and not pages:
        return []
    with store.db() as con:
        out = []
        for kind, num in refs:
            word = "Table" if kind == "table" else "Figure"
            out += [r["id"] for r in con.execute(
                "SELECT id FROM chunks WHERE text LIKE ? AND kind IN ('table','figure','table_row') LIMIT 30",
                (f"{word} {num}:%",)).fetchall()]
        for p in pages:
            rows = con.execute("SELECT id, pages FROM chunks WHERE pages LIKE ?", (f"%{p}%",)).fetchall()
            out += [r["id"] for r in rows if p in json.loads(r["pages"])][:30]
        return out


def rrf(lists: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    score: dict[int, float] = {}
    for lst in lists:
        for rank, cid in enumerate(lst):
            score[cid] = score.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(score.items(), key=lambda x: -x[1])


def search(query: str, top_k: int | None = None, candidates: int | None = None, rerank: bool = True) -> dict:
    qa = analyse(query)
    # Superlative / comparison questions need one fact from every chapter, not the 6 best overall.
    if qa["aggregate"]:
        top_k = max(top_k or config.TOP_K, 14)
        candidates = max(candidates or config.CANDIDATES, 90)
    top_k = top_k or config.TOP_K
    candidates = candidates or config.CANDIDATES
    t0 = time.time()
    bm25 = _fts(qa["terms"], candidates)
    dense = _dense(query, candidates)
    refs = _ref_hits(qa["refs"], qa["pages"])
    fused = rrf([bm25, dense] + ([refs, refs] if refs else []))[:candidates]
    rows = store.chunk_rows([cid for cid, _ in fused])
    cands = [dict(rows[cid], rrf=s) for cid, s in fused if cid in rows]
    t1 = time.time()
    if rerank and cands:
        scores = models.rerank(query, [c["embed_text"][:900] for c in cands])
        for c, s in zip(cands, scores):
            c["rerank"] = s
            c["score"] = s + (2.0 if c["id"] in refs else 0.0)
        cands.sort(key=lambda c: -c["score"])
    else:
        for c in cands:
            c["score"] = c["rrf"]
    hits = _diversify(cands, top_k, per_section=1 if qa["aggregate"] else 0)
    return {"query": query, "analysis": qa, "hits": hits,
            "timing": {"retrieve_ms": round((t1 - t0) * 1000), "rerank_ms": round((time.time() - t1) * 1000)},
            "counts": {"bm25": len(bm25), "dense": len(dense), "fused": len(fused)}}


def _diversify(cands: list[dict], k: int, per_section: int = 0) -> list[dict]:
    """Avoid filling every slot with near-copies: max 3 rows of one table, no exact duplicate text.
    With per_section, keep at most that many hits per top-level section (one per chapter)."""
    out, per_table, seen, sections = [], {}, set(), {}
    for c in cands:
        key = c["text"][:200]
        if key in seen:
            continue
        if per_section and c["kind"] not in ("table", "table_row"):
            top = (c["section"] or "").split(" > ")[0]
            if sections.get(top, 0) >= per_section:
                continue
            sections[top] = sections.get(top, 0) + 1
        g = c["meta"].get("group")
        if c["kind"] == "table_row" and g is not None:
            if per_table.get(g, 0) >= 3:
                continue
            per_table[g] = per_table.get(g, 0) + 1
        seen.add(key)
        out.append(c)
        if len(out) >= k:
            break
    return out
