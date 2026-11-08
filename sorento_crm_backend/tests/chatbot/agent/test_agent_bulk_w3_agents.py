"""AGENT-BULK-W3-AGENTS (PLAN-agent-bulk-w3-agents-8nov.md, UAC agent-bulk-w3-agents-8nov-acceptance-criteria.md):
the agent assigns / changes the sales agent of customer accounts from a pasted table through `crm_batch_propose` over
a new batchable row write, `crm_customer_agent`.

Red tests, written before the code. Test numbers in the names are the UAC's brackets (01..09). Seeding comes from the
#2226 / #2241 modules. Postgres only (blank schema); every test seeds its own chain. Codes and names are invented
(public repo).

Pinned shapes:
- `crm_customer_agent` args: `company` (company code, optional), `customer_code`, `customer_name`, `agent` (agent
  code or name as written).
- A row that cannot apply is refused in `read_before` (4xx) with every reason joined by "; ". A customer given by
  name only, or an agent written not exactly, makes the row wait: `contact_grant.NeedsChoice` with choices
  {"written", "company", "candidates": [{"code", "name"}], "more", "noun": "account" | "agent", "kept": [...]}.
- The step's summary / "Will change" cell: "agent <old or none> -> <new>"; a company whose `sales_agent_source` is
  `customer` adds "Past invoiced sales of this customer move to <new> (RM x in the last 12 months)".
- Confirm writes through `CustomerService.assign_sales_agent_many` (the route's path) and records one
  `customer.sales_agent_agent` audit row per customer. No AutoCount write (Q1 (a)).
"""
from __future__ import annotations

import uuid

from app.models.audit import AuditLog
from app.models.base import company_scope
from app.models.company import Company
from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from tests.chatbot.agent.test_agent_bulk_grant import (  # noqa: F401  (fixtures are used by name)
    AGENTS_EDIT,
    BATCH,
    EDIT,
    GRANT,
    STOCK_EDIT,
    _listeners,
    ctx_of,
    db,
    make_world,
    store,
)
from tests.chatbot.agent.test_agent_writes import answer_, round_of, run_turn, tc

WRITE = "crm_customer_agent"
SLUG = "master_data.sales_agents.edit"
EVENT = "customer.sales_agent_agent"
NEEDS = "Needs your choice:"
NOT_CHANGED = "Not changed:"
READY = "I will make these changes when you confirm:"
AGENT_TAIL = "Reply with the agent code for each row under Needs your choice, or skip."
ALL = (EDIT, AGENTS_EDIT, STOCK_EDIT, SLUG)


def world(db, slugs=ALL, superadmin=True):
    return make_world(db, slugs=slugs, superadmin=superadmin)


def code(stem: str) -> str:
    return f"ZZT{stem}{uuid.uuid4().hex[:5]}".upper()


def agent_(db, company_id, stem: str, *, label=None, active=True) -> SalesAgent:
    with company_scope(db, None):
        row = SalesAgent(id=str(uuid.uuid4()), sales_agent=code(stem), person_label=label, company_id=company_id,
                         is_active=active)
        db.add(row)
        db.flush()
    db.commit()
    return row


def customer_(db, company_id, name: str, agent=None) -> Customer:
    with company_scope(db, None):
        row = Customer(id=str(uuid.uuid4()), customer_code=code("C"), customer_name=name, company_id=company_id,
                       sales_agent_id=agent.id if agent else None)
        db.add(row)
        db.flush()
    db.commit()
    return row


def agent_of(db, customer) -> str | None:
    db.expire_all()
    with company_scope(db, None):
        return db.get(Customer, str(customer.id)).sales_agent_id


def row_(*, company="SRT", customer=None, name=None, agent=None) -> dict:
    out = {}
    if company is not None:
        out["company"] = company
    if customer is not None:
        out["customer_code"] = customer
    if name is not None:
        out["customer_name"] = name
    if agent is not None:
        out["agent"] = agent
    return out


def propose_rows(db, w, rows, **kw):
    from app.services.chatbot.agent import batch

    return batch.propose_rows(db, ctx_of(db, w), WRITE, rows, seen_ids=set(), **kw)


def reason_of(skipped, n: int) -> str:
    found = [s for s in skipped if s["row"] == n]
    assert found, f"row {n} was not skipped: {skipped}"
    return found[0]["reason"]


