"""COMBO-SEED-FLYER follow-up 2: `scripts/oneoff/remove_flyer_seed_duplicates.py` (red tests, written first).

UAC: documentation/plans/dealer-kit/combo-seed-flyer-acceptance-criteria.md, AC-D1 to AC-D5.
Line shape (AC-D2): `<VERDICT> | <host> | <flyer name> | owner: <names> | <details>`.
Each test builds what prod had: the owner's combo made by hand, then the importer (--strict --apply,
no aka) made the flyer-named duplicate beside it.
"""
from __future__ import annotations

import io
import json
import uuid
from decimal import Decimal

import pytest

from app.models.accessory import ProductComboAccessory
from app.models.audit import AuditLog
from app.models.base import company_scope, set_company_scope
from app.models.dealer_kit import ComboTagTemplate, TagTemplate
from app.models.dealer_kit import TagTemplateVersion
from app.models.product import Product
from app.models.product_combo import ProductCombo, ProductComboPart
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha
from tests._pg_fixture import blank_session

OWNER_USER = "11111111-2222-3333-4444-555555555555"
VERDICTS = ("DELETE", "KEEP", "NO DUPLICATE", "NO OWNER COMBO")


def _cleanup_script():
    from scripts.oneoff import remove_flyer_seed_duplicates as script

    return script


def _importer():
    from scripts import import_product_combos as script

    return script


@pytest.fixture()
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


def _prod(db, code, company_id=DEFAULT_COMPANY_ID):
    row = product(db, company_id=company_id, code=code)
    row.list_price = Decimal("100.00")
    db.flush()
    db.commit()
    return row


def _write(tmp_path, entries):
    path = tmp_path / f"seed-{uuid.uuid4().hex[:6]}.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def _entry(host, name, part, **extra):
    return {"id": f"{host}-{name}", "host_code": host, "combo_name": name, "page": 1,
            "components": [{"code": part, "role": "Part"}], **extra}


def _import(db, tmp_path, entries, company="SRT"):
    out = io.StringIO()
    code = _importer().main(
        ["--file", str(_write(tmp_path, entries)), "--report", str(tmp_path / f"r-{uuid.uuid4().hex[:6]}.csv"),
         "--company", company, "--strict", "--apply"],
        db=db, out=out,
    )
    assert code == 0, out.getvalue()


def _owner_combo(db, host_code, name="OWNER PACK"):
    host = db.query(Product).filter(Product.product_code == host_code).one()
    row = ProductCombo(id=str(uuid.uuid4()), host_product_id=host.id, name=name,
                       created_by=OWNER_USER, company_id=host.company_id) \
        if hasattr(ProductCombo, "company_id") else \
        ProductCombo(id=str(uuid.uuid4()), host_product_id=host.id, name=name, created_by=OWNER_USER)
    db.add(row)
    db.commit()
    return row


def _combos(db, host_code, name=None):
    db.expire_all()
    with company_scope(db, None):
        host = db.query(Product).filter(Product.product_code == host_code).one()
        query = db.query(ProductCombo).filter(ProductCombo.host_product_id == host.id)
        if name is not None:
            query = query.filter(ProductCombo.name == name)
        return query.all()


def _parts_of(db, combo_id):
    with company_scope(db, None):
        return db.query(ProductComboPart).filter(ProductComboPart.combo_id == combo_id).count()


def _counts(db):
    db.expire_all()
    with company_scope(db, None):
        return tuple(db.query(m).count() for m in (ProductCombo, ProductComboPart, ProductComboAccessory, AuditLog))


def _audit_ids(db):
    db.expire_all()
    with company_scope(db, None):
        return {row.id for row in db.query(AuditLog).all()}


def _lines(text):
    found = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.split(" | ")]
        if len(cells) >= 4 and cells[0] in VERDICTS:
            found.append((cells[0], cells[1], cells[2], cells[3], " | ".join(cells[4:])))
    return found


