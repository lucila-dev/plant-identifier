from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.auth import (
    authenticate_user,
    create_user,
    get_current_user,
    get_session_secret,
    login_user,
    logout_user,
    require_user,
)
from app.collection import (
    add_collection_plant,
    delete_collection_plant,
    get_collection_plant,
    list_collection,
    log_record,
    save_plant_image,
    update_collection_plant,
)
from app.database import UPLOADS_DIR, init_db
from app.diagnose import diagnose_plant
from app.plants import featured_plants, get_plant, related_plants, search_plants

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="BloomScan", description="Plant search and photo diagnosis")
app.add_middleware(SessionMiddleware, secret_key=get_session_secret(), https_only=False)
app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static", check_dir=False),
    name="static",
)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

MAX_IMAGE_BYTES = 8 * 1024 * 1024

SUGGESTIONS = [
    "Venus flytrap",
    "Monstera",
    "Snake plant",
    "Pothos",
    "Peace lily",
    "Aloe vera",
    "Orchid",
    "Fiddle leaf fig",
]


@app.on_event("startup")
def on_startup():
    init_db()
    try:
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def page_context(request: Request, **extra):
    ctx = {
        "request": request,
        "user": get_current_user(request),
        **extra,
    }
    return ctx


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        page_context(
            request,
            active="home",
            page_class="page-home",
            featured=featured_plants(6),
        ),
    )


@app.get("/scan", response_class=HTMLResponse)
async def scan_page(request: Request):
    return templates.TemplateResponse(
        "scan.html",
        page_context(
            request,
            active="scan",
            page_class="page-inner page-scan",
            openai_ready=bool(os.getenv("OPENAI_API_KEY", "").strip()),
        ),
    )


@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = ""):
    results = search_plants(q) if q else search_plants("", limit=18)
    return templates.TemplateResponse(
        "search.html",
        page_context(
            request,
            active="search",
            page_class="page-inner",
            query=q,
            results=results,
            suggestions=SUGGESTIONS,
        ),
    )


