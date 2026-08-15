"""Raw-SQL + binding-endpoint company-scope tests (Wave-2a gap closure).

The central ``do_orm_execute`` filter only covers ORM SELECTs. This module pins
the hand-written enforcement added for the paths that bypass it:

  - AC-I* / Group I: ``company_sql_predicate`` four-state fragment, and the
    ``variant_link_service`` raw ``text()`` product queries scoped by it (a variant
    must never link across companies).
  - AC-G1/G2 / Group G: the n8n binding endpoints scope the target-entity match to
    the bound attachment's company — a company-A attachment must NOT bind a
    same-coded product owned by company B (product_code is globally unique, so the
    realistic leak is "bind the ONE product that lives in another company").
  - AC-I3: ``POST /lookup/resolve`` reads ``contact_id`` + ``space_id`` from the
    BODY (not query params) and pins the session scope to the contact's companies.

NOT THE WHOLE RAW-SQL SURFACE. This module pins the paths listed above only. In
particular the entity resolver's trigram / phrase probes are scoped by their own
local ``_company_scope_sql`` (plus the ``_attach_company_info`` backstop) and are
pinned by ``tests/test_resolve_entity_company_scope.py``, ``test_rag_company_scope.py``
and ``test_embedding_company_scope.py``, NOT here. A reader who takes this file's
"gap closure" framing as evidence that the resolver is still unscoped has already
been wrong once, and filed a live-leak report for something fixed by 709ef9910.

Live-DB tests run inside a rolled-back SAVEPOINT against the local Postgres dev DB
and seed products/attachments via raw INSERT (bypassing ORM audit + auto-stamp) so
seeding is scope-independent and never commits real data. All rows carry a
``zzrawscope`` marker and are keyed by two throwaway company ids.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.base import UNSET, get_company_scope, set_company_scope
from app.models.company import Company
from app.services.company_scope import register_company_scope_listeners
from app.services.company_scope_sql import company_sql_predicate

# The scope listeners are installed at app/worker startup; install explicitly so
# this file enforces the same ORM filter when run in isolation.
register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


# --------------------------------------------------------------------------- #
# company_sql_predicate — four-state fragment (no DB)                          #
# --------------------------------------------------------------------------- #
def _stub(scope):
    s = SimpleNamespace(info={})
    set_company_scope(s, scope)
    return s


def test_predicate_none_is_empty_fragment():
    frag, params = company_sql_predicate(_stub(None))
    assert frag == ""
    assert params == {}


def test_predicate_unset_is_false():
    frag, params = company_sql_predicate(_stub(UNSET))
    assert frag == "1=0"
    assert params == {}


def test_predicate_empty_frozenset_is_false():
    frag, params = company_sql_predicate(_stub(frozenset()))
    assert frag == "1=0"
    assert params == {}


def test_predicate_frozenset_is_in_clause_with_params():
    cid = str(uuid.uuid4())
    frag, params = company_sql_predicate(_stub(frozenset({cid})))
    assert "company_id IN (:cscope0)" == frag
    assert params == {"cscope0": cid}


def test_predicate_shared_unset_is_null_only():
    frag, params = company_sql_predicate(_stub(UNSET), shared=True)
    assert frag == "company_id IS NULL"
    assert params == {}


def test_predicate_shared_frozenset_is_null_or_in():
    cid = str(uuid.uuid4())
    frag, params = company_sql_predicate(_stub(frozenset({cid})), shared=True, column="a.company_id")
    assert frag == "(a.company_id IS NULL OR a.company_id IN (:cscope0))"
    assert params == {"cscope0": cid}


# --------------------------------------------------------------------------- #
# Live-DB fixtures                                                             #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    session.begin_nested()  # SAVEPOINT rolled back at teardown
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _seed_category_uom(db: Session, company_id: str, suffix: str):
    cat_id = str(uuid.uuid4())
    uom_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO product_categories (id, category_code, category_name, is_active, company_id, created_at) "
            "VALUES (:id, :code, :name, true, :cid, now())"
        ),
        {"id": cat_id, "code": f"ZZRAW-CAT-{suffix}", "name": f"zzrawscope cat {suffix}", "cid": company_id},
    )
    db.execute(
        text(
            "INSERT INTO units_of_measure (id, uom_code, uom_name, is_active, company_id, created_at) "
            "VALUES (:id, :code, :name, true, :cid, now())"
        ),
        {"id": uom_id, "code": f"ZZRAW-UOM-{suffix}", "name": f"zzrawscope uom {suffix}", "cid": company_id},
    )
    return cat_id, uom_id


def _seed_product(db: Session, company_id: str, code: str, cat_id: str, uom_id: str) -> str:
    pid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO products "
            "(id, product_code, product_name, category_id, base_uom_id, list_price, currency, "
            " is_active, has_serial_tracking, has_batch_tracking, variant_link_manual, is_discontinued, "
            " company_id, created_at) "
            "VALUES (:id, :code, :name, :cat, :uom, 100, 'MYR', true, false, false, false, false, :cid, now())"
        ),
        {"id": pid, "code": code, "name": code, "cat": cat_id, "uom": uom_id, "cid": company_id},
    )
    return pid


@pytest.fixture()
def two_companies(db: Session):
    suffix = uuid.uuid4().hex[:8]
    a = Company(id=str(uuid.uuid4()), name=f"ZZRAW A {suffix}", code=f"ZRA{suffix}")
    b = Company(id=str(uuid.uuid4()), name=f"ZZRAW B {suffix}", code=f"ZRB{suffix}")
    db.add_all([a, b])
    db.flush()
    return {"a": a.id, "b": b.id, "suffix": suffix}


# --------------------------------------------------------------------------- #
# Group I — variant_link_service raw SQL is company-scoped                     #
# --------------------------------------------------------------------------- #
def test_derive_parent_stays_in_company(db, two_companies):
    from app.services.variant_link_service import _derive_parent_id

    a, suffix = two_companies["a"], two_companies["suffix"]
    cat, uom = _seed_category_uom(db, a, suffix)
    parent = _seed_product(db, a, f"ZZRAWSOFA{suffix}", cat, uom)
    child = _seed_product(db, a, f"ZZRAWSOFA{suffix}-01", cat, uom)
    db.flush()

    set_company_scope(db, frozenset({a}))
    got = _derive_parent_id(db, child, f"ZZRAWSOFA{suffix}-01")
    assert str(got) == parent  # same-company parent resolves


def test_derive_parent_never_crosses_company(db, two_companies):
    """A child in company A whose only prefix-parent lives in company B must NOT
    link to it under company-A scope (the leak the raw-SQL predicate closes)."""
    from app.services.variant_link_service import _derive_parent_id

    a, b, suffix = two_companies["a"], two_companies["b"], two_companies["suffix"]
    cat_a, uom_a = _seed_category_uom(db, a, f"{suffix}A")
    cat_b, uom_b = _seed_category_uom(db, b, f"{suffix}B")
    # Parent "DESK" exists ONLY in company B; child "DESK-01" only in company A.
    parent_b = _seed_product(db, b, f"ZZRAWDESK{suffix}", cat_b, uom_b)
    child_a = _seed_product(db, a, f"ZZRAWDESK{suffix}-01", cat_a, uom_a)
    db.flush()

    # Under company-A scope: B's parent is invisible -> no link.
    set_company_scope(db, frozenset({a}))
    assert _derive_parent_id(db, child_a, f"ZZRAWDESK{suffix}-01") is None

    # Sanity: with no company scope (all companies) the prefix parent IS found,
    # proving the None result above is the scope filter, not a bad prefix.
    set_company_scope(db, None)
    assert str(_derive_parent_id(db, child_a, f"ZZRAWDESK{suffix}-01")) == parent_b


# --------------------------------------------------------------------------- #
# Group G — binding endpoint scopes product match to attachment's company      #
# --------------------------------------------------------------------------- #
def _seed_attachment(db: Session, company_id, suffix: str, tag: str) -> str:
    aid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO attachments (id, original_filename, stored_filename, file_path, is_deleted, "
            " company_id, uploaded_at, created_at) "
            "VALUES (:id, :fn, :fn, :fp, false, :cid, now(), now())"
        ),
        {"id": aid, "fn": f"zzrawscope-{suffix}-{tag}.pdf", "fp": f"/zzrawscope/{suffix}-{tag}.pdf",
         "cid": company_id},
    )
    return aid


def test_product_query_under_attachment_scope_excludes_other_company(db, two_companies):
    from app.models.product import Product

    a, b, suffix = two_companies["a"], two_companies["b"], two_companies["suffix"]
    cat_b, uom_b = _seed_category_uom(db, b, suffix)
    code = f"ZZRAWWIDGET{suffix}"
    _seed_product(db, b, code, cat_b, uom_b)  # product owned by company B only
    db.flush()

    # Pinned to company A (the attachment's company): B's product is invisible.
    set_company_scope(db, frozenset({a}))
    assert db.query(Product).filter(Product.product_code.ilike(f"%{code.lower()}%")).first() is None
    # Control: with all-companies scope it IS found.
    set_company_scope(db, None)
    assert db.query(Product).filter(Product.product_code.ilike(f"%{code.lower()}%")).first() is not None


def test_bind_endpoint_rejects_cross_company_product(db, two_companies):
    """AC-G2 end-to-end: a company-A attachment cannot bind company B's product."""
    from fastapi import HTTPException

    from app.api.v1.external.product_attachments import create_product_attachment
    from app.schemas.external.attachments import ProductAttachmentLinkRequestAny

    a, b, suffix = two_companies["a"], two_companies["b"], two_companies["suffix"]
    cat_b, uom_b = _seed_category_uom(db, b, suffix)
    code = f"ZZRAWBIND{suffix}"
    _seed_product(db, b, code, cat_b, uom_b)  # product owned by company B
    att_a = _seed_attachment(db, a, suffix, "a")  # attachment owned by company A
    db.flush()

    # Resolver would have set None (X-API-Key, no contact) so the attachment loads.
    set_company_scope(db, None)
    payload = ProductAttachmentLinkRequestAny(attachment_id=att_a, product_code=code)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_product_attachment(payload, current_user={"id": "system"}, db=db))
    assert exc.value.status_code == 400
    assert "product_code" in str(exc.value.detail).lower()


