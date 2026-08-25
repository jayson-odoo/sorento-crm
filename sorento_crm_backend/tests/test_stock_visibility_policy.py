"""Stock visibility policy - resolution, enforcement and the admin CRUD.

UAC `documentation/plans/inventory/stock-visibility-policy-acceptance-criteria.md`
sections A, B and C. PLAN `documentation/plans/inventory/PLAN-stock-visibility-policy.md`.

What the feature has to guarantee, and what each group here pins:

* **A - resolution.** Three tiers (contact override > access type > global default)
  with the MOST RESTRICTIVE access-type row winning when a contact holds several.
  A contact tagged both `dealer` and `end_user` must not be widened by the looser
  tag, or the dealer roll-out leaks quantities the day someone adds a second tag.
* **B - enforcement.** The policy is applied in `StockService.list_stock`, and ONLY
  when the request carries `contact_id` - the staff web grid calls the same route
  with no contact and must stay byte-identical. `compact` and `availability` return
  `data: []`: a row with the quantity stripped still names the locations and their
  count, and the raw (non-render) shape is readable by any direct MCP caller, so
  empty is the only shape that cannot leak.
* **C - CRUD.** One body shape for every tier (`{effective, override}`), reads on
  `inventory.stock.view`, writes on `inventory.stock.edit`, DELETE answering with
  the tier the caller falls back to.

Postgres only, blank schema, every row seeded here (CI's database has none).
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import (
    get_current_user,
    get_current_user_or_api_key,
    get_db,
)
from app.models.access import ContactAccessType, RespondContact, StockVisibilityPolicy
from app.models.base import set_company_scope
from app.models.inventory import StockLedger
from app.models.respond_workspace import RespondWorkspace
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.inventory_service import StockService
from app.services.stock_visibility import default_policy, resolve_policy
from app.services.user_service import UserPermissionService

from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha, stock, warehouse
from tests._pg_fixture import blank_session, unique_code

READ_PERM = "inventory.stock.view"
WRITE_PERM = "inventory.stock.edit"
BASE = "/api/v1/inventory/stock-visibility"


# --------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


# --------------------------------------------------------------------- seeding


def _workspace(db, space_id: str) -> RespondWorkspace:
    row = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=space_id,
        name="ZZT workspace",
        api_key_ciphertext="zzt",
    )
    db.add(row)
    db.flush()
    return row


def _contact(db, *, respond_io_id=None, workspace=None) -> RespondContact:
    row = RespondContact(
        id=unique_code("CONTACT"),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name="ZZT Contact",
        respond_io_id=respond_io_id,
        workspace_id=workspace.id if workspace else None,
    )
    db.add(row)
    db.flush()
    return row


def _access_type(db, code: str, name: str | None = None) -> ContactAccessType:
    row = ContactAccessType(code=code, name=name or code.title(), is_active=True)
    db.add(row)
    db.flush()
    return row


def _tag(db, contact: RespondContact, access_type: ContactAccessType) -> None:
    from app.models.access import respond_contact_access_types

    db.execute(
        respond_contact_access_types.insert().values(
            contact_id=contact.id, access_type_code=access_type.code
        )
    )
    db.flush()


def _policy_row(
    db,
    *,
    mode: str,
    warehouse_ids=None,
    contact=None,
    access_type=None,
) -> StockVisibilityPolicy:
    row = StockVisibilityPolicy(
        id=str(uuid.uuid4()),
        contact_id=contact.id if contact else None,
        access_type_code=access_type.code if access_type else None,
        mode=mode,
        warehouse_ids=warehouse_ids,
    )
    db.add(row)
    db.flush()
    return row


def _wh(db, code: str, *, company_id: str = DEFAULT_COMPANY_ID, segment=None):
    row = warehouse(db, company_id=company_id, code=code)
    row.segment = segment
    db.flush()
    return row


def _bulk_import_ledger(db, *, product_id: str, warehouse_id: str) -> StockLedger:
    """The row `last_updated_at` is derived from (system-wide latest BULK_IMPORT)."""
    row = StockLedger(
        id=str(uuid.uuid4()),
        product_id=product_id,
        warehouse_id=warehouse_id,
        transaction_type="BULK_IMPORT",
        quantity_change=1,
        previous_quantity=0,
        new_quantity=1,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    return row


# ============================================================ A. resolution


_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "416_stock_visibility_policy_stock_visibility_policies.py"
)


def _seed_from_migration(db) -> None:
    """Run ONLY the migration's seed half against the blank schema.

    `create_all` builds the table but never runs a migration's INSERT (see
    LESSONS `create_all skips migration seeds`), so the seed has to be invoked
    explicitly to be tested at all.
    """
    spec = importlib.util.spec_from_file_location("migration_416", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.seed_default_row(db.connection())


def test_migration_builds_the_table_the_model_expects(db):
    """`create_all` and the migration are two independent descriptions of the same
    table, and only one of them runs in production. Drop the created one, run the
    real `upgrade()` in its place, and use the ORM against the result - a CHECK or
    a partial unique that only exists on the model would fail here."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text as sa_text
    from sqlalchemy.exc import IntegrityError

    db.execute(sa_text("DROP TABLE stock_visibility_policies"))
    spec = importlib.util.spec_from_file_location("migration_416_upgrade", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        module.upgrade()

    seeded = db.query(StockVisibilityPolicy).all()
    assert [(row.mode, row.warehouse_ids) for row in seeded] == [("detailed", None)]

    with pytest.raises(IntegrityError):
        _policy_row(db, mode="availability")
        db.flush()
    db.rollback()


def test_default_row_seeded_inert(db):
    """A1. The deploy leaves one default row that changes nothing for anyone, and
    running the seed twice does not mint a second."""
    _seed_from_migration(db)
    _seed_from_migration(db)

    rows = (
        db.query(StockVisibilityPolicy)
        .filter(
            StockVisibilityPolicy.contact_id.is_(None),
            StockVisibilityPolicy.access_type_code.is_(None),
        )
        .all()
    )
    assert len(rows) == 1
    assert rows[0].mode == "detailed"
    assert rows[0].warehouse_ids is None

    policy = default_policy(db)
    assert (policy.mode, policy.warehouse_ids, policy.source) == (
        "detailed",
        None,
        "default",
    )


def test_default_policy_without_a_row_is_still_detailed(db):
    """The floor of the chain is code, not data: a database built by `create_all`
    (CI) carries no seeded row, and the resolver must not fail closed there - it
    would black out the staff-facing default for everyone."""
    policy = default_policy(db)
    assert (policy.mode, policy.warehouse_ids, policy.source) == (
        "detailed",
        None,
        "default",
    )


def test_contact_override_beats_access_type(db):
    """A2."""
    contact = _contact(db)
    dealer = _access_type(db, unique_code("dealer")[:50], "Dealer")
    _tag(db, contact, dealer)
    _policy_row(db, mode="availability", access_type=dealer)
    _policy_row(db, mode="compact", contact=contact)

    policy = resolve_policy(db, contact.id)

    assert policy.mode == "compact"
    assert policy.source == "contact"


def test_multiple_access_types_most_restrictive(db):
    """A3. Most restrictive mode, intersection of warehouses, NULL = all."""
    brw = _wh(db, unique_code("BRW")[:50])
    mwh = _wh(db, unique_code("MWH")[:50])
    dc1 = _wh(db, unique_code("DC1")[:50])
    contact = _contact(db)
    dealer = _access_type(db, unique_code("dealer")[:50], "Dealer")
    end_user = _access_type(db, unique_code("end_user")[:50], "End user")
    _tag(db, contact, dealer)
    _tag(db, contact, end_user)
    _policy_row(
        db,
        mode="availability",
        warehouse_ids=[brw.id, mwh.id, dc1.id],
        access_type=dealer,
    )
    _policy_row(db, mode="detailed", warehouse_ids=None, access_type=end_user)

    policy = resolve_policy(db, contact.id)

    assert policy.mode == "availability"
    assert policy.warehouse_ids == frozenset({brw.id, mwh.id, dc1.id})
    assert policy.source == "access_type"


def test_multiple_access_types_intersect_their_warehouses(db):
    """A3, the half a single-row fixture cannot show: two rows that each name
    warehouses narrow to the OVERLAP, never to the union."""
    brw = _wh(db, unique_code("BRW")[:50])
    mwh = _wh(db, unique_code("MWH")[:50])
    dc1 = _wh(db, unique_code("DC1")[:50])
    contact = _contact(db)
    one = _access_type(db, unique_code("t1")[:50], "Type one")
    two = _access_type(db, unique_code("t2")[:50], "Type two")
    _tag(db, contact, one)
    _tag(db, contact, two)
    _policy_row(db, mode="compact", warehouse_ids=[brw.id, mwh.id], access_type=one)
    _policy_row(db, mode="compact", warehouse_ids=[mwh.id, dc1.id], access_type=two)

    policy = resolve_policy(db, contact.id)

    assert policy.warehouse_ids == frozenset({mwh.id})


def test_falls_back_to_default(db):
    """A4."""
    _seed_from_migration(db)
    contact = _contact(db)

    policy = resolve_policy(db, contact.id)

    assert (policy.mode, policy.warehouse_ids, policy.source) == (
        "detailed",
        None,
        "default",
    )


def test_unresolvable_contact_fails_closed(db):
    """A5. Same shape as company scope today: zero rows, and NO visibility block -
    a block would tell the caller a policy was applied when none resolved."""
    assert resolve_policy(db, "ZZT-NO-SUCH-CONTACT") is None

    p = product(db, company_id=DEFAULT_COMPANY_ID)
    wh = _wh(db, unique_code("WH")[:50])
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=wh.id, on_hand=5)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[p.id], contact_id="ZZT-NO-SUCH-CONTACT", space_id="364817"
    )

    assert result["data"] == []
    assert result["pagination"]["total"] == 0
    assert "stock_visibility" not in result


