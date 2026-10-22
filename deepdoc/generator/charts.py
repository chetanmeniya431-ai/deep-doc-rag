"""Charts for the demo report.

Two kinds on purpose, because real PDFs have both:
- Vector bar charts (reportlab graphics): labels are real PDF text, but scattered
  in odd positions with no reading order.
- Raster charts (matplotlib PNG): labels exist only as pixels, so the ingest
  pipeline must use OCR to read them.
"""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.graphics.charts.barcharts import VerticalBarChart  # noqa: E402
from reportlab.graphics.shapes import Drawing, String  # noqa: E402
from reportlab.lib import colors  # noqa: E402

from .facts import MONTHS, QUARTERS  # noqa: E402

INDIGO = colors.HexColor("#4f46e5")
EMERALD = "#059669"


def power_bar_chart(values: list[float], width: float, height: float = 150) -> Drawing:
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y = 36, 28
    chart.width, chart.height = width - 50, height - 52
    chart.data = [values]
    chart.categoryAxis.categoryNames = QUARTERS
    chart.categoryAxis.labels.fontName = "DejaVu"
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(values) * 1.25
    chart.valueAxis.labels.fontName = "DejaVu"
    chart.valueAxis.labels.fontSize = 6
    chart.bars[0].fillColor = INDIGO
    chart.bars[0].strokeColor = None
    chart.barLabelFormat = "%.1f"
    chart.barLabels.nudge = 7
    chart.barLabels.fontName = "DejaVu"
    chart.barLabels.fontSize = 7
    d.add(chart)
    d.add(String(36, height - 12, "GWh delivered", fontName="DejaVu", fontSize=7, fillColor=colors.grey))
    return d


def water_line_png(values: list[float], peak_month: int, region: str) -> bytes:
    fig, ax = plt.subplots(figsize=(3.4, 2.1), dpi=220)
    ax.plot(MONTHS, values, color=EMERALD, linewidth=1.6, marker="o", markersize=2.5)
    ax.set_ylabel("ML/day", fontsize=7)
    ax.tick_params(labelsize=6)
    ax.set_ylim(0, max(values) * 1.3)
    ax.grid(axis="y", linewidth=0.3, alpha=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.annotate(f"Peak {values[peak_month]} ML/day in {MONTHS[peak_month]}",
                xy=(peak_month, values[peak_month]), xytext=(0.03, 0.9), textcoords="axes fraction",
                fontsize=7, color="#111827",
                arrowprops=dict(arrowstyle="->", color="#6b7280", linewidth=0.6))
    ax.set_title(f"{region}: average daily water demand", fontsize=7)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def cause_pie_png(by_cause: dict[str, int]) -> bytes:
    fig, ax = plt.subplots(figsize=(4.8, 3.0), dpi=220)
    labels = [f"{k}: {v}" for k, v in by_cause.items()]
    palette = ["#4f46e5", "#059669", "#d97706", "#e11d48", "#0284c7", "#6b7280"]
    ax.pie(list(by_cause.values()), labels=labels, colors=palette, startangle=90,
           textprops={"fontsize": 7}, wedgeprops={"linewidth": 0.8, "edgecolor": "white"})
    ax.set_title("Safety incidents by cause, all regions", fontsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
