"""AGENTIC-P3 slice 3 (PLAN-agentic-p3-writes-30oct.md, "Build contract, slices 2 and 3"): W0 dealer
contact access (role, resign) through the proposal path.

Red tests, written before the tools exist. The owner's example shape: four dealer contacts to
Business owner and one resign (AI replies off, unlinked from the salesperson's customer). Phones,
names, company names and codes are invented. Service level (`writes.run_user_read`,
`writes.propose_step`, `actions.store_proposal`, `actions.confirm`) with the real route and service
functions, plus one turn-level test. Postgres only (blank schema); every test seeds its own chain.

Assumed shapes (the plan does not pin them):
- `crm_contacts_find` returns `data` holding one list of per-phone dicts, in input order, each with a
  `status` (`found | not_found | ambiguous | not_yours | invalid_phone`); a found entry carries the
  plan's fields flat (`contact_id, name, phone, companies, role, chatbot_allowed, accounts`).
- `crm_contact_access_update` args: `contact_id`, `role` (`owner | employee`), `chatbot_allowed`,
  `link_customer_ids`, `unlink_customer_ids`.
- A scope failure in `read_before` is a 403/404 route error, so `propose_step` answers `denied`.
- Summaries contain `Employee -> Business owner (Sorento)`, `AI replies on -> off`, `unlinked from <code>`.
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import clear_actor
from app.models.access import ContactAccessType, RespondContact, RespondContactCustomer
from app.models.audit import AuditLog
from app.models.base import company_scope
from app.models.company import Company, RespondContactCompany, UserCompany
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from tests._ask_todo_seed import SORENTO
from tests._ask_todo_seed import agent as seed_sales_agent
from tests._ask_todo_seed import contact as seed_plain_contact
from tests._ask_todo_seed import customer as seed_customer
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_contact, seed_user
from tests.chatbot.agent.test_agent_writes import (  # noqa: F401 - helpers, not tests
    PROPOSAL_HEAD,
    answer_,
    round_of,
    run_turn,
    tc,
    tool_names,
)
from tests.chatbot.agent.test_agent_writes_opportunity import ctx_of, propose_and_store

FIND = "crm_contacts_find"
UPDATE = "crm_contact_access_update"
EDIT_OWN = "user_management.contacts.edit_own"
EDIT = "user_management.contacts.edit"
EVENT = "contact.access_agent"
OWNER_TYPES = {"dealer", "cabana_dealer"}
BACKEND = Path(__file__).resolve().parents[3]
_counter = [0]


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    register_audit_listeners()
    yield
    clear_actor()


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


# ------------------------------------------------------------------ seeding


@dataclass
class CW:
    contact: dict
    user_id: str
    me: object
    other: object
    mine: object  # a customer of the user's agent
    mine2: object  # a second customer of the user's agent
    theirs: object  # a customer of another agent
    mch: str

    @property
    def respond_id(self) -> str:
        return self.contact["respond_id"]


def ensure_catalog(db) -> str:
    """The access types the sheet TEMPLATE uses (plus one extra) and the MCH company. Returns MCH's id."""
    for code in ("dealer", "cabana_dealer", "mocha_dealer", "end_user", "zzt_extra"):
        if db.get(ContactAccessType, code) is None:
            db.add(ContactAccessType(code=code, name=f"ZZT {code}", is_active=True, sort_order=1))
    mch = db.query(Company).filter(Company.code == "MCH").first()
    if mch is None:
        mch = Company(id=str(uuid.uuid4()), name="ZZT Mocha Co", code="MCH")
        db.add(mch)
    db.flush()
    return str(mch.id)


def make_world(db, *, slugs=(EDIT_OWN,)) -> CW:
    mch = ensure_catalog(db)
    contact = seed_contact(db)
    user_id = seed_user(db, contact_pk=contact["pk"], slugs=slugs)
    db.add(UserCompany(user_id=user_id, company_id=SORENTO))
    db.flush()
    me = seed_sales_agent(db, contact["pk"], "ME")
    other = seed_sales_agent(db, seed_plain_contact(db, "Other agent"), "OT")
    w = CW(
        contact=contact, user_id=user_id, me=me, other=other,
        mine=seed_customer(db, unique_code("Mine"), me),
        mine2=seed_customer(db, unique_code("Mine2"), me),
        theirs=seed_customer(db, unique_code("Theirs"), other),
        mch=mch,
    )
    db.commit()
    return w


def fake_phone() -> str:
    _counter[0] += 1
    return f"6019{uuid.uuid4().int % 1000:03d}{_counter[0]:05d}"


