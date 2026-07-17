from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile

from app.care_schedule import build_care_schedule, watering_status
from app.database import (
    UPLOADS_DIR,
    UPLOADS_ENABLED,
    get_connection,
    insert_returning_id,
)
from app.plants import get_plant

MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/octet-stream"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _row_to_dict(row) -> dict:
    return dict(row) if row else {}


def _catalog_image_url(catalog_plant_id: Optional[str]) -> Optional[str]:
    if not catalog_plant_id:
        return None
    catalog = get_plant(catalog_plant_id)
    if catalog and catalog.image_url:
        return catalog.image_url
    return None


def _with_display_image(item: dict) -> dict:
    """Prefer uploaded photo; fall back to catalog image URL."""
    if not item.get("image_path"):
        catalog_url = _catalog_image_url(item.get("catalog_plant_id"))
        if catalog_url:
            item["image_path"] = catalog_url
    return item


async def save_plant_image(upload: UploadFile) -> Optional[str]:
    content_type = (upload.content_type or "").lower()
    if content_type and content_type not in ALLOWED_TYPES and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file.")
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="Image file is empty.")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image must be under 8 MB.")

    # On serverless the filesystem is ephemeral/read-only: skip persisting the
    # upload and let the caller fall back to the catalog image.
    if not UPLOADS_ENABLED:
        return None

    ext = ".jpg"
    if "png" in content_type:
        ext = ".png"
    elif "webp" in content_type:
        ext = ".webp"
    elif "gif" in content_type:
        ext = ".gif"

    filename = f"{uuid.uuid4().hex}{ext}"
    path = UPLOADS_DIR / filename
    path.write_bytes(data)
    return f"/static/uploads/collection/{filename}"


