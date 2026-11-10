"""COMBO-SETTINGS-UX: part labels, the main label, the parts line and `dimensions_lwh`.

Covers the PATCH/GET contract on `product-combos` and combo parts, the copy-to-products carry-over,
the tag-preview payload (asserted on the wire: `response_model` drops what it does not declare),
the `L780xW480xH400mm` formatter and the additive migration. Synthetic data only.
"""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.product_combo import ProductCombo, ProductComboPart
from app.services.company_scope import register_company_scope_listeners

from tests import _ptag_combo_seed as seed
from tests.test_pricetag_combo_format_browser_fixes import STAFF_PREVIEW
from tests.test_product_combo_copy_to_products import COPY
from tests.test_product_combos import (  # noqa: F401  (db, _clear_overrides are fixtures)
    COMBO,
    COMBO_PART,
    COMBOS,
    EDIT,
    VIEW,
    _caller,
    _clear_overrides,
    _combo,
    _part,
    _product,
    db,
)
from tests.test_product_tag_templates import _template, env  # noqa: F401

BACKEND = Path(__file__).resolve().parents[1]
REVISION = "combo_0001_part_labels"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


# --------------------------------------------------------------------------- formatter
@pytest.mark.parametrize(
    "dims, expected",
    [
        ((Decimal("780.00"), Decimal("480"), Decimal("400")), "L780xW480xH400mm"),
        ((Decimal("12.50"), Decimal("1"), Decimal("2")), "L12.5xW1xH2mm"),
        ((800, None, 700), "L800xW-xH700mm"),
        ((None, None, 400.0), "L-xW-xH400mm"),
        ((None, None, None), ""),
    ],
)
def test_format_dimensions_lwh(dims, expected):
    from app.services.dealer_kit.tag_data_service import format_dimensions_lwh

    assert format_dimensions_lwh(*dims) == expected


