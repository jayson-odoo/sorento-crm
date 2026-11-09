"""COMBO-SEED-FLYER: report details found on a real dry run (AC-15, AC-6)."""
from __future__ import annotations

import uuid

from app.models.base import company_scope
from app.models.product import Product
from app.models.product_combo import ProductComboPart

from tests.test_import_product_combos_strict import (  # noqa: F401  (db is a fixture)
    _combos, _entry, _existing, _line, _parts, _prod, _run, db,
)


def test_ac_15_missing_host_names_only_the_host(db, tmp_path):
    _prod(db, "ZZRP1")
    _prod(db, "ZZRF1")
    entries = [
        _entry("ZZRNOHOST", "Pack", 1, components=[{"code": "ZZRP1", "role": "A"}],
               free_items=[{"kind": "product", "code": "ZZRF1", "label": "Tap"}]),
    ]
    _, out = _run(db, tmp_path, entries)
    verdict, _h, _n, _p, details = _line(out, "Pack")
    assert verdict.startswith("UNMATCHED")
    assert "missing: ZZRNOHOST" in details
    assert "ZZRF1" not in details and "ZZRP1" not in details


def test_ac_6_regrouped_choice_label_is_skip_and_named(db, tmp_path):
    _prod(db, "ZZRH2")
    o1, o2 = _prod(db, "ZZRO1"), _prod(db, "ZZRO2")
    combo = _existing(db, "ZZRH2", "Pack")
    with company_scope(db, None):
        for opt in (o1, o2):
            db.add(ProductComboPart(id=str(uuid.uuid4()), combo_id=combo.id, part_product_id=opt.id,
                                    choice_group="TAP"))
        db.commit()
    entries = [
        _entry("ZZRH2", "Pack", 1,
               choice_groups=[{"role": "KITCHEN TAP", "options": [{"code": "ZZRO1"}, {"code": "ZZRO2"}]}]),
    ]
    _, out = _run(db, tmp_path, entries, apply=True)
    verdict, _h, _n, _p, details = _line(out, "Pack")
    assert verdict == "SKIP"
    assert "grouped differently" in details and "parts differ" not in details
    parts = _parts(db, _combos(db, "ZZRH2", "Pack")[0])
    assert {p.choice_group for p in parts.values()} == {"TAP"}