def dealer(db, w: CW, *, types=("end_user",), companies=(SORENTO,), customers=(), ai=True, phone=None, name=None):
    """A dealer contact. Returns the row (id, phone_number, name)."""
    _counter[0] += 1
    row = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=phone or fake_phone(),
        name=name or f"ZZT Dealer {_counter[0]}",
        chatbot_allowed=ai,
    )
    db.add(row)
    db.flush()
    row.access_types = [db.get(ContactAccessType, code) for code in types]
    db.flush()
    for company_id in companies:
        db.add(RespondContactCompany(respond_contact_id=row.id, company_id=company_id))
    for customer in customers:
        db.add(RespondContactCustomer(id=str(uuid.uuid4()), contact_id=row.id, customer_id=customer.id, company_id=SORENTO))
    db.flush()
    db.commit()
    return row


def state(db, contact_id: str) -> dict:
    db.expire_all()
    with company_scope(db, None):
        row = db.query(RespondContact).filter(RespondContact.id == contact_id).one()
        return {
            "types": sorted(t.code for t in row.access_types),
            "ai": row.chatbot_allowed,
            "links": sorted(
                str(r.customer_id)
                for r in db.query(RespondContactCustomer).filter(RespondContactCustomer.contact_id == contact_id)
            ),
        }


def event_rows(db, contact_id: str) -> list:
    return db.query(AuditLog).filter(AuditLog.event == EVENT, AuditLog.entity_id == contact_id).all()


def entries(data) -> list:
    """The per-phone dicts of a find result: the first list of dicts that all carry a `status`."""
    if isinstance(data, list) and data and all(isinstance(x, dict) and "status" in x for x in data):
        return data
    if isinstance(data, dict):
        for value in data.values():
            found = entries(value)
            if found:
                return found
    return []


def find(db, w: CW, phones, seen=None):
    from app.services.chatbot.agent import writes

    seen = set() if seen is None else seen
    out = writes.run_user_read(db, ctx_of(db, w), FIND, {"phones": phones}, seen)
    assert out.status == "ok", f"{out.status}: {out.message}"
    return entries(out.data), out


def seen_for(*rows_and_customers) -> set[str]:
    return {str(x.id).lower() for x in rows_and_customers}


def owner_step(row) -> tuple[str, dict]:
    return UPDATE, {"contact_id": row.id, "role": "owner"}


# ------------------------------------------------------------------ registry


def test_the_registry_holds_the_find_read_and_the_access_write():
    from app.services.chatbot.agent import writes

    assert FIND in writes.USER_READS
    assert UPDATE in writes.WRITES
    assert writes.WRITES[UPDATE].record_key == "contact_id"


# ------------------------------------------------------------------ 1. find


def test_01_find_answers_each_phone_with_its_own_status(db):
    w = make_world(db)
    found = dealer(db, w, types=("dealer", "end_user"), customers=(w.mine,))
    theirs = dealer(db, w, customers=(w.theirs,))
    dup_digits = fake_phone()
    dealer(db, w, phone=dup_digits)
    dealer(db, w, phone="+" + dup_digits)  # same digits, so neither is returned
    phones = [
        "+" + found.phone_number,
        "+60190000000",  # well formed, nobody has it
        "+" + dup_digits,
        "+" + theirs.phone_number,
        "12345",
    ]

    got, _ = find(db, w, phones)

    assert [e["status"] for e in got] == ["found", "not_found", "ambiguous", "not_yours", "invalid_phone"]
    top = got[0]
    assert top["contact_id"] == found.id and top["name"] == found.name
    assert top["role"] == "owner" and top["chatbot_allowed"] is True
    assert set(top["companies"]) == {"SRT"}


def test_01_a_not_yours_entry_carries_no_name_no_id_and_nothing_else(db):
    w = make_world(db)
    theirs = dealer(db, w, customers=(w.theirs,))
    seen: set[str] = set()

    got, out = find(db, w, ["+" + theirs.phone_number], seen)

    assert got[0]["status"] == "not_yours"
    assert set(got[0]) <= {"status", "phone"}
    dump = json.dumps(out.data, default=str)
    assert theirs.name not in dump and theirs.id not in dump
    assert theirs.id.lower() not in seen and w.theirs.id.lower() not in seen


