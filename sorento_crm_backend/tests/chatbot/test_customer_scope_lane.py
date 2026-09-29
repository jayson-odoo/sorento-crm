"""Phase 2 RED tests - a linked contact is scoped to its customers, "my" means them.

`documentation/plans/chatbot/PLAN-chatbot-customer-scope-29sep.md` (Design D1, D3, D4) and
`chatbot-customer-scope-29sep-acceptance-criteria.md` AC-CS-01 to AC-CS-05, AC-CS-10 to
AC-CS-15, AC-CS-22 to AC-CS-26, AC-CS-30, AC-CS-33, AC-CS-34. Written BEFORE any of the
wiring exists.

Every turn is one real `engine.run_turn` through the harness the outstanding report lane
and the top selling lane use (`tests/chatbot/test_outstanding_lane.py::_run_turn`): parser,
access, resolver and MCP faked. The parser is faked, so the verdict dict passed as `qf` is
what the engine reads, `self_reference: True` included. Every assertion is on the captured
`(tool, args)` list, the reply text, and (where named) the session's open question.

Tester's choices, made explicit:

* The report is asked as `order_status="outstanding_both"`, not bare `"outstanding"`: a bare
  "outstanding" arms the DOCUMENT question ("Outstanding for which document?") and calls no
  tool (`TestBareOutstandingWithKeyArmsScopeQuestion`), which would hide the customer scope
  behind an unrelated question. The scope question these ACs speak of is the gate's
  "which customer / product?".
* The fake resolver is deliberately WRONG-TARGET where a scoped word is expected to be
  answered from the links ("own a" resolves to HANLIM's uuid), so an engine that still asks
  the generic resolver about a linked customer's own word fails visibly instead of passing
  by coincidence.
* `contact_customer_scope` is looked up through its MODULE (`app.services.
  contact_customer_scope.contact_customer_scope`); AC-CS-05's spy patches that attribute,
  so callers must reference it as `module.contact_customer_scope(...)`, not bind it with
  `from ... import` at import time.
* Links are seeded with an explicit `created_at` one second apart so "link order" is
  deterministic (`list_links` orders by `created_at`).

Postgres only (`session_factory`, blank schema). Every row seeded here.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.services.chatbot.lanes.business.services import ResolveGateServices
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import customer as seed_customer
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_outstanding_lane import (
    CONTACT_ID,
    HANLIM_UUID_1,
    REPORT_HIT,
    _ambiguous_hanlim_resolve_services,
    _resolve_services,
    _run_turn,
    _seed_contact,
    _session_of,
)

REPORT = "crm_outstanding_report"
ORDERS = "crm_order_management_orders_list"
SALES = "crm_sales_report"
OUTSTANDING_KEY = "sales_orders.outstanding"
SALES_KEY = "sales_orders.sales_report"
ORDER_UUID = "cccccccc-cccc-cccc-cccc-cccccccccccc"

OWN_A = "ZZT OWN A"


def refusal(*names: str) -> str:
    """AC-CS-11: `A.` / `A and B.` / `A, B and C.` in link order."""
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"Sorry, that isn't under your account. I can only check on {joined}."


def _ent(raw: str, hint: str = "customer") -> dict[str, Any]:
    return {"raw": raw, "hint": hint, "canonical_code": None, "current_message": True, "confident": True}


def _ask(entities: list[dict[str, Any]] | None = None, **over: Any) -> dict[str, Any]:
    """An outstanding report ask (both documents, so the tool is called directly)."""
    base: dict[str, Any] = dict(
        domain_hint="order",
        intent_hint="check_order",
        order_status="outstanding_both",
        entities=entities or [],
    )
    base.update(over)
    return _parser_output(**base)


def _turn(session_factory, monkeypatch, qf, body="outstanding for hanlim", *, attributes=(OUTSTANDING_KEY,), **kw):
    result, captured = _run_turn(
        session_factory, monkeypatch, qf=qf, text_body=body,
        msg_id=f"ZZT-cscope-{uuid.uuid4().hex[:10]}", attributes=list(attributes), **kw,
    )
    return ((result.reply or {}).get("text") or ""), captured


def _calls(captured, tool: str) -> list[dict[str, Any]]:
    return [args for name, args in captured if name == tool]


def _open_question(session_factory) -> dict[str, Any]:
    return _session_of(session_factory).get("open_question") or {}


def _link_customers(session_factory, *names: str, codes: dict[str, str] | None = None) -> list[str]:
    """Link the harness contact to one customer per name, in this order. Returns the ids."""
    db = session_factory()
    ids: list[str] = []
    for i, name in enumerate(names):
        row = seed_customer(db, company_id=DEFAULT_COMPANY_ID, name=name)
        if codes and name in codes:
            row.customer_code = codes[name]
            db.flush()
        db.execute(
            text(
                "INSERT INTO respond_contact_customers (id, contact_id, customer_id, company_id, created_at) "
                "SELECT gen_random_uuid(), id, :cust, :company, "
                "TIMESTAMP '2026-01-01 00:00:00' + make_interval(secs => :i) "
                "FROM respond_contacts WHERE respond_io_id = :cid"
            ),
            {"cust": str(row.id), "company": DEFAULT_COMPANY_ID, "cid": str(CONTACT_ID), "i": i},
        )
        ids.append(str(row.id))
    db.commit()
    return ids


def _other_customer(session_factory, name: str, code: str | None = None) -> str:
    """A customer nobody is linked to."""
    db = session_factory()
    row = seed_customer(db, company_id=DEFAULT_COMPANY_ID, name=name)
    if code:
        row.customer_code = code
        db.flush()
    db.commit()
    return str(row.id)


def _give_access_type(session_factory, name: str, *, active: bool = True) -> None:
    db = session_factory()
    code = f"zzt_at_{uuid.uuid4().hex[:12]}"
    db.execute(
        text("INSERT INTO contact_access_types (code, name, is_active) VALUES (:code, :name, :active)"),
        {"code": code, "name": name, "active": active},
    )
    db.execute(
        text(
            "INSERT INTO respond_contact_access_types (contact_id, access_type_code) "
            "SELECT id, :code FROM respond_contacts WHERE respond_io_id = :cid"
        ),
        {"code": code, "cid": str(CONTACT_ID)},
    )
    db.commit()


def _reset_session(session_factory) -> None:
    db = session_factory()
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE respond_io_id = :cid"),
        {"sv": '{"variables": {}}', "cid": str(CONTACT_ID)},
    )
    db.commit()


def _spied(services: ResolveGateServices) -> tuple[ResolveGateServices, list[list[str]]]:
    """The same services, recording the tokens every `resolve_entity` call was asked about."""
    looked_up: list[list[str]] = []
    inner = services.resolve_entity

    def _spy(body):
        looked_up.append([str(t) for t in (body.get("tokens") or [])])
        return inner(body)

    return services.__class__(access_types=services.access_types, resolve_entity=_spy, probe=services.probe), looked_up


def _hanlim_services() -> ResolveGateServices:
    """The ambiguous HANLIM book: two customers answer the word "hanlim"."""
    return _ambiguous_hanlim_resolve_services(lambda **_: {"items": [], "has_result": False})


def _asked_about(looked_up: list[list[str]], word: str) -> bool:
    return any(word.lower() in token.lower() for tokens in looked_up for token in tokens)


NO_SCOPE_QUESTION = ("which customer", "which product", "outstanding for which document")


def _assert_no_question(reply: str) -> None:
    low = reply.lower()
    for phrase in NO_SCOPE_QUESTION:
        assert phrase not in low, (phrase, reply)


# --------------------------------------------------------------------------- #
# Who is scoped: AC-CS-01 to AC-CS-05
# --------------------------------------------------------------------------- #


class TestWhoIsScoped:
    def test_one_link_no_office_type_is_scoped(self, session_factory, monkeypatch) -> None:
        """AC-CS-01: one link, no office type -> the ask is scoped to that customer id, even
        though the (wrong-target) resolver would have named someone else for the word."""
        _seed_contact(session_factory, variables={})
        (own_id,) = _link_customers(session_factory, OWN_A)
        reply, captured = _turn(
            session_factory, monkeypatch, _ask([_ent("own a")]), "outstanding for own a",
            matches={"own a": {"uuid": HANLIM_UUID_1, "entity_type": "customer", "canonical_code": "300-H070"}},
            mcp_response=REPORT_HIT,
        )
        (args,) = _calls(captured, REPORT)
        assert args["customer_ids"] == [own_id], args
        assert HANLIM_UUID_1 not in str(captured)

    def test_active_office_type_is_staff_even_when_linked(self, session_factory, monkeypatch) -> None:
        """AC-CS-02: an ACTIVE office type is staff whatever else it holds: the generic
        resolver and its picker run, never the refusal."""
        _seed_contact(session_factory, variables={})
        _link_customers(session_factory, OWN_A)
        _give_access_type(session_factory, "Sorento Office")
        _give_access_type(session_factory, "Sorento Dealer")
        reply, captured = _turn(
            session_factory, monkeypatch, _ask([_ent("hanlim")]), resolve_services=_hanlim_services(),
        )
        assert "Which customer" in reply, reply
        assert "under your account" not in reply
        assert captured == []

    def test_unlinked_contact_is_unchanged(self, session_factory, monkeypatch) -> None:
        """AC-CS-03: no link, no office type -> today's behaviour: the picker, no refusal,
        no forced customer ids."""
        _seed_contact(session_factory, variables={})
        reply, captured = _turn(
            session_factory, monkeypatch, _ask([_ent("hanlim")]), resolve_services=_hanlim_services(),
        )
        assert "Which customer" in reply, reply
        assert "under your account" not in reply
        assert captured == []

    def test_inactive_office_type_does_not_make_staff(self, session_factory, monkeypatch) -> None:
        """AC-CS-04: an inactive office type is no office type: one link still scopes, and
        another customer's word gets the refusal line."""
        _seed_contact(session_factory, variables={})
        _link_customers(session_factory, OWN_A)
        _give_access_type(session_factory, "Sorento Office", active=False)
        _give_access_type(session_factory, "Sorento Dealer")
        reply, captured = _turn(
            session_factory, monkeypatch, _ask([_ent("hanlim")]), resolve_services=_hanlim_services(),
        )
        assert reply.strip() == refusal(OWN_A), reply
        assert captured == []

    def test_top_selling_reads_the_shared_function(self, session_factory, monkeypatch) -> None:
        """AC-CS-05: the lane decides "scoped" through ONE function,
        `app.services.contact_customer_scope.contact_customer_scope`; a top selling turn
        from a linked contact calls it. (Red today as an ImportError: the module is new.)"""
        import app.services.contact_customer_scope as scope_mod

        real = scope_mod.contact_customer_scope
        seen: list[Any] = []

        def _spy(*args: Any, **kwargs: Any):
            seen.append((args, kwargs))
            return real(*args, **kwargs)

        monkeypatch.setattr(scope_mod, "contact_customer_scope", _spy)
        _seed_contact(session_factory, variables={})
        _link_customers(session_factory, OWN_A)
        _turn(
            session_factory, monkeypatch,
            _parser_output(
                domain_hint="order", intent_hint="check_order", order_status="top_selling", entities=[],
                rank_by="quantity", basis=None, rank_group=None, top_n=5,
            ),
            "top 5 selling items by quantity", attributes=(SALES_KEY,),
        )
        assert seen, "the top selling turn never asked the shared scope function"


