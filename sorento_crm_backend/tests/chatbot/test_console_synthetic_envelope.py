"""CONSOLE-SYNTH-ENVELOPE (owner, 9 Nov 2026): the Chatbot Console simulates ANY contact.

A contact with a `respond_contacts` row and no real WhatsApp turn used to answer 404
`CHATBOT_CONSOLE_NO_ENVELOPE` ("Send one real WhatsApp message from this contact first").
It now runs on a synthetic base envelope (`console_service._synthetic_envelope`), marked
`synthetic_envelope=true` on the stored envelope and on the console's trace summary.

UAC: documentation/plans/chatbot/console-synth-envelope-acceptance-criteria.md.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import console_service
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import turn_runtime
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.integration_service import RespondClient

from tests.chatbot.test_console_turn_endpoint import (  # noqa: F401 - fixtures
    CONSOLE_TURN_URL,
    NOT_SUPPORTED_OUTPUT,
    NOT_SUPPORTED_REPLY,
    _permissions,
    _run_id,
    client,
    seeded_contact_with_a_prior_turn,
    stub_console_seams,
)
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, _turn_row

STOCK_ASK = _parser_output(intent_hint="check_stock", domain_hint="inventory", demand_qty=5)


def _contact_only(session_factory, *, phone: str = "+60000000011") -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, first_name, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, 'ZZTSynth', CAST(:sv AS jsonb))"
        ),
        {"cid": str(CONTACT_ID), "phone": phone, "sv": json.dumps({"variables": {}})},
    )
    db.commit()


def _seed_webhook_turn(session_factory) -> None:
    db = session_factory()
    db.add(
        ChatbotTurn(
            contact_respond_id=str(CONTACT_ID),
            message_id="ZZT-synth-real-msg",
            ingress="webhook",
            envelope=json.loads(_envelope().model_dump_json()),
            is_test=False,
            status="done",
            stage="sent",
            branch_kind="business_query",
        )
    )
    db.commit()


@pytest.fixture()
def respond_sends(monkeypatch) -> list[Any]:
    """Every Respond message and every outbound HTTP request the turn tries, recorded, not made."""
    import httpx

    sends: list[Any] = []
    monkeypatch.setattr(
        RespondClient, "_post_contact_message", lambda self, ident, payload, **kw: sends.append(ident) or {}
    )

    def no_http(self, request):
        sends.append(str(request.url))
        raise httpx.ConnectError("no outbound HTTP in a console test", request=request)

    # The network transport, not `Client.send`: the TestClient's own requests use its ASGI transport.
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_http)
    return sends


def _post(client, text_body: str = "can I submit a goods receive here") -> dict[str, Any]:
    resp = client.post(
        CONSOLE_TURN_URL,
        json={"contact_respond_id": str(CONTACT_ID), "text": text_body, "run_id": _run_id()},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestContactWithNoRealTurnGetsAReply:
    def test_reply_is_marked_synthetic_and_nothing_is_sent(
        self, client, session_factory, system_settings_row, stub_console_seams, respond_sends, monkeypatch
    ):
        monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: NOT_SUPPORTED_OUTPUT)
        _contact_only(session_factory)

        body = _post(client)

        assert body["branch_kind"] == "not_supported"
        assert NOT_SUPPORTED_REPLY in body["reply_text"], body
        assert body["trace_summary"]["synthetic_envelope"] is True
        row = _turn_row(session_factory, body["turn_id"])
        assert row.is_test is True
        assert row.envelope["synthetic_envelope"] is True
        assert row.envelope["is_test"] is True and row.envelope["test_run_id"]
        # Shape check: the synthetic base claims no channel source.
        assert "channel" not in row.envelope["message"]
        assert row.envelope["contact"]["phone"] == "+60000000011"
        assert row.envelope["contact"]["firstName"] == "ZZTSynth"
        assert respond_sends == []

    def test_contact_with_real_history_still_borrows(
        self, client, session_factory, seeded_contact_with_a_prior_turn, system_settings_row,
        stub_console_seams, monkeypatch,
    ):
        monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: NOT_SUPPORTED_OUTPUT)

        body = _post(client)

        assert body["trace_summary"]["synthetic_envelope"] is False
        assert "synthetic_envelope" not in _turn_row(session_factory, body["turn_id"]).envelope


class TestBorrowRule:
    def test_a_console_row_is_never_borrowed_and_the_synthetic_base_is_fresh(self, session_factory):
        _contact_only(session_factory)
        db = session_factory()
        db.add(
            ChatbotTurn(
                contact_respond_id=str(CONTACT_ID),
                message_id=None,
                ingress="console",
                envelope={"contact": {"id": str(CONTACT_ID), "custom_fields": []}, "message": {}},
                is_test=True,
                status="processing",
                stage="sent",
            )
        )
        db.commit()

        first = console_service._borrow_envelope(session_factory(), str(CONTACT_ID))
        second = console_service._borrow_envelope(session_factory(), str(CONTACT_ID))

        assert first["synthetic_envelope"] is True
        assert first["contact"]["custom_fields"] == [{"name": "is_human_intervened", "value": "false"}]
        assert first == second and first is not second

    def test_no_contact_row_at_all_is_still_a_404(self, session_factory):
        with pytest.raises(console_service.ConsoleContactUnknown):
            console_service._borrow_envelope(session_factory(), "ZZT-no-such-contact")

    def test_phone_comes_from_the_default_workspace_row(self, session_factory, monkeypatch):
        """Two `respond_contacts` rows share one respond id (one per workspace): the
        default workspace's row wins, whatever order Postgres returns them in."""
        db = session_factory()
        for space, phone in (("ZZT-other-space", "+60000000098"), ("ZZT-default-space", "+60000000099")):
            db.execute(
                text(
                    "INSERT INTO respond_workspaces (id, space_id, name, api_key_ciphertext) "
                    "VALUES (gen_random_uuid(), :s, :s, 'ZZT-cipher')"
                ),
                {"s": space},
            )
            db.execute(
                text(
                    "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, workspace_id) "
                    "VALUES (gen_random_uuid()::text, :cid, :phone, '{}'::jsonb, "
                    "(SELECT id FROM respond_workspaces WHERE space_id = :s))"
                ),
                {"cid": str(CONTACT_ID), "phone": phone, "s": space},
            )
        db.commit()
        from app.services.chatbot.head import access as access_mod

        monkeypatch.setattr(access_mod, "default_space_id", lambda db: "ZZT-default-space")
        assert console_service._borrow_envelope(session_factory(), str(CONTACT_ID))["contact"]["phone"] == "+60000000099"
        monkeypatch.setattr(access_mod, "default_space_id", lambda db: "ZZT-other-space")
        assert console_service._borrow_envelope(session_factory(), str(CONTACT_ID))["contact"]["phone"] == "+60000000098"


