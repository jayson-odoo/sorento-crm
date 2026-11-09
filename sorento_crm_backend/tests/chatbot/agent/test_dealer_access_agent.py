"""DEALER-ACCESS-PORTAL v2 (UAC `documentation/plans/contacts/dealer-access-portal-09nov-acceptance-criteria.md`):
a salesperson (`user_management.contacts.edit_own`, no `.edit`) grants and changes dealer access through the agent
tools `crm_contact_grant` (single row and `crm_batch_propose`) and `crm_contact_access_update`; levels are the two
owner TAGS; a grant enqueues the Respond.io `ensure_respond_contact` job.

Red tests, written before the implementation. Each test name carries its UAC id. Service level
(`writes.propose_step`, `batch.propose_rows`, `actions.store_proposal`, `actions.confirm`) with the real engine,
plus the RQ job called in-process with a mocked Respond.io client. Postgres only (blank schema); every test seeds
its own chain, the owner tags included (a blank schema holds no migration data). Phones, names and codes are
invented (public repo).

Names the tests pin for the coder (from the captain's brief):
- Owner tags "Sorento Business Owner" (settings {"access_types": ["dealer", "cabana_dealer"]}) and
  "Mocha Business Owner" ({"access_types": ["mocha_dealer"]}), found case-insensitively by name.
- `app.tasks.respond_io_tasks.ensure_respond_contact(contact_id)`, enqueued through
  `app.services.queue_service.enqueue_job(..., queue_name="respond_io")` after the grant commits.
- `RespondClient.create_contact(phone, first_name)`.
"""
from __future__ import annotations

import dataclasses
import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import delete, func, insert, select

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import clear_actor
from app.models.access import ContactTag, RespondContact, RespondContactCustomer, respond_contact_tags
from app.models.audit import AuditLog
from app.models.base import company_scope
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from tests._ask_todo_seed import agent as seed_sales_agent
from tests._ask_todo_seed import contact as seed_plain_contact
from tests._ask_todo_seed import customer as seed_customer
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_user
from tests.chatbot.agent.test_agent_bulk_grant import (
    W,
    _company,
    ctx_of,
    dealer,
    events,
    fake_phone,
    make_world,
    row_,
    state,
)

GRANT = "crm_contact_grant"
BATCH = "crm_batch_propose"
UPDATE = "crm_contact_access_update"
EDIT = "user_management.contacts.edit"
EDIT_OWN = "user_management.contacts.edit_own"
NEITHER = "sales.customer_asks.view"
SRT_TAG = "Sorento Business Owner"
MCH_TAG = "Mocha Business Owner"
TAG_TYPES = {SRT_TAG: ["dealer", "cabana_dealer"], MCH_TAG: ["mocha_dealer"]}
STAFF = "This number belongs to a staff member."
ALREADY = "Already has this access; nothing to change."
ALSO = "also has access through another account"
DEMOTE_REFUSED = "This person also has access through another account; ask the office to change their level."
JOB_NAME = "ensure_respond_contact"
JOB_MODULE = "app.tasks.respond_io_tasks"


def missing_tag_text(tag: str = SRT_TAG) -> str:
    return f'The "{tag}" tag is missing; ask the office.'


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


@pytest.fixture(autouse=True)
def jobs(monkeypatch, db):
    """Every `enqueue_job` call, recorded instead of reaching Redis. Patched on the queue module and on the grant
    module (in case it imports the name), so the recorder sees the call whichever way it is made.

    `committed` (B1, review round 1 M6): no write was flushed since the session's last commit when the job was
    enqueued. The blank schema's outer transaction hides even committed rows from a fresh connection, so the
    session's own flush and commit events stand in for "the grant is committed"."""
    from sqlalchemy import event

    calls: list[SimpleNamespace] = []
    pending = {"flushed": False}

    def flushed(*_a):
        pending["flushed"] = True

    def committed(*_a):
        pending["flushed"] = False

    event.listen(db, "after_flush", flushed)
    event.listen(db, "after_commit", committed)

    def record(func, *args, **kwargs):
        calls.append(SimpleNamespace(func=func, args=args, kwargs=kwargs, committed=not pending["flushed"]))
        return SimpleNamespace(id=f"zzt-job-{len(calls)}")

    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", record)
    import app.services.chatbot.agent.contact_grant as contact_grant

    monkeypatch.setattr(contact_grant, "enqueue_job", record, raising=False)
    return calls


def respond_jobs(calls) -> list[SimpleNamespace]:
    return [
        c for c in calls
        if getattr(c.func, "__name__", "") == JOB_NAME and getattr(c.func, "__module__", "") == JOB_MODULE
    ]


# ------------------------------------------------------------------ seeding


def own_world(db, *, slugs=(EDIT_OWN,)) -> SimpleNamespace:
    """The bulk-grant world for an edit_own-only user (not superadmin, no stock / agents slug), plus a second
    salesperson with SRT and MCH accounts of their own. `w.cust_a`/`w.twin1`/`w.twin2` (SRT) and `w.cust_b` (MCH) are
    the user's own accounts."""
    w = make_world(db, slugs=slugs, superadmin=False)
    other_contact = seed_plain_contact(db, "ZZT Other Salesperson")
    other = seed_sales_agent(db, other_contact, "OT")
    with company_scope(db, None):
        theirs = seed_customer(db, unique_code("ZZT Gamma Theirs"), other, company_id=w.srt)
        theirs_m = seed_customer(db, unique_code("ZZT Delta Theirs"), other, company_id=w.mch)
    db.commit()
    return SimpleNamespace(w=w, other=other, other_contact=other_contact, theirs=theirs, theirs_m=theirs_m)


def add_customer(db, w: W, name: str, agent=None, *, company: str | None = None):
    """One more account; `agent` None = the user's own agent."""
    from app.models.sales_agent import SalesAgent

    if agent is None:
        agent = db.query(SalesAgent).filter(SalesAgent.contact_id == w.contact["pk"]).first()
    with company_scope(db, None):
        row = seed_customer(db, name, agent, company_id=company or w.srt)
    db.commit()
    return row


def owner_tag(db, name: str = SRT_TAG, *, active: bool = True, types=None) -> ContactTag:
    """The tag of that name (any case), set to exactly this name, state and settings; created when missing. The
    template world (`ensure_template_world`) seeds both owner tags already and names are unique case-insensitively."""
    settings = {"access_types": list(types if types is not None else TAG_TYPES.get(name) or TAG_TYPES[SRT_TAG])}
    tag = db.query(ContactTag).filter(func.lower(ContactTag.name) == name.lower()).first()
    if tag is None:
        tag = ContactTag(id=str(uuid.uuid4()), name=name, is_active=active, settings=settings)
        db.add(tag)
    else:
        tag.name, tag.is_active, tag.settings = name, active, settings
    db.commit()
    return tag


def drop_tag(db, name: str) -> None:
    """UAC A7: the owner tag deleted (the template world seeds it)."""
    db.execute(delete(ContactTag).where(func.lower(ContactTag.name) == name.lower()))
    db.commit()


def owner_tags(db) -> None:
    owner_tag(db, SRT_TAG)
    owner_tag(db, MCH_TAG)


def tags_of(db, contact_id: str) -> list[str]:
    db.expire_all()
    rows = db.execute(
        select(ContactTag.name)
        .join(respond_contact_tags, respond_contact_tags.c.tag_id == ContactTag.id)
        .where(respond_contact_tags.c.contact_id == str(contact_id))
    ).all()
    return sorted(name for (name,) in rows)


def tag_contact(db, contact_id: str, tag: ContactTag) -> None:
    db.execute(insert(respond_contact_tags).values(contact_id=str(contact_id), tag_id=str(tag.id)))
    db.commit()


def ai_on(db, row: RespondContact) -> RespondContact:
    with company_scope(db, None):
        db.query(RespondContact).filter(RespondContact.id == row.id).update({"chatbot_allowed": True})
    db.commit()
    return row


def propose(db, w: W, rows):
    from app.services.chatbot.agent import batch

    return batch.propose_rows(db, ctx_of(db, w), GRANT, rows, seen_ids=set())


def store(db, w: W, steps):
    from app.services.chatbot.agent import actions

    return actions.store_proposal(
        db, ctx_of(db, w), conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=steps
    )


def confirm(db, w: W, action):
    from app.services.chatbot.agent import actions

    return actions.confirm(db, w.respond_id, str(action.id), via="console")