def test_contact_id_both_forms(db):
    """A6. n8n thinks in Respond.io ids; other callers have already resolved the
    internal one. Guessing wrong denies an entitled contact."""
    workspace = _workspace(db, "364817")
    contact = _contact(db, respond_io_id="99887766", workspace=workspace)
    _policy_row(db, mode="compact", contact=contact)

    by_internal = resolve_policy(db, contact.id)
    by_respond = resolve_policy(db, "99887766", "364817")

    assert by_internal.mode == by_respond.mode == "compact"
    assert by_internal.source == by_respond.source == "contact"


def test_staff_path_ignores_policy(db):
    """A7. The staff web grid calls the same route with no contact params. Even
    with the DEFAULT row flipped to compact, staff still get full rows - or
    flipping the default for the chatbot silently breaks /inventory/stock."""
    _policy_row(db, mode="compact")
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    wh = _wh(db, unique_code("WH")[:50])
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=wh.id, on_hand=7)
    db.flush()

    result = StockService(db).list_stock(product_ids=[p.id])

    assert len(result["data"]) == 1
    assert result["pagination"]["total"] == 1
    assert "stock_visibility" not in result
    assert "stock_summary" not in result


# ============================================================ B. enforcement


def _three_warehouses(db):
    return (
        _wh(db, "ZZTBRW", segment="dealer"),
        _wh(db, "ZZTBRW-BB", segment="project"),
        _wh(db, "ZZTDC1", segment="dealer"),
    )


