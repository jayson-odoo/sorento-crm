"""A9 / AC-970: `TurnTrace.add`'s events reach `chatbot.turns.trace`, and the turn-detail
reader finds them there.

`documentation/plans/chatbot/PLAN-chatbot-growth-r1.md` Slice A / Slice D.

The gap this closes is the whole point of the file. `trace.add` was wired through
`run_fetch` and `run_crossdomain` and appended to a list that nothing persisted, so the
Slice D reader (`app/services/chatbot/trace_detail.py`, on the trace-UI lane) would have
rendered an empty `tool` / `crossdomain` / `reveals` section on every real turn while every
unit test of `add` passed. Only an end-to-end turn that then READS THE COLUMN can catch
that, which is what this file does.

The turn is real: `engine.run_turn` against the Postgres blank-schema fixture, with only
the injectable seams stubbed (`ResolveGateServices` / `FetchServices` / `AnswerServices`)
plus the parser and the access check. `run_until_exit`, `run_fetch`, `output_structurer`,
the tail and `_close_turn` all run unmocked, which is where the persistence actually
happens.

`_tool` / `_reveals` / `_cap_envelope` below are COPIES of `trace_detail.py`'s own, taken
verbatim from `origin/feat/chatbot-growth-trace-ui` (PR #733). That branch is not an
ancestor of this one, so importing the module is not possible yet; copying its reader is
what makes "the writer and the reader agree on the shape" a thing this lane can prove
rather than assert. When #733 merges, delete the copies and import the module - the
assertions do not change.
"""
from __future__ import annotations

import json
from typing import Any

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot.lanes.business.services import (
    AnswerServices,
    FetchServices,
    ResolveGateServices,
)
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_engine import (  # noqa: F401 - re-exported fixtures used by name
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)

# --------------------------------------------------------------------------- #
# Copied from `trace_detail.py` on feat/chatbot-growth-trace-ui (PR #733).
# --------------------------------------------------------------------------- #

TOOL_ENVELOPE_BYTE_CAP = 8_192


def _kind_records(records: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [r for r in records if r.get("kind") == kind]


def _stage_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if r.get("kind") is None and r.get("stage") is not None]


