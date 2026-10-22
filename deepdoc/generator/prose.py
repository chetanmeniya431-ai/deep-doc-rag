"""Builds the long body text of the report from sentence pools.

The fact sentences (director, incident, award, ...) appear exactly once per
region so the answer key can point to them. Filler sentences add realistic bulk:
similar wording across regions makes retrieval harder, because the system must
tell regions apart by name and numbers, not by phrasing.
"""
from __future__ import annotations

import random

from .facts import EQUIPMENT, MONTHS_LONG, Region, World

FILLER = {
    "overview": [
        "The region covers {towns_list} and a wide band of farmland between them.",
        "Most homes in {r} take water from the {t} network, which was laid in stages between 1962 and 1994.",
        "Demand in {r} rose by {pct}% over five years, mostly from new housing on the edge of {t}.",
        "The regional team meets the town councils of {t} and {t2} every quarter to agree on works that close roads.",
        "Around {n} kilometres of pipe in {r} are older than sixty years and are on the watch list.",
        "In {r}, field crews answered {n} call-outs this year, of which {pct}% were cleared within four hours.",
        "Public meetings in {t} raised noise from night works as the main concern of residents.",
        "The regional plan for {r} puts safety first, then supply, then cost.",
    ],
    "water": [
        "Water from the {t} intake is treated in three steps: settling, sand filters and a final chlorine dose.",
        "Crews in {r} replaced {n} metres of trunk main, most of it under busy roads near {t}.",
        "A pressure-management scheme in {t2} cut burst pipes by {pct}% compared with the year before.",
        "Raw water quality at the {t} reservoir stayed within limits on all but {small} sampling days.",
        "The night-flow survey in {r} found {small} large hidden leaks, each losing more than one litre per second.",
        "Smart meters now cover {pct}% of homes in {t}, which helps spot leaks on the customer side.",
        "Storage at {t2} holds about {small} days of normal demand if the main plant must stop.",
        "Water hardness in the south of {r} remains high, and the team trialled softening at one site in {t}.",
    ],
    "power": [
        "The grid in {r} links {small} major substations and a ring of smaller feeder points around {t}.",
        "Rooftop solar on public buildings in {t2} now adds about {n} megawatt-hours a year.",
        "Line crews in {r} cleared trees along {n} kilometres of overhead line before the storm season.",
        "Peak electricity demand in {r} now falls in the early evening, when people return home and cook.",
        "The control room in {t} can switch power around a fault in under {small} minutes on most feeders.",
        "Old oil-filled cables near {t2} are being replaced with dry cables that need less upkeep.",
        "A heat pump trial in {small} schools of {r} cut their gas use by about {pct}%.",
        "Voltage complaints from rural farms near {t} fell after two new regulators were fitted.",
    ],
    "transit": [
        "Buses in {r} carried about {n} thousand passengers in the year, mostly on the {t}–{t2} corridor.",
        "{small} bridges in {r} were inspected by drone, which cut lane closures by {pct}%.",
        "New bus shelters with live arrival screens were installed at {small} stops in {t}.",
        "The light-rail study for {t2} looked at three routes and picked the one along the old freight line.",
        "Electric buses now make up {pct}% of the {r} fleet, up from a handful three years ago.",
        "Road resurfacing in {t} was timed with pipe works so that each street was dug up only once.",
        "Cycle lanes along the river in {t2} were extended by {small} kilometres.",
        "Ticket machines in {r} were replaced with tap-to-pay readers on every vehicle.",
    ],
    "people": [
        "The {r} team ran {n} hours of safety training, including confined-space and live-line courses.",
        "Apprentices in {r} now make up {pct}% of new hires, many of them from schools in {t}.",
        "Staff turnover in {r} was {pct}%, close to the national average for utilities.",
        "A new depot canteen in {t} was built after staff asked for a warm place to eat on night shifts.",
        "Field crews now log every near-miss on a phone app, and {n} near-misses were recorded.",
        "Mental health first aiders are now present at every depot in {r}.",
        "The pay review agreed with unions in {r} took effect in {month}.",
    ],
    "customers": [
        "Most complaints in {r} were about billing, followed by low pressure and road works.",
        "The call centre for {r} answered {pct}% of calls within two minutes.",
        "Customers in {t} can now report leaks with a photo through the public app.",
        "A support fund in {r} helped {n} low-income homes pay their water bills.",
        "Planned outages in {t2} were announced by text message at least 48 hours ahead.",
        "Customer satisfaction in {r} was measured by an independent survey of {n} homes.",
    ],
    "environment": [
        "Treatment works in {r} returned cleaned water to the river at {t} under a strict permit.",
        "Tree planting along the {t2} stream covered {small} hectares this year.",
        "Sludge from the {t} plant is dried and used on farmland under a soil-safety plan.",
        "The {r} fleet used {pct}% less diesel after route planning software was introduced.",
        "Fish passes were added at {small} weirs in {r} so that trout can move upstream again.",
        "Flood barriers protect the pump stations at {t} and {t2} up to a one-in-200-year flood.",
    ],
    "outlook": [
        "For next year, {r} plans to focus on leakage, grid reliability and safer road works.",
        "The capital plan for {r} favours repair over new build where an asset still has useful life.",
        "Land for the new reservoir near {t2} is under review by the national planning board.",
        "The team in {r} expects steel and copper prices to stay high for at least two years.",
        "{r} will share its drone inspection method with the other eleven regions.",
        "A review of standby generators across {r} is due by the end of the second quarter.",
    ],
}

