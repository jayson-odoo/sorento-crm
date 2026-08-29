"""The trailing-slash 307 must carry a path-only Location.

Starlette builds that redirect from the Host the backend saw. Behind the Next
dev rewrite (and any proxy that rewrites Host) that is the backend's own
address, e.g. ``http://localhost:8000``, which is the wrong machine for a
browser on another laptop: it follows the redirect to its own localhost and
reports "Failed to fetch". A path-only Location resolves against whatever
origin the browser used, so the redirect works from any host.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_trailing_slash_redirect_location_is_path_only():
    client = TestClient(app, base_url="http://localhost:8000")
    response = client.get("/api/v1/inventory/warehouses", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/api/v1/inventory/warehouses/"


def test_redirect_to_another_host_is_left_alone():
    """Only the backend's own absolute URL is relativised; a real external
    redirect keeps its host."""
    from starlette.responses import RedirectResponse

    from app.middleware.relative_redirect_middleware import RelativeRedirectMiddleware
    from starlette.applications import Starlette
    from starlette.routing import Route

    async def away(request):
        return RedirectResponse("https://example.com/elsewhere", status_code=307)

    inner = Starlette(routes=[Route("/go", away)])
    client = TestClient(RelativeRedirectMiddleware(inner), base_url="http://localhost:8000")
    response = client.get("/go", follow_redirects=False)
    assert response.headers["location"] == "https://example.com/elsewhere"
