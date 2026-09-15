"""r9 S5/D19: a request's own design history (AC-S5-6).

Templates have had a version list, a viewer and a restore since r4. Requests
have been WRITING versions the whole time - ``_snapshot_draft`` fires on every
manual Save and on proof_ready - and offering no way to read one back, so the
history existed and was unreachable.

Three things worth stating, because a naive implementation gets each wrong:

* newest FIRST. A list that grows downwards buries the version somebody wants.
* a version carries ``pinned_line_data`` (D19). Restoring the document without
  the pins puts old artwork over today's prices, which is worse than not
  restoring at all.
* Restore ADDS a version ("Restored v<n>") rather than truncating the history.
  That is why it needs no confirmation: the way back is the list itself.

Red before the coder starts: the three routes and the column do not exist.
"""
from __future__ import annotations

import os

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


@pytest.fixture(autouse=True)
def no_respond(monkeypatch):
    """S8: no test run reaches api.respond.io. See `_ptag_r9_seed.block_respond`."""
    return seed.block_respond(monkeypatch)



@pytest.fixture(autouse=True)
def quiet_notifier(monkeypatch):
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


def _request_with_three_versions(db):
    """A designing request whose page carries versions 1, 2 and 3."""
    from app.services.price_tag_request_service import PriceTagRequestService

    product = seed.seed_product(db)
    contact_id = seed.seed_portal_contact(db)
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
    page, doc = seed.attach_design(db, request)

    from app.models.dealer_kit import PageVersion

    for version, message in ((2, "Saved"), (3, "Marked proof ready")):
        db.add(
            PageVersion(
                page_id=page.id,
                version=version,
                doc={**doc, "sheets": [{"id": f"sheet-v{version}", "tags": []}]},
                commit_message=message,
            )
        )
    db.flush()
    db.commit()
    return request, page, doc


def _first_tag_id(db, request) -> str:
    """The request's first TAG, which is what a pin and a placement key on."""
    from app.models.price_tag import PriceTagRequestLine, PriceTagRequestTag

    return (
        db.query(PriceTagRequestTag.id)
        .join(PriceTagRequestLine, PriceTagRequestLine.id == PriceTagRequestTag.line_id)
        .filter(PriceTagRequestLine.request_id == request.id)
        .order_by(PriceTagRequestLine.sort_order, PriceTagRequestTag.sort_order)
        .scalar()
    )


class TestTheVersionList:
    def test_it_lists_newest_first_with_a_readable_author(self, crm):
        client, db = crm
        request, _page, _doc = _request_with_three_versions(db)

        response = client.get(f"{_CRM.format(id=request.id)}/versions")

        assert response.status_code == 200, response.text
        rows = response.json()
        assert [row["version"] for row in rows] == [3, 2, 1]
        assert rows[0]["commit_message"] == "Marked proof ready"
        for row in rows:
            assert "created_by_name" in row, "no UUID reaches a screen"
            assert "created_at" in row

    def test_a_request_with_no_page_answers_an_empty_list_not_a_404(self, crm):
        """An empty history is a state the sheet draws, not an error."""
        client, db = crm
        contact_id = seed.seed_portal_contact(db)
        request = seed.seed_request(
            db, contact_id, status="new", products=[seed.seed_product(db)]
        )

        response = client.get(f"{_CRM.format(id=request.id)}/versions")

        assert response.status_code == 200, response.text
        assert response.json() == []


class TestReadingOneVersion:
    def test_it_answers_the_full_design_payload_for_that_version(self, crm):
        client, db = crm
        request, _page, _doc = _request_with_three_versions(db)

        response = client.get(f"{_CRM.format(id=request.id)}/versions/2")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["version"] == 2
        assert body["doc"]["sheets"][0]["id"] == "sheet-v2"
        for key in ("lines", "assets", "images", "fonts"):
            assert key in body, (
                f"missing {key!r} - a version opens in the shared lightbox "
                "(D19), which needs the same media maps a live design needs"
            )

    def test_a_version_that_does_not_exist_404s(self, crm):
        client, db = crm
        request, _page, _doc = _request_with_three_versions(db)

        assert client.get(f"{_CRM.format(id=request.id)}/versions/99").status_code == 404


