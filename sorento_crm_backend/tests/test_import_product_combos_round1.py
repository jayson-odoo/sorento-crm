"""PRICETAG-COMBO-RENDER fix round 1 (L2, L3) for `scripts/import_product_combos.py`."""
from __future__ import annotations

from decimal import Decimal

from tests import _ptag_combo_seed as seed
from tests import _ptag_shapes_seed as shapes
from tests.test_import_product_combos_reseed import (  # noqa: F401  (fixtures and helpers)
    _combo,
    _parts,
    _run,
    catalogue,
    db,
    entry,
    s1_entry,
    s3_entry,
)

D = Decimal


def _mark_no_sp(db, product):
    from app.models.product import Brand

    db.get(Brand, product.brand_id).no_promo_selling_price = True
    db.commit()


# --------------------------------------------------------------------------- L2: per part


def test_a_no_selling_price_part_gets_no_option_sp_or_topup_on_a_normal_host(db, catalogue, tmp_path):
    _mark_no_sp(db, catalogue["SRTKT1863SS"])
    _mark_no_sp(db, catalogue[shapes.S1_UPGRADE])
    groups = [("Kitchen tap", [{"code": c, "sp": 100} for c in shapes.S1_OPTIONS])]
    e = entry("S1", shapes.S1_HOST, "ZZT S1", groups=groups, topups=[{"code": shapes.S1_UPGRADE, "topup": 150}], sp=2000)
    _code, _out, rows = _run(db, tmp_path, [e], "--apply")
    parts = _parts(db, _combo(db, "ZZT S1", shapes.S1_HOST))
    assert parts["SRTKT1862SS"].sell_price == D("100.00"), "a normal brand part keeps its price"
    assert parts["SRTKT1863SS"].sell_price is None, "this part's own brand has no selling price"
    assert parts[shapes.S1_UPGRADE].topup_amount is None
    assert _combo(db, "ZZT S1", shapes.S1_HOST).sell_price == D("2000.00"), "the host's brand is normal"
    assert "price not loaded: no selling price brand" in rows["S1"]["price_note"]


def test_update_clears_a_combo_sp_an_earlier_load_left_on_a_no_selling_price_host(db, catalogue, tmp_path):
    host = catalogue[shapes.S3_HOST]
    seed.combo(
        db, host, "ZZT S3",
        parts=[{"product": catalogue[c], "group": "Tap colour", "sell_price": D("80.00")} for c in shapes.S3_OPTIONS],
        sell_price=D("800.00"), list_price=D("900.00"),
    )
    db.commit()
    _mark_no_sp(db, host)
    _code, _out, dry = _run(db, tmp_path, [s3_entry(lp=900, sp=800)])
    assert "selling price" in dry["S3"]["differences"] and "none" in dry["S3"]["differences"]
    _run(db, tmp_path, [s3_entry(lp=900, sp=800)], "--apply")
    assert _combo(db, "ZZT S3", shapes.S3_HOST).sell_price == D("800.00"), "bare apply never clears"
    _code, _out, rows = _run(db, tmp_path, [s3_entry(lp=900, sp=800)], "--apply", "--update")
    combo = _combo(db, "ZZT S3", shapes.S3_HOST)
    assert combo.sell_price is None and combo.list_price == D("900.00")
    assert all(p.sell_price is None for p in _parts(db, combo).values())
    assert "price not loaded: no selling price brand" in rows["S3"]["price_note"]


# --------------------------------------------------------------------------- L3: seed shape


def test_a_bad_seed_entry_is_reported_and_skipped_not_a_crash(db, catalogue, tmp_path):
    bad_name = s3_entry()
    bad_name["id"] = "BAD1"
    bad_name["combo_name"] = 5
    bad_list = s3_entry()
    bad_list["id"] = "BAD2"
    bad_list["components"] = "not a list"
    too_long = s3_entry()
    too_long["id"] = "BAD3"
    too_long["combo_description"] = "x" * 5000
    for flags in ((), ("--apply",)):
        code, _out, rows = _run(db, tmp_path, ["a string", bad_name, bad_list, too_long, s3_entry()], *flags)
        assert code == 0
        assert rows["S3"]["status"] in {"new", "created", "matches"}
        for bad in ("BAD1", "BAD2", "BAD3"):
            assert rows[bad]["status"] == "invalid_entry" and rows[bad]["notes"]
        assert rows[""]["status"] == "invalid_entry"
    assert _combo(db, "ZZT S3", shapes.S3_HOST) is not None


def test_a_title_only_entry_is_still_read(db, catalogue, tmp_path):
    e = s3_entry()
    e["title"] = e.pop("combo_name")
    _code, _out, rows = _run(db, tmp_path, [e])
    assert rows["S3"]["status"] == "new"


# --------------------------------------------------------------------------- F3: links persist


def test_apply_link_templates_commits_the_links(db, catalogue, tmp_path):
    from app.models.base import company_scope
    from app.models.dealer_kit import ComboTagTemplate
    from tests.test_import_product_combos_reseed import _template_with

    fits = _template_with(db, "ZZT main", {"kind": "main"})
    db.commit()
    _run(db, tmp_path, [s3_entry()], "--apply", "--link-templates")
    # What a second connection would see: anything the run left uncommitted is gone.
    db.rollback()
    db.expire_all()
    combo = _combo(db, "ZZT S3", shapes.S3_HOST)
    with company_scope(db, None):
        linked = {r.template_id for r in db.query(ComboTagTemplate).filter_by(combo_id=combo.id).all()}
    assert linked == {fits}


# --------------------------------------------------------------------------- F3: unsure is never pruned


def test_update_keeps_a_discontinued_part_the_seed_lists_and_does_not_report_it_removed(db, catalogue, tmp_path):
    host = catalogue[shapes.S1_HOST]
    seed.combo(
        db, host, "ZZT S1",
        parts=[{"product": catalogue[c], "group": "Kitchen tap"} for c in shapes.S1_OPTIONS]
        + [{"product": catalogue[shapes.S1_UPGRADE], "is_upgrade": True}],
    )
    catalogue["SRTKT1892SS"].is_discontinued = True
    db.commit()
    _code, _out, dry = _run(db, tmp_path, [s1_entry()])
    assert dry["S1"]["status"] == "unsure"
    assert "SRTKT1892SS" in dry["S1"]["discontinued"]
    assert "removed SRTKT1892SS" not in dry["S1"]["differences"]
    _run(db, tmp_path, [s1_entry()], "--apply", "--update")
    assert "SRTKT1892SS" in _parts(db, _combo(db, "ZZT S1", shapes.S1_HOST)), "the existing part stays"


def test_update_does_not_prune_an_unsure_combo_even_for_a_part_the_seed_dropped(db, catalogue, tmp_path):
    host = catalogue[shapes.S3_HOST]
    seed.combo(
        db, host, "ZZT S3",
        parts=[{"product": catalogue[c], "group": "Tap colour"} for c in shapes.S3_OPTIONS]
        + [{"product": catalogue["SRTWT6203-GM"]}],
    )
    db.commit()
    e = s3_entry(unsure="price smudged")
    _run(db, tmp_path, [e], "--apply", "--update")
    assert "SRTWT6203-GM" in _parts(db, _combo(db, "ZZT S3", shapes.S3_HOST))
