"""Chunking that follows the document's structure, not a fixed character count.

- Text: the paragraphs of one section are read as one stream (so a sentence cut by
  a column or page break is whole again), then cut into ~150-word windows on
  sentence ends.
- Tables: one chunk for the whole table (as Markdown) plus one chunk per row
  written as "column: value" pairs, so a single cell can be found by meaning.
- Figures and side boxes: one chunk each, with the caption and any read-out data.

Every chunk starts with a context line (document › section) before it is
embedded. Without it, "the leakage rate was 12%" is the same in all 12 regions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .layout import Element, PageParse

SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(\[])")
TARGET_WORDS = 150
MAX_WORDS = 220


@dataclass
class Chunk:
    kind: str
    section: str
    text: str
    pages: list[int]
    boxes: list[dict]
    meta: dict = field(default_factory=dict)
    embed_text: str = ""


def _box(e: Element) -> dict:
    return {"page": e.page, "bbox": [round(v, 1) for v in e.bbox]}


def _ctx(title: str, section: str) -> str:
    return f"{title} › {section}" if section else title


def build_chunks(pages: list[PageParse], title: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    stream: list[tuple[str, Element]] = []
    stream_section = None

    def flush():
        nonlocal stream
        if stream:
            chunks.extend(_text_windows(stream, stream_section, title))
        stream = []

    for p in pages:
        for e in p.elements:
            section = e.meta.get("section", "")
            if e.kind in ("text", "footnote", "heading") and section != stream_section:
                flush()
                stream_section = section
            if e.kind == "text":
                stream.append((e.text, e))
            elif e.kind == "footnote":
                stream.append((f"(Footnote {e.text})", e))
                # Also on its own: inside a 150-word window a one-line footnote is easy to miss.
                chunks.append(Chunk("footnote", section, f"Footnote: {e.text.replace('[^', '').replace(']', '', 1)}",
                                    [e.page], [_box(e)]))
            elif e.kind == "box":
                chunks.append(Chunk("box", section, f"Side box: {e.text}", [e.page], [_box(e)]))
            elif e.kind == "figure":
                cap = e.meta.get("caption", "")
                body = e.text or "(no readable text in this figure)"
                if e.meta.get("vlm"):
                    body += "\nDescription: " + e.meta["vlm"]
                chunks.append(Chunk("figure", section, f"{cap}\n{body}".strip(), [e.page], [_box(e)],
                                    meta={"caption": cap, "source": e.meta.get("source")}))
            elif e.kind == "table":
                chunks.extend(_table_chunks(e, section))
    flush()
    for c in chunks:
        label = {"table": "Table", "table_row": "Table row", "figure": "Figure", "box": "Side box", "footnote": "Footnote"}.get(c.kind, "")
        c.embed_text = f"{_ctx(title, c.section)}\n{label + ': ' if label and not c.text.startswith(label) else ''}{c.text}"
    return chunks


def _text_windows(stream: list[tuple[str, Element]], section: str, title: str) -> list[Chunk]:
    # Sentences with the element they came from. Paragraphs that end without a full
    # stop continue in the next element (column or page break in mid-sentence).
    sents: list[tuple[str, list[Element]]] = []
    carry, carry_els = "", []
    for text, el in stream:
        text = (carry + " " + text).strip() if carry else text
        parts = SENT_RE.split(text)
        first_els = carry_els + [el]
        if parts and not re.search(r"[.!?:)\]”\"]\s*$", parts[-1]):
            tail = parts.pop()
            carry, carry_els = tail, (first_els if not parts else [el])
        else:
            carry, carry_els = "", []
        sents += [(s, first_els if i == 0 else [el]) for i, s in enumerate(parts) if s.strip()]
    if carry:
        sents.append((carry, carry_els))

    out, cur, words = [], [], 0
    for s, els_ in sents:
        n = len(s.split())
        if cur and (words + n > MAX_WORDS or words >= TARGET_WORDS):
            out.append(cur)
            cur = cur[-1:] if len(cur[-1][0].split()) < 40 else []  # one sentence overlap
            words = sum(len(x[0].split()) for x in cur)
        cur.append((s, els_))
        words += n
    if cur:
        out.append(cur)
    chunks = []
    for win in out:
        els = []
        for _, sent_els in win:
            for el in sent_els:
                if el not in els:
                    els.append(el)
        chunks.append(Chunk("text", section, " ".join(s for s, _ in win),
                            sorted({e.page for e in els}), [_box(e) for e in els]))
    return chunks


def _table_chunks(e: Element, section: str) -> list[Chunk]:
    header, rows = e.meta.get("header") or [], e.meta.get("rows") or []
    cap = e.meta.get("caption", "")
    part = e.meta.get("part", "")
    name = cap or "Table"
    out = []
    head = f"{name}{' (part ' + part + ')' if part else ''}"
    for i in range(0, max(len(rows), 1), 25):
        block = rows[i:i + 25]
        md = "| " + " | ".join(header) + " |\n|" + "---|" * len(header) + "\n" + \
             "\n".join("| " + " | ".join(r) + " |" for r in block)
        out.append(Chunk("table", section, f"{head}\n{md}", [e.page], [_box(e)],
                         meta={"caption": cap, "group": e.meta.get("group")}))
    for r in rows:
        pairs = "; ".join(f"{h or 'Column'}: {v}" for h, v in zip(header, r) if v)
        if pairs:
            out.append(Chunk("table_row", section, f"{name} — row: {pairs}", [e.page], [_box(e)],
                             meta={"caption": cap, "group": e.meta.get("group")}))
    return out
