"""Round 7d RED tests: a customer the office grouped (`customers.customer_group_id`) is ONE customer on every path (owner R3:
a named customer is never silently dropped or narrowed to one ledger).

Seed (masked): one company; "ZZT ZZDEALER SDN BHD [A/C I]", "... [A/C III]" and "... (PROJECT)" share ONE CustomerGroup; a
different customer "ZZT ZZDEALER BATH CONCEPT SDN BHD" has no group. Staff contact; flag on (`rbot`) or off (`bot`).
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.models.order import CustomerGroup
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_report_semantic_carry import (  # noqa: F401 - fixtures
    _FIXTURES, _ent, _pick_of, _ra, _ran, _v, bot, console, rbot,
)
from tests.chatbot.test_chat_state_parser_input import _fresh_prompt_cache  # noqa: F401

OCT = {"date_from": "2026-10-01", "date_to": "2026-10-31"}
OCTF = {"date_filter_start": "2026-10-01", "date_filter_end": "2026-10-31"}
BASE = "ZZT ZZDEALER SANITARYWARE SDN BHD"  # what the model wrote; matches no row exactly
BATH = "ZZT ZZDEALER BATH CONCEPT SDN BHD (PROJECT)"  # ungrouped competitor
WORD = "zzdealer"
GROUPED = (f"{BASE} [A/C I]", f"{BASE} [A/C II]", f"{BASE} [A/C III]", f"{BASE} [A/C IV]", f"{BASE} (PROJECT)")
SHOWCASE = f"*{BASE} (SHOWCASE)"  # ungrouped sibling by name


def _seed(b) -> tuple[set[str], str]:
    _seed.by_name = {}
    from tests._mc_lookup_seed import customer

    db = b.console.session_factory()
    try:
        group = CustomerGroup(id=str(uuid.uuid4()), name=BASE, company_id=DEFAULT_COMPANY_ID)
        db.add(group)
        db.flush()
        ids = set()
        for name in GROUPED:
            row = customer(db, company_id=DEFAULT_COMPANY_ID, name=name)
            row.customer_group_id = group.id
            ids.add(str(row.id))
            _seed.by_name[name] = str(row.id)
        _seed.showcase = str(customer(db, company_id=DEFAULT_COMPANY_ID, name=SHOWCASE).id)
        bath = str(customer(db, company_id=DEFAULT_COMPANY_ID, name=BATH).id)
        db.commit()
        return ids, bath
    finally:
        db.close()


def _is_the_group(got: Any, ids: set[str]) -> bool:
    """The picked option: every grouped ledger; the name-rule sibling (SHOWCASE) may ride along as it does today."""
    got = set(got or [])
    return ids <= got <= ids | {_seed.showcase}


def _model_entity() -> dict[str, Any]:
    """Turn r2 step 23: the model's own words became a confident customer entity, no canonical code."""
    return {"raw": BASE, "hint": "customer", "canonical_code": None, "kind_said": None, "current_message": True, "confident": True}


def _ask(customers: list[str], *entities: dict[str, Any], basis: str | None = "invoiced", flag_on: bool = True, **over: Any):
    ra = _ra(channel="dealer", basis=basis, customers=customers, **OCT) if flag_on else None
    return _v("sales_report", ra, *entities, sales_channel="dealer", domain_in_message=True, basis=basis, sales_basis=basis,
              **OCTF, **over)


def _outcome(text: str, calls) -> tuple[str, Any]:
    ran = _ran(calls)
    return ("ran", frozenset(ran[0].get("customer_ids") or [])) if ran else ("asked", text.strip())


# ------------------------------------------------------------------------------------------ flag on, the object names the group


def _not_a_strict_subset(out: tuple[str, Any], ids: set[str], tag: str) -> None:
    if out[0] == "ran":
        assert not (out[1] < ids), f"R3 ({tag}): the run bound only part of the group: {sorted(out[1])} of {sorted(ids)}"


def _typed_then_object(b, ids: set[str], message: str, object_follow, reset_ask=None) -> tuple[tuple, tuple]:
    """The typed-word outcome (object null) and the object outcome for the SAME entity, in the same seed."""
    typed = _v("sales_report", None, _model_entity(), sales_channel="dealer", domain_in_message=True,
               basis="invoiced", sales_basis="invoiced", **OCTF)
    want = _outcome(*b.say(typed, message))
    if reset_ask is not None:
        b.say(reset_ask, "dealer sales oct invoiced")
    got = _outcome(*b.say(object_follow, message))
    return want, got