def grant(db, w: W, rows):
    """Propose the rows, store, confirm. Returns (outcome, steps, skipped, action)."""
    steps, skipped, waiting = propose(db, w, rows)
    assert steps, f"nothing proposed: skipped={skipped} waiting={waiting}"
    action = store(db, w, steps)
    return confirm(db, w, action), steps, skipped, action


def reason(skipped, n: int = 1) -> str:
    """The skip reason of the n-th input row (1-based), as written."""
    found = [s for s in skipped if s["row"] == n]
    assert found, f"row {n} was not skipped: {skipped}"
    return found[0]["reason"]


def update_step(db, w: W, args: dict, *, seen):
    from app.services.chatbot.agent import writes

    return writes.propose_step(db, ctx_of(db, w), UPDATE, args, seen_ids={str(s).lower() for s in seen})


def update_and_confirm(db, w: W, args: dict, *, seen):
    res, step = update_step(db, w, args, seen=seen)
    assert res.status == "proposed", f"{res.status}: {res.message}"
    outcome = confirm(db, w, store(db, w, [step]))
    assert outcome.status == "executed", outcome.steps
    return step, outcome


# ------------------------------------------------------------------ A1 who may grant


def test_A1_an_edit_own_holder_is_offered_the_grant_write_and_a_user_with_neither_slug_is_not(db):
    from app.services.chatbot.agent import writes

    own = own_world(db).w
    none = make_world(db, slugs=(NEITHER,), superadmin=False)

    assert GRANT in {d.name for d in writes.permitted_writes(db, ctx_of(db, own))}
    assert GRANT not in {d.name for d in writes.permitted_writes(db, ctx_of(db, none))}


def test_A1_an_edit_own_holder_is_offered_the_batch_tool_for_the_grant(db):
    from app.services.chatbot.agent import batch

    own = own_world(db).w
    schema = batch.batch_tool_schema(db, ctx_of(db, own))

    assert schema is not None
    assert GRANT in schema["function"]["parameters"]["properties"]["write"]["enum"]


def test_A1_an_edit_own_holder_proposes_and_confirms_a_single_row_grant_of_a_new_phone(db):
    from app.services.chatbot.agent import writes

    w = own_world(db).w
    phone = fake_phone()

    res, step = writes.propose_step(
        db, ctx_of(db, w), GRANT, row_(phone, name="ZZT Single Row", role="employee", codes=[w.cust_a.customer_code]),
        seen_ids=set(),
    )
    assert res.status == "proposed", f"{res.status}: {res.message}"
    outcome = confirm(db, w, store(db, w, [step]))

    assert outcome.status == "executed", outcome.steps
    after = state(db, phone)
    assert after is not None and after["links"] == [str(w.cust_a.id)]


def test_A1_a_direct_grant_propose_without_either_slug_is_denied(db):
    from app.services.chatbot.agent import writes

    w = make_world(db, slugs=(NEITHER,), superadmin=False)

    res, step = writes.propose_step(
        db, ctx_of(db, w), GRANT, row_(fake_phone(), codes=[w.cust_a.customer_code]), seen_ids=set()
    )

    assert res.status == "denied" and step is None


# ------------------------------------------------------------------ A2 own scope, codes


def test_A2_an_own_accounts_code_resolves(db):
    w = own_world(db).w

    steps, skipped, waiting = propose(db, w, [row_(fake_phone(), codes=[w.cust_a.customer_code])])

    assert skipped == [] and waiting == []
    assert len(steps) == 1


def test_A2_another_salespersons_code_and_a_nonexistent_code_are_refused_with_the_same_text(db):
    o = own_world(db)
    none_code = "ZZT-NO-SUCH-CODE"

    steps, skipped, _ = propose(db, o.w, [
        row_(fake_phone(), codes=[o.theirs.customer_code]),
        row_(fake_phone(), codes=[none_code]),
    ])

    assert steps == []
    theirs_reason, none_reason = reason(skipped, 1), reason(skipped, 2)
    assert theirs_reason == f'No customer with the code "{o.theirs.customer_code}" in your accounts.'
    assert none_reason == f'No customer with the code "{none_code}" in your accounts.'
    assert theirs_reason.replace(o.theirs.customer_code, "<c>") == none_reason.replace(none_code, "<c>")


# ------------------------------------------------------------------ A3 own scope, names


def test_A3_an_exact_name_shared_with_another_salespersons_account_links_only_the_own_one(db):
    o = own_world(db)
    shared = unique_code("ZZT Shared Shop", alpha=True)
    mine = add_customer(db, o.w, shared)
    add_customer(db, o.w, shared, o.other)

    outcome, steps, skipped, _ = grant(db, o.w, [row_(fake_phone(), role="employee", names=[shared])])

    assert skipped == [] and outcome.status == "executed", outcome.steps
    phone = steps[0]["shown"]["phone"]
    assert state(db, phone)["links"] == [str(mine.id)]


def test_A3_a_phrase_fitting_two_own_accounts_waits_for_the_pick_and_offers_only_own_accounts(db):
    o = own_world(db)
    stem = unique_code("ZZT Yoo Living", alpha=True)
    own1 = add_customer(db, o.w, f"{stem} A/C I")
    own2 = add_customer(db, o.w, f"{stem} A/C III")
    theirs = add_customer(db, o.w, f"{stem} A/C IV", o.other)
    phone = fake_phone()

    steps, skipped, waiting = propose(db, o.w, [row_(phone, names=[stem])])

    assert steps == [] and skipped == []
    assert [x["row"] for x in waiting] == [1]
    codes = {c["code"] for c in waiting[0]["candidates"]}
    assert codes == {own1.customer_code, own2.customer_code}
    assert theirs.customer_code not in json.dumps(waiting)
    assert state(db, phone) is None


# ------------------------------------------------------------------ A4 word fallback


def test_A4_a_written_name_sharing_a_word_with_an_own_account_offers_it_as_a_pick(db):
    o = own_world(db)
    kbox = add_customer(db, o.w, "ZZT KBOX LOGISTICS")
    theirs_kbox = add_customer(db, o.w, "ZZT KBOX TRADING", o.other)
    phone = fake_phone()

    steps, skipped, waiting = propose(db, o.w, [row_(phone, names=["ZZT KBOX LOGISTIC & SUPPLY"])])

    assert steps == [] and skipped == [], skipped
    assert len(waiting) == 1
    candidates = waiting[0]["candidates"]
    assert candidates and candidates[0]["code"] == kbox.customer_code  # most shared words first
    assert theirs_kbox.customer_code not in {c["code"] for c in candidates}
    assert len(candidates) <= 10
    assert state(db, phone) is None  # never linked without the pick


def test_A4_a_written_name_sharing_no_word_is_refused_in_own_scope(db):
    w = own_world(db).w

    steps, skipped, waiting = propose(db, w, [row_(fake_phone(), names=["Nothing Matches Here"])])

    assert steps == [] and waiting == []
    assert reason(skipped) == 'No customer named "Nothing Matches Here" in your accounts.'


# ------------------------------------------------------------------ A5 the whole template


def test_A5_an_edit_own_only_grant_writes_the_whole_template(db):
    from app.models.access import (
        AccessAgent,
        ContactAgentAccess,
        StockVisibilityPolicy,
        respond_contact_market_segments,
    )
    from app.models.company import RespondContactCompany
    from app.models.inventory import Warehouse
    from app.models.media import ContactMediaLimit

    w = own_world(db).w
    phone = fake_phone()

    outcome, _, _, _ = grant(db, w, [row_(phone, name="ZZT Template", role="employee", codes=[w.cust_a.customer_code])])

    assert outcome.status == "executed", outcome.steps
    after = state(db, phone)
    cid = after["id"]
    assert "end_user" in after["types"]
    assert after["chatbot_allowed"] is True
    with company_scope(db, None):
        assert db.query(RespondContactCompany).filter(
            RespondContactCompany.respond_contact_id == cid, RespondContactCompany.company_id == w.srt
        ).count() == 1
        policy = db.query(StockVisibilityPolicy).filter(StockVisibilityPolicy.contact_id == cid).one_or_none()
        assert policy is not None and policy.mode == "availability"
        locations = {
            str(i) for (i,) in db.query(Warehouse.id).filter(
                Warehouse.company_id == w.srt, Warehouse.warehouse_code.in_(("BRW", "MWH"))
            )
        }
        assert len(locations) == 2 and set(map(str, policy.warehouse_ids or [])) >= locations
        agents = {
            code for (code,) in db.query(AccessAgent.code)
            .join(ContactAgentAccess, ContactAgentAccess.agent_id == AccessAgent.id)
            .filter(ContactAgentAccess.respond_contact_id == cid)
        }
        assert {"general_enquiries", "order_enquiries", "incoming_stock_enquiries"} <= agents
        segments = {
            code for (code,) in db.execute(
                select(respond_contact_market_segments.c.segment_code)
                .where(respond_contact_market_segments.c.contact_id == cid)
            )
        }
        assert "retail" in segments
        media = db.query(ContactMediaLimit).filter(
            ContactMediaLimit.contact_id == cid, ContactMediaLimit.modality == "image"
        ).one_or_none()
        assert media is not None and media.is_allowed is True


