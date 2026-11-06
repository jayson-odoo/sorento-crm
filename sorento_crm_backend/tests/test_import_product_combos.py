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


def _free_names(db, combo) -> list[str]:
    from app.models.accessory import Accessory, ProductComboAccessory

    with company_scope(db, None):
        rows = (
            db.query(Accessory.name)
            .join(ProductComboAccessory, ProductComboAccessory.accessory_id == Accessory.id)
            .filter(ProductComboAccessory.combo_id == combo.id)
            .order_by(ProductComboAccessory.sort_order)
            .all()
        )
    return [name for (name,) in rows]


def _set_free_list(db, combo, names) -> None:
    from app.models.accessory import Accessory, ProductComboAccessory

    db.query(ProductComboAccessory).filter(ProductComboAccessory.combo_id == combo.id).delete()
    for index, name in enumerate(names):
        item = Accessory(name=name, company_id=combo.host_product.company_id)
        db.add(item)
        db.flush()
        db.add(ProductComboAccessory(combo_id=combo.id, accessory_id=item.id, sort_order=index))
    db.flush()


# --------------------------------------------------------------------------- AC-8.2


def test_ac_8_2_apply_loads_the_combo_description_free_items_and_cover(
    db, catalogue, photos, tmp_path, storage
):
    _run(db, tmp_path, photos, apply=True)
    combo = _combo(db, "ZZT 3 in 1", "ZZTH1")
    assert combo is not None
    assert combo.description == "Cabinet, mirror and basin set"

    # PRICETAG-ACCESSORIES: free items load as the combo's accessory list, not as text.
    items = _free_names(db, combo)
    assert len(items) == 2, items
    assert combo.free_items is None
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


def test_ac_8_3_prices_are_loaded(db, catalogue, photos, tmp_path, storage):
    # PRICETAG-COMBO-RENDER K9: the old rule (no price loaded) is retired; the seed's prices load.
    _run(db, tmp_path, photos, apply=True)
    combo = _combo(db, "ZZT 3 in 1", "ZZTH1")
    assert (combo.list_price, combo.sell_price) == (Decimal("1500.00"), Decimal("1200.00"))
    parts = _parts(db, combo)
    assert parts["ZZTBW"].sell_price == Decimal("250.00")
    assert parts["ZZTU1"].topup_amount == Decimal("100.00")
    assert parts["ZZTM1"].sell_price is None, "a component's own lp is not a price to load"


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
        _set_free_list(db, combo, ["ZZT MARKETING ITEM"])
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
    assert _free_names(db, combo) == ["ZZT MARKETING ITEM"], "a list someone set is never overwritten"
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
    assert _free_names(db, combo), "the empty free items list is filled"
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


def _starter_names():
    return [shape[0] for shape in _script().STARTER_SHAPES]


def test_ac_8_9_templates_flag_creates_and_publishes_one_starter_per_shape(
    db, catalogue, photos, tmp_path, storage
):
    _run(db, tmp_path, photos, apply=True, templates=True)
    found = _templates(db)
    assert set(found) == set(_starter_names())
    for template in found.values():
        assert template.published_version_id is not None, "published, so the designer can pick it"
        # The doc is a valid TagTemplateDoc, and every starter reads positions, never a part number.
        from app.schemas.price_tag import TagTemplateDocModel

        TagTemplateDocModel.model_validate(template.doc)
        assert "subjectSlot" in json.dumps(template.doc)
        assert "subjectPart" not in json.dumps(template.doc)


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
        edited = db.query(TagTemplate).filter(TagTemplate.name == _starter_names()[0]).one()
        edited.doc = {**edited.doc, "marketing_edit": "kept"}
        db.commit()
        published_before = {n: t.published_version_id for n, t in first.items()}

    _run(db, tmp_path, photos, apply=True, templates=True)

    found = _templates(db)
    assert len(found) == len(_starter_names()) and _count(db, TagTemplate) == len(_starter_names())
    assert found[_starter_names()[0]].doc.get("marketing_edit") == "kept"
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


def test_a_rerun_with_nothing_to_change_reports_matches_and_an_upgrade_is_one_write(
    db, catalogue, photos, tmp_path, storage
):
    _run(db, tmp_path, photos, apply=True)
    _code, _out, rows = _run(db, tmp_path, photos, apply=True)
    assert _by_id(rows)["C1"]["status"] == "matches"
    _code, _out, dry = _run(db, tmp_path, photos)
    assert _by_id(dry)["C1"]["status"] == "matches"
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


