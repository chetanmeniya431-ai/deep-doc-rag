"""Fast tests: no models, no index. Run with: docker compose run --rm app pytest -q"""
import io

import fitz
import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Table, TableStyle

from deepdoc.eval.run import contains
from deepdoc.ingest.chunker import build_chunks
from deepdoc.ingest.layout import Element, PageParse, Word, _reading_order, build_table, parse_page
from deepdoc.retrieve.search import analyse, rrf


def two_column_pdf() -> fitz.Document:
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4)
    w = (A4[0] - 144) / 2
    doc.addPageTemplates([PageTemplate("two", [Frame(72, 72, w - 6, A4[1] - 144, id="L"),
                                               Frame(72 + w + 6, 72, w - 6, A4[1] - 144, id="R")])])
    st = ParagraphStyle("b", fontName="Helvetica", fontSize=9, leading=12)
    story = [Paragraph(f"Left {i} " + "alpha " * 40, st) for i in range(6)]
    story += [Paragraph(f"Right {i} " + "omega " * 40, st) for i in range(6)]
    rows = [["Item", "2024", "2025"], ["Pumps", "10", "12"], ["Valves", "7", "9"], ["Meters", "3", "4"]]
    t = Table(rows)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, "#999999"),
                           ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
    story.append(t)
    doc.build(story)
    return fitz.open(stream=buf.getvalue(), filetype="pdf")


def test_two_columns_read_left_then_right():
    page = two_column_pdf()[0]
    texts = [e.text for e in parse_page(page, ocr=False).elements if e.kind == "text"]
    joined = " ".join(texts)
    assert joined.index("Left 5") < joined.index("Right 0")


def test_rule_only_table_is_found_with_header():
    doc = two_column_pdf()
    tables = [e for p in doc for e in parse_page(p, ocr=False).elements if e.kind == "table"]
    assert tables, "table drawn with horizontal rules only was not found"
    t = tables[0].meta
    assert t["header"] == ["Item", "2024", "2025"]
    assert ["Valves", "7", "9"] in t["rows"]


def test_merged_header_spreads_over_columns():
    W = lambda t, x0, y, bold=False: Word(t, x0, y, x0 + 5 * len(t), y + 7, 7, bold)
    words = [W("Name", 0, 2, True), W("Result", 100, 2, True), W("2024", 100, 12, True), W("2025", 160, 12, True),
             W("Alpha", 0, 25), W("1.5", 100, 25), W("2.5", 160, 25),
             W("Beta", 0, 38), W("3.0", 100, 38), W("4.0", 160, 38)]
    tab = build_table((0, 0, 200, 46), [21, 34, 46], words)
    assert tab["header"] == ["Name", "Result 2024", "Result 2025"]
    assert tab["rows"][1] == ["Beta", "3.0", "4.0"]


def test_reading_order_full_width_cuts_bands():
    E = lambda t, b: Element("text", t, b, 1)
    els = [E("title", (50, 50, 550, 70)), E("L1", (50, 100, 290, 200)), E("R1", (310, 100, 550, 200)),
           E("wide table", (50, 220, 550, 300)), E("L2", (50, 320, 290, 400)), E("R2", (310, 320, 550, 400))]
    _reading_order(els, 600)
    assert [e.text for e in els] == ["title", "L1", "R1", "wide table", "L2", "R2"]


def test_sentence_split_over_columns_is_joined():
    a = Element("text", "The pump failed and cut supply to 4,000", (0, 0, 10, 10), 3, meta={"section": "S"})
    b = Element("text", "households for 9 days. Repairs followed.", (20, 0, 30, 10), 4, meta={"section": "S"})
    chunks = build_chunks([PageParse(3, 600, 800, [a]), PageParse(4, 600, 800, [b])], "Doc")
    assert "cut supply to 4,000 households for 9 days." in chunks[0].text
    assert chunks[0].pages == [3, 4]
    assert chunks[0].embed_text.startswith("Doc › S")


