"""QUOTE-COVER-DESIGN round 3 red tests: merge-field rendering may not amplify uncapped values
past 50000 characters (one rule, in render())."""
from __future__ import annotations

import time
import tracemalloc

import pytest

from .test_project_quotation_document_routes import (  # noqa: F401  (api is a fixture)
    BASE as PS,
    _create_document,
    api,
)
from .test_quote_cover_design_preview import project_url

MARKER = "zzt-qcround3"


def test_render_refuses_a_result_over_50000_before_building_it():
    from app.services.error_handler import AppException
    from app.services.project_quotation_template_service import render

    tracemalloc.start()
    start = time.monotonic()
    with pytest.raises(AppException) as caught:
        render("{{attn_name}}" * 1000, {"attn_name": "x" * 1000})
    elapsed = time.monotonic() - start
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert caught.value.status_code == 422
    assert elapsed < 1
    assert peak < 20 * 1024 * 1024


def test_render_at_the_limit_still_works():
    from app.services.project_quotation_template_service import render

    out = render("{{attn_name}}" * 5, {"attn_name": "x" * 10000})
    assert out == "x" * 50000


def test_preview_with_an_amplifying_token_is_422_and_fast(api):
    client, _db, _c, _u, project, _party = api
    start = time.monotonic()
    res = client.post(
        project_url(project),
        json={"attn_name": "x" * 20000, "cover_letter_html": "{{attn_name}}" * 100},
    )
    assert res.status_code == 422, res.text[:200]
    assert time.monotonic() - start < 2


def test_patch_with_an_amplifying_subject_title_is_422(api):
    client, _db, _c, _u, project, _party = api
    created = _create_document(client, project.id)
    res = client.patch(
        f"{PS}/projects/{project.id}/quotation-documents/{created['id']}",
        json={"subject_title": "x" * 20000, "cover_closing_html": "<p>" + "{{subject_title}}" * 10 + "</p>"},
    )
    assert res.status_code == 422, res.text[:200]


def test_a_normal_render_still_fills_the_value(api):
    client, _db, _c, _u, project, _party = api
    res = client.post(
        project_url(project),
        json={"attn_name": f"{MARKER} Kelly", "cover_letter_html": "<p>Dear {{attn_name}}</p>"},
    )
    assert res.status_code == 200, res.text
    assert f"{MARKER} Kelly" in res.json()["cover_intro_html"]
