"""Answer key for the demo report.

We wrote the report from known facts, so we know every right answer and where it
lives. Each item says which kind of content holds the answer (two-column text,
table, vector chart, raster chart, side box, footnote, landscape table, ...).
The page is found after the PDF is built by looking for an anchor string.
"""
from __future__ import annotations

import re

import fitz

from .facts import CAUSES, MONTHS, MONTHS_LONG, World


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def questions(world: World) -> list[dict]:
    items: list[dict] = []
    for i, r in enumerate(world.regions):
        ch = 3 + i
        inc = r.incident
        kpi = {k[0]: k for k in r.kpis}
        lk = kpi["Leakage rate"]
        ren = kpi["Renewable share of power"]
        p0 = r.projects[0]
        p1 = r.projects[-1]
        q3 = r.power_gwh[2]
        add = items.append
        add(dict(type="text", q=f"Who is the Regional Director of {r.name}?", answers=[r.director],
                 anchor=f"Regional Director {r.director}"))
        add(dict(type="text", q=f"How many households lost water supply in the {inc.month} incident in {r.name}, and for how many days?",
                 answers=[f"{inc.households:,}", str(inc.days)], anchor=f"cut supply to {inc.households:,} households"))
        add(dict(type="text", q=f"How many staff did the {r.name} region employ at year end?",
                 answers=[f"{r.staff:,}"], anchor=f"region employed {r.staff:,} staff"))
        add(dict(type="text", q=f"Which award did the {r.name} team receive in {world.year}?",
                 answers=[r.award], anchor=f"team received the {r.award}"))
        add(dict(type="table", q=f"What was the leakage rate in {r.name} in 2025, and what is the 2026 target?",
                 answers=[str(lk[3]), str(lk[4])], anchor=f"Table {ch}.1:"))
        add(dict(type="table", q=f"What was the renewable share of power in {r.name} in 2024?",
                 answers=[str(ren[2])], anchor=f"Table {ch}.1:"))
        add(dict(type="table", q=f"Which contractor is building project {p0.code}?",
                 answers=[p0.contractor], anchor=p0.code))
        add(dict(type="table", q=f"What is the budget and status of the {p1.name} project in {r.name}?",
                 answers=[f"{p1.budget_m:.1f}", p1.status], anchor=p1.code))
        add(dict(type="chart_vector", q=f"How much electricity did {r.name} deliver in Q3 {world.year}?",
                 answers=[f"{q3:.1f}"], anchor=f"Figure {ch}.2:"))
        add(dict(type="chart_raster", q=f"In which month did water demand peak in {r.name}, and what was the peak value?",
                 answers=[MONTHS[r.peak_month], str(r.water_ml_day[r.peak_month])], anchor=f"Figure {ch}.1:"))
        add(dict(type="sidebar", q=f"What is the key risk for {r.name} and what is its risk score?",
                 answers=[r.risk_top.split()[0], str(r.risk_score)], anchor=f"Key risk — {r.name}"))
        add(dict(type="footnote", q=f"What do the {r.name} water figures exclude, according to the footnote?",
                 answers=[r.footnote_fact.split(" exclude ")[1].split(" private")[0]], anchor=r.footnote_fact[:40]))
        add(dict(type="finance_table", q=f"What were the opex and grants received for {r.name} in {world.year}?",
                 answers=[f"{r.opex_m:.1f}", f"{r.grant_m:.1f}"], anchor="Table 15.1:"))
        cause = CAUSES[i % len(CAUSES)]
        add(dict(type="safety_table", q=f"How many '{cause}' safety incidents were recorded in {r.name}?",
                 answers=[str(r.safety_by_cause[cause])], anchor="Table 16.1:"))
        m = (i * 5) % 12
        add(dict(type="landscape_table", q=f"What was the Water Quality Index for {r.name} in {MONTHS_LONG[m]}?",
                 answers=[str(r.quality_index[m])], anchor="Table A.1:"))
    top_capex = max(world.regions, key=lambda r: r.capex_m)
    top_staff = max(world.regions, key=lambda r: r.staff)
    items += [
        dict(type="multi_hop", q="Which region had the highest capex in 2025?", answers=[top_capex.name], anchor="Table 15.1:"),
        dict(type="multi_hop", q="Which region employed the most staff at year end?", answers=[top_staff.name],
             anchor=f"region employed {top_staff.staff:,} staff"),
        dict(type="summary", q="What share of power must come from renewable sources by 2030?",
             answers=[f"{world.national_target_renewable}%"], anchor="Renewable target for 2030"),
        dict(type="summary", q="Who is the Chair of the Board?", answers=[world.chair], anchor="Chair of the Board"),
        dict(type="glossary", q="What risk score makes a risk a red risk?", answers=["15"], anchor="Risk score."),
        dict(type="glossary", q="What does SCADA mean in this report?", answers=["control"], anchor="SCADA."),
        dict(type="chart_raster", q="How many safety incidents were caused by severe weather across all regions, according to the chart?",
             answers=[str(sum(r.safety_by_cause["Severe weather"] for r in world.regions))], anchor="Figure 16.1:"),
    ]
    for n, it in enumerate(items, 1):
        it["id"] = n
    return items


def locate_pages(pdf_path: str, items: list[dict]) -> list[dict]:
    doc = fitz.open(pdf_path)
    texts = [_norm(p.get_text()) for p in doc]
    for it in items:
        a = _norm(it["anchor"])
        pages = [i + 1 for i, t in enumerate(texts) if a in t]
        if not pages:
            # The fact is split over a page break: look in each pair of pages.
            pages = [p for i in range(len(texts) - 1) if a in texts[i] + " " + texts[i + 1] for p in (i + 1, i + 2)]
            it["split"] = True
        # Skip the contents pages: they repeat captions and headings.
        it["pages"] = [p for p in pages if p > 3] or pages
    return items