def test_detailed_filters_warehouses(db):
    """B1."""
    brw, brw_bb, dc1 = _three_warehouses(db)
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    for wh, qty in ((brw, 500), (brw_bb, 200), (dc1, 999)):
        stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=wh.id, on_hand=qty)
    contact = _contact(db)
    _policy_row(db, mode="detailed", warehouse_ids=[brw.id, brw_bb.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(product_ids=[p.id], contact_id=contact.id)

    assert {row.warehouse_id for row in result["data"]} == {brw.id, brw_bb.id}
    assert result["pagination"]["total"] == 2
    assert result["stock_visibility"] == {
        "mode": "detailed",
        "warehouse_codes": ["ZZTBRW", "ZZTBRW-BB"],
        "source": "contact",
    }


def test_detailed_null_is_all(db):
    """B2. NULL warehouses = today's behaviour, byte for byte."""
    brw, brw_bb, dc1 = _three_warehouses(db)
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    for wh in (brw, brw_bb, dc1):
        stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=wh.id, on_hand=5)
    contact = _contact(db)
    _policy_row(db, mode="detailed", warehouse_ids=None, contact=contact)
    db.flush()

    scoped = StockService(db).list_stock(product_ids=[p.id], contact_id=contact.id)
    staff = StockService(db).list_stock(product_ids=[p.id])

    assert len(scoped["data"]) == len(staff["data"]) == 3
    assert scoped["stock_visibility"]["warehouse_codes"] is None


def test_compact_groups_and_sums_on_hand(db):
    """B3. One block per product; the disallowed location is absent from the
    total as well as from the list."""
    brw, brw_bb, dc1 = _three_warehouses(db)
    brw_ib = _wh(db, "ZZTBRW-IB", segment="project")
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    for wh, qty in ((brw, 500), (brw_bb, 200), (brw_ib, 300), (dc1, 999)):
        stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=wh.id, on_hand=qty)
    contact = _contact(db)
    _policy_row(
        db,
        mode="compact",
        warehouse_ids=[brw.id, brw_bb.id, brw_ib.id],
        contact=contact,
    )
    db.flush()

    result = StockService(db).list_stock(product_ids=[p.id], contact_id=contact.id)

    assert result["data"] == []
    assert result["pagination"]["total"] == 0
    assert result["stock_visibility"]["mode"] == "compact"
    assert len(result["stock_summary"]) == 1
    block = result["stock_summary"][0]
    assert block["product_id"] == p.id
    assert block["product_code"] == p.product_code
    assert block["total_on_hand"] == 1000
    assert block["locations"] == [
        {"warehouse_code": "ZZTBRW", "quantity_on_hand": 500},
        {"warehouse_code": "ZZTBRW-BB", "quantity_on_hand": 200},
        {"warehouse_code": "ZZTBRW-IB", "quantity_on_hand": 300},
    ]
    assert block["flags"] == {"discontinued": False}


