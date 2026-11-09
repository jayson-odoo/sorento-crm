"""COMBO-SEED-FLYER review round 1: AC-6 subset, AC-15b, AC-15c, AC-18b (all under --strict)."""
from __future__ import annotations

import uuid

from app.models.accessory import Accessory, ProductComboAccessory
from app.models.base import company_scope
from app.models.product_combo import ProductComboPart
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests.test_import_product_combos_strict import (  # noqa: F401  (db is a fixture)
    _combos, _entry, _existing, _line, _lines, _parts, _prod, _run, db,
)


def _add_part(db, combo, prod):
    with company_scope(db, None):
        db.add(ProductComboPart(id=str(uuid.uuid4()), combo_id=combo.id, part_product_id=prod.id))
        db.commit()


def test_ac_6_existing_with_fewer_parts_is_skip_parts_differ_and_untouched(db, tmp_path):
    _prod(db, "ZZQH1")
    a, _b = _prod(db, "ZZQA1"), _prod(db, "ZZQB1")
    combo = _existing(db, "ZZQH1", "Pack")
    _add_part(db, combo, a)
    entries = [_entry("ZZQH1", "Pack", 1, components=[{"code": "ZZQA1", "role": "A"}, {"code": "ZZQB1", "role": "B"}])]
    _, out = _run(db, tmp_path, entries, apply=True)
    verdict, _h, _n, _p, details = _line(out, "Pack")
    assert verdict == "SKIP" and "parts differ" in details
    assert set(_parts(db, _combos(db, "ZZQH1", "Pack")[0])) == {"ZZQA1"}


def test_ac_15b_discontinued_part_is_not_loaded_but_combo_is_created(db, tmp_path):
    _prod(db, "ZZQH2")
    _prod(db, "ZZQA2")
    d = _prod(db, "ZZQD2")
    d.is_discontinued = True
    db.commit()
    entries = [_entry("ZZQH2", "Pack", 1, components=[{"code": "ZZQA2", "role": "A"}, {"code": "ZZQD2", "role": "D"}])]
    _, dry = _run(db, tmp_path, entries)
    _, out = _run(db, tmp_path, entries, apply=True)
    for text in (dry, out):
        verdict, _h, _n, _p, details = _line(text, "Pack")
        assert verdict == "CREATE" and "not loaded (discontinued): ZZQD2" in details
    assert set(_parts(db, _combos(db, "ZZQH2", "Pack")[0])) == {"ZZQA2"}


def test_ac_15b_discontinued_host_still_creates_with_a_note(db, tmp_path):
    host = _prod(db, "ZZQH3")
    _prod(db, "ZZQA3")
    host.is_discontinued = True
    db.commit()
    entries = [_entry("ZZQH3", "Pack", 1, components=[{"code": "ZZQA3", "role": "A"}])]
    _, out = _run(db, tmp_path, entries, apply=True)
    verdict, _h, _n, _p, details = _line(out, "Pack")
    assert verdict == "CREATE" and "host discontinued" in details
    assert len(_combos(db, "ZZQH3", "Pack")) == 1


def test_ac_15c_free_item_that_is_already_a_part_is_skipped_not_failed(db, tmp_path):
    _prod(db, "ZZQH4")
    p = _prod(db, "ZZQP4")
    with company_scope(db, None):
        lib_id = str(uuid.uuid4())
        db.add(Accessory(id=lib_id, name="WIDGET", company_id=DEFAULT_COMPANY_ID))
        db.commit()
    combo = _existing(db, "ZZQH4", "Pack")
    _add_part(db, combo, p)
    entries = [
        _entry("ZZQH4", "Pack", 1, free_items=[
            {"kind": "product", "code": "ZZQP4", "label": "P"},
            {"kind": "accessory", "label": "WIDGET"},
        ]),
        _entry("ZZQH4", "Second", 2),
    ]
    _, out = _run(db, tmp_path, entries, apply=True)
    verdict, _h, _n, _p, details = _line(out, "Pack")
    assert verdict == "UPDATE" and "already a part: ZZQP4" in details
    with company_scope(db, None):
        rows = db.query(ProductComboAccessory).filter(ProductComboAccessory.combo_id == combo.id).all()
        assert [(r.item_product_id, r.accessory_id) for r in rows] == [(None, lib_id)]
    assert len(_combos(db, "ZZQH4", "Second")) == 1


def test_ac_18b_control_characters_in_names_cannot_forge_a_line(db, tmp_path):
    _prod(db, "ZZQH5")
    _existing(db, "ZZQH5", "Evil\nUNMATCHED | FAKE | x | p1 | missing: y")
    _, out = _run(db, tmp_path, [_entry("ZZQH5", "Brand New", 1)])
    assert not any(line.startswith("UNMATCHED | FAKE") for line in out.splitlines())
    assert [v for v, *_ in _lines(out)] == ["CREATE"]
    details = _line(out, "Brand New")[4]
    assert "Evil" in details and "\n" not in details


def test_ac_18b_exit_code_is_nonzero_when_a_host_fails(db, tmp_path, monkeypatch):
    from app.services.product_combo_service import ProductComboService

    _prod(db, "ZZQH6")
    clean_code, _ = _run(db, tmp_path, [_entry("ZZQH6", "Fine", 1)])
    assert clean_code == 0
    real = ProductComboService.create

    def create(self, host_id, name, *args, **kwargs):
        if name == "Boom":
            raise RuntimeError("boom")
        return real(self, host_id, name, *args, **kwargs)

    monkeypatch.setattr(ProductComboService, "create", create)
    code, out = _run(db, tmp_path, [_entry("ZZQH6", "Boom", 2)], apply=True)
    assert _line(out, "Boom")[0].startswith("FAILED")
    assert code != 0