def _line(text, name):
    hits = [row for row in _lines(text) if row[2] == name]
    assert len(hits) == 1, f"one line for {name!r}, got {_lines(text)} in {text!r}"
    return hits[0]


def _cleanup(db, tmp_path, *extra, apply=False, company="SRT", host="ZZRH1", part="ZZRP1", name="H + P"):
    seed = _write(tmp_path, [_entry(host, name, part, aka=["OWNER PACK"])])
    argv = ["--file", str(seed), "--company", company, *extra]
    if apply:
        argv.append("--apply")
    out = io.StringIO()
    code = _cleanup_script().main(argv, db=db, out=out)
    return code, out.getvalue()


def _setup(db, tmp_path, host="ZZRH1", part="ZZRP1", company_id=DEFAULT_COMPANY_ID, company="SRT", with_owner=True):
    """Host + part, the owner's combo, then the importer's flyer duplicate "H + P" (no aka)."""
    _prod(db, host, company_id)
    _prod(db, part, company_id)
    owner = _owner_combo(db, host) if with_owner else None
    _import(db, tmp_path, [_entry(host, "H + P", part)], company=company)
    dup = _combos(db, host, "H + P")
    assert len(dup) == 1
    return owner, dup[0]


# --------------------------------------------------------------------------- AC-D2 / AC-D4


def test_ac_d2_d4_dry_run_names_the_delete_and_writes_nothing(db, tmp_path):
    _cleanup_script()
    _setup(db, tmp_path)
    before = _counts(db)
    code, out = _cleanup(db, tmp_path)
    assert code == 0, out
    verdict, host, name, owner, details = _line(out, "H + P")
    assert (verdict, host) == ("DELETE", "ZZRH1")
    assert owner == "owner: OWNER PACK"
    assert _counts(db) == before
    assert len(_combos(db, "ZZRH1", "H + P")) == 1


def test_ac_d4_apply_deletes_only_the_duplicate_and_is_idempotent(db, tmp_path):
    _cleanup_script()
    owner, dup = _setup(db, tmp_path)
    dup_id, owner_id = dup.id, owner.id
    with company_scope(db, None):
        db.add(ProductComboPart(id=str(uuid.uuid4()), combo_id=owner_id,
                                part_product_id=db.query(Product).filter(Product.product_code == "ZZRP1").one().id))
        db.commit()
    owner_parts = _parts_of(db, owner_id)
    audit_before = _audit_ids(db)
    code, out = _cleanup(db, tmp_path, apply=True)
    assert code == 0, out
    assert _line(out, "H + P")[0] == "DELETE"
    assert _combos(db, "ZZRH1", "H + P") == []
    assert _parts_of(db, dup_id) == 0
    assert [c.id for c in _combos(db, "ZZRH1", "OWNER PACK")] == [owner_id]
    assert _parts_of(db, owner_id) == owner_parts
    now = _audit_ids(db)
    assert audit_before <= now, "an audit row that existed before was removed"
    assert len(now - audit_before) >= 1, "the delete is not audited"
    after = _counts(db)
    code2, out2 = _cleanup(db, tmp_path, apply=True)
    assert code2 == 0, out2
    assert _line(out2, "H + P")[0] == "NO DUPLICATE"
    assert _counts(db) == after


# --------------------------------------------------------------------------- AC-D3


def test_ac_d3_touched_by_a_user_is_kept(db, tmp_path):
    _cleanup_script()
    _, dup = _setup(db, tmp_path)
    with company_scope(db, None):
        mine = db.query(AuditLog).filter(AuditLog.entity_id == dup.id).first()
        assert mine is not None, "the importer left no audit row on the duplicate"
        db.add(AuditLog(id=str(uuid.uuid4()), entity_type=mine.entity_type, entity_id=dup.id, action="UPDATE",
                        user_id=OWNER_USER, actor_type="user", job_id=None,
                        old_values={"sell_price": None}, new_values={"sell_price": "9.00"}))
        db.commit()
    before = _counts(db)
    code, out = _cleanup(db, tmp_path, apply=True)
    verdict, _h, _n, _o, details = _line(out, "H + P")
    assert verdict == "KEEP"
    assert "user" in details.lower() or "audit" in details.lower() or "touched" in details.lower()
    assert len(_combos(db, "ZZRH1", "H + P")) == 1
    assert _counts(db) == before


