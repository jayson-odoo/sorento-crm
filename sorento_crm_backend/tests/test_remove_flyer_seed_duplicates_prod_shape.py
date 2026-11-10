"""COMBO-SEED-FLYER follow-up 2: the exact prod shape reported 9 Nov for host SRTBF11834 (made-up codes).

An OLD combo from an earlier importer run, edited once by a person, plus a later flyer duplicate "(p21)".
Guard tests: green once the script honours AC-D3/D3b.
"""
from __future__ import annotations

import io
import uuid

from app.models.audit import AuditLog
from app.models.base import company_scope
from app.models.product_combo import ProductComboPart

from tests import test_remove_flyer_seed_duplicates as base
from tests.test_remove_flyer_seed_duplicates import (
    OWNER_USER,
    _cleanup_script,
    _combos,
    _counts,
    _import,
    _line,
    _lines,
    _prod,
    _write,
)

db = base.db
HOST, OLD, DUP = "ZZB834", "ZZB834 + ZZM502", "ZZB834 + ZZM502 (p21)"
PARTS = [f"ZZBP{i}" for i in range(8)]


def _comp(codes):
    return [{"code": c, "role": "Part"} for c in codes]


def _e(name, page, codes, **extra):
    return {"id": f"{HOST}-{name}", "host_code": HOST, "combo_name": name, "page": page,
            "components": _comp(codes), **extra}


def _build(db, tmp_path):
    """OLD (8 parts, importer rows + one user edit), then the flyer duplicate (7 parts, importer rows)."""
    _prod(db, HOST)
    for code in PARTS:
        _prod(db, code)
    _import(db, tmp_path, [_e(OLD, 9, PARTS)])
    old = _combos(db, HOST, OLD)[0]
    with company_scope(db, None):
        etype = db.query(AuditLog).filter(AuditLog.entity_id == old.id).first().entity_type
        db.add(AuditLog(id=str(uuid.uuid4()), entity_type=etype, entity_id=old.id, action="UPDATE",
                        user_id=OWNER_USER, actor_type="user", job_id=None,
                        old_values={"a": 1}, new_values={"a": 2}))
        db.commit()
    _import(db, tmp_path, [_e(DUP, 21, PARTS[:7])])
    dup = _combos(db, HOST, DUP)[0]
    return old, dup


def _old_state(db, old_id):
    db.expire_all()
    with company_scope(db, None):
        audit = {r.id for r in db.query(AuditLog).filter(
            (AuditLog.entity_id == old_id) | (AuditLog.root_entity_id == old_id)).all()}
        parts = db.query(ProductComboPart).filter(ProductComboPart.combo_id == old_id).count()
    return audit, parts


def _run(db, tmp_path, entries, apply=True):
    argv = ["--file", str(_write(tmp_path, entries)), "--company", "SRT"] + (["--apply"] if apply else [])
    out = io.StringIO()
    assert _cleanup_script().main(argv, db=db, out=out) == 0, out.getvalue()
    return out.getvalue()


def test_prod_shape_owner_seed_deletes_p21_and_leaves_the_old_combo(db, tmp_path):
    _cleanup_script()
    old, dup = _build(db, tmp_path)
    assert _old_state(db, old.id)[1] == 8
    audit_before, parts_before = _old_state(db, old.id)
    dup_id = dup.id
    out = _run(db, tmp_path, [
        _e(DUP, 21, PARTS[:7], aka=[f"{OLD} (p9)", OLD]),
        _e(f"{OLD} (p20)", 20, PARTS[:7]),
    ])
    verdict, host, _n, owner, _d = _line(out, DUP)
    assert (verdict, host) == ("DELETE", HOST)
    assert owner == f"owner: {OLD}"
    assert _combos(db, HOST, DUP) == []
    with company_scope(db, None):
        assert db.query(ProductComboPart).filter(ProductComboPart.combo_id == dup_id).count() == 0
    survivors = _combos(db, HOST, OLD)
    assert [c.id for c in survivors] == [old.id] and survivors[0].name == OLD
    assert _old_state(db, old.id) == (audit_before, parts_before)
    assert not any(row[2] == OLD for row in _lines(out)), "the old combo must never be named as the flyer combo"


def test_prod_shape_main_seed_deletes_nothing(db, tmp_path):
    _cleanup_script()
    old, dup = _build(db, tmp_path)
    state = _old_state(db, old.id)
    before = _counts(db)
    out = _run(db, tmp_path, [
        _e(OLD, 20, PARTS[:7]),
        _e(DUP, 21, PARTS[:7], aka=[f"{OLD} (p9)"]),
    ])
    assert _line(out, DUP)[0] == "NO OWNER COMBO"
    assert not any(row[0] == "DELETE" for row in _lines(out))
    assert _counts(db) == before
    assert len(_combos(db, HOST, DUP)) == 1
    assert [c.id for c in _combos(db, HOST, OLD)] == [old.id]
    assert _old_state(db, old.id) == state
