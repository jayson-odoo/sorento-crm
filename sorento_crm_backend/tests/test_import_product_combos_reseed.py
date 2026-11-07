"""PRICETAG-COMBO-RENDER K9 / AC-E2 to E7: the flyer re-seed through `import_product_combos.py`.

Written test-FIRST. Today the script ignores every price, reports `would_create` / `unchanged`
style statuses, never removes or regroups a part, cannot link templates and builds two fixed
starters. Everything runs through `script.main(argv, db=db, out=StringIO)` on a blank Postgres
schema with the exact system codes of the reference flyer, each test seeding its own chain.

Decisions where the plan is open (simplest reading):
* Dry run report columns: id, flyer, page, host, combo, shape, status, differences,
  dropped_parts, discontinued, price_note, unsure (lower-cased, spaces to underscores).
* A combo is matched on host + name (as today). `differs` lists each difference as text that
  names the part code ("added SRTWT7449-RG", "removed ...", "regrouped ...").
* `--apply` loads prices and adds missing parts; bringing a differing combo to the flyer
  (remove, regroup) needs `--update` (K9) in addition to `--apply`. Whether bare `--apply`
  also updates (AC-E3 wording) is left open and not asserted.
* An `unsure` combo (unresolved or discontinued code, or the seed's own `unsure` text) is
  reported `unsure`; its bad code is never written as a part.
* A no-selling-price host loads combo LP only; the note is "price not loaded: no selling price
  brand".
* `--templates` builds one 105 x 148 published template per distinct shape: S1 (3 picks of group 1
  at most is not guessed: the template needs the whole group, 5, and the upgrade), S2 (1 fixed),
  S3 (2 picks), S4 (2 fixed). Asserted through `template_needs` of each published document.
"""
from __future__ import annotations

import csv
import io
import json
from decimal import Decimal

import pytest

from app.models.base import company_scope, set_company_scope
from app.models.dealer_kit import ComboTagTemplate, TagTemplate
from app.models.product_combo import ProductCombo, ProductComboPart
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests import _ptag_shapes_seed as shapes
from tests._mc_lookup_seed import MOCHA_ID, product as mocha_product, seed_mocha
from tests._pg_fixture import blank_session

D = Decimal
ALL_CODES = (
    [shapes.S1_HOST, *shapes.S1_OPTIONS, shapes.S1_UPGRADE, shapes.S2_HOST, shapes.S2_FIXED]
    + shapes.S3_OPTIONS
    + [shapes.S4_HOST, *shapes.S4_FIXED]
)


def _script():
    from scripts import import_product_combos as script

    return script


@pytest.fixture()
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


@pytest.fixture()
def catalogue(db):
    rows = {code: shapes.prod(db, code) for code in dict.fromkeys(ALL_CODES)}
    db.commit()
    return rows


def entry(eid, host, name, *, components=(), groups=(), topups=(), **extra):
    return {
        "id": eid,
        "host_code": host,
        "combo_name": name,
        "flyer": "flyer.pdf",
        "page": 7,
        "components": [{"code": c, "role": ""} for c in components],
        "choice_groups": [
            {"role": role, "options": [o if isinstance(o, dict) else {"code": o} for o in options]}
            for role, options in groups
        ],
        "topups": [t if isinstance(t, dict) else {"code": t} for t in topups],
        "free_items": [],
        "unsure": "",
        **extra,
    }


def s3_entry(**extra):
    return entry(
        "S3", shapes.S3_HOST, "ZZT S3", groups=[("Tap colour", shapes.S3_OPTIONS)], **extra
    )


def s1_entry(**extra):
    return entry(
        "S1", shapes.S1_HOST, "ZZT S1",
        groups=[("Kitchen tap", shapes.S1_OPTIONS)], topups=[shapes.S1_UPGRADE], **extra,
    )


def _run(db, tmp_path, entries, *flags):
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps(entries))
    report = tmp_path / f"report-{len(list(tmp_path.glob('report-*.csv')))}.csv"
    out = io.StringIO()
    code = _script().main(
        ["--file", str(seed_file), "--report", str(report), *flags], db=db, out=out
    )
    rows = []
    if report.exists():
        with open(report, newline="", encoding="utf-8-sig") as fh:
            for raw in csv.DictReader(fh):
                rows.append({k.strip().lower().replace(" ", "_"): v for k, v in raw.items()})
    return code, out.getvalue(), {row["id"]: row for row in rows}


