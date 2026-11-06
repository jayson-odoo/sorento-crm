"""PRICETAG-COMBO: the new combo columns, their PATCH contract and the migration.

UAC: `documentation/plans/dealer-kit/price-tag-combo-template-fields-acceptance-criteria.md`
(AC-0.1, AC-1.1 to AC-1.5).

Written test-FIRST (PRINCIPLES.md Phase 2). None of the columns exist yet, so every
case is red for one reason: the column, the PATCH key or the migration is missing.
The model is imported inside each test where it matters so one missing attribute
fails one test, not the whole file.

Harness borrowed from `tests/test_product_combos.py` (auth + company scope overrides,
real FK chain per test). Synthetic figures only.
"""
from __future__ import annotations

import ast
import glob
from decimal import Decimal
from pathlib import Path

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.audit import AuditLog
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners

from tests._pg_fixture import blank_session
from tests.test_product_combos import (  # noqa: F401  (fixtures + helpers reused as-is)
    COMBO,
    COMBO_PART,
    COMBO_PARTS,
    COMBOS,
    EDIT,
    MOCHA,
    VIEW,
    _caller,
    _clear_overrides,
    _combo,
    _mocha,
    _part,
    _product,
)

BACKEND = Path(__file__).resolve().parent.parent

COMBO_COLUMNS = {
    ("product_combos", "description"),
    ("product_combos", "free_items"),
    ("product_combos", "list_price"),
    ("product_combos", "sell_price"),
    ("product_combo_parts", "sell_price"),
    ("product_combo_parts", "topup_amount"),
    ("product_combo_parts", "is_upgrade"),
}


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _audit_listeners():
    register_company_scope_listeners()
    register_audit_listeners()


def _num(value):
    return None if value is None else Decimal(str(value))


# --------------------------------------------------------------------------- AC-0.1


def _combo_migration_path() -> Path:
    """The one revision file that adds the combo columns (found by content, so the
    coder is free to name it)."""
    hits = []
    for name in sorted(glob.glob(str(BACKEND / "alembic" / "versions" / "*.py"))):
        text = Path(name).read_text()
        if "product_combo_parts" in text and "topup_amount" in text and "is_upgrade" in text:
            hits.append(Path(name))
    assert len(hits) == 1, f"expected exactly one migration adding the combo columns, found {hits}"
    return hits[0]


def _add_column_calls(path: Path) -> list[tuple[str, str, ast.Call]]:
    tree = ast.parse(path.read_text())
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_column"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[1], ast.Call)
            and node.args[1].args
            and isinstance(node.args[1].args[0], ast.Constant)
        ):
            found.append((node.args[0].value, node.args[1].args[0].value, node.args[1]))
    return found


def test_ac_0_1_the_migration_adds_exactly_the_seven_combo_columns_and_no_table():
    path = _combo_migration_path()
    calls = _add_column_calls(path)
    assert {(t, c) for t, c, _ in calls} == COMBO_COLUMNS
    assert len(calls) == len(COMBO_COLUMNS), "each column is added once"

    source = path.read_text()
    assert "create_table" not in source, "no new combo table: columns only"
    assert "drop_table" not in source
    assert "alter_column" not in source, "nothing existing is altered"

    # Every new column is nullable or defaulted (AC-0.1). is_upgrade is NOT NULL DEFAULT false.
    for table, column, col_call in calls:
        kwargs = {kw.arg: kw.value for kw in col_call.keywords}
        nullable = kwargs.get("nullable")
        is_not_null = isinstance(nullable, ast.Constant) and nullable.value is False
        if is_not_null:
            assert "server_default" in kwargs, f"{table}.{column} is NOT NULL without a default"
    is_upgrade = next(c for t, name, c in calls if name == "is_upgrade")
    assert any(kw.arg == "server_default" for kw in is_upgrade.keywords)