def confirm(db, w, steps):
    from app.services.chatbot.agent import actions

    action = store(db, w, steps)
    return actions.confirm(db, w.respond_id, str(action.id), via="console")


def say(db, w, rows, text_, final="Done."):
    script = [round_of(tc(BATCH, {"write": WRITE, "rows": rows}, "b1")), answer_(final)]
    return run_turn(db, w, script, text_=text_)[0]


def set_source(db, company_id: str, source: str) -> None:
    with company_scope(db, None):
        db.get(Company, company_id).sales_agent_source = source
    db.commit()


# ------------------------------------------------------------------ T1 (01) registry and exposure


def test_01_the_agent_write_is_registered_batchable_with_the_sales_agents_edit_slug():
    from app.services.chatbot.agent import tools, writes

    d = writes.WRITES[WRITE]
    assert d.batchable is True and d.user_permission == SLUG and d.runs_as == "user"
    props = d.schema["function"]["parameters"]["properties"]
    assert {"company", "customer_code", "customer_name", "agent"} <= set(props)
    assert WRITE in tools.TOOL_LABELS


def test_01_the_batch_tool_offers_the_write_only_with_the_slug(db):
    from app.services.chatbot.agent import batch

    w = world(db, superadmin=False)
    enum = batch.batch_tool_schema(db, ctx_of(db, w))["function"]["parameters"]["properties"]["write"]["enum"]
    assert WRITE in enum

    without = world(db, slugs=(EDIT,), superadmin=False)
    enum = batch.batch_tool_schema(db, ctx_of(db, without))["function"]["parameters"]["properties"]["write"]["enum"]
    assert WRITE not in enum
    steps = []
    out = batch.propose(db, ctx_of(db, without), {"write": WRITE, "rows": [row_(customer="X", agent="Y")]}, steps,
                        seen_ids=set())
    assert out.status == "denied" and steps == []


# ------------------------------------------------------------------ T2 (02) exact code end to end


def test_02_exact_customer_code_and_agent_code_preview_then_confirm_moves_and_audits(db):
    w = world(db)
    old = agent_(db, w.srt, "JOHN")
    new = agent_(db, w.srt, "SEAN")
    cust = customer_(db, w.srt, "ZZT Ace Hardware", old)

    steps, skipped, waiting = propose_rows(
        db, w, [row_(customer=f"  {cust.customer_code.lower()} ", agent=new.sales_agent.lower())]
    )
    assert skipped == [] and waiting == [] and len(steps) == 1, (skipped, waiting)
    step = steps[0]
    change = f"agent {old.sales_agent} -> {new.sales_agent}"
    assert change in step["summary"]
    assert step["cells"]["Customer"] == cust.customer_code and step["cells"]["Name"] == "ZZT Ace Hardware"
    assert change in step["cells"]["Will change"]
    assert agent_of(db, cust) == old.id  # a preview writes nothing

    outcome = confirm(db, w, steps)
    assert outcome.status == "executed", outcome.steps
    assert agent_of(db, cust) == new.id
    rows = db.query(AuditLog).filter(AuditLog.entity_id == str(cust.id)).all()
    assert len([a for a in rows if a.event == EVENT]) == 1
    # the customer listener's own before / after row, as on screen
    assert any(a.event != EVENT and "sales_agent_id" in str(a.new_values or {}) for a in rows)


def test_02_an_agent_by_exact_person_label_and_a_customer_with_no_agent(db):
    w = world(db)
    new = agent_(db, w.srt, "LS", label="ZZT Lisa Tan")
    cust = customer_(db, w.srt, "ZZT Bravo Trading")

    steps, skipped, waiting = propose_rows(db, w, [row_(customer=cust.customer_code, agent="zzt  lisa tan")])
    assert skipped == [] and waiting == []
    assert f"agent none -> {new.sales_agent}" in steps[0]["summary"]
    assert confirm(db, w, steps).status == "executed"
    assert agent_of(db, cust) == new.id


# ------------------------------------------------------------------ T3 (03) no fuzzy matching: picks


