"""AGENTIC-UNIFY PR 4, slice 1 (red): what dispatch does with each ported read's raw route answer (AC-6).

The route's body is fed through a fake `call`; the user is a real non-admin holding the tool's slug on the
blank Postgres schema. Covers: no rows is `empty` never a bare `ok`, an oversized list is cut with the count of
what was cut, `view=render` only on `crm_find`, an analytics body with no buckets, and a route's error body.
"""
from __future__ import annotations

import json

import pytest

from app.services.chatbot.agent import tools as agent_tools
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_user
from tests.chatbot.agent._ported_reads_support import (
    AC1,
    AC1_NAMES,
    CAPABILITIES,
    FIND,
    Recorder,
    dispatch,
    make_ctx,
    tool,
)

SLUG_OF = {name: slug for name, slug, _own in AC1}
SLUG_OF[CAPABILITIES] = None
#: Every read whose answer is the route's raw JSON (all but crm_find).
RAW = [n for n in AC1_NAMES if n != FIND]
ANALYTICS = ["crm_complaint_analytics", "crm_order_analytics"]


@pytest.fixture(scope="module")
def db():
    """One blank schema for the module; every test seeds its own uniquely named users."""
    with blank_session() as session:
        yield session


def ctx_for(db, name):
    slug = SLUG_OF[name]
    return make_ctx(seed_user(db, contact_pk=None, slugs=(slug,) if slug else ()))


# ------------------------------------------------------------------ empty


@pytest.mark.parametrize("name", RAW)
def test_AC6_a_route_answering_no_rows_is_empty_never_ok(db, name):
    out = dispatch(db, ctx_for(db, name), name, rec=Recorder({"data": []}))
    assert out.status == "empty", (out.status, out.message)
    assert out.message


@pytest.mark.parametrize("name", RAW)
def test_AC6_a_route_answering_an_explicit_empty_flag_is_empty(db, name):
    out = dispatch(db, ctx_for(db, name), name, rec=Recorder({"data": [], "total": 0, "empty": True}))
    assert out.status == "empty", (out.status, out.message)


def test_AC6_crm_find_with_no_rows_is_empty(db):
    out = dispatch(db, ctx_for(db, FIND), FIND, rec=Recorder({"has_result": False, "items": []}))
    assert out.status == "empty", (out.status, out.message)


@pytest.mark.parametrize("name", ANALYTICS)
def test_AC6_an_analytics_body_with_empty_buckets_and_the_empty_flag_is_empty(db, name):
    body = {"metric": "count", "group_by": "status", "groups": [],
            "total": {"group_key": "__all__", "metric": "count", "value": 0}, "empty": True}
    out = dispatch(db, ctx_for(db, name), name, rec=Recorder(body))
    assert out.status == "empty", (out.status, out.message)


@pytest.mark.parametrize("name", ANALYTICS)
def test_AC6_an_analytics_body_with_empty_buckets_and_no_flag_is_empty(db, name):
    """Finding probe: the routes set `empty`, but a body without it (a cached or reshaped answer) that has no
    buckets and a zero total must not read as an `ok` figure the model then reports as '0 complaints/orders'
    without saying nothing matched. `_is_empty` today looks only at `empty` and a `data` list."""
    body = {"metric": "count", "group_by": "status", "groups": [],
            "total": {"group_key": "__all__", "metric": "count", "value": 0}}
    out = dispatch(db, ctx_for(db, name), name, rec=Recorder(body))
    assert out.status == "empty", (out.status, out.message)


@pytest.mark.parametrize("name", ANALYTICS)
def test_AC6_an_analytics_body_with_buckets_is_ok(db, name):
    body = {"metric": "count", "group_by": "status",
            "groups": [{"group_key": "approved", "group_label": "Approved", "metric": "count", "value": 3}],
            "total": {"group_key": "__all__", "metric": "count", "value": 3}, "empty": False}
    out = dispatch(db, ctx_for(db, name), name, rec=Recorder(body))
    assert out.status == "ok", (out.status, out.message)
    assert out.data["groups"][0]["value"] == 3


# ------------------------------------------------------------------ capped, counted


def _rows(n: int) -> list[dict]:
    return [{"ref": f"ZZT-{i:04d}", "note": "x" * 120} for i in range(n)]


@pytest.mark.parametrize("name", RAW)
def test_AC6_an_oversized_list_is_cut_to_the_cap_with_the_count_of_what_was_cut(db, name):
    out = dispatch(db, ctx_for(db, name), name, rec=Recorder({"data": _rows(300), "total": 300}))
    assert out.status == "ok", (out.status, out.message)
    kept = len(out.data["data"])
    assert 0 < kept < 300
    assert out.more == 300 - kept
    assert len(json.dumps(out.data, default=str)) <= agent_tools.RESULT_CHAR_CAP


def test_AC6_crm_find_oversized_items_are_cut_and_counted(db):
    body = {"has_result": True, "items": _rows(300)}
    out = dispatch(db, ctx_for(db, FIND), FIND, rec=Recorder(body))
    assert out.status == "ok", (out.status, out.message)
    kept = len(out.data["items"])
    assert 0 < kept < 300
    assert out.more == 300 - kept


@pytest.mark.parametrize("name", RAW)
def test_AC6_a_short_list_is_returned_whole_with_nothing_cut(db, name):
    out = dispatch(db, ctx_for(db, name), name, rec=Recorder({"data": _rows(3), "total": 3}))
    assert out.status == "ok", (out.status, out.message)
    assert len(out.data["data"]) == 3 and out.more == 0


# ------------------------------------------------------------------ the view param


@pytest.mark.parametrize("name", RAW)
def test_AC6_every_read_but_find_is_called_without_the_render_view(db, name):
    rec = Recorder({"data": _rows(1)})
    dispatch(db, ctx_for(db, name), name, rec=rec)
    assert [c[0] for c in rec.calls] == [name]
    assert "view" not in rec.calls[0][1], rec.calls[0][1]


def test_AC6_crm_find_is_called_with_the_render_view(db):
    rec = Recorder({"has_result": True, "items": [{"ref": "ZZT-1"}]})
    dispatch(db, ctx_for(db, FIND), FIND, rec=rec)
    assert rec.calls and rec.calls[0][1].get("view") == "render", rec.calls


@pytest.mark.parametrize("name", AC1_NAMES)
def test_AC6_a_model_chosen_view_is_never_sent_through(db, name):
    rec = Recorder()
    out = dispatch(db, ctx_for(db, name), name, {"view": "raw"}, rec=rec)
    assert out.status == "ok", (out.status, out.message)
    expected = "render" if name == FIND else None
    assert rec.calls[0][1].get("view") == expected


# ------------------------------------------------------------------ an error body


@pytest.mark.parametrize("name", RAW)
def test_AC6_a_route_error_body_is_not_ok(db, name):
    body = {"status_code": 404, "detail": "No project with that reference."}
    out = dispatch(db, ctx_for(db, name), name, rec=Recorder(body))
    assert out.status == "invalid", (out.status, out.message)
    assert "No project" in out.message


@pytest.mark.parametrize("name", RAW)
def test_AC6_a_route_refusal_body_is_denied(db, name):
    body = {"status_code": 403, "detail": "Not available with access to your own records only."}
    out = dispatch(db, ctx_for(db, name), name, rec=Recorder(body))
    assert out.status == "denied", (out.status, out.message)


@pytest.mark.parametrize("name", RAW)
def test_AC6_the_registry_row_exists_and_is_not_a_presenter_tool(db, name):
    assert tool(name).render is False