class TestRestore:
    def test_it_writes_the_doc_and_the_pins_back_and_adds_a_version(self, crm):
        client, db = crm
        from app.models.dealer_kit import Page, PageVersion
        from app.models.price_tag import PriceTagRequestLine, PriceTagRequestTag

        request, page, _doc = _request_with_three_versions(db)
        # Version 1 is the one the pins were taken with; move the pin on since,
        # so a restore that only put the DOC back would be visible.
        version_one = (
            db.query(PageVersion)
            .filter(PageVersion.page_id == page.id, PageVersion.version == 1)
            .first()
        )
        # Keyed by TAG since the combos slice: that is what the document keys
        # its placements on, so a restore puts each pin back under the tag that
        # was drawn from it.
        version_one.pinned_line_data = {
            _first_tag_id(db, request): {"code": "ZZT-PINNED-V1", "list_price": 111.0}
        }
        db.query(PriceTagRequestTag).filter(
            PriceTagRequestTag.id == _first_tag_id(db, request)
        ).update({"pinned_tag_data": {"code": "ZZT-MOVED-ON", "list_price": 999.0}})
        db.commit()

        response = client.post(f"{_CRM.format(id=request.id)}/versions/1/restore")

        assert response.status_code == 200, response.text
        assert response.json()["version"] == 4

        db.expire_all()
        versions = (
            db.query(PageVersion)
            .filter(PageVersion.page_id == page.id)
            .order_by(PageVersion.version)
            .all()
        )
        assert [row.version for row in versions] == [1, 2, 3, 4], (
            "Restore adds to the history, it does not truncate it"
        )
        # Owner finding, PT-202609-0015: the NEW version restore adds is the
        # state being LEFT (what was live before the restore), not a duplicate
        # of v1 - v1 already exists as history, so re-snapshotting it a second
        # time under "Restored v1" is the bug this pins down.
        assert versions[-1].commit_message == "Before restore to v1"

        restored_page = db.query(Page).filter(Page.id == page.id).first()
        drawn = restored_page.draft_doc or versions[-1].doc
        assert drawn["sheets"][0]["id"] == "sheet-1"

        line = (
            db.query(PriceTagRequestTag)
            .filter(PriceTagRequestTag.id == _first_tag_id(db, request))
            .first()
        )
        assert line.pinned_tag_data["code"] == "ZZT-PINNED-V1", (
            "the pins are half the version - a doc restored over today's data "
            "shows old artwork at new prices"
        )

    def test_the_owner_sequence_pin_update_restore_restore(self, crm):
        """PT-202609-0015: pin 1260 -> update to 2260 -> restore v1 -> restore
        v2, walked exactly as the owner hit it.

        Before this fix, Update snapshotted only the OLD pin (never captured
        2260 anywhere), and Restore re-snapshotted the version it restored TO
        instead of the state it was leaving - so after "Update then Restore
        v1", no version anywhere held 2260 and it was gone for good.
        """
        from app.models.dealer_kit import PageVersion
        from app.models.price_tag import PriceTagRequestTag
        from app.services.price_tag_request_service import PriceTagRequestService

        client, db = crm
        product = seed.seed_product(db, list_price=1260.00)
        contact_id = seed.seed_portal_contact(db)
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
        tag_id = _first_tag_id(db, request)
        assert float(
            db.query(PriceTagRequestTag)
            .filter(PriceTagRequestTag.id == tag_id)
            .first()
            .pinned_tag_data["list_price"]
        ) == 1260.00

        # Update to 2260: the pin route creates the page (none exists yet).
        product.list_price = 2260.00
        db.commit()
        update = client.post(
            f"{_CRM.format(id=request.id)}/tags/{tag_id}/pin",
            json={"action": "update"},
        )
        assert update.status_code == 200, update.text

        req = PriceTagRequestService.get_request(db, request.id)
        page_id = req.page_id
        assert page_id, "the update action must create the page"

        def versions():
            db.expire_all()
            return (
                db.query(PageVersion)
                .filter(PageVersion.page_id == page_id)
                .order_by(PageVersion.version)
                .all()
            )

        def pin_of(version_row) -> float:
            return float((version_row.pinned_line_data or {})[tag_id]["list_price"])

        rows = versions()
        assert len(rows) == 2, [r.commit_message for r in rows]
        v1, v2 = rows
        assert v1.commit_message.startswith("Before product update:")
        assert pin_of(v1) == 1260.00
        assert v2.commit_message.startswith("Product update:")
        assert pin_of(v2) == 2260.00

        live_pin = lambda: float(
            db.query(PriceTagRequestTag)
            .filter(PriceTagRequestTag.id == tag_id)
            .first()
            .pinned_tag_data["list_price"]
        )
        assert live_pin() == 2260.00

        # Restore v1: the state being LEFT (2260) is what the new version
        # carries, and the live pin becomes v1's (1260) - not re-snapshotted.
        restore_v1 = client.post(f"{_CRM.format(id=request.id)}/versions/1/restore")
        assert restore_v1.status_code == 200, restore_v1.text

        rows = versions()
        assert len(rows) == 3, [r.commit_message for r in rows]
        v3 = rows[2]
        assert v3.commit_message == "Before restore to v1"
        assert pin_of(v3) == 2260.00
        assert live_pin() == 1260.00

        # Restoring v2 then brings 2260 back.
        restore_v2 = client.post(f"{_CRM.format(id=request.id)}/versions/2/restore")
        assert restore_v2.status_code == 200, restore_v2.text
        assert live_pin() == 2260.00

    def test_one_request_writing_two_versions_gets_consecutive_numbers(self, crm):
        """Live 500 on :3082, PT-202609-0015: `_snapshot_draft` computed
        ``max(PageVersion.version) + 1`` with a query, and the before + after
        snapshots an Update writes in ONE request both read that same max,
        because the first ``PageVersion`` was only ``db.add``ed, not flushed,
        before the second query ran - both got version 1, and the second
        INSERT hit ``uq_dealer_kit_page_version``.

        This suite's own session defaults to autoflush (SQLAlchemy's own
        default), which is exactly why every other test here never tripped
        over it: the app's real ``SessionLocal`` runs with ``autoflush=False``
        (see ``tests/_pg_fixture.py: pg_session``'s own docstring on the same
        point), so the live route's second query genuinely could not see the
        first, unflushed row. Turning autoflush off here for one call is what
        makes this test tell the truth about the route instead of about this
        fixture's own session.
        """
        from app.models.dealer_kit import PageVersion
        from app.services.price_tag_request_service import PriceTagRequestService

        client, db = crm
        product = seed.seed_product(db, list_price=1000.00)
        contact_id = seed.seed_portal_contact(db)
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
        tag_id = _first_tag_id(db, request)

        product.list_price = 1200.00
        db.commit()

        db.autoflush = False
        try:
            response = client.post(
                f"{_CRM.format(id=request.id)}/tags/{tag_id}/pin",
                json={"action": "update"},
            )
        finally:
            db.autoflush = True

        assert response.status_code == 200, response.text

        req = PriceTagRequestService.get_request(db, request.id)
        db.expire_all()
        versions = (
            db.query(PageVersion)
            .filter(PageVersion.page_id == req.page_id)
            .order_by(PageVersion.version)
            .all()
        )
        assert [v.version for v in versions] == [1, 2], [
            (v.version, v.commit_message) for v in versions
        ]
        assert versions[0].commit_message.startswith("Before product update:")
        assert versions[1].commit_message.startswith("Product update:")

    def test_restoring_a_version_that_does_not_exist_404s(self, crm):
        client, db = crm
        request, _page, _doc = _request_with_three_versions(db)

        assert (
            client.post(f"{_CRM.format(id=request.id)}/versions/99/restore").status_code
            == 404
        )


