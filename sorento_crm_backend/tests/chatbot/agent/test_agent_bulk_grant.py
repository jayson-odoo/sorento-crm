"""AGENT-BULK-ACTIONS (PLAN-agent-bulk-actions-7nov.md): the agent grants dealer-contact access from a pasted
table through one generic batch tool (`crm_batch_propose`) over a row write (`crm_contact_grant`).

Red tests, written before the tools exist. Service level (`batch.propose_rows`, `writes.propose_step`,
`actions.store_proposal`, `actions.confirm`) with the real engine and service functions, plus turn-level tests
through a scripted provider. Postgres only (blank schema); every test seeds its own chain. Phones, names, company
names and codes are invented (public repo).

Assumed shapes (the plan pins the names, these pin the rest):
- `crm_contact_grant` args: `phone`, `name`, `role` (owner | employee), `companies` (SRT | MCH),
  `customer_codes`, `customer_names`. A row that cannot apply is refused in `read_before` with a 4xx whose
  message is the reason the preview shows.
- `batch.propose_rows(db, ctx, write, rows, seen_ids)` -> (steps, skipped); skipped = [{"row", "reason", ...}].
- A batch action's steps carry `batch: True`; confirm runs every row, each its own transaction.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import clear_actor
from app.models.access import (
    AccessAgent,
    ContactAccessType,
    MarketSegment,
    RespondContact,
    RespondContactCustomer,
)
from app.models.audit import AuditLog
from app.models.base import company_scope
from app.models.company import Company, RespondContactCompany, UserCompany
from app.models.user import UserRole, UserRoleAssignment
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from tests._ask_todo_seed import SORENTO
from tests._ask_todo_seed import agent as seed_sales_agent
from tests._ask_todo_seed import customer as seed_customer
from tests._mc_lookup_seed import warehouse
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_contact, seed_user
from tests.chatbot.agent.test_agent_writes import answer_, round_of, run_turn, tc, tool_names

GRANT = "crm_contact_grant"
BATCH = "crm_batch_propose"
EDIT = "user_management.contacts.edit"
EDIT_OWN = "user_management.contacts.edit_own"
AGENTS_EDIT = "user_management.access_agents.edit"
STOCK_EDIT = "inventory.stock.edit"
EVENT = "contact.access_agent"
OWNER_SRT = {"end_user", "dealer", "cabana_dealer"}
_n = [0]


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
class W:
    contact: dict
    user_id: str
    srt: str
    mch: str
    hidden: str
    cust_a: object  # SRT, unique name
    cust_b: object  # MCH
    twin1: object  # SRT, same name as twin2
    twin2: object

    @property
    def respond_id(self) -> str:
        return self.contact["respond_id"]


def _company(db, code: str, name: str) -> str:
    with company_scope(db, None):
        row = db.query(Company).filter(Company.code == code).first()
        if row is None:
            row = Company(id=str(uuid.uuid4()), name=name, code=code)
            db.add(row)
            db.flush()
        return str(row.id)


def ensure_template_world(db) -> tuple[str, str]:
    """What the 26 Oct template needs: SRT, MCH, their stock locations, the three enquiry agents, the retail
    segment and the access types. Returns (srt id, mch id)."""
    srt = _company(db, "SRT", "ZZT Sorento Co")
    mch = _company(db, "MCH", "ZZT Mocha Co")
    with company_scope(db, None):
        from app.models.inventory import Warehouse

        for company_id, codes in ((srt, ("BRW", "MWH")), (mch, ("HQ", "MOCHA-WH"))):
            for code in codes:
                if not db.query(Warehouse).filter(Warehouse.company_id == company_id, Warehouse.warehouse_code == code).first():
                    warehouse(db, company_id=company_id, code=code)
        for code in ("general_enquiries", "order_enquiries", "incoming_stock_enquiries"):
            if db.query(AccessAgent).filter(AccessAgent.code == code).first() is None:
                db.add(AccessAgent(code=code, name=f"ZZT {code}"))
        if db.query(MarketSegment).filter(MarketSegment.code == "retail").first() is None:
            db.add(MarketSegment(code="retail", name="ZZT retail", is_active=True, sort_order=1))
        for code in ("dealer", "cabana_dealer", "mocha_dealer", "end_user"):
            if db.get(ContactAccessType, code) is None:
                db.add(ContactAccessType(code=code, name=f"ZZT {code}", is_active=True, sort_order=1))
        db.flush()
    return srt, mch


def make_superadmin(db, user_id: str) -> None:
    role = db.query(UserRole).filter(UserRole.slug == "superadmin").first()
    if role is None:
        role = UserRole(id=str(uuid.uuid4()), slug="superadmin", name="ZZT Superadmin")
        db.add(role)
        db.flush()
    db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=user_id, role_id=role.id))
    db.flush()


def make_world(db, *, slugs=(EDIT, AGENTS_EDIT, STOCK_EDIT), superadmin=True) -> W:
    srt, mch = ensure_template_world(db)
    hidden = _company(db, "ZZH", "ZZT Hidden Co")
    contact = seed_contact(db)
    user_id = seed_user(db, contact_pk=contact["pk"], slugs=slugs)
    for company_id in (srt, mch):
        db.add(UserCompany(user_id=user_id, company_id=company_id))
    db.flush()
    if superadmin:
        make_superadmin(db, user_id)
    me = seed_sales_agent(db, contact["pk"], "ME")
    twin_name = unique_code("ZZT Twin Hardware")
    with company_scope(db, None):
        w = W(
            contact=contact, user_id=user_id, srt=srt, mch=mch, hidden=hidden,
            cust_a=seed_customer(db, unique_code("ZZT Alpha Trading"), me, company_id=srt),
            cust_b=seed_customer(db, unique_code("ZZT Beta Mocha"), me, company_id=mch),
            twin1=seed_customer(db, twin_name, me, company_id=srt),
            twin2=seed_customer(db, twin_name, me, company_id=srt),
        )
    db.commit()
    return w


def fake_phone() -> str:
    """+601 and 9 digits: a Malaysian mobile number nobody holds."""
    _n[0] += 1
    return f"+6019{uuid.uuid4().int % 1000:03d}{_n[0] % 100000:05d}"


def local(phone: str) -> str:
    """The same number the way a sheet writes it: 019-xxx xxxxx."""
    digits = phone.lstrip("+")[2:]
    return f"0{digits[:2]}-{digits[2:5]} {digits[5:]}"


def dealer(db, w: W, *, types=("end_user",), companies=None, customers=(), phone=None, name=None) -> RespondContact:
    _n[0] += 1
    row = RespondContact(id=str(uuid.uuid4()), phone_number=phone or fake_phone(), name=name or f"ZZT Dealer {_n[0]}")
    db.add(row)
    db.flush()
    row.access_types = [db.get(ContactAccessType, code) for code in types]
    for company_id in (w.srt,) if companies is None else companies:
        db.add(RespondContactCompany(respond_contact_id=row.id, company_id=company_id))
    for customer in customers:
        db.add(RespondContactCustomer(
            id=str(uuid.uuid4()), contact_id=row.id, customer_id=customer.id, company_id=customer.company_id,
        ))
    db.flush()
    db.commit()
    return row


def state(db, phone: str) -> dict | None:
    """The contact holding this phone, as the access screens see it; None when there is none."""
    db.expire_all()
    with company_scope(db, None):
        digits = phone.lstrip("+")
        rows = db.query(RespondContact).filter(
            text("regexp_replace(respond_contacts.phone_number, '\\D', '', 'g') = :d")
        ).params(d=digits).all()
        if not rows:
            return None
        assert len(rows) == 1, "one contact per phone"
        row = rows[0]
        return {
            "id": str(row.id),
            "name": row.name,
            "types": sorted(t.code for t in row.access_types),
            "companies": sorted(
                str(c) for (c,) in db.query(RespondContactCompany.company_id)
                .filter(RespondContactCompany.respond_contact_id == row.id)
            ),
            "links": sorted(
                str(c) for (c,) in db.query(RespondContactCustomer.customer_id)
                .filter(RespondContactCustomer.contact_id == row.id)
            ),
            "chatbot_allowed": bool(row.chatbot_allowed),
        }


def events(db, contact_id: str) -> list:
    return db.query(AuditLog).filter(AuditLog.event == EVENT, AuditLog.entity_id == str(contact_id)).all()


def ctx_of(db, w: W):
    from app.services.chatbot.agent.access import build_context

    return build_context(db, w.respond_id)


def row_(phone, *, name="ZZT Person", role="owner", companies=("SRT",), codes=(), names=()) -> dict:
    out = {"phone": phone, "name": name, "role": role, "companies": list(companies)}
    if codes:
        out["customer_codes"] = list(codes)
    if names:
        out["customer_names"] = list(names)
    return out


def propose_rows(db, w: W, rows):
    from app.services.chatbot.agent import batch

    return batch.propose_rows(db, ctx_of(db, w), GRANT, rows, seen_ids=set())


def store(db, w: W, steps):
    from app.services.chatbot.agent import actions

    return actions.store_proposal(
        db, ctx_of(db, w), conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=steps
    )


def propose_and_confirm(db, w: W, rows):
    from app.services.chatbot.agent import actions

    steps, skipped = propose_rows(db, w, rows)
    assert steps, f"nothing proposed: {skipped}"
    action = store(db, w, steps)
    return actions.confirm(db, w.respond_id, str(action.id), via="console"), skipped


def reason_of(skipped, n: int) -> str:
    """The skip reason of the n-th input row (1-based)."""
    found = [s for s in skipped if s["row"] == n]
    assert found, f"row {n} was not skipped: {skipped}"
    return found[0]["reason"].lower()


# ------------------------------------------------------------------ 1. registry and exposure


def test_01_the_row_write_is_registered_and_batchable_and_the_batch_tool_exists():
    from app.services.chatbot.agent import batch, writes

    grant = writes.WRITES[GRANT]
    assert grant.batchable is True
    assert grant.user_permission == EDIT
    props = grant.schema["function"]["parameters"]["properties"]
    assert {"phone", "name", "role", "companies", "customer_codes", "customer_names"} <= set(props)
    assert batch.BATCH == BATCH
    assert batch.MAX_ROWS == 50


def test_01_the_batch_tool_is_offered_only_with_the_contacts_edit_slug_and_its_arrays_name_their_items(db):
    from app.services.chatbot.agent import batch

    w = make_world(db, superadmin=False)
    schema = batch.schema_for(db, ctx_of(db, w))
    assert schema is not None
    fn = schema["function"]
    assert fn["name"] == BATCH
    params = fn["parameters"]
    assert params["properties"]["write"]["enum"] == [GRANT]
    rows = params["properties"]["rows"]
    assert rows["type"] == "array" and rows["items"]["type"] == "object"
    for spec in rows["items"]["properties"].values():
        if spec.get("type") == "array":
            assert "items" in spec  # Gemini refuses an array without items

    own = make_world(db, slugs=(EDIT_OWN,), superadmin=False)
    assert batch.schema_for(db, ctx_of(db, own)) is None


def test_01_a_batch_call_without_the_slug_is_denied_and_proposes_nothing(db):
    from app.services.chatbot.agent import batch

    w = make_world(db, slugs=(EDIT_OWN,), superadmin=False)
    steps, out = [], None
    out = batch.propose(db, ctx_of(db, w), {"write": GRANT, "rows": [row_(fake_phone())]}, steps, seen_ids=set())
    assert out.status == "denied"
    assert steps == []


def test_01_a_batch_of_a_write_that_is_not_batchable_is_invalid(db):
    from app.services.chatbot.agent import batch

    w = make_world(db)
    steps = []
    out = batch.propose(db, ctx_of(db, w), {"write": "crm_contact_access_update", "rows": [{}]}, steps, seen_ids=set())
    assert out.status in ("invalid", "denied")
    assert steps == []


# ------------------------------------------------------------------ 2. one existing contact, end to end


def test_02_an_existing_contact_by_local_phone_and_customer_code_previews_then_confirm_applies(db):
    w = make_world(db)
    person = dealer(db, w)
    before = state(db, person.phone_number)

    steps, skipped = propose_rows(db, w, [row_(local(person.phone_number), codes=[w.cust_a.customer_code])])

    assert skipped == []
    assert len(steps) == 1 and steps[0]["batch"] is True
    assert w.cust_a.customer_code in steps[0]["summary"]
    assert "existing" in json.dumps(steps[0]["cells"]).lower()
    assert state(db, person.phone_number) == before  # a proposal writes nothing

    action = store(db, w, steps)
    from app.services.chatbot.agent import actions

    outcome = actions.confirm(db, w.respond_id, str(action.id), via="console")

    assert outcome.status == "executed", outcome.steps
    after = state(db, person.phone_number)
    assert set(after["types"]) == OWNER_SRT
    assert after["links"] == [str(w.cust_a.id)]
    assert w.srt in after["companies"]
    rows = events(db, person.id)
    assert rows and all(str(a.user_id) == w.user_id and a.auth_method == "agent" for a in rows)


def test_02_a_phone_not_in_the_crm_creates_the_contact_with_the_tables_name(db):
    w = make_world(db)
    phone = fake_phone()

    steps, skipped = propose_rows(db, w, [row_(local(phone), name="ZZT New Person", role="employee", codes=[w.cust_a.customer_code])])

    assert skipped == []
    assert "new" in json.dumps(steps[0]["cells"]).lower()
    assert state(db, phone) is None
    action = store(db, w, steps)
    from app.services.chatbot.agent import actions

    outcome = actions.confirm(db, w.respond_id, str(action.id), via="console")

    assert outcome.status == "executed", outcome.steps
    after = state(db, phone)
    assert after is not None and after["name"] == "ZZT New Person"
    assert after["types"] == ["end_user"]
    assert after["links"] == [str(w.cust_a.id)]
    assert events(db, after["id"])


# ------------------------------------------------------------------ 3. explicit matching only


def test_03_a_customer_by_exact_name_with_one_match_is_linked(db):
    w = make_world(db)
    person = dealer(db, w)

    outcome, skipped = propose_and_confirm(
        db, w, [row_(person.phone_number, names=[f"  {w.cust_a.customer_name.upper()} "])]
    )

    assert skipped == [] and outcome.status == "executed"
    assert state(db, person.phone_number)["links"] == [str(w.cust_a.id)]


def test_03_a_name_held_by_two_customers_a_near_name_and_an_unknown_code_are_skipped_never_guessed(db):
    w = make_world(db)
    a, b, c = dealer(db, w), dealer(db, w), dealer(db, w)

    steps, skipped = propose_rows(db, w, [
        row_(a.phone_number, names=[w.twin1.customer_name]),
        row_(b.phone_number, names=[w.cust_a.customer_name[:-1]]),  # one letter short: no fuzzy link
        row_(c.phone_number, codes=["ZZT-NO-SUCH-CODE"]),
    ])

    assert steps == []
    assert "more than one" in reason_of(skipped, 1)
    assert "no customer" in reason_of(skipped, 2)
    assert "no customer" in reason_of(skipped, 3)
    for person in (a, b, c):
        assert state(db, person.phone_number)["links"] == []


def test_03_a_customer_of_a_company_the_row_does_not_name_is_skipped(db):
    w = make_world(db)
    person = dealer(db, w)

    steps, skipped = propose_rows(db, w, [row_(person.phone_number, companies=["SRT"], codes=[w.cust_b.customer_code])])

    assert steps == []
    assert "mocha" in reason_of(skipped, 1) or "mch" in reason_of(skipped, 1)


def test_03_a_customer_outside_the_users_companies_is_not_found(db):
    w = make_world(db, superadmin=False)
    person = dealer(db, w)
    with company_scope(db, None):
        hidden = seed_customer(db, unique_code("ZZT Hidden"), None, company_id=w.hidden)
    db.commit()

    steps, skipped = propose_rows(db, w, [row_(person.phone_number, codes=[hidden.customer_code])])

    assert steps == []
    assert "no customer" in reason_of(skipped, 1)


def test_03_an_ambiguous_phone_an_invalid_phone_and_a_repeated_phone_are_skipped(db):
    w = make_world(db)
    shared = fake_phone()
    dealer(db, w, phone=shared)
    dealer(db, w, phone=local(shared))  # same digits after normalising, a second contact
    once = dealer(db, w)

    steps, skipped = propose_rows(db, w, [
        row_(shared),
        row_("12345"),
        row_(once.phone_number, codes=[w.cust_a.customer_code]),
        row_(local(once.phone_number), codes=[w.cust_a.customer_code]),
    ])

    assert len(steps) == 1
    assert "two contacts" in reason_of(skipped, 1) or "more than one contact" in reason_of(skipped, 1)
    assert "phone" in reason_of(skipped, 2)
    assert "row 3" in reason_of(skipped, 4)


def test_03_a_row_with_nothing_to_change_is_skipped_as_already_set(db):
    w = make_world(db)
    person = dealer(db, w)
    outcome, _ = propose_and_confirm(db, w, [row_(person.phone_number, codes=[w.cust_a.customer_code])])
    assert outcome.status == "executed"

    steps, skipped = propose_rows(db, w, [row_(person.phone_number, codes=[w.cust_a.customer_code])])

    assert steps == []
    assert "already" in reason_of(skipped, 1)


def test_03_an_unknown_role_or_company_is_refused_by_the_schema(db):
    w = make_world(db)
    steps, skipped = propose_rows(db, w, [
        {**row_(fake_phone()), "role": "boss"},
        {**row_(fake_phone()), "companies": ["ZZX"]},
    ])
    assert steps == []
    assert len(skipped) == 2


# ------------------------------------------------------------------ 4. the batch: preview, partial failure, recheck


def test_04_a_batch_previews_every_row_and_confirm_applies_each(db):
    w = make_world(db)
    a, b = dealer(db, w), dealer(db, w)
    fresh = fake_phone()

    outcome, skipped = propose_and_confirm(db, w, [
        row_(a.phone_number, codes=[w.cust_a.customer_code]),
        row_(b.phone_number, role="employee", companies=["SRT", "MCH"], codes=[w.cust_a.customer_code, w.cust_b.customer_code]),
        row_(fresh, name="ZZT Fresh", companies=["MCH"], codes=[w.cust_b.customer_code]),
        row_("not a phone"),
    ])

    assert outcome.status == "executed", outcome.steps
    assert [s["status"] for s in outcome.steps] == ["done"] * 3
    assert len(skipped) == 1
    assert set(state(db, a.phone_number)["types"]) == OWNER_SRT
    sb = state(db, b.phone_number)
    assert sb["links"] == sorted([str(w.cust_a.id), str(w.cust_b.id)])
    assert set(sb["companies"]) >= {w.srt, w.mch}
    sf = state(db, fresh)
    assert set(sf["types"]) == {"end_user", "mocha_dealer"} and sf["links"] == [str(w.cust_b.id)]


def test_04_a_row_that_fails_at_confirm_is_rolled_back_whole_and_the_other_rows_still_apply(db, monkeypatch):
    from app.services import contact_customer_service

    w = make_world(db)
    good = dealer(db, w)
    fresh = fake_phone()
    real = contact_customer_service.link_customer

    def failing(db_, contact_id, customer_id, **kw):
        if str(customer_id) == str(w.cust_b.id):
            raise RuntimeError("boom")
        return real(db_, contact_id, customer_id, **kw)

    monkeypatch.setattr(contact_customer_service, "link_customer", failing)
    outcome, _ = propose_and_confirm(db, w, [
        row_(fresh, name="ZZT Half", companies=["MCH"], codes=[w.cust_b.customer_code]),
        row_(good.phone_number, codes=[w.cust_a.customer_code]),
    ])

    assert outcome.status == "partial"
    assert [s["status"] for s in outcome.steps] == ["failed", "done"]
    assert outcome.steps[0]["error"]
    assert state(db, fresh) is None  # no half-written row: not even the contact
    assert state(db, good.phone_number)["links"] == [str(w.cust_a.id)]


def test_04_a_row_changed_on_screen_since_the_preview_fails_alone(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    moved, steady = dealer(db, w), dealer(db, w)
    steps, _ = propose_rows(db, w, [
        row_(moved.phone_number, codes=[w.cust_a.customer_code]),
        row_(steady.phone_number, codes=[w.cust_a.customer_code]),
    ])
    action = store(db, w, steps)
    with company_scope(db, None):
        db.add(RespondContactCustomer(
            id=str(uuid.uuid4()), contact_id=moved.id, customer_id=w.twin1.id, company_id=w.twin1.company_id,
        ))
    db.commit()

    outcome = actions.confirm(db, w.respond_id, str(action.id), via="console")

    assert outcome.status == "partial"
    assert [s["status"] for s in outcome.steps] == ["failed", "done"]
    assert "changed" in outcome.steps[0]["error"].lower()
    assert state(db, moved.phone_number)["links"] == [str(w.twin1.id)]
    assert state(db, steady.phone_number)["links"] == [str(w.cust_a.id)]


def test_04_the_slug_removed_before_confirm_fails_every_row_and_writes_nothing(db):
    from app.models.user import UserRolePermission
    from app.services.chatbot.agent import actions
    from app.services.user_service import invalidate_rbac_cache

    w = make_world(db, superadmin=False)
    person = dealer(db, w)
    steps, _ = propose_rows(db, w, [row_(person.phone_number, codes=[w.cust_a.customer_code])])
    action = store(db, w, steps)
    db.execute(text(
        "DELETE FROM user_role_permissions WHERE role_id IN "
        "(SELECT role_id FROM user_role_assignments WHERE user_id = :u)"
    ), {"u": w.user_id})
    db.commit()
    invalidate_rbac_cache()

    outcome = actions.confirm(db, w.respond_id, str(action.id), via="console")

    assert outcome.status == "rejected"
    assert state(db, person.phone_number)["links"] == []


def test_04_more_than_fifty_rows_is_invalid_and_proposes_nothing(db):
    from app.services.chatbot.agent import batch

    w = make_world(db)
    steps = []
    out = batch.propose(
        db, ctx_of(db, w), {"write": GRANT, "rows": [row_(fake_phone()) for _ in range(51)]}, steps, seen_ids=set()
    )
    assert out.status == "invalid" and "50" in out.message
    assert steps == []


# ------------------------------------------------------------------ 5. permissions beyond the slug


def test_05_a_user_who_cannot_set_companies_on_screen_gets_the_row_without_the_company(db):
    w = make_world(db, slugs=(EDIT,), superadmin=False)
    person = dealer(db, w, companies=())

    steps, skipped = propose_rows(db, w, [row_(person.phone_number, codes=[w.cust_a.customer_code])])

    assert skipped == []
    assert "not applied" in steps[0]["summary"].lower()
    from app.services.chatbot.agent import actions

    outcome = actions.confirm(db, w.respond_id, str(store(db, w, steps).id), via="console")
    assert outcome.status == "executed", outcome.steps
    after = state(db, person.phone_number)
    assert after["companies"] == []
    assert after["links"] == [str(w.cust_a.id)]


# ------------------------------------------------------------------ 6. through a turn


def test_06_a_turn_with_a_pasted_table_shows_one_preview_table_and_writes_nothing(db):
    w = make_world(db)
    a = dealer(db, w)
    fresh = fake_phone()
    rows = [
        row_(local(a.phone_number), name="ZZT Ali", codes=[w.cust_a.customer_code]),
        row_(fresh, name="ZZT Mei", role="employee", companies=["MCH"], codes=[w.cust_b.customer_code]),
        row_(fake_phone(), name="ZZT Siti", names=["ZZT No Such Shop"]),
    ]
    script = [round_of(tc(BATCH, {"write": GRANT, "rows": rows}, "b1")), answer_("Here is what I will change.")]

    result, provider = run_turn(db, w, script, text_="please grant access to these people")

    assert BATCH in tool_names(provider)
    assert result.pending_action is not None
    assert len(result.pending_action["lines"]) == 2
    reply = result.reply_text
    assert "| # |" in reply
    assert "ZZT Ali" in reply and "ZZT Mei" in reply
    assert "ZZT Siti" in reply and "no customer" in reply.lower()
    assert state(db, fresh) is None
    assert state(db, a.phone_number)["links"] == []


def test_06_a_second_batch_call_in_the_turn_replaces_the_first(db):
    w = make_world(db)
    a, b = dealer(db, w), dealer(db, w)
    first = [row_(a.phone_number, codes=[w.cust_a.customer_code])]
    second = [row_(b.phone_number, codes=[w.cust_a.customer_code])]
    script = [
        round_of(tc(BATCH, {"write": GRANT, "rows": first}, "b1")),
        round_of(tc(BATCH, {"write": GRANT, "rows": second}, "b2")),
        answer_("Corrected."),
    ]

    result, _ = run_turn(db, w, script, text_="grant access")

    assert len(result.pending_action["lines"]) == 1
    assert b.phone_number in result.pending_action["lines"][0]


# ------------------------------------------------------------------ 7. security review round 1


def test_07_a_console_operator_grants_only_the_facets_both_people_may_set(db):
    """B1: a superadmin linked user, an operator holding only the contacts slug: no company, stock or agents."""
    import dataclasses

    from app.models.access import ContactAgentAccess, StockVisibilityPolicy
    from app.services.chatbot.agent import actions, batch

    w = make_world(db)  # the linked user: superadmin with the agents and stock slugs
    operator = seed_user(db, contact_pk=None, slugs=(EDIT,))
    for company_id in (w.srt, w.mch):
        db.add(UserCompany(user_id=operator, company_id=company_id))
    db.commit()
    person = dealer(db, w, companies=())
    ctx = dataclasses.replace(ctx_of(db, w), operator_user_id=operator)

    steps, skipped = batch.propose_rows(db, ctx, GRANT, [row_(person.phone_number, codes=[w.cust_a.customer_code])], seen_ids=set())
    assert skipped == [] and "not applied" in steps[0]["summary"].lower()
    action = store(db, w, steps)
    outcome = actions.confirm(db, w.respond_id, str(action.id), via="console", operator_user_id=operator)

    assert outcome.status == "executed", outcome.steps
    after = state(db, person.phone_number)
    assert after["companies"] == []
    assert after["links"] == [str(w.cust_a.id)]
    with company_scope(db, None):
        assert db.query(StockVisibilityPolicy).filter(StockVisibilityPolicy.contact_id == person.id).count() == 0
        assert db.query(ContactAgentAccess).filter(ContactAgentAccess.respond_contact_id == person.id).count() == 0


def test_07_more_than_ten_customers_on_a_row_is_refused(db):
    w = make_world(db)
    steps, skipped = propose_rows(db, w, [row_(fake_phone(), codes=[f"ZZT-{i}" for i in range(11)])])
    assert steps == []
    assert "more than 10" in reason_of(skipped, 1)


def test_07_a_cell_cannot_carry_a_markdown_link_or_a_pipe(db):
    from app.services.chatbot.agent import batch

    w = make_world(db)
    steps, skipped = propose_rows(db, w, [row_("[click](http://evil.example) | x", name="A|B")])
    block = batch.preview_block(steps, skipped)
    assert "](" not in block and "A/B" in block


# ------------------------------------------------------------------ 8. review round 1


def test_08_a_company_the_user_is_not_granted_is_refused(db):
    w = make_world(db, slugs=(EDIT,), superadmin=False)
    db.query(UserCompany).filter(UserCompany.user_id == w.user_id, UserCompany.company_id == w.mch).delete()
    db.commit()
    person = dealer(db, w)

    steps, skipped = propose_rows(db, w, [row_(person.phone_number, companies=["MCH"])])

    assert steps == []
    assert "not one of your companies" in reason_of(skipped, 1)


def test_08_a_customer_renamed_between_preview_and_confirm_fails_the_row(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    person = dealer(db, w)
    said = w.cust_a.customer_name
    steps, _ = propose_rows(db, w, [row_(person.phone_number, names=[said])])
    action = store(db, w, steps)
    with company_scope(db, None):
        db.execute(text("UPDATE customers SET customer_name = customer_name || ' OLD' WHERE id = :i"), {"i": w.cust_a.id})
        db.execute(text("UPDATE customers SET customer_name = :n WHERE id = :i"), {"n": said, "i": w.twin1.id})
    db.commit()

    outcome = actions.confirm(db, w.respond_id, str(action.id), via="console")

    assert outcome.status == "rejected"
    assert state(db, person.phone_number)["links"] == []


def test_08_a_new_contact_gets_the_agents_flagged_for_new_contacts(db):
    from app.models.access import ContactAgentAccess

    w = make_world(db)
    with company_scope(db, None):
        flagged = AccessAgent(code=unique_code("zzt_new").lower(), name="ZZT default", assign_to_new_internal_contacts=True)
        db.add(flagged)
    db.commit()
    phone = fake_phone()

    outcome, _ = propose_and_confirm(db, w, [row_(phone, name="ZZT Defaults", codes=[w.cust_a.customer_code])])

    assert outcome.status == "executed", outcome.steps
    with company_scope(db, None):
        held = {str(a.agent_id) for a in db.query(ContactAgentAccess).filter(
            ContactAgentAccess.respond_contact_id == state(db, phone)["id"])}
    assert str(flagged.id) in held


def test_08_a_single_change_after_a_batch_and_a_batch_after_a_single_change_are_refused(db):
    w = make_world(db)
    a, b = dealer(db, w), dealer(db, w)
    batch_call = tc(BATCH, {"write": GRANT, "rows": [row_(a.phone_number, codes=[w.cust_a.customer_code])]}, "b1")
    single = tc(GRANT, row_(b.phone_number, codes=[w.cust_a.customer_code]), "s1")

    result, _ = run_turn(db, w, [round_of(batch_call), round_of(single), answer_("ok")], text_="grant access")
    assert len(result.pending_action["lines"]) == 1 and a.phone_number in result.pending_action["lines"][0]

    result, _ = run_turn(db, w, [round_of(single), round_of(batch_call), answer_("ok")], text_="grant access")
    assert len(result.pending_action["lines"]) == 1 and b.phone_number in result.pending_action["lines"][0]
