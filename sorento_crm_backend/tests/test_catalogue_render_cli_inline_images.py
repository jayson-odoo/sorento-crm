"""B5: the layout reader's picture inlining (no browser needed)."""
from __future__ import annotations

import base64

from app.tasks.catalogue_render_cli import inline_images


def _fetcher(table):
    calls = []

    def fetch(url):
        calls.append(url)
        return table.get(url)

    fetch.calls = calls
    return fetch


def test_images_become_data_urls_once_each():
    fetch = _fetcher({"https://cdn/a.png": ("image/png", b"AAA")})
    out = inline_images(["https://cdn/a.png", "https://cdn/a.png"], fetch)
    assert out == {"https://cdn/a.png": "data:image/png;base64," + base64.b64encode(b"AAA").decode()}
    assert fetch.calls == ["https://cdn/a.png"]


def test_non_image_oversize_empty_and_failed_fetches_are_skipped():
    def fetch(url):
        if url.endswith("boom"):
            raise RuntimeError("down")
        return {
            "https://x/html": ("text/html", b"<p>"),
            "https://x/big": ("image/jpeg", b"x" * 11),
            "https://x/none": None,
            "https://x/empty": ("image/png", b""),
            "https://x/ok": ("image/jpeg; charset=binary", b"ok"),
        }.get(url)

    out = inline_images(
        ["https://x/html", "https://x/big", "https://x/none", "https://x/empty", "https://x/boom", "https://x/ok"],
        fetch,
        per_image_max=10,
    )
    assert list(out) == ["https://x/ok"]
    assert out["https://x/ok"].startswith("data:image/jpeg;base64,")


def test_the_total_cap_stops_adding_pictures():
    fetch = _fetcher({f"https://x/{i}": ("image/png", b"x" * 6) for i in range(3)})
    out = inline_images([f"https://x/{i}" for i in range(3)], fetch, per_image_max=10, total_max=13)
    assert list(out) == ["https://x/0", "https://x/1"]
