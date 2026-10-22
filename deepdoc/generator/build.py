"""Builds the 100–200 page demo report: "Velmora Integrated Annual Review 2025".

Hard parts packed in on purpose:
- two-column body text that the parser must read down, not across
- chapter opener pages: a full-width band on top, two columns below
- tables with merged header cells, a totals row, and a register that runs over many pages
- vector charts (text as scattered PDF glyphs) and raster charts (text only as pixels)
- side boxes, footnotes, running headers and footers (noise to strip)
- a landscape page with a 14-column table
"""
from __future__ import annotations

import io
import random
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, FrameBreak, Image, KeepTogether,
                                NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

from . import charts
from .facts import CAUSES, MONTHS, World
from .prose import chapter_intro, region_paragraphs

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu", boldItalic="DejaVu-Bold")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
GUTTER = 7 * mm
COL_W = (PAGE_W - 2 * MARGIN - GUTTER) / 2
FULL_W = PAGE_W - 2 * MARGIN
BAND_H = 330

GREY = colors.HexColor("#6b7280")
LIGHT = colors.HexColor("#eef2ff")
LINE = colors.HexColor("#d1d5db")
ACCENT = colors.HexColor("#4f46e5")

S = {
    "body": ParagraphStyle("body", fontName="DejaVu", fontSize=8.6, leading=11.4, alignment=TA_JUSTIFY, spaceAfter=5),
    "body1": ParagraphStyle("body1", fontName="DejaVu", fontSize=9.4, leading=13, spaceAfter=7),
    "h1": ParagraphStyle("h1", fontName="DejaVu-Bold", fontSize=17, leading=21, spaceAfter=8, textColor=colors.HexColor("#111827")),
    "h2": ParagraphStyle("h2", fontName="DejaVu-Bold", fontSize=10.5, leading=13, spaceBefore=7, spaceAfter=4, textColor=ACCENT),
    "cap": ParagraphStyle("cap", fontName="DejaVu", fontSize=7.2, leading=9, textColor=GREY, spaceBefore=2, spaceAfter=8),
    "cell": ParagraphStyle("cell", fontName="DejaVu", fontSize=7, leading=8.6),
    "cellb": ParagraphStyle("cellb", fontName="DejaVu-Bold", fontSize=7, leading=8.6),
    "foot": ParagraphStyle("foot", fontName="DejaVu", fontSize=6.6, leading=8, textColor=GREY, spaceBefore=3),
    "box": ParagraphStyle("box", fontName="DejaVu", fontSize=8, leading=10.5),
    "tile_n": ParagraphStyle("tile_n", fontName="DejaVu-Bold", fontSize=15, leading=18, alignment=TA_CENTER, textColor=ACCENT),
    "tile_l": ParagraphStyle("tile_l", fontName="DejaVu", fontSize=7.4, leading=9, alignment=TA_CENTER, textColor=GREY),
    "cover": ParagraphStyle("cover", fontName="DejaVu-Bold", fontSize=28, leading=34, textColor=colors.HexColor("#111827")),
    "cover2": ParagraphStyle("cover2", fontName="DejaVu", fontSize=13, leading=18, textColor=GREY),
}

GRID = TableStyle([
    ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),
    ("FONTSIZE", (0, 0), (-1, -1), 7),
    ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 2.5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
])


