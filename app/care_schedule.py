from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.plants import get_plant


@dataclass
class CareSchedule:
    watering_interval_days: int
    fertilize_interval_days: int
    light: str
    water: str
    humidity: str
    watering_tip: str
    fertilize_tip: str
    light_tip: str
    humidity_tip: str


def _infer_interval_from_water_text(water: str) -> int:
    w = water.lower()
    if any(x in w for x in ("sparingly", "dry fully", "dry between", "infrequently", "almost dry")):
        return 14
    if any(x in w for x in ("never let", "lightly moist", "evenly moist", "keep moist", "never dry")):
        return 4
    if any(x in w for x in ("when top", "when mostly", "when soil dries", "when dry")):
        return 7
    if "weekly" in w or "week" in w:
        return 7
    return 7


def _infer_plant_type(catalog_id: Optional[str], species_name: str, scientific_name: str) -> str:
    text = " ".join(filter(None, [catalog_id or "", species_name, scientific_name])).lower()
    if any(x in text for x in ("cactus", "succulent", "aloe", "jade", "echeveria", "haworthia", "sedum", "lithops")):
        return "succulent"
    if any(x in text for x in ("fern", "calathea", "maranta", "fittonia", "orchid", "begonia")):
        return "humidity_lover"
    if any(x in text for x in ("venus", "flytrap", "dionaea", "carnivorous", "pitcher")):
        return "carnivorous"
    if any(x in text for x in ("snake", "zz", "pothos", "philodendron", "monstera")):
        return "tropical"
    return "houseplant"


def build_care_schedule(
    *,
    catalog_plant_id: Optional[str] = None,
    species_name: str = "",
    scientific_name: str = "",
    light: str = "",
    water: str = "",
    humidity: str = "",
) -> CareSchedule:
    catalog = get_plant(catalog_plant_id) if catalog_plant_id else None
    if catalog:
        light = light or catalog.care.light
        water = water or catalog.care.water
        humidity = humidity or catalog.care.humidity
        species_name = species_name or catalog.common_names[0]
        scientific_name = scientific_name or catalog.scientific_name

    plant_type = _infer_plant_type(catalog_plant_id, species_name, scientific_name)
    interval = _infer_interval_from_water_text(water or "")

    if plant_type == "succulent":
        interval = max(interval, 14)
        watering_tip = "Let soil dry fully between waterings — usually every 2–3 weeks indoors."
        fertilize_interval = 60
        fertilize_tip = "Feed lightly in spring and summer, about once every 2 months."
    elif plant_type == "humidity_lover":
        interval = min(interval, 5)
        watering_tip = "Keep soil lightly moist — check every 4–5 days; never let it go bone dry."
        fertilize_interval = 30
        fertilize_tip = "Weak liquid feed monthly during active growth."
    elif plant_type == "carnivorous":
        interval = 3
        watering_tip = "Keep moist with distilled or rainwater — tray method works well; every 2–4 days."
        fertilize_interval = 0
        fertilize_tip = "Do not fertilize — they catch their own snacks."
    elif plant_type == "tropical":
        interval = 7
        watering_tip = "Water when the top 2–3 cm of soil feels dry — roughly once a week."
        fertilize_interval = 30
        fertilize_tip = "Balanced houseplant fertilizer monthly in spring and summer."
    else:
        watering_tip = f"Water on a {interval}-day rhythm, adjusting if soil stays wet or dry too fast."
        fertilize_interval = 45
        fertilize_tip = "Feed every 6 weeks during the growing season if the plant is actively growing."

    if not light:
        light = "Bright indirect light"
    if not water:
        water = "Water when top soil dries"
    if not humidity:
        humidity = "Medium"

    return CareSchedule(
        watering_interval_days=interval,
        fertilize_interval_days=fertilize_interval,
        light=light,
        water=water,
        humidity=humidity,
        watering_tip=watering_tip,
        fertilize_tip=fertilize_tip,
        light_tip=f"Give {light.lower()} — rotate the pot weekly for even growth.",
        humidity_tip=f"Target {humidity.lower()} humidity; mist or use a pebble tray if leaves crisp up.",
    )


def days_since(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00").split(".")[0])
    except ValueError:
        return None
    return (datetime.utcnow() - dt.replace(tzinfo=None)).days


def watering_status(last_watered: Optional[str], interval_days: int) -> dict:
    since = days_since(last_watered)
    if since is None:
        return {
            "status": "unknown",
            "label": "Not logged yet",
            "message": "Log a watering to start your care rhythm.",
        }
    if since >= interval_days:
        return {
            "status": "due",
            "label": "Time to water",
            "message": f"Last watered {since} day(s) ago — due around every {interval_days} days.",
        }
    if since >= interval_days - 1:
        return {
            "status": "soon",
            "label": "Water soon",
            "message": f"Last watered {since} day(s) ago — check soil tomorrow.",
        }
    return {
        "status": "ok",
        "label": "All good",
        "message": f"Last watered {since} day(s) ago — next check in ~{interval_days - since} day(s).",
    }
