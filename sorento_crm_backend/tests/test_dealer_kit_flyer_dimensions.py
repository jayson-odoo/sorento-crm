"""Applying a flyer's printed sizes to the product master (S7.6).

Written before the route.

Every other part of the flyer feature reads. This is the one that WRITES to
``products``, and it writes to a table holding real master data that other
systems quote from, so the tests are about what it refuses rather than what it
does:

* **Nothing is applied that was not named.** The dangerous failure is a caller
  selecting one row and the server writing thirty, so the first assertion in the
  file is that the rows nobody ticked are byte-identical afterwards.
* **A conflict is not a correction.** A card that disagrees with a value somebody
  entered deliberately is refused unless the caller says out loud that they are
  overwriting it. A blank master is not the same act and does not need the same
  confirmation.
* **Partial success is reported per row.** 20 applied and 3 failed must come back
  as 20 and 3, naming the 3. Answering "success" for the 20 is the failure mode
  this endpoint exists to avoid.
* **The numbers come from the reading, never from the caller.** The request names
  codes; the millimetres are read off the stored flyer. Otherwise the endpoint is
  a "write anything into the product master" endpoint wearing a flyer costume.
* **Drafting a brochure is not permission to edit the master.** A designer holding
  every dealer-kit permission there is gets a 403.

Postgres only, on a blank scratch schema. Product codes are the real ones the
fixture flyer prints, because matching a printed code is the whole point; every
other value on every row is ZZT-scoped.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._fake_storage import patch_storage
from tests._pg_fixture import blank_session, unique_code

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "dealer_kit" / "flyer_sample.pdf"

# Codes printed on page 2 of the fixture, with the sizes it prints beside them.
# Verified against flyer_golden.json.
SIZED = "SRTJC8041"
SIZED_MM = (Decimal("1700.00"), Decimal("800.00"), Decimal("590.00"))
OTHER = "SRTJC2023"
OTHER_MM = (Decimal("1700.00"), Decimal("850.00"), Decimal("600.00"))
THIRD = "SRTJC8037"
THIRD_MM = (Decimal("1600.00"), Decimal("750.00"), Decimal("600.00"))

# Printed on the fixture, but with no L x W x H line under it, so it is never a
# dimension candidate however it is asked for.
UNSIZED = "SRTMRL707"

_SORENTO = "00000000-0000-0000-0000-000000000001"

_ADMIN_ID = "2f7e4c81-9a35-5d62-b418-7c0d9e3a5b16"
_ADMIN_ROLE = "8c1a6f39-4d72-5b08-9e51-3a7b2d4c6e80"
# Holds every dealer-kit permission and nothing else. The whole permission
# decision of this slice is that this person may NOT write to the master.
_DESIGNER_ID = "5b3d8a27-1e64-5f09-8c72-4d1a6b9e3f50"
_DESIGNER_ROLE = "9a4c7e12-6b38-5d71-a209-8f3e1c5b7d64"
# Holds the master-data write AND enough dealer-kit to see the reading.
_CURATOR_ID = "7e2b9d54-3c81-5a06-9f43-1b8c6e2d4a79"
_CURATOR_ROLE = "3d6f1b85-7a29-5c14-8e60-2b9d4f7a1c38"
# Holds the master-data write but cannot see a flyer reading at all.
_OUTSIDER_ID = "4a8c2e69-5f13-5b70-9d28-6e1b3a7c5d92"
_OUTSIDER_ROLE = "6b9e3a17-2d54-5f82-a136-7c4d8b1e9f25"
_NOPERM_ID = "1f5a8c34-9b26-5e70-8d19-3c7b2a6e4d81"

_PAGE_VIEW = "dealer_kit.page.view"
_PAGE_EDIT = "dealer_kit.page.edit"
_PRODUCTS_EDIT = "master_data.products.edit"

APPLY = "/api/v1/dealer-kit/flyer-readings/{}/dimensions/apply"


def _seed_roles(db) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    roles = {
        _ADMIN_ROLE: ("superadmin", "Superadmin", True),
        _DESIGNER_ROLE: ("zzt_dim_designer", "ZZT Designer", False),
        _CURATOR_ROLE: ("zzt_dim_curator", "ZZT Curator", False),
        _OUTSIDER_ROLE: ("zzt_dim_outsider", "ZZT Outsider", False),
    }
    for role_id, (slug, name, protected) in roles.items():
        db.add(
            UserRole(
                id=role_id,
                slug=slug,
                name=name,
                description="",
                is_protected=protected,
                is_default=False,
            )
        )

    users = {
        _ADMIN_ID: ("zzt-dim-admin", _ADMIN_ROLE),
        _DESIGNER_ID: ("zzt-dim-designer", _DESIGNER_ROLE),
        _CURATOR_ID: ("zzt-dim-curator", _CURATOR_ROLE),
        _OUTSIDER_ID: ("zzt-dim-outsider", _OUTSIDER_ROLE),
        _NOPERM_ID: ("zzt-dim-nobody", None),
    }
    for user_id, (handle, _role) in users.items():
        db.add(User(id=user_id, email=f"{handle}@test.com", name=handle, status="ACTIVE"))
    db.flush()

    for user_id, (_handle, role_id) in users.items():
        if role_id:
            db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))

    # The blank schema carries no permission rows, so the ones a migration seeds
    # in a real database are created here.
    grants = {
        _PAGE_VIEW: [_DESIGNER_ROLE, _CURATOR_ROLE],
        _PAGE_EDIT: [_DESIGNER_ROLE],
        _PRODUCTS_EDIT: [_CURATOR_ROLE, _OUTSIDER_ROLE],
    }
    for slug, role_ids in grants.items():
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        db.flush()
        for role_id in role_ids:
            db.add(
                UserRolePermission(
                    id=str(uuid.uuid4()), role_id=role_id, permission_id=perm_id
                )
            )
    db.commit()


@pytest.fixture
def api(monkeypatch):
    """The route stack with a switchable principal AND a switchable company."""
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db,
    )
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_roles(db)
        patch_storage(monkeypatch)
        here = {"company": _SORENTO}

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({here["company"]})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        def _in_company(company_id: str):
            here["company"] = company_id
            set_company_scope(db, frozenset({company_id}))

        _as(_ADMIN_ID)
        yield db, _as, _in_company

        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Rows
# --------------------------------------------------------------------------- #
def _upload(client: TestClient) -> str:
    res = client.post(
        "/api/v1/dealer-kit/flyer-readings",
        files={"file": ("zzt-dim-flyer.pdf", FIXTURE_PDF.read_bytes(), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _product(db, code: str, size: tuple | None = None):
    """A product carrying a code the fixture flyer prints, optionally sized."""
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    stem = unique_code("ZZTDIM")
    category = ProductCategory(category_code=stem, category_name=f"ZZT cat {stem}")
    uom = UnitOfMeasure(uom_code=stem, uom_name=f"ZZT uom {stem}")
    db.add_all([category, uom])
    db.flush()

    product = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
        dimensions_length=size[0] if size else None,
        dimensions_width=size[1] if size else None,
        dimensions_height=size[2] if size else None,
    )
    db.add(product)
    db.commit()
    return product


def _company(db) -> str:
    from app.models.company import Company

    company = Company(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT Other Co"),
        code=unique_code("ZZTDIMC")[:20],
        is_active=True,
    )
    db.add(company)
    db.commit()
    return company.id


def _size_of(db, product_id: str) -> tuple:
    from app.models.product import Product

    db.expire_all()
    row = db.query(Product).filter(Product.id == product_id).one()
    return (row.dimensions_length, row.dimensions_width, row.dimensions_height)


def _apply(client: TestClient, reading_id: str, codes, **body):
    return client.post(APPLY.format(reading_id), json={"codes": codes, **body})


def _refusal(body: dict, code: str) -> dict:
    return next(row for row in body["refused"] if row["code"] == code)


# --------------------------------------------------------------------------- #
# Applying
# --------------------------------------------------------------------------- #
class TestApply:
    def test_a_named_size_reaches_the_product_master(self, api) -> None:
        """The slice in one call: the flyer's millimetres, on the product."""
        db, _as, _scope = api
        product = _product(db, SIZED)

        with TestClient(app) as c:
            reading_id = _upload(c)
            res = _apply(c, reading_id, [SIZED])

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["appliedCount"] == 1
        assert body["refusedCount"] == 0
        entry = body["applied"][0]
        assert entry["code"] == SIZED
        # Named by code, never by id: the response is read by a screen.
        assert entry["productCode"] == SIZED
        assert (entry["lengthMm"], entry["widthMm"], entry["heightMm"]) == (1700, 800, 590)
        assert entry["previousLengthMm"] is None
        assert entry["wasConflict"] is False

        assert _size_of(db, product.id) == SIZED_MM

    def test_the_printed_millimetres_are_written_unconverted(self, api) -> None:
        """``products.dimensions_*`` is millimetres, and so is the flyer.

        Measured before this endpoint was written: of the fixture's 27 sized
        codes that exist in the live master, 24 hold EXACTLY the printed figure
        and the one disagreement is 10 mm on a single height. A unit conversion
        anywhere in this path would corrupt every one of them.
        """
        db, _as, _scope = api
        product = _product(db, SIZED)

        with TestClient(app) as c:
            reading_id = _upload(c)
            _apply(c, reading_id, [SIZED])

        length, width, height = _size_of(db, product.id)
        assert (length, width, height) == (
            Decimal("1700.00"),
            Decimal("800.00"),
            Decimal("590.00"),
        )

    def test_only_the_codes_named_are_written(self, api) -> None:
        """The dangerous one.

        Two candidates, one named. The other holds a size somebody entered that
        the flyer disagrees with, which is exactly the row an over-eager apply
        would destroy - and destroy silently, since the response would still say
        the request succeeded.
        """
        db, _as, _scope = api
        chosen = _product(db, SIZED)
        untouched = _product(db, OTHER, (Decimal("1699.00"), Decimal("849.00"), Decimal("599.00")))

        with TestClient(app) as c:
            reading_id = _upload(c)
            res = _apply(c, reading_id, [SIZED])

        assert res.status_code == 200, res.text
        assert [row["code"] for row in res.json()["applied"]] == [SIZED]
        assert _size_of(db, chosen.id) == SIZED_MM
        # Byte for byte what it was. Not "close to", not "the printed value".
        assert _size_of(db, untouched.id) == (
            Decimal("1699.00"),
            Decimal("849.00"),
            Decimal("599.00"),
        )

    def test_an_empty_selection_is_refused_rather_than_meaning_everything(
        self, api
    ) -> None:
        """"Apply everything you found" is not an operation this offers.

        An empty list read as "all" is one careless click from rewriting 342
        products off a PDF.
        """
        db, _as, _scope = api
        product = _product(db, SIZED)

        with TestClient(app) as c:
            reading_id = _upload(c)
            res = _apply(c, reading_id, [])

        assert res.status_code == 422, res.text
        # The message matters: a bare 422 reads as a broken screen.
        assert "name" in res.text.lower() and "apply" in res.text.lower()
        assert _size_of(db, product.id) == (None, None, None)

    def test_the_numbers_come_from_the_reading_not_from_the_caller(self, api) -> None:
        """The request names codes. It cannot carry millimetres.

        If a caller could send figures, this would be an endpoint for writing
        anything at all into the product master, reachable by anybody who can
        upload a PDF.
        """
        db, _as, _scope = api
        product = _product(db, SIZED)

        with TestClient(app) as c:
            reading_id = _upload(c)
            res = c.post(
                APPLY.format(reading_id),
                json={
                    "codes": [SIZED],
                    "lengthMm": 9999,
                    "widthMm": 9999,
                    "heightMm": 9999,
                },
            )

        assert res.status_code == 200, res.text
        assert _size_of(db, product.id) == SIZED_MM

    def test_a_code_named_twice_is_applied_once(self, api) -> None:
        db, _as, _scope = api
        _product(db, SIZED)

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _apply(c, reading_id, [SIZED, SIZED]).json()

        assert body["appliedCount"] == 1
        assert len(body["applied"]) == 1