def _cap_envelope(envelope: Any) -> Any:
    if envelope is None:
        return None
    try:
        encoded = json.dumps(envelope, default=str, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return {"truncated": True, "note": "payload is not JSON-serialisable"}
    encoded_bytes = encoded.encode("utf-8")
    if len(encoded_bytes) <= TOOL_ENVELOPE_BYTE_CAP:
        return json.loads(encoded)
    return {
        "truncated": True,
        "bytes": len(encoded_bytes),
        "head": encoded_bytes[:TOOL_ENVELOPE_BYTE_CAP].decode("utf-8", errors="ignore"),
    }


def _tool(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    entries = _kind_records(records, "tool")
    if not entries:
        return None
    entry = entries[-1]
    return {
        "name": entry.get("name"),
        "args": entry.get("args"),
        "envelope": _cap_envelope(entry.get("envelope")),
        "ms": entry.get("ms"),
    }


def _reveals(records: list[dict[str, Any]]) -> dict[str, Any]:
    entries = _kind_records(records, "reveals")
    entry = entries[-1] if entries else {}
    return {
        "restricted_fields_seen": entry.get("restricted_fields_seen") or [],
        "granted": entry.get("granted") or [],
        "dropped": entry.get("dropped") or [],
    }


# --------------------------------------------------------------------------- #
# The turn.
# --------------------------------------------------------------------------- #

PRODUCT_UUID = "11111111-1111-1111-1111-111111111111"
STOCK_ENVELOPE = {
    "result_type": "stock",
    "intro": "Stock details found for the requested products.",
    "items": [
        {
            "fields": [
                {"label": "Product Code", "value": "SRTWC8517"},
                {"label": "On Hand", "value": 12},
            ]
        }
    ],
    "summary_items": [],
    "has_result": True,
}


def _resolved_bundle() -> ResolveGateServices:
    def _resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "tokens": ["SRTWC8517"],
            "resolutions": [
                {
                    "raw": "SRTWC8517",
                    "matches": [
                        {
                            "uuid": PRODUCT_UUID,
                            "entity_type": "product",
                            "canonical_code": "SRTWC8517",
                        }
                    ],
                }
            ],
            "unresolved_tokens": [],
        }

    return ResolveGateServices(
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
        resolve_entity=_resolve_entity,
        probe=lambda **_: None,
    )


def _fetch_services(envelope: dict[str, Any]) -> FetchServices:
    return FetchServices(
        embed=lambda query: [0.0, 0.0, 0.0],
        tool_search=lambda embedding, *, query, domain: [
            {"name": "crm_inventory_stock_balance_list", "similarity": 0.9}
        ],
        mcp_call=lambda name, args: json.dumps(envelope),
    )


def _answer_services() -> AnswerServices:
    return AnswerServices(
        mcp_probe=lambda name, args: {"answers": [], "has_result": False},
        family_fetch=lambda query: {"data": []},
    )


def _run_a_stock_turn(session_factory, monkeypatch, *, envelope=None):
    from app.services.chatbot import engine as engine_mod

    from app.models.user import SystemSetting

    set_chatbot_switches(session_factory, business_lane=True)
    db = session_factory()
    row = db.query(SystemSetting).first()
    row.chatbot_completed_lanes = ["business_query"]
    db.commit()
    bundle = _resolved_bundle()
    monkeypatch.setattr(
        engine_mod.business_services,
        "production_services",
        lambda db, *, space_id=None: bundle,
    )
    monkeypatch.setattr(
        engine_mod.business_services,
        "fetch_services",
        lambda db: _fetch_services(envelope if envelope is not None else STOCK_ENVELOPE),
    )
    monkeypatch.setattr(
        engine_mod.business_services,
        "answer_services_for",
        lambda session_factory: _answer_services(),
    )
    result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
    row = (
        session_factory()
        .query(ChatbotTurn)
        .filter(ChatbotTurn.id == result.turn_id)
        .first()
    )
    return result, list(row.trace or [])


class TestTheToolEventIsPersistedAndReadable:
    def test_a_real_turn_writes_a_tool_entry_the_reader_renders(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """AC-970's `tool` section, end to end: the engine calls one MCP tool, the event
        lands in `chatbot.turns.trace`, and `trace_detail._tool` composes a section with
        the tool's name, its arguments and its envelope."""
        stub_parser(
            _parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                entities=[{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
            )
        )
        stub_access()

        result, trace = _run_a_stock_turn(session_factory, monkeypatch)
        assert result.status == "done", result.error

        tool = _tool(trace)
        assert tool is not None, (
            "no `tool` entry in the persisted trace - trace.add's events are not reaching "
            "chatbot.turns.trace, so the turn-detail screen renders an empty tool section "
            "on every real turn"
        )
        assert tool["name"] == "crm_inventory_stock_balance_list"
        assert tool["args"]["product_ids"] == [PRODUCT_UUID]
        assert tool["envelope"]["result_type"] == "stock"
        assert isinstance(tool["ms"], int)

    def test_the_events_come_after_every_stage_record(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """The stage timeline is read top to bottom, so an event interleaved into it would
        read as a stage with no summary."""
        stub_parser(
            _parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                entities=[{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
            )
        )
        stub_access()

        _, trace = _run_a_stock_turn(session_factory, monkeypatch)

        kinds = [entry.get("kind") is not None for entry in trace]
        assert True in kinds, "no events were persisted at all"
        first_event = kinds.index(True)
        assert all(kinds[first_event:]), (
            "a stage record was persisted after an event: "
            + ", ".join(str(e.get("kind") or e.get("stage")) for e in trace)
        )
        assert len(_stage_records(trace)) >= 5

    def test_every_stage_record_survived_the_join(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """`persisted()` adds events; it must not drop or reshape a single stage record."""
        stub_parser(
            _parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                entities=[{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
            )
        )
        stub_access()

        _, trace = _run_a_stock_turn(session_factory, monkeypatch)

        stages = [r["stage"] for r in _stage_records(trace)]
        assert stages[:4] == ["received", "understood", "access", "routed"]
        for record in _stage_records(trace):
            assert record["summary"] and record["why"]
            assert "raw" in record

    def test_a_reveals_event_is_persisted_when_the_envelope_restricts_a_field(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """AC-970's `reveals` section. `check_access` returns `attributes: None` until
        Slice C, so every restricted key is dropped by construction today - which is the
        answer the section must show, not an empty one."""
        stub_parser(
            _parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                entities=[{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
            )
        )
        stub_access()

        restricted = {
            **STOCK_ENVELOPE,
            "restricted_fields": {"Sellable": "inventory.sellable"},
        }
        _, trace = _run_a_stock_turn(session_factory, monkeypatch, envelope=restricted)

        reveals = _reveals(trace)
        assert reveals["restricted_fields_seen"] == ["Sellable"]
        assert reveals["granted"] == []
        assert reveals["dropped"] == ["Sellable"]


class TestTheEnvelopeIsCappedAtWriteTime:
    def test_a_large_envelope_is_truncated_with_a_marker_in_the_column(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """AC-970 caps the envelope at 8 KB. Capping only on READ would still write the
        whole thing into a row that is kept forever, so the cap is applied here, at
        `trace.add`, and the marker says the truth instead of showing a silently
        shortened object."""
        stub_parser(
            _parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                entities=[{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
            )
        )
        stub_access()

        huge = {
            **STOCK_ENVELOPE,
            "items": [
                {
                    "fields": [
                        {"label": "Product Code", "value": f"SRTWC{index:05d}"},
                        {"label": "On Hand", "value": index},
                        {"label": "Note", "value": "x" * 200},
                    ]
                }
                for index in range(200)
            ],
        }
        _, trace = _run_a_stock_turn(session_factory, monkeypatch, envelope=huge)

        tool = _tool(trace)
        assert tool is not None
        assert tool["envelope"]["truncated"] is True
        assert tool["envelope"]["bytes"] > TOOL_ENVELOPE_BYTE_CAP
        assert len(tool["envelope"]["head"].encode("utf-8")) <= TOOL_ENVELOPE_BYTE_CAP
        # The cap is the WRITE side's: the reader's own `_cap_envelope` had nothing left
        # to do, which is what stops the row growing without bound.
        raw_entry = _kind_records(trace, "tool")[-1]
        assert raw_entry["envelope"]["truncated"] is True

    def test_a_multibyte_envelope_is_cut_on_bytes_and_still_decodes(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """A code-point cut on a Chinese envelope either undercounts against the byte cap
        or slices a character in half, and the column is JSONB - an invalid string would
        fail the write, not degrade."""
        stub_parser(
            _parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                entities=[{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
            )
        )
        stub_access()

        chinese = {
            **STOCK_ENVELOPE,
            "items": [
                {"fields": [{"label": "备注", "value": "上次进货" * 2000}]}
            ],
        }
        _, trace = _run_a_stock_turn(session_factory, monkeypatch, envelope=chinese)

        tool = _tool(trace)
        assert tool is not None
        assert tool["envelope"]["truncated"] is True
        assert len(tool["envelope"]["head"].encode("utf-8")) <= TOOL_ENVELOPE_BYTE_CAP
        assert isinstance(tool["envelope"]["head"], str)


class TestResumeKeepsTheTwoListsApart:
    def test_a_resumed_trace_puts_new_stages_among_the_stages(self) -> None:
        """A delegated turn's tail resumes the head's trace and appends `replied` /
        `remembered`. Those are STAGES and must land among the stage records, not after
        the head's tool event."""
        from app.services.chatbot import trace as trace_mod

        head = trace_mod.TurnTrace()
        head.record("received", summary="Received a message.", why="A customer wrote in.")
        head.add("tool", {"name": "crm_master_products_list", "args": {}, "ms": 1})
        persisted = head.persisted()

        tail = trace_mod.TurnTrace.resume(persisted)
        tail.record("replied", summary="Replied with a list.", why="The tool returned rows.")

        joined = tail.persisted()
        assert [entry.get("stage") for entry in joined[:2]] == ["received", "replied"]
        assert joined[-1]["kind"] == "tool"
