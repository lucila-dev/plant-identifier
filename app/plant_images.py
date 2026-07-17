"""Plant images: multi-source resolve + local catalog mirroring."""
from __future__ import annotations

import json
import mimetypes
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from app import perenual

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "image_cache.json"
PLANTS_PATH = Path(__file__).resolve().parent.parent / "data" / "plants.json"
CATALOG_DIR = Path(__file__).resolve().parent.parent / "static" / "images" / "catalog"
PLACEHOLDER = "/static/images/plant-placeholder.svg"
USER_AGENT = "BloomScan/1.0 (plant identifier; educational; contact@example.com)"
# Wikimedia blocks some bot UAs with 403; use a browser-like UA for image bytes.
IMAGE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
MIN_IMAGE_BYTES = 1000
REQUEST_DELAY_WIKI = 0.35

DEFAULT_ISSUES = [
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
]


def _load_cache() -> dict[str, str]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict[str, str]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:70] or "plant"


def _perenual_cache_key(query: str) -> str:
    return f"perenual:{query.lower()}"


def _perenual_match_cache_key(query: str) -> str:
    return f"perenual-match:{query.lower()}"


def _wiki_cache_key(title: str) -> str:
    return f"wiki:{title.lower()}"


def _wiki_meta_cache_key(title: str) -> str:
    return f"wiki-meta:{title.lower()}"


def _query_candidates(scientific: str, common_names: list[str]) -> list[str]:
    return perenual.query_candidates(scientific, common_names)


def _wiki_title_candidates(scientific: str, common_names: list[str]) -> list[str]:
    titles: list[str] = []
    sci = scientific.strip()
    if sci:
        titles.append(sci)
        base = re.sub(r"\s*'[^']+'.*$", "", sci).strip()
        if base and base != sci:
            titles.append(base)
    for name in common_names:
        n = name.strip()
        if n:
            titles.append(n)
    seen: set[str] = set()
    out: list[str] = []
    for t in titles:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def _http_get_json(url: str) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, urllib.error.HTTPError):
        return None


def fetch_wikipedia_page(title: str) -> dict[str, Any] | None:
    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="")
    data = _http_get_json(WIKI_SUMMARY.format(title=encoded))
    if not data or data.get("type") == "disambiguation":
        return None
    thumb = (data.get("originalimage") or {}).get("source") or (data.get("thumbnail") or {}).get(
        "source"
    )
    extract = (data.get("extract") or "").strip()
    if not thumb or not extract:
        return None
    lower = thumb.lower()
    if "wikimedia" not in lower and "wikipedia" not in lower:
        return None
    return {
        "title": (data.get("title") or title).strip(),
        "image_url": thumb,
        "description": extract,
        "page_url": (data.get("content_urls") or {}).get("desktop", {}).get("page"),
    }


def _fetch_wikipedia_for_title(title: str, cache: dict[str, str]) -> dict[str, Any] | None:
    key = _wiki_cache_key(title)
    meta_key = _wiki_meta_cache_key(title)
    if key in cache:
        url = cache[key]
        if not url:
            return None
        meta = json.loads(cache.get(meta_key) or "{}")
        meta["image_url"] = url
        return meta

    page = fetch_wikipedia_page(title)
    cache[key] = (page or {}).get("image_url") or ""
    cache[meta_key] = json.dumps(
        {
            "title": (page or {}).get("title") or "",
            "description": (page or {}).get("description") or "",
            "page_url": (page or {}).get("page_url") or "",
        }
        if page
        else {}
    )
    _save_cache(cache)
    time.sleep(REQUEST_DELAY_WIKI)
    return page


def resolve_wikipedia(
    scientific: str, common_names: list[str], cache: dict[str, str]
) -> dict[str, Any] | None:
    for title in _wiki_title_candidates(scientific, common_names):
        page = _fetch_wikipedia_for_title(title, cache)
        if page and page.get("description"):
            return page
    return None