def test_d1_the_models_own_name_never_binds_part_of_the_group_and_equals_the_typed_word(rbot) -> None:
    """R3 (turn r2 step 23): the object names the group by words matching no row exactly, as a confident customer entity. The
    run is never a strict subset of the group's ledgers, and the outcome EQUALS the typed-word path (the group's ids, or the
    same which-one question when the typed path asks)."""
    ids, _bath = _seed(rbot)
    want, got = _typed_then_object(rbot, ids, "dealer zzdealer sanitaryware oct sale invoiced", _ask([BASE], _model_entity()))
    _not_a_strict_subset(got, ids, "object")
    _not_a_strict_subset(want, ids, "typed")
    assert got == want, f"R3: the object path differs from the typed-word path: typed {want}, object {got}"


def test_d2_the_bare_word_in_the_object_gives_what_the_typed_word_gives(rbot) -> None:
    """Equivalence: object customers ['zzdealer'] == the typed-word path for 'zzdealer' (the object left null) in the same seed."""
    _seed(rbot)
    typed = _v("sales_report", None, _ent(WORD, "customer"), sales_channel="dealer", domain_in_message=True,
               basis="invoiced", sales_basis="invoiced", **OCTF)
    want = _outcome(*rbot.say(typed, "dealer zzdealer oct sale invoiced"))
    got = _outcome(*rbot.say(_ask([WORD], _ent(WORD, "customer")), "dealer zzdealer oct sale invoiced"))
    assert got == want, f"the object path differs from the typed-word path: typed {want}, object {got}"


def test_d3_a_customer_only_narrows_to_the_whole_group_and_equals_the_typed_word(rbot) -> None:
    """R4 shape: after a report, '<customer> only' with the model's own name -> never part of the group; equals the typed path."""
    ids, _bath = _seed(rbot)
    first = _v("sales_report", _ra(channel="dealer", basis="invoiced", **OCT), sales_channel="dealer", basis="invoiced",
               sales_basis="invoiced", domain_in_message=True, **OCTF)
    text, calls = rbot.say(first, "dealer sales oct invoiced")
    assert _ran(calls), f"setup: {text!r}"
    typed = _v("sales_report", None, _model_entity(), continuation=True, entity_op="replace_combine", basis="invoiced",
               sales_basis="invoiced", **OCTF)
    want = _outcome(*rbot.say(typed, "zzdealer sanitaryware only"))
    rbot.say(first, "dealer sales oct invoiced")
    follow = _v("sales_report", _ra(channel="dealer", basis="invoiced", customers=[BASE], **OCT), _model_entity(),
                continuation=True, entity_op="replace_combine", **OCTF)
    got = _outcome(*rbot.say(follow, "zzdealer sanitaryware only"))
    _not_a_strict_subset(got, ids, "object")
    assert got == want, f"R4: the object path differs from the typed-word path: typed {want}, object {got}"


@pytest.mark.parametrize("object_customers", [[], [BASE]], ids=["object-drops", "object-rewrites-the-base-name"])
def test_d4_a_held_grouped_customer_carries_through_breakdown_and_top_n(rbot, object_customers) -> None:
    """C6-2 + R3: the group is held (picked at the which-one when the typed path asks); 'breakdown product' and 'top 5' keep
    exactly the same ids whether the object drops the customer or rewrites the model's name; never part of the group."""
    ids, _bath = _seed(rbot)
    want, got = _typed_then_object(rbot, ids, "dealer zzdealer sanitaryware oct sale invoiced", _ask([BASE], _model_entity()))
    assert got == want, f"setup: the object path differs from the typed-word path: typed {want}, object {got}"
    _not_a_strict_subset(got, ids, "setup")
    if got[0] == "asked":  # the typed path asks which one: pick the group
        text, calls = rbot.say(_pick_one(_group_position(got[1])), "1")
        got = _outcome(text, calls)
    assert got[0] == "ran", f"setup: no run for the held ask: {got}"
    held = set(got[1])
    _not_a_strict_subset(got, ids, "held")
    ra_b = _ra(channel="dealer", basis="invoiced", group_by="product", customers=object_customers, **OCT)
    text, calls = rbot.say(_v("sales_analysis", ra_b, group_by="product", sales_basis="invoiced", entity_op="reuse",
                              continuation=True, report_breakdown=True), "breakdown product")
    ran = _ran(calls)
    assert ran and set(ran[0].get("customer_ids") or []) == held and ran[0].get("group_by") == "product", (
        f"breakdown: want the held ids {sorted(held)}, got {ran[0].get('customer_ids') if ran else text!r}")
    ra_t = _ra(channel="dealer", basis="invoiced", group_by="product", top_n=5, measure="qty", customers=object_customers, **OCT)
    text, calls = rbot.say(_v("sales_ranking", ra_t, group_by="product", top_n=5, measure="qty", basis="invoiced",
                              rank_direction="top", entity_op="reuse", continuation=True, ranking_refine=True), "top 5, by invoiced qty")
    ran = _ran(calls)
    assert ran and set(ran[0].get("customer_ids") or []) == held, (
        f"top 5: want the held ids {sorted(held)}, got {ran[0].get('customer_ids') if ran else text!r}")