# ------------------------------------------------------------------ A6 owner via tag


def test_A6_a_sorento_owner_grant_adds_the_sorento_owner_tag_and_its_types(db):
    w = make_world(db)
    owner_tags(db)
    phone = fake_phone()

    outcome, steps, _, _ = grant(db, w, [row_(phone, role="owner", codes=[w.cust_a.customer_code])])

    assert outcome.status == "executed", outcome.steps
    assert "Business owner (Sorento)" in steps[0]["summary"]
    after = state(db, phone)
    assert tags_of(db, after["id"]) == [SRT_TAG]
    assert set(after["types"]) >= {"dealer", "cabana_dealer", "end_user"}


def test_A6_a_mocha_owner_grant_adds_the_mocha_owner_tag_and_mocha_dealer(db):
    w = make_world(db)
    owner_tags(db)
    phone = fake_phone()

    outcome, _, _, _ = grant(db, w, [row_(phone, role="owner", companies=["MCH"], codes=[w.cust_b.customer_code])])

    assert outcome.status == "executed", outcome.steps
    after = state(db, phone)
    assert tags_of(db, after["id"]) == [MCH_TAG]
    assert set(after["types"]) >= {"mocha_dealer", "end_user"}


def test_A6_an_employee_grant_adds_no_owner_tag_and_end_user_only(db):
    w = make_world(db)
    owner_tags(db)
    phone = fake_phone()

    outcome, _, _, _ = grant(db, w, [row_(phone, role="employee", codes=[w.cust_a.customer_code])])

    assert outcome.status == "executed", outcome.steps
    after = state(db, phone)
    assert tags_of(db, after["id"]) == []
    assert after["types"] == ["end_user"]


def test_A6_the_owner_tag_is_found_whatever_the_case_of_its_name(db):
    w = make_world(db)
    tag = owner_tag(db, "sorento BUSINESS owner", types=TAG_TYPES[SRT_TAG])
    phone = fake_phone()

    outcome, _, _, _ = grant(db, w, [row_(phone, role="owner", codes=[w.cust_a.customer_code])])

    assert outcome.status == "executed", outcome.steps
    assert tags_of(db, state(db, phone)["id"]) == [tag.name]


def test_A6_an_own_scope_owner_grant_adds_the_tag(db):
    w = own_world(db).w
    owner_tags(db)
    phone = fake_phone()

    outcome, _, _, _ = grant(db, w, [row_(phone, role="owner", codes=[w.cust_a.customer_code])])

    assert outcome.status == "executed", outcome.steps
    after = state(db, phone)
    assert tags_of(db, after["id"]) == [SRT_TAG]
    assert set(after["types"]) >= {"dealer", "cabana_dealer", "end_user"}


# ------------------------------------------------------------------ A7 missing / inactive tag


@pytest.mark.parametrize("which", ["missing", "inactive"])
def test_A7_a_missing_or_inactive_owner_tag_refuses_the_owner_row_and_the_employee_row_applies(db, which):
    w = make_world(db)
    owner_tag(db, MCH_TAG)
    if which == "inactive":
        owner_tag(db, SRT_TAG, active=False)
    else:
        drop_tag(db, SRT_TAG)
    owner_phone, employee_phone = fake_phone(), fake_phone()

    steps, skipped, _ = propose(db, w, [
        row_(owner_phone, role="owner", codes=[w.cust_a.customer_code]),
        row_(employee_phone, role="employee", codes=[w.cust_a.customer_code]),
    ])

    assert reason(skipped, 1) == missing_tag_text(SRT_TAG)
    assert [s["row"] for s in steps] == [2]
    outcome = confirm(db, w, store(db, w, steps))
    assert outcome.status == "executed", outcome.steps
    assert state(db, owner_phone) is None
    assert state(db, employee_phone)["links"] == [str(w.cust_a.id)]


# ------------------------------------------------------------------ A8 regrant


def test_A8_regranting_the_same_person_level_and_account_changes_nothing(db):
    w = own_world(db).w
    owner_tags(db)
    phone = fake_phone()
    first, _, _, _ = grant(db, w, [row_(phone, role="owner", codes=[w.cust_a.customer_code])])
    assert first.status == "executed", first.steps

    steps, skipped, _ = propose(db, w, [row_(phone, role="owner", codes=[w.cust_a.customer_code])])

    assert steps == []
    assert reason(skipped) == ALREADY


# ------------------------------------------------------------------ A9 staff phones


def _staff_phones(db) -> tuple[str, str]:
    """(phone of a CRM user's contact, phone of a sales agent's contact), both valid Malaysian mobiles."""
    user_contact = RespondContact(id=str(uuid.uuid4()), phone_number=fake_phone(), name="ZZT Staff User")
    agent_contact = RespondContact(id=str(uuid.uuid4()), phone_number=fake_phone(), name="ZZT Staff Agent")
    db.add_all([user_contact, agent_contact])
    db.flush()
    seed_user(db, contact_pk=user_contact.id, slugs=())
    seed_sales_agent(db, agent_contact.id, "SA")
    db.commit()
    return user_contact.phone_number, agent_contact.phone_number


@pytest.mark.parametrize("scope", ["edit_own", "edit"])
def test_A9_a_staff_users_phone_and_a_sales_agents_phone_are_refused(db, scope):
    w = own_world(db).w if scope == "edit_own" else make_world(db)
    user_phone, agent_phone = _staff_phones(db)

    steps, skipped, _ = propose(db, w, [
        row_(user_phone, role="employee", codes=[w.cust_a.customer_code]),
        row_(agent_phone, role="employee", codes=[w.cust_a.customer_code]),
    ])

    assert steps == []
    assert reason(skipped, 1) == STAFF
    assert reason(skipped, 2) == STAFF


# ------------------------------------------------------------------ A10 a person linked to another account


def test_A10_an_existing_contact_of_another_account_gets_the_own_link_and_never_sees_the_other_account(db):
    from app.models.chatbot_agent import AgentAction
    from app.services.chatbot.agent import batch

    o = own_world(db)
    w = o.w
    person = dealer(db, w, customers=(o.theirs,))
    hidden = (o.theirs.customer_code, o.theirs.customer_name)

    steps, skipped, waiting = propose(db, w, [row_(person.phone_number, role="employee", codes=[w.cust_a.customer_code])])
    assert steps, f"nothing proposed: {skipped}"
    preview = json.dumps([steps, skipped, waiting], default=str) + batch.preview_block(steps, skipped, waiting)
    assert ALSO in preview
    action = store(db, w, steps)
    audit_before = {str(i) for (i,) in db.query(AuditLog.id)}

    outcome = confirm(db, w, action)

    assert outcome.status == "executed", outcome.steps
    assert state(db, person.phone_number)["links"] == sorted([str(o.theirs.id), str(w.cust_a.id)])
    db.expire_all()
    stored = db.get(AgentAction, action.id).steps
    new_audit = [a for a in db.query(AuditLog).all() if str(a.id) not in audit_before]
    assert new_audit
    audit_text = json.dumps(
        [[a.event, a.entity_type, a.entity_id, a.old_values, a.new_values, a.description] for a in new_audit],
        default=str,
    )
    for label, blob in (
        ("preview", preview),
        ("stored steps", json.dumps(stored, default=str)),
        ("confirm result", json.dumps(dataclasses.asdict(outcome), default=str)),
        ("audit rows", audit_text),
    ):
        for secret in hidden:
            assert secret not in blob, f"the other account's {secret!r} leaked into the {label}"


# ------------------------------------------------------------------ A11 audit