def test_compact_multi_product_blocks(db):
    """B4. One block per product, each with its own total."""
    brw, brw_bb, _ = _three_warehouses(db)
    first = product(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-SKU-A")
    second = product(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-SKU-B")
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=first.id, warehouse_id=brw.id, on_hand=10)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=first.id, warehouse_id=brw_bb.id, on_hand=5)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=second.id, warehouse_id=brw.id, on_hand=2)
    contact = _contact(db)
    _policy_row(db, mode="compact", contact=contact)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[first.id, second.id], contact_id=contact.id
    )

    blocks = {b["product_code"]: b for b in result["stock_summary"]}
    assert list(blocks) == ["ZZT-SKU-A", "ZZT-SKU-B"]
    assert blocks["ZZT-SKU-A"]["total_on_hand"] == 15
    assert blocks["ZZT-SKU-B"]["total_on_hand"] == 2


def test_compact_uses_on_hand_not_available(db):
    """B5. The basis is `quantity_on_hand` (today's answer); reserved is ignored,
    or the compact block would silently disagree with the detailed one."""
    brw, _, _ = _three_warehouses(db)
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    row = stock(
        db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=100
    )
    row.quantity_reserved = 40
    contact = _contact(db)
    _policy_row(db, mode="compact", contact=contact)
    db.flush()

    result = StockService(db).list_stock(product_ids=[p.id], contact_id=contact.id)

    assert result["stock_summary"][0]["total_on_hand"] == 100


# ---- the availability leak walk ---------------------------------------------