def test_table_rows_become_column_value_chunks():
    t = Element("table", "", (0, 0, 10, 10), 5, meta={"section": "Finance", "caption": "Table 15.1: Spend",
                                                       "header": ["Region", "Capex"], "rows": [["Ashmoor", "251.1"]]})
    chunks = build_chunks([PageParse(5, 600, 800, [t])], "Doc")
    rows = [c for c in chunks if c.kind == "table_row"]
    assert rows and "Region: Ashmoor; Capex: 251.1" in rows[0].text


def test_query_analysis_and_rrf():
    qa = analyse("What does Table 3.2 show on page 14?")
    assert ("table", "3.2") in qa["refs"] and qa["pages"] == [14]
    fused = rrf([[1, 2, 3], [3, 1]])
    assert fused[0][0] in (1, 3) and {c for c, _ in fused} == {1, 2, 3}


@pytest.mark.parametrize("hay,needle,ok", [("peak in September", "Sep", True), ("40443 homes", "40,443", True),
                                           ("score 15", "16", False)])
def test_answer_matching(hay, needle, ok):
    assert contains(hay, needle) is ok


def test_word_broken_in_narrow_cell_is_glued():
    W = lambda t, x0, y, x1=None, bold=False: Word(t, x0, y, x1 or x0 + 5 * len(t), y + 7, 7, bold)
    words = [W("Code", 0, 2, bold=True), W("Status", 100, 2, bold=True),
             W("CAL-18", 0, 14, 30), W("5", 0, 22), W("Complete", 100, 14, 140), W("d", 100, 22),
             W("CAL-19", 0, 36, 30), W("Upgrade", 100, 36, 140), W("of", 100, 44),
             W("CAL-20", 0, 58, 30), W("On", 100, 58), W("track", 112, 58)]
    tab = build_table((0, 0, 150, 68), [11, 32, 54, 68], words)
    assert tab["rows"][0] == ["CAL-185", "Completed"]
    assert tab["rows"][1] == ["CAL-19", "Upgrade of"]
    assert tab["rows"][2] == ["CAL-20", "On track"]


def test_calculator_finds_highest_and_skips_totals():
    from deepdoc.generate.answer import table_extreme
    md = ("Table 15.1: Spending by region\n| Region | Capex | Opex |\n|---|---|---|\n"
          "| Ashmoor | 251.1 | 318.2 |\n| Caldris | 412.0 | 100.0 |\n| All regions | 999.9 | 1.0 |")
    hit = {"kind": "table", "text": md, "pages": [125]}
    assert table_extreme("Which region had the highest capex?", [hit])["row"] == "Caldris"
    assert table_extreme("Which region had the lowest opex?", [hit])["row"] == "Caldris"
    assert table_extreme("What was Ashmoor's capex?", [hit]) is None


def test_chart_lookup_picks_named_label():
    from deepdoc.generate.answer import chart_lookup
    hit = {"kind": "figure", "pages": [18],
           "text": "Figure 4.2: Electricity by quarter\nChart values: Q1: 697.2; Q2: 586.3; Q3: 549.3; Q4: 641.5\nText in chart: x"}
    assert "Q3 = 549.3" in chart_lookup("How much in Q3 2025?", [hit])["text"]
    assert chart_lookup("How much in total?", [hit]) is None


def test_table_cell_lookup_month_prefix():
    from deepdoc.generate.answer import table_cell_lookup
    hit = {"kind": "table_row", "pages": [127],
           "text": "Table A.1: WQI — row: Region: Brenvale; Jan: 92; May: 64; Jun: 80; Jul: 69; Avg: 74.8"}
    assert table_cell_lookup("What was the Water Quality Index for Brenvale in June?", [hit])["row"] == "80"
    assert table_cell_lookup("What was the WQI for Ashmoor in June?", [hit]) is None
