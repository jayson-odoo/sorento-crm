"""ACCESS-SHEET-FIXES fix 4b: `scripts/fix_access_sheet_mocha_brands.py`.

Owner ruling 27 Oct: "give back every brands for all the mocha contacts". The 27 Oct access-sheet
import narrowed some contacts from every brand to the Sorento dealer brands although they hold
MCH. The script finds them by the import's own audit (`contact.access_sheet`, brands moved from
"every brand" to a list) and the MCH membership they hold now, and resets them to every brand.
Dry run by default; `--apply` writes in one transaction with an audit row per contact.
Postgres only (``blank_session``), every row seeded here.
"""
from __future__ import annotations

import uuid

import pytest

import scripts.fix_access_sheet_mocha_brands as fix  # noqa: E402 - red until the script exists

from app.models.access import RespondContact
from app.models.audit import AuditLog
from app.models.base import set_company_scope
from app.models.company import Company, RespondContactCompany
from app.services import audit_service
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def w(db):
    mch = str(uuid.uuid4())
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, mch}))
    db.add(Company(id=mch, name="ZZT Mocha Co", code="MCH"))
    db.flush()
    return {"srt": DEFAULT_COMPANY_ID, "mch": mch, "brands": [str(uuid.uuid4()), str(uuid.uuid4())]}


def _contact(db, n, *, companies, brand_ids, audit_brands=("every brand", ["ZZT A", "ZZT B"])):
    row = RespondContact(id=str(uuid.uuid4()), phone_number=f"601999{n:05d}", name=f"ZZT Fix {n}", brand_ids=brand_ids)
    db.add(row)
    db.flush()
    for company_id in companies:
        db.add(RespondContactCompany(respond_contact_id=row.id, company_id=company_id))
    if audit_brands is not None:
        before, after = audit_brands
        audit_service.record(
            db, event="contact.access_sheet", entity_type="respond_contacts", entity_id=row.id,
            old_values={"brands": before, "companies": ["SRT"]}, new_values={"brands": after, "companies": ["SRT", "MCH"]},
        )
    db.flush()
    return row.id


def _brands(db, cid):
    db.expire_all()
    return db.query(RespondContact.brand_ids).filter(RespondContact.id == cid).scalar()


def test_dry_run_lists_narrowed_mocha_contacts_and_writes_nothing(db, w):
    hit = _contact(db, 1, companies=[w["srt"], w["mch"]], brand_ids=w["brands"])
    found = fix.repair(db, apply=False)
    assert [f["contact_id"] for f in found] == [hit]
    assert sorted(_brands(db, hit)) == sorted(w["brands"])
    assert not db.query(AuditLog).filter(AuditLog.event == fix.EVENT).count()


def test_apply_resets_them_to_every_brand_with_an_audit_row_each(db, w):
    hit = _contact(db, 1, companies=[w["mch"]], brand_ids=w["brands"])
    fix.repair(db, apply=True)
    assert _brands(db, hit) is None
    (row,) = db.query(AuditLog).filter(AuditLog.event == fix.EVENT, AuditLog.entity_id == hit).all()
    assert sorted(row.old_values["brand_ids"]) == sorted(w["brands"]) and row.new_values == {"brand_ids": None}


def test_contacts_outside_the_rule_are_left_alone(db, w):
    srt_only = _contact(db, 1, companies=[w["srt"]], brand_ids=w["brands"])
    already_all = _contact(db, 2, companies=[w["mch"]], brand_ids=None)
    never_all = _contact(db, 3, companies=[w["mch"]], brand_ids=w["brands"], audit_brands=(["ZZT A"], ["ZZT A", "ZZT B"]))
    no_audit = _contact(db, 4, companies=[w["mch"]], brand_ids=w["brands"], audit_brands=None)
    assert fix.repair(db, apply=True) == []
    assert sorted(_brands(db, srt_only)) == sorted(w["brands"])
    assert _brands(db, already_all) is None
    assert sorted(_brands(db, never_all)) == sorted(w["brands"])
    assert sorted(_brands(db, no_audit)) == sorted(w["brands"])