def list_collection(user_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM collection_plants
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    items = []
    for row in rows:
        item = _with_display_image(_row_to_dict(row))
        item["watering"] = watering_status(
            item.get("last_watered"), item.get("watering_interval_days") or 7
        )
        items.append(item)
    return items


def find_collection_by_catalog(user_id: int, catalog_plant_id: str) -> Optional[dict]:
    """Return an existing collection entry linked to a catalog plant, if any."""
    if not catalog_plant_id:
        return None
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM collection_plants
            WHERE user_id = ? AND catalog_plant_id = ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (user_id, catalog_plant_id),
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_collection_plant(user_id: int, plant_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM collection_plants WHERE id = ? AND user_id = ?",
            (plant_id, user_id),
        ).fetchone()
    if not row:
        return None
    item = _with_display_image(_row_to_dict(row))
    schedule = build_care_schedule(
        catalog_plant_id=item.get("catalog_plant_id"),
        species_name=item.get("species_name") or "",
        scientific_name=item.get("scientific_name") or "",
        light=item.get("light") or "",
        water=item.get("water") or "",
        humidity=item.get("humidity") or "",
    )
    item["schedule"] = schedule
    item["watering"] = watering_status(
        item.get("last_watered"), item.get("watering_interval_days") or schedule.watering_interval_days
    )
    item["records"] = list_records(plant_id)
    return item


def list_records(collection_plant_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM plant_records
            WHERE collection_plant_id = ?
            ORDER BY recorded_at DESC
            LIMIT 50
            """,
            (collection_plant_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def add_collection_plant(
    user_id: int,
    *,
    nickname: str,
    catalog_plant_id: Optional[str] = None,
    species_name: str = "",
    scientific_name: str = "",
    notes: str = "",
    image_path: Optional[str] = None,
    location: str = "",
    acquired_at: Optional[str] = None,
    source: str = "manual",
) -> int:
    nickname = nickname.strip()
    if not nickname:
        raise HTTPException(status_code=400, detail="Give your plant a nickname.")

    catalog = get_plant(catalog_plant_id) if catalog_plant_id else None
    if catalog:
        species_name = species_name or catalog.common_names[0]
        scientific_name = scientific_name or catalog.scientific_name
        if not image_path and catalog.image_url:
            image_path = catalog.image_url

    schedule = build_care_schedule(
        catalog_plant_id=catalog_plant_id,
        species_name=species_name,
        scientific_name=scientific_name,
        light=catalog.care.light if catalog else "",
        water=catalog.care.water if catalog else "",
        humidity=catalog.care.humidity if catalog else "",
    )

    with get_connection() as conn:
        plant_id = insert_returning_id(
            conn,
            """
            INSERT INTO collection_plants (
                user_id, nickname, catalog_plant_id, species_name, scientific_name,
                notes, image_path, location, acquired_at, watering_interval_days,
                fertilize_interval_days, light, water, humidity, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                nickname,
                catalog_plant_id,
                species_name,
                scientific_name,
                notes.strip(),
                image_path,
                location.strip(),
                acquired_at or _now()[:10],
                schedule.watering_interval_days,
                schedule.fertilize_interval_days,
                schedule.light,
                schedule.water,
                schedule.humidity,
                source,
            ),
        )
        conn.execute(
            """
            INSERT INTO plant_records (collection_plant_id, record_type, note)
            VALUES (?, 'added', ?)
            """,
            (plant_id, f"Added {nickname} to your collection."),
        )
    return plant_id


def update_collection_plant(
    user_id: int,
    plant_id: int,
    *,
    nickname: Optional[str] = None,
    notes: Optional[str] = None,
    location: Optional[str] = None,
    image_path: Optional[str] = None,
) -> None:
    existing = get_collection_plant(user_id, plant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Plant not found in your collection.")

    fields = []
    values = []
    if nickname is not None:
        fields.append("nickname = ?")
        values.append(nickname.strip())
    if notes is not None:
        fields.append("notes = ?")
        values.append(notes.strip())
    if location is not None:
        fields.append("location = ?")
        values.append(location.strip())
    if image_path is not None:
        fields.append("image_path = ?")
        values.append(image_path)
    if not fields:
        return
    fields.append("updated_at = ?")
    values.append(_now())
    values.extend([plant_id, user_id])

    with get_connection() as conn:
        conn.execute(
            f"UPDATE collection_plants SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values,
        )


def log_record(
    user_id: int,
    plant_id: int,
    record_type: str,
    note: str = "",
) -> None:
    existing = get_collection_plant(user_id, plant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Plant not found in your collection.")

    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO plant_records (collection_plant_id, record_type, note, recorded_at)
            VALUES (?, ?, ?, ?)
            """,
            (plant_id, record_type, note.strip(), now),
        )
        if record_type == "watered":
            conn.execute(
                """
                UPDATE collection_plants
                SET last_watered = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (now, now, plant_id, user_id),
            )
        else:
            conn.execute(
                "UPDATE collection_plants SET updated_at = ? WHERE id = ? AND user_id = ?",
                (now, plant_id, user_id),
            )


def delete_collection_plant(user_id: int, plant_id: int) -> None:
    image_path = None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT image_path FROM collection_plants WHERE id = ? AND user_id = ?",
            (plant_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Plant not found in your collection.")
        image_path = row["image_path"]
        conn.execute(
            "DELETE FROM collection_plants WHERE id = ? AND user_id = ?",
            (plant_id, user_id),
        )
    if image_path and image_path.startswith("/static/uploads/"):
        file_path = Path(__file__).resolve().parent.parent / image_path.lstrip("/")
        if file_path.exists():
            file_path.unlink(missing_ok=True)


def delete_collection_plants(user_id: int, plant_ids: list[int]) -> int:
    """Delete multiple plants owned by the user. Returns the number removed."""
    ids = []
    for pid in plant_ids:
        try:
            ids.append(int(pid))
        except (TypeError, ValueError):
            continue
    ids = list(dict.fromkeys(ids))
    if not ids:
        return 0

    placeholders = ",".join("?" for _ in ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, image_path FROM collection_plants "
            f"WHERE user_id = ? AND id IN ({placeholders})",
            (user_id, *ids),
        ).fetchall()
        found = [_row_to_dict(r) for r in rows]
        if not found:
            return 0
        found_ids = [r["id"] for r in found]
        del_placeholders = ",".join("?" for _ in found_ids)
        conn.execute(
            f"DELETE FROM collection_plants "
            f"WHERE user_id = ? AND id IN ({del_placeholders})",
            (user_id, *found_ids),
        )

    base_dir = Path(__file__).resolve().parent.parent
    for item in found:
        image_path = item.get("image_path")
        if image_path and image_path.startswith("/static/uploads/"):
            file_path = base_dir / image_path.lstrip("/")
            if file_path.exists():
                file_path.unlink(missing_ok=True)

    return len(found)
