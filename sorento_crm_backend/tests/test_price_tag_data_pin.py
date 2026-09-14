"""r9 S5/D16-D18: the product data gate (AC-S5-1 .. AC-S5-5, AC-S5-7).

ADR 0008 resolves a tag's product data LIVE on every render. That is right for
a design being drawn and wrong for one that has been sent for approval: a price
edited in master data on Tuesday silently rewrote the proof the salesperson
approved on Monday, and nobody saw it happen.

So the data is PINNED when marketing starts designing. The live resolve keeps
running beside it, the difference is shown to a person, and NOTHING on a tag
changes without that person choosing. The tests below are about that sentence:

* the pin is written at the transition into ``designing``, and on a line added
  while designing;
* every read path answers the PIN, not the live values - the designer, the
  portal preview and the print payload, because the whole point is that they
  agree;
* the diff names the fields that moved, including the case that has no obvious
  wording ("promotion ended" when the offer disappears);
* ``keep`` records an ack so the SAME change stops asking; ``update`` writes a
  version FIRST and then replaces the pin, so the design as it stood is always
  one Restore away;
* a terminal request runs no live resolve at all - it can decide nothing, so
  the work has no reader.

Red before the coder starts: the three columns, the diff and the pin route do
not exist.
"""
from __future__ import annotations

import glob
import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests import _ptag_r9_seed as seed
from tests._pg_fixture import blank_session

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)

_CRM = "/api/v1/dealer-kit/price-tag-requests/{id}"
_PORTAL = "/api/v1/public/portal/submissions/price_tag_request/{id}"


@pytest.fixture
def db_only():
    with blank_session() as db:
        seed.seed_marketer(db)
        yield db


@pytest.fixture(autouse=True)
def quiet_notifier(monkeypatch):
    """S4's notifier is a different slice; nothing here is about a WhatsApp."""
    try:
        from app.services import price_tag_notify
    except ImportError:
        return
    monkeypatch.setattr(price_tag_notify, "notify_salesperson", lambda *a, **k: None)


@pytest.fixture
def crm():
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db,
    )
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        seed.seed_marketer(db)

        def _override_get_db():
            yield db

        async def _override_scope():
            scope = frozenset({seed.SORENTO})
            set_company_scope(db, scope)
            return scope

        principal = {"id": seed.MARKETER_ID, "email": "zzt-ptag-r9-marketer@test.com"}
        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
        try:
            with TestClient(app) as client:
                yield client, db
        finally:
            app.dependency_overrides.clear()


def _lines(db, request_id):
    from app.models.price_tag import PriceTagRequestLine

    return (
        db.query(PriceTagRequestLine)
        .filter(PriceTagRequestLine.request_id == request_id)
        .order_by(PriceTagRequestLine.sort_order)
        .all()
    )


def _designing_request(db, *, product=None, contact_id=None):
    """A request that has been CLAIMED, so its lines carry pins."""
    from app.services.price_tag_request_service import PriceTagRequestService

    product = product or seed.seed_product(db)
    contact_id = contact_id or seed.seed_portal_contact(db)
    request = seed.seed_request(
        db,
        contact_id,
        status="new",
        products=[product],
        print_by="office",
        assigned_to_id=seed.MARKETER_ID,
    )
    PriceTagRequestService.transition_status(
        db, request.id, "designing", user_id=seed.MARKETER_ID
    )
    db.commit()
    return request, product, contact_id


# ---------------------------------------------------------------------------
# AC-S5-1 - when the pin is written
# ---------------------------------------------------------------------------