# --------------------------------------------------------------------------- company of the rows written
#
# The script runs as its own process and never installs the company-scope listeners, so
# nothing auto-stamps `company_id` there. The test process installs them (tests/conftest.py),
# which stamped the starter templates for us and hid the defect. `_standalone` switches the
# auto-stamp off, as it is in the real run.


@pytest.fixture()
def _standalone(monkeypatch):
    from app.services import company_scope as scope_module

    monkeypatch.setattr(scope_module, "_ENFORCE", False)


def _templates_named(db, name):
    db.expire_all()
    with company_scope(db, None):
        return db.query(TagTemplate).filter(TagTemplate.name == name).all()


def _seed_template(db, name, company_id, *, published=True):
    """A template row the way an earlier run (or marketing) left it, in `company_id`."""
    from app.models.dealer_kit import TagTemplateVersion as Version

    doc = {"layers": [], "width_mm": 10, "height_mm": 10, "marker": f"seeded {name}"}
    with company_scope(db, frozenset({DEFAULT_COMPANY_ID})):
        row = TagTemplate(name=name, family="sink_combo", doc=doc, print_size={"width_mm": 10, "height_mm": 10})
        db.add(row)
        db.flush()
        version = Version(template_id=row.id, version_no=1, doc=doc, print_size=row.print_size)
        db.add(version)
        db.flush()
        if published:
            row.published_version_id = version.id
        db.commit()
        row_id, version_id = row.id, version.id
    with company_scope(db, None):
        db.query(TagTemplate).filter(TagTemplate.id == row_id).update(
            {TagTemplate.company_id: company_id}, synchronize_session=False
        )
        db.commit()
    return row_id, version_id


def test_templates_are_written_in_the_chosen_company_and_list_for_it(
    db, catalogue, photos, tmp_path, storage, _standalone
):
    _run(db, tmp_path, photos, "--company", "SRT", apply=True, templates=True)
    found = [t for name in _starter_names() for t in _templates_named(db, name)]
    assert len(found) == len(_starter_names())
    assert {t.company_id for t in found} == {DEFAULT_COMPANY_ID}, "NULL company hides them from staff"
    assert all(t.published_version_id for t in found)

    from app.services.dealer_kit import tag_template_service

    with company_scope(db, frozenset({DEFAULT_COMPANY_ID})):
        listed = {t.name for t in tag_template_service._scoped(db).all()}
    assert set(_starter_names()) <= listed


def test_a_starter_left_with_no_company_is_claimed_not_duplicated(
    db, catalogue, photos, tmp_path, storage, _standalone
):
    from app.models.dealer_kit import TagTemplateVersion as Version

    row_id, version_id = _seed_template(db, _starter_names()[0], None)

    # A dry run reports it and writes nothing.
    _code, out, _rows = _run(db, tmp_path, photos, "--company", "SRT", templates=True)
    assert _starter_names()[0] in out and "would" in out.lower()
    assert _templates_named(db, _starter_names()[0])[0].company_id is None

    _code, out, _rows = _run(db, tmp_path, photos, "--company", "SRT", apply=True, templates=True)
    rows = _templates_named(db, _starter_names()[0])
    assert [r.id for r in rows] == [row_id], "no duplicate"
    assert rows[0].company_id == DEFAULT_COMPANY_ID
    assert rows[0].doc["marker"] == f"seeded {_starter_names()[0]}", "its doc is left alone"
    assert rows[0].published_version_id == version_id
    with company_scope(db, None):
        assert db.query(Version).filter(Version.template_id == row_id).count() == 1
    assert _starter_names()[0] in out

    # And a further rerun changes nothing.
    _run(db, tmp_path, photos, "--company", "SRT", apply=True, templates=True)
    assert [r.id for r in _templates_named(db, _starter_names()[0])] == [row_id]


def test_another_companys_template_and_other_unowned_names_are_not_touched(
    db, catalogue, photos, tmp_path, storage, _standalone
):
    theirs_id, _ = _seed_template(db, _starter_names()[0], MOCHA_ID)
    loose_id, _ = _seed_template(db, "ZZT Some other template", None)

    _run(db, tmp_path, photos, "--company", "SRT", apply=True, templates=True)

    theirs = [r for r in _templates_named(db, _starter_names()[0]) if r.id == theirs_id]
    assert theirs[0].company_id == MOCHA_ID and theirs[0].doc["marker"] == f"seeded {_starter_names()[0]}"
    mine = [r for r in _templates_named(db, _starter_names()[0]) if r.id != theirs_id]
    assert len(mine) == 1 and mine[0].company_id == DEFAULT_COMPANY_ID, "ours is created, theirs not claimed"
    loose = _templates_named(db, "ZZT Some other template")[0]
    assert loose.id == loose_id and loose.company_id is None