# --------------------------------------------------------------------------- #
# Upstream block, before the resolver: AC-CS-10 to AC-CS-15
# --------------------------------------------------------------------------- #


class TestUpstreamBlock:
    def test_other_customer_by_name_is_refused_before_any_lookup(self, session_factory, monkeypatch) -> None:
        """AC-CS-10: the customer word matches none of the links -> the refusal line, the
        resolver is never asked about it, no picker, no MCP call, no open question."""
        _seed_contact(session_factory, variables={})
        _link_customers(session_factory, OWN_A)
        services, looked_up = _spied(_hanlim_services())
        reply, captured = _turn(session_factory, monkeypatch, _ask([_ent("hanlim")]), resolve_services=services)
        assert reply.strip() == refusal(OWN_A), reply
        assert captured == []
        assert not _asked_about(looked_up, "hanlim"), looked_up
        assert "Which customer" not in reply
        assert "HANLIM" not in reply
        assert not _open_question(session_factory), _open_question(session_factory)

    @pytest.mark.parametrize("count", [1, 2, 3])
    def test_refusal_line_names_one_two_and_three_links(self, session_factory, monkeypatch, count) -> None:
        """AC-CS-11: `A.` / `A and B.` / `A, B and C.` (link order); no escalate offer, no
        open question."""
        names = ["ZZT ALPHA CO", "ZZT BRAVO CO", "ZZT CHARLIE CO"][:count]
        _seed_contact(session_factory, variables={})
        _link_customers(session_factory, *names)
        reply, captured = _turn(
            session_factory, monkeypatch, _ask([_ent("hanlim")]), resolve_services=_hanlim_services(),
        )
        assert reply.strip() == refusal(*names), reply
        assert "escalate" not in reply.lower()
        assert captured == []
        assert not _open_question(session_factory)

    def test_own_customer_word_runs_on_its_own_ledger_without_a_picker(self, session_factory, monkeypatch) -> None:
        """AC-CS-12: the word matches a linked customer -> the fetch carries exactly that
        id, no picker, and the ambiguous HANLIM book is never consulted."""
        _seed_contact(session_factory, variables={})
        (own_id,) = _link_customers(session_factory, "ZZT HANLIM OWN")
        services, looked_up = _spied(_hanlim_services())
        reply, captured = _turn(
            session_factory, monkeypatch, _ask([_ent("hanlim")]), resolve_services=services, mcp_response=REPORT_HIT,
        )
        (args,) = _calls(captured, REPORT)
        assert args["customer_ids"] == [own_id], args
        assert "Which customer" not in reply
        assert not _asked_about(looked_up, "hanlim"), looked_up

    def test_word_matching_two_own_links_uses_both(self, session_factory, monkeypatch) -> None:
        """AC-CS-13: a word matching two links -> both ids in link order, no picker."""
        _seed_contact(session_factory, variables={})
        one, two = _link_customers(session_factory, "ZZT HANLIM ONE", "ZZT HANLIM TWO")
        reply, captured = _turn(
            session_factory, monkeypatch, _ask([_ent("hanlim")]), resolve_services=_hanlim_services(),
            mcp_response=REPORT_HIT,
        )
        (args,) = _calls(captured, REPORT)
        assert args["customer_ids"] == [one, two], args
        assert "Which customer" not in reply

    def test_other_customer_code_is_refused(self, session_factory, monkeypatch) -> None:
        """AC-CS-14: another customer's exact code is a customer word -> AC-CS-10."""
        _seed_contact(session_factory, variables={})
        _link_customers(session_factory, OWN_A)
        other_id = _other_customer(session_factory, "ZZT SOMEONE ELSE", code="ZZTX-999")
        services, looked_up = _spied(
            _resolve_services({"ZZTX-999": {"uuid": other_id, "entity_type": "customer", "canonical_code": "ZZTX-999"}})
        )
        reply, captured = _turn(
            session_factory, monkeypatch, _ask([_ent("ZZTX-999")]), "outstanding for ZZTX-999",
            resolve_services=services,
        )
        assert reply.strip() == refusal(OWN_A), reply
        assert captured == []
        assert not _asked_about(looked_up, "ZZTX-999"), looked_up
        assert "SOMEONE ELSE" not in reply

    def test_foreign_do_number_is_a_miss_inside_the_scope(self, session_factory, monkeypatch) -> None:
        """AC-CS-15: a DO number that resolves to an order uuid goes to the orders list
        with that `order_ids` AND the links as `customer_ids`; the route (not the lane)
        answers "no rows", so the reply is the ordinary miss text, never the refusal."""
        _seed_contact(session_factory, variables={})
        (own_id,) = _link_customers(session_factory, OWN_A)
        reply, captured = _turn(
            session_factory, monkeypatch,
            _parser_output(
                domain_hint="order", intent_hint="check_order", order_status=None,
                entities=[_ent("DO-ZZT-1", "order")],
            ),
            "status of DO-ZZT-1", attributes=(),
            matches={"DO-ZZT-1": {"uuid": ORDER_UUID, "entity_type": "customer_order", "canonical_code": "DO-ZZT-1"}},
        )
        (args,) = _calls(captured, ORDERS)
        assert args["order_ids"] == [ORDER_UUID], args
        assert args["customer_ids"] == [own_id], args
        assert reply.strip()
        assert "under your account" not in reply, reply


