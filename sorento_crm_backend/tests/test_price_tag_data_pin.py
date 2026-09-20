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
from datetime import date
from decimal import Decimal
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
def signable_images(monkeypatch):
    """A product photo signs through ``product_images``, and the real signer
    cannot find a CloudFront key in a test process - so an image DIFF would be
    empty for a reason that has nothing to do with the diff."""
    monkeypatch.setattr(
        "app.services.dealer_kit.product_images.resolve_signed_url",
        lambda path, **_kwargs: (
            f"https://signed.example.test/{path.rsplit('/', 1)[-1]}"
        ),
    )


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


def _tags(db, request_id):
    """The request's TAGS in print order.

    The pin, its timestamp and the ack hash moved onto the tag when a line
    became able to print several of them (combos D3): two tags split off one
    line resolve different products, so they are drawn from different data and
    a Keep on one must not silence the other. One tag per line unless a Split
    made more, so this is the same row count these assertions always had.
    """
    from app.models.price_tag import PriceTagRequestLine, PriceTagRequestTag

    return (
        db.query(PriceTagRequestTag)
        .join(PriceTagRequestLine, PriceTagRequestLine.id == PriceTagRequestTag.line_id)
        .filter(PriceTagRequestLine.request_id == request_id)
        .order_by(PriceTagRequestLine.sort_order, PriceTagRequestTag.sort_order)
        .all()
    )