def test_ac_0_1_the_revision_id_fits_and_alembic_has_one_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    path = _combo_migration_path()
    tree = ast.parse(path.read_text())
    revision = next(
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "revision" for t in node.targets)
        and isinstance(node.value, ast.Constant)
    )
    assert len(revision) <= 32, revision

    # The combo migration is in the graph and the repo has one head. It is not pinned AS the head:
    # every later migration stacks on top of it (#2073's das_0001 did, and turned this red).
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert script.get_revision(revision) is not None, revision
    heads = script.get_heads()
    assert len(heads) == 1, heads


# --------------------------------------------------------------------------- AC-1.1


def test_ac_1_1_product_combos_gains_the_four_columns_with_the_right_types():
    from sqlalchemy import Numeric, Text

    from app.models.product_combo import ProductCombo

    table = ProductCombo.__table__
    for name in ("description", "free_items"):
        assert name in table.c, f"product_combos.{name} is missing"
        assert isinstance(table.c[name].type, Text)
        assert table.c[name].nullable is True
    for name in ("list_price", "sell_price"):
        assert name in table.c, f"product_combos.{name} is missing"
        assert isinstance(table.c[name].type, Numeric)
        assert (table.c[name].type.precision, table.c[name].type.scale) == (12, 2)
        assert table.c[name].nullable is True


def test_ac_1_1_product_combo_parts_gains_sell_price_topup_and_is_upgrade():
    from sqlalchemy import Boolean, Numeric

    from app.models.product_combo import ProductComboPart

    table = ProductComboPart.__table__
    for name in ("sell_price", "topup_amount"):
        assert name in table.c, f"product_combo_parts.{name} is missing"
        assert isinstance(table.c[name].type, Numeric)
        assert (table.c[name].type.precision, table.c[name].type.scale) == (12, 2)
        assert table.c[name].nullable is True
    assert "is_upgrade" in table.c, "product_combo_parts.is_upgrade is missing"
    assert isinstance(table.c["is_upgrade"].type, Boolean)
    assert table.c["is_upgrade"].nullable is False
    assert table.c["is_upgrade"].server_default is not None


def test_ac_1_1_a_part_row_defaults_is_upgrade_to_false(db):
    host = _product(db, "SRTBF1")
    mirror = _product(db, "SRTMR1")
    part = _part(db, _combo(db, host, "3 in 1"), mirror)
    db.refresh(part)
    assert part.is_upgrade is False
    assert part.sell_price is None
    assert part.topup_amount is None


# --------------------------------------------------------------------------- AC-1.2


