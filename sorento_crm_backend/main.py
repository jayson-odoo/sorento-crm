"""FastAPI application entry point - redirect to app.main."""
# This file redirects to the actual app in app/main.py
# Run with: uvicorn app.main:app --reload
from app.main import app

__all__ = ["app"]