def _load_pins_migration():
    """The pins/versions revision, imported by FILENAME PATTERN.

    Revision filenames start with a digit or a label, so they cannot be
    imported by module path (the `_run_migration` idiom); matched by pattern so
    the coder is free to rename the numeric prefix at merge time.
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
    return module


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

        line = _tags(db_only, request.id)[0]
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

        rows = _tags(db_only, request.id)
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
        original = _tags(db_only, request.id)[0].pinned_tag_data
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

        assert _tags(db_only, request.id)[0].pinned_tag_data == original

    def test_the_migration_backfills_non_terminal_requests_only(self, db_only):
        """The migration exposes ``backfill_pins(bind) -> int``.

        Same reasoning as S3's ``map_ready_rows_to_approved``: a data step
        inside ``upgrade()`` cannot be exercised without running the whole
        chain, so the migration calls a named function and so does this test.
        """
        module = _load_pins_migration()

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

        assert _tags(db_only, live.id)[0].pinned_tag_data is not None
        assert _tags(db_only, finished.id)[0].pinned_tag_data is None, (
            "a finished request can decide nothing, so a pin on it is dead weight"
        )

    @pytest.mark.parametrize(
        "status,pinned",
        [
            ("new", False),
            ("designing", True),
            ("changes_requested", True),
            ("proof_ready", True),
            ("approved", True),
            ("ready_for_collection", False),
            ("collected", False),
            ("rejected", False),
            ("void", False),
        ],
    )
    def test_the_backfill_starts_at_designing_not_at_new(
        self, db_only, status, pinned
    ):
        """D16/A1: the pin starts at `designing`.

        A `new` request has not been claimed, nobody is drawing anything, and
        pinning it freezes master data against a design that does not exist -
        so the first thing marketing sees after claiming is a gate asking about
        a change nobody made. `NOT IN (terminal)` is the wrong side of the
        line: it pins `new` too.
        """
        module = _load_pins_migration()
        contact_id = seed.seed_portal_contact(db_only)
        request = seed.seed_request(
            db_only,
            contact_id,
            status=status,
            products=[seed.seed_product(db_only)],
            print_by="office",
        )

        module.backfill_pins(db_only.get_bind())
        db_only.expire_all()

        row = _tags(db_only, request.id)[0]
        assert (row.pinned_tag_data is not None) is pinned, (
            f"{status!r} should {'' if pinned else 'NOT '}be pinned by the backfill"
        )

    def test_a_backfilled_product_pin_carries_the_FULL_resolved_data(self, db_only):
        """A "light" pin is a pin that lies.

        Every read path answers the pin once one exists, so a pin holding only
        the code, the name and the list price silently blanks the dimensions,
        the spec lines, the spec values and the photo on every tag of every
        request that was mid-design at upgrade - and the diff then reports each
        of those as a CHANGE, which is the opposite of "nothing changes
        visually on day one". The pin has to equal what the resolver answers.
        """
        from app.services.dealer_kit import tag_data_service

        module = _load_pins_migration()
        contact_id = seed.seed_portal_contact(db_only)
        product = seed.seed_product(db_only, list_price=1000.00, barcode="9550000000001")
        seed.seed_product_photo(db_only, product)
        promotion = seed.seed_promotion_on(db_only, product, offer="799.00")
        request = seed.seed_request(
            db_only,
            contact_id,
            status="proof_ready",
            products=[product],
            print_by="office",
        )
        from app.models.price_tag import PriceTagRequest, PriceTagRequestLine

        # D1: the promotion moved to the LINE - the header column is gone
        # (ptag_0011), so this seeds it directly on every line of the request.
        db_only.query(PriceTagRequestLine).filter(
            PriceTagRequestLine.request_id == request.id
        ).update({"promotion_id": promotion.id})
        db_only.commit()
        db_only.expire_all()
        request = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()

        # What the resolver says BEFORE any pin exists is what the pin has to be.
        live = tag_data_service.resolve_request_line_data(db_only, request)[0]

        module.backfill_pins(db_only.get_bind())
        db_only.expire_all()

        pin = _tags(db_only, request.id)[0].pinned_tag_data
        assert pin["code"] == live["code"]
        assert pin["name"] == live["name"]
        assert pin["dimensions"] == live["dimensions"]
        assert pin["spec_lines"] == live["spec_lines"]
        assert [spec["key"] for spec in pin["specs"]] == [
            spec["key"] for spec in live["specs"]
        ]
        assert [image["attachment_id"] for image in pin["images"]] == [
            image["attachment_id"] for image in live["images"]
        ]
        assert float(pin["list_price"]) == float(live["list_price"])
        assert pin["sell_price"] is not None, (
            "the promotion priced this line at 799 before the upgrade; a pin "
            "that drops the offer makes the tag print the list price instead"
        )
        assert float(pin["sell_price"]) == float(live["sell_price"])
        assert pin["barcode"] == live["barcode"]

    def test_a_backfilled_set_pin_carries_the_set_own_data(self, db_only):
        """A set line has no `products` row to read, so a backfill written as a
        LEFT JOIN on products pins an empty code, an empty name and no price at
        all - and the tag goes blank on day one."""
        from app.services.dealer_kit import tag_data_service

        module = _load_pins_migration()
        contact_id = seed.seed_portal_contact(db_only)
        member = seed.seed_product(db_only, list_price=1000.00)
        product_set = seed.seed_product_set(db_only, members=[member])
        request = seed.seed_request(
            db_only, contact_id, status="proof_ready", print_by="office"
        )
        from app.services.price_tag_request_service import PriceTagRequestService

        PriceTagRequestService.replace_lines(
            db_only,
            request,
            [{"line_type": "product_set", "product_set_id": product_set.id}],
        )
        db_only.commit()
        db_only.expire_all()
        from app.models.price_tag import PriceTagRequest

        request = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()
        live = tag_data_service.resolve_request_line_data(db_only, request)[0]

        module.backfill_pins(db_only.get_bind())
        db_only.expire_all()

        pin = _tags(db_only, request.id)[0].pinned_tag_data
        assert pin["code"] == live["code"] == product_set.set_code
        assert pin["name"] == live["name"]
        assert pin["list_price"] is not None
        assert float(pin["list_price"]) == float(live["list_price"])
        assert pin["set_members"] == live["set_members"]


# ---------------------------------------------------------------------------
# Live finding - a request claimed through a backend that predates pins left
# its lines unpinned, and an unpinned line reads LIVE - exactly what the gate
# forbids. Ruling: an unpinned line on an IN-FLIGHT request is pinned on the
# first resolve that reaches it.
# ---------------------------------------------------------------------------


class TestAnUnpinnedInFlightLinePinsItselfOnFirstRead:
    def test_the_first_design_read_pins_it_and_a_later_edit_no_longer_moves_it(
        self, crm
    ):
        client, db = crm
        product = seed.seed_product(db, list_price=1000.00)
        request, _product, _contact = _designing_request(db, product=product)
        seed.attach_design(db, request)
        line = _tags(db, request.id)[0]
        # Simulate a row from before pins existed: claimed, designing, never
        # pinned - the raw update a pre-pin backend would have left behind.
        line.pinned_tag_data = None
        line.pinned_at = None
        db.commit()

        first = client.get(f"{_CRM.format(id=request.id)}/design")
        assert first.status_code == 200, first.text
        first_row = next(
            row for row in first.json()["lines"] if row["tag_id"] == line.id
        )
        assert first_row["list_price"] == 1000.00

        db.expire_all()
        fresh_line = _tags(db, request.id)[0]
        assert fresh_line.pinned_tag_data is not None, (
            "the first read must pin the line, or it stays exposed to master "
            "data forever - reading it again and again is not a decision"
        )
        assert fresh_line.pinned_at is not None
        assert float(fresh_line.pinned_tag_data["list_price"]) == 1000.00, (
            "the pin must equal what THIS read resolved, not some other value"
        )

        # A second, later edit must no longer move the payload - it is pinned.
        product.list_price = 1500.00
        db.commit()

        second = client.get(f"{_CRM.format(id=request.id)}/design")
        assert second.status_code == 200, second.text
        second_row = next(
            row for row in second.json()["lines"] if row["tag_id"] == line.id
        )
        assert second_row["list_price"] == 1000.00, (
            "the line is pinned now - a later master data edit must not move it"
        )
        assert any(
            change["field"] == "list_price"
            for change in second_row.get("data_changes") or []
        ), second_row

        # resolve-prices answers the same pinned figure, not a re-derived live
        # one - it is the SAME resolver, not a second one that forgot the pin.
        resolved = client.post(f"{_CRM.format(id=request.id)}/resolve-prices").json()
        resolved_row = next(row for row in resolved if row["tag_id"] == line.id)
        assert resolved_row["list_price"] == 1000.00

    def test_a_terminal_requests_unpinned_line_is_not_pinned_by_a_read(
        self, db_only
    ):
        """The ruling only revives an IN-FLIGHT request's forgotten pin. A
        terminal request can decide nothing, so writing a pin now would be a
        pin nobody asked for and nobody can act on - the same reasoning
        `TestATerminalRequestNeverRunsTheLiveResolve` holds the resolver to.
        """
        from app.models.price_tag import PriceTagRequest, PriceTagRequestTag
        from app.services.dealer_kit import tag_data_service

        product = seed.seed_product(db_only, list_price=1000.00)
        request, _product, _contact = _designing_request(db_only, product=product)
        line = _tags(db_only, request.id)[0]
        line.pinned_tag_data = None
        line.pinned_at = None
        db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).update({"status": "collected"})
        db_only.commit()
        db_only.expire_all()
        request = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()

        tag_data_service.resolve_request_line_data(db_only, request)
        db_only.commit()
        db_only.expire_all()

        fresh_line = (
            db_only.query(PriceTagRequestTag)
            .filter(PriceTagRequestTag.id == line.id)
            .first()
        )
        assert fresh_line.pinned_tag_data is None
        assert fresh_line.pinned_at is None


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
        tag_id = _tags(db, request.id)[0].id
        assert printed["resolvedData"][tag_id]["list_price"] == 1000.00

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
        line = _tags(db_only, request.id)[0]
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
        REASON it existed did.

        The promotion has to RESOLVE an offer at pin time or there is nothing to
        lose, so the chain is the real one: promotion -> group -> a
        ``promotion_products`` row priced under list. ``is_active`` is then
        flipped, which is exactly how somebody pulls a live offer in a hurry.
        """
        from app.models.marketing import Promotion, PromotionGroup, PromotionProduct
        from app.models.price_tag import PriceTagRequest, PriceTagRequestLine
        from app.services.dealer_kit import tag_data_service

        product = seed.seed_product(db_only, list_price=1000.00)
        promotion = Promotion(
            id=str(uuid.uuid4()),
            description="ZZT r9 promotion",
            is_active=True,
            company_id=seed.SORENTO,
        )
        db_only.add(promotion)
        db_only.flush()
        group = PromotionGroup(
            id=uuid.uuid4(),
            promotion_id=promotion.id,
            group_name="ZZT r9 group",
            sort_order=0,
            company_id=seed.SORENTO,
        )
        db_only.add(group)
        db_only.flush()
        db_only.add(
            PromotionProduct(
                id=str(uuid.uuid4()),
                promotion_id=promotion.id,
                promotion_group_id=group.id,
                product_id=product.id,
                promo_selling_price=Decimal("799.00"),
                company_id=seed.SORENTO,
            )
        )
        db_only.flush()

        contact_id = seed.seed_portal_contact(db_only)
        from app.services.price_tag_request_service import PriceTagRequestService

        request = seed.seed_request(
            db_only,
            contact_id,
            status="new",
            products=[product],
            print_by="office",
            assigned_to_id=seed.MARKETER_ID,
        )
        # D1: the promotion moved to the LINE - the header column is gone
        # (ptag_0011), so this seeds it directly on every line of the request.
        db_only.query(PriceTagRequestLine).filter(
            PriceTagRequestLine.request_id == request.id
        ).update({"promotion_id": promotion.id})
        db_only.commit()
        db_only.expire_all()
        request = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()
        PriceTagRequestService.transition_status(
            db_only, request.id, "designing", user_id=seed.MARKETER_ID
        )
        db_only.commit()

        # The pin has to have caught the offer, or "it disappeared" is vacuous.
        pinned = _tags(db_only, request.id)[0].pinned_tag_data
        assert float(pinned["sell_price"]) == 799.00, pinned

        promotion.is_active = False
        db_only.commit()
        db_only.expire_all()
        request = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()
        assert (
            tag_data_service.product_tag_data(
                db_only,
                db_only.query(type(product)).filter_by(id=product.id).first(),
                tag_data_service.staff_viewer(),
                promotion.id,
            )["offer_price"]
            is None
        ), "the promotion is still live, so nothing has disappeared"

        offer_changes = [
            change
            for change in self._changes(db_only, request)
            if change["field"] == "offer_price"
        ]
        assert offer_changes, self._changes(db_only, request)
        assert "promotion ended" in (offer_changes[0].get("note") or "").lower()

    def test_a_marketing_override_is_not_a_product_data_change(self, db_only):
        """S4: the override is marketing's OWN decision, made after the pin.

        The live resolve applies `marketing_price_override` and the pin (taken
        at `designing`, before anybody typed one) does not, so the diff reads
        the office's own edit back to it as "master data moved" and the card
        counts a line as changed that nothing changed under. Marketing then
        presses Update to adopt its own number, which writes a version for
        nothing.
        """
        from decimal import Decimal

        product = seed.seed_product(db_only, list_price=1000.00)
        request, _product, _contact = _designing_request(db_only, product=product)
        assert self._changes(db_only, request) == []

        line = _tags(db_only, request.id)[0]
        line.marketing_price_override = Decimal("123.45")
        db_only.commit()
        db_only.expire_all()
        from app.models.price_tag import PriceTagRequest

        request = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()

        assert self._changes(db_only, request) == [], (
            "an override is not a change to the product"
        )

    def test_an_override_does_not_raise_the_changed_line_count(self, crm):
        """The same defect where a reader meets it: the record card pill."""
        from decimal import Decimal

        client, db = crm
        product = seed.seed_product(db, list_price=1000.00)
        request, _product, _contact = _designing_request(db, product=product)
        seed.attach_design(db, request)
        line = _tags(db, request.id)[0]
        line.marketing_price_override = Decimal("123.45")
        db.commit()

        body = client.get(f"{_CRM.format(id=request.id)}/data-changes").json()

        assert body == [], body

    def test_no_offer_row_when_only_the_promotion_switched_off(self, db_only):
        """S5: a line that never had an offer cannot lose one.

        `promotion_ended` is ORed into the offer comparison, so a request
        carrying a promotion that covers NONE of its lines emits an
        `offer_price` row reading "old: null, new: null, note: Promotion
        ended" on every single line the moment the promotion is switched off.
        The dialog then shows a row with nothing in either column.

        Something ELSE has to move as well, or the whole diff short-circuits on
        the pin/live hash comparison and the bogus row never gets a chance to be
        emitted - which is exactly the real case: a product renamed while a
        promotion is switched off.
        """
        from app.models.price_tag import PriceTagRequest, PriceTagRequestLine

        uncovered = seed.seed_product(db_only, list_price=1000.00)
        # The promotion prices a DIFFERENT product, so this line's offer is
        # null before and after.
        promotion = seed.seed_promotion_on(db_only, seed.seed_product(db_only))
        request, _product, _contact = _designing_request(db_only, product=uncovered)
        # D1: the promotion moved to the LINE - the header column is gone
        # (ptag_0011), so this seeds it directly on every line of the request.
        db_only.query(PriceTagRequestLine).filter(
            PriceTagRequestLine.request_id == request.id
        ).update({"promotion_id": promotion.id})
        db_only.commit()

        promotion.is_active = False
        uncovered.product_name = "ZZT renamed while the promotion ended"
        db_only.commit()
        db_only.expire_all()
        request = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()

        assert "name" in {
            change["field"] for change in self._changes(db_only, request)
        }, "the rename itself has to register, or this proves nothing"
        offer_rows = [
            change
            for change in self._changes(db_only, request)
            if change["field"] == "offer_price"
        ]
        assert offer_rows == [], (
            "the offer was null before and is null now: nothing moved"
        )

    def test_exactly_one_offer_row_when_the_offer_disappears(self, db_only):
        """One row, not two: the value moving and the promotion ending are the
        same event, and the note is what tells them apart."""
        from app.models.price_tag import PriceTagRequest, PriceTagRequestLine

        product = seed.seed_product(db_only, list_price=1000.00)
        promotion = seed.seed_promotion_on(db_only, product, offer="799.00")
        request, _product, _contact = _designing_request(db_only, product=product)
        # D1: the promotion moved to the LINE - the header column is gone
        # (ptag_0011), so this seeds it directly on every line of the request.
        db_only.query(PriceTagRequestLine).filter(
            PriceTagRequestLine.request_id == request.id
        ).update({"promotion_id": promotion.id})
        db_only.commit()
        db_only.expire_all()
        request = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()
        # Re-pin now the promotion is on the request, so the pin holds the offer.
        from app.services.dealer_kit import tag_data_service

        tag_data_service.pin_tags(db_only, request, only_unpinned=False)
        db_only.commit()
        assert float(_tags(db_only, request.id)[0].pinned_tag_data["sell_price"]) == 799.0

        promotion.is_active = False
        db_only.commit()
        db_only.expire_all()
        request = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()

        offer_rows = [
            change
            for change in self._changes(db_only, request)
            if change["field"] == "offer_price"
        ]
        assert len(offer_rows) == 1, offer_rows
        assert (offer_rows[0].get("note") or "").lower() == "promotion ended"
        assert offer_rows[0]["new"] is None

    def test_a_promotion_past_its_end_date_has_ended(self, db_only):
        """S5: `_promotion_is_live` reads `is_active` and nothing else.

        A promotion that ran to the 30th and is still flagged active is OVER on
        the 1st - the pricing engine already knows that (it filters on the
        window), so the offer disappears while the diff says the value simply
        changed. The one wording that explains it to a reader is exactly the
        one that goes missing.
        """
        from datetime import timedelta

        from app.models.price_tag import PriceTagRequest, PriceTagRequestLine
        from app.services.dealer_kit import tag_data_service

        product = seed.seed_product(db_only, list_price=1000.00)
        promotion = seed.seed_promotion_on(db_only, product, offer="799.00")
        request, _product, _contact = _designing_request(db_only, product=product)
        # D1: the promotion moved to the LINE - the header column is gone
        # (ptag_0011), so this seeds it directly on every line of the request.
        db_only.query(PriceTagRequestLine).filter(
            PriceTagRequestLine.request_id == request.id
        ).update({"promotion_id": promotion.id})
        db_only.commit()
        db_only.expire_all()
        request = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()
        tag_data_service.pin_tags(db_only, request, only_unpinned=False)
        db_only.commit()

        # Still `is_active`, but its window closed yesterday.
        promotion.end_date = date.today() - timedelta(days=1)
        db_only.commit()
        db_only.expire_all()
        request = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()

        assert (
            tag_data_service._promotion_is_live(db_only, promotion.id) is False
        ), "a promotion past its end date is not running"
        offer_rows = [
            change
            for change in self._changes(db_only, request)
            if change["field"] == "offer_price"
        ]
        assert len(offer_rows) == 1, offer_rows
        assert (offer_rows[0].get("note") or "").lower() == "promotion ended"

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
        tag_id = _tags(db, request.id)[0].id

        response = client.post(
            f"{_CRM.format(id=request.id)}/tags/{tag_id}/pin",
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

        line = _tags(db, request.id)[0]
        assert float(line.pinned_tag_data["list_price"]) == 1200.00
        assert line.data_change_ack_hash is None

    def test_update_writes_an_AFTER_version_too_carrying_the_new_pin(self, crm):
        """PT-202609-0015: Update snapshotted only the OLD pin (BEFORE), so
        the new value (1200 here) never landed in any version - a Restore to
        an earlier version could never bring it back because nothing ever
        held it. The version count must grow by TWO: the before, and now the
        after.
        """
        client, db = crm
        from app.models.dealer_kit import PageVersion

        product = seed.seed_product(db, list_price=1000.00)
        request, _product, _contact = _designing_request(db, product=product)
        page, _doc = seed.attach_design(db, request)
        product.list_price = 1200.00
        db.commit()
        tag_id = _tags(db, request.id)[0].id

        before_count = (
            db.query(PageVersion).filter(PageVersion.page_id == page.id).count()
        )

        response = client.post(
            f"{_CRM.format(id=request.id)}/tags/{tag_id}/pin",
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
        assert len(versions) == before_count + 2, [
            v.commit_message for v in versions
        ]

        before = [
            v for v in versions
            if (v.commit_message or "").startswith("Before product update:")
        ]
        after = [
            v for v in versions
            if (v.commit_message or "").startswith("Product update:")
        ]
        assert len(before) == 1, [v.commit_message for v in versions]
        assert len(after) == 1, [v.commit_message for v in versions]
        assert float(before[0].pinned_line_data[tag_id]["list_price"]) == 1000.00
        assert float(after[0].pinned_line_data[tag_id]["list_price"]) == 1200.00, (
            "the AFTER version must carry the NEW pin - equal to the live "
            "value this update just wrote"
        )

    def test_update_all_writes_one_before_and_one_after_for_the_whole_batch(
        self, crm
    ):
        """"Update all" is N sequential single-tag update calls (the FE's
        `updateAllTagPins`). The batch must still read as ONE before-state and
        ONE after-state, not a before/after pair per tag - the second tag's
        own "before" would otherwise duplicate the first tag's "after" (both
        snapshot the whole request's pins, not just the tag being touched).
        """
        client, db = crm
        from app.models.dealer_kit import PageVersion
        from app.services.price_tag_request_service import PriceTagRequestService

        product_a = seed.seed_product(db, list_price=1000.00)
        product_b = seed.seed_product(db, list_price=2000.00)
        request, _product, _contact = _designing_request(db, product=product_a)
        PriceTagRequestService.replace_lines(
            db,
            request,
            [
                {"line_type": "product", "product_id": product_a.id},
                {"line_type": "product", "product_id": product_b.id},
            ],
        )
        db.commit()
        page, _doc = seed.attach_design(db, request)
        product_a.list_price = 1100.00
        product_b.list_price = 2200.00
        db.commit()

        tag_ids = [tag.id for tag in _tags(db, request.id)]
        assert len(tag_ids) == 2, "the fixture needs two tags to be a batch"

        for tag_id in tag_ids:
            response = client.post(
                f"{_CRM.format(id=request.id)}/tags/{tag_id}/pin",
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
        before = [
            v for v in versions
            if (v.commit_message or "").startswith("Before product update:")
        ]
        after = [
            v for v in versions
            if (v.commit_message or "").startswith("Product update:")
        ]
        assert len(before) == 1, [v.commit_message for v in versions]
        assert len(after) == 1, [v.commit_message for v in versions]

    def test_keep_records_an_ack_and_silences_that_change(self, crm):
        client, db = crm
        from app.services.dealer_kit import tag_data_service

        product = seed.seed_product(db, list_price=1000.00)
        request, _product, _contact = _designing_request(db, product=product)
        seed.attach_design(db, request)
        product.list_price = 1200.00
        db.commit()
        tag_id = _tags(db, request.id)[0].id

        response = client.post(
            f"{_CRM.format(id=request.id)}/tags/{tag_id}/pin",
            json={"action": "keep"},
        )

        assert response.status_code == 200, response.text
        db.expire_all()
        line = _tags(db, request.id)[0]
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
            f"{_CRM.format(id=request.id)}/tags/{tag_id_of(db, request)}/pin",
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
            f"{_CRM.format(id=request_a.id)}/tags/{tag_id_of(db, request_b)}/pin",
            json={"action": "keep"},
        )

        assert response.status_code == 404, response.text


def tag_id_of(db, request) -> str:
    return _tags(db, request.id)[0].id


# ---------------------------------------------------------------------------
# r9 review-round leftover R3/R4 - Update tag on a request with no page yet
# still has to leave behind a document the designer can OPEN
# ---------------------------------------------------------------------------


class TestUpdateOnARequestWithNoPageBuildsAnOpenableDocument:
    """``_EMPTY_SHEET_DOC`` (the fallback the pin route's ``update`` action
    writes when a page has no draft and no saved version yet - which is always
    true the FIRST time Update tag runs on a request nobody has claimed
    through the CRM, only auto-assigned) used to be
    ``{"kind": "tag_sheet", "sheets": []}`` - no ``imposition`` key at all.

    ``GET .../design`` answers that same document once the pin route has
    written it, and every reader of a tag_sheet doc (``ScaledSheet``,
    ``TagSheetRenderer``) reads ``doc.imposition.page_width_mm`` /
    ``page_height_mm`` unconditionally - so a request whose FIRST design
    action was Update tag (not a CRM Claim, which never wrote an imposition
    either, but was never the only version on the page) left a document
    nothing could draw.
    """

    def test_the_page_update_tag_creates_carries_an_imposition(self, crm):
        client, db = crm

        product = seed.seed_product(db)
        request, _product, _contact = _designing_request(db, product=product)
        assert request.page_id is None, (
            "the fixture must not have claimed a page yet, or Update tag is "
            "not the thing creating one"
        )
        tag_id = _tags(db, request.id)[0].id

        response = client.post(
            f"{_CRM.format(id=request.id)}/tags/{tag_id}/pin",
            json={"action": "update"},
        )
        assert response.status_code == 200, response.text

        design = client.get(f"{_CRM.format(id=request.id)}/design")
        assert design.status_code == 200, design.text
        doc = design.json()["doc"]
        assert doc is not None
        imposition = doc.get("imposition")
        assert imposition, (
            "Update tag on a page-less request wrote a doc with no imposition "
            f"at all: {doc!r}"
        )
        assert imposition["page_width_mm"] == 210
        assert imposition["page_height_mm"] == 297


# ---------------------------------------------------------------------------
# Owner test round, finding 3 - "Check product data" re-runs the gate
# ---------------------------------------------------------------------------


class TestRecheckProductData:
    """After Keep current there was no way to re-run the comparison, so a red
    dot silenced by Keep stayed silent forever - even for a later, unrelated
    edit that would have tripped the gate on its own.

    ``POST /{request_id}/data-changes/recheck`` clears ``data_change_ack_hash``
    on every line of the request and answers the fresh ``data_changes`` per
    line, the same shape ``GET /data-changes`` answers.
    """

    def test_recheck_clears_the_ack_and_the_diff_reappears(self, crm):
        client, db = crm
        product = seed.seed_product(db, list_price=1000.00)
        request, _product, _contact = _designing_request(db, product=product)
        seed.attach_design(db, request)
        tag_id = _tags(db, request.id)[0].id

        product.list_price = 1200.00
        db.commit()

        keep = client.post(
            f"{_CRM.format(id=request.id)}/tags/{tag_id}/pin",
            json={"action": "keep"},
        )
        assert keep.status_code == 200, keep.text

        # Silenced: Keep acknowledged this exact drift.
        silenced = client.get(f"{_CRM.format(id=request.id)}/data-changes").json()
        assert silenced == [], silenced

        line = _tags(db, request.id)[0]
        assert line.data_change_ack_hash is not None, (
            "Keep must have recorded an ack, or this test proves nothing"
        )

        response = client.post(f"{_CRM.format(id=request.id)}/data-changes/recheck")
        assert response.status_code == 200, response.text
        body = response.json()
        changed_row = next(
            (row for row in body if row["tag_id"] == tag_id), None
        )
        assert changed_row is not None, body
        assert any(
            change["field"] == "list_price" for change in changed_row["changes"]
        ), changed_row

        db.expire_all()
        line = _tags(db, request.id)[0]
        assert line.data_change_ack_hash is None, (
            "recheck must clear the ack, not just answer a fresh diff once"
        )

        # The ordinary GET agrees - the clear was PERSISTED, not returned once
        # and thrown away.
        after = client.get(f"{_CRM.format(id=request.id)}/data-changes").json()
        assert any(row["tag_id"] == tag_id for row in after), after

    def test_recheck_404s_for_another_companys_request(self, crm):
        client, db = crm
        from app.models.company import Company
        from app.models.price_tag import PriceTagRequest

        other_company_id = str(uuid.uuid4())
        db.execute(
            Company.__table__.insert().values(
                id=other_company_id,
                name="ZZT Other Co",
                code=seed.unique_code("OTH")[:20],
                is_active=True,
            )
        )
        db.flush()

        contact_id = seed.seed_portal_contact(db)
        product = seed.seed_product(db)
        other_request = seed.seed_request(
            db, contact_id, status="designing", products=[product]
        )
        db.query(PriceTagRequest).filter(
            PriceTagRequest.id == other_request.id
        ).update({"company_id": other_company_id})
        db.commit()

        response = client.post(
            f"{_CRM.format(id=other_request.id)}/data-changes/recheck"
        )

        assert response.status_code == 404, response.text
        # The APP's own NOT_FOUND, not a bare "no such route" 404 - the route
        # must exist and be the thing that refuses this id, or the assertion
        # above passes for a reason that has nothing to do with company scope.
        assert response.json().get("code") == "NOT_FOUND", response.text


# ---------------------------------------------------------------------------
# S8 (PLAN-price-tag-r10.md, "Product data change: auto-apply, keep the old
# data for rollback, indicator"): `designing`/`changes_requested` no longer
# wait for a person to click Update - the read seam itself (`resolve_request_
# line_data`) applies the change the next time anything reads it. Written
# test-FIRST: `data_updated_at`/`data_update_changes`/`data_update_version`
# do not exist on the model yet, so every assertion reading them is red on
# AttributeError; the auto-apply behaviour itself is red because today
# nothing re-pins without an explicit `pin` action.
# ---------------------------------------------------------------------------


class TestS8AutoApplyOnDesigning:
    def test_ac_s8_2_the_next_poll_applies_the_change_and_reports_it_once(self, crm):
        client, db = crm
        from app.models.dealer_kit import PageVersion

        product = seed.seed_product(db, list_price=1000.00)
        request, _product, _contact = _designing_request(db, product=product)
        page, _doc = seed.attach_design(db, request)
        product.list_price = 1200.00
        db.commit()
        tag_id = _tags(db, request.id)[0].id

        response = client.get(f"{_CRM.format(id=request.id)}/data-changes")

        assert response.status_code == 200, response.text
        body = response.json()
        row = next(r for r in body if r["tag_id"] == tag_id)
        assert any(c.get("field") == "list_price" for c in row["changes"]), row

        db.expire_all()
        tag = _tags(db, request.id)[0]
        assert float(tag.pinned_tag_data["list_price"]) == 1200.00, (
            "the tag must be re-pinned to the LIVE value with no click"
        )
        assert tag.data_updated_at is not None
        assert tag.data_update_changes, tag.data_update_changes
        assert tag.data_update_version is not None

        versions = (
            db.query(PageVersion)
            .filter(PageVersion.page_id == page.id)
            .order_by(PageVersion.version)
            .all()
        )
        before = [
            v for v in versions
            if (v.commit_message or "").startswith("Before product update:")
        ]
        assert len(before) == 1, [v.commit_message for v in versions]
        assert tag.data_update_version == before[0].version

    def test_ac_s8_2_a_second_poll_with_no_further_edit_reports_nothing(self, crm):
        client, db = crm

        product = seed.seed_product(db, list_price=1000.00)
        request, _product, _contact = _designing_request(db, product=product)
        seed.attach_design(db, request)
        product.list_price = 1200.00
        db.commit()

        client.get(f"{_CRM.format(id=request.id)}/data-changes")

        again = client.get(f"{_CRM.format(id=request.id)}/data-changes").json()
        assert again == [], again

    def test_ac_s8_3_three_tags_changing_together_fold_into_one_before_version(self, crm):
        client, db = crm
        from app.models.dealer_kit import PageVersion
        from app.services.price_tag_request_service import PriceTagRequestService

        products = [seed.seed_product(db, list_price=100.00 * (i + 1)) for i in range(3)]
        request, _p, _contact = _designing_request(db, product=products[0])
        PriceTagRequestService.replace_lines(
            db,
            request,
            [{"line_type": "product", "product_id": p.id} for p in products],
        )
        db.commit()
        page, _doc = seed.attach_design(db, request)
        for p in products:
            p.list_price = p.list_price + 50
        db.commit()

        response = client.get(f"{_CRM.format(id=request.id)}/data-changes")
        assert response.status_code == 200, response.text

        db.expire_all()
        tags = _tags(db, request.id)
        assert len(tags) == 3
        assert all(t.data_updated_at is not None for t in tags)

        versions = (
            db.query(PageVersion)
            .filter(PageVersion.page_id == page.id)
            .order_by(PageVersion.version)
            .all()
        )
        before = [
            v for v in versions
            if (v.commit_message or "").startswith("Before product update:")
        ]
        assert len(before) == 1, (
            "three tags changing in one sweep must fold into ONE before-version, "
            f"got {[v.commit_message for v in versions]}"
        )

    def test_ac_s8_4_proof_ready_is_not_auto_applied_flag_only_as_today(self, crm):
        client, db = crm

        product = seed.seed_product(db, list_price=1000.00)
        request, _product, _contact = _designing_request(db, product=product)
        seed.attach_design(db, request)
        request.status = "proof_ready"
        db.commit()
        product.list_price = 1200.00
        db.commit()
        tag_id = _tags(db, request.id)[0].id

        response = client.get(f"{_CRM.format(id=request.id)}/data-changes")

        assert response.status_code == 200, response.text
        body = response.json()
        row = next(r for r in body if r["tag_id"] == tag_id)
        assert row["changes"], "the change must still be FLAGGED at proof_ready"

        db.expire_all()
        tag = _tags(db, request.id)[0]
        assert float(tag.pinned_tag_data["list_price"]) == 1000.00, (
            "proof_ready must NOT auto-apply - Keep/Update stay a person's own click"
        )

        # Keep still works exactly as before S8.
        kept = client.post(
            f"{_CRM.format(id=request.id)}/tags/{tag_id}/pin", json={"action": "keep"}
        )
        assert kept.status_code == 200, kept.text

    def test_ac_s8_5_the_list_sweep_applies_the_update_too(self, crm):
        client, db = crm

        product = seed.seed_product(db, list_price=1000.00)
        request, _product, _contact = _designing_request(db, product=product)
        seed.attach_design(db, request)
        product.list_price = 1200.00
        db.commit()
        tag_id = _tags(db, request.id)[0].id

        listed = client.get("/api/v1/dealer-kit/price-tag-requests")
        assert listed.status_code == 200, listed.text

        db.expire_all()
        tag = _tags(db, request.id)[0]
        assert tag.data_updated_at is not None, (
            "the list sweep must apply the update the same way the detail poll does"
        )

        row = next(r for r in listed.json()["data"] if r["id"] == request.id)
        assert row["data_changed_tag_count"] >= 1

    def test_ac_s8_6_dismiss_clears_the_three_columns_and_the_count_drops(self, crm):
        client, db = crm

        product = seed.seed_product(db, list_price=1000.00)
        request, _product, _contact = _designing_request(db, product=product)
        seed.attach_design(db, request)
        product.list_price = 1200.00
        db.commit()
        tag_id = _tags(db, request.id)[0].id
        client.get(f"{_CRM.format(id=request.id)}/data-changes")

        response = client.post(f"{_CRM.format(id=request.id)}/tags/{tag_id}/dismiss")

        assert response.status_code == 200, response.text
        db.expire_all()
        tag = _tags(db, request.id)[0]
        assert tag.data_updated_at is None
        assert tag.data_update_changes is None
        assert tag.data_update_version is None

    def test_ac_s8_10_a_terminal_request_is_never_re_pinned(self, db_only):
        from app.services.dealer_kit import tag_data_service

        product = seed.seed_product(db_only, list_price=1000.00)
        contact_id = seed.seed_portal_contact(db_only)
        request = seed.seed_request(
            db_only, contact_id, status="collected", products=[product],
            print_by="office", assigned_to_id=seed.MARKETER_ID,
        )
        line = request.lines[0]
        tag = seed.first_tag(request)
        tag.pinned_tag_data = {"code": product.product_code, "list_price": 1000.00}
        tag.pinned_at = seed.utcnow()
        db_only.commit()
        product.list_price = 1200.00
        db_only.commit()

        tag_data_service.resolve_request_line_data(db_only, request)

        db_only.expire_all()
        fresh = (
            db_only.query(type(tag)).filter_by(id=tag.id).first()
        )
        assert float(fresh.pinned_tag_data["list_price"]) == 1000.00
        assert fresh.data_updated_at is None


# ---------------------------------------------------------------------------
# AC-S4-8 (PLAN-price-tag-r10.md S4): editing `price_tag_description` on a
# product with an open request changes the tag's data hash, so `GET
# data-changes` flags it - the same gate every other pinned field already
# goes through. Checked at `proof_ready`, outside `AUTO_UPDATE_STATUSES`
# (S8), so this is a clean "flag, not auto-apply" assertion.
# ---------------------------------------------------------------------------


def test_ac_s4_8_a_price_tag_description_edit_is_flagged_as_a_data_change():
    with blank_session() as db:
        seed.seed_marketer(db)
        product = seed.seed_product(db)
        product.price_tag_description = "Original copy"
        contact_id = seed.seed_portal_contact(db)
        request = seed.seed_request(
            db, contact_id, status="new", products=[product],
            print_by="office", assigned_to_id=seed.MARKETER_ID,
        )
        from app.services.price_tag_request_service import PriceTagRequestService

        PriceTagRequestService.transition_status(
            db, request.id, "designing", user_id=seed.MARKETER_ID
        )
        request.status = "proof_ready"
        db.commit()

        product.price_tag_description = "Changed copy"
        db.commit()

        from app.services.dealer_kit import tag_data_service

        rows = tag_data_service.resolve_request_line_data(db, request)

        row = rows[0]
        fields = {c.get("field") for c in (row.get("data_changes") or [])}
        assert "price_tag_description" in fields, row.get("data_changes")