def _combo(db, name, host_code):
    db.expire_all()
    with company_scope(db, None):
        return (
            db.query(ProductCombo)
            .join(ProductCombo.host_product)
            .filter(ProductCombo.name == name)
            .filter_by(product_code=host_code)
            .first()
        )


def _parts(db, combo):
    db.expire_all()
    with company_scope(db, None):
        return {
            p.part_product.product_code: p
            for p in db.query(ProductComboPart).filter(ProductComboPart.combo_id == combo.id).all()
        }


def _count(db, model):
    db.expire_all()
    with company_scope(db, None):
        return db.query(model).count()


# --------------------------------------------------------------------------- AC-E2 dry run


def test_dry_run_new_row_carries_the_flyer_columns(db, catalogue, tmp_path):
    code, _out, rows = _run(db, tmp_path, [s3_entry()])
    assert code == 0
    row = rows["S3"]
    assert row["status"] == "new"
    assert row["flyer"] == "flyer.pdf" and row["page"] == "7"
    assert row["host"] == shapes.S3_HOST and row["combo"] == "ZZT S3"
    assert row["shape"]
    for column in ("differences", "dropped_parts", "discontinued", "price_note", "unsure"):
        assert column in row


def test_dry_run_shape_tells_the_shapes_apart(db, catalogue, tmp_path):
    entries = [
        s1_entry(),
        s3_entry(),
        entry("S4", shapes.S4_HOST, "ZZT S4", components=shapes.S4_FIXED),
    ]
    _code, _out, rows = _run(db, tmp_path, entries)
    assert len({rows["S1"]["shape"], rows["S3"]["shape"], rows["S4"]["shape"]}) == 3


def test_dry_run_writes_nothing(db, catalogue, tmp_path):
    _run(db, tmp_path, [s1_entry(lp=2500, sp=2000), s3_entry()], "--link-templates", "--templates")
    assert _count(db, ProductCombo) == 0
    assert _count(db, ProductComboPart) == 0
    assert _count(db, ComboTagTemplate) == 0
    assert _count(db, TagTemplate) == 0


def test_dry_run_matches_when_the_combo_is_already_the_flyers(db, catalogue, tmp_path):
    shapes.s3(db, "ZZT S3")
    db.commit()
    _code, _out, rows = _run(db, tmp_path, [s3_entry()])
    assert rows["S3"]["status"] == "matches"
    assert rows["S3"]["differences"] == ""


def test_dry_run_differs_names_an_added_part(db, catalogue, tmp_path):
    from tests import _ptag_combo_seed as seed

    host = catalogue[shapes.S3_HOST]
    seed.combo(db, host, "ZZT S3", parts=[{"product": catalogue["SRTWT7449-BL"], "group": "Tap colour"}])
    db.commit()
    _code, _out, rows = _run(db, tmp_path, [s3_entry()])
    assert rows["S3"]["status"] == "differs"
    assert "SRTWT7449-RG" in rows["S3"]["differences"]


def test_dry_run_differs_names_a_removed_and_a_regrouped_part(db, catalogue, tmp_path):
    from tests import _ptag_combo_seed as seed

    host = catalogue[shapes.S3_HOST]
    seed.combo(
        db, host, "ZZT S3",
        parts=[
            {"product": catalogue["SRTWT7449-BL"], "group": "Tap colour"},
            {"product": catalogue["SRTWT7449-RG"]},  # fixed on the combo, grouped on the flyer
            {"product": catalogue["SRTWT6203-GM"]},  # not on the flyer any more
        ],
    )
    db.commit()
    _code, _out, rows = _run(db, tmp_path, [s3_entry()])
    differences = rows["S3"]["differences"]
    assert rows["S3"]["status"] == "differs"
    assert "SRTWT7449-RG" in differences and "SRTWT6203-GM" in differences


def test_dry_run_unsure_for_an_unresolved_code(db, catalogue, tmp_path):
    bad = s3_entry()
    bad["choice_groups"][0]["options"].append({"code": "SRTNOPE0001"})
    _code, _out, rows = _run(db, tmp_path, [bad])
    assert rows["S3"]["status"] == "unsure"
    assert "SRTNOPE0001" in rows["S3"]["unsure"] + rows["S3"]["dropped_parts"]


def test_dry_run_unsure_for_a_code_of_another_company(db, catalogue, tmp_path):
    seed_mocha(db)
    mocha_product(db, company_id=MOCHA_ID, code="SRTMOCHAONLY1")
    db.commit()
    bad = s3_entry()
    bad["choice_groups"][0]["options"].append({"code": "SRTMOCHAONLY1"})
    _code, _out, rows = _run(db, tmp_path, [bad])
    assert rows["S3"]["status"] == "unsure"
    assert "SRTMOCHAONLY1" in rows["S3"]["unsure"] + rows["S3"]["dropped_parts"]