def test_01_found_lists_only_the_accounts_of_the_users_own_agents_and_adds_the_ids_to_the_turn(db):
    w = make_world(db)
    row = dealer(db, w, customers=(w.mine, w.theirs))
    seen: set[str] = set()

    got, _ = find(db, w, ["+" + row.phone_number], seen)

    accounts = got[0]["accounts"]
    assert [a["customer_id"] for a in accounts] == [w.mine.id]
    assert accounts[0]["code"] == w.mine.customer_code and accounts[0]["name"] == w.mine.customer_name
    assert {row.id.lower(), w.mine.id.lower()} <= seen
    assert w.theirs.id.lower() not in seen


@pytest.mark.parametrize(
    "types, ai, role",
    [(("dealer", "end_user"), True, "owner"), (("end_user",), False, "employee"), ((), True, "none")],
    ids=["owner", "employee", "none"],
)
def test_01_found_reports_the_role_from_the_access_types(db, types, ai, role):
    w = make_world(db)
    row = dealer(db, w, types=types, ai=ai, customers=(w.mine,))

    got, _ = find(db, w, ["+" + row.phone_number])

    assert got[0]["role"] == role and got[0]["chatbot_allowed"] is ai


# ------------------------------------------------------------------ 2. the owner example proposes, writes nothing


def example(db, w):
    """Four employees to become Business owner, and one dealer to resign."""
    owners = [dealer(db, w, customers=(w.mine,)) for _ in range(4)]
    resign = dealer(db, w, types=("dealer", "end_user"), customers=(w.mine,))
    calls = [owner_step(r) for r in owners] + [
        (UPDATE, {"contact_id": resign.id, "chatbot_allowed": False, "unlink_customer_ids": [w.mine.id]})
    ]
    seen = seen_for(*owners, resign, w.mine)
    return owners, resign, calls, seen


def test_02_four_role_steps_and_one_resign_are_proposed_and_nothing_is_written(db):
    w = make_world(db)
    owners, resign, calls, seen = example(db, w)
    before = {r.id: state(db, r.id) for r in [*owners, resign]}

    steps, row = propose_and_store(db, w, calls, seen)

    assert len(steps) == 5 and len(row.steps) == 5
    for step, contact in zip(steps[:4], owners):
        assert contact.name in step["summary"]
        assert "Employee -> Business owner (Sorento)" in step["summary"]
    assert resign.name in steps[4]["summary"]
    assert "AI replies on -> off" in steps[4]["summary"]
    assert f"unlinked from {w.mine.customer_code}" in steps[4]["summary"]
    assert {r.id: state(db, r.id) for r in [*owners, resign]} == before
    assert db.query(AuditLog).filter(AuditLog.event == EVENT).count() == 0


# ------------------------------------------------------------------ 3. confirm