# --------------------------------------------------------------------------- #
# AC-I3 — lookup/resolve reads scope from the BODY                             #
# --------------------------------------------------------------------------- #
def test_lookup_resolve_scopes_from_body(db, two_companies, monkeypatch):
    import app.api.v1.lookup as lookup_mod
    from app.models.lookup import LookupOption, LookupSet
    from app.schemas.lookup import LookupResolveRequest

    a, suffix = two_companies["a"], two_companies["suffix"]

    # Minimal (non-scoped) lookup set + option so resolve returns a hit.
    s = LookupSet(set_key=f"zzraw_set_{suffix}", name="zzrawscope set")
    db.add(s)
    db.flush()
    db.add(LookupOption(set_id=s.id, value="CHAIR-01", label="Chair"))
    db.flush()

    # The route builds ContactAccessTypeService(db); stub the company resolution
    # so we don't need to seed Respond contact/workspace rows.
    monkeypatch.setattr(
        lookup_mod.ContactAccessTypeService,
        "resolve_contact_company_ids",
        lambda self, contact_id, space_id: [a],
    )

    set_company_scope(db, None)
    body = LookupResolveRequest(
        set_key=f"zzraw_set_{suffix}", raw="CHAIR-01", contact_id="rid-1", space_id="space-1"
    )
    # X-API-Key/MCP principal -> body contact params DO re-scope (AC-I3).
    result = asyncio.run(
        lookup_mod.resolve(
            body, current_user={"id": "system", "auth_method": "api_key"}, db=db
        )
    )

    assert result.value == "CHAIR-01"
    assert get_company_scope(db) == frozenset({a})  # scope pinned from the body

    # L3: a logged-in JWT user with the SAME forged body params is NOT re-scoped —
    # their active-company scope is preserved (no cross-company escalation).
    set_company_scope(db, None)
    asyncio.run(
        lookup_mod.resolve(
            body, current_user={"id": "u1", "auth_method": "jwt"}, db=db
        )
    )
    assert get_company_scope(db) is None  # JWT scope untouched by body params


def test_lookup_resolve_without_contact_leaves_scope(db, two_companies, monkeypatch):
    import app.api.v1.lookup as lookup_mod
    from app.models.lookup import LookupOption, LookupSet
    from app.schemas.lookup import LookupResolveRequest

    suffix = two_companies["suffix"]
    s = LookupSet(set_key=f"zzraw_set2_{suffix}", name="zzrawscope set2")
    db.add(s)
    db.flush()
    db.add(LookupOption(set_id=s.id, value="CHAIR-01", label="Chair"))
    db.flush()

    # No contact params in the body -> resolver's scope is left untouched.
    set_company_scope(db, None)
    body = LookupResolveRequest(set_key=f"zzraw_set2_{suffix}", raw="CHAIR-01")
    asyncio.run(lookup_mod.resolve(body, current_user={"id": "system"}, db=db))
    assert get_company_scope(db) is None
