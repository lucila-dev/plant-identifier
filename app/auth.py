from __future__ import annotations

import os
import re
from typing import Optional

from fastapi import HTTPException, Request
from passlib.context import CryptContext

from app.database import get_connection

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def validate_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email.")
    return email


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")


def create_user(email: str, name: str, password: str) -> int:
    email = validate_email(email)
    validate_password(password)
    name = name.strip() or email.split("@")[0]
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="An account with that email already exists.")
        cur = conn.execute(
            "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
            (email, name, hash_password(password)),
        )
        return int(cur.lastrowid)


def authenticate_user(email: str, password: str) -> Optional[dict]:
    email = validate_email(email)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, email, name, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        return {"id": row["id"], "email": row["email"], "name": row["name"]}


def get_user_by_id(user_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, email, name FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not row:
            return None
        return {"id": row["id"], "email": row["email"], "name": row["name"]}


def get_session_secret() -> str:
    secret = os.getenv("SECRET_KEY", "").strip()
    if not secret:
        secret = "dev-only-change-me-in-production"
    return secret


def login_user(request: Request, user: dict) -> None:
    request.session["user_id"] = user["id"]


def logout_user(request: Request) -> None:
    request.session.clear()


def get_current_user(request: Request) -> Optional[dict]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(int(user_id))


def require_user(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    return user