# --------------------------------------------------------------------------- PATCH / GET
def test_labels_patch_and_read_back(db, monkeypatch):
    host = _product(db, "ZZLBH")
    basin = _product(db, "ZZLBB")
    combo = _combo(db, host, "3 in 1")
    part = _part(db, combo, basin)
    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    r = client.patch(COMBO_PART.format(part_id=part.id), json={"label": "  BASIN "})
    assert r.status_code == 200, r.text
    assert r.json()["label"] == "BASIN"
    r = client.patch(
        COMBO.format(combo_id=combo.id),
        json={"main_label": " CABINET ", "parts_line": "<p>{{part.code}} (BASIN)</p>"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["main_label"] == "CABINET"
    assert r.json()["parts_line"] == "<p>{{part.code}} (BASIN)</p>"

    (row,) = client.get(COMBOS.format(product_id=host.id)).json()["data"]
    assert row["main_label"] == "CABINET"
    assert row["parts_line"] == "<p>{{part.code}} (BASIN)</p>"
    assert row["parts"][0]["label"] == "BASIN"

    # Omitted = unchanged.
    r = client.patch(COMBO.format(combo_id=combo.id), json={"name": "4 in 1"})
    assert r.json()["main_label"] == "CABINET"
    assert client.patch(COMBO_PART.format(part_id=part.id), json={"sort_order": 2}).json()["label"] == "BASIN"


def test_blank_label_saves_null(db, monkeypatch):
    host = _product(db, "ZZLBH2")
    combo = _combo(db, host, "3 in 1")
    part = _part(db, combo, _product(db, "ZZLBB2"))
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    client.patch(COMBO_PART.format(part_id=part.id), json={"label": "BASIN"})
    client.patch(COMBO.format(combo_id=combo.id), json={"main_label": "X", "parts_line": "<p>x</p>"})

    assert client.patch(COMBO_PART.format(part_id=part.id), json={"label": "   "}).json()["label"] is None
    body = client.patch(
        COMBO.format(combo_id=combo.id), json={"main_label": "", "parts_line": "  "}
    ).json()
    assert body["main_label"] is None
    assert body["parts_line"] is None


def test_label_over_100_chars_is_422(db, monkeypatch):
    host = _product(db, "ZZLBH3")
    combo = _combo(db, host, "3 in 1")
    part = _part(db, combo, _product(db, "ZZLBB3"))
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    assert client.patch(COMBO_PART.format(part_id=part.id), json={"label": "x" * 101}).status_code == 422
    assert client.patch(COMBO.format(combo_id=combo.id), json={"main_label": "x" * 101}).status_code == 422
    assert client.patch(COMBO_PART.format(part_id=part.id), json={"label": "x" * 100}).status_code == 200
    assert client.patch(COMBO.format(combo_id=combo.id), json={"main_label": "x" * 100}).status_code == 200


# --------------------------------------------------------------------------- copy
def test_copy_carries_labels_and_parts_line(db, monkeypatch):
    host = _product(db, "ZZLBH4")
    combo = _combo(db, host, "3 in 1")
    part = _part(db, combo, _product(db, "ZZLBB4"))
    combo.main_label = "CABINET"
    combo.parts_line = "<p>line</p>"
    part.label = "BASIN"
    db.flush()
    target = _product(db, "ZZLBT4")
    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    r = client.post(COPY.format(combo_id=combo.id), json={"target_product_ids": [target.id]})
    assert r.status_code == 200, r.text
    db.expire_all()
    copy = db.query(ProductCombo).filter(ProductCombo.host_product_id == target.id).one()
    assert (copy.main_label, copy.parts_line) == ("CABINET", "<p>line</p>")
    (copied_part,) = db.query(ProductComboPart).filter(ProductComboPart.combo_id == copy.id).all()
    assert copied_part.label == "BASIN"


# --------------------------------------------------------------------------- tag preview
def _preview_world(db):
    host = seed.product(db, "ZZLBPH", list_price="1000.00")
    host.dimensions_length, host.dimensions_width, host.dimensions_height = (
        Decimal("780.00"), Decimal("480"), Decimal("400"),
    )
    fixed = seed.product(db, "ZZLBPF", list_price="200.00")
    fixed.dimensions_length, fixed.dimensions_width, fixed.dimensions_height = (
        Decimal("800"), Decimal("130"), Decimal("700"),
    )
    bare = seed.product(db, "ZZLBPB", list_price="50.00")
    cb = seed.combo(
        db, host, "ZZT label combo", main_label="CABINET", parts_line="<p>{{part.code}}</p>",
        parts=[{"product": fixed, "label": "MIRROR"}, {"product": bare}],
    )
    template_id = _template(db, "LB")
    from app.models.dealer_kit import ComboTagTemplate

    db.add(ComboTagTemplate(combo_id=cb.id, template_id=template_id))
    db.flush()
    return host, cb, template_id, fixed, bare


def test_tag_preview_carries_labels_parts_line_and_dimensions_lwh(env):  # noqa: F811
    db, c, _ = env
    host, cb, template_id, fixed, bare = _preview_world(db)
    body = {
        "price_mode": "list",
        "lines": [
            {
                "key": "k", "line_type": "product", "product_id": host.id, "combo_id": cb.id,
                "tag_template_id": template_id, "price_type": "selling",
                "parts": [{"product_id": fixed.id}, {"product_id": bare.id}],
            }
        ],
    }
    res = c.post(STAFF_PREVIEW, json=body)
    assert res.status_code == 200, res.text
    (line,) = res.json()["lines"]
    assert line["combo"]["main_label"] == "CABINET"
    assert line["combo"]["parts_line"] == "<p>{{part.code}}</p>"
    assert line["combo"]["part_labels"] == {fixed.id: "MIRROR"}
    assert line["slots"]["main"]["dimensions_lwh"] == "L780xW480xH400mm"
    by_id = {p["product_id"]: p for p in line["slots"]["fixed"]}
    assert by_id[fixed.id]["dimensions_lwh"] == "L800xW130xH700mm"
    assert by_id[bare.id]["dimensions_lwh"] == ""


def test_a_pinned_combo_without_the_new_keys_reads_defaults():
    from app.schemas.price_tag import TagCombo, TagPartData

    combo = TagCombo(id="c", name="n")
    assert (combo.main_label, combo.parts_line, combo.part_labels) == (None, None, {})
    assert TagPartData(code="a", name="b").dimensions_lwh == ""


# --------------------------------------------------------------------------- migration
def test_migration_is_additive_nullable_and_chains_onto_one_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    rev = script.get_revision(REVISION)
    assert rev is not None and len(REVISION) <= 32
    assert len(script.get_heads()) == 1

    source = Path(rev.path).read_text()
    tree = ast.parse(source)
    calls = [
        (n.args[0].value, n.args[1].args[0].value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "add_column"
    ]
    assert set(calls) == {
        ("product_combo_parts", "label"),
        ("product_combos", "main_label"),
        ("product_combos", "parts_line"),
    }
    assert "nullable=False" not in source
