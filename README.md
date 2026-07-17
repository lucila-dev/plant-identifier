# BloomScan

Cute plant scan app — identify plants by photo, search the catalog, and track your own collection with care reminders.


## Features

- **Scan** — upload or capture a plant photo for diagnosis
- **Search** — find plants by nickname or scientific name (500+ with photos)
- **Sign in** — create an account and save plants to your collection
- **Collection** — photos, notes, care history, watering reminders
- **Care suggestions** — watering rhythm, light, humidity, and feed tips by plant type


## Accounts & collection

1. Click **Sign in** → **Create an account**
2. Open **Collection** to see your plants
3. Add plants manually, from the catalog, or save after a scan
4. Log watering and view personalized care suggestions


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
