"""Perenual plant API client (species search, names, images)."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = "https://perenual.com/api/v2"
USER_AGENT = "BloomScan/1.0 (plant identifier; educational; contact@example.com)"
REQUEST_DELAY = 0.6
MAX_RETRIES = 3
UPGRADE_MARKERS = ("upgrade_access", "image/upgrade")


def get_api_key() -> str:
    return os.getenv("PERENUAL_API_KEY", "").strip()


def is_configured() -> bool:
    return bool(get_api_key())


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_cultivar(text: str) -> str:
    return re.sub(r"\s*'[^']+'.*$", "", text).strip()


def is_valid_image_url(url: str | None) -> bool:
    if not url:
        return False
    lower = url.lower()
    return not any(marker in lower for marker in UPGRADE_MARKERS)


# Back-compat alias
_is_valid_image_url = is_valid_image_url


def image_from_species(species: dict[str, Any]) -> str | None:
    img = species.get("default_image") or {}
    for key in ("medium_url", "regular_url", "small_url", "original_url", "thumbnail"):
        url = img.get(key)
        if _is_valid_image_url(url):
            return url
    return None


def _http_get_json(url: str) -> dict[str, Any] | None:
    """Fetch JSON via curl (more reliable under local proxy/sandbox constraints)."""
    import subprocess
    import tempfile

    for attempt in range(MAX_RETRIES):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            out_path = tmp.name
        try:
            proc = subprocess.run(
                [
                    "curl",
                    "-sS",
                    "-L",
                    "-A",
                    USER_AGENT,
                    "-H",
                    "Accept: application/json",
                    "-o",
                    out_path,
                    "-w",
                    "%{http_code}",
                    "--max-time",
                    "25",
                    url,
                ],
                capture_output=True,
                text=True,
            )
            code_s = (proc.stdout or "").strip()
            try:
                code = int(code_s)
            except ValueError:
                code = 0
            body = Path(out_path).read_bytes() if Path(out_path).exists() else b""
            if code in (429, 503) and attempt < MAX_RETRIES - 1:
                time.sleep(min(5 * (2**attempt), 60))
                continue
            if code != 200 or not body:
                return None
            return json.loads(body.decode("utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            if attempt < MAX_RETRIES - 1:
                time.sleep(min(5 * (2**attempt), 60))
                continue
            return None
        finally:
            try:
                Path(out_path).unlink(missing_ok=True)
            except OSError:
                pass
    return None


def search_species(query: str) -> list[dict[str, Any]]:
    key = get_api_key()
    q = query.strip()
    if not key or not q:
        return []

    params = urllib.parse.urlencode({"key": key, "q": q})
    data = _http_get_json(f"{BASE_URL}/species-list?{params}")
    if not data:
        return []
    return data.get("data") or []


def list_species_page(page: int = 1, **filters: Any) -> dict[str, Any] | None:
    """Fetch one page of the Perenual species list (includes pagination metadata)."""
    key = get_api_key()
    if not key:
        return None

    params: dict[str, Any] = {"key": key, "page": max(1, int(page))}
    for name, value in filters.items():
        if value is None or value == "":
            continue
        params[name] = value

    return _http_get_json(f"{BASE_URL}/species-list?{urllib.parse.urlencode(params)}")


def iter_species_pages(*, max_pages: int | None = None, start_page: int = 1):
    """Yield (page_number, species_list) until last page or max_pages."""
    page = max(1, start_page)
    fetched = 0
    while True:
        data = list_species_page(page)
        if not data:
            break
        species = data.get("data") or []
        yield page, species
        fetched += 1
        last_page = int(data.get("last_page") or page)
        if page >= last_page:
            break
        if max_pages is not None and fetched >= max_pages:
            break
        page += 1
        time.sleep(REQUEST_DELAY)


_WATERING_LABELS = {
    "frequent": "Keep soil evenly moist; water often",
    "average": "Water when the top inch of soil is dry",
    "minimum": "Allow soil to dry between waterings",
    "none": "Minimal watering",
}

_SUNLIGHT_LABELS = {
    "full_shade": "Full shade",
    "part_shade": "Part shade",
    "sun-part_shade": "Sun to part shade",
    "full_sun": "Full sun",
}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:70] or "plant"


def care_from_species(species: dict[str, Any]) -> dict[str, str]:
    watering = species.get("watering")
    if isinstance(watering, str):
        water = _WATERING_LABELS.get(watering.lower().strip(), watering.replace("_", " ").title())
    else:
        water = "Water when the top inch of soil is dry"

    sunlight = species.get("sunlight")
    if isinstance(sunlight, list) and sunlight:
        labels = []
        for item in sunlight:
            if isinstance(item, str):
                labels.append(_SUNLIGHT_LABELS.get(item.lower().strip(), item.replace("_", " ").title()))
        light = ", ".join(labels) if labels else "Bright indirect light"
    elif isinstance(sunlight, str) and sunlight.strip():
        key = sunlight.lower().strip()
        light = _SUNLIGHT_LABELS.get(key, sunlight.replace("_", " ").title())
    else:
        light = "Bright indirect light"

    return {"light": light, "water": water, "humidity": "Average household humidity"}


def plant_from_species(species: dict[str, Any]) -> dict[str, Any] | None:
    """Map a Perenual species record to a catalog plant. Requires a usable image."""
    image_url = image_from_species(species)
    if not image_url:
        return None

    perenual_id = species.get("id")
    if perenual_id is None:
        return None

    common = (species.get("common_name") or "").strip()
    sci_list = [s for s in (species.get("scientific_name") or []) if isinstance(s, str) and s.strip()]
    scientific = sci_list[0].strip() if sci_list else common
    if not scientific:
        return None

    others = [o.strip() for o in (species.get("other_name") or []) if isinstance(o, str) and o.strip()]
    names: list[str] = []
    if common:
        names.append(common)
    for name in others:
        if name.lower() not in {n.lower() for n in names}:
            names.append(name)
    if not names:
        names = [scientific]

    family = species.get("family")
    if not isinstance(family, str) or not family.strip():
        family = (species.get("genus") or "Unknown").strip() or "Unknown"

    genus = (species.get("genus") or "").strip()
    fam = family.strip() if isinstance(family, str) else "Unknown"
    if genus:
        description = f"{names[0]} ({scientific}) is a plant in the genus {genus} (family {fam})."
    else:
        description = f"{names[0]} ({scientific}) is a plant in the {fam} family."

    plant_id = f"{_slug(names[0])}-{perenual_id}"

    return {
        "id": plant_id,
        "common_names": names,
        "scientific_name": scientific,
        "family": family.strip(),
        "description": description,
        "care": care_from_species(species),
        "common_issues": [
            {
                "symptom": "Yellow leaves, soft stems",
                "causes": ["Overwatering", "Poor drainage"],
                "treatments": ["Let soil dry", "Improve drainage"],
            },
            {
                "symptom": "Crispy tips / wilting",
                "causes": ["Underwatering", "Low humidity"],
                "treatments": ["Water thoroughly", "Raise humidity"],
            },
        ],
        "image_url": image_url,
        "perenual_id": perenual_id,
    }


def query_candidates(scientific: str, common_names: list[str]) -> list[str]:
    candidates: list[str] = []
    sci = scientific.strip()
    if sci:
        candidates.append(sci)
        base = _strip_cultivar(sci)
        if base and base != sci:
            candidates.append(base)
    for name in common_names:
        n = name.strip()
        if n:
            candidates.append(n)
            short = _strip_cultivar(n)
            if short and short != n:
                candidates.append(short)
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def score_match(scientific: str, common_names: list[str], species: dict[str, Any]) -> int:
    score = 0
    sci_target = _normalize(_strip_cultivar(scientific))
    sci_names = [_normalize(s) for s in (species.get("scientific_name") or []) if s]
    common = _normalize(species.get("common_name") or "")
    others = [_normalize(o) for o in (species.get("other_name") or []) if o]

    for sn in sci_names:
        if sci_target and sn == sci_target:
            score = max(score, 100)
        elif sci_target and sn and (sci_target in sn or sn in sci_target):
            score = max(score, 88)
        elif sci_target and sn:
            target_genus = sci_target.split()[0] if sci_target.split() else ""
            species_genus = sn.split()[0] if sn.split() else ""
            if target_genus and target_genus == species_genus:
                score = max(score, 55)

    for name in common_names:
        nn = _normalize(_strip_cultivar(name))
        if not nn:
            continue
        if nn == common:
            score = max(score, 95)
        elif common and (nn in common or common in nn):
            score = max(score, 78)

    for other in others:
        for name in common_names:
            nn = _normalize(_strip_cultivar(name))
            if nn and (nn == other or nn in other or other in nn):
                score = max(score, 72)

    if image_from_species(species):
        score += 3

    return score


def best_match(
    scientific: str,
    common_names: list[str],
    results: list[dict[str, Any]],
    *,
    min_score: int = 60,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = 0
    for species in results:
        score = score_match(scientific, common_names, species)
        if score > best_score:
            best_score = score
            best = species
    if best and best_score >= min_score:
        return best
    return None


def lookup_species(
    scientific: str,
    common_names: list[str],
    *,
    min_score: int = 60,
) -> dict[str, Any] | None:
    if not is_configured():
        return None

    best: dict[str, Any] | None = None
    best_score = 0

    for query in query_candidates(scientific, common_names):
        for species in search_species(query):
            score = score_match(scientific, common_names, species)
            if score > best_score:
                best_score = score
                best = species
        time.sleep(REQUEST_DELAY)

    if best and best_score >= min_score:
        return best
    return None


def lookup_image(scientific: str, common_names: list[str]) -> str | None:
    species = lookup_species(scientific, common_names)
    if not species:
        return None
    return image_from_species(species)


def enrich_names(common_names: list[str], species: dict[str, Any]) -> list[str]:
    """Add Perenual common name when missing from catalog."""
    perenual_name = (species.get("common_name") or "").strip()
    if not perenual_name:
        return common_names

    existing = {_normalize(n) for n in common_names}
    if _normalize(perenual_name) in existing:
        return common_names

    return [perenual_name] + list(common_names)


def enrich_plant_fields(plant: dict[str, Any], species: dict[str, Any]) -> bool:
    changed = False

    enriched = enrich_names(plant.get("common_names", []), species)
    if enriched != plant.get("common_names"):
        plant["common_names"] = enriched
        changed = True

    family = species.get("family")
    if family and isinstance(family, str) and family.strip():
        cleaned = family.strip()
        if plant.get("family") != cleaned:
            plant["family"] = cleaned
            changed = True

    return changed
