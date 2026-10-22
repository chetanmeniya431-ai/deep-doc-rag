"""Whole-document steps that one page cannot do alone:

- the body font size (to tell headings and footnotes from normal text)
- running headers/footers: lines that repeat on many pages are noise
- heading levels and the section path of every element
- tables that continue on the next page (same header) are joined into one
"""
from __future__ import annotations

import re
from collections import Counter

import fitz

from .layout import Element, PageParse


def body_font_size(doc: fitz.Document, sample: int = 40) -> float:
    sizes: Counter = Counter()
    step = max(1, len(doc) // sample)
    for i in range(0, len(doc), step):
        for b in doc[i].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    sizes[round(s["size"], 1)] += len(s["text"])
    return sizes.most_common(1)[0][0] if sizes else 10.0


def _sig(text: str) -> str:
    return re.sub(r"\d+", "#", text.lower()).strip()


def drop_running_lines(pages: list[PageParse]) -> int:
    """Remove text that repeats near the top or bottom of many pages."""
    counts: Counter = Counter()
    for p in pages:
        seen = set()
        for e in p.elements:
            if e.kind in ("text", "heading") and (e.bbox[1] < p.height * 0.1 or e.bbox[3] > p.height * 0.9):
                seen.add(_sig(e.text))
        counts.update(seen)
    limit = max(3, len(pages) * 0.25)
    noisy = {s for s, n in counts.items() if n >= limit}
    removed = 0
    for p in pages:
        keep = []
        for e in p.elements:
            edge = e.bbox[1] < p.height * 0.1 or e.bbox[3] > p.height * 0.9
            if edge and e.kind in ("text", "heading") and _sig(e.text) in noisy:
                removed += 1
                continue
            keep.append(e)
        p.elements = keep
    return removed


def assign_sections(pages: list[PageParse], outline: list) -> None:
    """Give headings a level and every element its section path ("Chapter 3 > Water")."""
    toc_level = {_sig(t[1]): t[0] for t in outline}
    sizes = sorted({round(e.size, 1) for p in pages for e in p.elements if e.kind == "heading"}, reverse=True)
    for p in pages:
        for e in p.elements:
            if e.kind == "heading":
                e.level = toc_level.get(_sig(e.text)) or (sizes.index(round(e.size, 1)) + 1 if round(e.size, 1) in sizes else 3)
                e.level = min(e.level, 4)
    stack: list[tuple[int, str]] = []
    for p in pages:
        for e in p.elements:
            if e.kind == "heading":
                while stack and stack[-1][0] >= e.level:
                    stack.pop()
                stack.append((e.level, e.text))
            e.meta["section"] = " > ".join(t for _, t in stack)


def join_continued_tables(pages: list[PageParse]) -> None:
    """A table at the top of a page with the same header as the last table on the page
    before is the same table. Give all parts one group id and the shared caption."""
    group = 0
    last: Element | None = None
    members: dict[int, list[Element]] = {}
    for p in pages:
        tables = [e for e in p.elements if e.kind == "table"]
        for i, t in enumerate(tables):
            first_on_page = i == 0 and not any(e.kind in ("text", "heading") and e.order < t.order and e.column == -1
                                               for e in p.elements if len(e.text) > 120)
            same = (last is not None and first_on_page and last.page == p.number - 1
                    and last.meta.get("header") == t.meta.get("header"))
            if not same:
                group += 1
            t.meta["group"] = group
            members.setdefault(group, []).append(t)
            last = t
        if any(e.kind in ("text", "heading") for e in p.elements if tables and e.order > tables[-1].order and len(e.text) > 200):
            last = None
    for parts in members.values():
        cap = next((t.meta.get("caption") for t in parts if t.meta.get("caption")), None)
        for n, t in enumerate(parts, 1):
            if cap and not t.meta.get("caption"):
                t.meta["caption"] = cap
            t.meta["part"] = f"{n} of {len(parts)}" if len(parts) > 1 else ""