# --------------------------------------------------------------------------- #
# Self-reference: AC-CS-22 to AC-CS-26
# --------------------------------------------------------------------------- #


class TestSelfReference:
    def test_my_outstanding_with_one_link(self, session_factory, monkeypatch) -> None:
        """AC-CS-22: `self_reference: true`, outstanding, no entities -> the report runs on
        the link, no scope question. The Customer header line is the ROUTE's echo of
        `customer_name` for the ids it ran on (`orders._customer_echo`), which the presenter
        prints; the harness does not reproduce the echo, so the body handed back here carries
        it, and the echo itself is asserted on the route in
        `tests/test_customer_scope_routes.py`. `customer_ids == [own_id]` is the real guard."""
        _seed_contact(session_factory, variables={})
        (own_id,) = _link_customers(session_factory, OWN_A)
        reply, captured = _turn(
            session_factory, monkeypatch, _ask(self_reference=True), "what's my outstanding",
            mcp_response={**REPORT_HIT, "customer_name": OWN_A},
        )
        (args,) = _calls(captured, REPORT)
        assert args["customer_ids"] == [own_id], args
        _assert_no_question(reply)
        assert f"Customer: {OWN_A}" in reply, reply

    def test_my_outstanding_with_two_links_uses_both(self, session_factory, monkeypatch) -> None:
        """AC-CS-23: two links -> both ids in link order, no picker (`is_primary` unread)."""
        _seed_contact(session_factory, variables={})
        a, b = _link_customers(session_factory, "ZZT ALPHA CO", "ZZT BRAVO CO")
        reply, captured = _turn(
            session_factory, monkeypatch, _ask(self_reference=True), "what's my outstanding",
            mcp_response=REPORT_HIT,
        )
        (args,) = _calls(captured, REPORT)
        assert args["customer_ids"] == [a, b], args
        _assert_no_question(reply)

    def test_my_with_no_link_is_ignored(self, session_factory, monkeypatch) -> None:
        """AC-CS-24: no link -> `self_reference` is ignored: the same calls and the same
        reply as the identical verdict without the key."""
        _seed_contact(session_factory, variables={})
        without_reply, without_calls = _turn(
            session_factory, monkeypatch, _ask(), "what's my outstanding", mcp_response=REPORT_HIT,
        )
        _reset_session(session_factory)
        with_reply, with_calls = _turn(
            session_factory, monkeypatch, _ask(self_reference=True), "what's my outstanding",
            mcp_response=REPORT_HIT,
        )
        assert with_calls == without_calls
        assert with_reply == without_reply

    def test_staff_with_a_link_and_my_uses_the_link(self, session_factory, monkeypatch) -> None:
        """AC-CS-25: an office contact WITH a link and `self_reference: true` -> its links."""
        _seed_contact(session_factory, variables={})
        (own_id,) = _link_customers(session_factory, OWN_A)
        _give_access_type(session_factory, "Sorento Office")
        reply, captured = _turn(
            session_factory, monkeypatch, _ask(self_reference=True), "what's my outstanding",
            mcp_response=REPORT_HIT,
        )
        (args,) = _calls(captured, REPORT)
        assert args["customer_ids"] == [own_id], args

    def test_my_plus_own_customer_word_narrows(self, session_factory, monkeypatch) -> None:
        """AC-CS-26 (first half): `self_reference` + a word naming link B -> B alone."""
        _seed_contact(session_factory, variables={})
        _a, b = _link_customers(session_factory, "ZZT ALPHA CO", "ZZT BRAVO CO")
        reply, captured = _turn(
            session_factory, monkeypatch, _ask([_ent("bravo")], self_reference=True), "my outstanding for bravo",
            resolve_services=_hanlim_services(), mcp_response=REPORT_HIT,
        )
        (args,) = _calls(captured, REPORT)
        assert args["customer_ids"] == [b], args

    def test_my_plus_other_customer_word_refuses(self, session_factory, monkeypatch) -> None:
        """AC-CS-26 (second half): `self_reference` + another customer's word -> AC-CS-10."""
        _seed_contact(session_factory, variables={})
        _link_customers(session_factory, "ZZT ALPHA CO", "ZZT BRAVO CO")
        services, looked_up = _spied(_hanlim_services())
        reply, captured = _turn(
            session_factory, monkeypatch, _ask([_ent("hanlim")], self_reference=True), "my outstanding for hanlim",
            resolve_services=services,
        )
        assert reply.strip() == refusal("ZZT ALPHA CO", "ZZT BRAVO CO"), reply
        assert captured == []
        assert not _asked_about(looked_up, "hanlim")