def test_every_other_row_the_import_writes_is_in_the_hosts_company_or_has_none(
    db, catalogue, photos, tmp_path, storage, _standalone
):
    from app.models.product import ProductAttachment

    assert "company_id" not in ProductCombo.__table__.c
    assert "company_id" not in ProductComboPart.__table__.c
    _run(db, tmp_path, photos, apply=True)
    db.expire_all()
    with company_scope(db, None):
        cover = db.query(Attachment).filter(Attachment.entity_type == "product_combo_image").all()
        links = db.query(ProductAttachment).filter(ProductAttachment.attachment_id.in_([a.id for a in cover])).all()
    assert cover and links
    assert {a.company_id for a in cover} == {DEFAULT_COMPANY_ID}
    assert {link.company_id for link in links} == {DEFAULT_COMPANY_ID}


# --------------------------------------------------------------------------- PRICETAG-COMBO-FORMAT
#
# AC-9 (the importer stores the sanitised description) and AC-12 (the compare judges text, not
# markup). Written test-FIRST: the importer does not call `sanitise_tag_html` / `plain_text` yet.


def _run_with_seed(db, tmp_path, photos, entries, *, apply):
    seed_path = tmp_path / f"fmt-seed-{len(list(tmp_path.glob('fmt-seed-*.json')))}.json"
    seed_path.write_text(json.dumps(entries))
    report = tmp_path / f"fmt-report-{len(list(tmp_path.glob('fmt-report-*.csv')))}.csv"
    argv = ["--file", str(seed_path), "--photos", str(photos), "--report", str(report)]
    if apply:
        argv.append("--apply")
    assert _script().main(argv, db=db, out=io.StringIO()) == 0
    with open(report, newline="", encoding="utf-8-sig") as fh:
        return [
            {k.strip().lower().replace(" ", "_"): v for k, v in raw.items()}
            for raw in csv.DictReader(fh)
        ]


def test_ac_9_the_importer_stores_the_sanitised_description(db, catalogue, photos, tmp_path, storage):
    """AC-9: a seed description `<p onclick=x>a</p>` is stored as `<p>a</p>` on --apply."""
    entries = json.loads(SEED.read_text())
    entries[0]["combo_description"] = "<p onclick=x>a</p>"
    _run_with_seed(db, tmp_path, photos, entries, apply=True)
    assert _combo(db, "ZZT 3 in 1", "ZZTH1").description == "<p>a</p>"


def test_ac_9_a_seed_script_tag_is_not_stored(db, catalogue, photos, tmp_path, storage):
    entries = json.loads(SEED.read_text())
    entries[0]["combo_description"] = "<p>a<img src=x onerror=alert(1)><script>x</script>b</p>"
    _run_with_seed(db, tmp_path, photos, entries, apply=True)
    assert _combo(db, "ZZT 3 in 1", "ZZTH1").description == "<p>ab</p>"


def test_ac_12_a_combo_whose_only_difference_is_formatting_reports_matches(
    db, catalogue, photos, tmp_path, storage
):
    """AC-12: stored `<p><strong>SRTBF11416</strong> (CABINET)</p>` against the seed text
    "SRTBF11416 (CABINET)" is "matches", not "differs" (already true today because a set
    description is never compared; the test pins that the new plain_text compare keeps it so)."""
    entries = json.loads(SEED.read_text())
    entries[0]["combo_description"] = "SRTBF11416 (CABINET)"
    _run_with_seed(db, tmp_path, photos, entries, apply=True)

    combo = _combo(db, "ZZT 3 in 1", "ZZTH1")
    with company_scope(db, None):
        combo.description = "<p><strong>SRTBF11416</strong> (CABINET)</p>"
        db.commit()

    for apply in (False, True):
        rows = _run_with_seed(db, tmp_path, photos, entries, apply=apply)
        assert _by_id(rows)["C1"]["status"] == "matches", (apply, _by_id(rows)["C1"])
    assert (
        _combo(db, "ZZT 3 in 1", "ZZTH1").description == "<p><strong>SRTBF11416</strong> (CABINET)</p>"
    ), "formatting the owner added is never overwritten by the plain seed text"