class ReviewDoc(BaseDocTemplate):
    def __init__(self, path: str, world: World):
        super().__init__(path, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN + 6,
                         bottomMargin=MARGIN + 4, title=world.title, author="Velmora RIA (fictional)",
                         subject="Synthetic demo document")
        self.world = world
        self.chapter = ""
        top = PAGE_H - MARGIN - 6
        body_h = top - (MARGIN + 4)
        left = MARGIN
        two = [Frame(left, MARGIN + 4, COL_W, body_h, id="L", leftPadding=0, rightPadding=0),
               Frame(left + COL_W + GUTTER, MARGIN + 4, COL_W, body_h, id="R", leftPadding=0, rightPadding=0)]
        band = [Frame(left, top - BAND_H, FULL_W, BAND_H, id="band", leftPadding=0, rightPadding=0),
                Frame(left, MARGIN + 4, COL_W, body_h - BAND_H - 6, id="bL", leftPadding=0, rightPadding=0),
                Frame(left + COL_W + GUTTER, MARGIN + 4, COL_W, body_h - BAND_H - 6, id="bR", leftPadding=0, rightPadding=0)]
        one = [Frame(left, MARGIN + 4, FULL_W, body_h, id="one", leftPadding=0, rightPadding=0)]
        lw, lh = landscape(A4)
        land = [Frame(MARGIN, MARGIN, lw - 2 * MARGIN, lh - 2 * MARGIN - 10, id="land", leftPadding=0, rightPadding=0)]
        self.addPageTemplates([
            PageTemplate("cover", one, onPage=lambda c, d: None),
            PageTemplate("one", one, onPage=self._decorate),
            PageTemplate("two", two, onPage=self._decorate),
            PageTemplate("band", band, onPage=self._decorate),
            PageTemplate("land", land, onPage=self._decorate, pagesize=landscape(A4)),
        ])

    def _decorate(self, canvas, doc):
        w, h = canvas._pagesize
        canvas.saveState()
        canvas.setFont("DejaVu", 6.8)
        canvas.setFillColor(GREY)
        canvas.drawString(MARGIN, h - MARGIN + 4, "Velmora Regional Infrastructure Authority · Integrated Annual Review 2025")
        canvas.drawRightString(w - MARGIN, h - MARGIN + 4, self.chapter[:70])
        canvas.setStrokeColor(LINE)
        canvas.line(MARGIN, h - MARGIN + 1, w - MARGIN, h - MARGIN + 1)
        canvas.drawString(MARGIN, MARGIN - 8, "Synthetic data · fictional organisation · for RAG testing only")
        canvas.drawRightString(w - MARGIN, MARGIN - 8, f"Page {doc.page}")
        canvas.restoreState()

    def beforeDocument(self):
        # multiBuild runs several passes; start each one with no current chapter.
        self.chapter = ""

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            style = flowable.style.name
            text = flowable.getPlainText()
            if style == "h1":
                self.chapter = text
                key = f"ch{self.seq.nextf('toc')}"
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=0)
                self.notify("TOCEntry", (0, text, self.page, key))
            elif style == "h2" and self.chapter:
                key = f"s{self.seq.nextf('toc2')}"
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=1, closed=True)


def _p(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, S[style])


def _caption(text: str) -> Paragraph:
    return _p(text, "cap")


def _table(rows, widths, header_rows=1, extra=None, repeat=None, zebra=True) -> Table:
    cell_rows = []
    for i, row in enumerate(rows):
        style = "cellb" if i < header_rows else "cell"
        cell_rows.append([c if not isinstance(c, str) else Paragraph(c, S[style]) for c in row])
    t = Table(cell_rows, colWidths=widths, repeatRows=repeat if repeat is not None else header_rows)
    style = TableStyle(GRID.getCommands())
    style.add("BACKGROUND", (0, 0), (-1, header_rows - 1), LIGHT)
    style.add("LINEBELOW", (0, header_rows - 1), (-1, header_rows - 1), 0.8, ACCENT)
    if zebra:
        for r in range(header_rows, len(rows)):
            if (r - header_rows) % 2 == 1:
                style.add("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f9fafb"))
    for cmd in extra or []:
        style.add(*cmd)
    t.setStyle(style)
    return t


