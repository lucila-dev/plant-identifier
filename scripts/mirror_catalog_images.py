#!/usr/bin/env python3
"""Mirror Perenual/Wasabi plant images locally and prune failures."""
from __future__ import annotations

import json
import mimetypes
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLANTS_PATH = ROOT / "data" / "plants.json"
CATALOG_DIR = ROOT / "static" / "images" / "catalog"
USER_AGENT = "BloomScan/1.0"
WORKERS = 4
MIN_BYTES = 1000
SPECIES_PAGE = "https://perenual.com/plant-species-database-search-finder/species/2498"
VENUS_ID = "venus-flytrap"

VENUS_ENTRY = {
    "id": VENUS_ID,
    "common_names": ["Venus Flytrap", "Venus fly trap"],
    "scientific_name": "Dionaea muscipula",
    "family": "Droseraceae",
    "description": (
        "Venus Flytrap (Dionaea muscipula) is a carnivorous plant known for "
        "its hinged snap traps that close on insects."
    ),
    "care": {
        "light": "Full sun, part shade",
        "water": "Allow soil to dry between waterings; use distilled/rain water",
        "humidity": "Medium",
    },
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
    "image_url": f"/static/images/catalog/{VENUS_ID}.jpg",
    "perenual_id": 2498,
}


def curl_get(url: str, dest: Path, timeout: int = 60) -> tuple[int, str | None]:
    """Download URL to dest via curl. Returns (http_code, content_type)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    ctype_file = Path(tempfile.mktemp(prefix="ctype_"))
    try:
        cmd = [
            "curl",
            "-sS",
            "-L",
            "-A",
            USER_AGENT,
            "-o",
            str(dest),
            "-w",
            "%{http_code}",
            "-D",
            str(ctype_file),
            "--max-time",
            str(timeout),
            url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        code_str = (proc.stdout or "").strip()
        try:
            code = int(code_str)
        except ValueError:
            code = 0
        ctype = None
        if ctype_file.exists():
            headers = ctype_file.read_text(errors="replace")
            for line in headers.splitlines():
                if line.lower().startswith("content-type:"):
                    ctype = line.split(":", 1)[1].strip()
                    break
        if proc.returncode != 0 and code == 0:
            return 0, None
        return code, ctype
    finally:
        if ctype_file.exists():
            ctype_file.unlink(missing_ok=True)


def curl_get_bytes(url: str, timeout: int = 60) -> tuple[int, bytes]:
    cmd = [
        "curl",
        "-sS",
        "-L",
        "-A",
        USER_AGENT,
        "-o",
        "-",
        "-w",
        "\n%{http_code}",
        "--max-time",
        str(timeout),
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 and not proc.stdout:
        return 0, b""
    raw = proc.stdout
    # last line is http code
    nl = raw.rfind(b"\n")
    if nl < 0:
        return 0, raw
    body, code_b = raw[:nl], raw[nl + 1 :]
    try:
        code = int(code_b.decode().strip())
    except ValueError:
        code = 0
    return code, body


def ext_from_content_type(ctype: str | None, url: str) -> str:
    if ctype:
        main = ctype.split(";")[0].strip().lower()
        if main == "image/jpeg":
            return ".jpg"
        if main == "image/png":
            return ".png"
        if main == "image/webp":
            return ".webp"
        if main == "image/gif":
            return ".gif"
        guessed = mimetypes.guess_extension(main)
        if guessed == ".jpe":
            return ".jpg"
        if guessed:
            return guessed
    path = url.split("?", 1)[0].lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


def is_remote_perenual(url: str) -> bool:
    u = (url or "").lower()
    return "wasabisys" in u or "perenual.com" in u or "perenual" in u


def find_existing_local(plant_id: str) -> Path | None:
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        p = CATALOG_DIR / f"{plant_id}{ext}"
        if p.exists() and p.stat().st_size > MIN_BYTES:
            return p
    return None


def download_venus() -> Path:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    dest = CATALOG_DIR / f"{VENUS_ID}.jpg"
    if dest.exists() and dest.stat().st_size > MIN_BYTES:
        print(f"[venus] skip existing {dest} ({dest.stat().st_size} bytes)")
        return dest

    print(f"[venus] fetching species page {SPECIES_PAGE}")
    code, html = curl_get_bytes(SPECIES_PAGE)
    if code != 200 or not html:
        raise RuntimeError(f"Species page HTTP {code}")
    text = html.decode("utf-8", errors="replace")
    patterns = [
        r'https://s3\.us-central-1\.wasabisys\.com/perenual/species_image/2498_dionaea_muscipula/medium/[^"\'\s>]+\.jpe?g[^"\'\s>]*',
        r'https://[^"\'\s>]*2498_dionaea_muscipula/medium/[^"\'\s>]+\.jpe?g[^"\'\s>]*',
        r'https://s3\.us-central-1\.wasabisys\.com/perenual/species_image/2498_dionaea_muscipula/[^"\'\s>]+\.jpe?g[^"\'\s>]*',
    ]
    url = None
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            url = m.group(0).replace("&amp;", "&")
            break
    if not url:
        raise RuntimeError("Could not find signed Wasabi URL for Dionaea muscipula on species page")

    print("[venus] downloading image (URL redacted)")
    code, ctype = curl_get(url, dest)
    if code != 200 or not dest.exists() or dest.stat().st_size < MIN_BYTES:
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise RuntimeError(f"Venus image download failed HTTP {code}")
    print(f"[venus] saved {dest} ({dest.stat().st_size} bytes, ctype={ctype})")
    return dest


def download_one(plant: dict) -> tuple[str, str | None, str]:
    pid = plant["id"]
    url = plant.get("image_url") or ""

    existing = find_existing_local(pid)
    if existing:
        rel = f"/static/images/catalog/{existing.name}"
        return pid, rel, "skip_exists"

    if not is_remote_perenual(url):
        if url.startswith("/static/images/catalog/"):
            rel = url.lstrip("/")
            fp = ROOT / rel
            if fp.exists() and fp.stat().st_size > MIN_BYTES:
                return pid, url, "already_local"
            return pid, None, "local_missing"
        return pid, url, "keep_other"

    tmp = CATALOG_DIR / f".tmp_{pid}"
    try:
        code, ctype = curl_get(url, tmp)
        if code != 200:
            tmp.unlink(missing_ok=True)
            return pid, None, f"http_{code}"
        if not tmp.exists() or tmp.stat().st_size < MIN_BYTES:
            size = tmp.stat().st_size if tmp.exists() else 0
            tmp.unlink(missing_ok=True)
            return pid, None, f"too_small:{size}"
        ext = ext_from_content_type(ctype, url)
        dest = CATALOG_DIR / f"{pid}{ext}"
        tmp.replace(dest)
        return pid, f"/static/images/catalog/{pid}{ext}", "ok"
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return pid, None, f"error:{type(e).__name__}"


def main() -> int:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    download_venus()

    plants = json.loads(PLANTS_PATH.read_text())
    plants = [p for p in plants if p.get("id") != VENUS_ID]
    plants.insert(0, dict(VENUS_ENTRY))

    to_process = []
    for p in plants:
        if p["id"] == VENUS_ID:
            continue
        url = p.get("image_url") or ""
        if is_remote_perenual(url) or url.startswith("/static/images/catalog/"):
            to_process.append(p)

    print(f"Mirroring {len(to_process)} plants with {WORKERS} workers...")
    results: dict[str, tuple[str | None, str]] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(download_one, p): p["id"] for p in to_process}
        for fut in as_completed(futs):
            pid, new_url, status = fut.result()
            results[pid] = (new_url, status)
            done += 1
            if done % 25 == 0 or done == len(to_process):
                print(f"progress {done}/{len(to_process)}", flush=True)

    new_plants = [dict(VENUS_ENTRY)]
    removed = 0
    ok = 0
    skipped = 0
    for p in plants:
        if p["id"] == VENUS_ID:
            continue
        if p["id"] not in results:
            new_plants.append(p)
            continue
        new_url, status = results[p["id"]]
        if new_url is None:
            removed += 1
            continue
        if status == "ok":
            ok += 1
        elif status.startswith("skip") or status == "already_local":
            skipped += 1
        p = dict(p)
        p["image_url"] = new_url
        new_plants.append(p)

    venus_path = find_existing_local(VENUS_ID) or (CATALOG_DIR / f"{VENUS_ID}.jpg")
    if not venus_path.exists() or venus_path.stat().st_size <= MIN_BYTES:
        print("ERROR: Venus image missing after mirror", file=sys.stderr)
        return 1
    new_plants[0]["image_url"] = f"/static/images/catalog/{venus_path.name}"

    PLANTS_PATH.write_text(json.dumps(new_plants, indent=2, ensure_ascii=False) + "\n")
    print(
        f"Wrote {PLANTS_PATH}: total={len(new_plants)} downloaded_ok={ok} "
        f"skipped_existing={skipped} removed={removed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
