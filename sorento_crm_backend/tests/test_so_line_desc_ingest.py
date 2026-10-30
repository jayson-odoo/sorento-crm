"""SO-LINE-DESC ingest (AC-1, AC-2, AC-3, AC-8): the canonical sales order line's `product_name`
(AutoCount SODTL.Description) is stored on `sales_order_lines.description`, with the same
presence rules as `line_remark`; a product push never touches the OI-email tick."""
from __future__ import annotations

from sqlalchemy import text

from .test_ingest_documents import INGEST_SO, _so_line, _so_record, env  # noqa: F401
from .test_ingest_item_classes import (  # noqa: F401
    INGEST_PRODUCTS,
    MARKER,
    _ref,
    env as class_env,
    unique_code,
)

PUSH = "SORENTO ACCESSORIES SRTWC8320-S150-UF PUSH BUTTON ONLY"


def _stored(env, record):
    header = env.header("sales_orders", record["source_ref"])
    assert header is not None
    return env.so_lines(header["id"])[0]


def _push(env, record):
    res = env.post(INGEST_SO, [record])
    assert res.status_code == 200, res.text
    assert res.json()["records"][0]["outcome"] in {"created", "updated", "unchanged"}, res.text
    return res


def test_ac1_product_name_is_stored_trimmed_as_the_line_description(env):
    record = _so_record(env, lines=[_so_line(env, product_name=f"  {PUSH}  ")])

    _push(env, record)

    assert _stored(env, record)["description"] == PUSH


def test_ac2_an_absent_key_keeps_it_and_an_explicit_null_clears_it(env):
    line = _so_line(env, product_name=PUSH)
    record = _so_record(env, lines=[line])
    _push(env, record)

    without_key = {k: v for k, v in line.items() if k != "product_name"}
    _push(env, dict(record, lines=[dict(without_key, qty_ordered=11)]))
    assert _stored(env, record)["description"] == PUSH

    _push(env, dict(record, lines=[dict(line, product_name=None)]))
    assert _stored(env, record)["description"] is None


def test_ac2_a_blank_or_whitespace_value_stores_nothing(env):
    for blank in ("", "   "):
        record = _so_record(env, lines=[_so_line(env, product_name=blank)])
        _push(env, record)
        assert _stored(env, record)["description"] is None, repr(blank)


def test_ac2_a_later_value_replaces_the_earlier_one(env):
    line = _so_line(env, product_name="REPLACE ACCESORIES JOIN PART")
    record = _so_record(env, lines=[line])
    _push(env, record)

    _push(env, dict(record, lines=[dict(line, product_name=PUSH)]))

    assert _stored(env, record)["description"] == PUSH


def test_ac3_the_line_still_resolves_its_product_whatever_the_description_says(env):
    line = _so_line(env, product_name=PUSH)
    record = _so_record(env, lines=[line])

    _push(env, record)

    stored = _stored(env, record)
    assert stored["description"] == PUSH
    assert str(stored["product_id"]) == str(
        env.refs.resolve(entity_type="products", source_ref=line["product_ref"])
    )


def test_ac8_a_product_push_never_changes_the_oi_email_tick(class_env):
    env = class_env
    code = unique_code(MARKER)
    product = {
        "source_ref": _ref("ITEM"),
        "code": code,
        "name": f"{MARKER} product",
        "category_code": env._category.category_code,
        "uom_code": env._uom.uom_code,
    }
    created = env.post(INGEST_PRODUCTS, [product]).json()["records"][0]
    assert created["outcome"] == "created", created
    read = text("SELECT show_so_line_description FROM products WHERE id = :id")
    assert env.db.execute(read, {"id": created["entity_id"]}).scalar() is False

    env.db.execute(
        text("UPDATE products SET show_so_line_description = true WHERE id = :id"),
        {"id": created["entity_id"]},
    )
    again = env.post(INGEST_PRODUCTS, [dict(product, name=f"{MARKER} renamed")]).json()
    assert again["records"][0]["outcome"] == "updated", again

    assert env.db.execute(read, {"id": created["entity_id"]}).scalar() is True