def test_ac_d3_created_by_set_is_kept(db, tmp_path):
    _cleanup_script()
    _, dup = _setup(db, tmp_path)
    with company_scope(db, None):
        row = db.query(ProductCombo).filter(ProductCombo.id == dup.id).one()
        row.created_by = OWNER_USER
        db.commit()
    code, out = _cleanup(db, tmp_path, apply=True)
    verdict, _h, _n, _o, details = _line(out, "H + P")
    assert verdict == "KEEP"
    assert "created_by" in details or "created by" in details.lower()
    assert len(_combos(db, "ZZRH1", "H + P")) == 1


def test_ac_d3_in_use_by_a_tag_template_link_is_kept(db, tmp_path):
    _cleanup_script()
    _, dup = _setup(db, tmp_path)
    doc = {"layers": [], "width_mm": 10, "height_mm": 10}
    with company_scope(db, None):
        template = TagTemplate(name="ZZR tpl", family="sink_combo", doc=doc, print_size={"width_mm": 10, "height_mm": 10})
        db.add(template)
        db.flush()
        db.add(TagTemplateVersion(template_id=template.id, version_no=1, doc=doc, print_size=template.print_size))
        db.add(ComboTagTemplate(id=str(uuid.uuid4()), combo_id=dup.id, template_id=template.id))
        db.commit()
    code, out = _cleanup(db, tmp_path, apply=True)
    verdict, _h, _n, _o, details = _line(out, "H + P")
    assert verdict == "KEEP"
    assert "template" in details.lower()
    assert len(_combos(db, "ZZRH1", "H + P")) == 1


# --------------------------------------------------------------------------- AC-D2


def test_ac_d2_no_owner_combo_leaves_the_flyer_combo(db, tmp_path):
    _cleanup_script()
    _setup(db, tmp_path, with_owner=False)
    before = _counts(db)
    code, out = _cleanup(db, tmp_path, apply=True)
    assert code == 0, out
    assert _line(out, "H + P")[0] == "NO OWNER COMBO"
    assert len(_combos(db, "ZZRH1", "H + P")) == 1
    assert _counts(db) == before


# --------------------------------------------------------------------------- AC-D5


def test_ac_d5_another_company_is_never_touched(db, tmp_path):
    _cleanup_script()
    mocha = seed_mocha(db)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
    _setup(db, tmp_path, host="ZZRH1", part="ZZRP1")
    # The same names in Mocha (other host and part codes, so no code collides across companies).
    _prod(db, "ZZRH2", MOCHA_ID)
    _prod(db, "ZZRP2", MOCHA_ID)
    _owner_combo(db, "ZZRH2")
    _import(db, tmp_path, [_entry("ZZRH2", "H + P", "ZZRP2")], company=mocha.code)
    assert len(_combos(db, "ZZRH2", "H + P")) == 1
    seed = _write(tmp_path, [_entry("ZZRH1", "H + P", "ZZRP1", aka=["OWNER PACK"]),
                             _entry("ZZRH2", "H + P", "ZZRP2", aka=["OWNER PACK"])])
    out = io.StringIO()
    code = _cleanup_script().main(["--file", str(seed), "--company", "SRT", "--apply"], db=db, out=out)
    assert code == 0, out.getvalue()
    assert _combos(db, "ZZRH1", "H + P") == []
    assert len(_combos(db, "ZZRH2", "H + P")) == 1
    assert len(_combos(db, "ZZRH2", "OWNER PACK")) == 1
    assert not any(row[1] == "ZZRH2" and row[0] == "DELETE" for row in _lines(out.getvalue()))
