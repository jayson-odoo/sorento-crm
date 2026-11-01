"""PRICETAG-COMBO: `scripts/import_product_combos.py` (red tests, written first).

UAC: documentation/plans/dealer-kit/price-tag-combo-template-fields-acceptance-criteria.md
(AC-8.1 to AC-8.9, AC-8.11).

Everything runs through `script.main(argv, db=db, out=StringIO)` on a blank Postgres
schema; every test seeds its own products. The seed is the synthetic
`tests/fixtures/product_combos/seed.json` (made-up codes and prices); photos are tiny
files written to tmp_path; storage is an in-process fake. The script is imported inside
each test so a missing script is one red per test, not one collection error.

Assumed report columns (UAC AC-8.5: "id, status, dropped parts, guess"): header names are
compared lower-cased with spaces turned into underscores.
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.base import company_scope, set_company_scope
from app.models.company import Company
from app.models.dealer_kit import TagTemplate, TagTemplateVersion
from app.models.product_combo import ProductCombo, ProductComboPart
from app.models.resources import Attachment
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha
from tests._pg_fixture import blank_session
from tests.test_product_combos import _jpg_bytes, storage  # noqa: F401  (fake storage fixture)

SEED = Path(__file__).resolve().parent / "fixtures" / "product_combos" / "seed.json"
REPO = Path(__file__).resolve().parents[2]


def _script():
    from scripts import import_product_combos as script

    return script


@pytest.fixture()
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


def _prod(db, code, *, company_id=DEFAULT_COMPANY_ID):
    row = product(db, company_id=company_id, code=code)
    row.list_price = Decimal("100.00")
    db.flush()
    return row


@pytest.fixture()
def catalogue(db):
    """Every product the seed names, except the ones the tests want missing."""
    seed_mocha(db)
    codes = ["ZZTH1", "ZZTH3", "ZZTM1", "ZZTM2", "ZZTBW", "ZZTBB", "ZZTU1"]
    rows = {code: _prod(db, code) for code in codes}
    rows["ZZTMOCHAHOST"] = _prod(db, "ZZTMOCHAHOST", company_id=MOCHA_ID)
    db.commit()
    return rows


@pytest.fixture()
def photos(tmp_path):
    folder = tmp_path / "photos"
    folder.mkdir()
    (folder / "c1.jpg").write_bytes(_jpg_bytes())
    return folder


def _run(db, tmp_path, photos, *extra, apply=False, templates=False):
    report = tmp_path / f"report-{len(list(tmp_path.glob('report-*.csv')))}.csv"
    argv = ["--file", str(SEED), "--photos", str(photos), "--report", str(report), *extra]
    if apply:
        argv.append("--apply")
    if templates:
        argv.append("--templates")
    out = io.StringIO()
    code = _script().main(argv, db=db, out=out)
    rows = []
    if report.exists():
        with open(report, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                rows.append({k.strip().lower().replace(" ", "_"): v for k, v in raw.items()})
    return code, out.getvalue(), rows


def _by_id(rows):
    found = {row["id"]: row for row in rows}
    assert len(found) == len(rows), "one row per seed entry"
    return found


def _combo(db, name, host_code):
    db.expire_all()
    with company_scope(db, None):
        host = _hostrow(db, host_code)
        return (
            db.query(ProductCombo)
            .filter(ProductCombo.host_product_id == host.id, ProductCombo.name == name)
            .first()
        )


def _hostrow(db, code):
    from app.models.product import Product

    with company_scope(db, None):
        return db.query(Product).filter(Product.product_code == code).one()


def _parts(db, combo):
    with company_scope(db, None):
        return {
            part.part_product.product_code: part
            for part in db.query(ProductComboPart).filter(ProductComboPart.combo_id == combo.id).all()
        }


def _count(db, model):
    db.expire_all()
    with company_scope(db, None):
        return db.query(model).count()


# --------------------------------------------------------------------------- AC-8.1


def test_ac_8_1_a_dry_run_is_the_default_and_writes_nothing(db, catalogue, photos, tmp_path, storage):
    attachments_before = _count(db, Attachment)
    code, _out, rows = _run(db, tmp_path, photos, "--company", "SRT", templates=True)
    assert code == 0
    assert _count(db, ProductCombo) == 0
    assert _count(db, ProductComboPart) == 0
    assert _count(db, Attachment) == attachments_before
    assert _count(db, TagTemplate) == 0, "templates are not written on a dry run either"
    assert _count(db, TagTemplateVersion) == 0
    assert storage.objects == {}, "no photo is stored on a dry run"
    assert len(rows) == 4, "the report is still written, one row per seed entry"


def test_ac_8_1_apply_writes_and_a_report_is_always_produced(db, catalogue, photos, tmp_path, storage):
    code, _out, rows = _run(db, tmp_path, photos, apply=True)
    assert code == 0
    assert _count(db, ProductCombo) == 2
    assert len(rows) == 4


# --------------------------------------------------------------------------- AC-8.2


def test_ac_8_2_apply_loads_the_combo_description_free_items_and_cover(
    db, catalogue, photos, tmp_path, storage
):
    _run(db, tmp_path, photos, apply=True)
    combo = _combo(db, "ZZT 3 in 1", "ZZTH1")
    assert combo is not None
    assert combo.description == "Cabinet, mirror and basin set"

    items = combo.free_items.split(", ")
    assert len(items) == 2, combo.free_items
    assert "ZZTTAP1" in items[0] and "Tap" in items[0]
    assert items[0].index("ZZTTAP1") < items[0].index("Tap"), "the code prefixes the label"
    assert items[1] == "Waste", "no code, so the label alone"

    assert combo.image_attachment_id is not None
    assert len(storage.objects) == 1, "the cover went through the storage seam once"


def test_ac_8_2_components_become_fixed_parts_options_share_a_group_topups_are_upgrades(
    db, catalogue, photos, tmp_path, storage
):
    _run(db, tmp_path, photos, apply=True)
    combo = _combo(db, "ZZT 3 in 1", "ZZTH1")
    parts = _parts(db, combo)
    assert set(parts) == {"ZZTM1", "ZZTM2", "ZZTBW", "ZZTBB", "ZZTU1"}

    for code in ("ZZTM1", "ZZTM2"):
        assert parts[code].choice_group is None and parts[code].is_upgrade is False
    for code in ("ZZTBW", "ZZTBB"):
        assert parts[code].choice_group == "Basin" and parts[code].is_upgrade is False
    assert parts["ZZTU1"].is_upgrade is True


# --------------------------------------------------------------------------- AC-8.3


def test_ac_8_3_no_price_is_loaded(db, catalogue, photos, tmp_path, storage):
    _run(db, tmp_path, photos, apply=True)
    with company_scope(db, None):
        combos = db.query(ProductCombo).all()
        parts = db.query(ProductComboPart).all()
    assert combos and parts
    assert all(c.list_price is None and c.sell_price is None for c in combos)
    assert all(p.sell_price is None and p.topup_amount is None for p in parts)


# --------------------------------------------------------------------------- AC-8.4


def test_ac_8_4_a_host_code_with_no_product_is_not_loaded_and_reported(
    db, catalogue, photos, tmp_path, storage
):
    _code, _out, rows = _run(db, tmp_path, photos, apply=True)
    assert _by_id(rows)["C2"]["status"] == "not_loaded_host_missing"
    with company_scope(db, None):
        assert db.query(ProductCombo).filter(ProductCombo.name == "ZZT Orphan").count() == 0


def test_ac_8_4_a_missing_part_or_codeless_component_is_dropped_and_the_combo_still_loads(
    db, catalogue, photos, tmp_path, storage
):
    _code, _out, rows = _run(db, tmp_path, photos, apply=True)
    combo = _combo(db, "ZZT 2 in 1", "ZZTH3")
    assert combo is not None, "the combo loads despite the dropped parts"
    assert set(_parts(db, combo)) == {"ZZTM1"}

    dropped = _by_id(rows)["C3"]["dropped_parts"]
    assert "ZZTGONE" in dropped, "a part code with no product is listed by code"
    assert dropped.strip() != "ZZTGONE", "the codeless component is listed too"
    assert _by_id(rows)["C3"]["status"] != "not_loaded_host_missing"


# --------------------------------------------------------------------------- AC-8.5


def test_ac_8_5_every_guess_is_listed_and_the_report_has_one_row_per_entry(
    db, catalogue, photos, tmp_path, storage
):
    _code, _out, rows = _run(db, tmp_path, photos, apply=True)
    by_id = _by_id(rows)
    assert set(by_id) == {"C1", "C2", "C3", "C4"}
    for row in rows:
        assert set(row) >= {"id", "status", "dropped_parts", "guess"}
    assert by_id["C3"]["guess"] == "read as 2 in 1, the flyer is smudged"
    assert by_id["C1"]["guess"] == ""
    assert by_id["C1"]["dropped_parts"] == ""


# --------------------------------------------------------------------------- AC-8.6


def test_ac_8_6_a_rerun_changes_nothing_already_there(db, catalogue, photos, tmp_path, storage):
    _run(db, tmp_path, photos, apply=True)
    objects_after_first = dict(storage.objects)
    first = _combo(db, "ZZT 3 in 1", "ZZTH1")
    cover = first.image_attachment_id
    parts_before = sorted(_parts(db, first))

    code, _out, _rows = _run(db, tmp_path, photos, apply=True)
    assert code == 0
    assert _count(db, ProductCombo) == 2, "no duplicate combo for host + name"
    again = _combo(db, "ZZT 3 in 1", "ZZTH1")
    assert again.id == first.id
    assert sorted(_parts(db, again)) == parts_before
    assert again.image_attachment_id == cover
    assert storage.objects == objects_after_first, "the picture is not uploaded twice"


def test_ac_8_6_what_marketing_filled_stays_and_missing_parts_are_added_back(
    db, catalogue, photos, tmp_path, storage
):
    extra = _prod(db, "ZZTEXTRA")
    db.commit()
    _run(db, tmp_path, photos, apply=True)

    combo = _combo(db, "ZZT 3 in 1", "ZZTH1")
    with company_scope(db, None):
        combo.description = "Marketing wrote this"
        combo.free_items = "Marketing free items"
        combo.list_price = Decimal("2222.00")
        combo.sell_price = Decimal("1111.00")
        parts = _parts(db, combo)
        parts["ZZTBW"].sell_price = Decimal("222.00")
        db.delete(parts["ZZTM2"])
        db.add(ProductComboPart(combo_id=combo.id, part_product_id=extra.id, sort_order=9))
        db.commit()

    _run(db, tmp_path, photos, apply=True)
    combo = _combo(db, "ZZT 3 in 1", "ZZTH1")
    assert combo.description == "Marketing wrote this"
    assert combo.free_items == "Marketing free items"
    assert combo.list_price == Decimal("2222.00") and combo.sell_price == Decimal("1111.00")
    parts = _parts(db, combo)
    assert parts["ZZTBW"].sell_price == Decimal("222.00")
    assert "ZZTM2" in parts, "a part missing from the combo is added back"
    assert "ZZTEXTRA" in parts, "a part present is never removed"


def test_ac_8_6_an_empty_description_free_items_or_cover_is_filled_but_set_ones_stay(
    db, catalogue, photos, tmp_path, storage
):
    host = _hostrow(db, "ZZTH1")
    with company_scope(db, None):
        db.add(ProductCombo(host_product_id=host.id, name="ZZT 3 in 1", sort_order=0, description="Already here"))
        db.commit()
    _run(db, tmp_path, photos, apply=True)
    combo = _combo(db, "ZZT 3 in 1", "ZZTH1")
    assert combo.description == "Already here", "a description already set stays"
    assert combo.free_items, "the blank free items are filled"
    assert combo.image_attachment_id is not None, "the blank cover is filled"
    assert _count(db, ProductCombo) == 2


def test_ac_8_6_combos_under_other_names_are_not_touched(db, catalogue, photos, tmp_path, storage):
    host = _hostrow(db, "ZZTH1")
    extra = _prod(db, "ZZTEXTRA")
    with company_scope(db, None):
        other = ProductCombo(
            host_product_id=host.id, name="ZZT Other", sort_order=5, description="Mine", free_items="Mine too"
        )
        db.add(other)
        db.flush()
        db.add(ProductComboPart(combo_id=other.id, part_product_id=extra.id, sort_order=0))
        db.commit()
        other_id = other.id

    _run(db, tmp_path, photos, apply=True)

    db.expire_all()
    with company_scope(db, None):
        other = db.query(ProductCombo).filter(ProductCombo.id == other_id).one()
        assert (other.name, other.description, other.free_items) == ("ZZT Other", "Mine", "Mine too")
        assert other.image_attachment_id is None
        assert [p.part_product.product_code for p in other.parts] == ["ZZTEXTRA"]


# --------------------------------------------------------------------------- AC-8.7


def test_ac_8_7_a_missing_photo_file_is_reported_and_the_combo_still_loads(
    db, catalogue, photos, tmp_path, storage
):
    _code, _out, rows = _run(db, tmp_path, photos, apply=True)
    row = _by_id(rows)["C3"]
    assert any("absent.jpg" in value or "photo" in value.lower() for value in row.values()), row
    combo = _combo(db, "ZZT 2 in 1", "ZZTH3")
    assert combo is not None
    assert combo.image_attachment_id is None


# --------------------------------------------------------------------------- AC-8.8


def test_ac_8_8_the_host_is_looked_up_under_the_chosen_companys_scope_only(
    db, catalogue, photos, tmp_path, storage
):
    _code, _out, rows = _run(db, tmp_path, photos, "--company", "SRT", apply=True)
    assert _by_id(rows)["C4"]["status"] == "not_loaded_host_missing"
    with company_scope(db, None):
        assert db.query(ProductCombo).filter(ProductCombo.name == "ZZT Foreign").count() == 0


def test_ac_8_8_a_part_that_exists_only_in_another_company_is_dropped(
    db, catalogue, photos, tmp_path, storage
):
    foreign = _prod(db, "ZZTFOREIGNPART", company_id=MOCHA_ID)
    assert foreign is not None
    entries = json.loads(SEED.read_text())
    entries[0]["components"].append({"code": "ZZTFOREIGNPART", "role": "Odd", "dimensions": "", "lp": 1})
    seed_path = tmp_path / "scoped.json"
    seed_path.write_text(json.dumps(entries))
    report = tmp_path / "scoped.csv"
    out = io.StringIO()
    code = _script().main(
        ["--file", str(seed_path), "--photos", str(photos), "--report", str(report), "--apply"],
        db=db,
        out=out,
    )
    assert code == 0
    assert "ZZTFOREIGNPART" not in _parts(db, _combo(db, "ZZT 3 in 1", "ZZTH1"))


# --------------------------------------------------------------------------- AC-8.9


def _templates(db):
    db.expire_all()
    with company_scope(db, None):
        return {t.name: t for t in db.query(TagTemplate).all()}


def test_ac_8_9_templates_flag_creates_and_publishes_the_two_starters(
    db, catalogue, photos, tmp_path, storage
):
    _run(db, tmp_path, photos, apply=True, templates=True)
    found = _templates(db)
    assert set(found) == {"Bathroom furniture combo", "Kitchen sink combo"}
    assert found["Bathroom furniture combo"].family == "furniture_set"
    assert found["Kitchen sink combo"].family == "sink_combo"
    for template in found.values():
        assert template.published_version_id is not None, "published, so the designer can pick it"
        text = json.dumps(template.doc)
        for slot in ("combo_image", "combo_name", "combo_description", "combo_choices", "combo_topups"):
            assert slot in text, f"{template.name} does not use {slot}"
        # The doc is a valid TagTemplateDoc (the combo slots are in SLOT_BINDINGS), and a
        # combo with no price prints nothing, never a placeholder figure.
        from app.schemas.price_tag import TagTemplateDocModel

        TagTemplateDocModel.model_validate(template.doc)
        prices = [
            layer for layer in template.doc["layers"] if layer["slot_binding"] in ("list_price", "sell_price")
        ]
        assert len(prices) == 2
        assert all(layer["props"]["text"] == "" for layer in prices)


def test_ac_8_9_no_templates_flag_means_no_templates(db, catalogue, photos, tmp_path, storage):
    _run(db, tmp_path, photos, apply=True)
    assert _templates(db) == {}


def test_ac_8_9_rerunning_does_not_duplicate_or_overwrite_the_templates(
    db, catalogue, photos, tmp_path, storage
):
    _run(db, tmp_path, photos, apply=True, templates=True)
    first = _templates(db)
    versions_before = _count(db, TagTemplateVersion)
    with company_scope(db, None):
        edited = db.query(TagTemplate).filter(TagTemplate.name == "Kitchen sink combo").one()
        edited.doc = {**edited.doc, "marketing_edit": "kept"}
        db.commit()
        published_before = {n: t.published_version_id for n, t in first.items()}

    _run(db, tmp_path, photos, apply=True, templates=True)

    found = _templates(db)
    assert len(found) == 2 and _count(db, TagTemplate) == 2
    assert found["Kitchen sink combo"].doc.get("marketing_edit") == "kept"
    assert {n: t.published_version_id for n, t in found.items()} == published_before
    assert _count(db, TagTemplateVersion) == versions_before


# --------------------------------------------------------------------------- AC-8.11


def test_ac_8_11_the_repo_holds_the_script_and_a_synthetic_fixture_only():
    assert (REPO / "sorento_crm_backend" / "scripts" / "import_product_combos.py").exists()
    assert SEED.exists()
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    real = [
        path
        for path in tracked
        if "combos-seed" in path.lower() or "flyer" in path.lower() and path.lower().endswith(".json")
        and "fixtures" not in path.lower()
    ]
    assert real == [], f"real flyer data must not be committed: {real}"
    data = json.loads(SEED.read_text())
    assert all(entry["host_code"].startswith("ZZT") for entry in data), "made-up codes only"


def test_a_rerun_with_nothing_to_change_reports_unchanged_and_an_upgrade_is_one_write(
    db, catalogue, photos, tmp_path, storage
):
    _run(db, tmp_path, photos, apply=True)
    _code, _out, rows = _run(db, tmp_path, photos, apply=True)
    assert _by_id(rows)["C1"]["status"] == "unchanged"
    _code, _out, dry = _run(db, tmp_path, photos)
    assert _by_id(dry)["C1"]["status"] == "unchanged"
    assert _parts(db, _combo(db, "ZZT 3 in 1", "ZZTH1"))["ZZTU1"].is_upgrade is True


def test_the_host_listed_among_the_components_is_not_a_drop_but_a_missing_code_still_is(
    db, catalogue, photos, tmp_path, storage
):
    entries = json.loads(SEED.read_text())
    entries[0]["components"].insert(0, {"code": "ZZTH1", "role": "Cabinet", "dimensions": "", "lp": 1})
    entries[0]["components"].append({"code": "ZZTLOST", "role": "Odd", "dimensions": "", "lp": 1})
    seed_path = tmp_path / "host-listed.json"
    seed_path.write_text(json.dumps(entries))
    for apply in (False, True):
        report = tmp_path / f"host-{apply}.csv"
        argv = ["--file", str(seed_path), "--photos", str(photos), "--report", str(report)]
        assert _script().main(argv + (["--apply"] if apply else []), db=db, out=io.StringIO()) == 0
        with open(report, newline="", encoding="utf-8-sig") as fh:
            row = next(r for r in csv.DictReader(fh) if r["id"] == "C1")
        assert "ZZTH1" not in row["dropped_parts"], (apply, row["dropped_parts"])
        assert row["dropped_parts"] == "ZZTLOST"
    assert "ZZTH1" not in _parts(db, _combo(db, "ZZT 3 in 1", "ZZTH1"))