def test_03_a_customer_by_name_only_waits_with_the_rows_company_accounts_even_one(db):
    w = world(db)
    new = agent_(db, w.srt, "SEAN")
    stem = f"ZZT Ace {uuid.uuid4().hex[:4]}"
    one = customer_(db, w.srt, f"{stem} Hardware")
    customer_(db, w.mch, f"{stem} Hardware Mocha")  # another company: never offered on an SRT row

    steps, skipped, waiting = propose_rows(db, w, [row_(name=stem, agent=new.sales_agent)])
    assert steps == [] and skipped == []
    assert len(waiting) == 1 and waiting[0]["row"] == 1
    assert [c["code"] for c in waiting[0]["candidates"]] == [one.customer_code]
    assert waiting[0]["noun"] == "customer"


def tiers(db, company_id, person: str, suffixes=(" I", " III", " IV")) -> list[SalesAgent]:
    """One person, one code per account tier (the dev shape: 'X I' sits inside 'X III'), all labelled the person."""
    base = code("T")
    rows = [agent_(db, company_id, "T", label=person) for _ in suffixes]
    for row, suffix in zip(rows, suffixes):
        row.sales_agent = f"{base}{suffix}"
    db.commit()
    return rows


def test_03_an_exact_code_wins_over_the_codes_that_contain_it(db):
    w = world(db)
    one, three, four = tiers(db, None, f"ZZT Person {uuid.uuid4().hex[:4]}")
    cust = customer_(db, w.srt, "ZZT Delta Trading")
    steps, skipped, waiting = propose_rows(db, w, [row_(customer=cust.customer_code, agent=one.sales_agent)])
    assert skipped == [] and waiting == [] and f"-> {one.sales_agent}" in steps[0]["summary"]


def test_03_a_person_name_held_by_several_agents_waits_with_those_agents_and_is_never_auto_picked(db):
    w = world(db)
    person = f"ZZT Person {uuid.uuid4().hex[:4]}"
    agents = tiers(db, None, person)
    other = agent_(db, w.mch, "Z", label=person)  # another company's: never offered for an SRT customer
    cust = customer_(db, w.srt, "ZZT Delta Trading")

    steps, skipped, waiting = propose_rows(db, w, [row_(customer=cust.customer_code, agent=person.upper())])
    assert steps == [] and skipped == []
    assert waiting[0]["noun"] == "agent"
    got = sorted(c["code"] for c in waiting[0]["candidates"])
    assert got == sorted(a.sales_agent for a in agents) and other.sales_agent not in got
    assert all(c["name"] == person for c in waiting[0]["candidates"])


def test_03_a_person_name_held_by_one_agent_is_that_agent(db):
    w = world(db)
    person = f"ZZT Solo {uuid.uuid4().hex[:4]}"
    solo = agent_(db, w.srt, "S", label=person)
    cust = customer_(db, w.srt, "ZZT Delta Trading")
    steps, skipped, waiting = propose_rows(db, w, [row_(customer=cust.customer_code, agent=person)])
    assert skipped == [] and waiting == [] and f"-> {solo.sales_agent}" in steps[0]["summary"]


def test_03_a_name_inside_longer_names_waits_and_a_code_is_never_matched_by_containment(db):
    w = world(db)
    stem = f"ZZT Ma {uuid.uuid4().hex[:4]}"
    short = agent_(db, None, "M", label=f"{stem} Longer")
    longer = agent_(db, None, "N", label=f"{stem} Longest")
    cust = customer_(db, w.srt, "ZZT Delta Trading")
    _, skipped, waiting = propose_rows(db, w, [row_(customer=cust.customer_code, agent=stem)])
    assert skipped == [] and sorted(c["code"] for c in waiting[0]["candidates"]) == sorted(
        [short.sales_agent, longer.sales_agent]
    )

    # a written code that is only PART of agent codes is not a pick list: it is not found
    piece = short.sales_agent[:-2]
    steps, skipped, waiting = propose_rows(db, w, [row_(customer=cust.customer_code, agent=piece)])
    assert steps == [] and waiting == [] and f'No sales agent named "{piece}"' in reason_of(skipped, 1)