def test_03_confirm_adds_owner_types_per_company_keeps_end_user_and_resigns(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    owners, resign, calls, seen = example(db, w)
    both = dealer(db, w, companies=(SORENTO, w.mch), customers=(w.mine,))
    calls.append(owner_step(both))
    seen |= seen_for(both)
    _, row = propose_and_store(db, w, calls, seen)

    outcome = actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert outcome.status == "executed"
    assert [s["status"] for s in outcome.steps] == ["done"] * 6
    for contact in owners:
        assert set(state(db, contact.id)["types"]) == OWNER_TYPES | {"end_user"}
    assert set(state(db, both.id)["types"]) == OWNER_TYPES | {"mocha_dealer", "end_user"}
    gone = state(db, resign.id)
    assert gone["ai"] is False and gone["links"] == []
    assert gone["types"] == sorted(["dealer", "end_user"])  # a resign does not touch the role
    for contact in [*owners, resign, both]:
        rows = [a for a in event_rows(db, contact.id) if a.auth_method == "agent"]
        assert rows, f"no {EVENT} audit row for {contact.name}"
        assert all(str(a.user_id) == w.user_id and a.actor_type == "user" for a in rows)


# ------------------------------------------------------------------ 4. downgrade


def test_04_employee_removes_the_owner_types_only_and_keeps_or_adds_end_user(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    with_end_user = dealer(db, w, types=("dealer", "cabana_dealer", "end_user", "zzt_extra"), customers=(w.mine,))
    without = dealer(db, w, types=("dealer",), customers=(w.mine,))
    steps, row = propose_and_store(
        db, w,
        [(UPDATE, {"contact_id": r.id, "role": "employee"}) for r in (with_end_user, without)],
        seen_for(with_end_user, without),
    )
    assert all("Business owner (Sorento) -> Employee" in s["summary"] for s in steps)

    outcome = actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert outcome.status == "executed"
    assert state(db, with_end_user.id)["types"] == ["end_user", "zzt_extra"]
    assert state(db, without.id)["types"] == ["end_user"]


# ------------------------------------------------------------------ 5. scope


def test_05_contact_in_scope_follows_the_slug_the_agents_customers_and_the_self_rule(db):
    from app.services.chatbot.agent import writes

    own = make_world(db, slugs=(EDIT_OWN,))
    broad = make_world(db, slugs=(EDIT,))
    mine = dealer(db, own, customers=(own.mine,))
    foreign = dealer(db, own, customers=(own.theirs,))
    unlinked = dealer(db, own)

    assert writes.contact_in_scope(db, own.user_id, mine.id) is True
    assert writes.contact_in_scope(db, own.user_id, foreign.id) is False
    assert writes.contact_in_scope(db, own.user_id, unlinked.id) is False
    assert writes.contact_in_scope(db, broad.user_id, foreign.id) is True
    assert writes.contact_in_scope(db, broad.user_id, unlinked.id) is True


@pytest.mark.parametrize("slug", [EDIT_OWN, EDIT])
def test_05_a_users_own_linked_contact_is_never_in_scope(db, slug):
    from app.services.chatbot.agent import writes

    w = make_world(db, slugs=(slug,))
    db.add(RespondContactCustomer(id=str(uuid.uuid4()), contact_id=w.contact["pk"], customer_id=w.mine.id, company_id=SORENTO))
    db.commit()

    assert writes.contact_in_scope(db, w.user_id, w.contact["pk"]) is False
    res, step = _propose(db, w, {"contact_id": w.contact["pk"], "chatbot_allowed": False}, seen={w.contact["pk"]})
    assert res.status == "denied" and step is None


def _propose(db, w, args, *, seen):
    from app.services.chatbot.agent import writes

    return writes.propose_step(db, ctx_of(db, w), UPDATE, args, seen_ids={s.lower() for s in seen})


def test_05_edit_own_is_denied_on_another_salespersons_dealer_contact(db):
    w = make_world(db, slugs=(EDIT_OWN,))
    mine = dealer(db, w, customers=(w.mine,))
    foreign = dealer(db, w, customers=(w.theirs,))

    allowed, _ = _propose(db, w, {"contact_id": mine.id, "role": "owner"}, seen={mine.id})
    refused, step = _propose(db, w, {"contact_id": foreign.id, "role": "owner"}, seen={foreign.id})

    assert allowed.status == "proposed"
    assert refused.status == "denied" and step is None


def test_05_edit_holder_is_allowed_on_another_salespersons_dealer_contact(db):
    w = make_world(db, slugs=(EDIT,))
    foreign = dealer(db, w, customers=(w.theirs,))

    res, step = _propose(db, w, {"contact_id": foreign.id, "role": "owner"}, seen={foreign.id})

    assert res.status == "proposed" and step is not None


def test_05_linking_or_unlinking_a_customer_of_another_agent_is_refused_for_edit_own(db):
    w = make_world(db, slugs=(EDIT_OWN,))
    row = dealer(db, w, customers=(w.mine, w.theirs))

    control, _ = _propose(db, w, {"contact_id": row.id, "link_customer_ids": [w.mine2.id]}, seen={row.id, w.mine2.id})
    unlink, _ = _propose(db, w, {"contact_id": row.id, "unlink_customer_ids": [w.theirs.id]}, seen={row.id, w.theirs.id})
    link, _ = _propose(db, w, {"contact_id": row.id, "link_customer_ids": [w.theirs.id]}, seen={row.id, w.theirs.id})

    assert control.status == "proposed"
    assert unlink.status in ("denied", "invalid") and link.status in ("denied", "invalid")


# ------------------------------------------------------------------ 6. no slug


def test_06_without_either_slug_neither_tool_is_exposed_and_with_edit_own_both_are(db):
    from app.services.chatbot.agent import writes

    none = make_world(db, slugs=("sales.customer_asks.view",))
    own = make_world(db, slugs=(EDIT_OWN,))
    broad = make_world(db, slugs=(EDIT,))

    def exposed(w):
        ctx = ctx_of(db, w)
        return (
            UPDATE in {d.name for d in writes.permitted_writes(db, ctx)},
            FIND in {r.name for r in writes.permitted_user_reads(db, ctx)},
        )

    assert exposed(none) == (False, False)
    assert exposed(own) == (True, True)
    assert exposed(broad) == (True, True)


def test_06_a_direct_call_without_either_slug_is_denied(db):
    w = make_world(db, slugs=("sales.customer_asks.view",))
    row = dealer(db, w, customers=(w.mine,))
    holder = make_world(db, slugs=(EDIT_OWN,))
    held_row = dealer(db, holder, customers=(holder.mine,))

    control, _ = _propose(db, holder, {"contact_id": held_row.id, "role": "owner"}, seen={held_row.id})
    res, step = _propose(db, w, {"contact_id": row.id, "role": "owner"}, seen={row.id})

    assert control.status == "proposed"
    assert res.status == "denied" and step is None


# ------------------------------------------------------------------ 7. undo of a resign


def resign_and_confirm(db, w, row):
    from app.services.chatbot.agent import actions

    _, action = propose_and_store(
        db, w,
        [(UPDATE, {"contact_id": row.id, "chatbot_allowed": False, "unlink_customer_ids": [w.mine.id]})],
        seen_for(row, w.mine),
    )
    outcome = actions.confirm(db, w.respond_id, str(action.id), via="console")
    assert outcome.status == "executed"


def test_07_the_same_user_may_relink_a_resigned_contact_to_the_same_customer_and_restore_it(db):
    from app.services.chatbot.agent import actions, writes

    w = make_world(db)
    row = dealer(db, w, types=("dealer", "end_user"), customers=(w.mine,))
    resign_and_confirm(db, w, row)
    assert writes.contact_in_scope(db, w.user_id, row.id) is False  # out of scope now

    _, action = propose_and_store(
        db, w,
        [(UPDATE, {"contact_id": row.id, "chatbot_allowed": True, "link_customer_ids": [w.mine.id]})],
        seen_for(row, w.mine),
    )
    outcome = actions.confirm(db, w.respond_id, str(action.id), via="console")

    assert outcome.status == "executed"
    assert state(db, row.id) == {"types": ["dealer", "end_user"], "ai": True, "links": [w.mine.id]}


def test_07_a_relink_to_a_customer_it_was_never_unlinked_from_is_denied(db):
    w = make_world(db)
    row = dealer(db, w, customers=(w.mine,))
    resign_and_confirm(db, w, row)

    res, step = _propose(db, w, {"contact_id": row.id, "link_customer_ids": [w.mine2.id]}, seen={row.id, w.mine2.id})

    assert res.status in ("denied", "invalid") and step is None


def test_07_a_relink_by_another_edit_own_user_is_denied(db):
    w = make_world(db)
    row = dealer(db, w, customers=(w.mine,))
    resign_and_confirm(db, w, row)
    second = make_world(db)

    res, step = _propose(
        db, second, {"contact_id": row.id, "link_customer_ids": [second.mine.id]}, seen={row.id, second.mine.id}
    )
    same_customer, step2 = _propose(
        db, second, {"contact_id": row.id, "link_customer_ids": [w.mine.id]}, seen={row.id, w.mine.id}
    )

    assert res.status in ("denied", "invalid") and step is None
    assert same_customer.status in ("denied", "invalid") and step2 is None


def test_07_an_unexecuted_proposal_does_not_open_the_undo(db):
    w = make_world(db)
    row = dealer(db, w, customers=(w.mine,))
    propose_and_store(
        db, w,
        [(UPDATE, {"contact_id": row.id, "chatbot_allowed": False, "unlink_customer_ids": [w.mine.id]})],
        seen_for(row, w.mine),
    )
    with company_scope(db, None):
        db.query(RespondContactCustomer).filter(RespondContactCustomer.contact_id == row.id).delete()
        db.commit()

    res, step = _propose(db, w, {"contact_id": row.id, "link_customer_ids": [w.mine.id]}, seen={row.id, w.mine.id})

    assert res.status in ("denied", "invalid") and step is None


# ------------------------------------------------------------------ 8. invalid


def test_08_a_contact_with_no_company_cannot_have_its_role_set(db):
    w = make_world(db)
    row = dealer(db, w, companies=(), customers=(w.mine,))

    res, step = _propose(db, w, {"contact_id": row.id, "role": "owner"}, seen={row.id})

    assert res.status == "invalid" and step is None
    assert "This contact has no company, so its role cannot be set." in res.message


@pytest.mark.parametrize(
    "types, ai, args",
    [
        (("dealer", "end_user"), True, {"role": "owner"}),
        (("end_user",), True, {"role": "employee"}),
        (("end_user",), True, {"chatbot_allowed": True}),
    ],
    ids=["already owner", "already employee", "already on"],
)
def test_08_a_step_that_changes_nothing_is_invalid(db, types, ai, args):
    w = make_world(db)
    row = dealer(db, w, types=types, ai=ai, customers=(w.mine,))

    res, step = _propose(db, w, {"contact_id": row.id, **args}, seen={row.id})

    assert res.status == "invalid" and step is None
    assert "Nothing to change" in res.message


def test_08_a_call_with_no_field_to_change_is_invalid(db):
    w = make_world(db)
    row = dealer(db, w, customers=(w.mine,))

    res, step = _propose(db, w, {"contact_id": row.id}, seen={row.id})

    assert res.status == "invalid" and step is None


# ------------------------------------------------------------------ re-check at confirm


def test_a_contact_changed_on_screen_since_the_proposal_is_rejected_and_nothing_is_written(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    row = dealer(db, w, customers=(w.mine,))
    _, action = propose_and_store(db, w, [owner_step(row)], seen_for(row))
    with company_scope(db, None):
        live = db.query(RespondContact).filter(RespondContact.id == row.id).one()
        live.access_types = [db.get(ContactAccessType, "dealer"), db.get(ContactAccessType, "end_user")]
        db.commit()

    outcome = actions.confirm(db, w.respond_id, str(action.id), via="console")

    assert outcome.status == "rejected"
    assert "changed" in (outcome.steps[0]["error"] or "").lower()
    assert state(db, row.id)["types"] == ["dealer", "end_user"]
    assert event_rows(db, row.id) == []


def test_the_scope_is_checked_again_at_confirm(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    row = dealer(db, w, customers=(w.mine,))
    _, action = propose_and_store(db, w, [owner_step(row)], seen_for(row))
    with company_scope(db, None):
        db.query(RespondContactCustomer).filter(RespondContactCustomer.contact_id == row.id).delete()
        db.add(RespondContactCustomer(id=str(uuid.uuid4()), contact_id=row.id, customer_id=w.theirs.id, company_id=SORENTO))
        db.commit()

    outcome = actions.confirm(db, w.respond_id, str(action.id), via="console")

    assert outcome.status == "rejected"
    assert state(db, row.id)["types"] == ["end_user"]


# ------------------------------------------------------------------ one turn


def test_a_turn_finds_the_phones_then_proposes_the_role_change_and_writes_nothing(db):
    w = make_world(db)
    row = dealer(db, w, customers=(w.mine,))
    script = [
        round_of(tc(FIND, {"phones": ["+" + row.phone_number]}, "f1")),
        round_of(tc(UPDATE, {"contact_id": row.id, "role": "owner"}, "u1")),
        answer_("I have prepared the role change."),
    ]

    result, provider = run_turn(db, w, script, text_="make this dealer a business owner")

    assert {FIND, UPDATE} <= tool_names(provider)
    assert result.pending_action is not None
    assert PROPOSAL_HEAD in result.reply_text
    assert "Employee -> Business owner (Sorento)" in result.reply_text
    assert state(db, row.id)["types"] == ["end_user"]


# ------------------------------------------------------------------ 9. migration and registry


def _migration():
    path = BACKEND / "alembic" / "versions" / "agp3_0002_contacts_edit_own.py"
    spec = importlib.util.spec_from_file_location("agp3_0002_contacts_edit_own", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_09_the_registry_lists_the_slug_with_its_name():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    entry = next((p for p in PERMISSION_REGISTRY if p["slug"] == EDIT_OWN), None)
    assert entry is not None, f"{EDIT_OWN} is not in the registry"
    assert entry["name"] == "Edit Own Dealer Contacts' Access"
    assert entry.get("description")


def test_09_the_migration_seeds_the_slug_once_grants_it_to_no_role_and_is_safe_to_rerun(db):
    module = _migration()
    assert len(module.revision) <= 32
    ctx = MigrationContext.configure(db.connection())

    with Operations.context(ctx):
        module.upgrade()
        module.upgrade()

    count = db.execute(text("select count(*) from user_permissions where slug = :s"), {"s": EDIT_OWN}).scalar()
    granted = db.execute(
        text(
            "select count(*) from user_role_permissions urp "
            "join user_permissions p on p.id = urp.permission_id where p.slug = :s"
        ),
        {"s": EDIT_OWN},
    ).scalar()
    assert count == 1 and granted == 0


def test_09_the_migration_chains_after_the_ledger_migration_with_a_single_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    module = _migration()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"expected one alembic head, found {heads}"
    ancestors = {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}
    assert module.revision in ancestors
    assert "agp3_0001_agent_actions" in ancestors
