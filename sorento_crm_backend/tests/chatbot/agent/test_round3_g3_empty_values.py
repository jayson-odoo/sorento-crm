"""PR 4 round 3 G3 (red): MCP read results drop empty values before the cap, and the cap is 16,000.

Plan: documentation/plans/chatbot/PLAN-agentic-unify-tools-1nov.md, round 3, G3 (crew's measurement: a projects
row is every ProjectResponse field, about half of them empty, so 8 of 15 rows fit 12,000 characters).
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.services.chatbot.agent import tools
from tests._pg_fixture import blank_session
from tests.chatbot.agent import _ported_reads_support as support
from tests.chatbot.agent._ported_reads_support import AC1, Recorder, panel_ctx, panel_turn, slugs_for
from tests.chatbot.agent._seed import seed_user

NAME = "crm_projects_list"
SLUG = {n: s for n, s, _own in AC1}[NAME]


@pytest.fixture(scope="module")
def db():
    with blank_session() as session:
        yield session


def _read(db, body):
    ctx = panel_ctx(db, seed_user(db, contact_pk=None, slugs=slugs_for(NAME, SLUG)))
    with panel_turn(ctx.user_id):
        return support.dispatch(db, ctx, NAME, None, rec=Recorder(body))


def _project_row(i: int, size: int = 1660) -> dict:
    """45 keys, 25 of them empty (about half the characters) (nulls, "" and []), the rest an id, a code, a title, timestamps, numbers."""
    row: dict = {
        "id": str(uuid.uuid4()), "code": f"PPF26{i:05d}", "title": f"ZZT project {i}",
        "created_at": "2026-10-01T08:00:00.000000", "updated_at": "2026-11-02T09:30:00.000000",
        "budget": 125000.5, "stage_count": 4, "progress": 35, "status": "Active",
    }
    for k in range(25):
        row[f"empty_field_with_a_long_name_{k:02d}"] = (None, "", [])[k % 3]
    for k in range(10):
        row[f"field_{k:02d}"] = f"value {k}"
    row["notes"] = ""
    pad = size - len(json.dumps(row))
    row["notes"] = "n" * max(pad, 0)
    live = {k: v for k, v in row.items() if v not in (None, "", [])}
    assert len(json.dumps(live)) * 14 < 15_000  # fits the new cap once empties go
    assert len(row) == 45 and abs(len(json.dumps(row)) - size) <= 10
    return row


def test_G3_empty_values_are_dropped_at_any_depth_and_falsy_values_stay(db):
    body = {"data": [{
        "keep": "x", "a": None, "b": "", "c": [], "d": {},
        "nested": {"e": None, "f": {"g": ""}}, "rows": [{"h": None, "i": 1}, {"j": []}],
        "zero": 0, "zerof": 0.0, "no": False, "szero": "0", "padded": "  x ",
    }], "total": 1}
    out = _read(db, body)
    assert out.status == "ok", (out.status, out.message)
    row = out.data["data"][0]
    for gone in ("a", "b", "c", "d", "nested"):
        assert gone not in row, (gone, row)
    assert row["rows"] == [{"i": 1}]
    assert row["zero"] == 0 and row["zerof"] == 0.0 and row["no"] is False
    assert row["szero"] == "0" and row["padded"] == "  x "
    assert row["keep"] == "x"


def test_G3_fourteen_project_rows_with_half_empty_fields_fit_one_call(db):
    rows = [_project_row(i) for i in range(14)]
    out = _read(db, {"data": rows, "total": 14})
    assert out.status == "ok", (out.status, out.message)
    assert len(out.data["data"]) == 14
    assert out.more == 0
    assert "next page" not in out.message.lower()


def test_G3_the_cap_is_sixteen_thousand():
    assert tools.RESULT_CHAR_CAP == 16_000


def test_G3_a_read_with_no_rows_is_still_empty(db):
    out = _read(db, {"data": [], "total": 0})
    assert out.status == "empty", (out.status, out.message)


def test_G3_non_empty_rows_above_the_new_cap_are_still_cut_with_the_message(db):
    body = {"data": [{"ref": f"ZZT-{i:03d}", "note": "x" * 1500} for i in range(15)], "total": 15}
    out = _read(db, body)
    assert out.status == "ok" and out.more > 0
    assert "next page" in out.message.lower() and str(out.more) in out.message


def test_G3_a_positional_list_keeps_its_nulls_and_a_list_of_dicts_drops_emptied_ones(db):
    body = {"data": [{"ref": "A"}], "labels": ["Jan", "Feb", "Mar"], "values": [10, None, 5],
            "rows": [{"a": None}, {"b": 1}], "gone": None, "also": "", "list": [], "dict": {}}
    data = _read(db, body).data
    assert data["labels"] == ["Jan", "Feb", "Mar"]
    assert data["values"] == [10, None, 5]
    assert data["rows"] == [{"b": 1}]
    for key in ("gone", "also", "list", "dict"):
        assert key not in data, key