def _inat_cache_key(query: str) -> str:
    return f"inat:{query.lower()}"


def resolve_inaturalist_image(
    scientific: str, common_names: list[str], cache: dict[str, str]
) -> str | None:
    for query in _wiki_title_candidates(scientific, common_names):
        key = _inat_cache_key(query)
        if key in cache:
            if cache[key]:
                return cache[key]
            continue
        params = urllib.parse.urlencode({"q": query, "rank": "species"})
        data = _http_get_json(f"https://api.inaturalist.org/v1/taxa?{params}")
        url = None
        for taxa in (data or {}).get("results") or []:
            photo = taxa.get("default_photo") or {}
            for field in ("medium_url", "square_url", "url"):
                candidate = photo.get(field)
                if candidate and str(candidate).startswith("http"):
                    url = candidate
                    break
            if url:
                break
        cache[key] = url or ""
        _save_cache(cache)
        time.sleep(0.25)
        if url:
            return url
    return None


def _openverse_cache_key(query: str) -> str:
    return f"openverse:{query.lower()}"


def resolve_openverse_image(
    scientific: str, common_names: list[str], cache: dict[str, str]
) -> str | None:
    for query in _wiki_title_candidates(scientific, common_names)[:3]:
        key = _openverse_cache_key(query)
        if key in cache:
            if cache[key]:
                return cache[key]
            continue
        params = urllib.parse.urlencode({"q": query, "page_size": 5})
        data = _http_get_json(f"https://api.openverse.org/v1/images/?{params}")
        url = None
        for row in (data or {}).get("results") or []:
            candidate = row.get("url") or row.get("thumbnail")
            if candidate and str(candidate).startswith("http"):
                # Prefer clearly plant-related titles when possible
                title = (row.get("title") or "").lower()
                q = query.lower()
                if q.split()[0] in title or any(n.lower() in title for n in common_names[:2]):
                    url = candidate
                    break
                if not url:
                    url = candidate
        cache[key] = url or ""
        _save_cache(cache)
        time.sleep(0.25)
        if url:
            return url
    return None


def resolve_any_image(
    scientific: str, common_names: list[str], cache: dict[str, str]
) -> tuple[str | None, str]:
    """Find a usable remote image URL from any available source."""
    wiki = resolve_wikipedia(scientific, common_names, cache)
    if wiki and wiki.get("image_url"):
        return wiki["image_url"], "wikipedia"
    url = resolve_inaturalist_image(scientific, common_names, cache)
    if url:
        return url, "inaturalist"
    url = resolve_openverse_image(scientific, common_names, cache)
    if url:
        return url, "openverse"
    return None, "none"


def _fetch_perenual_for_query(
    query: str,
    scientific: str,
    common_names: list[str],
    cache: dict[str, str],
) -> tuple[str | None, dict | None]:
    key = _perenual_cache_key(query)
    match_key = _perenual_match_cache_key(query)

    if key in cache:
        hit = cache[key]
        match_raw = cache.get(match_key)
        match = json.loads(match_raw) if match_raw else None
        return (hit or None), match

    if not perenual.is_configured():
        return None, None

    results = perenual.search_species(query)
    match = perenual.best_match(scientific, common_names, results)
    url = perenual.image_from_species(match) if match else None
    if not url:
        for species in results:
            url = perenual.image_from_species(species)
            if url:
                if not match:
                    match = species
                break

    cache[key] = url or ""
    cache[match_key] = json.dumps(match) if match else ""
    _save_cache(cache)
    time.sleep(perenual.REQUEST_DELAY)
    return url, match


def _resolve_perenual_image(
    scientific: str, common_names: list[str], cache: dict[str, str]
) -> str | None:
    if not perenual.is_configured():
        return None
    for query in _query_candidates(scientific, common_names):
        url, _ = _fetch_perenual_for_query(query, scientific, common_names, cache)
        if url:
            return url
    return None