def test_A11_one_audit_row_per_contact_with_the_salesperson_as_actor_and_created_said(db):
    w = own_world(db).w
    phone = fake_phone()

    outcome, _, _, _ = grant(db, w, [row_(phone, name="ZZT Audited", role="employee", codes=[w.cust_a.customer_code])])

    assert outcome.status == "executed", outcome.steps
    rows = events(db, state(db, phone)["id"])
    assert len(rows) == 1
    assert str(rows[0].user_id) == w.user_id
    assert "created" in json.dumps(rows[0].new_values or {}).lower()


# ------------------------------------------------------------------ B1 enqueue after the grant


def test_B1_a_grant_of_a_new_phone_enqueues_ensure_respond_contact_on_the_respond_io_queue(db, jobs):
    w = make_world(db)
    phone = fake_phone()

    outcome, _, _, _ = grant(db, w, [row_(phone, role="employee", codes=[w.cust_a.customer_code])])

    assert outcome.status == "executed", outcome.steps
    calls = respond_jobs(jobs)
    assert len(calls) == 1, [getattr(c.func, "__name__", c.func) for c in jobs]
    assert [str(a) for a in calls[0].args] == [state(db, phone)["id"]]
    assert calls[0].kwargs.get("queue_name") == "respond_io"
    assert calls[0].committed, "the job was enqueued before the grant committed"


def test_B1_a_grant_of_an_existing_contact_without_a_respond_id_enqueues_the_job(db, jobs):
    w = make_world(db)
    person = dealer(db, w)

    outcome, _, _, _ = grant(db, w, [row_(person.phone_number, role="employee", codes=[w.cust_a.customer_code])])

    assert outcome.status == "executed", outcome.steps
    calls = respond_jobs(jobs)
    assert len(calls) == 1 and [str(a) for a in calls[0].args] == [str(person.id)]
    assert calls[0].committed, "the job was enqueued before the grant committed"


def test_B1_a_grant_of_a_contact_that_has_a_respond_id_enqueues_nothing(db, jobs):
    w = make_world(db)
    person = dealer(db, w)
    with company_scope(db, None):
        db.query(RespondContact).filter(RespondContact.id == person.id).update({"respond_io_id": "900000222"})
    db.commit()

    outcome, _, _, _ = grant(db, w, [row_(person.phone_number, role="employee", codes=[w.cust_a.customer_code])])

    assert outcome.status == "executed", outcome.steps
    assert respond_jobs(jobs) == []


# ------------------------------------------------------------------ B2 the Respond.io job


class _SharedSession:
    """The test session handed to the job as its own `SessionLocal()`: closing it is a no-op."""

    def __init__(self, session):
        self._session = session

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getattr__(self, name):
        return getattr(self._session, name)


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://respond.invalid/v2/contact/phone:x")
    response = httpx.Response(status, request=request, json={"message": "zzt"})
    return httpx.HTTPStatusError(f"{status}", request=request, response=response)


@pytest.fixture()
def respond(monkeypatch, db):
    """A RespondClient whose every HTTP path is a recorder: `found` decides what get_contact_by_phone does, a send
    or a raw HTTP client fails the test. Returns the recorder; `job()` runs ensure_respond_contact in-process."""
    import app.database as database
    from app.services import integration_service
    from app.services.integration_service import RespondClient

    rec = SimpleNamespace(calls=[], forbidden=[], lookup="found", key=True)

    def creds(*_a, **_k):
        return ("zzt-test-key", "https://respond.invalid", None) if rec.key else None

    monkeypatch.setattr(integration_service, "_resolve_workspace_credentials", creds)
    monkeypatch.setattr(integration_service.settings, "respond_api_key", None, raising=False)

    def forbid(name):
        def _f(self, *a, **k):
            rec.forbidden.append(name)
            raise AssertionError(f"RespondClient.{name} must not be called")
        return _f

    monkeypatch.setattr(RespondClient, "_http", staticmethod(lambda *a, **k: forbid("_http")(None)))
    for name in dir(RespondClient):
        if "send" in name or name == "_post_contact_message":
            monkeypatch.setattr(RespondClient, name, forbid(name))

    def get_by_phone(self, phone):
        rec.calls.append(("get_contact_by_phone", phone))
        if rec.lookup == "found":
            return {"id": 900000111, "phone": phone}
        raise _http_error(404 if rec.lookup == "missing" else 500)

    def create(self, phone, first_name=None, *a, **k):
        rec.calls.append(("create_contact", phone, first_name))
        return {"id": 900000123}

    def update(self, identifier, payload):
        rec.calls.append(("update_contact", identifier, payload))
        return {}

    monkeypatch.setattr(RespondClient, "get_contact_by_phone", get_by_phone)
    monkeypatch.setattr(RespondClient, "get_contact_by_identifier", forbid("get_contact_by_identifier"))
    monkeypatch.setattr(RespondClient, "create_contact", create, raising=False)
    monkeypatch.setattr(RespondClient, "update_contact", update)
    monkeypatch.setattr(database, "SessionLocal", lambda *a, **k: _SharedSession(db))

    def job(contact_id: str):
        import app.tasks.respond_io_tasks as tasks

        monkeypatch.setattr(tasks, "SessionLocal", lambda *a, **k: _SharedSession(db), raising=False)
        from app.tasks.respond_io_tasks import ensure_respond_contact

        return ensure_respond_contact(contact_id)

    rec.job = job
    return rec


def _job_contact(db) -> RespondContact:
    row = RespondContact(id=str(uuid.uuid4()), phone_number=fake_phone(), name="ZZT Job Person")
    db.add(row)
    db.commit()
    return row


def _respond_id(db, contact_id: str):
    db.expire_all()
    with company_scope(db, None):
        return db.query(RespondContact.respond_io_id).filter(RespondContact.id == str(contact_id)).scalar()


def _backend_id_written(rec, respond_id: str) -> bool:
    return any(
        c[0] == "update_contact" and respond_id in str(c[1]) and "backend_id" in json.dumps(c[2], default=str)
        for c in rec.calls
    )


def test_B2_a_contact_found_by_phone_gets_its_respond_id_stored_and_backend_id_written(db, respond):
    contact = _job_contact(db)
    respond.lookup = "found"

    respond.job(str(contact.id))

    assert _respond_id(db, contact.id) == "900000111"
    assert not any(c[0] == "create_contact" for c in respond.calls)
    assert _backend_id_written(respond, "900000111")
    assert respond.forbidden == []


def test_B2_a_contact_not_in_respond_is_created_with_phone_and_first_name_then_stored(db, respond):
    contact = _job_contact(db)
    respond.lookup = "missing"

    respond.job(str(contact.id))

    created = [c for c in respond.calls if c[0] == "create_contact"]
    assert len(created) == 1
    _, phone, first_name = created[0]
    digits = "".join(ch for ch in contact.phone_number if ch.isdigit())
    assert "".join(ch for ch in str(phone) if ch.isdigit()) == digits
    assert first_name == "ZZT Job Person"
    assert _respond_id(db, contact.id) == "900000123"
    assert _backend_id_written(respond, "900000123")
    assert respond.forbidden == []


def test_B2_no_respond_key_makes_the_job_a_no_op_without_any_http_call(db, respond):
    contact = _job_contact(db)
    respond.key = False

    respond.job(str(contact.id))

    assert respond.calls == [] and respond.forbidden == []
    assert _respond_id(db, contact.id) is None


def test_B2_a_respond_error_other_than_404_raises_so_rq_retries(db, respond):
    contact = _job_contact(db)
    respond.lookup = "error"

    with pytest.raises(Exception) as caught:
        respond.job(str(contact.id))

    assert not isinstance(caught.value, (ImportError, AssertionError)), caught.value
    assert not any(c[0] == "create_contact" for c in respond.calls)
    assert _respond_id(db, contact.id) is None
    assert respond.forbidden == []


# ------------------------------------------------------------------ C1 / C2 role change through tags


def test_C1_role_owner_on_an_own_accounts_contact_adds_the_sorento_owner_tag_and_its_types(db):
    w = own_world(db).w
    owner_tags(db)
    person = dealer(db, w, customers=(w.cust_a,))

    update_and_confirm(db, w, {"contact_id": person.id, "role": "owner"}, seen={person.id})

    assert tags_of(db, person.id) == [SRT_TAG]
    assert set(state(db, person.phone_number)["types"]) >= {"dealer", "cabana_dealer", "end_user"}


