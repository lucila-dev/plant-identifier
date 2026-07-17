"""Vercel serverless entry point.

Vercel's @vercel/python runtime detects the module-level ``app`` ASGI
application and serves it. All routing is delegated to the FastAPI app in
``main.py``.
"""
from main import app

__all__ = ["app"]