@app.get("/plants/{plant_id}", response_class=HTMLResponse)
async def plant_detail(request: Request, plant_id: str):
    plant = get_plant(plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    return templates.TemplateResponse(
        "plant_detail.html",
        page_context(
            request,
            active="search",
            page_class="page-inner",
            plant=plant,
            related=related_plants(plant_id),
        ),
    )


@app.get("/auth/signin", response_class=HTMLResponse)
async def signin_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/collection", status_code=303)
    return templates.TemplateResponse(
        "auth_signin.html",
        page_context(request, active="auth", page_class="page-inner"),
    )


@app.get("/auth/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/collection", status_code=303)
    return templates.TemplateResponse(
        "auth_signup.html",
        page_context(request, active="auth", page_class="page-inner"),
    )


@app.post("/auth/signin")
async def signin_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    user = authenticate_user(email, password)
    if not user:
        return templates.TemplateResponse(
            "auth_signin.html",
            page_context(
                request,
                active="auth",
                page_class="page-inner",
                error="Wrong email or password — try again?",
                email=email,
            ),
            status_code=400,
        )
    login_user(request, user)
    return RedirectResponse("/collection", status_code=303)


@app.post("/auth/signup")
async def signup_submit(
    request: Request,
    name: str = Form(""),
    email: str = Form(...),
    password: str = Form(...),
):
    user = None
    try:
        create_user(email, name, password)
        user = authenticate_user(email, password)
    except HTTPException as exc:
        return templates.TemplateResponse(
            "auth_signup.html",
            page_context(
                request,
                active="auth",
                page_class="page-inner",
                error=exc.detail,
                name=name,
                email=email,
            ),
            status_code=exc.status_code,
        )
    if user:
        login_user(request, user)
    return RedirectResponse("/collection", status_code=303)


@app.post("/auth/signout")
async def signout(request: Request):
    logout_user(request)
    return RedirectResponse("/", status_code=303)


@app.get("/collection", response_class=HTMLResponse)
async def collection_page(request: Request):
    user = require_user(request)
    plants = list_collection(user["id"])
    return templates.TemplateResponse(
        "collection_list.html",
        page_context(
            request,
            active="collection",
            page_class="page-inner",
            plants=plants,
        ),
    )


@app.get("/collection/add", response_class=HTMLResponse)
async def collection_add_page(
    request: Request,
    catalog: Optional[str] = None,
    nickname: str = "",
    species: str = "",
    scientific: str = "",
):
    require_user(request)
    catalog_plant = get_plant(catalog) if catalog else None
    return templates.TemplateResponse(
        "collection_add.html",
        page_context(
            request,
            active="collection",
            page_class="page-inner",
            catalog_plant=catalog_plant,
            catalog_id=catalog,
            nickname=nickname or (catalog_plant.common_names[0] if catalog_plant else ""),
            species=species or (catalog_plant.common_names[0] if catalog_plant else ""),
            scientific=scientific or (catalog_plant.scientific_name if catalog_plant else ""),
        ),
    )


@app.post("/collection/add")
async def collection_add_submit(
    request: Request,
    nickname: str = Form(...),
    species_name: str = Form(""),
    scientific_name: str = Form(""),
    catalog_plant_id: str = Form(""),
    notes: str = Form(""),
    location: str = Form(""),
    image: Optional[UploadFile] = File(None),
):
    user = require_user(request)
    image_path = None
    if image and image.filename:
        image_path = await save_plant_image(image)
    plant_id = add_collection_plant(
        user["id"],
        nickname=nickname,
        catalog_plant_id=catalog_plant_id or None,
        species_name=species_name,
        scientific_name=scientific_name,
        notes=notes,
        image_path=image_path,
        location=location,
        source="catalog" if catalog_plant_id else "manual",
    )
    return RedirectResponse(f"/collection/{plant_id}", status_code=303)


@app.get("/collection/{plant_id}", response_class=HTMLResponse)
async def collection_detail(request: Request, plant_id: int):
    user = require_user(request)
    plant = get_collection_plant(user["id"], plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found in your collection.")
    return templates.TemplateResponse(
        "collection_detail.html",
        page_context(
            request,
            active="collection",
            page_class="page-inner",
            plant=plant,
        ),
    )


@app.post("/collection/{plant_id}/record")
async def collection_log_record(
    request: Request,
    plant_id: int,
    record_type: str = Form(...),
    note: str = Form(""),
):
    user = require_user(request)
    if record_type not in ("watered", "fertilized", "repotted", "note", "issue"):
        raise HTTPException(status_code=400, detail="Invalid record type.")
    log_record(user["id"], plant_id, record_type, note)
    return RedirectResponse(f"/collection/{plant_id}", status_code=303)


@app.post("/collection/{plant_id}/delete")
async def collection_delete(request: Request, plant_id: int):
    user = require_user(request)
    delete_collection_plant(user["id"], plant_id)
    return RedirectResponse("/collection", status_code=303)


@app.get("/api/plants/search")
async def api_search(q: str = Query(""), limit: int = Query(24, ge=1, le=50)):
    return {"results": [r.model_dump() for r in search_plants(q, limit=limit)]}


@app.post("/api/diagnose")
async def api_diagnose(
    request: Request,
    image: UploadFile = File(...),
    notes: str = Form(""),
):
    content_type = (image.content_type or "").lower()
    if content_type and not (
        content_type.startswith("image/") or content_type == "application/octet-stream"
    ):
        raise HTTPException(status_code=400, detail="Please upload an image file.")

    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="Image file is empty.")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image must be under 8 MB.")

    result = await diagnose_plant(data, notes=notes.strip() or None)
    payload = result.model_dump()
    payload["signed_in"] = bool(get_current_user(request))
    return JSONResponse(payload)


@app.post("/api/collection/from-scan")
async def api_collection_from_scan(
    request: Request,
    nickname: str = Form(...),
    catalog_plant_id: str = Form(""),
    species_name: str = Form(""),
    scientific_name: str = Form(""),
    notes: str = Form(""),
    image: UploadFile = File(...),
):
    user = require_user(request)
    image_path = await save_plant_image(image)
    plant_id = add_collection_plant(
        user["id"],
        nickname=nickname,
        catalog_plant_id=catalog_plant_id or None,
        species_name=species_name,
        scientific_name=scientific_name,
        notes=notes,
        image_path=image_path,
        source="scan",
    )
    return JSONResponse({"id": plant_id, "url": f"/collection/{plant_id}"})


@app.get("/health")
async def health():
    return {
        "ok": True,
        "openai_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "plant_images_configured": bool(os.getenv("PERENUAL_API_KEY", "").strip()),
    }


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 401 and "text/html" in request.headers.get("accept", ""):
        return RedirectResponse(f"/auth/signin?next={request.url.path}", status_code=303)
    if exc.status_code == 404 and "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(
            "404.html",
            page_context(request, active="", page_class="page-inner"),
            status_code=404,
        )
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse({"detail": exc.errors()}, status_code=422)