def test_C1_role_owner_with_the_owner_tag_missing_is_refused_with_the_a7_text(db):
    w = own_world(db).w
    owner_tag(db, MCH_TAG)
    drop_tag(db, SRT_TAG)
    person = dealer(db, w, customers=(w.cust_a,))

    res, step = update_step(db, w, {"contact_id": person.id, "role": "owner"}, seen={person.id})

    assert step is None and res.status in ("invalid", "denied")
    assert missing_tag_text(SRT_TAG) in (res.message or "")


def test_C2_role_employee_removes_the_owner_tag_and_owner_types_and_keeps_end_user(db):
    w = own_world(db).w
    owner_tags(db)
    srt_tag = db.query(ContactTag).filter(ContactTag.name == SRT_TAG).one()
    person = dealer(db, w, types=("dealer", "cabana_dealer", "end_user"), customers=(w.cust_a,))
    tag_contact(db, person.id, srt_tag)

    update_and_confirm(db, w, {"contact_id": person.id, "role": "employee"}, seen={person.id})

    assert tags_of(db, person.id) == []
    assert state(db, person.phone_number)["types"] == ["end_user"]


# ------------------------------------------------------------------ C3 demote outside own accounts


def test_C3_own_scope_demote_of_a_contact_also_linked_to_another_account_is_refused(db):
    o = own_world(db)
    w = o.w
    owner_tags(db)
    person = dealer(db, w, types=("dealer", "cabana_dealer", "end_user"), customers=(w.cust_a, o.theirs))

    res, step = update_step(db, w, {"contact_id": person.id, "role": "employee"}, seen={person.id})

    assert step is None and res.status in ("invalid", "denied")
    assert DEMOTE_REFUSED in (res.message or "")
    assert set(state(db, person.phone_number)["types"]) == {"dealer", "cabana_dealer", "end_user"}


# ------------------------------------------------------------------ C4 last link turns AI replies off


def test_C4_unlinking_the_last_link_turns_ai_replies_off_in_the_same_change(db):
    w = own_world(db).w
    person = ai_on(db, dealer(db, w, customers=(w.cust_a,)))

    step, _ = update_and_confirm(
        db, w, {"contact_id": person.id, "unlink_customer_ids": [str(w.cust_a.id)]}, seen={person.id, w.cust_a.id}
    )

    assert "AI replies on -> off" in step["summary"]
    after = state(db, person.phone_number)
    assert after["links"] == [] and after["chatbot_allowed"] is False


def test_C4_unlinking_one_of_two_own_links_leaves_ai_replies_on(db):
    w = own_world(db).w
    person = ai_on(db, dealer(db, w, customers=(w.cust_a, w.twin1)))

    step, _ = update_and_confirm(
        db, w, {"contact_id": person.id, "unlink_customer_ids": [str(w.cust_a.id)]}, seen={person.id, w.cust_a.id}
    )

    assert "AI replies" not in step["summary"]
    assert state(db, person.phone_number)["chatbot_allowed"] is True


@pytest.mark.parametrize("elsewhere", ["another salesperson", "another company"])
def test_C4_a_link_the_user_cannot_see_still_counts_so_ai_replies_stay_on(db, elsewhere):
    o = own_world(db)
    w = o.w
    if elsewhere == "another salesperson":
        other_link = o.theirs
    else:
        hidden = _company(db, "ZZH", "ZZT Hidden Co")
        with company_scope(db, None):
            other_link = seed_customer(db, unique_code("ZZT Hidden Shop"), None, company_id=hidden)
        db.commit()
    person = ai_on(db, dealer(db, w, customers=(w.cust_a, other_link)))

    step, _ = update_and_confirm(
        db, w, {"contact_id": person.id, "unlink_customer_ids": [str(w.cust_a.id)]}, seen={person.id, w.cust_a.id}
    )

    assert "AI replies" not in step["summary"]
    with company_scope(db, None):
        left = {
            str(c) for (c,) in db.query(RespondContactCustomer.customer_id)
            .filter(RespondContactCustomer.contact_id == person.id)
        }
    assert left == {str(other_link.id)}
    assert state(db, person.phone_number)["chatbot_allowed"] is True


# ------------------------------------------------------------------ C5 no leak in the update tool


def _leak_check(blobs: dict, hidden: tuple) -> None:
    for label, blob in blobs.items():
        for secret in hidden:
            assert secret not in blob, f"the other account's {secret!r} leaked into the {label}"


# "ai off" on a shared contact is refused since crew live x3 (C6); C6 checks that refusal names nothing.
@pytest.mark.parametrize("change", ["unlink own"])
def test_C5_own_scope_update_never_names_another_salespersons_account(db, change):
    from app.models.chatbot_agent import AgentAction
    from app.services.chatbot.agent import batch

    o = own_world(db)
    w = o.w
    person = ai_on(db, dealer(db, w, customers=(w.cust_a, o.theirs)))
    hidden = (o.theirs.customer_code, o.theirs.customer_name)
    if change == "unlink own":
        args, seen = {"contact_id": person.id, "unlink_customer_ids": [str(w.cust_a.id)]}, {person.id, w.cust_a.id}
    else:
        args, seen = {"contact_id": person.id, "chatbot_allowed": False}, {person.id}

    res, step = update_step(db, w, args, seen=seen)
    assert res.status == "proposed", f"{res.status}: {res.message}"
    action = store(db, w, [step])
    preview = json.dumps([dataclasses.asdict(res) if dataclasses.is_dataclass(res) else vars(res), step], default=str)
    preview += batch.preview_block([step], [])
    audit_before = {str(i) for (i,) in db.query(AuditLog.id)}

    outcome = confirm(db, w, action)

    assert outcome.status == "executed", outcome.steps
    db.expire_all()
    stored = db.get(AgentAction, action.id).steps
    new_audit = [a for a in db.query(AuditLog).all() if str(a.id) not in audit_before]
    assert new_audit
    audit_text = json.dumps(
        [[a.event, a.entity_type, a.entity_id, a.old_values, a.new_values, a.description] for a in new_audit],
        default=str,
    )
    _leak_check(
        {
            "preview": preview,
            "stored steps": json.dumps(stored, default=str),
            "confirm result": json.dumps(dataclasses.asdict(outcome), default=str),
            "audit rows": audit_text,
        },
        hidden,
    )
    if change == "unlink own":
        # The link that stays is named as such, never by its code.
        assert "another account" in audit_text
    with company_scope(db, None):
        left = {
            str(c) for (c,) in db.query(RespondContactCustomer.customer_id)
            .filter(RespondContactCustomer.contact_id == person.id)
        }
    assert str(o.theirs.id) in left


# ------------------------------------------------------------------ review round 1 (UAC A12-A16, B3)

NO_OWN_ACCOUNT = "Name one of your accounts for this person (code or name)."
KEPT = "kept as they are: AI replies, stock, brands and media (another account also has this person)"


def test_A12_an_own_scope_row_naming_no_account_is_refused_for_new_and_existing_contacts_and_both_roles(db):
    o = own_world(db)
    existing = dealer(db, o.w, customers=(o.theirs,))
    rows = [
        row_(fake_phone(), role="employee"),
        row_(fake_phone(), role="owner"),
        row_(existing.phone_number, role="employee"),
        row_(existing.phone_number.replace("+6019", "+6018"), role="owner"),
    ]

    steps, skipped, waiting = propose(db, o.w, rows)

    assert steps == [] and waiting == []
    for n in (1, 2, 3, 4):
        assert reason(skipped, n) == NO_OWN_ACCOUNT


def _settings_of(db, contact_id: str) -> dict:
    from app.models.access import StockVisibilityPolicy
    from app.models.media import ContactMediaLimit

    db.expire_all()
    with company_scope(db, None):
        row = db.get(RespondContact, contact_id)
        policy = db.query(StockVisibilityPolicy).filter(StockVisibilityPolicy.contact_id == contact_id).one_or_none()
        media = db.query(ContactMediaLimit).filter(ContactMediaLimit.contact_id == contact_id).all()
        return {
            "switches": {
                k: getattr(row, k) for k in (
                    "chatbot_allowed", "chatbot_stock_allowed", "chatbot_eta_offset_applied", "escalation_allowed",
                    "packing_list_allowed",
                )
            },
            "brands": sorted(map(str, row.brand_ids or [])),
            "stock": None if policy is None else (
                policy.mode, sorted(map(str, policy.warehouse_ids or [])),
                sorted(map(str, policy.excluded_warehouse_ids or [])), policy.hide_zero_locations,
            ),
            "media": sorted((m.modality, m.is_allowed) for m in media),
        }