def test_ac_1_2_combo_patch_sets_the_four_fields_and_the_list_returns_them(db, monkeypatch):
    host = _product(db, "SRTBF2")
    combo = _combo(db, host, "3 in 1")
    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    response = client.patch(
        COMBO.format(combo_id=combo.id),
        json={
            "description": "Cabinet, mirror and basin",
            "list_price": "2500.00",
            "sell_price": "1999.00",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["description"] == "Cabinet, mirror and basin"
    assert _num(body["list_price"]) == Decimal("2500.00")
    assert _num(body["sell_price"]) == Decimal("1999.00")

    listed = client.get(COMBOS.format(product_id=host.id))
    assert listed.status_code == 200, listed.text
    (row,) = listed.json()["data"]
    assert row["description"] == "Cabinet, mirror and basin"
    assert _num(row["list_price"]) == Decimal("2500.00")
    assert _num(row["sell_price"]) == Decimal("1999.00")


def test_ac_1_2_combo_patch_leaves_an_omitted_field_alone_and_clears_an_explicit_null(
    db, monkeypatch
):
    host = _product(db, "SRTBF3")
    combo = _combo(db, host, "3 in 1")
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    url = COMBO.format(combo_id=combo.id)
    assert (
        client.patch(
            url,
            json={
                "description": "Keep me",
                "list_price": "100.00",
                "sell_price": "80.00",
            },
        ).status_code
        == 200
    )

    # Omitted = left alone.
    renamed = client.patch(url, json={"name": "4 in 1"})
    assert renamed.status_code == 200, renamed.text
    body = renamed.json()
    assert body["name"] == "4 in 1"
    assert body["description"] == "Keep me"
    assert _num(body["list_price"]) == Decimal("100.00")
    assert _num(body["sell_price"]) == Decimal("80.00")

    # Explicit null = cleared, and only the fields named.
    cleared = client.patch(url, json={"description": None, "sell_price": None})
    assert cleared.status_code == 200, cleared.text
    body = cleared.json()
    assert body["description"] is None
    assert body["sell_price"] is None
    assert _num(body["list_price"]) == Decimal("100.00")


def test_ac_1_2_part_patch_sets_the_three_fields_and_the_list_returns_them(db, monkeypatch):
    host = _product(db, "SRTBF4")
    basin = _product(db, "SRTBS4")
    combo = _combo(db, host, "3 in 1")
    part = _part(db, combo, basin, choice_group="Basin")
    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    response = client.patch(
        COMBO_PART.format(part_id=part.id),
        json={"sell_price": "350.00", "topup_amount": "120.00", "is_upgrade": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert _num(body["sell_price"]) == Decimal("350.00")
    assert _num(body["topup_amount"]) == Decimal("120.00")
    assert body["is_upgrade"] is True
    # What was there before is not disturbed.
    assert body["choice_group"] == "Basin"

    listed = client.get(COMBOS.format(product_id=host.id)).json()["data"][0]["parts"][0]
    assert _num(listed["sell_price"]) == Decimal("350.00")
    assert _num(listed["topup_amount"]) == Decimal("120.00")
    assert listed["is_upgrade"] is True


def test_ac_1_2_part_patch_leaves_omitted_alone_and_clears_explicit_null(db, monkeypatch):
    host = _product(db, "SRTBF5")
    basin = _product(db, "SRTBS5")
    combo = _combo(db, host, "3 in 1")
    part = _part(db, combo, basin, choice_group="Basin")
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    url = COMBO_PART.format(part_id=part.id)
    client.patch(url, json={"sell_price": "350.00", "topup_amount": "120.00", "is_upgrade": True})

    only_order = client.patch(url, json={"sort_order": 3})
    assert only_order.status_code == 200, only_order.text
    body = only_order.json()
    assert _num(body["sell_price"]) == Decimal("350.00")
    assert _num(body["topup_amount"]) == Decimal("120.00")
    assert body["is_upgrade"] is True

    cleared = client.patch(url, json={"sell_price": None, "topup_amount": None})
    assert cleared.status_code == 200, cleared.text
    body = cleared.json()
    assert body["sell_price"] is None
    assert body["topup_amount"] is None
    assert body["is_upgrade"] is True, "is_upgrade was not named, so it stays"


# --------------------------------------------------------------------------- AC-1.3


@pytest.mark.parametrize("field", ["list_price", "sell_price"])
def test_ac_1_3_a_negative_combo_price_is_422(db, monkeypatch, field):
    host = _product(db, "SRTBF6")
    combo = _combo(db, host, "3 in 1")
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    response = client.patch(COMBO.format(combo_id=combo.id), json={field: "-0.01"})
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("field", ["sell_price", "topup_amount"])
def test_ac_1_3_a_negative_part_price_or_topup_is_422(db, monkeypatch, field):
    host = _product(db, "SRTBF7")
    basin = _product(db, "SRTBS7")
    part = _part(db, _combo(db, host, "3 in 1"), basin)
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    response = client.patch(COMBO_PART.format(part_id=part.id), json={field: "-1"})
    assert response.status_code == 422, response.text


def test_ac_1_3_rm_zero_is_allowed_on_a_topup_and_a_price(db, monkeypatch):
    host = _product(db, "SRTBF8")
    basin = _product(db, "SRTBS8")
    combo = _combo(db, host, "3 in 1")
    part = _part(db, combo, basin)
    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    topup = client.patch(COMBO_PART.format(part_id=part.id), json={"topup_amount": "0"})
    assert topup.status_code == 200, topup.text
    assert _num(topup.json()["topup_amount"]) == Decimal("0")

    price = client.patch(COMBO.format(combo_id=combo.id), json={"sell_price": "0"})
    assert price.status_code == 200, price.text
    assert _num(price.json()["sell_price"]) == Decimal("0")


# --------------------------------------------------------------------------- AC-1.4


def test_ac_1_4_both_writes_need_the_edit_permission(db, monkeypatch):
    host = _product(db, "SRTBF9")
    basin = _product(db, "SRTBS9")
    combo = _combo(db, host, "3 in 1")
    part = _part(db, combo, basin)
    client = _caller(db, {VIEW}, monkeypatch)

    combo_write = client.patch(COMBO.format(combo_id=combo.id), json={"description": "x"})
    assert combo_write.status_code == 403, combo_write.text
    part_write = client.patch(COMBO_PART.format(part_id=part.id), json={"topup_amount": "5"})
    assert part_write.status_code == 403, part_write.text

    db.expire_all()
    db.refresh(combo)
    assert combo.description is None


def test_ac_1_4_a_host_in_another_company_answers_404_and_changes_nothing(db, monkeypatch):
    _mocha(db)
    host = _product(db, "SRTBF10")
    basin = _product(db, "SRTBS10")
    combo = _combo(db, host, "3 in 1")
    part = _part(db, combo, basin)
    client = _caller(db, {VIEW, EDIT}, monkeypatch, company_id=MOCHA)

    combo_write = client.patch(
        COMBO.format(combo_id=combo.id), json={"description": "x", "sell_price": "1"}
    )
    assert combo_write.status_code == 404, combo_write.text
    part_write = client.patch(
        COMBO_PART.format(part_id=part.id), json={"sell_price": "1", "is_upgrade": True}
    )
    assert part_write.status_code == 404, part_write.text

    db.expire_all()
    from app.models.base import company_scope

    with company_scope(db, None):
        db.refresh(combo)
        db.refresh(part)
    assert combo.description is None and combo.sell_price is None
    assert part.sell_price is None and part.is_upgrade is False


# --------------------------------------------------------------------------- AC-1.5


def _updates(db, entity_id):
    return [
        row
        for row in db.query(AuditLog)
        .filter(AuditLog.entity_id == str(entity_id), AuditLog.action == "UPDATE")
        .all()
    ]


def test_ac_1_5_a_combo_edit_lands_on_the_audit_trail_with_the_new_values(db, monkeypatch):
    host = _product(db, "SRTBF11")
    combo = _combo(db, host, "3 in 1")
    db.commit()
    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    response = client.patch(
        COMBO.format(combo_id=combo.id),
        json={"description": "Audited text", "list_price": "10.00"},
    )
    assert response.status_code == 200, response.text

    rows = _updates(db, combo.id)
    assert rows, "a combo edit must write an audit row"
    assert {row.entity_type for row in rows} == {"product_combo"}
    merged = {}
    for row in rows:
        merged.update(row.new_values or {})
    assert merged.get("description") == "Audited text"
    assert "list_price" in merged


def test_ac_1_5_a_part_edit_lands_on_the_audit_trail_with_the_new_values(db, monkeypatch):
    host = _product(db, "SRTBF12")
    basin = _product(db, "SRTBS12")
    part = _part(db, _combo(db, host, "3 in 1"), basin)
    db.commit()
    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    response = client.patch(
        COMBO_PART.format(part_id=part.id),
        json={"sell_price": "99.00", "topup_amount": "20.00", "is_upgrade": True},
    )
    assert response.status_code == 200, response.text

    rows = _updates(db, part.id)
    assert rows, "a part edit must write an audit row"
    merged = {}
    for row in rows:
        merged.update(row.new_values or {})
    assert {"sell_price", "topup_amount", "is_upgrade"} <= set(merged)
    assert merged["is_upgrade"] in (True, "true", "True")


# PRICETAG-ACCESSORIES: `free_items` is no longer written through the PATCH (the list replaced it).
@pytest.mark.parametrize("field,limit", [("description", 5000)])
def test_a_text_over_its_limit_is_422_and_at_the_limit_is_saved(db, monkeypatch, field, limit):
    host = _product(db, "SRTBF20")
    combo = _combo(db, host, "3 in 1")
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    url = COMBO.format(combo_id=combo.id)
    assert client.patch(url, json={field: "x" * (limit + 1)}).status_code == 422
    assert client.patch(url, json={field: "x" * limit}).status_code == 200
