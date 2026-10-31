"""PRICETAG-PDF-FIELDS: the PDF print payload carries every resolved tag field.

Owner report (31 Oct, PT-202610-0008): the designer drew each tag's
"price tag description" lines under the product code, the exported PDF drew
none. The designer and the portal read the resolver's rows through
`ResolvedLineData`; the print payload (`tag_sheet_export_service.
_resolved_payload`) copied a hand-picked field list instead, and the
description (added later) was never added to it - nor `currency` or
`own_parts`.

These tests pin the print payload to the SAME schema the screens read, so a
field added to `ResolvedLineData` reaches the PDF without anybody having to
remember a second list.
"""
from __future__ import annotations

import pytest

from tests import _ptag_r9_seed as seed
from tests._pg_fixture import blank_session

_DESCRIPTION = "Angle Valve\nS/Steel\nGunmetal"


@pytest.fixture(autouse=True)
def quiet_notifier(monkeypatch):
    seed.block_respond(monkeypatch)


def _request_with_description(db):
    seed.seed_marketer(db)
    product = seed.seed_product(db)
    product.price_tag_description = _DESCRIPTION
    db.flush()
    contact_id = seed.seed_portal_contact(db)
    request = seed.seed_request(
        db,
        contact_id,
        status="new",
        products=[product],
        print_by="office",
        assigned_to_id=seed.MARKETER_ID,
    )
    page, doc = seed.attach_design(db, request)
    return request, page, doc


def _print_payload(db, request, page, doc) -> dict:
    from app.services.dealer_kit import tag_sheet_export_service

    return tag_sheet_export_service._resolved_payload(
        db,
        {
            "page_id": page.id,
            "version_id": None,
            "version": 1,
            "doc": doc,
            "request": request,
            "page": page,
        },
    )


def test_the_print_payload_carries_every_resolved_line_data_field():
    from app.schemas.price_tag import ResolvedLineData

    with blank_session() as db:
        request, page, doc = _request_with_description(db)
        tag_id = seed.first_tag(request).id

        row = _print_payload(db, request, page, doc)["resolvedData"][tag_id]

        # `data_changes` is the one field the schema itself omits when there
        # is no diff to report (its model_serializer drops it), so it is not
        # a field the PDF could be missing.
        expected = set(ResolvedLineData.model_fields) - {"data_changes"}
        missing = expected - set(row)
        assert not missing, f"print payload drops {sorted(missing)}"


def test_the_print_payload_matches_what_the_designer_reads():
    """Same rows, same schema: the PDF and the screen cannot disagree."""
    from app.schemas.price_tag import ResolvedLineData
    from app.services.dealer_kit import tag_sheet_export_service

    with blank_session() as db:
        request, page, doc = _request_with_description(db)
        tag_id = seed.first_tag(request).id

        rows, _media = tag_sheet_export_service.design_media(db, request, doc)
        screen = {
            r["tag_id"]: ResolvedLineData.model_validate(r).model_dump(mode="json")
            for r in rows
        }
        printed = _print_payload(db, request, page, doc)["resolvedData"]

        assert printed[tag_id] == screen[tag_id]


def test_a_tags_price_tag_description_reaches_the_export():
    with blank_session() as db:
        request, page, doc = _request_with_description(db)
        tag_id = seed.first_tag(request).id

        row = _print_payload(db, request, page, doc)["resolvedData"][tag_id]

        assert row["price_tag_description"] == _DESCRIPTION
        assert row["currency"] == "MYR"
        own_parts = row["own_parts"]
        assert own_parts is None or isinstance(own_parts, list)