def test_dry_run_unsure_for_a_discontinued_product_and_it_is_named(db, catalogue, tmp_path):
    catalogue["SRTWT7449-RG"].is_discontinued = True
    db.commit()
    _code, _out, rows = _run(db, tmp_path, [s3_entry()])
    assert rows["S3"]["status"] == "unsure"
    assert "SRTWT7449-RG" in rows["S3"]["discontinued"]


def test_dry_run_unsure_carries_the_seeds_own_note(db, catalogue, tmp_path):
    _code, _out, rows = _run(db, tmp_path, [s3_entry(unsure="price smudged on the flyer")])
    assert rows["S3"]["status"] == "unsure"
    assert "smudged" in rows["S3"]["unsure"]


# --------------------------------------------------------------------------- AC-E3 apply


def test_apply_loads_combo_option_and_topup_prices(db, catalogue, tmp_path):
    groups = [
        ("Kitchen tap", [{"code": c, "sp": 100 + i} for i, c in enumerate(shapes.S1_OPTIONS)])
    ]
    e = entry(
        "S1", shapes.S1_HOST, "ZZT S1", groups=groups,
        topups=[{"code": shapes.S1_UPGRADE, "topup": 150}], lp=2500, sp=2000,
    )
    code, _out, rows = _run(db, tmp_path, [e], "--apply")
    assert code == 0
    assert rows["S1"]["status"] in {"new", "created"}
    combo = _combo(db, "ZZT S1", shapes.S1_HOST)
    assert combo.list_price == D("2500.00") and combo.sell_price == D("2000.00")
    parts = _parts(db, combo)
    assert parts["SRTKT1863SS"].sell_price == D("101.00")
    assert parts[shapes.S1_UPGRADE].is_upgrade is True
    assert parts[shapes.S1_UPGRADE].topup_amount == D("150.00")


def test_apply_update_brings_a_differing_combo_to_the_flyer(db, catalogue, tmp_path):
    from tests import _ptag_combo_seed as seed

    host = catalogue[shapes.S3_HOST]
    seed.combo(
        db, host, "ZZT S3",
        parts=[
            {"product": catalogue["SRTWT7449-BL"], "group": "Tap colour"},
            {"product": catalogue["SRTWT7449-RG"]},
            {"product": catalogue["SRTWT6203-GM"]},
        ],
    )
    db.commit()
    code, _out, _rows = _run(db, tmp_path, [s3_entry(lp=900)], "--apply", "--update")
    assert code == 0
    combo = _combo(db, "ZZT S3", shapes.S3_HOST)
    parts = _parts(db, combo)
    assert set(parts) == {"SRTWT7449-BL", "SRTWT7449-RG"}, "the part the flyer dropped is removed"
    assert parts["SRTWT7449-RG"].choice_group == "Tap colour", "regrouped"
    assert combo.list_price == D("900.00")


def test_apply_update_adds_a_missing_part_and_reflags_an_upgrade(db, catalogue, tmp_path):
    from tests import _ptag_combo_seed as seed

    host = catalogue[shapes.S1_HOST]
    seed.combo(
        db, host, "ZZT S1",
        parts=[{"product": catalogue[c], "group": "Kitchen tap"} for c in shapes.S1_OPTIONS[:3]]
        + [{"product": catalogue[shapes.S1_UPGRADE]}],  # an ordinary fixed part until now
    )
    db.commit()
    _run(db, tmp_path, [s1_entry()], "--apply", "--update")
    parts = _parts(db, _combo(db, "ZZT S1", shapes.S1_HOST))
    assert set(parts) == set(shapes.S1_OPTIONS) | {shapes.S1_UPGRADE}
    assert parts[shapes.S1_UPGRADE].is_upgrade is True
    assert parts["SRTKT1892SS"].choice_group == "Kitchen tap"


def test_a_combo_the_flyer_no_longer_shows_is_untouched(db, catalogue, tmp_path):
    from tests import _ptag_combo_seed as seed

    host = catalogue[shapes.S3_HOST]
    seed.combo(db, host, "ZZT Old pack", parts=[{"product": catalogue["SRTWT6203-GM"]}], list_price=D("111.00"))
    db.commit()
    _run(db, tmp_path, [s3_entry(lp=900)], "--apply", "--update")
    old = _combo(db, "ZZT Old pack", shapes.S3_HOST)
    assert old is not None and old.list_price == D("111.00")
    assert set(_parts(db, old)) == {"SRTWT6203-GM"}