def _resolve_perenual_match(
    scientific: str, common_names: list[str], cache: dict[str, str]
) -> dict | None:
    if not perenual.is_configured():
        return None
    for query in _query_candidates(scientific, common_names):
        _, match = _fetch_perenual_for_query(query, scientific, common_names, cache)
        if match:
            return match
    return None


def _ext_from_content_type(ctype: str | None, url: str) -> str:
    if ctype:
        main = ctype.split(";")[0].strip().lower()
        if main == "image/jpeg":
            return ".jpg"
        if main == "image/png":
            return ".png"
        if main == "image/webp":
            return ".webp"
        guessed = mimetypes.guess_extension(main)
        if guessed == ".jpe":
            return ".jpg"
        if guessed:
            return guessed
    path = url.split("?", 1)[0].lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


def is_remote_image_url(url: str | None) -> bool:
    if not url:
        return False
    lower = url.lower()
    if "upgrade_access" in lower or "image/upgrade" in lower:
        return False
    return lower.startswith("https://")


def is_usable_image_url(url: str | None) -> bool:
    if not url or url == PLACEHOLDER:
        return False
    if url.startswith("/static/images/catalog/"):
        path = Path(__file__).resolve().parent.parent / url.lstrip("/")
        return path.exists() and path.stat().st_size >= MIN_IMAGE_BYTES
    return is_remote_image_url(url)


def mirror_remote_image(plant_id: str, remote_url: str, *, retries: int = 4) -> str | None:
    """Download a remote image into static/images/catalog/. Returns local URL or None."""
    if remote_url.startswith("/static/images/catalog/"):
        return remote_url if is_usable_image_url(remote_url) else None
    if not is_remote_image_url(remote_url):
        return None

    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        existing = CATALOG_DIR / f"{plant_id}{ext}"
        if existing.exists() and existing.stat().st_size >= MIN_IMAGE_BYTES:
            return f"/static/images/catalog/{existing.name}"

    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", plant_id).strip("-") or "plant"
    tmp = CATALOG_DIR / f".tmp_{safe_id}"
    hdr = CATALOG_DIR / f".hdr_{safe_id}.txt"
    try:
        for attempt in range(retries):
            proc = subprocess.run(
                [
                    "curl",
                    "-sS",
                    "-L",
                    "-A",
                    IMAGE_USER_AGENT,
                    "-o",
                    str(tmp),
                    "-w",
                    "%{http_code}",
                    "-D",
                    str(hdr),
                    "--max-time",
                    "60",
                    remote_url,
                ],
                capture_output=True,
                text=True,
            )
            try:
                code = int((proc.stdout or "").strip())
            except ValueError:
                code = 0
            if code in (429, 503) and attempt < retries - 1:
                time.sleep(min(8 * (2**attempt), 90))
                continue
            if code != 200 or not tmp.exists() or tmp.stat().st_size < MIN_IMAGE_BYTES:
                tmp.unlink(missing_ok=True)
                return None
            ctype = None
            if hdr.exists():
                for line in hdr.read_text(errors="replace").splitlines():
                    if line.lower().startswith("content-type:"):
                        ctype = line.split(":", 1)[1].strip()
                        break
            # Reject HTML error pages saved as images
            if ctype and "text/html" in ctype.lower():
                tmp.unlink(missing_ok=True)
                if attempt < retries - 1:
                    time.sleep(min(8 * (2**attempt), 90))
                    continue
                return None
            ext = _ext_from_content_type(ctype, remote_url)
            dest = CATALOG_DIR / f"{safe_id}{ext}"
            if dest.exists():
                dest.unlink()
            tmp.rename(dest)
            return f"/static/images/catalog/{dest.name}"
        return None
    finally:
        tmp.unlink(missing_ok=True)
        hdr.unlink(missing_ok=True)