def test_d5_control_an_ungrouped_customer_named_exactly_is_that_one_id(rbot) -> None:
    _ids, bath = _seed(rbot)
    text, calls = rbot.say(_ask([BATH], _ent(BATH, "customer")), "dealer zzdealer bath concept oct sale invoiced")
    ran = _ran(calls)
    assert ran and ran[0].get("customer_ids") == [bath], f"control: want only {bath}, got {ran[0].get('customer_ids') if ran else text!r}"


# ------------------------------------------------------------------------------------------ the open which-one pick (both paths)


def _answer_basis(flag_on: bool) -> dict[str, Any]:
    """'invoiced' while the which-one is open: a basis, no customer entity, no pick."""
    ra = _ra(channel="dealer", basis="invoiced", customers=[], **OCT) if flag_on else None
    extra = dict(open_question_answer={"mode": "fill", "items": [], "picked": [], "qty_for_all": None}) if flag_on else {}
    return _v("sales_report", ra, basis="invoiced", sales_basis="invoiced", entity_op="reuse", continuation=True, **extra)


def _pick_one(position: int = 1) -> dict[str, Any]:
    return _v("sales_report", None, message_type="answer", intent_hint=None, domain_hint=None, entities=[],
              reference_positions=[position], open_question_answer=_pick_of(position), date_filter_start=None,
              date_filter_end=None, basis=None)


def _group_position(text: str) -> int:
    """The roster option for the group, found by its label (the group's name), never by position."""
    for ln in text.splitlines():
        head, _, label = ln.partition(". ")
        if head.isdigit() and label.strip() == BASE:
            return int(head)
    raise AssertionError(f"no option labelled {BASE!r} in {text!r}")


def _which_one_open(b, flag_on: bool) -> str:
    text, calls = b.say(_ask([WORD], _ent(WORD, "customer"), basis=None, flag_on=flag_on), "dealer zzdealer oct sale")
    assert not _ran(calls), f"setup: want the which-one question, got a run {calls}"
    low = text.lower()
    assert "1." in text and "2." in text and "zzdealer" in low, f"setup: want the which-one question, got {text!r}"
    return text


@pytest.mark.parametrize("flag_on", [True, False], ids=["flag-on", "flag-off"])
def test_d6_another_slots_answer_while_the_which_one_is_open_keeps_the_slot_and_asks_again(request, flag_on) -> None:
    """R3 (crew (a)): 'invoiced' while 'Which one do you mean?' is open must NOT run over every dealer; it keeps basis
    invoiced, re-asks the same which-one, and then '1' runs the group's three ledgers (invoiced, dealer, Oct, no basis question)."""
    b = request.getfixturevalue("rbot" if flag_on else "bot")
    ids, _bath = _seed(b)
    first = _which_one_open(b, flag_on)
    text, calls = b.say(_answer_basis(flag_on), "invoiced")
    assert not _ran(calls), f"R3: 'invoiced' ran the report with no customer: {_ran(calls)[0] if _ran(calls) else ''}"
    assert text.strip() == first.strip(), f"R3: want the same which-one question again, got {text!r}"
    text, calls = b.say(_pick_one(_group_position(first)), "1")
    ran = _ran(calls)
    assert ran, f"R3: the pick did not run; the bot said {text.strip()!r}"
    args = ran[0]
    assert _is_the_group(args.get("customer_ids"), ids), f"R3: want the group's ledgers, got {args.get('customer_ids')}"
    assert args.get("basis") == "invoiced" and args.get("channel") == "dealer" and args.get("date_from") == "2026-10-01", args


@pytest.mark.parametrize("flag_on", [True, False], ids=["flag-on", "flag-off"])
def test_d6_control_a_pick_right_away_runs_the_group(request, flag_on) -> None:
    b = request.getfixturevalue("rbot" if flag_on else "bot")
    ids, _bath = _seed(b)
    text, calls = b.say(_ask([WORD], _ent(WORD, "customer"), flag_on=flag_on), "dealer zzdealer oct sale invoiced")
    assert not _ran(calls), f"setup: want the which-one, got a run: {calls}"
    text, calls = b.say(_pick_one(_group_position(text)), "1")
    ran = _ran(calls)
    assert ran and _is_the_group(ran[0].get("customer_ids"), ids), f"control: {ran or text!r}"


