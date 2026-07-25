"""Backend suite for the variant manual-curation feature.

Covers docs/plans/PLAN-variant-manual-curation.md §9 / §10:

Endpoints (auth = get_current_user JWT):
  - PUT    /api/v1/master-data/products/{id}/variant-parent   (set / change / attach-child)
  - DELETE /api/v1/master-data/products/{id}/variant-parent   (unlink / remove-child)
  - POST   /api/v1/master-data/products/{id}/variant-reset     (reset to auto)
  - GET    /api/v1/master-data/products?variant_filter=...     (base|variant|all + refs/count)

Service (D1 — "manual wins, sticky"):
  - reconcile_variant_links does NOT re-derive a manual row's own parent but STILL
    adopts its auto orphans.
  - _adopt_orphans does NOT steal a manual child.
  - backfill main()/derive_parents skips manual rows (0 changes on re-run) while
    still letting them be candidate parents.

Runs against a blank copy of the real Postgres schema, rolled back per test. The
pg-only string functions ``regexp_replace`` / ``left`` used by the derivation SQL
are native here (they were python shims under the old sqlite bind). The backfill
session binds to the SAME connection as ``db`` (create_savepoint) so its committed
UPDATEs are visible to the test's assertions within the single rolled-back
transaction.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.product_service import ProductService
from app.services.variant_link_service import (
    reconcile_variant_links,
    _adopt_orphans,
)
from tests._pg_fixture import blank_session


@pytest.fixture()
def db():
    """A blank Postgres schema, rolled back after the test.

    Was an in-memory sqlite bind with python shims for regexp_replace / left --
    both are native on Postgres, so the derivation SQL runs against the real
    dialect here. category_id / base_uom_id are NOT NULL foreign keys, so the
    shared parent rows are seeded up front (Postgres enforces what sqlite did not).
    """
    with blank_session() as session:
        session.add(
            ProductCategory(id=_CAT, category_code="ZZT-VMC-CAT", category_name="ZZT")
        )
        session.add(UnitOfMeasure(id=_UOM, uom_code="ZZT-VMC-UOM", uom_name="Each"))
        session.flush()
        yield session


@pytest.fixture()
def engine(db):
    """The Connection the session is bound to.

    Tests attach a statement-count listener to it and bind a second (backfill)
    session to it, so both sessions observe the same rolled-back transaction.
    """
    return db.get_bind()


# --------------------------------------------------------------------------- #
# Seed helpers
# --------------------------------------------------------------------------- #
_CAT = str(uuid.uuid4())
_UOM = str(uuid.uuid4())


def _mk(db, code, *, parent_id=None, manual=False, commit=True) -> str:
    pid = str(uuid.uuid4())
    p = Product(
        id=pid,
        product_code=code,
        product_name=code,
        category_id=_CAT,
        base_uom_id=_UOM,
        list_price=0,
        variant_of_id=parent_id,
        variant_link_manual=manual,
    )
    db.add(p)
    if commit:
        db.commit()
    return pid


def _parent_of(db, pid):
    db.expire_all()
    val = db.query(Product.variant_of_id).filter(Product.id == pid).scalar()
    return str(val) if val is not None else None


def _manual_of(db, pid) -> bool:
    db.expire_all()
    return bool(db.query(Product.variant_link_manual).filter(Product.id == pid).scalar())


# --------------------------------------------------------------------------- #
# TestClient wiring
# --------------------------------------------------------------------------- #
_USER = {"id": str(uuid.uuid4()), "email": "curator@example.com"}


@pytest.fixture()
def client(db):
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def anon_client(db):
    """No auth override — the real get_current_user / or_api_key deps run, so an
    unauthenticated request is rejected before the route body."""
    from app.main import app
    from app.database import get_db

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


BASE = "/api/v1/master-data/products"


# =========================================================================== #
# 1. SET PARENT — PUT /{id}/variant-parent
# =========================================================================== #
def test_set_parent_happy_path_uuid(client, db):
    parent = _mk(db, "SRTKT71SS")
    child = _mk(db, "SRTKT71SS-BL")

    r = client.put(f"{BASE}/{child}/variant-parent", json={"parent_id": parent})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["variant_link_manual"] is True
    assert body["is_variant"] is True
    assert body["variant_of"]["id"] == parent
    assert body["variant_of"]["product_code"] == "SRTKT71SS"
    # persisted
    assert _parent_of(db, child) == parent
    assert _manual_of(db, child) is True


def test_set_parent_accepts_product_code_for_both_ids(client, db):
    _mk(db, "SRTKT80SS")
    _mk(db, "SRTKT80SS-GM")

    # path = child code, body = parent code (neither is a UUID)
    r = client.put(
        f"{BASE}/SRTKT80SS-GM/variant-parent", json={"parent_id": "SRTKT80SS"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["variant_of"]["product_code"] == "SRTKT80SS"
    assert body["variant_link_manual"] is True


def test_set_parent_missing_parent_id_400(client, db):
    child = _mk(db, "ABC-1")
    r = client.put(f"{BASE}/{child}/variant-parent", json={})
    assert r.status_code == 400
    assert "parent_id is required" in r.text


def test_set_parent_blank_parent_id_400(client, db):
    child = _mk(db, "ABC-2")
    r = client.put(f"{BASE}/{child}/variant-parent", json={"parent_id": "   "})
    assert r.status_code == 400
    assert "parent_id is required" in r.text


def test_set_parent_self_parent_400(client, db):
    p = _mk(db, "SELF-1")
    r = client.put(f"{BASE}/{p}/variant-parent", json={"parent_id": p})
    assert r.status_code == 400
    assert "A product cannot be a variant of itself" in r.text


def test_set_parent_cycle_simple_400(client, db):
    a = _mk(db, "CYCA")
    b = _mk(db, "CYCB")
    # B -> A (legit)
    assert client.put(f"{BASE}/{b}/variant-parent", json={"parent_id": a}).status_code == 200
    # Now A -> B would close a cycle.
    r = client.put(f"{BASE}/{a}/variant-parent", json={"parent_id": b})
    assert r.status_code == 400
    assert "would create a variant cycle" in r.text


def test_set_parent_cycle_deeper_descendant_400(client, db):
    # Chain P <- C1 <- C2 (C2 variant_of C1 variant_of P). Setting P's parent to
    # its own grandchild C2 must be rejected (walk C2's ancestors -> P found).
    p = _mk(db, "DEEPP")
    c1 = _mk(db, "DEEPP-A", parent_id=None)
    c2 = _mk(db, "DEEPP-A-B", parent_id=None)
    # link via the endpoint so state is consistent
    assert client.put(f"{BASE}/{c1}/variant-parent", json={"parent_id": p}).status_code == 200
    assert client.put(f"{BASE}/{c2}/variant-parent", json={"parent_id": c1}).status_code == 200

    r = client.put(f"{BASE}/{p}/variant-parent", json={"parent_id": c2})
    assert r.status_code == 400
    assert "would create a variant cycle" in r.text


def test_set_parent_missing_parent_404(client, db):
    child = _mk(db, "NOPARENT-1")
    r = client.put(
        f"{BASE}/{child}/variant-parent", json={"parent_id": str(uuid.uuid4())}
    )
    assert r.status_code == 404
    assert "Parent product not found" in r.text


def test_set_parent_missing_product_404(client, db):
    parent = _mk(db, "REALPARENT")
    r = client.put(
        f"{BASE}/{uuid.uuid4()}/variant-parent", json={"parent_id": parent}
    )
    assert r.status_code == 404
    assert "Product not found" in r.text


def test_set_parent_auth_denied_anonymous(anon_client, db):
    child = _mk(db, "AUTH-1")
    parent = _mk(db, "AUTH-0")
    r = anon_client.put(f"{BASE}/{child}/variant-parent", json={"parent_id": parent})
    assert r.status_code in (401, 403)


def test_set_parent_auth_denied_readonly_api_key(db):
    """A read-only api-key principal (system) passes the module guard but the
    write route requires a JWT user (get_current_user) -> rejected."""
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user_or_api_key

    parent = _mk(db, "AK-0")
    child = _mk(db, "AK-1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": "system"}
    try:
        c = TestClient(app)
        r = c.put(f"{BASE}/{child}/variant-parent", json={"parent_id": parent})
        assert r.status_code in (401, 403)
    finally:
        app.dependency_overrides.clear()


# =========================================================================== #
# 2. UNLINK — DELETE /{id}/variant-parent
# =========================================================================== #
def test_unlink_happy_path(client, db):
    parent = _mk(db, "UNL-0")
    child = _mk(db, "UNL-0-BL", parent_id=parent)

    r = client.delete(f"{BASE}/{child}/variant-parent")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["variant_of"] is None
    assert body["is_variant"] is False
    assert body["variant_link_manual"] is True
    assert _parent_of(db, child) is None
    assert _manual_of(db, child) is True


def test_unlink_missing_product_404(client, db):
    r = client.delete(f"{BASE}/{uuid.uuid4()}/variant-parent")
    assert r.status_code == 404
    assert "Product not found" in r.text


def test_unlink_auth_denied_anonymous(anon_client, db):
    child = _mk(db, "UNLAUTH-1")
    r = anon_client.delete(f"{BASE}/{child}/variant-parent")
    assert r.status_code in (401, 403)


# =========================================================================== #
# 3. RESET — POST /{id}/variant-reset
# =========================================================================== #
def test_reset_re_derives_via_reconcile(client, db):
    # Base + a code-derivable variant, but hand-linked (manual=true).
    parent = _mk(db, "RST100")
    child = _mk(db, "RST100-BL", parent_id=parent, manual=True)
    assert _manual_of(db, child) is True

    r = client.post(f"{BASE}/{child}/variant-reset")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["variant_link_manual"] is False
    # reconcile re-derives the code-prefix parent
    assert body["is_variant"] is True
    assert body["variant_of"]["product_code"] == "RST100"
    assert _manual_of(db, child) is False
    assert _parent_of(db, child) == parent


def test_reset_persists_flag_even_when_derivation_is_noop(client, db):
    # A base with NO derivable parent: reconcile yields no self-change, but the
    # manual flag clear must still persist (committed before reconcile).
    p = _mk(db, "ZZLONELY999", manual=True)
    assert _manual_of(db, p) is True

    r = client.post(f"{BASE}/{p}/variant-reset")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["variant_link_manual"] is False
    assert body["variant_of"] is None
    assert _manual_of(db, p) is False


def test_reset_missing_product_404(client, db):
    r = client.post(f"{BASE}/{uuid.uuid4()}/variant-reset")
    assert r.status_code == 404
    assert "Product not found" in r.text


def test_reset_auth_denied_anonymous(anon_client, db):
    p = _mk(db, "RSTAUTH-1")
    r = anon_client.post(f"{BASE}/{p}/variant-reset")
    assert r.status_code in (401, 403)


# =========================================================================== #
# 4. SERVICE-LEVEL — D1 manual-wins guards
# =========================================================================== #
def test_reconcile_skips_manual_own_parent_but_adopts_orphans(db):
    # base ZZM100; a MANUAL child hand-pointed at a WRONG parent; plus an AUTO
    # orphan that should be adopted by the base on reconcile.
    base = _mk(db, "ZZM100")
    wrong = _mk(db, "ZZWRONG")
    manual_child = _mk(db, "ZZM100-BL", parent_id=wrong, manual=True)
    auto_orphan = _mk(db, "ZZM100-GM", parent_id=None, manual=False)

    res = reconcile_variant_links(db, base)
    assert res["found"] is True
    # base itself has no parent
    assert res["parent_id"] is None
    # the auto orphan was adopted...
    assert _parent_of(db, auto_orphan) == base
    assert res["orphans_adopted"] == 1
    # ...but the manual child's (deliberately wrong) parent is left untouched.
    assert _parent_of(db, manual_child) == wrong

    # Reconciling the manual row itself does NOT re-derive its own parent.
    res2 = reconcile_variant_links(db, manual_child)
    assert res2["self_changed"] is False
    assert _parent_of(db, manual_child) == wrong


def test_adopt_orphans_does_not_steal_manual_child(db):
    base = _mk(db, "ZZA100")
    manual_child = _mk(db, "ZZA100-BL", parent_id=None, manual=True)
    auto_child = _mk(db, "ZZA100-GM", parent_id=None, manual=False)

    parent_row = db.query(Product).filter(Product.id == base).first()
    changed = _adopt_orphans(db, parent_row)
    db.commit()

    # Only the auto child was adopted; the manual child is never re-pointed.
    assert _parent_of(db, auto_child) == base
    assert _parent_of(db, manual_child) is None
    assert changed == 1


# =========================================================================== #
# 4c. BACKFILL — skips manual rows, still a candidate parent
# =========================================================================== #
def test_backfill_skips_manual_rows(db, engine, monkeypatch, capsys):
    import scripts.backfill_variant_links as bf
    from scripts.backfill_variant_links import derive_parents

    base = _mk(db, "ZZB100")
    # manual child hand-pointed at a wrong parent — backfill must NOT overwrite it.
    wrong = _mk(db, "ZZBWRONG")
    manual_child = _mk(db, "ZZB100-BL", parent_id=wrong, manual=True)
    # an auto orphan that the backfill SHOULD link to the base.
    auto_child = _mk(db, "ZZB100-GM", parent_id=None, manual=False)

    # derive_parents (pure) still treats the base as a candidate parent for BOTH.
    rows = [
        (base, "ZZB100"),
        (wrong, "ZZBWRONG"),
        (manual_child, "ZZB100-BL"),
        (auto_child, "ZZB100-GM"),
    ]
    derived = derive_parents(rows)
    assert derived[auto_child] == base
    assert derived[manual_child] == base  # candidate-parent derivation ignores manual

    # main() must skip the manual row (not overwrite) but fix the auto orphan.
    # Bind to the same connection with create_savepoint so the backfill's commit
    # lands on a savepoint the test session (on that connection) can then read.
    factory = sessionmaker(bind=engine, join_transaction_mode="create_savepoint")
    monkeypatch.setattr(bf, "SessionLocal", factory)
    monkeypatch.setattr("sys.argv", ["backfill_variant_links.py"])
    assert bf.main() == 0
    out = capsys.readouterr().out
    assert "rows changed     : 1" in out  # only the auto orphan

    assert _parent_of(db, auto_child) == base
    assert _parent_of(db, manual_child) == wrong  # untouched

    # Re-run is a no-op for everyone (0 changes) — manual row never overwritten.
    monkeypatch.setattr("sys.argv", ["backfill_variant_links.py"])
    assert bf.main() == 0
    out2 = capsys.readouterr().out
    assert "rows changed     : 0" in out2
    assert _parent_of(db, manual_child) == wrong


# =========================================================================== #
# 5. LIST — variant_filter + parent ref + child count + no N+1
# =========================================================================== #
def test_list_variant_filter_base(client, db):
    base = _mk(db, "LST100")
    _mk(db, "LST100-BL", parent_id=base)

    r = client.get(BASE, params={"variant_filter": "base", "limit": 100})
    assert r.status_code == 200, r.text
    codes = {row["product_code"] for row in r.json()["data"]}
    assert "LST100" in codes
    assert "LST100-BL" not in codes


def test_list_variant_filter_variant(client, db):
    base = _mk(db, "LST200")
    _mk(db, "LST200-BL", parent_id=base)

    r = client.get(BASE, params={"variant_filter": "variant", "limit": 100})
    assert r.status_code == 200, r.text
    codes = {row["product_code"] for row in r.json()["data"]}
    assert "LST200-BL" in codes
    assert "LST200" not in codes


def test_list_variant_filter_all(client, db):
    base = _mk(db, "LST300")
    _mk(db, "LST300-BL", parent_id=base)

    r = client.get(BASE, params={"variant_filter": "all", "limit": 100})
    assert r.status_code == 200, r.text
    codes = {row["product_code"] for row in r.json()["data"]}
    assert {"LST300", "LST300-BL"} <= codes


def test_list_row_exposes_variant_of_and_child_count(client, db):
    base = _mk(db, "LST400")
    _mk(db, "LST400-BL", parent_id=base)
    _mk(db, "LST400-GM", parent_id=base)

    r = client.get(BASE, params={"variant_filter": "all", "limit": 100})
    assert r.status_code == 200, r.text
    by_code = {row["product_code"]: row for row in r.json()["data"]}

    # base row: no parent ref, 2 direct children
    assert by_code["LST400"]["variant_of"] is None
    assert by_code["LST400"]["variant_child_count"] == 2

    # variant row: human-readable parent ref (code + name, no bare UUID surfaced)
    variant = by_code["LST400-BL"]
    assert variant["variant_of"]["product_code"] == "LST400"
    assert variant["variant_of"]["product_name"] == "LST400"
    assert variant["variant_of"]["id"] == base
    assert variant["variant_child_count"] == 0


def test_list_variant_fields_no_n_plus_one(db, engine):
    """`_populate_list_variant_fields` runs a FIXED two queries (one parent-ref,
    one child-count) regardless of page size — proving no per-row N+1."""
    base = _mk(db, "NPL100")
    svc = ProductService(db)

    # Seed both page sets up front (commits expire prior rows, so load fresh below).
    small_ids = [_mk(db, "NPL100-BL", parent_id=base), _mk(db, "NPL100-GM", parent_id=base)]
    large_ids = [
        _mk(db, "NPL100-A", parent_id=base),
        _mk(db, "NPL100-B", parent_id=base),
        _mk(db, "NPL100-C", parent_id=base),
        _mk(db, "NPL100-D", parent_id=base),
    ]

    def _count_selects(ids):
        # Load the page rows fresh (single query) BEFORE arming the counter, so
        # attribute access inside _populate doesn't trigger a post-commit reload
        # (a sqlite expire_on_commit artifact, not a real N+1).
        rows = db.query(Product).filter(Product.id.in_(ids)).all()
        for r in rows:  # touch identity cols so they're not lazily reloaded later
            _ = (r.id, r.variant_of_id)
        counter = {"n": 0}

        @event.listens_for(engine, "after_cursor_execute")
        def _on_exec(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
            if statement.lstrip().upper().startswith("SELECT"):
                counter["n"] += 1

        try:
            svc._populate_list_variant_fields(rows)
        finally:
            event.remove(engine, "after_cursor_execute", _on_exec)
        return counter["n"]

    n_small = _count_selects(small_ids)
    n_large = _count_selects(large_ids)

    assert n_small == n_large == 2  # constant, independent of page size