def test_a_rerun_of_apply_changes_nothing_more(db, catalogue, tmp_path):
    _run(db, tmp_path, [s3_entry(lp=900)], "--apply")
    _code, _out, rows = _run(db, tmp_path, [s3_entry(lp=900)])
    assert rows["S3"]["status"] == "matches"


# --------------------------------------------------------------------------- AC-E4 no selling price


def _no_sp_host(db, catalogue):
    from app.models.product import Brand

    brand = db.get(Brand, catalogue[shapes.S1_HOST].brand_id)
    brand.no_promo_selling_price = True
    db.commit()


def test_no_selling_price_brand_loads_no_sp_option_sp_or_topup(db, catalogue, tmp_path):
    _no_sp_host(db, catalogue)
    groups = [("Kitchen tap", [{"code": c, "sp": 100} for c in shapes.S1_OPTIONS])]
    e = entry(
        "S1", shapes.S1_HOST, "ZZT S1", groups=groups,
        topups=[{"code": shapes.S1_UPGRADE, "topup": 150}], lp=2500, sp=2000,
    )
    _code, _out, rows = _run(db, tmp_path, [e], "--apply")
    assert "price not loaded: no selling price brand" in rows["S1"]["price_note"]
    combo = _combo(db, "ZZT S1", shapes.S1_HOST)
    assert combo.sell_price is None
    assert combo.list_price == D("2500.00")
    parts = _parts(db, combo)
    assert all(p.sell_price is None for p in parts.values())
    assert parts[shapes.S1_UPGRADE].topup_amount is None


def test_no_selling_price_note_is_in_the_dry_run_too(db, catalogue, tmp_path):
    _no_sp_host(db, catalogue)
    _code, _out, rows = _run(db, tmp_path, [s1_entry(lp=2500, sp=2000)])
    assert "price not loaded: no selling price brand" in rows["S1"]["price_note"]


def test_a_normal_brand_has_no_price_note(db, catalogue, tmp_path):
    _code, _out, rows = _run(db, tmp_path, [s3_entry(lp=900, sp=800)])
    assert rows["S3"]["price_note"] == ""


# --------------------------------------------------------------------------- AC-E5 bad codes


def test_a_discontinued_or_unresolved_code_is_never_written_as_a_part(db, catalogue, tmp_path):
    catalogue["SRTKT1880SS"].is_discontinued = True
    db.commit()
    e = s1_entry()
    e["choice_groups"][0]["options"].append({"code": "SRTNOPE0002"})
    _code, _out, rows = _run(db, tmp_path, [e], "--apply")
    assert rows["S1"]["status"] == "unsure"
    assert "SRTKT1880SS" in rows["S1"]["discontinued"]
    combo = _combo(db, "ZZT S1", shapes.S1_HOST)
    written = set(_parts(db, combo)) if combo is not None else set()
    assert "SRTKT1880SS" not in written and "SRTNOPE0002" not in written


# --------------------------------------------------------------------------- AC-E6 link templates


def _template_with(db, name, *slots):
    from app.models.dealer_kit import TagTemplate as T
    from tests.test_product_tag_templates import _template

    template_id = _template(db, name)
    template = db.get(T, template_id)
    doc = {
        "layers": [
            {
                "id": f"l{i}", "type": "text", "x_mm": 0, "y_mm": 0, "width_mm": 5, "height_mm": 5,
                "z_index": 1, "props": {"kind": "text", "subjectSlot": slot},
            }
            for i, slot in enumerate(slots)
        ],
        "width_mm": 105, "height_mm": 148,
    }
    template.doc = doc
    template.published_version.doc = doc
    db.flush()
    return template_id


def _linked(db, combo):
    db.expire_all()
    with company_scope(db, None):
        return {r.template_id for r in db.query(ComboTagTemplate).filter_by(combo_id=combo.id).all()}


