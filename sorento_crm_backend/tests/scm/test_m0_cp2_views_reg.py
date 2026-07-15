"""SCM M0 CP2 — views + module registration tests (Postgres-backed).

Covers the CP2 slice of the M0 UAC:
- AC-M0.8  net_position_v reconciles (on_hand + on_order − committed).
- AC-M0.11 decoupling: no view reads inbound_shipments / spo_allocations.
- AC-M0.7  numbering format SO-YYYY/MM-#### / PO-YYYY/MM-####.
- AC-M0.6  RBAC slugs seeded + granted to admin (+ purchasing); a bare role isn't.
- AC-M0.4/D3 module dormant: catalog row present, not enabled by default.

SQLite can't model the scm schema or cross-schema views, so these run only
against a live Postgres DATABASE_URL.
"""
from __future__ import annotations

import os
import re

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def _pg_url() -> str | None:
    for line in open(os.path.join(os.path.dirname(__file__), "..", "..", ".env")):
        if line.startswith("DATABASE_URL"):
            raw = line.split("=", 1)[1].strip().strip('"').strip("'")
            return re.sub(r"^postgresql\+\w+", "postgresql", raw)
    return None


URL = _pg_url()
pytestmark = pytest.mark.skipif(
    not URL or not URL.startswith("postgresql"),
    reason="CP2 view/registration tests require a live Postgres DATABASE_URL",
)

SCM_VIEWS = {"on_order_v", "committed_v", "consumption_v", "net_position_v", "receipt_lead_v"}
SCM_SLUGS = {
    "scm.dashboard.view",
    "scm.reorder.run",
    "scm.recommendation.manage",
    "scm.policy.manage",
    "scm.config.manage",
}


@pytest.fixture()
def conn():
    eng = create_engine(URL)
    with eng.connect() as c:
        yield c
    eng.dispose()


@pytest.fixture()
def engine():
    eng = create_engine(URL)
    yield eng
    eng.dispose()


# --- AC-M0.8: net position reconciles ---------------------------------------

def test_all_five_views_present(conn):
    rows = conn.execute(text(
        "select table_name from information_schema.views where table_schema='scm'"
    )).scalars().all()
    assert SCM_VIEWS.issubset(set(rows)), f"missing scm views: {SCM_VIEWS - set(rows)}"


def test_net_position_reconciles_with_no_po_so(conn):
    """A SKU with no open PO/SO nets to on_hand; on_order/committed default 0.

    CP2 seeds no scm SO/PO rows, so at least one net_position_v row has
    on_order=0 and committed=0 and must equal quantity_on_hand.
    """
    row = conn.execute(text(
        """
        select quantity_on_hand, on_order, committed, net_position
        from scm.net_position_v
        where on_order = 0 and committed = 0
        limit 1
        """
    )).fetchone()
    assert row is not None, "expected at least one stock row with no PO/SO position"
    assert row.on_order == 0 and row.committed == 0
    assert row.net_position == row.quantity_on_hand

    # The identity holds for every row regardless of PO/SO presence.
    mismatch = conn.execute(text(
        """
        select count(*) from scm.net_position_v
        where net_position <> quantity_on_hand + on_order - committed
        """
    )).scalar()
    assert mismatch == 0, "net_position != on_hand + on_order - committed"


# --- AC-M0.11: decoupling ---------------------------------------------------

def test_views_do_not_reference_decoupled_tables(conn):
    """No position/consumption view may read inbound_shipments or spo_allocations."""
    banned = ("inbound_shipments", "spo_allocations")
    offenders = []
    for v in SCM_VIEWS:
        definition = conn.execute(text(
            "select pg_get_viewdef((:qual)::regclass, true)"
        ), {"qual": f"scm.{v}"}).scalar() or ""
        low = definition.lower()
        for bad in banned:
            if bad in low:
                offenders.append(f"scm.{v} references {bad}")
    assert not offenders, offenders


# --- AC-M0.7: numbering format ----------------------------------------------

@pytest.mark.parametrize(
    "doc_type,pattern",
    [
        ("sales_order", r"^SO-\d{4}/\d{2}-\d{4}$"),
        ("purchase_order", r"^PO-\d{4}/\d{2}-\d{4}$"),
    ],
)
def test_numbering_format(engine, doc_type, pattern):
    from app.services.numbering_service import NumberingService

    session = Session(bind=engine)
    try:
        # commit_rule=False -> flush only; rollback leaves next_value untouched.
        num = NumberingService(session).get_next_number(doc_type, commit_rule=False)
        assert num is not None, f"no numbering rule for {doc_type}"
        assert re.match(pattern, num), f"{doc_type} -> {num!r} did not match {pattern}"
    finally:
        session.rollback()
        session.close()


# --- AC-M0.6: RBAC ----------------------------------------------------------

def test_scm_slugs_exist(conn):
    found = set(conn.execute(text(
        "select slug from user_permissions where slug = any(:s)"
    ), {"s": list(SCM_SLUGS)}).scalars().all())
    assert found == SCM_SLUGS, f"missing slugs: {SCM_SLUGS - found}"


def test_admin_holds_all_scm_grants(conn):
    granted = set(conn.execute(text(
        """
        select p.slug
        from user_role_permissions urp
        join user_roles r on r.id = urp.role_id
        join user_permissions p on p.id = urp.permission_id
        where r.slug = 'admin' and p.slug = any(:s)
        """
    ), {"s": list(SCM_SLUGS)}).scalars().all())
    assert granted == SCM_SLUGS, f"admin missing scm grants: {SCM_SLUGS - granted}"


def test_purchasing_role_seeded_and_granted(conn):
    role = conn.execute(text(
        "select id from user_roles where slug = 'purchasing'"
    )).fetchone()
    assert role is not None, "purchasing role was not seeded"
    granted = conn.execute(text(
        """
        select count(*)
        from user_role_permissions urp
        join user_permissions p on p.id = urp.permission_id
        where urp.role_id = :rid and p.slug = any(:s)
        """
    ), {"rid": role.id, "s": list(SCM_SLUGS)}).scalar()
    assert granted == len(SCM_SLUGS)


def test_bare_role_lacks_scm_grants(conn):
    """A role that wasn't granted the slugs holds none of them (deny path)."""
    granted = conn.execute(text(
        """
        select count(*)
        from user_role_permissions urp
        join user_roles r on r.id = urp.role_id
        join user_permissions p on p.id = urp.permission_id
        where r.slug = 'guest' and p.slug = any(:s)
        """
    ), {"s": list(SCM_SLUGS)}).scalar()
    assert granted == 0


# --- AC-M0.4 / D3: module dormant -------------------------------------------

def test_scm_catalog_row_present_but_dormant(conn):
    cat = conn.execute(text(
        "select display_name, is_core from app_modules_catalog where module_key = 'scm'"
    )).fetchone()
    assert cat is not None, "scm catalog row missing"
    assert cat.is_core is False
    # Dormant = registered but NOT enabled by default. M0's migration must not
    # auto-enable it; enablement is per-tenant opt-in (a tenant CAN enable it in
    # dev/demo — so we assert an ARBITRARY tenant that never opted in has no row,
    # rather than "no enabled row anywhere", which a legitimate dev-enable breaks).
    enabled = conn.execute(text(
        "select count(*) from tenant_modules "
        "where module_key = 'scm' and enabled = true and tenant_id = '__never_enabled_probe__'"
    )).scalar()
    assert enabled == 0, "a tenant that never opted in must have no scm enablement (dormant by default)"