def resolve_image_with_source(
    scientific: str, common_names: list[str], cache: dict[str, str]
) -> tuple[str, str]:
    url = _resolve_perenual_image(scientific, common_names, cache)
    if url:
        return url, "perenual"
    wiki = resolve_wikipedia(scientific, common_names, cache)
    if wiki and wiki.get("image_url"):
        return wiki["image_url"], "wikipedia"
    return PLACEHOLDER, "placeholder"


def resolve_image(scientific: str, common_names: list[str], cache: dict[str, str]) -> str:
    url, _ = resolve_image_with_source(scientific, common_names, cache)
    return url


def lookup_image(scientific: str, common_names: list[str], cache: dict[str, str] | None = None) -> str:
    if cache is None:
        cache = _load_cache()
    return resolve_image(scientific, common_names, cache)


def filter_plants_with_usable_images(plants: list[dict]) -> list[dict]:
    return [p for p in plants if is_usable_image_url(p.get("image_url"))]


filter_plants_with_perenual_images = filter_plants_with_usable_images


def _perenual_reachable() -> bool:
    if not perenual.is_configured():
        return False
    meta = perenual.list_species_page(1)
    return bool(meta and meta.get("data") is not None)


def build_plant_from_seed(
    seed: dict[str, Any], wiki: dict[str, Any] | None, image_url: str, source: str
) -> dict[str, Any]:
    names = list(seed["common_names"])
    description = ((wiki or {}).get("description") or seed.get("description") or "").strip()
    if not description:
        description = (
            f"{names[0]} ({seed['scientific_name']}) is a plant in the family {seed['family']}."
        )
    care = seed.get("care") or {
        "light": "Bright indirect light",
        "water": "Water when the top inch of soil is dry",
        "humidity": "Average household humidity",
    }
    return {
        "id": seed.get("id") or _slug(names[0]),
        "common_names": names,
        "scientific_name": seed["scientific_name"],
        "family": seed["family"],
        "description": description,
        "care": care,
        "common_issues": seed.get("common_issues") or DEFAULT_ISSUES,
        "image_url": image_url,
    }