def test_03_the_pick_by_reply_proposes_the_row_and_an_unlisted_pick_is_refused(db):
    w = world(db)
    person = f"ZZT Person {uuid.uuid4().hex[:4]}"
    _, a2, _ = tiers(db, None, person)
    stranger = agent_(db, w.srt, "Q")
    cust = customer_(db, w.srt, "ZZT Echo Trading")
    first = {**row_(customer=cust.customer_code, agent=person), "row": 1}
    _, _, waiting = propose_rows(db, w, [first])
    assert waiting

    picked = {**first, "agent": a2.sales_agent}
    steps, skipped, _ = propose_rows(db, w, [picked], previous_waiting=waiting, user_text=f"row 1: {a2.sales_agent}")
    assert skipped == [] and len(steps) == 1 and a2.sales_agent in steps[0]["summary"]

    wrong = {**first, "agent": stranger.sales_agent}
    steps, skipped, _ = propose_rows(db, w, [wrong], previous_waiting=waiting, user_text="row 1: the second one")
    assert steps == [] and "pick from the list" in reason_of(skipped, 1)


def test_03_a_pick_that_changes_the_rows_key_is_still_checked_against_that_rows_list(db):
    """Review 8 Nov: the row key is the customer as written, so a pick that drops the name or adds a company must not
    escape the pick check."""
    w = world(db)
    new = agent_(db, w.srt, "SEAN")
    stem = f"ZZT Fox {uuid.uuid4().hex[:4]}"
    customer_(db, w.srt, f"{stem} One")
    customer_(db, w.srt, f"{stem} Two")
    stranger = customer_(db, w.srt, "ZZT Unrelated Stranger")
    first = {**row_(name=stem, agent=new.sales_agent), "row": 1}
    _, _, waiting = propose_rows(db, w, [first])
    dropped = {"company": "SRT", "customer_code": stranger.customer_code, "agent": new.sales_agent, "row": 1}
    steps, skipped, _ = propose_rows(db, w, [dropped], previous_waiting=waiting, user_text="row 1: the first one")
    assert steps == [] and "pick from the list" in reason_of(skipped, 1)

    person = f"ZZT Person {uuid.uuid4().hex[:4]}"
    tiers(db, None, person)
    q = agent_(db, w.srt, "Q")
    cust = customer_(db, w.srt, "ZZT Golf Two")
    first = {**row_(company=None, customer=cust.customer_code, agent=person), "row": 1}
    _, _, waiting = propose_rows(db, w, [first])
    assert waiting
    added = {"company": "SRT", "customer_code": cust.customer_code, "agent": q.sales_agent, "row": 1}
    steps, skipped, _ = propose_rows(db, w, [added], previous_waiting=waiting, user_text="row 1: the second one")
    assert steps == [] and "pick from the list" in reason_of(skipped, 1)


def test_03_inactive_accounts_are_never_offered_as_a_pick(db):
    w = world(db)
    new = agent_(db, w.srt, "SEAN")
    stem = f"ZZT Kilo {uuid.uuid4().hex[:4]}"
    live = customer_(db, w.srt, f"{stem} Live")
    closed = customer_(db, w.srt, f"{stem} Closed")
    with company_scope(db, None):
        db.get(Customer, str(closed.id)).is_active = False
    db.commit()
    _, _, waiting = propose_rows(db, w, [row_(name=stem, agent=new.sales_agent)])
    assert [c["code"] for c in waiting[0]["candidates"]] == [live.customer_code]


def test_03_a_customer_name_pick_keeps_the_written_name_and_takes_the_listed_code(db):
    w = world(db)
    new = agent_(db, w.srt, "SEAN")
    stem = f"ZZT Fox {uuid.uuid4().hex[:4]}"
    c1 = customer_(db, w.srt, f"{stem} One")
    customer_(db, w.srt, f"{stem} Two")
    first = {**row_(name=stem, agent=new.sales_agent), "row": 1}
    _, _, waiting = propose_rows(db, w, [first])
    assert len(waiting[0]["candidates"]) == 2

    picked = {**first, "customer_code": c1.customer_code}
    steps, skipped, _ = propose_rows(db, w, [picked], previous_waiting=waiting, user_text=f"1: {c1.customer_code}")
    assert skipped == [] and len(steps) == 1
    assert steps[0]["cells"]["Customer"] == c1.customer_code


# ------------------------------------------------------------------ T4 (04) Not changed, every reason