#: Keys allowed to carry a number on an `availability` answer. `requested_qty` is
#: the DEALER'S OWN number echoed back, not stock.
_ALLOWED_NUMERIC_KEYS = {"requested_qty", "needs_quantity"}
_QUANTITY_WORDS = ("quantity", "on_hand", "qty")


def _walk(node, path="$"):
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{path}.{key}", key, value
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


def _assert_no_quantity_anywhere(body, forbidden_numbers):
    offending_keys = [
        path
        for path, key, _ in _walk(body)
        if key not in _ALLOWED_NUMERIC_KEYS
        and any(word in key for word in _QUANTITY_WORDS)
    ]
    assert not offending_keys, f"quantity-shaped keys leaked: {offending_keys}"

    leaked_values = [
        path
        for path, key, value in _walk(body)
        if key not in _ALLOWED_NUMERIC_KEYS
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value in forbidden_numbers
    ]
    assert not leaked_values, f"stock quantities leaked as values: {leaked_values}"


def test_availability_needs_quantity_no_leak(db):
    """B6. No number given yet -> ask for one, and say nothing else."""
    brw, _, _ = _three_warehouses(db)
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=613)
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(product_ids=[p.id], contact_id=contact.id)

    assert result["data"] == []
    assert result["stock_availability"] == [
        {
            "product_id": p.id,
            "product_code": p.product_code,
            "product_name": p.product_name,
            "needs_quantity": True,
            "requested_qty": None,
            "available": None,
        }
    ]
    assert "stock_summary" not in result
    _assert_no_quantity_anywhere(result, {613})


def test_availability_yes(db):
    """B7. 50 asked for, 60 on hand across the allowed locations."""
    brw, brw_bb, _ = _three_warehouses(db)
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=40)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw_bb.id, on_hand=20)
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id, brw_bb.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[p.id], contact_id=contact.id, requested_qty=50
    )

    entry = result["stock_availability"][0]
    assert entry["available"] is True
    assert entry["needs_quantity"] is False
    assert entry["requested_qty"] == 50
    _assert_no_quantity_anywhere(result, {40, 20, 60})


def test_availability_no_ignores_disallowed_warehouses(db):
    """B8. 500 sitting in a location the dealer may not see is not their stock."""
    brw, _, dc1 = _three_warehouses(db)
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=40)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=dc1.id, on_hand=500)
    contact = _contact(db)
    _policy_row(db, mode="availability", warehouse_ids=[brw.id], contact=contact)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[p.id], contact_id=contact.id, requested_qty=50
    )

    entry = result["stock_availability"][0]
    assert entry["available"] is False
    _assert_no_quantity_anywhere(result, {40, 500})


def test_last_updated_carried_on_every_mode(db):
    """B10. n8n's `_Data last updated_` footer reads the envelope's
    `last_updated_at`, which the MCP walks out of the body. `compact` and
    `availability` carry no rows, so the payload has to carry it itself or the
    footer silently disappears for exactly the contacts on the new formats."""
    brw, _, _ = _three_warehouses(db)
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=9)
    ledger = _bulk_import_ledger(db, product_id=p.id, warehouse_id=brw.id)
    contact = _contact(db)
    db.flush()

    for mode in ("detailed", "compact", "availability"):
        db.query(StockVisibilityPolicy).filter(
            StockVisibilityPolicy.contact_id == contact.id
        ).delete()
        _policy_row(db, mode=mode, contact=contact)
        db.flush()

        result = StockService(db).list_stock(product_ids=[p.id], contact_id=contact.id)

        assert result["last_updated_at"] == ledger.created_at, mode