# --------------------------------------------------------------------------- #
# Every customer-scoped fetch is forced to the links: AC-CS-30, 33, 34
# --------------------------------------------------------------------------- #


class TestForcedToTheLinks:
    def test_bare_order_ask_from_a_scoped_contact_is_forced_to_the_links(self, session_factory, monkeypatch) -> None:
        """AC-CS-30: an order ask naming no customer at all runs on the links; the link is
        the subject so no "which customer / product?" question is asked."""
        _seed_contact(session_factory, variables={})
        (own_id,) = _link_customers(session_factory, OWN_A)
        reply, captured = _turn(
            session_factory, monkeypatch,
            _parser_output(domain_hint="order", intent_hint="check_order", order_status=None, entities=[]),
            "list outstanding DO", attributes=(),
        )
        (args,) = _calls(captured, ORDERS)
        assert args["customer_ids"] == [own_id], args
        _assert_no_question(reply)

    def test_sales_report_other_customer_refused(self, session_factory, monkeypatch) -> None:
        """AC-CS-33 (other): the sales report of another customer -> AC-CS-10."""
        _seed_contact(session_factory, variables={})
        _link_customers(session_factory, OWN_A)
        services, looked_up = _spied(_hanlim_services())
        reply, captured = _turn(
            session_factory, monkeypatch, _ask([_ent("hanlim")], order_status="sales_report"),
            "sales report for hanlim", attributes=(SALES_KEY,), resolve_services=services,
        )
        assert reply.strip() == refusal(OWN_A), reply
        assert captured == []
        assert not _asked_about(looked_up, "hanlim")

    def test_sales_report_own_customer_runs_with_its_id(self, session_factory, monkeypatch) -> None:
        """AC-CS-33 (own): `crm_sales_report` runs with the contact's own id."""
        _seed_contact(session_factory, variables={})
        (own_id,) = _link_customers(session_factory, OWN_A)
        reply, captured = _turn(
            session_factory, monkeypatch, _ask([_ent("own a")], order_status="sales_report", sales_channel="dealer"),
            "sales report for own a", attributes=(SALES_KEY,),
            matches={"own a": {"uuid": HANLIM_UUID_1, "entity_type": "customer", "canonical_code": "300-H070"}},
        )
        (args,) = _calls(captured, SALES)
        assert args["customer_ids"] == [own_id], args

    def test_broaden_all_customers_keeps_the_scope(self, session_factory, monkeypatch) -> None:
        """AC-CS-34: "all customers" from a scoped contact still fetches on the links."""
        _seed_contact(session_factory, variables={})
        (own_id,) = _link_customers(session_factory, OWN_A)
        _turn(session_factory, monkeypatch, _ask(self_reference=True), "what's my outstanding", mcp_response=REPORT_HIT)
        reply, captured = _turn(
            session_factory, monkeypatch,
            _ask(broaden_axis="customer", broaden_to="all", correction=True), "all customers",
            mcp_response=REPORT_HIT,
        )
        # Whichever customer-scoped tool the broaden turn lands on (today it falls to the
        # plain orders list), it must still carry the links.
        calls = [args for name, args in captured if name in (REPORT, ORDERS, SALES)]
        assert calls, (captured, reply)
        assert all(args.get("customer_ids") == [own_id] for args in calls), calls