def test_04_unknown_customer_unknown_agent_inactive_other_company_and_already_set_are_not_changed(db):
    w = world(db)
    on = agent_(db, w.srt, "ON")
    sleepy = agent_(db, w.srt, "OLD", active=False)
    mocha = agent_(db, w.mch, "MOC")
    cust = customer_(db, w.srt, "ZZT Golf Trading", on)
    rows = [
        row_(customer="ZZTNOPE999", agent=on.sales_agent),
        row_(customer=cust.customer_code, agent="ZZTNOBODY999"),
        row_(customer=cust.customer_code, agent=sleepy.sales_agent),
        row_(customer=cust.customer_code, agent=mocha.sales_agent),
        row_(customer=cust.customer_code, agent=on.sales_agent),
    ]
    for n, r in enumerate(rows, 1):
        steps, skipped, waiting = propose_rows(db, w, [r])
        assert steps == [] and waiting == [], (n, steps, waiting)
        reason = reason_of(skipped, 1)
        if n == 1:
            assert reason.startswith('No customer with the code "ZZTNOPE999"')
        elif n == 2:
            assert 'No sales agent named "ZZTNOBODY999"' in reason
        elif n == 3:
            assert f'Sales agent "{sleepy.sales_agent}" is inactive' in reason
        elif n == 4:
            assert f'"{mocha.sales_agent}" is a Mocha agent' in reason
        else:
            assert reason == f"Already under {on.sales_agent}; nothing to change."


def test_04_no_customer_and_no_agent_say_what_to_give(db):
    w = world(db)
    steps, skipped, _ = propose_rows(db, w, [row_()])
    assert steps == []
    reason = reason_of(skipped, 1)
    assert "Give the customer code" in reason and "Name the sales agent" in reason


def test_04_a_customer_of_another_company_than_the_row_names_is_not_changed(db):
    w = world(db)
    new = agent_(db, None, "SH")
    cust = customer_(db, w.mch, "ZZT Hotel Mocha")
    steps, skipped, _ = propose_rows(db, w, [row_(company="SRT", customer=cust.customer_code, agent=new.sales_agent)])
    assert steps == [] and "is a Mocha customer" in reason_of(skipped, 1)


def test_04_a_customer_outside_the_users_companies_is_not_found(db):
    w = world(db, superadmin=False)
    new = agent_(db, None, "SH")
    hidden = customer_(db, w.hidden, "ZZT India Hidden")
    steps, skipped, _ = propose_rows(db, w, [row_(company=None, customer=hidden.customer_code, agent=new.sales_agent)])
    assert steps == [] and reason_of(skipped, 1).startswith(f'No customer with the code "{hidden.customer_code}"')


def test_04_the_same_code_in_two_companies_is_read_in_the_rows_company_and_needs_one_without(db):
    w = world(db)
    new = agent_(db, None, "SH")
    srt_cust = customer_(db, w.srt, "ZZT Heng Srt")
    mch_cust = customer_(db, w.mch, "ZZT Heng Mocha")
    with company_scope(db, None):
        db.get(Customer, str(mch_cust.id)).customer_code = srt_cust.customer_code
    db.commit()

    steps, skipped, _ = propose_rows(db, w, [row_(company="MCH", customer=srt_cust.customer_code, agent=new.sales_agent)])
    assert skipped == [] and steps[0]["cells"]["Name"] == "ZZT Heng Mocha"
    steps, skipped, _ = propose_rows(db, w, [row_(company=None, customer=srt_cust.customer_code, agent=new.sales_agent)])
    assert steps == [] and "give the company" in reason_of(skipped, 1)


def test_04_an_inactive_customer_is_not_changed(db):
    w = world(db)
    new = agent_(db, None, "SH")
    cust = customer_(db, w.srt, "ZZT Hengsen Closed")
    with company_scope(db, None):
        db.get(Customer, str(cust.id)).is_active = False
    db.commit()
    steps, skipped, _ = propose_rows(db, w, [row_(customer=cust.customer_code, agent=new.sales_agent)])
    assert steps == [] and f'Customer "{cust.customer_code}" is inactive' in reason_of(skipped, 1)


def test_04_a_customer_name_without_a_company_asks_for_the_company(db):
    w = world(db)
    new = agent_(db, None, "SH")
    customer_(db, w.srt, "ZZT Yee Tat One")
    steps, skipped, waiting = propose_rows(db, w, [row_(company=None, name="ZZT Yee Tat", agent=new.sales_agent)])
    assert steps == [] and waiting == [] and "Give the company" in reason_of(skipped, 1)