def _box(title: str, body: str, width: float) -> Table:
    t = Table([[Paragraph(f"<b>{title}</b><br/>{body}", S["box"])]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("BOX", (0, 0), (-1, -1), 0.8, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _fmt(v, unit=""):
    if isinstance(v, float) and v.is_integer() and unit == "min":
        v = int(v)
    return f"{v}"


def cover(world: World) -> list:
    return [
        Spacer(1, 150),
        _p("Velmora Regional Infrastructure Authority", "cover2"),
        Spacer(1, 8),
        _p("Integrated Annual Review 2025", "cover"),
        Spacer(1, 10),
        _p("Water · Power · Transit · Finance · Safety — twelve regions in one report", "cover2"),
        Spacer(1, 220),
        _p("This is a synthetic document. Velmora, its regions, people, companies and every number in it are "
           "invented. It was generated to test document AI systems on hard layouts.", "foot"),
        NextPageTemplate("one"), PageBreak(),
    ]


def toc() -> list:
    t = TableOfContents()
    t.levelStyles = [ParagraphStyle("toc0", fontName="DejaVu", fontSize=9.5, leading=14, leftIndent=0)]
    return [_p("Contents", "h2"), t, NextPageTemplate("one"), PageBreak()]


def chair_message(world: World, rng: random.Random) -> list:
    total_staff = sum(r.staff for r in world.regions)
    paras = [
        f"This review covers the work of the Velmora Regional Infrastructure Authority in {world.year}. "
        f"Our twelve regions run water, power and transit services for the whole country. "
        f"At year end we employed {total_staff:,} people.",
        "It was a hard year. Dry summers pushed water demand to new highs in many regions. Prices for steel, "
        "copper and transformers stayed high. Even so, most of our capital projects stayed on budget.",
        f"The national target is for renewable sources to supply {world.national_target_renewable}% of the "
        f"power we deliver by 2030. Each regional chapter shows how far that region has come.",
        "We thank our staff, our contractors and the town councils who worked with us. We also thank our "
        "customers for their patience during road works and planned outages.",
    ]
    out = [_p("Message from the Chair and the Chief Executive", "h1")]
    out += [_p(p, "body1") for p in paras]
    for _ in range(3):
        out.append(_p(" ".join(rng.sample([
            "Our first duty is to keep water safe to drink and power flowing to homes and hospitals.",
            "Every chapter in this review follows the same layout, so readers can compare regions.",
            "Some numbers changed after the draft accounts were audited; the audited figures are used here.",
            "We publish our project register in full in Appendix B.",
            "Where a region missed a target, the chapter says why and what will change.",
            "Safety on our sites improved, but one serious injury is still one too many.",
            "Digital tools now help crews find faults faster and plan works with less disruption.",
        ], 5)), "body1"))
    out += [Spacer(1, 10), _p(f"<b>{world.chair}</b>, Chair of the Board", "body1"),
            _p(f"<b>{world.ceo}</b>, Chief Executive", "body1")]
    out += [NextPageTemplate("band"), PageBreak()]
    return out


def executive_summary(world: World, rng: random.Random) -> list:
    n_projects = sum(len(r.projects) for r in world.regions)
    pop = sum(r.population for r in world.regions)
    tiles = [
        (f"VCR {world.total_capex_m:,.1f} m", "Capital spend, all regions"),
        (f"{n_projects}", "Projects in the register"),
        (f"{pop / 1e6:.2f} m", "People served"),
        (f"{world.national_target_renewable}%", "Renewable target for 2030"),
        (f"{sum(r.staff for r in world.regions):,}", "Staff at year end"),
        (f"{sum(r.customers_k for r in world.regions):,}k", "Customer accounts"),
    ]
    cells = [[[_p(n, "tile_n"), _p(l, "tile_l")] for n, l in tiles[i:i + 3]] for i in (0, 3)]
    grid = Table(cells, colWidths=[FULL_W / 3] * 3, rowHeights=[48, 48])
    grid.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.6, LINE),
                              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BACKGROUND", (0, 0), (-1, -1), colors.white)]))
    best = max(world.regions, key=lambda r: r.capex_m)
    out = [_p("Executive summary", "h1"), NextPageTemplate("two"),
           _p("The six numbers below sum up the year. Each regional chapter gives the detail.", "body1"),
           grid, Spacer(1, 6), _caption("Table 2.1: Key figures for 2025, all twelve regions."),
           FrameBreak()]
    themes = [
        ("Water", "Demand peaked in summer in every region. The highest peaks came in coastal regions, where "
                  "tourism doubles the population for a few weeks. Leakage work continued in all regions."),
        ("Power", "More rooftop and field solar came online. Grid availability stayed above 95% in most regions. "
                  "Battery sites helped cover the evening peak."),
        ("Transit", "Bus fleets kept moving to electric. Bridge checks by drone cut lane closures. "
                    "Two light-rail studies moved to the design stage."),
        ("Money", f"Capital spend was VCR {world.total_capex_m:,.1f} million. {best.name} spent the most, "
                  f"because of its large treatment plant and grid programmes. Chapter 15 sets out spend by region."),
        ("Safety", "Equipment failure was again the largest cause of incidents. Chapter 16 has the full table "
                   "and a chart of causes."),
    ]
    for head, text in themes:
        out.append(_p(head, "h2"))
        out.append(_p(text))
        out.append(_p(" ".join(rng.sample([
            "Regional teams shared methods through monthly calls.",
            "The board reviewed progress every quarter.",
            "Targets for next year are set out in each regional chapter.",
            "Independent auditors checked the main figures.",
            "Customers were kept informed through the public app and text alerts.",
            "Contractors were paid within 30 days in most cases.",
        ], 3))))
    out.append(_box("How to read this report",
                    "Chapters 3 to 14 cover one region each, in alphabetical order. Each opens with a table of "
                    "indicators, then two charts, the narrative, and a list of capital projects. Appendix A has "
                    "monthly water quality scores, Appendix B the full project register, Appendix C a glossary.", COL_W))
    return out


def region_chapter(world: World, idx: int, ch: int, rng: random.Random, paras: int) -> list:
    r = world.regions[idx]
    out = [NextPageTemplate("band"), PageBreak()] if idx > 0 else [NextPageTemplate("band"), PageBreak()]
    out += [_p(f"Chapter {ch} — {r.name} Region", "h1"), NextPageTemplate("two"), _p(chapter_intro(r), "body1")]
    rows = [["Indicator", "Unit", "Result", "", "Target 2026"], ["", "", "2024", "2025", ""]]
    for name, unit, v24, v25, tgt in r.kpis:
        rows.append([name, unit or "—", _fmt(v24, unit), _fmt(v25, unit), _fmt(tgt, unit)])
    kpi = _table(rows, [FULL_W * 0.42, FULL_W * 0.1, FULL_W * 0.15, FULL_W * 0.15, FULL_W * 0.18], header_rows=2,
                 extra=[("SPAN", (0, 0), (0, 1)), ("SPAN", (1, 0), (1, 1)), ("SPAN", (2, 0), (3, 0)),
                        ("SPAN", (4, 0), (4, 1)), ("ALIGN", (2, 0), (-1, -1), "CENTER")])
    out += [kpi, _caption(f"Table {ch}.1: {r.name} — performance indicators, 2024 and 2025, with the target for 2026."),
            FrameBreak()]
    fig_no = 1
    for key, heading, plist in region_paragraphs(r, world, rng, paras):
        out.append(_p(heading, "h2"))
        for j, para in enumerate(plist):
            if key == "water" and j == 0:
                para += "<super>1</super>"
            out.append(_p(para))
        if key == "overview":
            band = "red" if r.risk_score >= 15 else "amber"
            out.append(_box(f"Key risk — {r.name}",
                            f"{r.risk_top.capitalize()}. Risk score {r.risk_score} of 25 ({band}). "
                            f"Risk owner: {r.risk_owner}.", COL_W))
            out.append(Spacer(1, 6))
        if key == "water":
            png = charts.water_line_png(r.water_ml_day, r.peak_month, r.name)
            out.append(KeepTogether([Image(io.BytesIO(png), width=COL_W, height=COL_W * 2.1 / 3.4),
                                     _caption(f"Figure {ch}.{fig_no}: Average daily water demand by month, "
                                              f"{r.name}, {world.year}.")]))
            fig_no += 1
            out.append(_p(f"<super>1</super> {r.footnote_fact}", "foot"))
        if key == "power":
            out.append(KeepTogether([charts.power_bar_chart(r.power_gwh, COL_W),
                                     _caption(f"Figure {ch}.{fig_no}: Electricity delivered by quarter, "
                                              f"{r.name}, {world.year} (GWh).")]))
            fig_no += 1
    out += [NextPageTemplate("one"), PageBreak(), _p(f"{r.name} — capital projects", "h2"),
            _p(f"The table lists every capital project in {r.name} that was active in {world.year}. "
               f"Budgets and spend are in millions of Velmoran crowns (VCR).", "body1")]
    rows = [["Code", "Project", "Sector", "Contractor", "Budget", "Spent", "Status", "Finish"]]
    for p in r.projects:
        rows.append([p.code, p.name, p.sector, p.contractor, f"{p.budget_m:.1f}", f"{p.spent_m:.1f}", p.status, p.finish])
    w = FULL_W
    out += [_table(rows, [w * .09, w * .24, w * .08, w * .21, w * .09, w * .09, w * .1, w * .1]),
            _caption(f"Table {ch}.2: Capital projects in {r.name}, {world.year}. Budget and spent in VCR million.")]
    out.append(_p(f"Projects marked <i>At risk</i> are reviewed by the board each quarter. Total capital spend "
                  f"recorded for {r.name} in {world.year} was VCR {r.capex_m:.1f} million.", "body1"))
    return out


def finance_chapter(world: World, ch: int) -> list:
    out = [NextPageTemplate("one"), PageBreak(), _p(f"Chapter {ch} — Finance", "h1"),
           _p("This chapter shows what each region spent. Capex is money spent on new or rebuilt assets. "
              "Opex is the cost of running services. Grants are money received from national funds.", "body1")]
    rows = [["Region", "Spending, VCR million", "", "", "Total"], ["", "Capex", "Opex", "Grants received", ""]]
    tot = [0.0, 0.0, 0.0]
    for r in world.regions:
        rows.append([r.name, f"{r.capex_m:.1f}", f"{r.opex_m:.1f}", f"{r.grant_m:.1f}", f"{r.capex_m + r.opex_m:.1f}"])
        tot = [tot[0] + r.capex_m, tot[1] + r.opex_m, tot[2] + r.grant_m]
    rows.append(["All regions", f"{tot[0]:.1f}", f"{tot[1]:.1f}", f"{tot[2]:.1f}", f"{tot[0] + tot[1]:.1f}"])
    out += [_table(rows, [FULL_W * .3, FULL_W * .16, FULL_W * .16, FULL_W * .18, FULL_W * .2], header_rows=2,
                   extra=[("SPAN", (0, 0), (0, 1)), ("SPAN", (1, 0), (3, 0)), ("SPAN", (4, 0), (4, 1)),
                          ("FONTNAME", (0, -1), (-1, -1), "DejaVu-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.8, ACCENT),
                          ("ALIGN", (1, 0), (-1, -1), "RIGHT")]),
            _caption(f"Table {ch}.1: Spending by region, {world.year}. Total = capex + opex. Grants are shown separately.")]
    rows = [["Region", "Water", "Power", "Transit"]]
    for r in world.regions:
        by = {"Water": 0.0, "Power": 0.0, "Transit": 0.0}
        for p in r.projects:
            by[p.sector] += p.budget_m
        total = sum(by.values()) or 1
        rows.append([r.name] + [f"{by[s] / total * 100:.0f}%" for s in ("Water", "Power", "Transit")])
    out += [Spacer(1, 8), _p("Where the project money goes", "h2"),
            _p("The next table shows each region's project budgets split by sector. It helps explain why "
               "spending differs so much between regions.", "body1"),
            _table(rows, [FULL_W * .4, FULL_W * .2, FULL_W * .2, FULL_W * .2]),
            _caption(f"Table {ch}.2: Share of project budgets by sector, {world.year}.")]
    return out


def safety_chapter(world: World, ch: int) -> list:
    out = [NextPageTemplate("one"), PageBreak(), _p(f"Chapter {ch} — Safety", "h1"),
           _p("Every incident on our sites and networks is logged and given a cause. The table counts "
              "incidents by region and cause. The chart shows the national picture.", "body1")]
    rows = [["Region"] + CAUSES + ["Total"]]
    totals = {c: 0 for c in CAUSES}
    for r in world.regions:
        rows.append([r.name] + [str(r.safety_by_cause[c]) for c in CAUSES] + [str(sum(r.safety_by_cause.values()))])
        for c in CAUSES:
            totals[c] += r.safety_by_cause[c]
    rows.append(["All regions"] + [str(totals[c]) for c in CAUSES] + [str(sum(totals.values()))])
    w = FULL_W
    out += [_table(rows, [w * .16] + [w * .12] * 6 + [w * .12],
                   extra=[("FONTNAME", (0, -1), (-1, -1), "DejaVu-Bold"), ("ALIGN", (1, 0), (-1, -1), "CENTER")]),
            _caption(f"Table {ch}.1: Safety incidents by region and cause, {world.year}.")]
    png = charts.cause_pie_png(totals)
    out += [Spacer(1, 10), Image(io.BytesIO(png), width=FULL_W * 0.75, height=FULL_W * 0.75 * 3.0 / 4.8),
            _caption(f"Figure {ch}.1: Share of safety incidents by cause, all regions, {world.year}.")]
    return out


def appendix_quality(world: World) -> list:
    lw, _ = landscape(A4)
    width = lw - 2 * MARGIN
    rows = [["Region"] + MONTHS + ["Avg"]]
    for r in world.regions:
        rows.append([r.name] + [str(v) for v in r.quality_index] + [f"{sum(r.quality_index) / 12:.1f}"])
    return [NextPageTemplate("land"), PageBreak(),
            _p("Appendix A — Monthly Water Quality Index", "h1"),
            _p("The Water Quality Index (WQI) is a score from 0 to 100 built from 11 lab tests. "
               "A score of 80 or more is rated good. Scores under 70 trigger a review.", "body1"),
            _table(rows, [width * .14] + [width * .066] * 12 + [width * .068],
                   extra=[("ALIGN", (1, 0), (-1, -1), "CENTER")]),
            _caption("Table A.1: Water Quality Index by region and month, 2025.")]


def appendix_register(world: World) -> list:
    rows = [["Code", "Region", "Project", "Contractor", "Budget", "Spent", "Status", "Finish"]]
    for r in world.regions:
        for p in r.projects:
            rows.append([p.code, r.name, p.name, p.contractor, f"{p.budget_m:.1f}", f"{p.spent_m:.1f}", p.status, p.finish])
    w = FULL_W
    return [NextPageTemplate("one"), PageBreak(), _p("Appendix B — Project register", "h1"),
            _p("All capital projects active in 2025, across all regions. The header row repeats on each page.", "body1"),
            _table(rows, [w * .08, w * .11, w * .23, w * .2, w * .09, w * .09, w * .1, w * .1]),
            _caption("Table B.1: Full project register, 2025. Budget and spent in VCR million.")]


def appendix_glossary(world: World, rng: random.Random) -> list:
    out = [NextPageTemplate("two"), PageBreak(), _p("Appendix C — Glossary and method", "h1")]
    for term, meaning in world.glossary:
        out.append(_p(f"<b>{term}.</b> {meaning}"))
    out.append(_p("How the numbers were made", "h2"))
    method = [
        "Water demand is the average volume put into supply each day, measured at the outlet of each treatment plant.",
        "Electricity delivered is metered at the boundary between the national grid and each regional network.",
        "Indicators for 2024 were restated where audits found errors; the restated values are shown.",
        "Targets for 2026 were approved by the board in November and do not change during the year.",
        "Project budgets are the latest approved budget, not the original estimate.",
        "Safety incidents include near-misses only when they led to damage or a stop of work.",
        "Customer accounts count billing accounts, so one account can cover a whole block of flats.",
    ]
    for _ in range(6):
        out.append(_p(" ".join(rng.sample(method, 4))))
    return out


def build(out_path: Path, world: World, seed: int = 7, paras_per_section: int = 6) -> int:
    rng = random.Random(seed)
    doc = ReviewDoc(str(out_path), world)
    story = cover(world) + toc() + chair_message(world, rng) + executive_summary(world, rng)
    ch = 3
    for i in range(len(world.regions)):
        story += region_chapter(world, i, ch, rng, paras_per_section)
        ch += 1
    story += finance_chapter(world, ch)
    story += safety_chapter(world, ch + 1)
    story += appendix_quality(world) + appendix_register(world) + appendix_glossary(world, rng)
    doc.multiBuild(story)
    return doc.page
