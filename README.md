# BloomScan

Cute plant scan app — identify plants by photo, search the catalog, and track your own collection with care reminders.

## Features

- **Scan** — upload or capture a plant photo for diagnosis
- **Search** — find plants by nickname or scientific name (500+ with photos)
- **Sign in** — create an account and save plants to your collection
- **Collection** — photos, notes, care history, watering reminders
- **Care suggestions** — watering rhythm, light, humidity, and feed tips by plant type
- **OpenAI-ready** — mock diagnosis until you add an API key

## Setup

```bash
cd "Plant Identifier "
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Accounts & collection

1. Click **Sign in** → **Create an account**
2. Open **Collection** to see your plants
3. Add plants manually, from the catalog, or save after a scan
4. Log watering and view personalized care suggestions

Set `SECRET_KEY` in `.env` for secure sessions in production.

## OpenAI diagnosis

Add to `.env`:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Restart the server. Without a key, scan uses demo results tied to the catalog.

## Plant images

Optional API key for bulk species import (see `.env.example`). The searchable catalog stores plants with locally mirrored photos under `static/images/catalog/` so remote CDN links do not expire. Common plants can also be built from curated seeds with Wikimedia images:

```bash
source .venv/bin/activate
python -m app.plant_images --curated
```

Or re-mirror existing remote image URLs:

```bash
python scripts/mirror_catalog_images.py
```

## Project layout

```
main.py                 Routes + auth + collection pages
app/database.py         SQLite schema
app/auth.py             Sign up / sign in
app/collection.py       User plant collection
app/care_schedule.py    Watering & care suggestions
data/plants.json        Public plant catalog
static/uploads/         User plant photos
templates/              HTML pages
```
