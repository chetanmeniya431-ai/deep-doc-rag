"""A made-up world for the demo report.

Velmora is a fictional country. Every name, number and person here is invented.
All numbers come from one seeded random generator, so the same seed always
gives the same report and the same answer key.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

REGION_NAMES = [
    "Ashmoor", "Brenvale", "Caldris", "Dunmarrow", "Elsworth", "Fenwyck",
    "Glenhollow", "Harrowgate", "Istrane", "Juniper Coast", "Kestrel Plains", "Lorrimer",
]
FIRST = ["Amara", "Tobias", "Ingrid", "Ravi", "Selma", "Oduya", "Marek", "Lucia", "Henrik",
         "Priya", "Callum", "Noor", "Elena", "Jonas", "Fatima", "Dmitri", "Yara", "Bastian",
         "Keiko", "Anders", "Leona", "Matteo", "Sunniva", "Idris"]
LAST = ["Okafor", "Lindqvist", "Varga", "Mehta", "Castellano", "Brandt", "Haldane", "Nakamura",
        "Osei", "Ferreira", "Kowalczyk", "Ashworth", "Delacroix", "Rahman", "Thorsen", "Abiodun",
        "Vasquez", "Moreau", "Kirchner", "Sato", "Quill", "Barros", "Engström", "Petrov"]
TOWN_PARTS_A = ["Kor", "Mar", "Tal", "Ost", "Wren", "Bel", "Gar", "Lin", "Sev", "Pell", "Dra", "Vor",
                "Hal", "Rim", "Cas", "Tor", "Ul", "Ner", "Fal", "Quen"]
TOWN_PARTS_B = ["vel", "brook", "stead", "ford", "mere", "wick", "holm", "ridge", "haven", "dale",
                "port", "field", "moor", "crest", "bury"]
CONTRACTORS = ["Halvorsen Civil Works", "Brightline Engineering", "Corva Infrastructure Group",
               "Delmont & Pryce", "Equinor Builders Cooperative", "Fairhaven Utilities Contracting",
               "Granite Arc Partners", "Hollis-Tern Construction", "Ironleaf Systems",
               "Juno Grid Services", "Kaldor Water Technologies", "Lumen Rail Contractors"]
PROJECT_KINDS = [
    ("Water", "pumping station upgrade"), ("Water", "treatment plant expansion"),
    ("Water", "trunk main replacement"), ("Water", "reservoir lining"),
    ("Power", "substation rebuild"), ("Power", "solar farm"), ("Power", "battery storage site"),
    ("Power", "grid line reinforcement"), ("Transit", "bus depot electrification"),
    ("Transit", "light rail extension"), ("Transit", "bridge strengthening"),
    ("Transit", "smart signal corridor"),
]
STATUSES = ["On track", "On track", "On track", "Delayed", "At risk", "Completed", "Completed"]
EQUIPMENT = ["main valve", "transformer", "pump motor", "control cabinet", "switchgear unit",
             "chlorine dosing unit", "flow meter bank", "backup generator", "signal relay"]
CAUSES = ["Equipment failure", "Third-party damage", "Severe weather", "Human error",
          "Supply delay", "Cyber incident"]
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December"]
KPI_NAMES = [
    ("Water supply reliability", "%"), ("Leakage rate", "%"), ("Average outage length", "min"),
    ("Grid availability", "%"), ("Renewable share of power", "%"), ("Bus on-time rate", "%"),
    ("Customer complaints per 10,000", ""), ("Lost-time injury rate", ""),
]


@dataclass
class Project:
    code: str
    name: str
    sector: str
    contractor: str
    budget_m: float      # millions of Velmoran crowns (VCR)
    spent_m: float
    status: str
    finish: str          # e.g. "Nov 2026"


@dataclass
class Incident:
    month: str
    town: str
    equipment: str
    days: int
    households: int


@dataclass
class Region:
    name: str
    code: str
    director: str
    hq_town: str
    towns: list[str]
    population: int
    staff: int
    power_gwh: list[float]                 # by quarter, shown ONLY in a vector bar chart
    water_ml_day: list[float]              # by month, shown ONLY in a raster line chart
    peak_month: int
    kpis: list[tuple[str, str, float, float, float]]  # name, unit, 2024, 2025, target
    projects: list[Project]
    incident: Incident
    risk_top: str
    risk_score: int
    risk_owner: str
    capex_m: float
    opex_m: float
    grant_m: float
    safety_by_cause: dict[str, int]
    quality_index: list[int]               # by month, only in the landscape appendix table
    footnote_fact: str
    award: str
    customers_k: int
    new_connections: int


@dataclass
class World:
    title: str
    year: int
    chair: str
    ceo: str
    regions: list[Region] = field(default_factory=list)
    total_capex_m: float = 0.0
    national_target_renewable: int = 0
    glossary: list[tuple[str, str]] = field(default_factory=list)


def _person(rng: random.Random, used: set[str]) -> str:
    while True:
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if name not in used:
            used.add(name)
            return name


def _town(rng: random.Random, used: set[str]) -> str:
    while True:
        name = rng.choice(TOWN_PARTS_A) + rng.choice(TOWN_PARTS_B)
        if name not in used:
            used.add(name)
            return name


def build_world(seed: int = 2025) -> World:
    rng = random.Random(seed)
    people: set[str] = set()
    towns_used: set[str] = set()
    world = World(
        title="Velmora Regional Infrastructure Authority — Integrated Annual Review 2025",
        year=2025,
        chair=_person(rng, people),
        ceo=_person(rng, people),
        national_target_renewable=rng.choice([45, 48, 50, 52]),
    )
    awards = ["National Water Prize", "Green Grid Award", "Safe Sites Medal", "Transit Access Award",
              "Clean Rivers Citation", "Digital Utility Award", "Community Trust Award",
              "Apprentice Employer of the Year", "Flood Resilience Award", "Low Carbon Fleet Award",
              "Open Data Award", "Customer Care Award"]
    rng.shuffle(awards)
    project_counter = 100
    for i, name in enumerate(REGION_NAMES):
        towns = [_town(rng, towns_used) for _ in range(5)]
        base_power = rng.uniform(180, 900)
        power = [round(base_power * rng.uniform(0.8, 1.2), 1) for _ in QUARTERS]
        base_water = rng.uniform(14, 60)
        peak = rng.choice([5, 6, 7, 8])
        water = []
        for m in range(12):
            season = 1 + 0.25 * (1 - abs(m - peak) / 6)
            water.append(round(base_water * season * rng.uniform(0.95, 1.05), 1))
        water[peak] = round(max(water) * 1.04, 1)
        kpis = []
        for kname, unit in KPI_NAMES:
            if unit == "%":
                lo = 2 if "Leakage" in kname else (20 if "Renewable" in kname else 85)
                hi = 25 if "Leakage" in kname else (70 if "Renewable" in kname else 99.9)
                v24 = round(rng.uniform(lo, hi), 1)
                v25 = round(min(hi, max(lo, v24 + rng.uniform(-3, 4))), 1)
                tgt = round(min(hi, v25 + rng.uniform(0.5, 4)), 1) if "Leakage" not in kname else round(max(lo, v25 - rng.uniform(0.5, 3)), 1)
            elif unit == "min":
                v24 = round(rng.uniform(30, 240)); v25 = round(v24 * rng.uniform(0.7, 1.15)); tgt = round(v25 * 0.85)
            else:
                v24 = round(rng.uniform(0.4, 9), 2); v25 = round(v24 * rng.uniform(0.6, 1.2), 2); tgt = round(v25 * 0.8, 2)
            kpis.append((kname, unit, v24, v25, tgt))
        projects = []
        for _ in range(rng.randint(5, 8)):
            project_counter += rng.randint(1, 9)
            sector, kind = rng.choice(PROJECT_KINDS)
            budget = round(rng.uniform(4, 260), 1)
            status = rng.choice(STATUSES)
            spent = budget if status == "Completed" else round(budget * rng.uniform(0.05, 0.95), 1)
            if status == "At risk":
                spent = round(budget * rng.uniform(0.7, 1.15), 1)
            finish = f"{rng.choice(MONTHS)} {rng.choice([2025, 2026, 2027, 2028])}"
            if status == "Completed":
                finish = f"{rng.choice(MONTHS)} 2025"
            projects.append(Project(
                code=f"{name[:3].upper()}-{project_counter}",
                name=f"{rng.choice(towns)} {kind}",
                sector=sector, contractor=rng.choice(CONTRACTORS),
                budget_m=budget, spent_m=spent, status=status, finish=finish,
            ))
        capex = round(sum(p.budget_m for p in projects) * rng.uniform(0.25, 0.45), 1)
        incident = Incident(
            month=rng.choice(MONTHS_LONG), town=rng.choice(towns), equipment=rng.choice(EQUIPMENT),
            days=rng.randint(2, 31), households=rng.randint(800, 42000),
        )
        safety = {c: rng.randint(0, 40) for c in CAUSES}
        region = Region(
            name=name, code=name[:3].upper(), director=_person(rng, people), hq_town=towns[0],
            towns=towns, population=rng.randint(180_000, 2_400_000), staff=rng.randint(240, 3100),
            power_gwh=power, water_ml_day=water, peak_month=peak, kpis=kpis, projects=projects,
            incident=incident,
            risk_top=rng.choice(["ageing cast-iron mains", "drought in the upper catchment",
                                 "transformer supply shortages", "skills gap in signal engineers",
                                 "coastal flooding of pump sites", "rising steel prices",
                                 "cyber attacks on control systems", "slow land permits"]),
            risk_score=rng.randint(6, 25), risk_owner=_person(rng, people),
            capex_m=capex, opex_m=round(rng.uniform(30, 400), 1), grant_m=round(rng.uniform(0, 80), 1),
            safety_by_cause=safety,
            quality_index=[rng.randint(61, 99) for _ in range(12)],
            footnote_fact=f"Figures for {rng.choice(towns)} exclude {rng.randint(2, 19)} private wells that report on a separate cycle.",
            award=awards[i], customers_k=rng.randint(60, 900), new_connections=rng.randint(300, 9000),
        )
        world.regions.append(region)
    world.total_capex_m = round(sum(r.capex_m for r in world.regions), 1)
    world.glossary = [
        ("Capex", "Money spent on building or buying long-life assets such as pipes and substations."),
        ("Opex", "Money spent on running costs: staff, energy, repairs and chemicals."),
        ("GWh", "Gigawatt-hour. One million kilowatt-hours of electricity."),
        ("ML/day", "Megalitres per day. One megalitre is one million litres of water."),
        ("Leakage rate", "Share of treated water lost from pipes before it reaches a customer."),
        ("Lost-time injury rate", "Injuries that cause at least one lost work shift, per 200,000 hours worked."),
        ("Grid availability", "Share of hours in which the regional grid delivered power without a forced outage."),
        ("Water Quality Index (WQI)", "A 0–100 score built from 11 lab tests. 80 or above is rated good."),
        ("Risk score", "Likelihood (1–5) multiplied by impact (1–5). Scores of 15 or more are red risks."),
        ("VCR", "Velmoran crown, the fictional currency used in this report."),
        ("SCADA", "The computer system that watches and controls pumps, valves and switches from a control room."),
        ("Trunk main", "A large pipe that carries water between treatment plants and town networks."),
    ]
    return world