# --------------------------------------------------------------------------- #
# A conflict is not a correction
# --------------------------------------------------------------------------- #
class TestConflicts:
    def test_a_conflicting_row_is_not_overwritten_without_confirmation(
        self, api
    ) -> None:
        """Somebody typed 592. The flyer prints 590. Neither is obviously right.

        The master value stays until a human says, in the request, that they are
        replacing it.
        """
        db, _as, _scope = api
        entered = (Decimal("1700.00"), Decimal("800.00"), Decimal("592.00"))
        product = _product(db, SIZED, entered)

        with TestClient(app) as c:
            reading_id = _upload(c)
            res = _apply(c, reading_id, [SIZED])

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["appliedCount"] == 0
        assert _refusal(body, SIZED)["reason"] == "conflict_not_confirmed"
        # And it says which value it protected, in words, so a reviewer can
        # decide rather than guess at why nothing happened.
        assert "592" in _refusal(body, SIZED)["message"]
        assert _size_of(db, product.id) == entered

    def test_a_confirmed_conflict_is_overwritten_and_says_what_it_replaced(
        self, api
    ) -> None:
        db, _as, _scope = api
        entered = (Decimal("1700.00"), Decimal("800.00"), Decimal("592.00"))
        product = _product(db, SIZED, entered)

        with TestClient(app) as c:
            reading_id = _upload(c)
            res = _apply(c, reading_id, [SIZED], overwriteConflicts=True)

        assert res.status_code == 200, res.text
        entry = res.json()["applied"][0]
        assert entry["wasConflict"] is True
        # What was there before is in the response, because this is the one
        # answer nobody can get back out of the master afterwards.
        assert entry["previousHeightMm"] == 592
        assert _size_of(db, product.id) == SIZED_MM

    def test_a_half_filled_master_row_counts_as_a_conflict(self, api) -> None:
        """Two of the three numbers were entered by somebody.

        Treating that as "missing" would let a partial row be completed AND
        silently corrected in the same click.
        """
        db, _as, _scope = api
        half = (Decimal("1700.00"), None, None)
        product = _product(db, SIZED, half)

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _apply(c, reading_id, [SIZED]).json()

        assert _refusal(body, SIZED)["reason"] == "conflict_not_confirmed"
        assert _size_of(db, product.id) == half

    def test_confirming_conflicts_does_not_widen_the_selection(self, api) -> None:
        """The flag is permission to overwrite the NAMED rows, nothing more."""
        db, _as, _scope = api
        chosen = _product(db, SIZED, (Decimal("1.00"), Decimal("2.00"), Decimal("3.00")))
        untouched = _product(db, OTHER, (Decimal("4.00"), Decimal("5.00"), Decimal("6.00")))

        with TestClient(app) as c:
            reading_id = _upload(c)
            _apply(c, reading_id, [SIZED], overwriteConflicts=True)

        assert _size_of(db, chosen.id) == SIZED_MM
        assert _size_of(db, untouched.id) == (
            Decimal("4.00"),
            Decimal("5.00"),
            Decimal("6.00"),
        )

    def test_a_row_that_already_agrees_is_left_alone_and_says_so(self, api) -> None:
        """Not an error, and not a write. A no-op that reports itself."""
        db, _as, _scope = api
        product = _product(db, SIZED, SIZED_MM)

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _apply(c, reading_id, [SIZED]).json()

        assert body["appliedCount"] == 0
        assert _refusal(body, SIZED)["reason"] == "already_matches"
        assert _size_of(db, product.id) == SIZED_MM