class TestThePinIsWrittenWhenDesigningStarts:
    def test_the_transition_to_designing_pins_every_line(self, db_only):
        request, product, _contact = _designing_request(db_only)
        db_only.expire_all()

        line = _lines(db_only, request.id)[0]
        assert line.pinned_at is not None
        assert line.pinned_tag_data is not None
        assert line.pinned_tag_data["code"] == product.product_code
        assert line.data_change_ack_hash is None

    def test_a_line_added_while_designing_is_pinned_on_save(self, db_only):
        from app.services.price_tag_request_service import PriceTagRequestService

        request, first, _contact = _designing_request(db_only)
        second = seed.seed_product(db_only)

        PriceTagRequestService.replace_lines(
            db_only,
            request,
            [
                {"line_type": "product", "product_id": first.id},
                {"line_type": "product", "product_id": second.id},
            ],
        )
        db_only.commit()
        db_only.expire_all()

        rows = _lines(db_only, request.id)
        assert len(rows) == 2
        assert all(row.pinned_tag_data is not None for row in rows), [
            (row.id, row.pinned_at) for row in rows
        ]

    def test_a_changes_requested_return_does_not_repin_over_an_existing_pin(
        self, db_only
    ):
        """D16: the pin follows the DESIGN, not the round. Re-pinning on the way
        back from changes_requested would swallow the very difference the gate
        exists to show."""
        from app.models.price_tag import PriceTagRequest
        from app.services.price_tag_request_service import PriceTagRequestService

        request, product, _contact = _designing_request(db_only)
        original = _lines(db_only, request.id)[0].pinned_tag_data
        db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).update({"status": "changes_requested"})
        db_only.commit()
        product.list_price = 4444.00
        db_only.commit()

        PriceTagRequestService.transition_status(
            db_only, request.id, "designing", user_id=seed.MARKETER_ID
        )
        db_only.commit()
        db_only.expire_all()

        assert _lines(db_only, request.id)[0].pinned_tag_data == original

    def test_the_migration_backfills_non_terminal_requests_only(self, db_only):
        """The migration exposes ``backfill_pins(bind) -> int``.

        Same reasoning as S3's ``map_ready_rows_to_approved``: a data step
        inside ``upgrade()`` cannot be exercised without running the whole
        chain, so the migration calls a named function and so does this test.
        """
        matches = sorted(
            glob.glob(
                str(
                    Path(__file__).resolve().parent.parent
                    / "alembic"
                    / "versions"
                    / "*pins_versions*.py"
                )
            )
        )
        assert matches, "no alembic revision matching '*pins_versions*.py'"
        spec = importlib.util.spec_from_file_location(
            f"migration_{Path(matches[-1]).stem}", matches[-1]
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        contact_id = seed.seed_portal_contact(db_only)
        live = seed.seed_request(
            db_only,
            contact_id,
            status="proof_ready",
            products=[seed.seed_product(db_only)],
        )
        finished = seed.seed_request(
            db_only,
            contact_id,
            status="rejected",
            products=[seed.seed_product(db_only)],
        )

        module.backfill_pins(db_only.get_bind())
        db_only.expire_all()

        assert _lines(db_only, live.id)[0].pinned_tag_data is not None
        assert _lines(db_only, finished.id)[0].pinned_tag_data is None, (
            "a finished request can decide nothing, so a pin on it is dead weight"
        )


# ---------------------------------------------------------------------------
# AC-S5-2 / AC-S5-7 - what the read paths answer
# ---------------------------------------------------------------------------


class TestEveryReadPathAnswersThePin:
    def test_a_price_edit_after_the_pin_changes_none_of_the_three_payloads(
        self, crm
    ):
        from app.services.dealer_kit import tag_data_service, tag_sheet_export_service

        client, db = crm
        product = seed.seed_product(db, list_price=1000.00)
        request, _product, contact_id = _designing_request(db, product=product)
        page, doc = seed.attach_design(db, request)

        product.list_price = 9999.00
        db.commit()

        # 1. the resolver every surface goes through
        resolved = tag_data_service.resolve_request_line_data(db, request)
        assert float(resolved[0]["list_price"]) == 1000.00

        # 2. the CRM design payload
        crm_body = client.get(f"{_CRM.format(id=request.id)}/design").json()
        assert float(crm_body["lines"][0]["list_price"]) == 1000.00

        # 3. the print payload
        printed = tag_sheet_export_service._resolved_payload(
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
        line_id = request.lines[0].id
        assert printed["resolvedData"][line_id]["list_price"] == 1000.00

    def test_a_barcode_edit_is_equally_invisible_until_a_person_decides(self, db_only):
        from app.services.dealer_kit import tag_data_service

        product = seed.seed_product(db_only, barcode="9550000000001")
        request, _product, _contact = _designing_request(db_only, product=product)

        product.barcode = "9550000000999"
        db_only.commit()

        assert (
            tag_data_service.resolve_request_line_data(db_only, request)[0]["barcode"]
            == "9550000000001"
        )

    def test_the_marketing_override_still_wins_over_the_pinned_offer(self, db_only):
        """AC-S5-7: an override is a decision somebody made and logged a reason
        for. Pinning the data underneath it must not overrule it."""
        from decimal import Decimal

        from app.services.dealer_kit import tag_data_service

        request, _product, _contact = _designing_request(db_only)
        line = _lines(db_only, request.id)[0]
        line.marketing_price_override = Decimal("123.45")
        db_only.commit()

        resolved = tag_data_service.resolve_request_line_data(db_only, request)

        assert float(resolved[0]["sell_price"]) == 123.45


# ---------------------------------------------------------------------------
# AC-S5-3 - the diff
# ---------------------------------------------------------------------------


class TestTheDiff:
    def _changes(self, db, request) -> list[dict]:
        from app.services.dealer_kit import tag_data_service

        rows = tag_data_service.resolve_request_line_data(db, request)
        return rows[0].get("data_changes") or []

    def test_a_price_change_is_named_with_its_old_and_new_value(self, db_only):
        product = seed.seed_product(db_only, list_price=1000.00)
        request, _product, _contact = _designing_request(db_only, product=product)

        product.list_price = 1200.00
        db_only.commit()

        fields = {change["field"]: change for change in self._changes(db_only, request)}
        assert "list_price" in fields, fields
        assert fields["list_price"]["label"]
        assert "1000" in str(fields["list_price"]["old"])
        assert "1200" in str(fields["list_price"]["new"])

    def test_a_barcode_change_is_named(self, db_only):
        product = seed.seed_product(db_only, barcode="9550000000001")
        request, _product, _contact = _designing_request(db_only, product=product)

        product.barcode = "9550000000999"
        db_only.commit()

        assert "barcode" in {
            change["field"] for change in self._changes(db_only, request)
        }

    def test_a_name_change_is_named(self, db_only):
        product = seed.seed_product(db_only)
        request, _product, _contact = _designing_request(db_only, product=product)

        product.product_name = "ZZT renamed product"
        db_only.commit()

        assert "name" in {change["field"] for change in self._changes(db_only, request)}

    def test_a_new_photo_shows_as_an_image_change_with_both_thumbnails(self, db_only):
        product = seed.seed_product(db_only)
        request, _product, _contact = _designing_request(db_only, product=product)

        added = seed.seed_product_photo(db_only, product, is_primary=True)
        db_only.commit()

        image_changes = [
            change
            for change in self._changes(db_only, request)
            if change["field"].startswith("image:")
        ]
        assert image_changes, self._changes(db_only, request)
        assert added.id in " ".join(change["field"] for change in image_changes)

    def test_an_offer_that_disappears_says_the_promotion_ended(self, db_only):
        """The one case with no obvious wording: the number did not change, the
        REASON it existed did."""
        from app.models.marketing import Promotion
        from app.models.price_tag import PriceTagRequest

        promotion = Promotion(
            id=str(uuid.uuid4()),
            description="ZZT r9 promotion",
            is_active=True,
            company_id=seed.SORENTO,
        )
        db_only.add(promotion)
        db_only.flush()
        product = seed.seed_product(db_only, list_price=1000.00)
        request, _product, _contact = _designing_request(db_only, product=product)
        db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).update({"promotion_id": promotion.id})
        db_only.commit()

        promotion.is_active = False
        db_only.commit()
        db_only.expire_all()
        request = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()

        offer_changes = [
            change
            for change in self._changes(db_only, request)
            if change["field"] == "offer_price"
        ]
        assert offer_changes, self._changes(db_only, request)
        assert "promotion ended" in (offer_changes[0].get("note") or "").lower()

    def test_a_terminal_request_never_runs_the_live_resolve(self, db_only, monkeypatch):
        """AC-S5-3: nothing can be updated, so asking master data to say so is
        work with no reader. Asserted on the CALL, not on the output - an empty
        list would pass either way."""
        from app.models.price_tag import PriceTagRequest
        from app.services.dealer_kit import tag_data_service

        product = seed.seed_product(db_only)
        request, _product, _contact = _designing_request(db_only, product=product)
        db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).update({"status": "collected"})
        db_only.commit()
        db_only.expire_all()
        request = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()

        calls: list[str] = []
        original = tag_data_service.product_tag_data
        monkeypatch.setattr(
            tag_data_service,
            "product_tag_data",
            lambda *a, **k: (calls.append("live") or original(*a, **k)),
        )

        rows = tag_data_service.resolve_request_line_data(db_only, request)

        assert calls == [], "a terminal request resolved live data it cannot use"
        assert "data_changes" not in rows[0]