def test_04_a_hidden_companys_agent_or_company_is_never_named(db):
    """Review 8 Nov: the other-company agent message and the row's company read only companies the user sees."""
    w = world(db, superadmin=False)
    hidden_agent = agent_(db, w.hidden, "HID")
    cust = customer_(db, w.srt, "ZZT Papa Hidden")
    steps, skipped, _ = propose_rows(db, w, [row_(customer=cust.customer_code, agent=hidden_agent.sales_agent)])
    reason = reason_of(skipped, 1)
    assert steps == [] and "ZZH" not in reason and f'No sales agent named "{hidden_agent.sales_agent}"' in reason

    steps, skipped, _ = propose_rows(db, w, [row_(company="ZZH", customer=cust.customer_code, agent="x")])
    assert steps == [] and 'No company "ZZH"' in reason_of(skipped, 1)


def test_04_the_same_customer_twice_is_skipped_as_the_same_row(db):
    w = world(db)
    new = agent_(db, w.srt, "SEAN")
    cust = customer_(db, w.srt, "ZZT Juliet Trading")
    steps, skipped, _ = propose_rows(db, w, [row_(customer=cust.customer_code, agent=new.sales_agent)] * 2)
    assert len(steps) == 1 and reason_of(skipped, 2) == "Same as row 1."


# ------------------------------------------------------------------ T5 (05) customer-source companies (Q2 (a))


def test_05_a_customer_source_company_warns_that_past_sales_move_with_the_last_12_months_rm(db):
    from datetime import date, timedelta

    from tests._sales_unified_seed import doc

    w = world(db)
    set_source(db, w.mch, "customer")
    new = agent_(db, w.mch, "LISA")
    cust = customer_(db, w.mch, "ZZT Kilo Mocha")
    today = date.today()
    with company_scope(db, None):
        doc(db, "invoice", "1000.50", today - timedelta(days=30), customer=cust, company_id=w.mch)
        doc(db, "invoice", "250.00", today - timedelta(days=200), customer=cust, company_id=w.mch)
        doc(db, "credit_note", "100.00", today - timedelta(days=10), customer=cust, company_id=w.mch)
        doc(db, "invoice", "9999.00", today - timedelta(days=400), customer=cust, company_id=w.mch)  # older: out
        doc(db, "invoice", "7777.00", today - timedelta(days=5), customer=cust, company_id=w.mch, status="cancelled")
    db.commit()

    steps, skipped, _ = propose_rows(db, w, [row_(company="MCH", customer=cust.customer_code, agent=new.sales_agent)])
    assert skipped == []
    cell = steps[0]["cells"]["Will change"]
    assert f"Past invoiced sales of this customer move to {new.sales_agent}" in cell
    assert "RM 1,150.50 in the last 12 months" in cell

    srt_new = agent_(db, w.srt, "SEAN")
    srt_cust = customer_(db, w.srt, "ZZT Lima Trading")
    steps, _, _ = propose_rows(db, w, [row_(customer=srt_cust.customer_code, agent=srt_new.sales_agent)])
    assert "Past invoiced sales" not in steps[0]["cells"]["Will change"]


# ------------------------------------------------------------------ T6 (06) confirm rechecks


def test_06_a_customer_moved_on_screen_since_the_preview_fails_alone(db):
    w = world(db)
    new = agent_(db, w.srt, "SEAN")
    other = agent_(db, w.srt, "OTHER")
    moved = customer_(db, w.srt, "ZZT Mike Trading")
    calm = customer_(db, w.srt, "ZZT November Trading")
    steps, skipped, _ = propose_rows(db, w, [row_(customer=c.customer_code, agent=new.sales_agent) for c in (moved, calm)])
    assert len(steps) == 2 and skipped == []
    with company_scope(db, None):
        db.get(Customer, str(moved.id)).sales_agent_id = other.id
    db.commit()

    outcome = confirm(db, w, steps)
    assert outcome.status == "partial", outcome.steps
    assert agent_of(db, moved) == other.id and agent_of(db, calm) == new.id


def test_06_an_agent_retired_since_the_preview_fails_the_row(db):
    w = world(db)
    new = agent_(db, w.srt, "SEAN")
    cust = customer_(db, w.srt, "ZZT Oscar Trading")
    steps, _, _ = propose_rows(db, w, [row_(customer=cust.customer_code, agent=new.sales_agent)])
    with company_scope(db, None):
        db.get(SalesAgent, str(new.id)).is_active = False
    db.commit()
    outcome = confirm(db, w, steps)
    assert outcome.status != "executed"
    assert agent_of(db, cust) is None