# --------------------------------------------------------------------------- #
# Partial success
# --------------------------------------------------------------------------- #
class TestPartialSuccess:
    def test_it_says_exactly_which_rows_did_not_apply(self, api) -> None:
        """20 applied and 3 failed comes back as 20 and 3, naming the 3.

        Reporting success for the 20 and staying quiet about the rest is the
        failure this shape exists to prevent.
        """
        db, _as, _scope = api
        good = _product(db, SIZED)
        doomed = _product(db, OTHER)
        _product(db, UNSIZED)  # printed, but no size under it

        with TestClient(app) as c:
            reading_id = _upload(c)

            # The product disappears between the report and the click. Somebody
            # deleted it in another tab, which is the ordinary version of this.
            from app.models.product import Product

            db.query(Product).filter(Product.id == doomed.id).delete()
            db.commit()

            res = _apply(c, reading_id, [SIZED, OTHER, UNSIZED, "ZZT-NEVER-PRINTED"])

        assert res.status_code == 200, res.text
        body = res.json()

        assert body["appliedCount"] == 1
        assert body["refusedCount"] == 3
        assert [row["code"] for row in body["applied"]] == [SIZED]
        assert _size_of(db, good.id) == SIZED_MM

        # Each refusal says WHY, because "3 failed" sends a reviewer looking in
        # the wrong place for all three.
        assert _refusal(body, OTHER)["reason"] == "product_not_found"
        assert _refusal(body, UNSIZED)["reason"] == "not_a_candidate"
        assert _refusal(body, "ZZT-NEVER-PRINTED")["reason"] == "not_a_candidate"

    def test_every_code_asked_for_is_accounted_for_exactly_once(self, api) -> None:
        """The property that makes the counts trustworthy at all."""
        db, _as, _scope = api
        _product(db, SIZED)
        _product(db, OTHER, OTHER_MM)  # agrees already
        _product(db, THIRD, (Decimal("1.00"), Decimal("2.00"), Decimal("3.00")))  # conflicts

        asked = [SIZED, OTHER, THIRD, UNSIZED]
        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _apply(c, reading_id, asked).json()

        answered = [row["code"] for row in body["applied"]] + [
            row["code"] for row in body["refused"]
        ]
        assert sorted(answered) == sorted(asked)
        assert body["appliedCount"] + body["refusedCount"] == len(asked)

    def test_a_refusal_never_costs_the_rows_that_did_apply(self, api) -> None:
        """One bad code does not roll back the good ones."""
        db, _as, _scope = api
        good = _product(db, SIZED)

        with TestClient(app) as c:
            reading_id = _upload(c)
            _apply(c, reading_id, [SIZED, "ZZT-NEVER-PRINTED"])

        assert _size_of(db, good.id) == SIZED_MM


