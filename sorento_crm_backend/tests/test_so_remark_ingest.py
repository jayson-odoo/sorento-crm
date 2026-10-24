"""FULFIL-SO-REMARK ingest (AC-1, AC-2): ship_info, line_remark, section_heading.

  AC-1  stored on sales_orders / sales_order_lines; line_remark RTF stripped;
        re-ingest overwrites; a payload without the key leaves the stored value alone
  AC-2  one new alembic revision, single head, id <= 32 chars
"""
from __future__ import annotations

from pathlib import Path

from .test_ingest_documents import INGEST_SO, _so_line, _so_record, env  # noqa: F401

RTF_MOCK = r"{\rtf1\ansi\deff0 {\fonttbl {\f0 Arial;}}\f0\fs20 ***FOR STH(100)-2 UNITS MOCK UP\par}"


def _header(env, record):
    row = env.header("sales_orders", record["source_ref"])
    assert row is not None, "the order must exist before its ship_info can be read"
    return row


def _only_line(env, record):
    lines = env.so_lines(_header(env, record)["id"])
    assert len(lines) == 1
    return lines[0]


def test_ac1_create_stores_ship_info_on_the_header(env):
    record = _so_record(env, ship_info="SPONSORSHIP")

    res = env.post(INGEST_SO, [record])

    assert res.status_code == 200, res.text
    assert res.json()["records"][0]["outcome"] == "created", res.text
    assert _header(env, record)["ship_info"] == "SPONSORSHIP"


def test_ac1_create_stores_line_remark_plain_and_section_heading(env):
    line = _so_line(env, line_remark=RTF_MOCK, section_heading="MOCK UP - BLOCK 1")
    record = _so_record(env, lines=[line])

    res = env.post(INGEST_SO, [record])

    assert res.json()["records"][0]["outcome"] == "created", res.text
    stored = _only_line(env, record)
    assert "rtf" not in stored["line_remark"].lower()
    assert "{" not in stored["line_remark"]
    assert "MOCK UP" in stored["line_remark"]
    assert stored["section_heading"] == "MOCK UP - BLOCK 1"


def test_ac1_plain_line_remark_is_kept_as_typed(env):
    line = _so_line(env, line_remark="ship Friday")
    record = _so_record(env, lines=[line])

    env.post(INGEST_SO, [record])

    assert _only_line(env, record)["line_remark"] == "ship Friday"


def test_ac1_repush_with_new_values_overwrites(env):
    line = _so_line(env, line_remark="first", section_heading="HEAD A")
    record = _so_record(env, ship_info="OT06/2702", lines=[line])
    env.post(INGEST_SO, [record])

    again = dict(
        record,
        ship_info="PURCHASE REQUEST",
        lines=[dict(line, line_remark="second", section_heading="HEAD B")],
    )
    res = env.post(INGEST_SO, [again])

    assert res.json()["records"][0]["outcome"] in {"updated", "unchanged"}, res.text
    assert _header(env, record)["ship_info"] == "PURCHASE REQUEST"
    stored = _only_line(env, record)
    assert stored["line_remark"] == "second"
    assert stored["section_heading"] == "HEAD B"


def test_ac1_repush_without_the_keys_leaves_stored_values(env):
    line = _so_line(env, line_remark="keep me", section_heading="HEAD A")
    record = _so_record(env, ship_info="SPONSORSHIP", lines=[line])
    env.post(INGEST_SO, [record])

    bare_line = {k: v for k, v in line.items() if k not in {"line_remark", "section_heading"}}
    bare = {k: v for k, v in record.items() if k != "ship_info"}
    bare["lines"] = [bare_line]
    res = env.post(INGEST_SO, [bare])

    assert res.json()["records"][0]["outcome"] in {"updated", "unchanged"}, res.text
    assert _header(env, record)["ship_info"] == "SPONSORSHIP"
    stored = _only_line(env, record)
    assert stored["line_remark"] == "keep me"
    assert stored["section_heading"] == "HEAD A"


def test_ac1_canonical_schema_declares_the_new_fields():
    from app.schemas.canonical_documents import CanonicalSalesOrder

    assert "ship_info" in CanonicalSalesOrder.model_fields
    line_model = CanonicalSalesOrder.model_fields["lines"].annotation.__args__[0]
    assert {"line_remark", "section_heading"} <= set(line_model.model_fields)


def test_ac2_one_new_head_and_revision_id_within_32_chars():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, heads
    assert all(len(h) <= 32 for h in heads)
    # The columns land in a revision of this lane: its source names all three.
    text = "".join(
        p.read_text()
        for p in (root / "alembic" / "versions").glob("*.py")
        if "line_remark" in p.read_text() and "section_heading" in p.read_text()
    )
    assert "ship_info" in text, "no revision adds ship_info + line_remark + section_heading"


def test_ac2_models_carry_the_columns():
    from app.models.order import SalesOrder, SalesOrderLine

    assert SalesOrder.__table__.c.ship_info.nullable is True
    assert SalesOrderLine.__table__.c.line_remark.nullable is True
    assert SalesOrderLine.__table__.c.section_heading.nullable is True