def test_A13_an_own_scope_grant_on_a_contact_of_another_account_adds_only_the_additive_facets(db):
    from app.models.access import AccessAgent, ContactAgentAccess, StockVisibilityPolicy, respond_contact_market_segments
    from app.models.inventory import Warehouse

    o = own_world(db)
    w = o.w
    person = dealer(db, w, types=(), companies=(), customers=(o.theirs,))
    with company_scope(db, None):
        brw = db.query(Warehouse.id).filter(Warehouse.company_id == w.srt, Warehouse.warehouse_code == "BRW").scalar()
        db.query(RespondContact).filter(RespondContact.id == person.id).update({
            "chatbot_allowed": False, "chatbot_stock_allowed": False, "chatbot_eta_offset_applied": False,
            "escalation_allowed": True, "packing_list_allowed": True, "brand_ids": [str(uuid.uuid4())],
        })
        db.add(StockVisibilityPolicy(contact_id=person.id, mode="detailed", excluded_warehouse_ids=[str(brw)]))
    db.commit()
    kept = _settings_of(db, person.id)

    outcome, steps, skipped, _ = grant(db, w, [row_(person.phone_number, role="employee", codes=[w.cust_a.customer_code])])

    assert skipped == [] and outcome.status == "executed", outcome.steps
    summary = steps[0]["summary"]
    assert KEPT in summary
    summary = summary.replace(KEPT, "")
    for word in ("AI replies", "stock replies", "ETA offset", "hand-over", "packing list", "stock check",
                 "stock locations", "brands", "image replies"):
        assert word not in summary, f"{word!r} is planned on another account's contact: {summary}"
    after = state(db, person.phone_number)
    assert after["links"] == sorted([str(o.theirs.id), str(w.cust_a.id)])
    assert w.srt in after["companies"] and "end_user" in after["types"]
    with company_scope(db, None):
        agents = {
            code for (code,) in db.query(AccessAgent.code)
            .join(ContactAgentAccess, ContactAgentAccess.agent_id == AccessAgent.id)
            .filter(ContactAgentAccess.respond_contact_id == person.id)
        }
        segments = {
            c for (c,) in db.execute(
                select(respond_contact_market_segments.c.segment_code)
                .where(respond_contact_market_segments.c.contact_id == person.id)
            )
        }
    assert {"general_enquiries", "order_enquiries", "incoming_stock_enquiries"} <= agents
    assert "retail" in segments
    assert _settings_of(db, person.id) == kept


def test_A14_an_own_scope_owner_grant_for_a_contact_of_another_account_is_refused(db):
    o = own_world(db)
    person = dealer(db, o.w, customers=(o.theirs,))

    steps, skipped, _ = propose(db, o.w, [row_(person.phone_number, role="owner", codes=[o.w.cust_a.customer_code])])

    assert steps == []
    assert reason(skipped) == DEMOTE_REFUSED
    assert tags_of(db, person.id) == []


def test_A14_an_own_scope_promote_through_the_update_tool_for_a_contact_of_another_account_is_refused(db):
    o = own_world(db)
    w = o.w
    person = dealer(db, w, customers=(w.cust_a, o.theirs))

    res, step = update_step(db, w, {"contact_id": person.id, "role": "owner"}, seen={person.id})

    assert step is None and res.status in ("invalid", "denied")
    assert DEMOTE_REFUSED in (res.message or "")
    assert tags_of(db, person.id) == [] and state(db, person.phone_number)["types"] == ["end_user"]


@pytest.mark.parametrize(
    "settings",
    [
        {"access_types": ["dealer", "cabana_dealer"], "chatbot": {"stock_allowed": True}},
        {},
        {"access_types": ["dealer", "cabana_dealer", "mocha_dealer"]},
    ],
    ids=["extra section", "no access types", "more types"],
)
def test_A15_an_owner_tag_whose_settings_are_not_exactly_the_template_counts_as_missing(db, settings):
    w = make_world(db)
    with company_scope(db, None):
        db.query(ContactTag).filter(ContactTag.name == SRT_TAG).update({"settings": settings})
    db.commit()
    phone = fake_phone()

    steps, skipped, _ = propose(db, w, [row_(phone, role="owner", codes=[w.cust_a.customer_code])])

    assert steps == []
    assert reason(skipped) == missing_tag_text(SRT_TAG)


def test_A15_the_template_owner_types_in_another_order_still_count(db):
    w = make_world(db)
    owner_tag(db, SRT_TAG, types=["cabana_dealer", "dealer"])
    phone = fake_phone()

    outcome, _, _, _ = grant(db, w, [row_(phone, role="owner", codes=[w.cust_a.customer_code])])

    assert outcome.status == "executed", outcome.steps
    assert tags_of(db, state(db, phone)["id"]) == [SRT_TAG]


@pytest.mark.parametrize("form", ["international", "local"])
def test_A16_a_new_phone_equal_to_a_users_contact_number_is_refused_as_staff(db, form):
    from app.models.user import User

    w = make_world(db)
    phone = fake_phone()
    digits = phone.lstrip("+")
    staff = seed_user(db, contact_pk=None, slugs=())
    db.query(User).filter(User.id == staff).update(
        {"contact_number": f"+{digits}" if form == "international" else f"0{digits[2:5]}-{digits[5:]}"}
    )
    db.commit()

    steps, skipped, _ = propose(db, w, [row_(phone, role="employee", codes=[w.cust_a.customer_code])])

    assert steps == []
    assert reason(skipped) == STAFF
    assert state(db, phone) is None


def test_B3_the_job_looks_the_phone_up_in_its_normalised_form(db, respond):
    phone = fake_phone()
    digits = phone.lstrip("+")
    contact = RespondContact(id=str(uuid.uuid4()), phone_number=f"0{digits[2:5]}-{digits[5:]}", name="ZZT Quoted")
    db.add(contact)
    db.commit()

    respond.job(str(contact.id))

    looked = [c for c in respond.calls if c[0] == "get_contact_by_phone"]
    assert looked == [("get_contact_by_phone", phone)]  # +601..., no spaces, dashes or URL quoting


def test_B3_create_contact_puts_the_normalised_phone_in_the_path(monkeypatch):
    from app.services.integration_service import RespondClient

    sent = {}

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, headers=None, json=None):
            sent.update(url=url, json=json)
            return httpx.Response(200, request=httpx.Request("POST", url), json={"id": 900000124})

    monkeypatch.setattr(RespondClient, "_http", staticmethod(lambda *a, **k: _Client()))
    phone = fake_phone()

    out = RespondClient(api_key="zzt-key", base_url="https://respond.invalid").create_contact(phone, "ZZT Made")

    assert out == {"id": 900000124}
    assert sent["url"] == f"https://respond.invalid/v2/contact/phone:{phone}"
    assert sent["json"]["phone"] == phone and sent["json"]["firstName"] == "ZZT Made"


def test_B3_a_phone_that_does_not_normalise_skips_the_job_without_any_http_call(db, respond):
    contact = RespondContact(id=str(uuid.uuid4()), phone_number="12345", name="ZZT Not A Mobile")
    db.add(contact)
    db.commit()

    out = respond.job(str(contact.id))

    assert respond.calls == [] and respond.forbidden == []
    assert str(out.get("status", "")).startswith("skipped")
    assert _respond_id(db, contact.id) is None


def test_B3_a_retry_for_a_contact_that_has_its_respond_id_still_writes_backend_id(db, respond):
    contact = _job_contact(db)
    with company_scope(db, None):
        db.query(RespondContact).filter(RespondContact.id == contact.id).update({"respond_io_id": "900000333"})
    db.commit()

    respond.job(str(contact.id))

    assert not any(c[0] in ("get_contact_by_phone", "create_contact") for c in respond.calls)
    assert _backend_id_written(respond, "900000333")
    assert respond.forbidden == []


