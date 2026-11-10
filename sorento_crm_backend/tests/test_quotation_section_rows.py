"""PROPOSAL-FORM-COLLAPSE: a section heading is its own quotation line row (`is_section`).

Owner, 10 Nov 2026: "a heading shouldnt be tied to line". A heading row carries `band_label`
only (no product, set, quantity or price), has its own position in the list, and adds nothing
to any total; moving or deleting a line never moves or drops it.
"""
from __future__ import annotations

from .test_project_quotation_bulk_lines import (  # noqa: F401  (fixture + helpers)
    BASE,
    MARKER,
    _bulk,
    _catalogue_line,
    _quotation,
    _stored,
    api,
)


def _heading(label: str, **extra) -> dict:
    return {"is_section": True, "band_label": f"{MARKER} {label}", **extra}


def test_a_heading_row_saves_on_its_own_with_no_product_and_no_money(api):
    client, _db, _company_id, _user_id, project = api
    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]

    saved = _bulk(
        client,
        version_id,
        [
            _catalogue_line("Basin", "100.00", quantity="2"),
            _heading("PAGE 1"),
            _catalogue_line("Tap", "50.00"),
        ],
    )
    assert saved.status_code == 200, saved.text
    rows = saved.json()["data"]
    assert [row["is_section"] for row in rows] == [False, True, False]
    heading = rows[1]
    assert heading["band_label"] == f"{MARKER} PAGE 1"
    assert heading["product_id"] is None
    assert heading["line_total"] == "0.00"
    assert rows[0]["is_section"] is False and rows[0]["band_label"] is None

    listed = client.get(f"{BASE}/projects/{project.id}/quotations").json()["data"]
    assert listed[0]["current_total"] == "250.00"


def test_a_heading_row_ignores_any_product_or_price_sent_with_it(api):
    client, _db, _company_id, _user_id, project = api
    version_id = _quotation(client, project.id)["current_version_id"]

    saved = _bulk(
        client,
        version_id,
        [_heading("OPTION", product_id=_catalogue_line("x", "1")["product_id"],
                  unit_price="999.00", quantity="3")],
    )
    assert saved.status_code == 200, saved.text
    (heading,) = saved.json()["data"]
    assert heading["product_id"] is None
    assert heading["line_total"] == "0.00"
    assert heading["quantity"] in ("0.00", "0")


def test_a_heading_row_needs_a_label(api):
    client, _db, _company_id, _user_id, project = api
    version_id = _quotation(client, project.id)["current_version_id"]

    refused = _bulk(client, version_id, [{"is_section": True, "band_label": "   "}])
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "quotation_section_label_required"
    assert _stored(client, version_id) == []


def test_deleting_or_moving_the_line_under_a_heading_leaves_the_heading_where_it_is(api):
    client, _db, _company_id, _user_id, project = api
    version_id = _quotation(client, project.id)["current_version_id"]

    first = _bulk(
        client,
        version_id,
        [
            _catalogue_line("Basin", "100.00"),
            _heading("PAGE 1"),
            _catalogue_line("Tap", "50.00"),
            _catalogue_line("Mirror", "70.00"),
        ],
    ).json()["data"]
    basin, heading, tap, mirror = first

    # The tap (the line right under the heading) is deleted; the mirror moves to the top.
    second = _bulk(
        client,
        version_id,
        [{"id": mirror["id"]}, {"id": basin["id"]}, {"id": heading["id"]}],
    )
    assert second.status_code == 200, second.text
    rows = second.json()["data"]
    assert [row["id"] for row in rows] == [mirror["id"], basin["id"], heading["id"]]
    assert rows[2]["is_section"] is True and rows[2]["band_label"] == f"{MARKER} PAGE 1"


def test_a_revision_carries_its_heading_rows(api):
    client, _db, _company_id, _user_id, project = api
    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]
    _bulk(client, version_id, [_heading("PAGE 1"), _catalogue_line("Basin", "100.00")])

    revised = client.post(f"{BASE}/quotations/{quotation['id']}/revise")
    assert revised.status_code in (200, 201), revised.text
    new_version_id = revised.json()["id"]
    rows = _stored(client, new_version_id)
    assert [row["is_section"] for row in rows] == [True, False]
    assert rows[0]["band_label"] == f"{MARKER} PAGE 1"
