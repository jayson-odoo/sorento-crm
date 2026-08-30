"""A list route called without its trailing slash is served, not redirected.

The router declares list routes as ``@router.get("/")`` and most frontend
services call them without the slash. Starlette's answer is a 307, which a
browser on another laptop follows into a loop with the Next dev proxy (and
some browsers drop it outright). Fixing the path inside the backend serves
the request in one round trip for every client.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_list_route_without_slash_is_served_directly():
    client = TestClient(app, base_url="http://localhost:8000")
    response = client.get("/api/v1/inventory/warehouses?page=1", follow_redirects=False)
    # Unauthenticated: the route itself answers (401), no 307 in between.
    assert response.status_code == 401


def test_param_route_is_untouched():
    client = TestClient(app, base_url="http://localhost:8000")
    response = client.get("/api/v1/inventory/warehouses/not-a-uuid", follow_redirects=False)
    assert response.status_code != 307


def test_unknown_path_still_404s():
    client = TestClient(app, base_url="http://localhost:8000")
    response = client.get("/api/v1/no-such-thing", follow_redirects=False)
    assert response.status_code == 404
