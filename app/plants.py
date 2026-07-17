from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.schemas import Plant, PlantSummary

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "plants.json"


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=1)
def load_plants() -> list[Plant]:
    with DATA_PATH.open(encoding="utf-8") as f:
        raw = json.load(f)
    return [Plant.model_validate(item) for item in raw]


def _watering_frequency_label(plant: Plant) -> str:
    """Prefer an explicit frequency field; otherwise derive from care data."""
    care = plant.care
    explicit = getattr(care, "watering_frequency", None) or getattr(plant, "watering_frequency", None)
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    # Lazy import avoids circular import with care_schedule → plants
    from app.care_schedule import build_care_schedule

    schedule = build_care_schedule(
        catalog_plant_id=plant.id,
        species_name=plant.common_names[0] if plant.common_names else "",
        scientific_name=plant.scientific_name,
        light=care.light,
        water=care.water,
        humidity=care.humidity,
    )
    days = schedule.watering_interval_days
    if days <= 1:
        return "Daily"
    if days == 7:
        return "Every week"
    if days % 7 == 0 and days >= 14:
        weeks = days // 7
        return f"Every ~{weeks} weeks"
    return f"Every ~{days} days"


def _to_summary(plant: Plant) -> PlantSummary:
    return PlantSummary(
        id=plant.id,
        primary_name=plant.common_names[0],
        common_names=plant.common_names,
        scientific_name=plant.scientific_name,
        family=plant.family,
        description=plant.description,
        image_url=plant.image_url,
        watering_frequency=_watering_frequency_label(plant),
    )


def get_plant(plant_id: str) -> Optional[Plant]:
    for plant in load_plants():
        if plant.id == plant_id:
            return plant
    return None


def _score_plant(query: str, plant: Plant) -> int:
    q = _normalize(query)
    if not q:
        return 0

    names = [_normalize(n) for n in plant.common_names]
    sci = _normalize(plant.scientific_name)
    family = _normalize(plant.family)
    haystacks = names + [sci, family]

    score = 0
    for hay in haystacks:
        if q == hay:
            score = max(score, 100)
        elif hay.startswith(q + " ") or hay.startswith(q):
            # Full common-name prefix beats loose contains
            score = max(score, 90 if hay.startswith(q + " ") or q == hay.split()[0] else 80)
        elif f" {q} " in f" {hay} ":
            score = max(score, 70)
        elif q in hay:
            score = max(score, 55)

    tokens = [t for t in q.split() if len(t) >= 4]
    if tokens:
        for hay in names + [sci]:
            hay_tokens = set(hay.split())
            overlap = sum(1 for t in tokens if t in hay_tokens)
            if overlap == len(tokens):
                score = max(score, 85)
            elif overlap:
                score = max(score, 40 + overlap * 10)

    return score


def search_plants(query: str, limit: int = 24) -> list[PlantSummary]:
    q = _normalize(query)
    if not q:
        return [_to_summary(p) for p in load_plants()[:limit]]

    scored: list[tuple[int, Plant]] = []
    for plant in load_plants():
        score = _score_plant(q, plant)
        if score:
            scored.append((score, plant))

    scored.sort(key=lambda item: (-item[0], item[1].common_names[0].lower()))
    return [_to_summary(plant) for _, plant in scored[:limit]]


FEATURED_NAME_HINTS = (
    "venus flytrap",
    "monstera",
    "snake plant",
    "pothos",
    "fiddle leaf",
    "peace lily",
    "aloe",
    "orchid",
)


def featured_plants(limit: int = 8) -> list[PlantSummary]:
    plants = load_plants()
    found: list[Plant] = []
    used: set[str] = set()

    for hint in FEATURED_NAME_HINTS:
        for plant in plants:
            if plant.id in used:
                continue
            hay = " ".join(plant.common_names + [plant.scientific_name]).lower()
            if hint in hay:
                found.append(plant)
                used.add(plant.id)
                break
        if len(found) >= limit:
            break

    if len(found) < limit:
        for plant in plants:
            if plant.id not in used:
                found.append(plant)
                used.add(plant.id)
            if len(found) >= limit:
                break
    return [_to_summary(p) for p in found[:limit]]


def match_catalog_plant(
    common_name: Optional[str] = None,
    scientific_name: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[Plant]:
    """Best-effort link from a diagnosis (or free text) to a catalog plant."""
    queries = [q for q in (scientific_name, common_name, notes) if q]
    if not queries:
        return None

    candidates: list[tuple[int, Plant]] = []
    for plant in load_plants():
        score = 0
        for query in queries:
            score = max(score, _score_plant(query, plant))
            nq = _normalize(query)
            sci = _normalize(plant.scientific_name)
            if sci and sci in nq:
                score = max(score, 100)
            for name in plant.common_names:
                nn = _normalize(name)
                if not nn:
                    continue
                if nn in nq:
                    score = max(score, 95)
                else:
                    name_tokens = [t for t in nn.split() if len(t) > 2]
                    note_tokens = set(nq.split())
                    if name_tokens and all(t in note_tokens for t in name_tokens):
                        score = max(score, 88)
        if score >= 70:
            candidates.append((score, plant))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1].common_names[0].lower()))
    return candidates[0][1]


def related_plants(plant_id: str, limit: int = 4) -> list[PlantSummary]:
    plant = get_plant(plant_id)
    if not plant:
        return []

    same_family = [
        p for p in load_plants() if p.family == plant.family and p.id != plant.id
    ]
    same_family.sort(key=lambda p: p.common_names[0].lower())
    if len(same_family) >= limit:
        return [_to_summary(p) for p in same_family[:limit]]

    extras = [
        p
        for p in load_plants()
        if p.id != plant.id and p.id not in {x.id for x in same_family}
    ]
    extras.sort(key=lambda p: p.common_names[0].lower())
    combined = same_family + extras
    return [_to_summary(p) for p in combined[:limit]]