# --------------------------------------------------------------------------- #
# Idempotence, and what the report says afterwards
# --------------------------------------------------------------------------- #
class TestAfterwards:
    def test_the_row_stops_being_a_candidate_for_action(self, api) -> None:
        """The reading did not change, so the report recomputes - and must move.

        Applied rows come back as agreements. If they came back as candidates a
        reviewer would apply them again every time they opened the screen.
        """
        db, _as, _scope = api
        _product(db, SIZED)

        with TestClient(app) as c:
            reading_id = _upload(c)
            before = c.get(f"/api/v1/dealer-kit/flyer-readings/{reading_id}").json()
            _apply(c, reading_id, [SIZED])
            after = c.get(f"/api/v1/dealer-kit/flyer-readings/{reading_id}").json()

        def verdict(body):
            return next(
                row["verdict"]
                for row in body["report"]["dimensionCandidates"]
                if row["code"] == SIZED
            )

        assert verdict(before) == "missing"
        assert verdict(after) == "agrees"

    def test_applying_twice_writes_nothing_the_second_time(self, api) -> None:
        db, _as, _scope = api
        product = _product(db, SIZED)

        with TestClient(app) as c:
            reading_id = _upload(c)
            first = _apply(c, reading_id, [SIZED]).json()

            from app.models.product import Product

            stamped = db.query(Product).filter(Product.id == product.id).one().updated_at

            second = _apply(c, reading_id, [SIZED]).json()

        assert first["appliedCount"] == 1
        assert second["appliedCount"] == 0
        assert _refusal(second, SIZED)["reason"] == "already_matches"
        # Not re-stamped: an idempotent call that still bumps updated_at makes
        # every downstream "what changed today" answer wrong.
        from app.models.product import Product

        assert db.query(Product).filter(Product.id == product.id).one().updated_at == stamped

    def test_the_write_is_attributable(self, api) -> None:
        """Somebody overwrote the master. The row says who, and from what."""
        db, _as, _scope = api
        product = _product(db, SIZED, (Decimal("1700.00"), Decimal("800.00"), Decimal("592.00")))

        with TestClient(app) as c:
            reading_id = _upload(c)

        # The curator may write the master but not upload a flyer, so the two
        # acts are deliberately performed by different people here.
        _as(_CURATOR_ID)
        with TestClient(app) as c:
            _apply(c, reading_id, [SIZED], overwriteConflicts=True)

        from app.models.audit import AuditLog
        from app.models.product import Product

        db.expire_all()
        assert db.query(Product).filter(Product.id == product.id).one().updated_by == _CURATOR_ID

        logged = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "product",
                AuditLog.entity_id == product.id,
                # An overwrite is an UPDATE. Without this the seed row's own CREATE
                # audit entry also matches (it carries the entered 592 as a NEW
                # value), and NOTHING orders the two: the query has no ORDER BY,
                # and `changed_at` cannot break the tie because it defaults to
                # now(), which is the TRANSACTION timestamp, and the whole test
                # runs inside one transaction. So "the last row" was decided by
                # wherever Postgres happened to place the two tuples in the shared
                # scratch schema's heap, which is a function of everything that ran
                # before this test. When the free space map handed the UPDATE an
                # earlier page than the CREATE, `changed[-1]` was the CREATE row,
                # whose old_values is None, and this failed in CI with a TypeError.
                AuditLog.action == "UPDATE",
            )
            .all()
        )
        changed = [row for row in logged if (row.new_values or {}).get("dimensions_height")]
        assert changed, "a master overwrite must leave an audit row"
        assert str(changed[-1].old_values["dimensions_height"]).startswith("592")