def rebuild_catalog_from_seeds(
    seeds: list[dict[str, Any]],
    *,
    use_perenual: bool | None = None,
    merge_existing: bool = True,
) -> dict[str, int]:
    """Build/merge plants from curated seeds with correct images + descriptions."""
    from app.plants import load_plants

    cache = _load_cache()
    stats = {
        "seeded": len(seeds),
        "kept": 0,
        "skipped": 0,
        "perenual": 0,
        "wikipedia": 0,
        "merged": 0,
        "perenual_enabled": False,
    }

    if use_perenual is None:
        use_perenual = _perenual_reachable()
    stats["perenual_enabled"] = bool(use_perenual)
    if not use_perenual:
        print("  Bulk API skipped; using Wikipedia/iNaturalist/Openverse.", flush=True)

    by_id: dict[str, dict] = {}
    if merge_existing and PLANTS_PATH.exists():
        existing = json.loads(PLANTS_PATH.read_text(encoding="utf-8"))
        for plant in existing:
            if is_usable_image_url(plant.get("image_url")):
                by_id[plant["id"]] = plant
        stats["merged"] = len(by_id)

    for i, seed in enumerate(seeds, start=1):
        scientific = seed["scientific_name"]
        names = seed["common_names"]
        plant_id = seed.get("id") or _slug(names[0])
        image_url = None
        source = None
        wiki = None

        # Keep existing local mirror if already present for this id
        existing = by_id.get(plant_id)
        if existing and is_usable_image_url(existing.get("image_url")):
            # Still refresh description from Wikipedia when thin/generic
            desc = existing.get("description") or ""
            needs_desc = (
                len(desc) < 80
                or "Care details from" in desc
                or "catalog entry sourced from" in desc
                or "species data." in desc
            )
            if needs_desc:
                wiki = resolve_wikipedia(scientific, names, cache)
                if wiki and wiki.get("description"):
                    existing["description"] = wiki["description"]
                    existing["common_names"] = names
                    existing["scientific_name"] = scientific
                    existing["family"] = seed["family"]
                    if seed.get("care"):
                        existing["care"] = seed["care"]
            stats["kept"] += 1
            if i % 10 == 0 or i == len(seeds):
                print(f"  … {i}/{len(seeds)} (kept {stats['kept']}, skipped {stats['skipped']})", flush=True)
            continue

        if use_perenual:
            image_url = _resolve_perenual_image(scientific, names, cache)
            if image_url:
                source = "api"
                stats["perenual"] += 1

        wiki = resolve_wikipedia(scientific, names, cache)

        candidates: list[tuple[str, str]] = []
        # Prefer non-Wikimedia hosts first when bulk CDN is rate-limited.
        inat = resolve_inaturalist_image(scientific, names, cache)
        if inat:
            candidates.append((inat, "inaturalist"))
        openverse = resolve_openverse_image(scientific, names, cache)
        if openverse:
            candidates.append((openverse, "openverse"))
        if image_url:
            candidates.append((image_url, source or "api"))
        if wiki and wiki.get("image_url"):
            candidates.append((wiki["image_url"], "wikipedia"))
            stats["wikipedia"] += 1

        final_url = None
        chosen_source = None
        seen_urls: set[str] = set()
        for url, src in candidates:
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            local = mirror_remote_image(plant_id, url, retries=2)
            if local:
                final_url = local
                chosen_source = src
                break
            # Stable public hosts can be used remotely when mirroring is blocked
            if src in ("wikipedia", "inaturalist", "openverse") and is_remote_image_url(url):
                final_url = url
                chosen_source = src
                break
            time.sleep(0.3)

        if not final_url:
            stats["skipped"] += 1
            print(f"  skip {plant_id} (no usable image)", flush=True)
            continue

        plant = build_plant_from_seed(seed, wiki, final_url, chosen_source or "unknown")
        by_id[plant_id] = plant
        stats["kept"] += 1
        if i % 10 == 0 or i == len(seeds):
            print(f"  … {i}/{len(seeds)} (kept {stats['kept']}, skipped {stats['skipped']})", flush=True)

    plants = sorted(by_id.values(), key=lambda p: p["common_names"][0].lower())
    PLANTS_PATH.write_text(json.dumps(plants, indent=2), encoding="utf-8")
    _save_cache(cache)
    load_plants.cache_clear()
    stats["plant_count"] = len(plants)
    return stats


def rebuild_catalog_from_perenual(
    *,
    max_pages: int | None = None,
    max_plants: int | None = None,
    mirror: bool = True,
) -> dict[str, int]:
    from app.plants import load_plants

    if not perenual.is_configured():
        raise RuntimeError("PERENUAL_API_KEY is not configured")

    plants: list[dict] = []
    stats = {
        "pages": 0,
        "scanned": 0,
        "kept": 0,
        "skipped_no_image": 0,
        "mirrored": 0,
        "mirror_failed": 0,
        "last_page": 0,
    }

    for page, rows in perenual.iter_species_pages(max_pages=max_pages):
        stats["pages"] += 1
        for species in rows:
            stats["scanned"] += 1
            plant = perenual.plant_from_species(species)
            if not plant:
                stats["skipped_no_image"] += 1
                continue
            if mirror:
                local = mirror_remote_image(plant["id"], plant["image_url"])
                if not local:
                    stats["mirror_failed"] += 1
                    continue
                plant["image_url"] = local
                stats["mirrored"] += 1
            plant.pop("image_source", None)
            plants.append(plant)
            stats["kept"] += 1
            if max_plants is not None and len(plants) >= max_plants:
                break
        print(f"  … page {page}: kept {stats['kept']} (scanned {stats['scanned']})", flush=True)
        if max_plants is not None and len(plants) >= max_plants:
            break

    if max_plants is not None:
        plants = plants[:max_plants]

    meta = perenual.list_species_page(1)
    if meta:
        stats["last_page"] = int(meta.get("last_page") or 0)

    PLANTS_PATH.write_text(json.dumps(plants, indent=2), encoding="utf-8")
    _save_cache({k: v for k, v in _load_cache().items() if k.startswith(("perenual", "wiki"))})
    load_plants.cache_clear()
    stats["plant_count"] = len(plants)
    return stats