# ---------------------------------------------------------------------------
# AC-S5-5 - Update and Keep
# ---------------------------------------------------------------------------


class TestUpdateAndKeep:
    def test_update_writes_a_version_first_then_replaces_the_pin(self, crm):
        client, db = crm
        from app.models.dealer_kit import PageVersion

        product = seed.seed_product(db, list_price=1000.00)
        request, _product, _contact = _designing_request(db, product=product)
        page, _doc = seed.attach_design(db, request)
        product.list_price = 1200.00
        db.commit()
        line_id = request.lines[0].id

        response = client.post(
            f"{_CRM.format(id=request.id)}/lines/{line_id}/pin",
            json={"action": "update"},
        )

        assert response.status_code == 200, response.text
        db.expire_all()
        versions = (
            db.query(PageVersion)
            .filter(PageVersion.page_id == page.id)
            .order_by(PageVersion.version)
            .all()
        )
        assert any(
            (version.commit_message or "").startswith("Before product update:")
            for version in versions
        ), [version.commit_message for version in versions]

        kept = [
            version
            for version in versions
            if (version.commit_message or "").startswith("Before product update:")
        ][0]
        assert kept.pinned_line_data is not None, (
            "the version has to carry the pins it is a snapshot of, or Restore "
            "puts the doc back over the wrong data"
        )

        line = _lines(db, request.id)[0]
        assert float(line.pinned_tag_data["list_price"]) == 1200.00
        assert line.data_change_ack_hash is None

    def test_keep_records_an_ack_and_silences_that_change(self, crm):
        client, db = crm
        from app.services.dealer_kit import tag_data_service

        product = seed.seed_product(db, list_price=1000.00)
        request, _product, _contact = _designing_request(db, product=product)
        seed.attach_design(db, request)
        product.list_price = 1200.00
        db.commit()
        line_id = request.lines[0].id

        response = client.post(
            f"{_CRM.format(id=request.id)}/lines/{line_id}/pin",
            json={"action": "keep"},
        )

        assert response.status_code == 200, response.text
        db.expire_all()
        line = _lines(db, request.id)[0]
        assert line.data_change_ack_hash is not None
        assert float(line.pinned_tag_data["list_price"]) == 1000.00, (
            "Keep keeps the TAG as it is - it does not adopt the new value"
        )

        request = db.query(type(request)).filter_by(id=request.id).first()
        rows = tag_data_service.resolve_request_line_data(db, request)
        assert (rows[0].get("data_changes") or []) == []

    def test_a_second_change_after_a_keep_asks_again(self, crm):
        client, db = crm
        from app.services.dealer_kit import tag_data_service

        product = seed.seed_product(db, list_price=1000.00)
        request, _product, _contact = _designing_request(db, product=product)
        seed.attach_design(db, request)
        product.list_price = 1200.00
        db.commit()
        client.post(
            f"{_CRM.format(id=request.id)}/lines/{line_id_of(db, request)}/pin",
            json={"action": "keep"},
        )

        product.list_price = 1500.00
        db.commit()
        db.expire_all()
        request = db.query(type(request)).filter_by(id=request.id).first()

        rows = tag_data_service.resolve_request_line_data(db, request)
        assert rows[0].get("data_changes"), "the ack silenced a DIFFERENT change"

    def test_a_line_of_another_request_404s(self, crm):
        client, db = crm
        request_a, _pa, _ca = _designing_request(db)
        request_b, _pb, _cb = _designing_request(db)

        response = client.post(
            f"{_CRM.format(id=request_a.id)}/lines/{request_b.lines[0].id}/pin",
            json={"action": "keep"},
        )

        assert response.status_code == 404, response.text


def line_id_of(db, request) -> str:
    return _lines(db, request.id)[0].id
