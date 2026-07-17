# BloomScan

Cute plant scan app — identify plants by photo, search the catalog, and track your own collection with care reminders.

## Features

- **Scan** — upload or capture a plant photo for diagnosis
- **Search** — find plants by nickname or scientific name (500+ with photos), with a quick add straight to your collection
- **Sign in** — create an account and save plants to your collection
- **Collection** — photos, notes, care history, watering reminders, and multi-select bulk delete
- **Care suggestions** — watering rhythm, light, humidity, and feed tips by plant type

## Tech stack

- **Backend:** FastAPI, Uvicorn (Python)
- **Frontend:** Jinja2 templates, HTML, CSS, JavaScript
- **Database:** SQLite (local) / PostgreSQL (production)
- **Auth:** passlib password hashing with itsdangerous signed sessions
- **AI:** OpenAI API for photo diagnosis
- **Validation:** Pydantic
- **Deployment:** Vercel