class TestAVersionDrawsItsOwnPinnedData:
    """S2: `GET .../versions/{n}` resolves the lines from `row.pinned_line_data`.

    A version carries TWO things (D19): the document and the product data that
    was pinned when it was written. The route draws the version's document but
    resolves its lines against TODAY's pins, so View shows last week's layout
    filled with this week's prices - a page that never existed, presented as
    history, and the one thing somebody opens History to check.

    Restore already writes the pins back, so the data is there; only the read
    ignores it.
    """

    def _version_with_its_own_pin(self, db):
        """A request whose v1 was snapshotted at RM 1,000 and whose live pin has
        since moved to RM 1,900. Returns ``(request, page)``."""
        from app.models.dealer_kit import PageVersion
        from app.models.price_tag import PriceTagRequest, PriceTagRequestTag
        from app.services.price_tag_request_service import PriceTagRequestService

        product = seed.seed_product(db, list_price=1000.00)
        contact_id = seed.seed_portal_contact(db)
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
        page, doc = seed.attach_design(db, request)

        line_id = _first_tag_id(db, request)
        snapshot_pin = dict(
            db.query(PriceTagRequestTag)
            .filter(PriceTagRequestTag.id == line_id)
            .first()
            .pinned_tag_data
        )
        db.query(PageVersion).filter(
            PageVersion.page_id == page.id, PageVersion.version == 1
        ).update({"pinned_line_data": {line_id: snapshot_pin}})

        # Marketing has since pressed Update: the LIVE pin now says 1,900.
        moved = {**snapshot_pin, "list_price": 1900.0, "name": "ZZT renamed since"}
        db.query(PriceTagRequestTag).filter(
            PriceTagRequestTag.id == line_id
        ).update({"pinned_tag_data": moved})
        db.commit()
        db.expire_all()
        return (
            db.query(PriceTagRequest).filter(PriceTagRequest.id == request.id).first(),
            page,
        )

    def test_the_lines_come_from_the_version_own_pins(self, crm):
        client, db = crm
        request, _page = self._version_with_its_own_pin(db)

        body = client.get(f"{_CRM.format(id=request.id)}/versions/1").json()

        line = body["lines"][0]
        assert float(line["list_price"]) == 1000.00, (
            "the version was written when the tag said 1,000; drawing it at "
            "1,900 invents a page that never existed"
        )
        assert line["name"] != "ZZT renamed since"

    def test_the_live_design_still_shows_the_live_pin(self, crm):
        """The other half of the same rule, so a fix cannot swap them over."""
        client, db = crm
        request, _page = self._version_with_its_own_pin(db)

        body = client.get(f"{_CRM.format(id=request.id)}/design").json()

        assert float(body["lines"][0]["list_price"]) == 1900.00

    def test_a_version_written_before_pins_existed_still_draws(self, crm):
        """`pinned_line_data` is nullable: every version written before r9 has
        none, and falling back to the live resolve is the only thing left to
        do - but it must not 500."""
        from app.models.dealer_kit import PageVersion

        client, db = crm
        request, page = self._version_with_its_own_pin(db)
        db.query(PageVersion).filter(
            PageVersion.page_id == page.id, PageVersion.version == 1
        ).update({"pinned_line_data": None})
        db.commit()

        response = client.get(f"{_CRM.format(id=request.id)}/versions/1")

        assert response.status_code == 200, response.text
        assert response.json()["lines"]