def update_all_plants(*, limit: int | None = None, enrich_names: bool = True) -> dict[str, int]:
    from app.plants import load_plants

    plants = json.loads(PLANTS_PATH.read_text(encoding="utf-8"))
    cache = _load_cache()
    stats = {
        "updated": 0,
        "perenual": 0,
        "wikipedia": 0,
        "placeholder": 0,
        "enriched": 0,
        "removed": 0,
        "mirrored": 0,
        "plant_count": 0,
    }

    targets = plants[:limit] if limit else plants
    kept: list[dict] = []

    for plant in targets:
        if enrich_names and perenual.is_configured():
            species = _resolve_perenual_match(plant["scientific_name"], plant["common_names"], cache)
            if species and perenual.enrich_plant_fields(plant, species):
                stats["enriched"] += 1

        # Keep good local mirrors
        if is_usable_image_url(plant.get("image_url")) and str(plant.get("image_url", "")).startswith(
            "/static/images/catalog/"
        ):
            kept.append(plant)
            continue

        url, source = resolve_image_with_source(
            plant["scientific_name"], plant["common_names"], cache
        )
        stats[source] = stats.get(source, 0) + 1
        if source == "placeholder":
            stats["removed"] += 1
            continue

        local = mirror_remote_image(plant["id"], url)
        if not local:
            stats["removed"] += 1
            continue
        if source == "wikipedia":
            wiki = resolve_wikipedia(plant["scientific_name"], plant["common_names"], cache)
            if wiki and wiki.get("description"):
                plant["description"] = wiki["description"]
        if plant.get("image_url") != local:
            stats["updated"] += 1
        plant["image_url"] = local
        plant["image_source"] = source
        stats["mirrored"] += 1
        kept.append(plant)

    if limit is not None:
        for plant in plants[limit:]:
            if is_usable_image_url(plant.get("image_url")):
                kept.append(plant)
            else:
                stats["removed"] += 1

    PLANTS_PATH.write_text(json.dumps(kept, indent=2), encoding="utf-8")
    _save_cache(cache)
    load_plants.cache_clear()
    stats["plant_count"] = len(kept)
    return stats


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    args = sys.argv[1:]
    if args and args[0] in {"--curated", "curated"}:
        from scripts.curated_plants import CURATED_SEEDS

        print(f"Building curated catalog from {len(CURATED_SEEDS)} seeds…", flush=True)
        print(rebuild_catalog_from_seeds(CURATED_SEEDS), flush=True)
    elif args and args[0] in {"--rebuild", "rebuild"}:
        pages = int(args[1]) if len(args) > 1 else None
        plants_cap = int(args[2]) if len(args) > 2 else None
        print("Rebuilding catalog from species API (mirror locally)…", flush=True)
        print(rebuild_catalog_from_perenual(max_pages=pages, max_plants=plants_cap), flush=True)
    elif args and args[0] in {"--filter", "filter"}:
        from app.plants import load_plants

        plants = json.loads(PLANTS_PATH.read_text(encoding="utf-8"))
        before = len(plants)
        plants = filter_plants_with_usable_images(plants)
        PLANTS_PATH.write_text(json.dumps(plants, indent=2), encoding="utf-8")
        load_plants.cache_clear()
        print({"before": before, "kept": len(plants), "removed": before - len(plants)}, flush=True)
    else:
        lim = int(args[0]) if args else None
        print("Updating images (API → Wikimedia/other, mirror locally)…", flush=True)
        print(update_all_plants(limit=lim), flush=True)