# ------------------------------------------------------------------ T7 (07) the turn's tables


def test_07_a_turn_shows_ready_needs_choice_and_not_changed_tables_and_writes_nothing(db):
    w = world(db)
    new = agent_(db, w.srt, "SEAN")
    stem = f"ZZT Person {uuid.uuid4().hex[:4]}"
    tiers(db, None, stem)
    ready = customer_(db, w.srt, "ZZT Papa Trading")
    waits = customer_(db, w.srt, "ZZT Quebec Trading")
    rows = [
        {**row_(customer=ready.customer_code, agent=new.sales_agent), "row": 1},
        {**row_(customer=waits.customer_code, agent=stem), "row": 2},
        {**row_(customer="ZZTNOPE999", agent=new.sales_agent), "row": 3},
    ]
    reply = say(db, w, rows, "assign these agents please").reply_text
    assert READY in reply and NEEDS in reply and NOT_CHANGED in reply
    assert "| # | Customer | Name |" in reply
    assert "| Agent |" in reply or "| Agent" in reply
    assert AGENT_TAIL in reply
    assert agent_of(db, ready) is None and agent_of(db, waits) is None


# ------------------------------------------------------------------ T8 (08) the not-found claim is backed


def test_08_the_reply_may_say_the_agent_was_not_found(db):
    from app.services.chatbot.agent import loop

    ledger = {"b1": {"name": BATCH, "status": "invalid", "args": {}, "data": {
        "skipped": [{"row": 1, "reason": 'No sales agent named "ZZTNOBODY".'}],
    }}}
    assert loop._not_found_backed("ZZTNOBODY", "b1", ledger, set())


# ------------------------------------------------------------------ T9 (09) never AutoCount


def test_09_the_write_module_never_imports_an_autocount_writer():
    import ast
    import inspect

    from app.services.chatbot.agent import customer_agent

    tree = ast.parse(inspect.getsource(customer_agent))
    names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    names += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert names and not [m for m in names if "autocount" in m.lower()]


# ------------------------------------------------------------------ fix round 2 (crew live x3, 8 Nov)


def test_r2_a_partial_answer_keeps_the_other_rows_waiting_on_an_agent_and_on_a_customer(db):
    """Crew live: replying for row 3 only dropped row 4 (waiting on a person name) to Not changed, because the row's
    own written value, re-sent unchanged, was checked as a pick. A re-sent written value is not a pick."""
    w = world(db)
    new = agent_(db, w.srt, "SEAN")
    person = f"ZZT Person {uuid.uuid4().hex[:4]}"
    tiers(db, None, person)
    names = f"ZZT Yee {uuid.uuid4().hex[:4]}"
    pick = customer_(db, w.srt, f"{names} One")
    customer_(db, w.srt, f"{names} Two")
    other = f"ZZT Heng {uuid.uuid4().hex[:4]}"
    customer_(db, w.srt, f"{other} One")
    customer_(db, w.srt, f"{other} Two")
    cust = customer_(db, w.srt, "ZZT Mike Waiting")
    table = [
        {**row_(name=names, agent=new.sales_agent), "row": 3},
        {**row_(customer=cust.customer_code, agent=person), "row": 4},
        {**row_(name=other, agent=new.sales_agent), "row": 5},
        {**row_(customer="ZZTNOPE999", agent=new.sales_agent), "row": 6},
    ]
    _, skipped, waiting = propose_rows(db, w, table)
    assert {x["row"] for x in waiting} == {3, 4, 5} and reason_of(skipped, 6)

    again = [{**table[0], "customer_code": pick.customer_code}, *table[1:]]
    steps, skipped, waiting = propose_rows(
        db, w, again, previous_waiting=waiting, user_text=f"row 3: {pick.customer_code}"
    )
    assert [s["row"] for s in steps] == [3]
    assert {x["row"] for x in waiting} == {4, 5}, skipped
    assert {x["noun"] for x in waiting if x["row"] == 4} == {"agent"}
    assert {x["noun"] for x in waiting if x["row"] == 5} == {"customer"}
    assert [s["row"] for s in skipped] == [6]
    assert reason_of(skipped, 6).startswith('No customer with the code "ZZTNOPE999"')