# --------------------------------------------------------------------------- #
# Who may do it
# --------------------------------------------------------------------------- #
class TestAccess:
    def test_a_designer_holding_every_dealer_kit_permission_is_refused(
        self, api
    ) -> None:
        """The permission decision of this slice, as a test.

        Drafting a brochure is not authority over the product master. Somebody
        who may upload a flyer, seed a catalogue and publish it still may not
        change what a product measures.
        """
        db, _as, _scope = api
        product = _product(db, SIZED)

        with TestClient(app) as c:
            reading_id = _upload(c)

        _as(_DESIGNER_ID)
        with TestClient(app) as c:
            res = _apply(c, reading_id, [SIZED])

        assert res.status_code == 403, res.text
        # And it says which permission is missing, or the designer files a bug
        # about a screen that does nothing.
        assert _PRODUCTS_EDIT in res.text
        assert _size_of(db, product.id) == (None, None, None)

    def test_the_master_data_permission_plus_a_view_of_the_reading_is_enough(
        self, api
    ) -> None:
        """Holding the master-data write is the authority; page.view is only
        the right to see the flyer this is being applied from."""
        db, _as, _scope = api
        product = _product(db, SIZED)

        with TestClient(app) as c:
            reading_id = _upload(c)

        _as(_CURATOR_ID)
        with TestClient(app) as c:
            res = _apply(c, reading_id, [SIZED])

        assert res.status_code == 200, res.text
        assert _size_of(db, product.id) == SIZED_MM

    def test_somebody_who_cannot_see_the_reading_is_refused(self, api) -> None:
        """Master-data rights do not include reading another team's flyers."""
        db, _as, _scope = api
        product = _product(db, SIZED)

        with TestClient(app) as c:
            reading_id = _upload(c)

        _as(_OUTSIDER_ID)
        with TestClient(app) as c:
            res = _apply(c, reading_id, [SIZED])

        assert res.status_code == 403, res.text
        assert _size_of(db, product.id) == (None, None, None)

    def test_a_stranger_is_refused(self, api) -> None:
        db, _as, _scope = api
        product = _product(db, SIZED)

        with TestClient(app) as c:
            reading_id = _upload(c)

        _as(_NOPERM_ID)
        with TestClient(app) as c:
            assert _apply(c, reading_id, [SIZED]).status_code == 403

        assert _size_of(db, product.id) == (None, None, None)


# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #
class TestCompanyScope:
    def test_another_companys_reading_is_absent_and_writes_nothing(self, api) -> None:
        """404, never 403 - and the master is untouched either way."""
        db, _as, _in_company = api
        product = _product(db, SIZED)

        with TestClient(app) as c:
            reading_id = _upload(c)

        elsewhere = _company(db)
        _in_company(elsewhere)

        with TestClient(app) as c:
            res = _apply(c, reading_id, [SIZED])

        assert res.status_code == 404, res.text
        # An absent ROUTE also answers 404, so the message has to be the one
        # this feature writes.
        assert "reading" in res.text.lower()

        _in_company(_SORENTO)
        assert _size_of(db, product.id) == (None, None, None)

    def test_the_same_code_under_another_company_is_never_touched(self, api) -> None:
        """Every code on the real flyer resolves to two products, one per
        company. Writing to the wrong one is invisible until a dealer reads it."""
        db, _as, _in_company = api

        elsewhere = _company(db)
        _in_company(elsewhere)
        theirs = _product(db, SIZED, (Decimal("11.00"), Decimal("22.00"), Decimal("33.00")))

        _in_company(_SORENTO)
        ours = _product(db, SIZED)

        with TestClient(app) as c:
            reading_id = _upload(c)
            res = _apply(c, reading_id, [SIZED])

        assert res.status_code == 200, res.text
        assert res.json()["appliedCount"] == 1
        assert _size_of(db, ours.id) == SIZED_MM

        _in_company(elsewhere)
        assert _size_of(db, theirs.id) == (
            Decimal("11.00"),
            Decimal("22.00"),
            Decimal("33.00"),
        )


class TestUnknownReading:
    def test_an_unknown_reading_is_404_in_words(self, api) -> None:
        db, _as, _scope = api
        _product(db, SIZED)

        with TestClient(app) as c:
            res = _apply(c, str(uuid.uuid4()), [SIZED])

        assert res.status_code == 404, res.text
        assert "reading" in res.text.lower()