def test_link_templates_links_every_published_template_that_fits(db, catalogue, tmp_path):
    """A main-only template is a plain template: it fits every combo and prints the combo as one
    product, fixed parts included (owner ruling 5 Nov 2026, PRICETAG-COMBO-FIT-HOTFIX #2203), so
    it links too. A template that reads more fixed parts or a group the combo lacks does not."""
    fits_one = _template_with(db, "ZZT one fixed", {"kind": "fixed", "index": 0})
    fits_main = _template_with(db, "ZZT main", {"kind": "main"})
    too_many = _template_with(db, "ZZT three fixed", {"kind": "fixed", "index": 2})
    needs_group = _template_with(db, "ZZT group", {"kind": "pick", "group": 0, "index": 0})
    unpublished = _template_with(db, "ZZT unpublished", {"kind": "fixed", "index": 0})
    db.get(TagTemplate, unpublished).published_version_id = None
    db.commit()
    e = entry("S2", shapes.S2_HOST, "ZZT S2", components=[shapes.S2_FIXED])
    _code, _out, _rows = _run(db, tmp_path, [e], "--apply", "--link-templates")
    combo = _combo(db, "ZZT S2", shapes.S2_HOST)
    assert _linked(db, combo) == {fits_one, fits_main}
    assert too_many not in _linked(db, combo) and needs_group not in _linked(db, combo)


def test_link_templates_follows_the_combos_own_shape(db, catalogue, tmp_path):
    pick_two = _template_with(db, "ZZT pick two", {"kind": "pick", "group": 0, "index": 1})
    pick_three = _template_with(db, "ZZT pick three", {"kind": "pick", "group": 0, "index": 2})
    db.commit()
    _run(db, tmp_path, [s3_entry()], "--apply", "--link-templates")
    assert _linked(db, _combo(db, "ZZT S3", shapes.S3_HOST)) == {pick_two}
    assert pick_three not in _linked(db, _combo(db, "ZZT S3", shapes.S3_HOST))


def test_without_the_flag_nothing_is_linked(db, catalogue, tmp_path):
    _template_with(db, "ZZT main", {"kind": "main"})
    db.commit()
    _run(db, tmp_path, [s3_entry()], "--apply")
    assert _count(db, ComboTagTemplate) == 0


# --------------------------------------------------------------------------- AC-E7 starter templates


def _published_needs(db):
    from app.services.dealer_kit.template_needs import template_needs

    db.expire_all()
    out = []
    with company_scope(db, None):
        for template in db.query(TagTemplate).filter(TagTemplate.published_version_id.isnot(None)).all():
            version = template.published_version
            out.append((template, version, template_needs(version.doc)))
    return out


def test_templates_flag_builds_one_105_by_148_template_per_shape(db, catalogue, tmp_path):
    code, _out, _rows = _run(db, tmp_path, [s3_entry()], "--apply", "--templates")
    assert code == 0
    built = _published_needs(db)
    needs = [n for _t, _v, n in built]
    for wanted in (
        {"fixed": 0, "groups": [5], "upgrades": 1},  # S1 and S5
        {"fixed": 1, "groups": [], "upgrades": 0},  # S2
        {"fixed": 0, "groups": [2], "upgrades": 0},  # S3
        {"fixed": 2, "groups": [], "upgrades": 0},  # S4
    ):
        assert needs.count(wanted) == 1, (wanted, needs)
    for template, version, _n in built:
        assert version.print_size["width_mm"] == 105 and version.print_size["height_mm"] == 148
        assert template.company_id == DEFAULT_COMPANY_ID


def test_templates_flag_dry_run_creates_none(db, catalogue, tmp_path):
    _run(db, tmp_path, [s3_entry()], "--templates")
    assert _count(db, TagTemplate) == 0


def test_the_old_fixed_starters_are_gone(db, catalogue, tmp_path):
    _run(db, tmp_path, [s3_entry()], "--apply", "--templates")
    names = {t.name for t, _v, _n in _published_needs(db)}
    assert "Bathroom furniture combo" not in names and "Kitchen sink combo" not in names


def test_starter_layouts_come_from_one_generic_position_function():
    script = _script()
    assert callable(script.position_template)
    doc = script.position_template("ZZT shape", 1, [3], 1)
    from app.services.dealer_kit.template_needs import template_needs

    assert template_needs(doc) == {"fixed": 1, "groups": [3], "upgrades": 1}


def test_starter_price_text_layers_print_the_currency_and_validate():
    """AC-A3: the price text carries its own RM (showCurrency), so an empty price prints nothing
    at all; the strict doc model accepts the key."""
    from app.schemas.price_tag import TagTemplateDocModel

    doc = _script().position_template("ZZT shape", 1, [2], 0)
    TagTemplateDocModel.model_validate(doc)
    layers = [layer for layer in doc["layers"] if layer.get("slot_binding") in ("list_price", "sell_price")]
    assert layers and all(layer["props"].get("showCurrency") is True for layer in layers)