SECTIONS = [
    ("overview", "Regional overview"), ("water", "Water services"), ("power", "Power network"),
    ("transit", "Transit and roads"), ("people", "People and safety"),
    ("customers", "Customers"), ("environment", "Environment"), ("outlook", "Outlook"),
]


def _fill(rng: random.Random, template: str, region: Region) -> str:
    t, t2 = rng.sample(region.towns, 2)
    return template.format(
        r=region.name, t=t, t2=t2, towns_list=", ".join(region.towns[:-1]) + " and " + region.towns[-1],
        pct=rng.randint(3, 38), n=f"{rng.randint(120, 9800):,}", small=rng.randint(2, 14),
        month=rng.choice(MONTHS_LONG), equip=rng.choice(EQUIPMENT),
    )


def fact_sentences(region: Region, world: World) -> dict[str, list[str]]:
    """Sentences that carry answer-key facts, placed into specific sections."""
    inc = region.incident
    return {
        "overview": [
            f"The {region.name} region is led by Regional Director {region.director}, based at the head office in {region.hq_town}.",
            f"{region.name} serves a population of {region.population:,} people and about {region.customers_k:,} thousand customer accounts.",
        ],
        "water": [
            f"The most serious event of the year in {region.name} came in {inc.month}, when a failed {inc.equipment} "
            f"at {inc.town} cut supply to {inc.households:,} households for {inc.days} days.",
        ],
        "people": [
            f"At year end the {region.name} region employed {region.staff:,} staff.",
        ],
        "customers": [
            f"{region.name} added {region.new_connections:,} new customer connections during {world.year}.",
        ],
        "outlook": [
            f"In {world.year} the {region.name} team received the {region.award}.",
        ],
    }


def region_paragraphs(region: Region, world: World, rng: random.Random, paras_per_section: int) -> list[tuple[str, str, list[str]]]:
    """Returns [(section_key, heading, [paragraph, ...]), ...]."""
    facts = fact_sentences(region, world)
    out = []
    for key, heading in SECTIONS:
        pool = FILLER[key]
        paragraphs = []
        pending_facts = list(facts.get(key, []))
        for p in range(paras_per_section):
            sentences = [_fill(rng, s, region) for s in rng.sample(pool, k=min(len(pool), rng.randint(4, 6)))]
            if pending_facts and (p == paras_per_section // 2 or p == 0 and len(pending_facts) > 1):
                sentences.insert(rng.randint(1, len(sentences)), pending_facts.pop(0))
            paragraphs.append(" ".join(sentences))
        if pending_facts:
            paragraphs[-1] += " " + " ".join(pending_facts)
        out.append((key, heading, paragraphs))
    return out


def chapter_intro(region: Region) -> str:
    return (f"This chapter reports on the {region.name} region: its water, power and transit services, "
            f"its people, and the projects it is building. Numbers are for the calendar year unless a note says otherwise.")