# ------------------------------------------------------------------------------------------ d7: the resolver's code equals the typed word

FS = "ZZT FS SDN BHD"


def _seed_fs(b) -> tuple[str, str]:
    """Coder's minimal seed: two ledgers of ONE CustomerGroup + one live order whose `debtor_name` is exactly the bare name and
    whose `customer_id` is the [A/C I] ledger (so the resolver's canonical_code equals the typed word and
    `typed_exact_settles` keeps only [A/C I]). Returns ([A/C I] id, [A/C II] id)."""
    from app.models.order import Order
    from tests._mc_lookup_seed import customer

    db = b.console.session_factory()
    try:
        group = CustomerGroup(id=str(uuid.uuid4()), name=FS, company_id=DEFAULT_COMPANY_ID)
        db.add(group)
        db.flush()
        one = customer(db, company_id=DEFAULT_COMPANY_ID, name=f"{FS} [A/C I]")
        two = customer(db, company_id=DEFAULT_COMPANY_ID, name=f"{FS} [A/C II]")
        one.customer_group_id = group.id
        two.customer_group_id = group.id
        db.add(Order(id=str(uuid.uuid4()), order_number=f"ZZT-FS-{uuid.uuid4().hex[:8]}", customer_id=one.id,
                     debtor_name=FS, company_id=DEFAULT_COMPANY_ID))
        db.commit()
        return str(one.id), str(two.id)
    finally:
        db.close()


def _fs_ask(entity_raw: str, flag_on: bool) -> dict[str, Any]:
    ent = {"raw": entity_raw, "hint": "customer", "canonical_code": None, "kind_said": None, "current_message": True, "confident": True}
    ra = _ra(basis="invoiced", customers=[FS], **OCT) if flag_on else None
    return _v("sales_report", ra, ent, domain_in_message=True, basis="invoiced", sales_basis="invoiced", **OCTF)


@pytest.mark.parametrize(
    "flag_on,raw", [(True, "zzt fs"), (False, FS)], ids=["flag-on-object", "flag-off-bare-name"]
)
def test_d7_a_customer_whose_code_equals_the_typed_word_runs_every_ledger_of_its_group(request, flag_on, raw) -> None:
    """Rule: the report lane widens every customer id to all ledgers of its explicit customer_group in the same company.
    Flag on: entity 'zzt fs', object customers [bare name]. Flag off: the typed bare name (v71 shape). Today only [A/C I] runs."""
    b = request.getfixturevalue("rbot" if flag_on else "bot")
    one, two = _seed_fs(b)
    text, calls = b.say(_fs_ask(raw, flag_on), "zzt fs oct sale invoiced")
    ran = _ran(calls)
    assert ran, f"d7: no run; the bot said {text.strip()!r}"
    got = set(ran[0].get("customer_ids") or [])
    assert got == {one, two}, f"d7: want both ledgers of the group {sorted({one, two})}, got {sorted(got)}"


def test_d7c_guard_a_dealer_linked_to_one_ledger_never_sees_the_other(console) -> None:
    """Guard: a real DEALER contact (customer-scoped, linked to [A/C I] only) never gets [A/C II] (links win over the group)."""
    from sqlalchemy import text as _sql

    from tests.chatbot.test_engine import CONTACT_ID
    from tests.chatbot.test_report_unify_routing import Routing

    b = Routing(console)
    one, two = _seed_fs(b)
    db = console.session_factory()
    try:
        db.execute(
            _sql(
                "INSERT INTO respond_contact_customers (id, contact_id, customer_id, company_id) "
                "SELECT gen_random_uuid(), id, :cust, :company FROM respond_contacts WHERE respond_io_id = :cid"
            ),
            {"cust": one, "company": DEFAULT_COMPANY_ID, "cid": str(CONTACT_ID)},
        )
        db.commit()
    finally:
        db.close()
    text, calls = b.say(_fs_ask(FS, False), "zzt fs oct sale invoiced")
    ran = _ran(calls)
    assert ran, f"d7c: the dealer's ask did not run; the bot said {text.strip()!r}"
    assert ran[0].get("customer_ids") == [one], f"d7c: want only the linked ledger {one}, got {ran[0].get('customer_ids')}"
    assert two not in (ran[0].get("customer_ids") or []), f"d7c: the unlinked ledger ran for a dealer: {ran[0].get('customer_ids')}"
