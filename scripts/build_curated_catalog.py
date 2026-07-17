#!/usr/bin/env python3
"""Build data/plants.json from curated seeds with correct Wikipedia/Perenual media."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.plant_images import rebuild_catalog_from_seeds  # noqa: E402
from scripts.curated_plants import CURATED_SEEDS  # noqa: E402


def main() -> None:
    print(f"Building curated catalog from {len(CURATED_SEEDS)} seeds…", flush=True)
    stats = rebuild_catalog_from_seeds(CURATED_SEEDS)
    print(stats, flush=True)


if __name__ == "__main__":
    main()
