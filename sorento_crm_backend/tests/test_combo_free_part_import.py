"""COMBO-FREE-PART, the seed importer: a free item whose code is one of the combo's parts loads
as that catalogue product (loose and --strict), never as a name-matched library card and never
dropped as "already a part". Plan: `documentation/plans/dealer-kit/PLAN-combo-free-part-09nov.md`.
Written test-FIRST. Synthetic names only.
"""
from __future__ import annotations

import json

from app.models.accessory import ProductComboAccessory
from app.models.base import company_scope
from tests import test_import_product_combos as loose
from tests import test_import_product_combos_strict as strict
from tests.test_import_product_combos import catalogue, db, photos  # noqa: F401  (fixtures)
from tests.test_product_combos import _part, storage  # noqa: F401  (fake storage fixture)


def _free_rows(db, combo_id):
    db.expire_all()
    with company_scope(db, None):
        return [
            (r.item_product_id, r.accessory_id)
            for r in db.query(ProductComboAccessory)
            .filter(ProductComboAccessory.combo_id == combo_id)
            .order_by(ProductComboAccessory.sort_order)
            .all()
        ]


# --------------------------------------------------------------------------- seed import, loose



def test_loose_import_links_a_free_item_that_is_a_part_as_that_product(
    db, catalogue, photos, tmp_path, storage
):
    """Second load of the flyer, the combo already holding its parts and an emptied free list:
    a free item whose code is a part is that catalogue product, not a name-matched library card."""
    entries = json.loads(loose.SEED.read_text())
    entries[0]["free_items"] = [{"code": "ZZTM1", "label": "Mirror"}]
    loose._run_with_seed(db, tmp_path, photos, entries, apply=True)
    combo = loose._combo(db, "ZZT 3 in 1", "ZZTH1")
    mirror = catalogue["ZZTM1"]
    with company_scope(db, None):
        db.query(ProductComboAccessory).filter(ProductComboAccessory.combo_id == combo.id).delete()
        db.commit()

    loose._run_with_seed(db, tmp_path, photos, entries, apply=True)
    assert _free_rows(db, combo.id) == [(mirror.id, None)]


# --------------------------------------------------------------------------- seed import, --strict


def test_strict_import_creates_a_combo_whose_free_item_is_one_of_its_parts(db, tmp_path):
    strict._prod(db, "ZZQH8")
    tap = strict._prod(db, "ZZQT8")
    entries = [
        strict._entry("ZZQH8", "Pack", 1, components=[{"code": "ZZQT8", "role": "Tap"}],
                      free_items=[{"kind": "product", "code": "ZZQT8", "label": "Tap"}]),
    ]
    _, out = strict._run(db, tmp_path, entries, apply=True)
    verdict, _h, _n, _p, details = strict._line(out, "Pack")
    assert verdict == "CREATE", (verdict, details)
    [combo] = strict._combos(db, "ZZQH8", "Pack")
    assert set(strict._parts(db, combo)) == {"ZZQT8"}
    assert _free_rows(db, combo.id) == [(tap.id, None)]


def test_strict_import_keeps_a_free_item_that_is_already_a_part_of_the_existing_combo(db, tmp_path):
    strict._prod(db, "ZZQH9")
    tap = strict._prod(db, "ZZQT9")
    combo = strict._existing(db, "ZZQH9", "Pack")
    with company_scope(db, None):
        _part(db, combo, tap)
        db.commit()
    entries = [
        strict._entry("ZZQH9", "Pack", 1, components=[{"code": "ZZQT9", "role": "Tap"}], free_items=[{"kind": "product", "code": "ZZQT9", "label": "Tap"}]),
    ]
    _, out = strict._run(db, tmp_path, entries, apply=True)
    verdict, _h, _n, _p, details = strict._line(out, "Pack")
    assert "already a part" not in details, details
    assert _free_rows(db, combo.id) == [(tap.id, None)]