class TestSyntheticAnswersMatchBorrowed:
    """The facts that decide an answer are read from the DB by contact id, not off the
    envelope: stock allowed (the profile read) and its companies (two here, the company
    scope read), both spied on as the turn makes them. The customer links seeded here
    resolve inside that same company scope.
    The same turn on the synthetic base and, once a real turn exists, on the borrowed one
    must read the same facts and give the same answer."""

    def test_same_stock_gate_customer_links_and_companies(
        self, client, session_factory, system_settings_row, stub_console_seams, respond_sends, monkeypatch
    ):
        from app.models.user import SystemSetting
        from tests.chatbot._sales_pick_helpers import _add_mocha
        from tests.chatbot.test_customer_scope_lane import _link_customers
        from tests.chatbot.test_outstanding_lane import _seed_contact
        from tests._mc_lookup_seed import MOCHA_ID

        _seed_contact(session_factory, variables={})
        _add_mocha(session_factory)
        _link_customers(session_factory, "ZZT Synth Customer A", "ZZT Synth Customer B")
        db = session_factory()
        db.execute(
            text("UPDATE respond_contacts SET chatbot_stock_allowed = false WHERE respond_io_id = :c"),
            {"c": str(CONTACT_ID)},
        )
        setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
        setting.chatbot_stock_denial_enabled = True
        db.commit()
        monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: STOCK_ASK)

        reads: dict[str, list[Any]] = {"scope": [], "profile": []}
        real_scope, real_profile = engine_mod._contact_company_scope, turn_runtime.load_profile

        def spy_scope(factory, cid):
            out = real_scope(factory, cid)
            reads["scope"].append(out)
            return out

        def spy_profile(db, cid, *a, **k):
            out = real_profile(db, cid, *a, **k)
            reads["profile"].append((out[0].stock_allowed, out[1]))
            return out

        monkeypatch.setattr(engine_mod, "_contact_company_scope", spy_scope)
        monkeypatch.setattr(turn_runtime, "load_profile", spy_profile)

        def run() -> tuple[dict[str, Any], dict[str, list[Any]]]:
            for v in reads.values():
                v.clear()
            body = _post(client, "check stock srtwc286")
            return body, {k: list(v) for k, v in reads.items()}

        synthetic, synthetic_reads = run()
        _seed_webhook_turn(session_factory)
        borrowed, borrowed_reads = run()

        assert synthetic["trace_summary"]["synthetic_envelope"] is True
        assert borrowed["trace_summary"]["synthetic_envelope"] is False
        assert synthetic["branch_kind"] == borrowed["branch_kind"] == "stock_denied"
        assert synthetic["reply_text"] == borrowed["reply_text"]
        assert synthetic_reads == borrowed_reads
        assert synthetic_reads["scope"] and set(synthetic_reads["scope"][0]) == {DEFAULT_COMPANY_ID, MOCHA_ID}
        assert synthetic_reads["profile"] and synthetic_reads["profile"][0][0] is False
        assert respond_sends == []


class TestDirectIngressCountsAsRealHistory:
    """Crew pass #2269: the CRM's own respond.io webhook (`DIRECT_INGRESS`, 'respond_webhook')
    is a real WhatsApp turn too. Contact 573391060 had four of them and still got the
    synthetic envelope and the 'no real WhatsApp history' badge."""

    def test_a_respond_webhook_row_is_borrowed_not_synthesised(self, session_factory):
        from app.services.chatbot.contracts import DIRECT_INGRESS

        _contact_only(session_factory)
        db = session_factory()
        envelope = json.loads(_envelope().model_dump_json())
        envelope["contact"]["custom_fields"].append({"name": "ZZT-direct", "value": "1"})
        db.add(
            ChatbotTurn(
                contact_respond_id=str(CONTACT_ID),
                message_id="ZZT-direct-msg",
                ingress=DIRECT_INGRESS,
                envelope=envelope,
                is_test=False,
                status="done",
                stage="sent",
                branch_kind="business_query",
            )
        )
        db.commit()

        base = console_service._borrow_envelope(session_factory(), str(CONTACT_ID))

        assert "synthetic_envelope" not in base
        assert {"name": "ZZT-direct", "value": "1"} in base["contact"]["custom_fields"]
