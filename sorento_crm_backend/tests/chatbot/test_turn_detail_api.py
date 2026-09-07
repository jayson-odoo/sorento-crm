"""`GET /system/chatbot/turns/{id}` (chatbot growth r1, Slice D1, AC-970, AC-973).

`app.services.chatbot.trace_detail.compose_trace_detail` is exercised two ways:

* directly, over hand-built `trace` records carrying every `kind` the plan names
  (`test_compose_trace_detail.py`-shaped assertions, here because the endpoint's
  `response_model` is what proves the shape actually reaches a caller) - this lane
  does not depend on the sibling `data` / `dialogue` lanes landing `TurnTrace.add`
  first, so the kind records are constructed by hand rather than produced by a
  real tool call or a real cross-domain probe;
* through a REAL turn (`engine_mod.run_turn`, the same seam `test_engine.py` uses),
  proving the endpoint composes something real off the engine's OWN stage records,
  not just off a hand-built fixture.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.services.chatbot import engine as engine_mod

from tests.chatbot.test_engine import (
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,  # noqa: F401
    stub_access,  # noqa: F401
    stub_parser,  # noqa: F401
)
from tests.chatbot.test_turns_admin_api import (
    _GRANTS,
    _permissions,  # noqa: F401
    _seed_turn,
    _trace_record,
    BASE,
    client,  # noqa: F401
    db,  # noqa: F401
    VIEW,
)


def _contact(label: str = "") -> str:
    return f"ZZT-contact-{label}-{uuid.uuid4().hex[:8]}"


class TestComposedFromHandBuiltTrace:
    """Every `kind` the plan names (AC-970), plus the ones the engine already
    writes today (`stages`, `parse`, `session`)."""

    def _row(self, db):
        contact = _contact("detail")
        trace = [
            {
                "stage": "received",
                "status": "ok",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ms": 3,
                "summary": "received",
                "why": "received",
                "facts": {},
                "error": None,
                # Matches engine.py's own shape: raw={"session_vars": session_block},
                # session_block={"session_vars": {"variables": {...}}}.
                "raw": {
                    "session_vars": {
                        "session_vars": {"variables": {"domain_hint": "master_products"}}
                    }
                },
            },
            {
                "stage": "understood",
                "status": "ok",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ms": 5,
                "summary": "Understood as a business query.",
                "why": "parsed",
                "facts": {"prompt_version": 3},
                "error": None,
                "raw": {
                    "parser_raw": {"domain_hint": "master_products"},
                    "derived": {"domain_hint": "master_products", "entities": []},
                },
            },
            {
                "kind": "tool",
                "name": "crm_master_products_list",
                "args": {"product_ids": ["p-1"]},
                "envelope": {"items": [{"fields": [{"label": "Code", "value": "SRTWC8517"}]}]},
                "ms": 42,
            },
            {
                "kind": "crossdomain",
                "rung": 1,
                "tool": "crm_incoming_stock_list",
                "args": {"product_ids": ["p-1"]},
                "rows": 2,
                "rendered": True,
            },
            {
                "kind": "reveals",
                "restricted_fields_seen": ["inventory.sellable"],
                "granted": [],
                "dropped": ["inventory.sellable"],
            },
            {
                "kind": "decay",
                "slot": "products",
                "value": "SRTWC8517",
                "set_at_turn": 1,
                "age_turns": 4,
                "age_minutes": 12,
                "reason": "ttl_exceeded",
            },
            {
                "kind": "focus",
                "slot": "domain",
                "before": "master_products",
                "after": "incoming",
                "rule": "domain_from_switch_word",
                "source": "current_message",
            },
            {
                "kind": "open_question",
                "before": {"kind": "product_pick"},
                "answer": {"picks": [1]},
                "after": None,
                "handler": "product_pick",
                "outcome": "focus.products set",
            },
            {
                "stage": "remembered",
                "status": "ok",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ms": 2,
                "summary": "remembered",
                "why": "remembered",
                "facts": {},
                "error": None,
                "raw": {
                    "session_patch": {
                        "variables": {"domain_hint": "master_products", "new_key": "x"}
                    }
                },
            },
        ]
        return _seed_turn(db, contact_respond_id=contact, trace=trace)

    def test_every_kind_renders(self, client, db):
        row = self._row(db)
        resp = client.get(f"{BASE}/{row.id}")
        assert resp.status_code == 200, resp.text
        detail = resp.json()["trace_detail"]

        assert detail["tool"] == {
            "name": "crm_master_products_list",
            "args": {"product_ids": ["p-1"]},
            "envelope": {"items": [{"fields": [{"label": "Code", "value": "SRTWC8517"}]}]},
            "ms": 42,
        }
        assert detail["crossdomain"] == [
            {
                "rung": 1,
                "tool": "crm_incoming_stock_list",
                "args": {"product_ids": ["p-1"]},
                "rows": 2,
                "rendered": True,
            }
        ]
        assert detail["reveals"] == {
            "restricted_fields_seen": ["inventory.sellable"],
            "granted": [],
            "dropped": ["inventory.sellable"],
        }
        assert detail["decay"][0]["slot"] == "products"
        assert detail["decay"][0]["reason"] == "ttl_exceeded"
        assert detail["focus"][0]["rule"] == "domain_from_switch_word"
        assert detail["open_question"]["handler"] == "product_pick"

        assert detail["parse"]["prompt_version"] == 3
        assert detail["parse"]["post_processed"] == {
            "domain_hint": "master_products",
            "entities": [],
        }

        assert detail["session"]["before"] == {"domain_hint": "master_products"}
        assert detail["session"]["after"] == {"domain_hint": "master_products", "new_key": "x"}
        assert {"key": "new_key", "change": "gained"} in detail["session"]["diff"]

        names = [s["name"] for s in detail["stages"]]
        assert "received" in names and "understood" in names and "remembered" in names

    def test_missing_kinds_render_as_empty_sections(self, client, db):
        """No `tool` / `crossdomain` / `decay` / `focus` / `open_question` /
        `reveals` entries at all - the sibling lanes have not landed - and the
        endpoint still answers 200 with empty sections, not an error."""
        contact = _contact("missing-kinds")
        row = _seed_turn(
            db,
            contact_respond_id=contact,
            trace=[_trace_record("received"), _trace_record("understood")],
        )
        resp = client.get(f"{BASE}/{row.id}")
        assert resp.status_code == 200, resp.text
        detail = resp.json()["trace_detail"]
        assert detail["tool"] is None
        assert detail["crossdomain"] == []
        assert detail["decay"] == []
        assert detail["focus"] == []
        assert detail["open_question"] is None
        assert detail["reveals"] == {"restricted_fields_seen": [], "granted": [], "dropped": []}

    def test_requires_view_permission(self, client, db):
        row = self._row(db)
        _GRANTS.clear()
        resp = client.get(f"{BASE}/{row.id}")
        assert resp.status_code == 403, resp.text
        assert VIEW in resp.text

    def test_unknown_turn_is_404(self, client, db):
        resp = client.get(f"{BASE}/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestFailedTurnStageOrder:
    """AC-973: the failing stage renders FIRST, with its error text."""

    def test_the_failed_stage_is_first(self, client, db):
        contact = _contact("failed")
        trace = [
            _trace_record("received"),
            _trace_record(
                "understood",
                status="failed",
                error="the parser returned nothing usable",
            ),
        ]
        row = _seed_turn(db, contact_respond_id=contact, status="failed", trace=trace)

        resp = client.get(f"{BASE}/{row.id}")
        assert resp.status_code == 200, resp.text
        stages = resp.json()["trace_detail"]["stages"]
        assert stages[0]["name"] == "understood"
        assert stages[0]["status"] == "failed"
        assert stages[0]["error"] == "the parser returned nothing usable"
        assert stages[1]["name"] == "received"


class TestComposedFromARealTurn:
    """AC-970: the endpoint composes something real off a turn the engine actually ran."""

    def test_a_real_turn_through_the_engine_then_the_endpoint(
        self, session_factory, seeded, stub_parser, stub_access, client, db
    ):
        stub_parser(_parser_output())
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert result.turn_id

        resp = client.get(f"{BASE}/{result.turn_id}")
        assert resp.status_code == 200, resp.text
        detail = resp.json()["trace_detail"]

        stage_names = [s["name"] for s in detail["stages"]]
        assert "received" in stage_names
        assert "understood" in stage_names
        assert detail["parse"] is not None
        assert detail["parse"]["post_processed"]["domain_hint"] == "master_products"
        assert detail["session"]["before"] == {}

    def test_a_real_failed_turn_puts_understood_first(
        self, session_factory, seeded, stub_parser, client, db
    ):
        stub_parser(error=RuntimeError("boom"))

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert result.turn_id

        resp = client.get(f"{BASE}/{result.turn_id}")
        assert resp.status_code == 200, resp.text
        stages = resp.json()["trace_detail"]["stages"]
        assert stages[0]["name"] == "understood"
        assert stages[0]["status"] == "failed"
        assert stages[0]["error"]