def test_B3_an_own_scope_stored_action_carries_own_link_ids_and_a_count_of_the_others(db):
    from app.models.chatbot_agent import AgentAction

    o = own_world(db)
    w = o.w
    person = dealer(db, w, customers=(w.cust_a, o.theirs))

    steps, skipped, _ = propose(db, w, [row_(person.phone_number, role="employee", codes=[w.twin1.customer_code])])
    assert steps, skipped
    assert steps[0]["before"]["links"] == [str(w.cust_a.id)]
    assert steps[0]["before"]["other_links"] == 1
    action = store(db, w, steps)
    outcome = confirm(db, w, action)

    assert outcome.status == "executed", outcome.steps
    db.expire_all()
    stored = json.dumps(db.get(AgentAction, action.id).steps, default=str)
    assert str(o.theirs.id) not in stored
    assert state(db, person.phone_number)["links"] == sorted([str(w.cust_a.id), str(o.theirs.id), str(w.twin1.id)])


# ------------------------------------------------------------------ review round 2 (B3 update tool, security L1/L2)


# "ai off" on a shared contact is refused since crew live x3 (C6); C6 checks that refusal names nothing.
@pytest.mark.parametrize("change", ["unlink own"])
def test_B3_own_scope_update_never_stores_the_id_of_another_salespersons_account(db, change):
    from app.models.chatbot_agent import AgentAction

    o = own_world(db)
    w = o.w
    person = ai_on(db, dealer(db, w, customers=(w.cust_a, o.theirs)))
    hidden = str(o.theirs.id)
    if change == "unlink own":
        args, seen = {"contact_id": person.id, "unlink_customer_ids": [str(w.cust_a.id)]}, {person.id, w.cust_a.id}
    else:
        args, seen = {"contact_id": person.id, "chatbot_allowed": False}, {person.id}

    res, step = update_step(db, w, args, seen=seen)
    assert res.status == "proposed", f"{res.status}: {res.message}"
    assert hidden not in json.dumps(step, default=str)
    assert step["before"]["other_links"] == 1
    action = store(db, w, [step])
    audit_before = {str(i) for (i,) in db.query(AuditLog.id)}

    outcome = confirm(db, w, action)

    assert outcome.status == "executed", outcome.steps
    db.expire_all()
    stored = db.get(AgentAction, action.id).steps
    contact_audit = [
        a for a in db.query(AuditLog).all()
        if str(a.id) not in audit_before and a.event == "contact.access_agent"
    ]
    assert contact_audit
    for label, blob in (
        ("stored steps", json.dumps(stored, default=str)),
        ("confirm result", json.dumps(dataclasses.asdict(outcome), default=str)),
        ("audit row", json.dumps([[a.old_values, a.new_values, a.description] for a in contact_audit], default=str)),
    ):
        assert hidden not in blob, f"the other account's id leaked into the {label}"
    if change == "unlink own":
        assert "another account" in json.dumps([a.old_values for a in contact_audit], default=str)


def test_L1_a_demote_of_a_contact_holding_a_non_standard_owner_tag_is_refused(db):
    w = own_world(db).w
    tag = db.query(ContactTag).filter(ContactTag.name == SRT_TAG).one()
    person = dealer(db, w, types=("dealer", "cabana_dealer", "end_user"), customers=(w.cust_a,))
    tag_contact(db, person.id, tag)
    with company_scope(db, None):
        db.query(ContactTag).filter(ContactTag.id == tag.id).update(
            {"settings": {"access_types": ["dealer", "cabana_dealer"], "chatbot": {"stock_allowed": True}}}
        )
    db.commit()

    res, step = update_step(db, w, {"contact_id": person.id, "role": "employee"}, seen={person.id})

    assert step is None and res.status in ("invalid", "denied")
    assert f'The "{SRT_TAG}" tag is not the standard one; ask the office.' in (res.message or "")
    assert tags_of(db, person.id) == [SRT_TAG]


def test_L2_an_edit_own_console_operator_for_an_edit_user_grants_only_the_additive_facets(db):
    from app.models.company import UserCompany
    from app.services.chatbot.agent import actions, batch

    w = make_world(db)  # the linked user: `.edit`, superadmin
    op_contact = seed_plain_contact(db, "ZZT Operator")
    operator = seed_user(db, contact_pk=op_contact, slugs=(EDIT_OWN,))
    for company_id in (w.srt, w.mch):
        db.add(UserCompany(user_id=operator, company_id=company_id))
    op_agent = seed_sales_agent(db, op_contact, "OP")
    with company_scope(db, None):
        op_shop = seed_customer(db, unique_code("ZZT Operator Shop"), op_agent, company_id=w.srt)
    db.commit()
    person = dealer(db, w, customers=(w.cust_a,))  # the linked user's account: not the operator's own
    with company_scope(db, None):
        db.query(RespondContact).filter(RespondContact.id == person.id).update(
            {"chatbot_allowed": False, "escalation_allowed": True, "packing_list_allowed": True}
        )
    db.commit()
    kept = _settings_of(db, person.id)
    ctx = dataclasses.replace(ctx_of(db, w), operator_user_id=operator)

    steps, skipped, _ = batch.propose_rows(
        db, ctx, GRANT, [row_(person.phone_number, role="employee", codes=[op_shop.customer_code])], seen_ids=set()
    )
    assert skipped == [] and steps, skipped
    assert KEPT in steps[0]["summary"]
    outcome = actions.confirm(db, w.respond_id, str(store(db, w, steps).id), via="console", operator_user_id=operator)

    assert outcome.status == "executed", outcome.steps
    assert state(db, person.phone_number)["links"] == sorted([str(w.cust_a.id), str(op_shop.id)])
    assert _settings_of(db, person.id) == kept


def test_D2_an_edit_own_salesperson_without_agent_access_gets_the_normal_refusal(db):
    """Owner (9 Nov ~10:45): edit_own alone does not turn the agent on. Without the panel rollout slug the panel
    stays on its old path, and with the contact's agent switch off the WhatsApp agent refuses as `switch_off`
    (the usual "not enabled" handling), no crash."""
    from app.services.chatbot import panel_service
    from app.services.chatbot.agent.access import AgentRefused, build_context

    o = own_world(db)
    w = o.w
    assert panel_service.on_the_brain(db, w.user_id) is False
    with company_scope(db, None):
        row = db.query(RespondContact).filter(RespondContact.respond_io_id == w.respond_id).one()
        row.chatbot_allowed = True
        row.chatbot_agent_enabled = False
    db.flush()
    with pytest.raises(AgentRefused) as exc:
        build_context(db, w.respond_id)
    assert exc.value.reason == "switch_off"


# ------------------------------------------------------------------ C6 crew live x3 9 Nov: every setting is guarded

SETTINGS_REFUSED = "This person also has access through another account; ask the office to change their settings."


@pytest.mark.parametrize("ai", [True, False])
def test_C6_own_scope_ai_replies_change_on_a_contact_another_account_reaches_is_refused(db, ai):
    """Crew live x3 (9 Nov, run 2 step 10): the agent proposed "AI replies off -> on" for a contact another dealer's
    account also reaches. A13 keeps such a contact's settings as they are: the update tool refuses the change."""
    o = own_world(db)
    w = o.w
    person = dealer(db, w, customers=(w.cust_a, o.theirs))
    with company_scope(db, None):
        row = db.get(RespondContact, person.id)
        row.chatbot_allowed = not ai
    db.flush()

    res, step = update_step(db, w, {"contact_id": person.id, "chatbot_allowed": ai}, seen={person.id})

    assert step is None and res.status in ("invalid", "denied")
    assert SETTINGS_REFUSED in (res.message or "")
    for hidden in (o.theirs.customer_code, o.theirs.customer_name, str(o.theirs.id)):
        assert hidden not in (res.message or "")
    assert state(db, person.phone_number)["chatbot_allowed"] is (not ai)


def test_C6_own_scope_unlinking_an_own_account_of_a_shared_contact_still_applies(db):
    """The guard is on settings, not on the salesperson's own links: they can still take their account away."""
    o = own_world(db)
    w = o.w
    person = ai_on(db, dealer(db, w, customers=(w.cust_a, o.theirs)))

    step, _ = update_and_confirm(
        db, w, {"contact_id": person.id, "unlink_customer_ids": [str(w.cust_a.id)]}, seen={person.id, w.cust_a.id}
    )

    assert "AI replies" not in step["summary"]
    after = state(db, person.phone_number)
    assert str(w.cust_a.id) not in after["links"] and after["chatbot_allowed"] is True


# ------------------------------------------------------------------ crew live x3 9 Nov: the tool contract