def test_policy_composes_with_company_scope(db):
    """B12. Company scope runs first and the policy narrows what is left; a
    Mocha warehouse named on a Sorento contact's policy still yields nothing."""
    seed_mocha(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    sorento_wh = _wh(db, "ZZTBRW")
    mocha_wh = _wh(db, "ZZTMCH", company_id=MOCHA_ID)
    sorento_p = product(db, company_id=DEFAULT_COMPANY_ID)
    mocha_p = product(db, company_id=MOCHA_ID)
    stock(
        db,
        company_id=DEFAULT_COMPANY_ID,
        product_id=sorento_p.id,
        warehouse_id=sorento_wh.id,
        on_hand=10,
    )
    stock(
        db,
        company_id=MOCHA_ID,
        product_id=mocha_p.id,
        warehouse_id=mocha_wh.id,
        on_hand=777,
    )
    contact = _contact(db)
    _policy_row(db, mode="compact", contact=contact)
    db.flush()

    result = StockService(db).list_stock(
        product_ids=[sorento_p.id, mocha_p.id], contact_id=contact.id
    )

    codes = {b["product_code"] for b in result["stock_summary"]}
    assert codes == {sorento_p.product_code}
    totals = [b["total_on_hand"] for b in result["stock_summary"]]
    assert totals == [10]


# ============================================================ route level


@pytest.fixture
def client(db, monkeypatch):
    """A staff caller holding both stock permissions, on the SAME session the
    assertions read."""

    def _override_db():
        yield db

    principal = {"id": str(uuid.uuid4()), "email": "zzt-stock-visibility@test.com"}
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

    async def _override_scope():
        scope = frozenset({DEFAULT_COMPANY_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _override_scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in {READ_PERM, WRITE_PERM},
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_requested_qty_validation(client, db):
    """B9. A demand of 0 or less is not a question anyone asked; 422 rather than
    an accidental "yes, we have stock"."""
    contact = _contact(db)
    _policy_row(db, mode="availability", contact=contact)
    db.flush()

    for bad in (0, -5):
        response = client.get(
            "/api/v1/inventory/stock/balance",
            params={"contact_id": contact.id, "requested_qty": bad},
        )
        assert response.status_code == 422, bad


def test_response_model_declares_blocks(client, db):
    """B11. `response_model` silently drops undeclared fields, so the blocks are
    asserted on the SCHEMA and on a real response body."""
    from app.schemas.inventory import StockBalanceListResponse

    declared = set(StockBalanceListResponse.model_fields)
    assert {
        "stock_visibility",
        "stock_summary",
        "stock_availability",
        "last_updated_at",
    } <= declared

    brw, _, _ = _three_warehouses(db)
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=brw.id, on_hand=12)
    contact = _contact(db)
    _policy_row(db, mode="compact", contact=contact)
    db.flush()

    body = client.get(
        "/api/v1/inventory/stock/balance",
        params={"product_ids": p.id, "contact_id": contact.id},
    ).json()

    assert body["data"] == []
    assert body["stock_visibility"]["mode"] == "compact"
    assert body["stock_summary"][0]["total_on_hand"] == 12


# ============================================================ C. CRUD API


def test_contact_policy_upsert(client, db):
    """C1. Second PUT REPLACES the warehouse list; merging would make removing a
    location impossible."""
    brw, brw_bb, dc1 = _three_warehouses(db)
    contact = _contact(db)
    db.flush()

    first = client.put(
        f"{BASE}/contacts/{contact.id}",
        json={"mode": "compact", "warehouse_ids": [brw.id, brw_bb.id]},
    )
    assert first.status_code == 200
    body = first.json()
    assert body["override"]["mode"] == "compact"
    assert [w["code"] for w in body["override"]["warehouses"]] == ["ZZTBRW", "ZZTBRW-BB"]
    assert body["effective"]["source"] == "contact"

    second = client.put(
        f"{BASE}/contacts/{contact.id}",
        json={"mode": "availability", "warehouse_ids": [dc1.id]},
    )
    assert [w["code"] for w in second.json()["override"]["warehouses"]] == ["ZZTDC1"]
    assert second.json()["effective"]["mode"] == "availability"
    assert (
        db.query(StockVisibilityPolicy)
        .filter(StockVisibilityPolicy.contact_id == contact.id)
        .count()
        == 1
    )


def test_contact_policy_get_shows_the_inherited_tier(client, db):
    """The card has to name where the policy comes from, so an inheriting tier
    answers with the tier above it and a null override."""
    contact = _contact(db)
    dealer = _access_type(db, unique_code("dealer")[:50], "Dealer")
    _tag(db, contact, dealer)
    _policy_row(db, mode="availability", access_type=dealer)
    db.flush()

    body = client.get(f"{BASE}/contacts/{contact.id}").json()

    assert body["override"] is None
    assert body["effective"]["mode"] == "availability"
    assert body["effective"]["source"] == "access_type"
    assert body["effective"]["source_label"] == "Dealer"


def test_contact_policy_delete_falls_back(client, db):
    """C2. DELETE answers with the tier the contact falls back to, so the card
    re-renders the inherited policy without a second round trip."""
    contact = _contact(db)
    dealer = _access_type(db, unique_code("dealer")[:50], "Dealer")
    _tag(db, contact, dealer)
    _policy_row(db, mode="availability", access_type=dealer)
    _policy_row(db, mode="compact", contact=contact)
    db.flush()

    response = client.delete(f"{BASE}/contacts/{contact.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["override"] is None
    assert body["effective"]["mode"] == "availability"
    assert body["effective"]["source"] == "access_type"
    assert (
        db.query(StockVisibilityPolicy)
        .filter(StockVisibilityPolicy.contact_id == contact.id)
        .count()
        == 0
    )


def test_access_type_policy_roundtrip(client, db):
    """One dealer row is what makes the roll-out scale: every contact tagged
    `dealer` inherits it, so the access-type tier needs the same three verbs."""
    brw, _, dc1 = _three_warehouses(db)
    dealer = _access_type(db, unique_code("dealer")[:50], "Dealer")
    db.flush()

    saved = client.put(
        f"{BASE}/access-types/{dealer.code}",
        json={"mode": "availability", "warehouse_ids": [brw.id, dc1.id]},
    ).json()
    assert saved["effective"]["mode"] == "availability"
    assert saved["effective"]["source"] == "access_type"
    assert saved["effective"]["source_label"] == "Dealer"

    dropped = client.delete(f"{BASE}/access-types/{dealer.code}").json()
    assert dropped["override"] is None
    assert dropped["effective"]["source"] == "default"


def test_default_policy_routes(client, db):
    """The default tier is the floor: its override is always present and equals
    the effective policy, and there is no DELETE to leave the chain footless."""
    body = client.get(f"{BASE}/default").json()
    assert body["override"] == body["effective"]
    assert body["effective"]["source"] == "default"

    saved = client.put(f"{BASE}/default", json={"mode": "compact", "warehouse_ids": None}).json()
    assert saved["effective"]["mode"] == "compact"
    assert saved["override"]["warehouses"] is None

    assert client.delete(f"{BASE}/default").status_code == 405


def test_policy_validation(client, db):
    """C3. Unknown access type -> 404 (the row would dangle); a mode outside the
    three or a warehouse that does not exist -> 422."""
    contact = _contact(db)
    db.flush()

    unknown_type = client.put(
        f"{BASE}/access-types/ZZT-NO-SUCH-CODE",
        json={"mode": "compact", "warehouse_ids": None},
    )
    assert unknown_type.status_code == 404

    bad_mode = client.put(
        f"{BASE}/contacts/{contact.id}",
        json={"mode": "summary", "warehouse_ids": None},
    )
    assert bad_mode.status_code == 422

    bad_warehouse = client.put(
        f"{BASE}/contacts/{contact.id}",
        json={"mode": "compact", "warehouse_ids": [str(uuid.uuid4())]},
    )
    assert bad_warehouse.status_code == 422

    unknown_contact = client.put(
        f"{BASE}/contacts/ZZT-NO-SUCH-CONTACT",
        json={"mode": "compact", "warehouse_ids": None},
    )
    assert unknown_contact.status_code == 404


def test_single_default_row(client, db):
    """C6. Postgres NULLs are distinct, so a plain UNIQUE would let a second
    default row in and the resolution chain would pick one at random."""
    from sqlalchemy.exc import IntegrityError

    _policy_row(db, mode="detailed")
    db.flush()
    with pytest.raises(IntegrityError):
        _policy_row(db, mode="compact")
        db.flush()
    db.rollback()


def test_a_row_is_exactly_one_tier(db):
    """The CHECK behind the three-tier chain: a row naming both a contact and an
    access type has no defined precedence."""
    from sqlalchemy.exc import IntegrityError

    contact = _contact(db)
    dealer = _access_type(db, unique_code("dealer")[:50], "Dealer")
    db.flush()
    with pytest.raises(IntegrityError):
        _policy_row(db, mode="compact", contact=contact, access_type=dealer)
        db.flush()
    db.rollback()


def test_effective_external(client, db):
    """C4. n8n's preflight convenience, reachable with the integration key's
    act-as principal rather than a staff JWT."""
    workspace = _workspace(db, "364817")
    contact = _contact(db, respond_io_id="55443322", workspace=workspace)
    _policy_row(db, mode="compact", contact=contact)
    db.flush()

    body = client.get(
        f"{BASE}/effective",
        params={"contact_id": "55443322", "space_id": "364817"},
    ).json()

    assert body["mode"] == "compact"
    assert body["source"] == "contact"


def test_effective_is_reachable_without_a_staff_jwt(db, monkeypatch):
    """C4, the half the shared fixture hides: `/effective` must accept the
    API-key principal. Only `get_current_user_or_api_key` is overridden here, so
    a route guarded by the JWT-only `require_permission` would 401."""

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user_or_api_key] = lambda: {
        "id": str(uuid.uuid4()),
        "email": "zzt-integration@test.com",
    }
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug == READ_PERM,
    )
    try:
        response = TestClient(app).get(f"{BASE}/effective")
        assert response.status_code == 200
        assert response.json()["source"] == "default"
    finally:
        app.dependency_overrides.clear()


def test_policy_rbac(db, monkeypatch):
    """C5. Reads need view, writes need edit, and no credential at all is 401 -
    not 403, which would send an operator to the roles screen for nothing."""
    contact = _contact(db)
    db.flush()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        anonymous = TestClient(app)
        assert anonymous.get(f"{BASE}/contacts/{contact.id}").status_code == 401
        assert (
            anonymous.put(
                f"{BASE}/contacts/{contact.id}",
                json={"mode": "compact", "warehouse_ids": None},
            ).status_code
            == 401
        )

        principal = {"id": str(uuid.uuid4()), "email": "zzt-reader@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
        monkeypatch.setattr(
            UserPermissionService,
            "check_user_has_permission",
            lambda self, uid, slug: slug == READ_PERM,
        )
        reader = TestClient(app)
        assert reader.get(f"{BASE}/contacts/{contact.id}").status_code == 200
        assert (
            reader.put(
                f"{BASE}/contacts/{contact.id}",
                json={"mode": "compact", "warehouse_ids": None},
            ).status_code
            == 403
        )
        assert reader.delete(f"{BASE}/contacts/{contact.id}").status_code == 403
    finally:
        app.dependency_overrides.clear()


# ---- the warehouse `segment` filter the "Dealer pool" preset needs ----------


def test_warehouses_segment_filter(client, db):
    """The preset's only caller. `warehouses.segment` and `WarehouseResponse.segment`
    already existed; without the filter the FE would have to page the whole master
    and filter client-side, which is what the no-capped-dropdown rule forbids."""
    _wh(db, "ZZTBRW", segment="dealer")
    _wh(db, "ZZTMWH", segment="dealer")
    _wh(db, "ZZTBRW-BB", segment="project")
    db.flush()

    body = client.get(
        "/api/v1/inventory/warehouses/",
        params={"segment": "dealer", "is_active": "true", "limit": 200},
    ).json()

    codes = {row["warehouse_code"] for row in body["data"]}
    assert codes == {"ZZTBRW", "ZZTMWH"}
