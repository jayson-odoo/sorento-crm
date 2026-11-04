"""QUOTE-COVER-DESIGN round 4 red tests: the 50000 cap is an input limit only (R6), and the
cover preview's header text fields are capped at 2000 like its sibling fields (R7)."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from .test_project_quotation_document_routes import api  # noqa: F401  (api is a fixture)
from .test_quote_cover_design_preview import project_url
from .test_quote_cover_design_round1 import CAP, MARKER, TEMPLATES
from .test_quote_cover_design_templates import design


def test_r6_oversized_stored_template_body_is_still_listed_and_fetched(api):
    client, db, *_ = api
    made = client.post(
        TEMPLATES,
        json={"kind": "cover_page", "name": f"{MARKER} r6", "body_html": "<p>a</p>", "design": design()},
    )
    assert made.status_code == 201, made.text
    tid = made.json()["id"]
    db.execute(
        text("update quotation_templates set body_html = :b where id = :i"),
        {"b": "x" * (CAP + 10), "i": tid},
    )
    db.flush()
    db.expire_all()

    got = client.get(f"{TEMPLATES}/{tid}")
    assert got.status_code == 200, got.text
    assert len(got.json()["body_html"]) == CAP + 10
    listed = client.get(TEMPLATES, params={"kind": "cover_page"})
    assert listed.status_code == 200, listed.text
    assert any(len(r["body_html"]) == CAP + 10 for r in listed.json()["data"])


@pytest.mark.parametrize(
    "field", ["attn_name", "recipient_name_snapshot", "recipient_address_snapshot", "recipient_phone_snapshot"]
)
def test_r7_preview_header_fields_cap_at_2000(api, field):
    client, _db, _c, _u, project, _party = api
    url = project_url(project)
    assert client.post(url, json={field: "x" * 2001}).status_code == 422
    assert client.post(url, json={field: "x" * 2000}).status_code == 200
