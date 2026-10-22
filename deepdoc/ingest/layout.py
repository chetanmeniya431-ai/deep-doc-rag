"""Page layout analysis: turns one PDF page into typed elements in reading order.

A PDF only stores "draw this glyph at x,y" and "draw this line". It has no idea of
paragraphs, columns or tables. This module rebuilds them from coordinates:

1. Graphics first: ruled tables (from horizontal rules + whitespace columns),
   fully boxed tables, side boxes, vector charts and raster images.
2. Text lines that fall inside those regions belong to them; the rest become
   paragraphs, headings, captions and footnotes.
3. Reading order: full-width elements cut the page into horizontal bands; inside
   a band we read the left column top to bottom, then the right column.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import fitz

CAPTION_RE = re.compile(r"^(figure|fig\.|table|chart|exhibit|graph)\s+[a-z]?\d*[\d.]*[a-z]?\s*[:.\-—]", re.I)
SHORT_WORDS = {"a", "an", "of", "to", "in", "on", "at", "by", "or", "as", "is", "it", "be", "we", "do", "so",
               "no", "up", "if", "and", "the", "for"}
NUM_RE = re.compile(r"^[-+]?\(?\d[\d,]*\.?\d*\)?%?$")


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    bold: bool

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class Element:
    kind: str                       # heading | text | caption | footnote | table | figure | box
    text: str
    bbox: tuple
    page: int
    column: int = -1                # -1 = spans the page width
    order: int = 0
    level: int = 0                  # heading level (1 = chapter)
    size: float = 0.0
    meta: dict = field(default_factory=dict)


@dataclass
class PageParse:
    number: int
    width: float
    height: float
    elements: list


# ───────────────────────── helpers ─────────────────────────

def _overlap(a, b) -> float:
    """Area of a∩b divided by area of a."""
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    area = max((a[2] - a[0]) * (a[3] - a[1]), 1e-6)
    return (x1 - x0) * (y1 - y0) / area


def _inside(b, region, pad=1.5) -> bool:
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return region[0] - pad <= cx <= region[2] + pad and region[1] - pad <= cy <= region[3] + pad


def _union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _is_bold(span) -> bool:
    return bool(span["flags"] & 16) or "bold" in span["font"].lower()


def page_words_and_lines(page: fitz.Page):
    """Words (with font info) and text lines from the rawdict output."""
    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP)
    words: list[Word] = []
    lines = []
    for block in raw["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            if abs(line["dir"][1]) > 0.5:  # skip rotated text such as vertical axis titles
                continue
            spans = []
            for span in line["spans"]:
                chars = span["chars"]
                text = "".join(c["c"] for c in chars)
                if not text.strip():
                    continue
                spans.append({"text": text, "size": span["size"], "bold": _is_bold(span),
                              "bbox": span["bbox"], "flags": span["flags"]})
                cur = []
                for c in chars + [None]:
                    if c is None or c["c"].isspace():
                        if cur:
                            words.append(Word("".join(x["c"] for x in cur), cur[0]["bbox"][0], min(x["bbox"][1] for x in cur),
                                              cur[-1]["bbox"][2], max(x["bbox"][3] for x in cur), span["size"], _is_bold(span)))
                            cur = []
                    else:
                        cur.append(c)
            if spans:
                lines.append({"bbox": tuple(line["bbox"]), "spans": spans})
    return words, _merge_split_lines(lines)


def _merge_split_lines(lines):
    """Justified text makes wide gaps, and PDF tools then cut one line into pieces.
    Glue pieces that share a baseline and sit closer than a column gutter."""
    lines = sorted(lines, key=lambda l: (round(l["bbox"][3]), l["bbox"][0]))
    out = []
    for l in lines:
        if out:
            p = out[-1]
            size = max(s["size"] for s in l["spans"])
            gap = l["bbox"][0] - p["bbox"][2]
            if abs(p["bbox"][3] - l["bbox"][3]) < 1.5 and -1 < gap < min(14, 1.6 * size):
                p["spans"] = p["spans"] + [dict(l["spans"][0], text=" " + l["spans"][0]["text"])] + l["spans"][1:]
                p["bbox"] = _union([p["bbox"], l["bbox"]])
                continue
        out.append({"bbox": l["bbox"], "spans": list(l["spans"])})
    return out


# ───────────────────────── graphics: tables, boxes, charts ─────────────────────────

def _graphics(page: fitz.Page):
    hrules, vrules, fills = [], [], []
    for d in page.get_drawings():
        r = d["rect"]
        for item in d["items"]:
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) < 0.8 and abs(p1.x - p2.x) > 4:
                    hrules.append((min(p1.x, p2.x), p1.y, max(p1.x, p2.x), d.get("width") or 0.5))
                elif abs(p1.x - p2.x) < 0.8 and abs(p1.y - p2.y) > 4:
                    vrules.append((p1.x, min(p1.y, p2.y), max(p1.y, p2.y)))
            elif item[0] == "re" and d.get("fill") is not None:
                rr = item[1]
                if rr.width > 1 and rr.height > 1:
                    fills.append((rr.x0, rr.y0, rr.x1, rr.y1, tuple(d["fill"])))
        if d["type"] == "f" and not d["items"]:
            fills.append((r.x0, r.y0, r.x1, r.y1, tuple(d.get("fill") or ())))
    return hrules, vrules, fills


def _find_boxes(hrules, vrules, page_w):
    """Closed rectangles drawn with four lines: side boxes / callouts."""
    boxes = []
    for (x0, y, x1, _w) in hrules:
        if x1 - x0 < 80:
            continue
        for (xb0, yb, xb1, _w2) in hrules:
            if yb - y < 18 or abs(xb0 - x0) > 1.5 or abs(xb1 - x1) > 1.5:
                continue
            left = any(abs(vx - x0) < 1.5 and vy0 <= y + 1.5 and vy1 >= yb - 1.5 for vx, vy0, vy1 in vrules)
            right = any(abs(vx - x1) < 1.5 and vy0 <= y + 1.5 and vy1 >= yb - 1.5 for vx, vy0, vy1 in vrules)
            if left and right:
                inner = [h for h in hrules if y + 2 < h[1] < yb - 2 and h[2] - h[0] > (x1 - x0) * 0.5]
                if not inner:
                    boxes.append((x0, y, x1, yb))
                break
    return boxes


def _find_ruled_tables(hrules, fills, boxes, words):
    """Tables drawn with horizontal rules only (very common in reports).

    Groups of 3+ rules that share the same left and right ends, stacked with
    gaps of less than ~45pt, form a table. Header background fills of the same
    width extend the region upward.
    """
    long_rules = sorted({(round(x0, 0), round(y, 1), round(x1, 0)) for x0, y, x1, _ in hrules if x1 - x0 > 60},
                        key=lambda r: (r[0], r[2], r[1]))
    groups: dict = {}
    for x0, y, x1 in long_rules:
        if any(_inside((x0, y, x1, y), b, pad=2) for b in boxes):
            continue
        groups.setdefault((x0, x1), []).append(y)
    regions = []
    for (x0, x1), ys in groups.items():
        ys = sorted(set(ys))
        run = [ys[0]]
        for y in ys[1:] + [None]:
            if y is not None and y - run[-1] < 45:
                run.append(y)
                continue
            if len(run) >= 3:
                top = run[0]
                same_fills = [f for f in fills if abs(f[0] - x0) < 2 and abs(f[2] - x1) < 2 and f[1] < top + 1 and f[3] >= top - 1]
                if same_fills:
                    top = min(top, min(f[1] for f in same_fills))
                else:
                    above = [w for w in words if x0 - 1 <= w.cx <= x1 + 1 and top - 16 < w.y1 <= top + 1]
                    if above:
                        top = min(w.y0 for w in above) - 1
                regions.append({"bbox": (x0, top, x1, run[-1]), "rules": run})
            if y is not None:
                run = [y]
    return regions


def _find_charts(page, taken, fills, words):
    """Vector charts: clusters of drawings that are not tables or boxes."""
    charts = []
    try:
        clusters = page.cluster_drawings(x_tolerance=8, y_tolerance=8)
    except Exception:
        return charts
    for c in clusters:
        bb = (c.x0, c.y0, c.x1, c.y1)
        if c.width < 70 or c.height < 50:
            continue
        if any(_overlap(bb, t) > 0.3 for t in taken):
            continue
        bars = [f for f in fills if _inside(f, bb, pad=2) and (f[2] - f[0]) < c.width * 0.4]
        # grow the region to hold value labels above bars and axis labels below
        grown = (bb[0] - 30, bb[1] - 16, bb[2] + 8, bb[3] + 16)
        inner = [w for w in words if _inside((w.x0, w.y0, w.x1, w.y1), grown, pad=0)]
        long_text = [w for w in inner if len(w.text) > 14]
        if len(inner) < 3 or len(long_text) > len(inner) * 0.3:
            continue
        region = _union([bb] + [(w.x0, w.y0, w.x1, w.y1) for w in inner])
        charts.append({"bbox": region, "plot": bb, "bars": bars})
    return charts


# ───────────────────────── table cells ─────────────────────────

def _column_bounds(body_words, x0, x1, min_gap=3.0):
    """Column edges from vertical strips of white space that no body word touches."""
    width = int(x1 - x0) + 1
    covered = [False] * width
    for w in body_words:
        for i in range(max(0, int(w.x0 - x0)), min(width, int(w.x1 - x0) + 1)):
            covered[i] = True
    bounds, gap_start = [x0], None
    for i, c in enumerate(covered + [True]):
        if not c and gap_start is None:
            gap_start = i
        elif c and gap_start is not None:
            if i - gap_start >= min_gap and gap_start > 0 and i < width:
                bounds.append(x0 + (gap_start + i) / 2)
            gap_start = None
    bounds.append(x1)
    return bounds


def _phrases(words, max_gap=5.0):
    """Join words on one line into phrases when they are close together."""
    out = []
    for w in sorted(words, key=lambda w: w.x0):
        if out and w.x0 - out[-1]["x1"] <= max_gap and abs(w.cy - out[-1]["cy"]) < 3:
            out[-1]["text"] += " " + w.text
            out[-1]["x1"] = w.x1
        else:
            out.append({"text": w.text, "x0": w.x0, "x1": w.x1, "cy": w.cy})
    return out


def _cluster_lines(words, tol=2.5):
    rows = []
    for w in sorted(words, key=lambda w: w.cy):
        if rows and abs(rows[-1][0] - w.cy) <= tol:
            rows[-1][1].append(w)
        else:
            rows.append([w.cy, [w]])
    return [r[1] for r in rows]


def build_table(region_bbox, row_edges, words, span_rules=()):
    """Cells from words. row_edges are y positions of full-width rules."""
    x0, top, x1, bottom = region_bbox
    tw = [w for w in words if _inside((w.x0, w.y0, w.x1, w.y1), (x0, top, x1, bottom + 2), pad=1)]
    if not tw:
        return None
    edges = sorted(set([top] + [e for e in row_edges if top + 2 < e <= bottom + 1] + [bottom + 2]))
    bands = []
    for a, b in zip(edges, edges[1:]):
        bw = [w for w in tw if a <= w.cy < b]
        if bw:
            bands.append(bw)
    # Header bands: leading bands where (almost) all words are bold.
    n_head = 0
    for bw in bands:
        if sum(w.bold for w in bw) >= len(bw) * 0.8:
            n_head += 1
        else:
            break
    body = [w for bw in bands[n_head:] for w in bw] or tw
    bounds = _column_bounds(body, x0, x1)
    ncol = len(bounds) - 1
    if ncol < 2:
        return None

    def col_of(x):
        for i in range(ncol):
            if x < bounds[i + 1]:
                return i
        return ncol - 1

    header_rows = []
    for bw in bands[:n_head]:
        for line in _cluster_lines(bw):
            hr = [""] * ncol
            header_rows.append(hr)
            for ph in _phrases(line):
                # Body-derived edges are rough (numbers are often right-aligned), so a label
                # only counts for a column when a good part of it sits over that column.
                pw = max(ph["x1"] - ph["x0"], 1)
                ov = [max(0.0, min(ph["x1"], bounds[i + 1]) - max(ph["x0"], bounds[i])) for i in range(ncol)]
                cols = [i for i in range(ncol) if ov[i] > pw * 0.35] or [max(range(ncol), key=lambda i: ov[i])]
                # A label centred on a column edge is a merged cell over both columns.
                pc = (ph["x0"] + ph["x1"]) / 2
                for i in range(1, ncol):
                    near = 0.2 * min(bounds[i] - bounds[i - 1], bounds[i + 1] - bounds[i])
                    if abs(pc - bounds[i]) < near:
                        cols = sorted(set(cols) | {i - 1, i})
                # A short rule just under a label marks a merged cell over the columns it covers.
                for r in span_rules:
                    if ph["cy"] < r[1] < ph["cy"] + 12 and r[0] - 3 <= ph["x0"] <= r[2]:
                        cols = [i for i in range(ncol) if r[0] - 2 <= (bounds[i] + bounds[i + 1]) / 2 <= r[2] + 2] or cols
                for c in cols:
                    hr[c] = (hr[c] + " " + ph["text"]).strip()
    # Lower header row has a label but the row above is empty there:
    # the upper label on its left is a merged cell (e.g. "Result" over "2024 | 2025").
    for up, low in zip(header_rows, header_rows[1:]):
        for c in range(1, ncol):
            if not up[c] and low[c] and up[c - 1] and low[c - 1]:
                up[c] = up[c - 1]
    header = [" ".join(hr[c] for hr in header_rows if hr[c]).strip() for c in range(ncol)]
    rows = []
    for bw in bands[n_head:]:
        cells = [""] * ncol
        cell_x1 = [0.0] * ncol   # right edge of the text on the previous line of each cell
        cell_max = [0.0] * ncol  # widest line seen in each cell
        for line in _cluster_lines(bw):
            first_in_line = set()
            for w in sorted(line, key=lambda w: w.x0):
                c = col_of(w.cx)
                frag = w.text.rstrip(".,;:")
                broken = (c not in first_in_line and cells[c] and cells[c][-1].isalnum()
                          and cell_x1[c] >= cell_max[c] - 1.0 and frag.lower() not in SHORT_WORDS
                          and (frag.isdigit() or (len(frag) <= 2 and frag.isalpha() and frag.islower())))
                if c not in first_in_line:
                    first_in_line.add(c)
                    if cells[c] and not broken:
                        cells[c] += " "
                elif cells[c]:
                    cells[c] += " "
                # A narrow cell can break a word with no hyphen ("Complete" / "d"): glue it back.
                cells[c] += w.text
                cell_x1[c] = w.x1
                cell_max[c] = max(cell_max[c], w.x1)
        rows.append([x.strip() for x in cells])
    if not n_head and rows:
        header, rows = [f"Column {i + 1}" for i in range(ncol)], rows
    return {"header": header, "rows": rows, "has_header": bool(n_head)}


def table_to_markdown(header, rows) -> str:
    esc = lambda s: (s or "").replace("|", "/")
    lines = ["| " + " | ".join(esc(h) for h in header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


# ───────────────────────── charts ─────────────────────────

def read_bar_chart(chart, words):
    """Pair each bar with the number just above it and the category label below the axis."""
    region = chart["bbox"]
    inner = [w for w in words if _inside((w.x0, w.y0, w.x1, w.y1), region, pad=0)]
    pairs = []
    if chart["bars"]:
        base = max(b[3] for b in chart["bars"])
        cats = [w for w in inner if w.y0 >= base - 1 and not NUM_RE.match(w.text)]
        for bar in sorted(chart["bars"], key=lambda b: b[0]):
            bcx = (bar[0] + bar[2]) / 2
            vals = [w for w in inner if NUM_RE.match(w.text) and bar[0] - 4 <= w.cx <= bar[2] + 4 and bar[1] - 16 <= w.y1 <= bar[1] + 3]
            cat = min(cats, key=lambda w: abs(w.cx - bcx), default=None)
            if vals and cat is not None and abs(cat.cx - bcx) < (bar[2] - bar[0]):
                pairs.append(f"{cat.text}: {vals[0].text}")
    lines = [" ".join(w.text for w in sorted(l, key=lambda w: w.x0)) for l in _cluster_lines(inner)]
    return pairs, lines


def ocr_region(page, bbox, zoom=3.0) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    pix = page.get_pixmap(clip=fitz.Rect(bbox), matrix=fitz.Matrix(zoom, zoom))
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    try:
        text = pytesseract.image_to_string(img, config="--psm 11")
    except Exception:
        return ""
    keep = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in keep if sum(ch.isalnum() for ch in ln) >= 2)


# ───────────────────────── main entry ─────────────────────────

def parse_page(page: fitz.Page, body_size: float | None = None, ocr: bool = True) -> PageParse:
    W, H = page.rect.width, page.rect.height
    pno = page.number + 1
    words, lines = page_words_and_lines(page)
    if body_size is None:
        sizes = Counter(round(s["size"], 1) for l in lines for s in l["spans"] for _ in s["text"])
        body_size = sizes.most_common(1)[0][0] if sizes else 10.0
    hrules, vrules, fills = _graphics(page)

    elements: list[Element] = []
    taken: list[tuple] = []

    boxes = _find_boxes(hrules, vrules, W)
    cap_boxes = [l["bbox"] for l in lines if CAPTION_RE.match("".join(s["text"] for s in l["spans"]).strip())]
    chart_words = [w for w in words if not any(_inside((w.x0, w.y0, w.x1, w.y1), cb, pad=0.5) for cb in cap_boxes)]

    def add_chart(ch):
        pairs, label_lines = read_bar_chart(ch, chart_words)
        taken.append(ch["bbox"])
        parts = []
        if pairs:
            parts.append("Chart values: " + "; ".join(pairs))
        parts.append("Text in chart: " + " / ".join(label_lines))
        elements.append(Element("figure", "\n".join(parts), ch["bbox"], pno, meta={"source": "vector", "pairs": pairs}))

    # 1. Charts with clear bars go first: their axes look like a grid to table finders.
    for ch in _find_charts(page, boxes, fills, chart_words):
        if len({round(b[1]) for b in ch["bars"]}) >= 2:
            add_chart(ch)

    # 2. Fully ruled tables (grids with vertical lines) via PyMuPDF.
    try:
        grid_tables = page.find_tables(strategy="lines").tables
    except Exception:
        grid_tables = []
    for t in grid_tables:
        bb = tuple(t.bbox)
        if t.row_count * t.col_count <= 1 or any(_overlap(bb, b) > 0.8 for b in boxes):
            continue
        if any(_overlap(bb, c) > 0.3 for c in taken):
            continue
        data = [[(c or "").replace("\n", " ").strip() for c in row] for row in t.extract()]
        cells = [c for row in data for c in row]
        if not data or sum(1 for c in cells if not c) > len(cells) * 0.6:
            continue
        header = [f"Column {i + 1}" for i in range(len(data[0]))]
        elements.append(Element("table", table_to_markdown(header, data), bb, pno,
                                meta={"header": header, "rows": data, "has_header": False, "grid": True}))
        taken.append(bb)

    for b in boxes:
        if any(_overlap(b, t) > 0.5 for t in taken):
            continue
        taken.append(b)
        bw = [l for l in lines if _inside(l["bbox"], b)]
        text = " ".join("".join(s["text"] for s in l["spans"]).strip() for l in bw)
        if text:
            elements.append(Element("box", text, b, pno))

    # 3. Tables drawn with horizontal rules only.
    for reg in _find_ruled_tables(hrules, fills, boxes + taken, words):
        if any(_overlap(reg["bbox"], t) > 0.5 for t in taken):
            continue
        rx0, _, rx1, _ = reg["bbox"]
        partial = [h for h in hrules if rx0 - 1 <= h[0] and h[2] <= rx1 + 1 and (h[2] - h[0]) < (rx1 - rx0) * 0.9
                   and reg["bbox"][1] - 1 <= h[1] <= reg["bbox"][3]]
        tab = build_table(reg["bbox"], reg["rules"], words, partial)
        if not tab:
            continue
        taken.append(reg["bbox"])
        elements.append(Element("table", table_to_markdown(tab["header"], tab["rows"]), reg["bbox"], pno, meta=tab))

    # 4. Other vector charts (lines, areas, pies) not claimed above.
    for ch in _find_charts(page, taken, fills, chart_words):
        add_chart(ch)

    # 5. Raster images (photos, charts saved as pictures): read them with OCR.
    for img in page.get_image_info():
        bb = tuple(img["bbox"])
        if (bb[2] - bb[0]) < 60 or (bb[3] - bb[1]) < 40 or any(_overlap(bb, t) > 0.5 for t in taken):
            continue
        taken.append(bb)
        text = ocr_region(page, bb) if ocr else ""
        elements.append(Element("figure", ("Text read from image (OCR): " + text.replace("\n", " / ")) if text else "",
                                bb, pno, meta={"source": "raster", "ocr": text}))

    # 6. Text lines outside those regions → blocks.
    free = [l for l in lines if not any(_inside(l["bbox"], t) for t in taken)]
    free = [l for l in free if not (l["bbox"][3] < H * 0.065 or l["bbox"][1] > H * 0.95)]  # running header/footer
    blocks = _group_lines(free, body_size)
    for blk in blocks:
        elements.append(_classify(blk, body_size, pno))

    _attach_captions(elements)
    _reading_order(elements, W)
    return PageParse(pno, W, H, elements)


def _line_text(line, body_size) -> str:
    out = ""
    for s in line["spans"]:
        t = s["text"]
        if s["size"] < body_size * 0.8 and t.strip().isdigit():
            t = f"[^{t.strip()}] "  # footnote marker
        out += t
    return out


def _group_lines(lines, body_size):
    """Lines → blocks: same column, small vertical gap, same style."""
    lines = sorted(lines, key=lambda l: (round(l["bbox"][1], 0), l["bbox"][0]))
    blocks: list[list] = []
    for l in lines:
        x0, y0, x1, y1 = l["bbox"]
        size = max(s["size"] for s in l["spans"])
        bold = all(s["bold"] for s in l["spans"])
        placed = False
        for blk in reversed(blocks[-6:]):
            last = blk[-1]
            lx0, ly0, lx1, ly1 = last["bbox"]
            lsize = max(s["size"] for s in last["spans"])
            lbold = all(s["bold"] for s in last["spans"])
            same_col = abs(lx0 - x0) < 12 or (x0 >= lx0 - 2 and x1 <= lx1 + 2)
            if same_col and 0 <= y0 - ly1 < size * 0.6 and abs(lsize - size) < 0.6 and lbold == bold:
                blk.append(l)
                placed = True
                break
        if not placed:
            blocks.append([l])
    return blocks


def _classify(blk, body_size, pno) -> Element:
    bbox = _union([l["bbox"] for l in blk])
    text = " ".join(_line_text(l, body_size).strip() for l in blk)
    text = re.sub(r"-\s+(?=[a-z])", "", text) if re.search(r"[a-z]-\s+[a-z]", text) else text
    text = re.sub(r"\s+", " ", text).strip()
    spans = [s for l in blk for s in l["spans"]]
    size = max(s["size"] for s in spans)
    bold = all(s["bold"] for s in spans if s["text"].strip())
    first = blk[0]["spans"][0]
    if CAPTION_RE.match(text):
        kind = "caption"
    elif size >= body_size * 1.12 and (bold or size >= body_size * 1.5) and len(text.split()) <= 16:
        kind = "heading"
    elif first["size"] < body_size * 0.8 and first["text"].strip().isdigit() and size < body_size * 0.95:
        kind = "footnote"
    elif text.startswith("[^") and size < body_size * 0.95:
        kind = "footnote"
    else:
        kind = "text"
    return Element(kind, text, bbox, pno, size=size)


def _attach_captions(elements):
    """Glue each caption to the nearest table/figure above it (or below it)."""
    targets = [e for e in elements if e.kind in ("table", "figure")]
    for cap in [e for e in elements if e.kind == "caption"]:
        best, dist = None, 60.0
        for t in targets:
            h_overlap = min(cap.bbox[2], t.bbox[2]) - max(cap.bbox[0], t.bbox[0])
            if h_overlap <= 0:
                continue
            d = cap.bbox[1] - t.bbox[3] if cap.bbox[1] >= t.bbox[3] - 3 else (t.bbox[1] - cap.bbox[3]) + 15
            if 0 - 3 <= d < dist and not t.meta.get("caption"):
                best, dist = t, d
        if best is not None:
            best.meta["caption"] = cap.text
            cap.meta["caption_of"] = id(best)


def _reading_order(elements, page_w):
    if not elements:
        return
    left = min(e.bbox[0] for e in elements)
    right = max(e.bbox[2] for e in elements)
    content_w = max(right - left, 1)
    mid = left + content_w / 2
    for e in elements:
        w = e.bbox[2] - e.bbox[0]
        if w > content_w * 0.62 or (e.bbox[0] < mid - 20 and e.bbox[2] > mid + 20):
            e.column = -1
        else:
            e.column = 0 if (e.bbox[0] + e.bbox[2]) / 2 < mid else 1
    spanning = sorted([e for e in elements if e.column == -1], key=lambda e: e.bbox[1])
    cols = [e for e in elements if e.column != -1]
    cuts = [s.bbox[1] for s in spanning] + [1e9]
    ordered, prev = [], -1e9
    for s, cut in zip(spanning + [None], cuts):
        seg = [e for e in cols if prev <= (e.bbox[1] + e.bbox[3]) / 2 < cut]
        ordered += sorted([e for e in seg if e.column == 0], key=lambda e: e.bbox[1])
        ordered += sorted([e for e in seg if e.column == 1], key=lambda e: e.bbox[1])
        if s is not None:
            ordered.append(s)
            prev = s.bbox[3] - 1
    for i, e in enumerate(ordered):
        e.order = i
    elements.sort(key=lambda e: e.order)