def test_contract_the_grant_takes_the_dealer_name_as_typed_and_refusals_come_from_the_tool():
    from app.services.chatbot.agent import batch, writes

    grant = writes.WRITES[GRANT].schema["function"]
    names = grant["parameters"]["properties"]["customer_names"]["description"]
    assert "exactly as the user typed it" in names and "never a name you searched" in names
    assert "even for a phone you think is staff" in grant["description"]
    import inspect

    import re

    # The batch description needs a db and a ctx to build: read it from the source, adjacent literals joined.
    desc = re.sub(r'"\s*\n\s*(?:f)?"', "", inspect.getsource(batch.batch_tool_schema))
    assert "Never word a refusal or a skipped reason yourself" in desc
    assert "never show a table of rows that this tool did not return" in desc


# ------------------------------------------------------------------ crew live x3 round (UAC A17, C7, F1)

NOT_TYPED = '"{name}" is not in your message; write the dealer name as you typed it.'
NO_CHANGE = (
    "Nothing was changed: I did not propose any change in this turn. Tell me again what to change and I will show it "
    "for you to confirm."
)


def _turn(db, w: W, script, text_: str):
    from tests.chatbot.agent.test_agent_writes import run_turn

    return run_turn(db, w, script, text_=text_)[0]


def _batch_call(rows, cid="b1"):
    from tests.chatbot.agent.test_agent_writes import round_of, tc

    return round_of(tc(BATCH, {"write": GRANT, "rows": rows}, cid))


def _turn_waiting(db, turn_id: str) -> list[dict]:
    from app.models.chatbot_turn import ChatbotTurn

    db.expire_all()
    return (db.get(ChatbotTurn, turn_id).response or {}).get("batch_waiting") or []


def test_A17_a_customer_name_the_user_did_not_type_is_skipped_and_nothing_is_proposed(db):
    from app.services.chatbot.agent import batch

    w = make_world(db)
    phone = fake_phone()
    said = w.cust_a.customer_name

    steps, skipped, waiting = batch.propose_rows(
        db, ctx_of(db, w), GRANT, [row_(phone, role="employee", names=[said])], seen_ids=set(),
        user_text=f"please give {phone} access for ZZT Somebody Else",
    )

    assert steps == [] and waiting == []
    assert reason(skipped) == NOT_TYPED.format(name=said)
    assert state(db, phone) is None


def test_A17_a_single_row_grant_with_a_name_the_user_did_not_type_proposes_nothing(db):
    from tests.chatbot.agent.test_agent_writes import answer_, round_of, tc

    w = make_world(db)
    phone, said = fake_phone(), w.cust_a.customer_name
    call = round_of(tc(GRANT, row_(phone, role="employee", names=[said]), "g1"))

    refused = _turn(db, w, [call, answer_("Here is the change.")], f"give {phone} access to ZZT Somebody Else")
    control = _turn(db, w, [call, answer_("Here is the change.")], f"give {phone} access to {said}")

    assert refused.pending_action is None
    assert control.pending_action is not None
    assert state(db, phone) is None


def test_A17_a_name_typed_in_another_case_and_spacing_passes_and_the_typed_text_is_kept(db):
    from app.services.chatbot.agent import batch

    w = make_world(db)
    stem = unique_code("ZZT Yoo Living", alpha=True)
    add_customer(db, w, f"{stem} A/C I")
    add_customer(db, w, f"{stem} A/C III")
    typed = "  ".join(stem.lower().split())

    steps, skipped, waiting = batch.propose_rows(
        db, ctx_of(db, w), GRANT, [row_(fake_phone(), role="employee", names=[stem])], seen_ids=set(),
        user_text=f"add them for {typed} please",
    )

    assert skipped == [] and steps == []
    assert [x["written"] for x in waiting] == [" ".join(typed.split())]  # the user's casing, spaces collapsed


def test_A17_an_all_follow_up_re_sending_the_verified_name_passes_and_keeps_the_typed_text(db):
    from tests.chatbot.agent.test_agent_writes import answer_

    w = make_world(db)
    stem = unique_code("ZZT Kbox Shop", alpha=True)
    add_customer(db, w, f"{stem} A/C I")
    add_customer(db, w, f"{stem} A/C II")
    typed = stem.lower()
    phone = fake_phone()

    first = _turn(db, w, [_batch_call([row_(phone, role="employee", names=[stem])]), answer_("Which account?")],
                  f"grant {phone} employee at {typed}")
    second = _turn(db, w, [_batch_call([row_(phone, role="employee", names=[stem])], "b2"), answer_("Which account?")],
                   "all")

    assert [x["written"] for x in _turn_waiting(db, first.turn_id)] == [typed]
    assert NOT_TYPED.format(name=stem) not in second.reply_text
    assert [x["written"] for x in _turn_waiting(db, second.turn_id)] == [typed]


@pytest.mark.parametrize(
    "text",
    [
        "I have completed all your requested operations.",
        "Access has been granted to the three people.",
        "Stock replies have been turned off for him.",
        "I've updated the contact.",
        "All requested changes have been done.",
        "Your changes are completed!",
        "The link has been removed.",
    ],
)
def test_F1_a_reply_claiming_a_change_is_detected(text):
    from app.services.chatbot.agent import loop

    assert loop.claims_change(text) is True
    assert loop.no_false_completion(text, proposed=False, decided=False) == NO_CHANGE
    assert loop.no_false_completion(text, proposed=True, decided=False) == text
    assert loop.no_false_completion(text, proposed=False, decided=True) == text


@pytest.mark.parametrize(
    "text",
    [
        "Which account do you mean for row 2?",
        "Here is what I will change; reply yes to go ahead.",
        "Nothing was changed.",
        "I could not find that phone. Is it the right number?",
        "Stock replies are set by the office; ask the office.",
        "The contact has access through two accounts.",
        "Done.",  # a read turn's own closing word (test_agent_round6), not a claim
        "the ETA has been updated",
        "the order has been changed",
    ],
)
def test_F1_a_reply_that_claims_nothing_is_left_as_it_is(text):
    from app.services.chatbot.agent import loop

    assert loop.claims_change(text) is False
    assert loop.no_false_completion(text, proposed=False, decided=False) == text


def test_F1_a_turn_claiming_completion_without_any_proposal_gets_the_fixed_reply(db):
    from tests.chatbot.agent.test_agent_writes import answer_

    w = make_world(db)

    result = _turn(db, w, [answer_("I have completed all your requested operations.")], "stock replies off for him")

    assert result.pending_action is None
    assert result.reply_text == NO_CHANGE


def _setting_args(person, **extra):
    return {"contact_id": person.id, **extra}


SETTINGS = [
    ({"chatbot_stock_allowed": False}, "Stock replies"),
    ({"escalation_allowed": True}, "Hand-over"),
    ({"packing_list_allowed": True}, "Packing list"),
    ({"notify_salesman": True}, "Notify salesman"),
    ({"other_setting": "brands"}, '"brands"'),
]


@pytest.mark.parametrize("args,what", SETTINGS, ids=[w for _, w in SETTINGS])
def test_C7_an_own_scope_settings_change_is_refused_as_set_by_the_office(db, args, what):
    w = own_world(db).w
    person = dealer(db, w, customers=(w.cust_a,))
    before = state(db, person.phone_number)

    res, step = update_step(db, w, _setting_args(person, **args), seen={person.id})

    assert step is None and res.status == "invalid"
    assert res.message == f"{what} is set by the office; ask the office."
    assert state(db, person.phone_number) == before


@pytest.mark.parametrize("args,what", SETTINGS, ids=[w for _, w in SETTINGS])
def test_C7_an_edit_holders_settings_change_points_to_the_access_tab(db, args, what):
    w = make_world(db)
    person = dealer(db, w, customers=(w.cust_a,))

    res, step = update_step(db, w, _setting_args(person, **args), seen={person.id})

    assert step is None and res.status == "invalid"
    assert res.message == f"{what} is changed on the contact's Access tab, not here."


def test_C7_a_settings_change_combined_with_a_role_change_is_refused_whole(db):
    w = own_world(db).w
    person = dealer(db, w, customers=(w.cust_a,))
    before = state(db, person.phone_number)

    res, step = update_step(db, w, _setting_args(person, role="owner", escalation_allowed=True), seen={person.id})

    assert step is None and res.status == "invalid"
    assert res.message == "Hand-over is set by the office; ask the office."
    assert state(db, person.phone_number) == before and tags_of(db, person.id) == []