def test_r2_a_written_value_changed_to_something_unlisted_is_still_refused(db):
    w = world(db)
    person = f"ZZT Person {uuid.uuid4().hex[:4]}"
    tiers(db, None, person)
    stranger = agent_(db, w.srt, "Q")
    cust = customer_(db, w.srt, "ZZT November Waiting")
    first = {**row_(customer=cust.customer_code, agent=person), "row": 1}
    _, _, waiting = propose_rows(db, w, [first])
    wrong = {**first, "agent": stranger.sales_agent}
    steps, skipped, _ = propose_rows(db, w, [wrong], previous_waiting=waiting, user_text="row 1: the first one")
    assert steps == [] and "pick from the list" in reason_of(skipped, 1)


def test_r2_the_crew_repro_through_two_turns_keeps_row_4_waiting(db):
    w = world(db)
    new = agent_(db, w.srt, "SEAN")
    person = f"ZZT Person {uuid.uuid4().hex[:4]}"
    tiers(db, None, person)
    names = f"ZZT Yee {uuid.uuid4().hex[:4]}"
    pick = customer_(db, w.srt, f"{names} One")
    customer_(db, w.srt, f"{names} Two")
    cust = customer_(db, w.srt, "ZZT Oscar Waiting")
    table = [
        {**row_(name=names, agent=new.sales_agent), "row": 3},
        {**row_(customer=cust.customer_code, agent=person), "row": 4},
        {**row_(customer="ZZTNOPE999", agent=new.sales_agent), "row": 6},
    ]
    first = say(db, w, table, "assign these sales agents").reply_text
    assert NEEDS in first

    again = [{**table[0], "customer_code": pick.customer_code}, *table[1:]]
    second = say(db, w, again, f"row 3: {pick.customer_code}").reply_text
    assert READY in second and NEEDS in second and "pick from the list" not in second
    needs = second.split(NEEDS, 1)[1].split(NOT_CHANGED, 1)[0]
    assert "| 4 |" in needs and person in needs
    assert "ZZTNOPE999" in second.split(NOT_CHANGED, 1)[1]


def test_r2_the_row_number_fallback_is_only_for_this_write_and_never_for_a_phone_keyed_row(db):
    """Trial merge with #2252: a different grant phone at the same row number is another row (phone keys never move
    on a pick), and another write's waiting list never refuses a customer-agent row."""
    from app.services.chatbot.agent import batch

    w = world(db)
    new = agent_(db, w.srt, "SEAN")
    cust = customer_(db, w.srt, "ZZT Papa Fresh")
    grant_wait = [{"row": 1, "key": "+60190000001", "write": GRANT, "written": "ZZT x", "codes": ["A1"], "kept": []}]
    steps, skipped, _ = propose_rows(
        db, w, [{**row_(customer=cust.customer_code, agent=new.sales_agent), "row": 1}],
        previous_waiting=grant_wait, user_text="assign",
    )
    assert skipped == [] and len(steps) == 1

    other_phone = {"phone": "+60190000002", "customer_codes": ["B9"]}
    assert batch._not_listed(other_phone, "+60190000002", grant_wait, "x", 1, None) is None


def test_r2_a_written_customer_name_re_sent_as_a_code_is_still_refused(db):
    """Review 8 Nov: the text a CUSTOMER row waits on is a name; sent back as customer_code it must not pass the pick
    check, even when some account's code equals that text."""
    w = world(db)
    new = agent_(db, w.srt, "SEAN")
    stem = f"ZZT Fox {uuid.uuid4().hex[:4]}"
    customer_(db, w.srt, f"{stem} One")
    customer_(db, w.srt, f"{stem} Two")
    other = customer_(db, w.srt, "ZZT Totally Other")
    with company_scope(db, None):
        db.get(Customer, str(other.id)).customer_code = stem.upper()
    db.commit()
    first = {**row_(name=stem, agent=new.sales_agent), "row": 1}
    _, _, waiting = propose_rows(db, w, [first])
    assert waiting
    sneaky = {**first, "customer_code": stem}
    steps, skipped, _ = propose_rows(db, w, [sneaky], previous_waiting=waiting, user_text="row 2: X")
    assert steps == [] and "pick from the list" in reason_of(skipped, 1)
