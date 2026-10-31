"""QUOTE-DRAWING-ESCALATE rework red tests: the service and its hand-off notices.

Reworked for the owner's 30 Oct hand-test note (PLAN-quote-drawing-escalate-29oct.md, section
"Rework"). The earlier contract read a `form_sla_configs` step an admin had to configure. That
is gone: escalation reuses the WhatsApp bot's general-enquiries route, for TWO kinds of task,
`product_drawing` and `product_photo`.

The route under test
--------------------
- agent: the access agent coded `general_enquiries`;
- team set: `chatbot_domains` row `product_attachment`, column `escalation_team_code`;
- assignee: the tier-1 team of that team set in the PRODUCT'S company, then
  `AccessAgentService.get_next_assignee(agent_id, team_id, brand_code=<product brand>)`;
- policy: the `AgentTeam.policy_id` binding (`resolve_policy_id_for`);
- brand: `product_origin(db, [product_id])["brand"]` (`product_origin_service`, the core half of the
  bot's `focus_product_origin`), kept on the tracker (`brand_code`) and passed again when the overdue
  scan escalates a tier.
No `form_sla_configs` row exists in any test here, and one is never needed.

Service contract these tests pin (new in the rework)
-----------------------------------------------------
- `escalate(db, *, version_id, line_id, user, kind)` with kind "drawing" | "photo" (required);
- `escalation_states(db, product_ids, kind="drawing")`;
- `respond` / `resolve` unchanged in shape: the tracker's own source type decides the kind;
- `notify_drawing_linked(db, product_id)` (H3) and the new `notify_photo_linked(db, product_id)`.
- refusals: 409 `product_has_drawing` / `product_has_photo`, 409 `marketing_team_not_set_up`.

Postgres only, via ``blank_session``. Every row is seeded here (CI's database is empty) and every
name is a masked code. Nothing here ever sends (the enqueue and the WhatsApp sender are patched).
"""
from __future__ import annotations

import inspect
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team, TeamMember, team_member_brands
from app.models.chatbot_policy import ChatbotDomain
from app.models.notification import Notification, NotificationDelivery
from app.models.sla import (
    ConversationSLAEventLog,
    ConversationSLATracking,
    FormSLAConfig,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import User
from app.services.error_handler import AppException

from ._pg_fixture import blank_session, unique_code
from .test_project_quotation_images import _priced_line, _product, _setup, _user
from .test_quotation_lines_grid import _drawing, _file, _photo, _scope

SOURCE = "product_drawing"  # the drawing kind's tracker type (kept: other suites import it)
SOURCES = {"drawing": "product_drawing", "photo": "product_photo"}
KINDS = ["drawing", "photo"]
DRAWINGS = "Technical Specifications"
PHOTOS = "Product Photos"
FORM_SLA_NOTE_SOURCE = "form_sla_tracking"
AGENT_CODE = "general_enquiries"
DOMAIN_NAME = "product_attachment"
NOT_SET_UP = "The marketing product team is not set up for this company"


def _uid() -> str:
    return str(uuid.uuid4())


def _legacy_line_without_product(db, scope):
    """A line with neither product nor set, written straight to the table.

    QUOTE-NO-FREE-TEXT (#2020) refuses such a line on every service write path, so it can no
    longer be built through `upsert_line`. The column stays nullable with no DB constraint
    (#2020 shipped no migration) and `products.id` cascades SET NULL, so a legacy or
    raw-written row can still reach `escalate`, and its `line_has_no_product` guard still
    protects it.
    """
    from app.models.projects import ProjectQuotationLine
    from app.services import project_quotation_service as quotes

    version = quotes.current_version(db, scope.id)
    line = ProjectQuotationLine(
        version_id=version.id,
        description_snapshot="zzt typed description",
        unit_price=250,
        quantity=4,
        line_total=1000,
    )
    db.add(line)
    db.flush()
    return line


def _svc():
    """Imported lazily so a missing module fails each test with ImportError, not collection."""
    from app.services import product_drawing_request_service as pdr

    return pdr


# ---------------------------------------------------------------------------------- fixtures


@pytest.fixture
def sent(monkeypatch):
    """Nothing leaves the process. Delivery rows are created by the notification service and
    drained by a worker; the enqueue and the Respond sender are the only exits, and a call to
    either is recorded (enqueue) or fails the test (a real WhatsApp send)."""
    import app.services.queue_service as queue_service
    import app.services.respond_messaging_service as respond_messaging

    enqueued: list = []
    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: enqueued.append((a, k)))

    def _no_real_send(*args, **kwargs):  # pragma: no cover - only reached by a defect
        raise AssertionError("a test reached a real WhatsApp send")

    monkeypatch.setattr(respond_messaging, "send_text_or_template", _no_real_send)
    return enqueued


@pytest.fixture
def db(sent):
    with blank_session() as session:
        yield session


@pytest.fixture
def env(db):
    """The quotation chain (project, owner, category, uom) every line test hangs off."""
    return _setup(db)


def _policy(db, *, tiers: int) -> str:
    policy_id = _uid()
    db.add(SLAPolicy(id=policy_id, code=unique_code("POL"), name="ZZT media policy"))
    for level in range(1, tiers + 1):
        db.add(
            SLAPolicyTier(
                id=_uid(),
                policy_id=policy_id,
                tier_level=level,
                tier_name=f"Tier {level}",
                response_hours=4,
                resolution_hours=24,
            )
        )
    db.flush()
    return policy_id


def add_team_set(
    db,
    *,
    agent_id: str,
    company_id: str,
    policy_id: str | None,
    tiers: int = 1,
    members_per_tier: int = 1,
    email_on_assignment: bool = True,
    whatsapp_on_assignment: bool = False,
    link_whatsapp: bool = False,
    email_on_escalation: bool = True,
    whatsapp_on_escalation: bool = False,
) -> dict:
    """One team set of the agent: a team per tier (bound to ``policy_id``), ``members_per_tier``
    ACTIVE members each. The code is random on purpose: a hard-coded team in the service would
    not find it."""
    team_set_code = unique_code("teamset")
    members: dict[int, str] = {}
    pool: dict[int, list[str]] = {}
    team_ids: dict[int, str] = {}
    for level in range(1, tiers + 1):
        team_id = _uid()
        db.add(Team(id=team_id, name=unique_code(f"Team{level}"), company_id=company_id))
        db.add(
            AgentTeam(
                id=_uid(),
                agent_id=agent_id,
                code=team_set_code,
                team_id=team_id,
                tier=level,
                company_id=company_id,
                policy_id=policy_id,
            )
        )
        db.flush()
        team_ids[level] = team_id
        pool[level] = []
        for index in range(members_per_tier):
            contact_id = None
            if link_whatsapp:
                contact_id = _uid()
                db.add(
                    RespondContact(
                        id=contact_id,
                        phone_number=f"+6011{uuid.uuid4().int % 10**8:08d}",
                        name=f"ZZT WhatsApp T{level}",
                        respond_io_id=f"zzt-rio-{uuid.uuid4().hex[:8]}",
                        session_vars={},
                    )
                )
                db.flush()
            member_id = _uid()
            db.add(
                User(
                    id=member_id,
                    email=f"{member_id}@t.zzt",
                    name=f"ZZT Marketing Member T{level}-{index}",
                    status="ACTIVE",
                    respond_contact_id=contact_id,
                    notify_email_on_assignment=email_on_assignment,
                    notify_whatsapp_on_assignment=whatsapp_on_assignment,
                    notify_email_on_escalation=email_on_escalation,
                    notify_whatsapp_on_escalation=whatsapp_on_escalation,
                )
            )
            db.flush()
            db.add(TeamMember(id=_uid(), team_id=team_id, user_id=member_id))
            pool[level].append(member_id)
        db.flush()
        members[level] = pool[level][0]
    return {"team_set_code": team_set_code, "members": members, "pool": pool, "team_ids": team_ids}


def seed_drawing_team(
    db,
    *,
    tiers: int = 1,
    members_per_tier: int = 1,
    email_on_assignment: bool = True,
    whatsapp_on_assignment: bool = False,
    link_whatsapp: bool = False,
    email_on_escalation: bool = True,
    whatsapp_on_escalation: bool = False,
    company_id: str | None = None,
    agent: bool = True,
    domain: bool = True,
    policy: bool = True,
) -> dict:
    """The general-enquiries marketing product route, shaped the way production holds it.

    - the access agent coded ``general_enquiries`` (``agent=False`` codes it otherwise);
    - a team set (``tiers`` tiers, ``members_per_tier`` members each) bound to an SLA policy with a
      tier row per level (``policy=False`` leaves the binding empty);
    - the ``chatbot_domains`` row ``product_attachment`` naming that team set in
      ``escalation_team_code`` (``domain=False`` seeds no row).

    There is NO ``form_sla_configs`` row. The name stays `seed_drawing_team` because the route
    suites import it.
    """
    company_id = company_id or db.execute(text("select id from companies where code = 'SRT'")).scalar()
    policy_id = _policy(db, tiers=tiers)
    agent_id = _uid()
    agent_code = AGENT_CODE if agent else unique_code("not-general")
    db.add(AccessAgent(id=agent_id, code=agent_code, name="ZZT General Enquiries"))
    db.flush()
    team = add_team_set(
        db,
        agent_id=agent_id,
        company_id=company_id,
        policy_id=policy_id if policy else None,
        tiers=tiers,
        members_per_tier=members_per_tier,
        email_on_assignment=email_on_assignment,
        whatsapp_on_assignment=whatsapp_on_assignment,
        link_whatsapp=link_whatsapp,
        email_on_escalation=email_on_escalation,
        whatsapp_on_escalation=whatsapp_on_escalation,
    )
    domain_id = None
    if domain:
        domain_id = _uid()
        db.add(
            ChatbotDomain(
                id=domain_id,
                name=DOMAIN_NAME,
                label="ZZT Product attachment",
                escalation_team_code=team["team_set_code"],
            )
        )
    db.commit()
    return {
        "policy_id": policy_id,
        "agent_id": agent_id,
        "agent_code": agent_code,
        "company_id": company_id,
        "domain_id": domain_id,
        "assignee": team["members"][1],
        **team,
    }


def tag_member(db, seed: dict, user_id: str, *brands: str, level: int = 1) -> None:
    """Tag a team member with brands (the routing axis `next-assignee` narrows by)."""
    member_id = (
        db.query(TeamMember.id)
        .filter(TeamMember.team_id == seed["team_ids"][level], TeamMember.user_id == user_id)
        .scalar()
    )
    for code in brands:
        db.execute(team_member_brands.insert().values(team_member_id=member_id, brand_code=code))
    db.flush()


def actor(user_id: str) -> dict:
    """The dict a route hands the service (`get_current_user`)."""
    return {"id": user_id, "email": f"{user_id}@zzt.test", "name": "Tester"}


def brand_row(db, env, code: str):
    """The product brand ``code`` (upper-case, as production holds it) in the quotation company."""
    from app.models.product import Brand

    found = db.query(Brand).filter(Brand.brand_code == code.upper()).first()
    if found is not None:
        return found
    row = Brand(id=_uid(), brand_code=code.upper(), brand_name=f"ZZT {code}", company_id=env["company_id"])
    db.add(row)
    db.flush()
    return row


def quoted_product(db, env, *, brand: str | None = None):
    """A product on a saved quotation line. Returns (product, version, line). ``brand`` tags the
    product with that brand row; None leaves it brand-less (the Sorento-company default: no brand)."""
    from app.services import project_quotation_service as quotes

    product = _product(db, env)
    if brand:
        product.brand_id = brand_row(db, env, brand).id
        db.flush()
    _document, scope = _scope(db, env)
    line = _priced_line(db, env, scope, product)
    version = quotes.current_version(db, scope.id)
    db.commit()
    return product, version, line


def esc(db, version, line, user_id, kind: str = "drawing") -> dict:
    """One click of Escalate on a line, through the service."""
    return _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(user_id), kind=kind)


def trackers_for(db, product_id, kind: str = "drawing") -> list:
    return (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.source_entity_type == SOURCES[kind],
            ConversationSLATracking.source_entity_id == str(product_id),
        )
        .all()
    )


def requester_rows(db, tracker_id) -> list:
    return (
        db.query(ConversationSLAEventLog)
        .filter(
            ConversationSLAEventLog.sla_tracking_id == str(tracker_id),
            ConversationSLAEventLog.event_type == "requester",
        )
        .all()
    )


def notes_for(db, user_id) -> list:
    return (
        db.query(Notification)
        .filter(Notification.user_id == str(user_id))
        .order_by(Notification.created_at.asc(), Notification.id.asc())
        .all()
    )


def channels(db, note) -> set:
    return {
        d.channel
        for d in db.query(NotificationDelivery).filter(NotificationDelivery.notification_id == note.id)
    }


def naive_utc(value):
    """A response datetime (aware or ISO string or naive) as naive UTC, to compare with columns."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


@contextmanager
def captured_sql(db):
    """Every SQL statement the session's connection runs inside the block, in order."""
    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    connection = db.get_bind()
    event.listen(connection, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(connection, "before_cursor_execute", _record)


# ---------------------------------------------------------------------------- AC-1 has_drawing


def test_an_image_typed_technical_specifications_is_a_drawing(db, env):
    product = _product(db, env)
    _drawing(db, env, product, "d.jpg")
    assert _svc().has_drawing(db, product.id) is True


def test_a_pdf_typed_technical_specifications_is_a_drawing(db, env):
    product = _product(db, env)
    _drawing(db, env, product, "d.pdf", mime="application/pdf")
    assert _svc().has_drawing(db, product.id) is True


def test_a_deleted_drawing_is_not_a_drawing(db, env):
    product = _product(db, env)
    _drawing(db, env, product, "gone.jpg", deleted=True)
    _drawing(db, env, product, "gone.pdf", mime="application/pdf", deleted=True)
    assert _svc().has_drawing(db, product.id) is False


def test_a_file_of_another_type_is_not_a_drawing_even_as_a_pdf_or_image(db, env):
    product = _product(db, env)
    _photo(db, env, product, "photo.jpg")
    _photo(db, env, product, "brochure.pdf", mime="application/pdf")
    assert _svc().has_drawing(db, product.id) is False


def test_a_drawing_of_another_product_is_not_this_products_drawing(db, env):
    mine, other = _product(db, env), _product(db, env)
    _drawing(db, env, other, "theirs.jpg")
    assert _svc().has_drawing(db, mine.id) is False
    assert _svc().has_drawing(db, other.id) is True


def test_a_non_image_non_pdf_drawing_file_is_not_a_drawing(db, env):
    product = _product(db, env)
    _drawing(db, env, product, "sheet.xlsx", mime="application/vnd.ms-excel")
    assert _svc().has_drawing(db, product.id) is False


# --------------------------------------------------------------------- AC-3 one task per product


def test_a_set_line_escalates_its_driver_part_not_the_set(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    driver = _product(db, env)
    other_part = _product(db, env)
    _document, scope = _scope(db, env)
    version = quotes.current_version(db, scope.id)
    from app.models.projects import ProjectQuotationLine

    line = _priced_line(db, env, scope, driver)
    # Re-shape the saved line into a SET line: no own product, the parts frozen on it.
    line.product_id = None
    line.set_parts_snapshot = [
        {"product_id": str(other_part.id), "product_code": other_part.product_code, "quantity": "1", "is_driver": False},
        {"product_id": str(driver.id), "product_code": driver.product_code, "quantity": "1", "is_driver": True},
    ]
    db.flush()
    assert isinstance(line, ProjectQuotationLine)
    db.commit()
    caller = _user(db, "zzt Sales One")

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")

    assert len(trackers_for(db, driver.id)) == 1
    assert trackers_for(db, other_part.id) == []


# ---------------------------------------------------------------------------- AC-4 join, not dup


def test_a_second_quotation_of_the_same_product_joins_the_same_requesters_own_task(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    product, version_a, line_a = quoted_product(db, env)
    _document, scope_b = _scope(db, env)
    line_b = _priced_line(db, env, scope_b, product)
    version_b = quotes.current_version(db, scope_b.id)
    db.commit()
    first = _user(db, "zzt Sales One")

    _svc().escalate(db, version_id=version_a.id, line_id=line_a.id, user=actor(first), kind="drawing")
    out = _svc().escalate(db, version_id=version_b.id, line_id=line_b.id, user=actor(first), kind="drawing")

    assert len(trackers_for(db, product.id)) == 1
    assert out["joined"] is True
    reasons = {r.reason for r in requester_rows(db, trackers_for(db, product.id)[0].id)}
    assert reasons == {f"quotation_version:{version_a.id}", f"quotation_version:{version_b.id}"}


def test_escalate_holds_an_advisory_lock_on_the_product_from_before_the_task_to_after_the_requester(db, env):
    """Two clicks in the same second must open one task. "Is there an open task" is read then
    write, and the assignee draw commits in between, so a row lock would be gone by the INSERT.
    The lock is a SESSION-level advisory lock keyed on the product: taken before the tracker is
    written, released only after the requester row is written."""
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")

    with captured_sql(db) as statements:
        _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")

    lowered = [s.lower() for s in statements]

    def first(pred):
        return next((i for i, s in enumerate(lowered) if pred(s)), None)

    lock_at = first(lambda s: "pg_advisory_lock" in s)
    insert_at = first(lambda s: s.lstrip().startswith("insert into") and "conversation_sla_tracking (" in s)
    requester_at = first(lambda s: s.lstrip().startswith("insert into") and "conversation_sla_event_log" in s)
    unlock_at = first(lambda s: "pg_advisory_unlock" in s)
    assert None not in (lock_at, insert_at, requester_at, unlock_at), lowered
    assert lock_at < insert_at, "the lock must be taken before the tracker is written"
    assert requester_at < unlock_at, "the lock must outlive the requester write"
    assert not any("for update" in s and "from products" in s for s in lowered), "no raw SQL on products"


def _advisory_locks_held(db) -> int:
    return db.execute(
        text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()")
    ).scalar()


def test_a_hung_holder_cannot_block_an_escalation_forever_it_answers_busy_and_leaks_nothing(
    db, env, monkeypatch
):
    import time

    from app.database import engine as base_engine

    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")
    db.commit()  # the busy answer rolls the session back, so the seeds must be committed
    monkeypatch.setattr(_svc(), "LOCK_TIMEOUT_SECONDS", 1)
    key = {"k": f"product_drawing:{product.id}:{caller}"}
    holder = base_engine.connect()
    holder.execute(text("SELECT pg_advisory_lock(hashtext(:k))"), key)
    try:
        started = time.monotonic()
        with pytest.raises(AppException) as busy:
            _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")
        waited = time.monotonic() - started
    finally:
        holder.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), key)
        holder.close()

    assert busy.value.status_code == 409 and busy.value.code == "drawing_request_busy"
    assert busy.value.message == "Someone else is escalating this product, try again."
    assert waited < 8, waited
    assert trackers_for(db, product.id) == []
    assert _advisory_locks_held(db) == 0, "the failed wait leaked a lock"

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")
    assert len(trackers_for(db, product.id)) == 1
    assert _advisory_locks_held(db) == 0


def test_the_advisory_lock_is_released_when_the_escalation_is_refused(db, env):
    seed_drawing_team(db, domain=False)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")

    with captured_sql(db) as statements:
        with pytest.raises(AppException):
            _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")

    lowered = [s.lower() for s in statements]
    locks = sum("pg_advisory_lock" in s for s in lowered)
    unlocks = sum("pg_advisory_unlock" in s for s in lowered)
    assert locks == unlocks, (locks, unlocks)


@contextmanager
def _private_schema_engine():
    """A scratch schema of its own, so a test that REALLY commits cannot leave rows in the shared
    one (committed seeds would collide with every later test's seeds). The shared schema is set
    aside and put back, and the private one is dropped on the way out."""
    from . import _pg_fixture as pg

    saved = dict(pg._BLANK)
    pg._BLANK.clear()
    try:
        scoped = pg.blank_schema_engine()
        yield scoped, pg._BLANK["name"]
    finally:
        pg.drop_blank_schema()
        pg._BLANK.clear()
        pg._BLANK.update(saved)


def test_two_simultaneous_escalates_of_one_product_by_one_requester_open_one_task(sent, monkeypatch):
    """The real race: two sessions on two connections with real commits, the assignee draw slowed
    so both reach the open-task check together. Runs in a private scratch schema (see
    `_private_schema_engine`) because the commits are real."""
    import threading
    import time

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.database import engine as base_engine
    from app.models.base import company_scope
    from app.services import coverage_subscription_service as coverage

    with _private_schema_engine() as (scoped, name):
        path = ",".join(
            (name,)
            + tuple(f"{name}_{x}" for x in ("scm", "dealer_kit", "chatbot", "sales", "finance", "projects"))
            + ("public",)
        )
        own = create_engine(
            base_engine.url, connect_args={"options": f"-c search_path={path}"}, pool_size=6
        ).execution_options(schema_translate_map=scoped.get_execution_options()["schema_translate_map"])
        real = coverage.resolve_assignee_with_coverage

        def slow(*args, **kwargs):
            time.sleep(0.5)
            return real(*args, **kwargs)

        monkeypatch.setattr(coverage, "resolve_assignee_with_coverage", slow)
        seeder = Session(bind=own)
        try:
            env = _setup(seeder)
            seeder.commit()
            seed_drawing_team(seeder)
            product, version, line = quoted_product(seeder, env)
            first_user = _user(seeder, "zzt Sales One")
            second_user = first_user  # the lock key carries the requester: one person, two clicks
            seeder.commit()
            product_id, version_id, line_id = product.id, version.id, line.id
            company_id = env["company_id"]
            errors: list = []

            def click(user_id):
                session = Session(bind=own)
                try:
                    with company_scope(session, frozenset({company_id})):
                        _svc().escalate(session, version_id=version_id, line_id=line_id, user=actor(user_id), kind="drawing")
                except Exception as exc:  # pragma: no cover - reported below
                    errors.append(exc)
                finally:
                    session.close()

            threads = [threading.Thread(target=click, args=(u,)) for u in (first_user, second_user)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=60)

            check = Session(bind=own)
            try:
                trackers = trackers_for(check, product_id)
                requesters = [r for t in trackers for r in requester_rows(check, t.id)]
            finally:
                check.close()
            assert errors == []
            assert len([t for t in trackers if not t.is_resolved]) == 1, [t.id for t in trackers]
            assert {r.triggered_by_id for r in requesters} == {first_user}
            assert len(requesters) == 1
        finally:
            seeder.close()
            own.dispose()


# ------------------------------------------------------------------------------ AC-9 refusals


def test_a_product_that_has_a_drawing_is_refused_and_nothing_is_created(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _drawing(db, env, product, "d.jpg")
    db.commit()
    caller = _user(db, "zzt Sales One")

    with pytest.raises(AppException) as refused:
        _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")

    assert refused.value.status_code == 409
    assert refused.value.code == "product_has_drawing"
    assert trackers_for(db, product.id) == []


def test_a_pdf_drawing_also_refuses_the_escalation(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _drawing(db, env, product, "d.pdf", mime="application/pdf")
    db.commit()
    caller = _user(db, "zzt Sales One")

    with pytest.raises(AppException) as refused:
        _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")

    assert refused.value.status_code == 409
    assert refused.value.code == "product_has_drawing"
    assert trackers_for(db, product.id) == []


def test_an_off_catalogue_line_is_refused_and_nothing_is_created(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    _document, scope = _scope(db, env)
    line = _legacy_line_without_product(db, scope)
    version = quotes.current_version(db, scope.id)
    db.commit()
    caller = _user(db, "zzt Sales One")

    with pytest.raises(AppException) as refused:
        _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")

    assert (refused.value.status_code, refused.value.code) == (409, "line_has_no_product")
    assert (
        db.query(ConversationSLATracking)
        .filter(ConversationSLATracking.source_entity_type == SOURCE)
        .count()
        == 0
    )


def test_a_line_that_belongs_to_another_version_is_a_404(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _document, other_scope = _scope(db, env)
    other_version = quotes.current_version(db, other_scope.id)
    db.commit()
    caller = _user(db, "zzt Sales One")

    with pytest.raises(AppException) as refused:
        _svc().escalate(db, version_id=other_version.id, line_id=line.id, user=actor(caller), kind="drawing")

    assert refused.value.status_code == 404
    assert trackers_for(db, product.id) == []


@pytest.mark.parametrize("which", ["version", "line", "both"])
def test_an_unknown_version_or_line_is_a_404(db, env, which):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")
    version_id = _uid() if which in ("version", "both") else version.id
    line_id = _uid() if which in ("line", "both") else line.id

    with pytest.raises(AppException) as refused:
        _svc().escalate(db, version_id=version_id, line_id=line_id, user=actor(caller), kind="drawing")

    assert refused.value.status_code == 404
    assert trackers_for(db, product.id) == []


# ------------------------------------------------------------------- escalation_states (the cell)


def test_states_are_keyed_by_every_product_asked_for(db, env):
    seed_drawing_team(db)
    open_product, version, line = quoted_product(db, env)
    never = _product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")

    states = _svc().escalation_states(db, [open_product.id, never.id])

    assert set(states) == {str(open_product.id), str(never.id)}
    assert states[str(never.id)] is None


def test_an_open_task_state_carries_the_cell_fields(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    first = _user(db, "zzt Sales One")
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(first), kind="drawing")
    (tracker,) = trackers_for(db, product.id)

    state = _svc().escalation_states(db, [product.id])[str(product.id)]

    assert set(state) >= {
        "tracking_id", "opened_at", "responded_at", "due_at", "requester_count", "last_resolved_at",
    }
    assert str(state["tracking_id"]) == str(tracker.id)
    assert naive_utc(state["opened_at"]) == tracker.initiated_at
    assert state["responded_at"] is None
    assert naive_utc(state["due_at"]) == tracker.due_at, "before a response the response clock governs"
    assert state["requester_count"] == 1
    assert state["last_resolved_at"] is None


def test_after_a_response_the_resolution_clock_governs_the_due_date(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")
    (tracker,) = trackers_for(db, product.id)

    _svc().respond(db, tracker.id, actor(seed["assignee"]))
    db.refresh(tracker)
    state = _svc().escalation_states(db, [product.id])[str(product.id)]

    assert state["responded_at"] is not None
    assert naive_utc(state["due_at"]) == tracker.due_at_resolution


def test_a_resolved_task_leaves_only_when_it_was_last_resolved(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")
    (tracker,) = trackers_for(db, product.id)
    _svc().resolve(db, tracker.id, actor(seed["assignee"]))
    db.refresh(tracker)

    state = _svc().escalation_states(db, [product.id])[str(product.id)]

    assert state is not None
    assert state["tracking_id"] is None
    assert state["opened_at"] is None and state["responded_at"] is None and state["due_at"] is None
    assert state["requester_count"] in (None, 0)
    assert naive_utc(state["last_resolved_at"]) == tracker.resolved_at


def test_states_cost_the_same_number_of_queries_for_one_product_or_many(db, env):
    seed_drawing_team(db)
    products = []
    for _ in range(5):
        product, version, line = quoted_product(db, env)
        _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")
        products.append(product.id)
    _svc().escalation_states(db, products)  # warm any one-off lookup

    with captured_sql(db) as one:
        _svc().escalation_states(db, products[:1])
    with captured_sql(db) as many:
        _svc().escalation_states(db, products)

    assert len(many) == len(one), (len(one), len(many))


# ------------------------------------------------------------- AC-6 the normal SLA flow, respond/resolve


@pytest.mark.parametrize("action", ["respond", "resolve"])
def test_a_tracker_of_another_type_is_a_409(db, env, action):
    seed = seed_drawing_team(db)
    complaint_task = ConversationSLATracking(
        id=_uid(),
        policy_id=seed["policy_id"],
        current_tier=1,
        initiated_at=datetime.utcnow(),
        current_tier_started_at=datetime.utcnow(),
        due_at=datetime.utcnow() + timedelta(hours=4),
        due_at_resolution=datetime.utcnow() + timedelta(hours=24),
        is_resolved=False,
        source_entity_type="complaint",
        source_entity_id=_uid(),
        agent_id=seed["agent_id"],
        assigned_to_id=seed["assignee"],
    )
    db.add(complaint_task)
    db.commit()

    with pytest.raises(AppException) as refused:
        getattr(_svc(), action)(db, complaint_task.id, actor(seed["assignee"]))

    assert refused.value.status_code == 409
    db.refresh(complaint_task)
    assert complaint_task.is_resolved is False


@pytest.mark.parametrize("action", ["respond", "resolve"])
def test_an_unknown_tracker_is_a_404(db, env, action):
    seed = seed_drawing_team(db)
    with pytest.raises(AppException) as refused:
        getattr(_svc(), action)(db, _uid(), actor(seed["assignee"]))
    assert refused.value.status_code == 404


def test_the_task_is_on_my_pending_as_a_form_row_with_the_product_code_as_its_reference(db, env):
    from app.services.sla_service import ConversationSLATrackingService

    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")
    (tracker,) = trackers_for(db, product.id)

    rows = ConversationSLATrackingService(db).list_my_pending(seed["assignee"])

    row = next(r for r in rows if r["id"] == str(tracker.id))
    assert row["source_entity_type"] == SOURCE
    assert row["source_entity_id"] == str(product.id)
    assert row["is_form_sla"] is True
    assert row["reference"] == product.product_code
    assert row["current_tier"] == 1


# --------------------------------------------------------------------- AC-12 H1: opening the task


def _assigned_note(db, seed, tracker):
    notes = [
        n
        for n in notes_for(db, seed["assignee"])
        if n.source_entity_type == FORM_SLA_NOTE_SOURCE and str(n.source_entity_id) == str(tracker.id)
    ]
    assert len(notes) == 1, [n.title for n in notes]
    return notes[0]


def test_h1_toggles_off_leave_only_the_in_app_notice(db, env):
    seed = seed_drawing_team(
        db, email_on_assignment=False, whatsapp_on_assignment=False, link_whatsapp=True
    )
    product, version, line = quoted_product(db, env)

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")

    (tracker,) = trackers_for(db, product.id)
    assert channels(db, _assigned_note(db, seed, tracker)) == {"in_app"}


def test_h1_whatsapp_needs_a_linked_contact_even_with_the_toggle_on(db, env):
    seed = seed_drawing_team(db, whatsapp_on_assignment=True, link_whatsapp=False)
    product, version, line = quoted_product(db, env)

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")

    (tracker,) = trackers_for(db, product.id)
    assert channels(db, _assigned_note(db, seed, tracker)) == {"in_app", "email"}


def test_a_join_does_not_notify_the_assignee_again(db, env):
    seed = seed_drawing_team(db, whatsapp_on_assignment=True, link_whatsapp=True)
    product, version, line = quoted_product(db, env)

    caller = _user(db, "zzt Sales One")
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")

    (tracker,) = trackers_for(db, product.id)
    _assigned_note(db, seed, tracker)  # exactly one


# ------------------------------------------------------------- AC-12 H2: the overdue scan escalates


def test_h2_escalation_toggles_off_leave_only_in_app(db, env):
    from app.services.form_sla_service import FormSLAOrchestrator

    seed = seed_drawing_team(
        db, tiers=2, email_on_escalation=False, whatsapp_on_escalation=False, link_whatsapp=True
    )
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")
    (tracker,) = trackers_for(db, product.id)
    tracker.due_at = datetime.utcnow() - timedelta(hours=1)
    db.commit()

    FormSLAOrchestrator(db).scan_overdue_and_escalate()

    notes = [
        n
        for n in notes_for(db, seed["members"][2])
        if n.source_entity_type == FORM_SLA_NOTE_SOURCE and n.event_type == "escalated"
    ]
    assert len(notes) == 1
    assert channels(db, notes[0]) == {"in_app"}


# -------------------------------------------------------- AC-7 / AC-12 H3: a drawing linked while open


def _link_through_the_product_service(db, product, attachment):
    from app.schemas.product import ProductAttachmentCreate
    from app.services.product_service import ProductAttachmentService

    return ProductAttachmentService(db).create_product_attachment(
        ProductAttachmentCreate(product_id=str(product.id), attachment_id=str(attachment.id))
    )


def _drawing_added_notes(db, user_id) -> list:
    return [
        n for n in notes_for(db, user_id) if "Drawing added" in f"{n.title} {n.body or ''}"
    ]


@pytest.mark.parametrize("mime", ["image/png", "application/pdf"])
def test_h3_linking_a_drawing_while_the_task_is_open_notifies_the_assignee_and_leaves_it_open(
    db, env, mime
):
    seed = seed_drawing_team(db, whatsapp_on_assignment=True, link_whatsapp=True)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")
    (tracker,) = trackers_for(db, product.id)
    attachment = _file(db, env["company_id"], DRAWINGS, f"late.{mime.split('/')[1]}", mime=mime)

    _link_through_the_product_service(db, product, attachment)

    db.refresh(tracker)
    assert tracker.is_resolved is False and tracker.voided_at is None, "adding a drawing must not close the task"
    (note,) = _drawing_added_notes(db, seed["assignee"])
    assert product.product_code in f"{note.title} {note.body or ''}"
    assert "resolve" in (note.body or "").lower()
    assert channels(db, note) == {"in_app", "email", "whatsapp"}
    assert note.data["whatsapp_use_case"] == "sla_assignment"


def test_h3_toggles_off_leave_only_in_app(db, env):
    seed = seed_drawing_team(db, email_on_assignment=False, whatsapp_on_assignment=False, link_whatsapp=True)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")
    attachment = _file(db, env["company_id"], DRAWINGS, "late.png")

    _link_through_the_product_service(db, product, attachment)

    (note,) = _drawing_added_notes(db, seed["assignee"])
    assert channels(db, note) == {"in_app"}


def test_h3_a_file_that_is_not_a_drawing_notifies_nobody(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")
    photo = _file(db, env["company_id"], PHOTOS, "photo.jpg")
    other_type_pdf = _file(db, env["company_id"], PHOTOS, "brochure.pdf", mime="application/pdf")

    _link_through_the_product_service(db, product, photo)
    _link_through_the_product_service(db, product, other_type_pdf)

    assert _drawing_added_notes(db, seed["assignee"]) == []


def test_h3_a_drawing_with_no_open_task_notifies_nobody(db, env):
    seed = seed_drawing_team(db)
    product = _product(db, env)
    attachment = _file(db, env["company_id"], DRAWINGS, "early.png")

    _link_through_the_product_service(db, product, attachment)

    assert _drawing_added_notes(db, seed["assignee"]) == []
    assert trackers_for(db, product.id) == []


def test_notify_drawing_linked_is_a_noop_without_an_open_task_and_notifies_with_one(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)

    _svc().notify_drawing_linked(db, product.id)
    assert _drawing_added_notes(db, seed["assignee"]) == []

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")
    _svc().notify_drawing_linked(db, product.id)
    assert len(_drawing_added_notes(db, seed["assignee"])) == 1


# ----------------------------------------------------------- AC-8 / AC-12 H4: resolve tells requesters


def test_h4_resolving_tells_each_requester_once_in_app_and_email_and_never_on_whatsapp(db, env):
    """Q5: each requester has their own task now. The resolved notice keeps in-app and email
    (their own toggle) and never carries WhatsApp, even with the toggle on and a contact linked."""
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    contact = RespondContact(
        id=_uid(), phone_number="+60110000777", name="ZZT Sales WhatsApp",
        respond_io_id=f"zzt-rio-{uuid.uuid4().hex[:8]}", session_vars={},
    )
    db.add(contact)
    db.flush()
    first = _user(db, "zzt Sales One")
    second = _user(db, "zzt Sales Two")
    one = db.query(User).filter(User.id == first).one()
    one.respond_contact_id = contact.id
    one.notify_whatsapp_on_assignment = True
    one.notify_email_on_assignment = True
    two = db.query(User).filter(User.id == second).one()
    two.notify_email_on_assignment = False
    db.commit()
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(first), kind="drawing")
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(second), kind="drawing")
    assert len(trackers_for(db, product.id)) == 2

    for tracker in trackers_for(db, product.id):
        _svc().resolve(db, tracker.id, actor(seed["assignee"]))

    title = f"Product drawing request for {product.product_code} resolved"
    for requester, expected in ((first, {"in_app", "email"}), (second, {"in_app"})):
        notes = [n for n in notes_for(db, requester) if n.title == title]
        assert len(notes) == 1, (requester, [n.title for n in notes_for(db, requester)])
        assert channels(db, notes[0]) == expected
    # It names the project the requester escalated from, so the bell opens their quotation.
    one_note = [n for n in notes_for(db, first) if n.title == title][0]
    assert str(env["project"].id) in (one_note.data or {}).get("link", "")
    # The assignee closed it; they are not a requester and hear nothing about it.
    assert [n for n in notes_for(db, seed["assignee"]) if n.title == title] == []


def test_h4_a_second_resolve_does_not_tell_the_requesters_again(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")
    (tracker,) = trackers_for(db, product.id)

    _svc().resolve(db, tracker.id, actor(seed["assignee"]))
    try:
        _svc().resolve(db, tracker.id, actor(seed["assignee"]))
    except AppException:
        pass  # refusing the repeat is as good as ignoring it

    title = f"Product drawing request for {product.product_code} resolved"
    assert len([n for n in notes_for(db, caller) if n.title == title]) == 1


def test_h4_after_resolve_without_a_drawing_a_new_escalate_opens_a_new_task(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")
    (first,) = trackers_for(db, product.id)
    _svc().resolve(db, first.id, actor(seed["assignee"]))

    out = _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")

    assert out["joined"] is False
    open_tasks = [t for t in trackers_for(db, product.id) if not t.is_resolved]
    assert len(open_tasks) == 1 and str(open_tasks[0].id) != str(first.id)
    assert out["escalation"]["requester_count"] == 1, "a new task starts its own requester list"


# ------------------------------------------------------------- the quotation line read (cell state)


def test_a_line_read_carries_the_escalation_state_and_null_when_there_is_none(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    asked, version, line = quoted_product(db, env)
    quiet_product = _product(db, env)
    _document, scope = _scope(db, env)
    quiet_line = _priced_line(db, env, scope, quiet_product)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")

    cells = {r["id"]: r["technical_drawing"] for r in quotes.serialize_lines(db, [line, quiet_line])}

    escalation = cells[line.id]["escalation"]
    assert set(escalation) >= {"opened_at", "responded_at", "due_at", "requester_count", "last_resolved_at"}
    assert escalation["requester_count"] == 1
    assert "escalation" in cells[quiet_line.id] and cells[quiet_line.id]["escalation"] is None


def test_every_line_of_every_quotation_with_the_product_shows_the_same_state(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    product, version_a, line_a = quoted_product(db, env)
    _document, scope_b = _scope(db, env)
    line_b = _priced_line(db, env, scope_b, product)
    _svc().escalate(db, version_id=version_a.id, line_id=line_a.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")

    cells = {r["id"]: r["technical_drawing"] for r in quotes.serialize_lines(db, [line_a, line_b])}

    assert cells[line_a.id]["escalation"] == cells[line_b.id]["escalation"]
    assert cells[line_b.id]["escalation"] is not None


def test_a_pdf_only_product_reads_the_pdf_state_with_its_signed_url_and_filename(db, env):
    from app.services import project_quotation_service as quotes

    product, version, line = quoted_product(db, env)
    pdf = _drawing(db, env, product, "TS-0002.pdf", mime="application/pdf")
    db.commit()

    cell = quotes.serialize_lines(db, [line])[0]["technical_drawing"]

    assert cell["state"] == "pdf"
    assert cell["url"]
    assert cell["filename"] == pdf.original_filename
    assert "escalation" in cell


def test_an_image_drawing_wins_over_a_pdf_drawing_in_the_cell(db, env):
    from app.services import project_quotation_service as quotes

    product, version, line = quoted_product(db, env)
    _drawing(db, env, product, "TS-0002.pdf", mime="application/pdf")
    image = _drawing(db, env, product, "TS-0001.png")
    db.commit()

    cell = quotes.serialize_lines(db, [line])[0]["technical_drawing"]

    assert cell["state"] == "default"
    assert cell["attachment_id"] == image.id


def test_a_pdf_is_never_stamped_on_the_line_at_issue(db, env):
    from app.services import project_quotation_image_service as quotation_images

    product, version, line = quoted_product(db, env)
    _drawing(db, env, product, "TS-0002.pdf", mime="application/pdf")
    db.commit()

    quotation_images.freeze_version_images(db, version.id)

    db.refresh(line)
    assert line.drawing_attachment_id is None, "the quotation documents embed images only"


# ------------------------------------------------------------------ fix round 1: company scope


def _second_company(db) -> str:
    from app.models.company import Company

    company_id = _uid()
    db.add(Company(id=company_id, name="ZZT Company B", code=unique_code("CB")[:20]))
    db.flush()
    return company_id


def _team_for_company(db, seed: dict, company_id: str) -> str:
    """A tier-1 team of the SAME agent and team set, owned by another company. Returns its member."""
    team_id = _uid()
    db.add(Team(id=team_id, name=unique_code("TeamB"), company_id=company_id))
    db.add(
        AgentTeam(
            id=_uid(), agent_id=seed["agent_id"], code=seed["team_set_code"],
            team_id=team_id, tier=1, company_id=company_id, policy_id=seed["policy_id"],
        )
    )
    db.flush()
    member_id = _uid()
    db.add(User(id=member_id, email=f"{member_id}@t.zzt", name="ZZT Member B", status="ACTIVE"))
    db.flush()
    db.add(TeamMember(id=_uid(), team_id=team_id, user_id=member_id))
    db.commit()
    return member_id


def test_a_product_of_another_company_is_a_404_and_opens_nothing(db, env):
    from app.models.base import company_scope
    from app.models.product import Product

    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    other = _second_company(db)
    db.query(Product).filter(Product.id == product.id).update({"company_id": other})
    db.commit()
    caller = _user(db, "zzt Sales One")

    with company_scope(db, frozenset({env["company_id"]})):
        with pytest.raises(AppException) as refused:
            _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")

    assert refused.value.status_code == 404
    assert refused.value.code == "product_not_found"
    assert trackers_for(db, product.id) == []


def test_a_product_of_company_b_routes_to_company_bs_team_and_the_task_is_company_b(db, env):
    seed = seed_drawing_team(db)
    company_b = _second_company(db)
    member_b = _team_for_company(db, seed, company_b)
    from app.models.product import Product

    product, version, line = quoted_product(db, env)
    db.query(Product).filter(Product.id == product.id).update({"company_id": company_b})
    db.commit()
    caller = _user(db, "zzt Sales One")

    from app.models.base import company_scope

    with company_scope(db, frozenset({env["company_id"], company_b})):
        _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")

    (tracker,) = trackers_for(db, product.id)
    assert str(tracker.company_id) == str(company_b)
    assert tracker.assigned_to_id == member_b, "tier 1 of company B, not company A's member"


def test_a_company_a_product_still_routes_to_company_as_team(db, env):
    seed = seed_drawing_team(db)
    _team_for_company(db, seed, _second_company(db))
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")

    (tracker,) = trackers_for(db, product.id)
    assert str(tracker.company_id) == str(env["company_id"])
    assert tracker.assigned_to_id == seed["assignee"]


# ------------------------------------------- fix round 1: respond / resolve do not need the step's events


# ------------------------------------------------------ fix round 1: a failed notice never breaks the work


def _broken_notice(db):
    """A notice call that fails the way a real DB error does: the transaction is left aborted."""
    from sqlalchemy.exc import DBAPIError

    def boom(self, *args, **kwargs):
        try:
            db.execute(text("select * from zzt_no_such_table"))
        except DBAPIError:
            raise
        raise AssertionError("unreachable")  # pragma: no cover

    return boom


def test_a_failed_resolve_notice_leaves_the_task_resolved_and_the_session_usable(db, env, monkeypatch):
    from app.services.notification_service import NotificationService

    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")
    (tracker,) = trackers_for(db, product.id)
    monkeypatch.setattr(NotificationService, "create_with_channel_preferences", _broken_notice(db))

    _svc().resolve(db, tracker.id, actor(seed["assignee"]))

    assert db.query(User).count() > 0, "the session is still usable"
    db.refresh(tracker)
    assert tracker.is_resolved is True


def test_a_failed_drawing_linked_notice_does_not_break_the_attachment_link(db, env, monkeypatch):
    from app.services.notification_service import NotificationService

    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")), kind="drawing")
    attachment = _file(db, env["company_id"], DRAWINGS, "late.png")
    monkeypatch.setattr(NotificationService, "create_with_channel_preferences", _broken_notice(db))

    link = _link_through_the_product_service(db, product, attachment)

    assert link is not None and str(link.attachment_id) == str(attachment.id)
    assert db.query(User).count() > 0


def test_h4_notifies_a_requester_once_even_if_the_notices_are_sent_twice(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller), kind="drawing")
    (tracker,) = trackers_for(db, product.id)
    _svc().resolve(db, tracker.id, actor(seed["assignee"]))

    _svc()._notify_requesters_resolved(db, tracker)

    title = f"Product drawing request for {product.product_code} resolved"
    assert len([n for n in notes_for(db, caller) if n.title == title]) == 1


# =============================================================================================
# REWORK (owner hand test 30 Oct): the general-enquiries route, two kinds, brand narrowing.
# Everything below replaces the earlier "configured step" tests.
# =============================================================================================

LABEL = {"drawing": "Product drawing", "photo": "Product photo"}


def _resolved_title(kind: str, product) -> str:
    return f"{LABEL[kind]} request for {product.product_code} resolved"


# ------------------------------------------------------------------ one task per (kind, product)


@pytest.mark.parametrize("kind", KINDS)
def test_escalate_opens_one_task_for_the_product_from_the_general_enquiries_route(db, env, kind):
    team = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")

    out = esc(db, version, line, caller, kind)

    rows = trackers_for(db, product.id, kind)
    assert len(rows) == 1
    tracker = rows[0]
    assert tracker.source_entity_type == SOURCES[kind]
    assert tracker.assigned_to_id == team["assignee"]
    assert tracker.agent_id == team["agent_id"]
    assert tracker.team_set_code == team["team_set_code"]
    assert str(tracker.policy_id) == team["policy_id"]
    assert str(tracker.company_id) == str(env["company_id"])
    assert tracker.current_tier == 1
    assert tracker.brand_code is None, "a brand-less product routes with no brand"
    assert tracker.due_at is not None and tracker.due_at_resolution is not None
    assert tracker.is_resolved is False
    assert out["joined"] is False
    assert str(out["escalation"]["tracking_id"]) == str(tracker.id)
    assert out["escalation"]["requester_count"] == 1
    other = "photo" if kind == "drawing" else "drawing"
    assert trackers_for(db, product.id, other) == [], "one kind must not open the other"


@pytest.mark.parametrize("kind", KINDS)
def test_the_requester_is_an_event_log_row_naming_the_user_and_the_quotation(db, env, kind):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")

    esc(db, version, line, caller, kind)

    (tracker,) = trackers_for(db, product.id, kind)
    (row,) = requester_rows(db, tracker.id)
    assert row.triggered_by_id == caller
    assert row.reason == f"quotation_version:{version.id}"


@pytest.mark.parametrize("kind", KINDS)
def test_a_second_user_opens_their_own_task_and_the_first_stays_theirs(db, env, kind):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    first, second = _user(db, "zzt Sales One"), _user(db, "zzt Sales Two")

    esc(db, version, line, first, kind)
    out = esc(db, version, line, second, kind)

    rows = trackers_for(db, product.id, kind)
    assert len(rows) == 2, "one task per requester"
    assert out["joined"] is False
    assert out["escalation"]["requester_count"] == 1
    assert sorted(r.triggered_by_id for t in rows for r in requester_rows(db, t.id)) == sorted([first, second])
    assert all(len(requester_rows(db, t.id)) == 1 for t in rows)


@pytest.mark.parametrize("kind", KINDS)
def test_the_same_user_twice_is_recorded_once(db, env, kind):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")

    esc(db, version, line, caller, kind)
    out = esc(db, version, line, caller, kind)

    (tracker,) = trackers_for(db, product.id, kind)
    assert len(requester_rows(db, tracker.id)) == 1
    assert out["joined"] is True
    assert out["escalation"]["requester_count"] == 1


def test_a_drawing_and_a_photo_of_one_product_are_two_tasks_each_joinable(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    one, two = _user(db, "zzt Sales One"), _user(db, "zzt Sales Two")

    first_drawing = esc(db, version, line, one, "drawing")
    first_photo = esc(db, version, line, one, "photo")

    assert first_drawing["joined"] is False and first_photo["joined"] is False
    (drawing_task,) = trackers_for(db, product.id, "drawing")
    (photo_task,) = trackers_for(db, product.id, "photo")
    assert str(drawing_task.id) != str(photo_task.id)

    joined_drawing = esc(db, version, line, one, "drawing")
    joined_photo = esc(db, version, line, one, "photo")
    assert joined_drawing["joined"] is True and joined_photo["joined"] is True
    assert joined_drawing["escalation"]["requester_count"] == 1
    assert joined_photo["escalation"]["requester_count"] == 1
    assert len(trackers_for(db, product.id, "drawing")) == 1
    assert len(trackers_for(db, product.id, "photo")) == 1
    assert str(joined_drawing["escalation"]["tracking_id"]) == str(drawing_task.id)
    assert str(joined_photo["escalation"]["tracking_id"]) == str(photo_task.id)


def test_resolving_the_drawing_task_leaves_the_photo_task_open_and_joinable(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    one, two = _user(db, "zzt Sales One"), _user(db, "zzt Sales Two")
    esc(db, version, line, one, "drawing")
    esc(db, version, line, one, "photo")
    (drawing_task,) = trackers_for(db, product.id, "drawing")
    (photo_task,) = trackers_for(db, product.id, "photo")

    _svc().resolve(db, drawing_task.id, actor(seed["assignee"]))

    db.refresh(photo_task)
    assert photo_task.is_resolved is False
    out = esc(db, version, line, one, "photo")
    assert out["joined"] is True and out["escalation"]["requester_count"] == 1


# ----------------------------------------------------------------- the route: team, brand, policy


@pytest.mark.parametrize("kind", KINDS)
def test_the_team_set_is_read_from_the_product_attachment_domain_row(db, env, kind):
    seed = seed_drawing_team(db)
    policy_b = _policy(db, tiers=1)
    other = add_team_set(
        db, agent_id=seed["agent_id"], company_id=seed["company_id"], policy_id=policy_b
    )
    db.query(ChatbotDomain).filter(ChatbotDomain.id == seed["domain_id"]).update(
        {"escalation_team_code": other["team_set_code"]}
    )
    db.commit()
    product, version, line = quoted_product(db, env)

    esc(db, version, line, _user(db, "zzt Sales One"), kind)

    (tracker,) = trackers_for(db, product.id, kind)
    assert tracker.team_set_code == other["team_set_code"]
    assert tracker.assigned_to_id == other["members"][1]
    assert str(tracker.policy_id) == policy_b, "the policy is the team set's own binding"


@pytest.mark.parametrize("kind", KINDS)
def test_a_brand_tagged_member_always_gets_that_brands_products(db, env, kind):
    seed = seed_drawing_team(db, members_per_tier=2)
    mocha_member, cabana_member = seed["pool"][1]
    tag_member(db, seed, mocha_member, "mocha")
    tag_member(db, seed, cabana_member, "cabana")
    db.commit()
    caller = _user(db, "zzt Sales One")

    for _ in range(3):
        product, version, line = quoted_product(db, env, brand="MOCHA")
        esc(db, version, line, caller, kind)
        (tracker,) = trackers_for(db, product.id, kind)
        assert tracker.assigned_to_id == mocha_member, "round robin must be narrowed to the brand"
        assert tracker.brand_code == "mocha"


@pytest.mark.parametrize("kind", KINDS)
def test_a_product_with_no_brand_round_robins_over_the_whole_tier_team(db, env, kind):
    seed = seed_drawing_team(db, members_per_tier=2)
    first_member, second_member = seed["pool"][1]
    tag_member(db, seed, first_member, "mocha")
    tag_member(db, seed, second_member, "cabana")
    db.commit()
    caller = _user(db, "zzt Sales One")

    drawn = []
    for _ in range(2):
        product, version, line = quoted_product(db, env)
        esc(db, version, line, caller, kind)
        (tracker,) = trackers_for(db, product.id, kind)
        assert tracker.brand_code is None
        drawn.append(tracker.assigned_to_id)

    assert set(drawn) == {first_member, second_member}


@pytest.mark.parametrize("kind", KINDS)
def test_the_overdue_scan_keeps_the_brand_when_it_escalates_a_tier(db, env, kind):
    from app.services.form_sla_service import FormSLAOrchestrator

    seed = seed_drawing_team(db, tiers=2, members_per_tier=2)
    mocha_t2, cabana_t2 = seed["pool"][2]
    tag_member(db, seed, mocha_t2, "mocha", level=2)
    tag_member(db, seed, cabana_t2, "cabana", level=2)
    db.commit()
    caller = _user(db, "zzt Sales One")
    trackers = []
    # Two products: an unnarrowed round robin would hand the second one to the other member.
    for _ in range(2):
        product, version, line = quoted_product(db, env, brand="MOCHA")
        esc(db, version, line, caller, kind)
        (tracker,) = trackers_for(db, product.id, kind)
        tracker.due_at = datetime.utcnow() - timedelta(hours=1)
        tracker.due_at_resolution = datetime.utcnow() - timedelta(hours=1)
        trackers.append(tracker)
    db.commit()

    result = FormSLAOrchestrator(db).scan_overdue_and_escalate()

    assert result["escalated"] == 2, result
    for tracker in trackers:
        db.refresh(tracker)
        assert tracker.current_tier == 2
        assert tracker.assigned_to_id == mocha_t2
        assert tracker.brand_code == "mocha"


@pytest.mark.parametrize("kind", KINDS)
def test_the_overdue_scan_moves_a_media_task_up_and_notifies_the_new_assignee(db, env, kind):
    from app.services.form_sla_service import FormSLAOrchestrator

    seed = seed_drawing_team(db, tiers=2, whatsapp_on_escalation=True, link_whatsapp=True)
    product, version, line = quoted_product(db, env)
    esc(db, version, line, _user(db, "zzt Sales One"), kind)
    (tracker,) = trackers_for(db, product.id, kind)
    tracker.due_at = datetime.utcnow() - timedelta(hours=1)
    tracker.due_at_resolution = datetime.utcnow() - timedelta(hours=1)
    db.commit()

    result = FormSLAOrchestrator(db).scan_overdue_and_escalate()

    db.refresh(tracker)
    assert result["escalated"] == 1, result
    assert tracker.assigned_to_id == seed["members"][2]
    notes = [
        n
        for n in notes_for(db, seed["members"][2])
        if n.source_entity_type == FORM_SLA_NOTE_SOURCE and n.event_type == "escalated"
    ]
    assert len(notes) == 1
    assert channels(db, notes[0]) == {"in_app", "email", "whatsapp"}


@pytest.mark.parametrize("kind", KINDS)
def test_no_form_sla_config_row_exists_or_is_needed(db, env, kind):
    seed_drawing_team(db)
    assert db.query(FormSLAConfig).count() == 0
    product, version, line = quoted_product(db, env)

    esc(db, version, line, _user(db, "zzt Sales One"), kind)

    assert len(trackers_for(db, product.id, kind)) == 1
    assert db.query(FormSLAConfig).count() == 0


@pytest.mark.parametrize("kind", KINDS)
def test_a_form_sla_config_row_for_the_type_is_ignored(db, env, kind):
    """A leftover admin step must not redirect the task: the route is general enquiries."""
    seed = seed_drawing_team(db)
    decoy_agent = _uid()
    db.add(AccessAgent(id=decoy_agent, code=unique_code("decoy"), name="ZZT Decoy"))
    db.flush()
    decoy_policy = _policy(db, tiers=1)
    decoy = add_team_set(db, agent_id=decoy_agent, company_id=seed["company_id"], policy_id=decoy_policy)
    db.add(
        FormSLAConfig(
            id=_uid(),
            source_entity_type=SOURCES[kind],
            stage_code=unique_code("stage"),
            policy_id=decoy_policy,
            agent_code=db.query(AccessAgent.code).filter(AccessAgent.id == decoy_agent).scalar(),
            team_set_code=decoy["team_set_code"],
            start_event="escalate",
            respond_event="respond",
            resolve_event="resolve",
            is_active=True,
            notify_assignee=True,
        )
    )
    db.commit()
    product, version, line = quoted_product(db, env)

    esc(db, version, line, _user(db, "zzt Sales One"), kind)

    (tracker,) = trackers_for(db, product.id, kind)
    assert tracker.assigned_to_id == seed["assignee"]
    assert tracker.agent_id == seed["agent_id"]


def test_no_team_or_config_is_hard_coded_in_the_service():
    """The team set is the chatbot domain row's, never a literal, and no stage config is read."""
    source = inspect.getsource(_svc())
    for needle in ("marketing_product", "purchasing", "FormSLAConfig", "form_sla_configs"):
        assert needle not in source, f"{needle!r} must not appear in the service"


# --------------------------------------------------------------------- the 409 for a missing route


NOT_SET_UP_VARIANTS = [
    "no_general_enquiries_agent",
    "no_domain_row",
    "domain_without_team_code",
    "domain_names_unknown_team_set",
    "no_tier1_team_in_the_products_company",
    "no_member",
    "no_policy_binding",
]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("variant", NOT_SET_UP_VARIANTS)
def test_a_missing_piece_of_the_route_is_the_plain_409_with_no_internals(db, env, kind, variant):
    seed = seed_drawing_team(
        db,
        agent=variant != "no_general_enquiries_agent",
        domain=variant != "no_domain_row",
        policy=variant != "no_policy_binding",
    )
    if variant == "domain_without_team_code":
        db.query(ChatbotDomain).filter(ChatbotDomain.id == seed["domain_id"]).update(
            {"escalation_team_code": None}
        )
    elif variant == "domain_names_unknown_team_set":
        db.query(ChatbotDomain).filter(ChatbotDomain.id == seed["domain_id"]).update(
            {"escalation_team_code": unique_code("no-such-set")}
        )
    elif variant == "no_tier1_team_in_the_products_company":
        db.query(AgentTeam).filter(AgentTeam.agent_id == seed["agent_id"]).update(
            {"company_id": _second_company(db)}
        )
    elif variant == "no_member":
        db.query(TeamMember).filter(TeamMember.team_id == seed["team_ids"][1]).delete()
    db.commit()
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")

    with pytest.raises(AppException) as refused:
        esc(db, version, line, caller, kind)

    assert refused.value.status_code == 409
    assert refused.value.code == "marketing_team_not_set_up"
    assert NOT_SET_UP in refused.value.message
    shown = f"{refused.value.message} {refused.value.detail}"
    for internal in (seed["team_set_code"], seed["agent_id"], seed["policy_id"], str(seed["domain_id"])):
        assert internal not in shown
    assert "drawing_requests_not_set_up" not in shown
    assert trackers_for(db, product.id, kind) == []
    assert db.query(User).count() > 0, "the session must be usable after the refusal"


# --------------------------------------------------------------------------- photo trigger states


def _photo_cell(db, line) -> dict:
    from app.services import project_quotation_service as quotes

    return quotes.serialize_lines(db, [line])[0]["product_image"]


def test_a_product_with_no_photo_reads_no_photos_and_may_escalate_a_photo(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    assert _photo_cell(db, line)["state"] == "no_photos"

    out = esc(db, version, line, _user(db, "zzt Sales One"), "photo")

    assert out["joined"] is False
    assert len(trackers_for(db, product.id, "photo")) == 1


@pytest.mark.parametrize(
    "variant,expected_state",
    [("two_unpicked", "not_chosen"), ("two_one_primary", "chosen"), ("single_photo", "chosen")],
)
def test_a_product_that_has_any_photo_is_refused_product_has_photo(db, env, variant, expected_state):
    from app.models.product import ProductAttachment

    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _photo(db, env, product, "p1.jpg")
    if variant != "single_photo":
        _photo(db, env, product, "p2.jpg")
    if variant == "two_one_primary":
        first = db.query(ProductAttachment).filter(ProductAttachment.product_id == product.id).first()
        first.is_primary = True
    db.commit()
    assert _photo_cell(db, line)["state"] == expected_state

    with pytest.raises(AppException) as refused:
        esc(db, version, line, _user(db, "zzt Sales One"), "photo")

    assert refused.value.status_code == 409
    assert refused.value.code == "product_has_photo"
    assert trackers_for(db, product.id, "photo") == []


@pytest.mark.parametrize("variant", ["deleted_photo", "drawing_image_only", "photo_typed_pdf_only"])
def test_files_that_are_not_a_photograph_do_not_block_a_photo_escalation(db, env, variant):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    if variant == "deleted_photo":
        _photo(db, env, product, "gone.jpg", deleted=True)
    elif variant == "drawing_image_only":
        _drawing(db, env, product, "d.png")
    else:
        _photo(db, env, product, "brochure.pdf", mime="application/pdf")
    db.commit()
    assert _photo_cell(db, line)["state"] == "no_photos"

    esc(db, version, line, _user(db, "zzt Sales One"), "photo")

    assert len(trackers_for(db, product.id, "photo")) == 1


def test_a_photo_does_not_block_a_drawing_escalation(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _photo(db, env, product, "p1.jpg")
    db.commit()

    esc(db, version, line, _user(db, "zzt Sales One"), "drawing")

    assert len(trackers_for(db, product.id, "drawing")) == 1


def test_an_off_catalogue_line_is_refused_for_a_photo_too(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    _document, scope = _scope(db, env)
    line = _legacy_line_without_product(db, scope)
    version = quotes.current_version(db, scope.id)
    db.commit()

    with pytest.raises(AppException) as refused:
        esc(db, version, line, _user(db, "zzt Sales One"), "photo")

    assert (refused.value.status_code, refused.value.code) == (409, "line_has_no_product")
    assert (
        db.query(ConversationSLATracking)
        .filter(ConversationSLATracking.source_entity_type.in_(list(SOURCES.values())))
        .count()
        == 0
    )


def test_an_unknown_kind_is_refused_and_creates_nothing(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)

    with pytest.raises(AppException) as refused:
        esc(db, version, line, _user(db, "zzt Sales One"), "datasheet")

    assert refused.value.status_code in (400, 422)
    assert trackers_for(db, product.id, "drawing") == [] and trackers_for(db, product.id, "photo") == []


def test_the_photo_lock_key_is_per_kind_and_product(db, env, monkeypatch):
    """A drawing escalation holds the drawing key, a photo one its own: two kinds of one product
    must not make each other answer busy. With the drawing key held by another connection, a
    PHOTO escalation of the same product runs at once; a key without the kind would make it wait
    out the timeout and answer busy."""
    import time

    from app.database import engine as base_engine

    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")
    db.commit()
    monkeypatch.setattr(_svc(), "LOCK_TIMEOUT_SECONDS", 3)
    holder = base_engine.connect()
    key = {"k": f"product_drawing:{product.id}:{caller}"}
    holder.execute(text("SELECT pg_advisory_lock(hashtext(:k))"), key)
    try:
        started = time.monotonic()
        out = esc(db, version, line, caller, "photo")
        waited = time.monotonic() - started
    finally:
        holder.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), key)
        holder.close()
    assert out["joined"] is False
    assert waited < 2.5, f"the photo escalation waited {waited:.1f}s on the DRAWING key"


def test_drawing_and_photo_of_one_product_lock_two_different_keys(db, env):
    """The rule itself, whatever the key's spelling: one product's drawing and photo escalations
    take two different advisory keys, each naming the product. A key without the kind would make
    the two kinds queue behind each other (and a held drawing lock answer a photo click busy)."""
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")
    keys: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        if "pg_advisory_lock" in statement and isinstance(parameters, dict):
            keys.append(str(parameters.get("k")))

    connection = db.get_bind()
    event.listen(connection, "before_cursor_execute", _record)
    try:
        esc(db, version, line, caller, "drawing")
        esc(db, version, line, caller, "photo")
    finally:
        event.remove(connection, "before_cursor_execute", _record)

    assert len(keys) == 2, keys
    assert keys[0] != keys[1], f"drawing and photo locked the same key {keys[0]!r}"
    assert all(str(product.id) in key for key in keys), keys


def test_the_lock_connection_keeps_one_transaction_from_lock_to_unlock(sent):
    """Behind a transaction-mode pooler a COMMIT between lock and unlock would hand the connection
    back and the unlock would run elsewhere. The lock's own connection must run lock and unlock
    inside one open transaction: no COMMIT between them."""
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from ._pg_fixture import blank_schema_engine

    engine = blank_schema_engine()
    log: list[tuple] = []

    def on_sql(conn, cursor, statement, parameters, context, executemany):
        log.append(("sql", id(conn), statement.lower()))

    def on_commit(conn):
        log.append(("commit", id(conn), ""))

    event.listen(engine, "before_cursor_execute", on_sql)
    event.listen(engine, "commit", on_commit)
    session = Session(bind=engine)
    try:
        with _svc()._product_lock(session, "product_drawing", _uid()):
            pass
    finally:
        session.close()
        event.remove(engine, "before_cursor_execute", on_sql)
        event.remove(engine, "commit", on_commit)

    lock = next(i for i, e in enumerate(log) if e[0] == "sql" and "pg_advisory_lock" in e[2])
    unlock = next(i for i, e in enumerate(log) if e[0] == "sql" and "pg_advisory_unlock" in e[2])
    lock_conn = log[lock][1]
    assert log[unlock][1] == lock_conn, "unlock ran on another connection"
    commits = [e for e in log[lock:unlock] if e[0] == "commit" and e[1] == lock_conn]
    assert commits == [], "a COMMIT ran on the lock connection between lock and unlock"


# ---------------------------------------------------------------------------------- per-kind state


def test_states_are_per_kind(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    esc(db, version, line, _user(db, "zzt Sales One"), "drawing")

    drawing_state = _svc().escalation_states(db, [product.id], kind="drawing")[str(product.id)]
    photo_state = _svc().escalation_states(db, [product.id], kind="photo")[str(product.id)]

    assert drawing_state is not None and drawing_state["requester_count"] == 1
    assert photo_state is None

    esc(db, version, line, _user(db, "zzt Sales Two"), "photo")
    photo_state = _svc().escalation_states(db, [product.id], kind="photo")[str(product.id)]
    assert photo_state is not None and photo_state["requester_count"] == 1
    assert photo_state["tracking_id"] != drawing_state["tracking_id"]


@pytest.mark.parametrize("kind", KINDS)
def test_states_cost_the_same_number_of_queries_for_one_product_or_many_per_kind(db, env, kind):
    seed_drawing_team(db)
    products = []
    for _ in range(4):
        product, version, line = quoted_product(db, env)
        esc(db, version, line, _user(db, "zzt Sales One"), kind)
        products.append(product.id)
    _svc().escalation_states(db, products, kind=kind)

    with captured_sql(db) as one:
        _svc().escalation_states(db, products[:1], kind=kind)
    with captured_sql(db) as many:
        _svc().escalation_states(db, products, kind=kind)

    assert len(many) == len(one), (len(one), len(many))


# ------------------------------------------------------------------------- respond / resolve, both


@pytest.mark.parametrize("kind", KINDS)
def test_respond_then_resolve_flip_the_task_and_the_my_pending_row(db, env, kind):
    from app.services.sla_service import ConversationSLATrackingService

    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    esc(db, version, line, _user(db, "zzt Sales One"), kind)
    (tracker,) = trackers_for(db, product.id, kind)
    pending = ConversationSLATrackingService(db)

    row = next(r for r in pending.list_my_pending(seed["assignee"]) if r["id"] == str(tracker.id))
    assert row["is_responded"] is False and row["due_kind"] == "respond"
    assert row["source_entity_type"] == SOURCES[kind]
    assert row["is_form_sla"] is True
    assert row["reference"] == product.product_code

    _svc().respond(db, tracker.id, actor(seed["assignee"]))
    db.refresh(tracker)
    assert tracker.is_responded is True and tracker.is_resolved is False
    assert str(tracker.responded_by) == str(seed["assignee"])
    row = next(r for r in pending.list_my_pending(seed["assignee"]) if r["id"] == str(tracker.id))
    assert row["is_responded"] is True and row["due_kind"] == "resolve"

    _svc().resolve(db, tracker.id, actor(seed["assignee"]))
    db.refresh(tracker)
    assert tracker.is_resolved is True
    assert [r for r in pending.list_my_pending(seed["assignee"]) if r["id"] == str(tracker.id)] == []


@pytest.mark.parametrize("kind", KINDS)
def test_resolve_without_a_prior_respond_also_marks_it_responded(db, env, kind):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    esc(db, version, line, _user(db, "zzt Sales One"), kind)
    (tracker,) = trackers_for(db, product.id, kind)

    _svc().resolve(db, tracker.id, actor(seed["assignee"]))

    db.refresh(tracker)
    assert tracker.is_resolved is True and tracker.is_responded is True


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("action", ["respond", "resolve"])
def test_someone_who_is_not_the_assignee_cannot_act_and_nothing_changes(db, env, action, kind):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    esc(db, version, line, _user(db, "zzt Sales One"), kind)
    (tracker,) = trackers_for(db, product.id, kind)
    stranger = _user(db, "zzt Stranger")

    with pytest.raises(AppException) as refused:
        getattr(_svc(), action)(db, tracker.id, actor(stranger))

    assert refused.value.status_code in (400, 404)
    db.refresh(tracker)
    assert tracker.is_resolved is False and tracker.is_responded is False


@pytest.mark.parametrize("kind", KINDS)
def test_respond_and_resolve_work_after_the_domains_team_set_changed(db, env, kind):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    esc(db, version, line, _user(db, "zzt Sales One"), kind)
    (tracker,) = trackers_for(db, product.id, kind)
    db.query(ChatbotDomain).filter(ChatbotDomain.id == seed["domain_id"]).update(
        {"escalation_team_code": "changed"}
    )
    db.commit()

    _svc().respond(db, tracker.id, actor(seed["assignee"]))
    _svc().resolve(db, tracker.id, actor(seed["assignee"]))

    db.refresh(tracker)
    assert tracker.is_resolved is True and str(tracker.resolved_by) == str(seed["assignee"])


# --------------------------------------------------------------------------- H1, per kind


@pytest.mark.parametrize("kind", KINDS)
def test_h1_opening_the_task_notifies_the_assignee_on_every_channel_they_allow(db, env, kind):
    seed = seed_drawing_team(db, whatsapp_on_assignment=True, link_whatsapp=True)
    product, version, line = quoted_product(db, env)

    esc(db, version, line, _user(db, "zzt Sales One"), kind)

    (tracker,) = trackers_for(db, product.id, kind)
    note = _assigned_note(db, seed, tracker)
    assert note.event_type == "assigned"
    assert note.title == f"New SLA assignment: {product.product_code}"
    assert channels(db, note) == {"in_app", "email", "whatsapp"}
    assert note.data["link"] == f"/master-data-management/products/{product.id}"
    assert note.data["whatsapp_use_case"] == "sla_assignment"
    assert f"/master-data-management/products/{product.id}" in note.data["whatsapp_context_vars"]["form_url"]


# --------------------------------------------------------------------------- H3 for photos


def _photo_added_notes(db, user_id) -> list:
    return [n for n in notes_for(db, user_id) if "Photo added" in f"{n.title} {n.body or ''}"]


def test_h3_attaching_a_photo_while_the_photo_task_is_open_notifies_the_assignee_and_leaves_it_open(
    db, env
):
    seed = seed_drawing_team(db, whatsapp_on_assignment=True, link_whatsapp=True)
    product, version, line = quoted_product(db, env)
    esc(db, version, line, _user(db, "zzt Sales One"), "photo")
    (tracker,) = trackers_for(db, product.id, "photo")
    attachment = _file(db, env["company_id"], PHOTOS, "late.jpg")

    _link_through_the_product_service(db, product, attachment)

    db.refresh(tracker)
    assert tracker.is_resolved is False and tracker.voided_at is None, "a photo must not close the task"
    (note,) = _photo_added_notes(db, seed["assignee"])
    assert product.product_code in f"{note.title} {note.body or ''}"
    assert "resolve" in (note.body or "").lower()
    assert channels(db, note) == {"in_app", "email", "whatsapp"}
    assert note.data["whatsapp_use_case"] == "sla_assignment"


def test_h3_each_kind_notifies_only_its_own_task(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")
    esc(db, version, line, caller, "drawing")
    esc(db, version, line, caller, "photo")
    drawing_task = trackers_for(db, product.id, "drawing")[0]
    photo_task = trackers_for(db, product.id, "photo")[0]

    _link_through_the_product_service(db, product, _file(db, env["company_id"], PHOTOS, "late.jpg"))
    assert len(_photo_added_notes(db, seed["assignee"])) == 1
    assert _drawing_added_notes(db, seed["assignee"]) == [], "a photo must not touch the drawing task"

    _link_through_the_product_service(db, product, _file(db, env["company_id"], DRAWINGS, "late.png"))
    assert len(_drawing_added_notes(db, seed["assignee"])) == 1
    assert len(_photo_added_notes(db, seed["assignee"])) == 1, "a drawing must not touch the photo task"
    db.refresh(drawing_task)
    db.refresh(photo_task)
    assert drawing_task.is_resolved is False and photo_task.is_resolved is False


def test_h3_a_drawing_typed_image_or_a_non_image_photo_file_does_not_notify_the_photo_task(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    esc(db, version, line, _user(db, "zzt Sales One"), "photo")

    _link_through_the_product_service(db, product, _file(db, env["company_id"], DRAWINGS, "d.png"))
    _link_through_the_product_service(
        db, product, _file(db, env["company_id"], PHOTOS, "brochure.pdf", mime="application/pdf")
    )

    assert _photo_added_notes(db, seed["assignee"]) == []


def test_h3_a_photo_with_no_open_photo_task_notifies_nobody(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    esc(db, version, line, _user(db, "zzt Sales One"), "drawing")  # only a DRAWING task is open

    _link_through_the_product_service(db, product, _file(db, env["company_id"], PHOTOS, "early.jpg"))

    assert _photo_added_notes(db, seed["assignee"]) == []
    assert trackers_for(db, product.id, "photo") == []


def test_notify_photo_linked_is_a_noop_without_an_open_photo_task_and_notifies_with_one(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)

    _svc().notify_photo_linked(db, product.id)
    assert _photo_added_notes(db, seed["assignee"]) == []

    esc(db, version, line, _user(db, "zzt Sales One"), "photo")
    _svc().notify_photo_linked(db, product.id)
    assert len(_photo_added_notes(db, seed["assignee"])) == 1


def test_a_failed_photo_linked_notice_does_not_break_the_attachment_link(db, env, monkeypatch):
    from app.services.notification_service import NotificationService

    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    esc(db, version, line, _user(db, "zzt Sales One"), "photo")
    attachment = _file(db, env["company_id"], PHOTOS, "late.jpg")
    monkeypatch.setattr(NotificationService, "create_with_channel_preferences", _broken_notice(db))

    link = _link_through_the_product_service(db, product, attachment)

    assert link is not None and str(link.attachment_id) == str(attachment.id)
    assert db.query(User).count() > 0


# --------------------------------------------------------------------------- H4, per kind


@pytest.mark.parametrize("kind", KINDS)
def test_h4_resolving_tells_every_requester_once_naming_the_kind(db, env, kind):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    first, second = _user(db, "zzt Sales One"), _user(db, "zzt Sales Two")
    esc(db, version, line, first, kind)
    esc(db, version, line, second, kind)
    for tracker in trackers_for(db, product.id, kind):
        _svc().resolve(db, tracker.id, actor(seed["assignee"]))

    for requester in (first, second):
        told = [n for n in notes_for(db, requester) if n.title == _resolved_title(kind, product)]
        assert len(told) == 1, [n.title for n in notes_for(db, requester)]
        assert "in_app" in channels(db, told[0])
        assert LABEL[kind].lower() in f"{told[0].title} {told[0].body}".lower()
    assert [n for n in notes_for(db, seed["assignee"]) if n.title == _resolved_title(kind, product)] == []


def test_h4_resolving_the_photo_task_does_not_tell_the_drawing_requesters(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    drawing_person, photo_person = _user(db, "zzt Sales One"), _user(db, "zzt Sales Two")
    esc(db, version, line, drawing_person, "drawing")
    esc(db, version, line, photo_person, "photo")
    (photo_task,) = trackers_for(db, product.id, "photo")

    _svc().resolve(db, photo_task.id, actor(seed["assignee"]))

    assert [n for n in notes_for(db, photo_person) if n.title == _resolved_title("photo", product)]
    assert [n for n in notes_for(db, drawing_person) if "resolved" in n.title] == []


# ----------------------------------------------------------------------- the photo cell, line read


def test_a_no_photos_cell_carries_the_photo_escalation_and_null_when_there_is_none(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    asked, version, line = quoted_product(db, env)
    quiet_product = _product(db, env)
    _document, scope = _scope(db, env)
    quiet_line = _priced_line(db, env, scope, quiet_product)
    esc(db, version, line, _user(db, "zzt Sales One"), "photo")

    cells = {r["id"]: r["product_image"] for r in quotes.serialize_lines(db, [line, quiet_line])}

    assert cells[line.id]["state"] == "no_photos"
    escalation = cells[line.id]["escalation"]
    assert set(escalation) >= {"tracking_id", "opened_at", "responded_at", "due_at", "requester_count", "last_resolved_at"}
    assert escalation["requester_count"] == 1
    assert "escalation" in cells[quiet_line.id] and cells[quiet_line.id]["escalation"] is None


def test_each_cell_carries_only_its_own_kinds_escalation(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    esc(db, version, line, _user(db, "zzt Sales One"), "drawing")

    row = quotes.serialize_lines(db, [line])[0]

    assert row["technical_drawing"]["escalation"] is not None
    assert row["product_image"]["escalation"] is None

    esc(db, version, line, _user(db, "zzt Sales Two"), "photo")
    row = quotes.serialize_lines(db, [line])[0]
    assert row["technical_drawing"]["escalation"]["tracking_id"] != row["product_image"]["escalation"]["tracking_id"]


def test_a_not_chosen_photo_cell_keeps_todays_behaviour_with_no_escalation(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _photo(db, env, product, "p1.jpg")
    _photo(db, env, product, "p2.jpg")  # two photographs, none picked
    db.commit()

    cell = _photo_cell(db, line)

    assert cell["state"] == "not_chosen"
    assert cell.get("escalation") is None


# ---------------------------------------------------- final fix round: H3 only for a visible product


def test_a_file_linked_by_another_companys_session_does_not_notify_this_companys_assignee(db, env):
    from app.models.base import company_scope
    from app.models.product import Product

    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    esc(db, version, line, _user(db, "zzt Sales One"), "drawing")
    other = _second_company(db)
    db.query(Product).filter(Product.id == product.id).update({"company_id": other})
    db.commit()

    with company_scope(db, frozenset({env["company_id"]})):
        _svc().notify_drawing_linked(db, product.id)

    assert _drawing_added_notes(db, seed["assignee"]) == []


# =============================================================================================
# QUOTE-MEDIA-CHAT (PLAN-quote-media-chat-30oct.md): a drawing or photo request is a chat
# escalation. One ticket per (product, kind, requester); the requester's WhatsApp contact rides on
# the ticket; one acknowledgement per new ticket; the requester never gets WhatsApp notices.
# =============================================================================================

NOUN = {"drawing": "technical drawing", "photo": "product photo"}
SOURCE_TEXT = {"drawing": "Technical drawing for {code} ({no})", "photo": "Product photo for {code} ({no})"}
ACK_TEXT = (
    "Your project request: {noun} for {code} ({no}). Routed to your PIC, they will reply shortly."
)


@pytest.fixture
def acks(monkeypatch):
    """Records every call of the acknowledgement queue function. ``raising=False`` so a missing
    function reads as "never called" (an assertion), not as a fixture error."""
    calls: list = []
    monkeypatch.setattr(
        _svc(),
        "enqueue_request_ack",
        lambda contact_id, text, tracking_id=None: calls.append((contact_id, text)),
        raising=False,
    )
    return calls


@pytest.fixture
def notice_calls(monkeypatch):
    """Every ``create_with_channel_preferences`` call's keyword arguments; the real one still runs."""
    from app.services.notification_service import NotificationService

    calls: list = []
    real = NotificationService.create_with_channel_preferences

    def spy(self, *args, **kwargs):
        calls.append(kwargs)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(NotificationService, "create_with_channel_preferences", spy)
    return calls


def linked_user(db, name: str):
    """A salesperson whose ``users.respond_contact_id`` points at a real WhatsApp contact.
    Returns ``(user_id, contact)``."""
    contact = RespondContact(
        id=_uid(),
        phone_number=f"+6011{uuid.uuid4().int % 10**8:08d}",
        name=f"ZZT {name} WhatsApp",
        respond_io_id=f"zzt-rio-{uuid.uuid4().hex[:8]}",
        session_vars={},
    )
    db.add(contact)
    db.flush()
    user_id = _user(db, name)
    db.query(User).filter(User.id == user_id).update({"respond_contact_id": contact.id})
    db.commit()
    return user_id, contact


def quotation_no(db, version) -> str:
    """The number the quotation page prints for a draft: its document's number."""
    from app.models.projects import ProjectQuotation, ProjectQuotationDocument, ProjectQuotationVersion

    return (
        db.query(ProjectQuotationDocument.document_no)
        .join(ProjectQuotation, ProjectQuotation.document_id == ProjectQuotationDocument.id)
        .join(ProjectQuotationVersion, ProjectQuotationVersion.quotation_id == ProjectQuotation.id)
        .filter(ProjectQuotationVersion.id == version.id)
        .scalar()
    )


def _second_quotation_of(db, env, product):
    from app.services import project_quotation_service as quotes

    _document, scope = _scope(db, env)
    line = _priced_line(db, env, scope, product)
    version = quotes.current_version(db, scope.id)
    db.commit()
    return version, line


# ------------------------------------------------------------------ B1: one ticket per requester


@pytest.mark.parametrize("kind", KINDS)
def test_b1_two_requesters_get_two_tickets_and_a_repeat_joins_the_requesters_own(db, env, kind):
    seed_drawing_team(db)
    product, version_a, line_a = quoted_product(db, env)
    version_b, line_b = _second_quotation_of(db, env, product)
    a, b = _user(db, "zzt Sales One"), _user(db, "zzt Sales Two")

    first = esc(db, version_a, line_a, a, kind)
    second = esc(db, version_a, line_a, b, kind)

    rows = trackers_for(db, product.id, kind)
    assert len(rows) == 2, "B must not join A's ticket"
    assert first["joined"] is False and second["joined"] is False
    by_requester = {r.triggered_by_id: t for t in rows for r in requester_rows(db, t.id)}
    assert set(by_requester) == {a, b}
    assert all(len(requester_rows(db, t.id)) == 1 for t in rows)

    again = esc(db, version_b, line_b, a, kind)

    assert again["joined"] is True
    assert len(trackers_for(db, product.id, kind)) == 2, "A's repeat opens nothing"
    assert str(again["escalation"]["tracking_id"]) == str(by_requester[a].id), "the answer is A's own ticket"
    reasons = {r.reason for r in requester_rows(db, by_requester[a].id)}
    assert reasons == {f"quotation_version:{version_a.id}", f"quotation_version:{version_b.id}"}
    assert {r.reason for r in requester_rows(db, by_requester[b].id)} == {f"quotation_version:{version_a.id}"}


# --------------------------------------------------------------------------- the lock parameter


@pytest.mark.parametrize("kind", KINDS)
def test_b1_the_advisory_lock_key_is_source_product_and_requester(db, env, kind):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    a, b = _user(db, "zzt Sales One"), _user(db, "zzt Sales Two")
    keys: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        if "pg_advisory_lock" in statement and isinstance(parameters, dict):
            keys.append(str(parameters.get("k")))

    connection = db.get_bind()
    event.listen(connection, "before_cursor_execute", _record)
    try:
        esc(db, version, line, a, kind)
        esc(db, version, line, b, kind)
    finally:
        event.remove(connection, "before_cursor_execute", _record)

    assert keys == [f"{SOURCES[kind]}:{product.id}:{a}", f"{SOURCES[kind]}:{product.id}:{b}"]


# ----------------------------------------------------------- B2: the ticket is on the contact


@pytest.mark.parametrize("kind", KINDS)
def test_b2_a_new_ticket_carries_the_requesters_contact_and_the_exact_source_text(db, env, acks, kind):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    user_id, contact = linked_user(db, "zzt Sales One")

    esc(db, version, line, user_id, kind)

    (tracker,) = trackers_for(db, product.id, kind)
    assert tracker.respond_contact_id == contact.id
    assert tracker.contact is not None and tracker.contact.phone_number == contact.phone_number
    assert tracker.source_message_text == SOURCE_TEXT[kind].format(
        code=product.product_code, no=quotation_no(db, version)
    )


@pytest.mark.parametrize("kind", KINDS)
def test_b2_a_requester_without_a_contact_leaves_it_empty_but_the_source_text_is_set(db, env, acks, kind):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)

    esc(db, version, line, _user(db, "zzt Sales One"), kind)

    (tracker,) = trackers_for(db, product.id, kind)
    assert tracker.respond_contact_id is None
    assert tracker.contact is None
    assert tracker.source_message_text == SOURCE_TEXT[kind].format(
        code=product.product_code, no=quotation_no(db, version)
    )


# ----------------------------------------------------------------------- B3: the acknowledgement


@pytest.mark.parametrize("kind", KINDS)
def test_b3_a_new_ticket_with_a_contact_queues_one_acknowledgement_with_the_exact_text(db, env, acks, kind):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    user_id, contact = linked_user(db, "zzt Sales One")

    esc(db, version, line, user_id, kind)

    assert acks == [
        (
            contact.id,
            ACK_TEXT.format(noun=NOUN[kind], code=product.product_code, no=quotation_no(db, version)),
        )
    ]


@pytest.mark.parametrize("kind", KINDS)
def test_b3_a_join_queues_nothing(db, env, acks, kind):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    version_b, line_b = _second_quotation_of(db, env, product)
    user_id, _contact = linked_user(db, "zzt Sales One")

    esc(db, version, line, user_id, kind)
    assert len(acks) == 1, "the new ticket's own acknowledgement"
    again = esc(db, version_b, line_b, user_id, kind)

    assert again["joined"] is True
    assert len(acks) == 1, "a join sends nothing"


@pytest.mark.parametrize("kind", KINDS)
def test_b3_no_contact_queues_nothing(db, env, acks, kind):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)

    esc(db, version, line, _user(db, "zzt Sales One"), kind)

    assert acks == []


# ------------------------------------------------------------------------- B7: notices, no WhatsApp


@pytest.mark.parametrize("kind", KINDS)
def test_b7_the_requesters_resolved_notice_never_sends_whatsapp_and_is_in_app(db, env, notice_calls, kind):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    user_id, _contact = linked_user(db, "zzt Sales One")
    db.query(User).filter(User.id == user_id).update(
        {"notify_whatsapp_on_assignment": True, "notify_email_on_assignment": True}
    )
    db.commit()
    esc(db, version, line, user_id, kind)
    (tracker,) = trackers_for(db, product.id, kind)

    _svc().resolve(db, tracker.id, actor(seed["assignee"]))

    mine = [kw for kw in notice_calls if str(kw.get("user_id")) == user_id]
    assert mine, "the requester must still be told"
    assert all(not kw.get("send_whatsapp") for kw in mine), mine
    notes = [n for n in notes_for(db, user_id) if n.title == _resolved_title(kind, product)]
    assert len(notes) == 1
    assert "in_app" in channels(db, notes[0]) and "whatsapp" not in channels(db, notes[0])


def test_b7_the_pics_assignment_notice_keeps_whatsapp(db, env, notice_calls):
    seed = seed_drawing_team(db, whatsapp_on_assignment=True, link_whatsapp=True)
    product, version, line = quoted_product(db, env)

    esc(db, version, line, _user(db, "zzt Sales One"), "drawing")

    (tracker,) = trackers_for(db, product.id)
    pic = [kw for kw in notice_calls if str(kw.get("user_id")) == seed["assignee"]]
    assert pic and all(kw.get("send_whatsapp") is True for kw in pic), pic
    assert "whatsapp" in channels(db, _assigned_note(db, seed, tracker))


@pytest.mark.parametrize("kind", KINDS)
def test_b7_h3_a_linked_file_notifies_the_assignee_of_every_open_ticket(db, env, kind):
    seed = seed_drawing_team(db, members_per_tier=2)
    product, version, line = quoted_product(db, env)
    a, b = _user(db, "zzt Sales One"), _user(db, "zzt Sales Two")
    esc(db, version, line, a, kind)
    esc(db, version, line, b, kind)
    ticket_a, ticket_b = sorted(trackers_for(db, product.id, kind), key=lambda t: t.initiated_at)
    first_pic, second_pic = seed["pool"][1]
    ticket_a.assigned_to_id, ticket_b.assigned_to_id = first_pic, second_pic
    db.commit()

    if kind == "drawing":
        _svc().notify_drawing_linked(db, product.id)
    else:
        _svc().notify_photo_linked(db, product.id)

    noun = "Drawing" if kind == "drawing" else "Photo"
    for pic in (first_pic, second_pic):
        added = [n for n in notes_for(db, pic) if f"{noun} added" in f"{n.title} {n.body or ''}"]
        assert len(added) == 1, (pic, [n.title for n in notes_for(db, pic)])


# ---------------------------------------------------------------- B8: the tile is per viewer


@pytest.mark.parametrize("kind", KINDS)
def test_b8_states_for_a_requester_show_only_their_own_open_ticket(db, env, kind):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    a, b = _user(db, "zzt Sales One"), _user(db, "zzt Sales Two")
    esc(db, version, line, a, kind)
    (ticket_a,) = trackers_for(db, product.id, kind)
    pid = str(product.id)

    mine = _svc().escalation_states_by_kind(db, [pid], requester_id=a)[kind][pid]
    theirs = _svc().escalation_states_by_kind(db, [pid], requester_id=b)[kind][pid]

    assert mine is not None and str(mine["tracking_id"]) == str(ticket_a.id)
    assert theirs is None, "B has no ticket while A's is open"

    esc(db, version, line, b, kind)
    ticket_b = next(t for t in trackers_for(db, product.id, kind) if str(t.id) != str(ticket_a.id))
    again = _svc().escalation_states_by_kind(db, [pid], requester_id=b)[kind][pid]
    assert str(again["tracking_id"]) == str(ticket_b.id)
    assert str(_svc().escalation_states_by_kind(db, [pid], requester_id=a)[kind][pid]["tracking_id"]) == str(
        ticket_a.id
    )

    _svc().resolve(db, ticket_b.id, actor(seed["assignee"]))
    after = _svc().escalation_states_by_kind(db, [pid], requester_id=b)[kind][pid]
    assert after["tracking_id"] is None and after["last_resolved_at"] is not None
    assert _svc().escalation_states_by_kind(db, [pid], requester_id=a)[kind][pid]["tracking_id"] is not None


# ----------------------------------------------------------- the detail says if there is a chat


def test_media_request_detail_has_conversation_follows_the_contact(db, env, acks):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    with_contact, _contact = linked_user(db, "zzt Sales One")
    without = _user(db, "zzt Sales Two")
    esc(db, version, line, with_contact, "drawing")
    esc(db, version, line, without, "photo")
    (drawing_task,) = trackers_for(db, product.id, "drawing")
    (photo_task,) = trackers_for(db, product.id, "photo")

    on = _svc().media_request_detail(db, drawing_task.id, actor(seed["assignee"]), has_resolve_permission=True)
    off = _svc().media_request_detail(db, photo_task.id, actor(seed["assignee"]), has_resolve_permission=True)

    assert on["has_conversation"] is True
    assert off["has_conversation"] is False


# ------------------------------------------------- R4: a contact with no Respond.io id


@pytest.mark.parametrize("kind", KINDS)
def test_r4_a_contact_without_a_respond_id_is_no_conversation(db, env, acks, kind):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    user_id, contact = linked_user(db, "zzt Sales One")
    db.query(RespondContact).filter(RespondContact.id == contact.id).update({"respond_io_id": ""})
    db.commit()

    esc(db, version, line, user_id, kind)

    (tracker,) = trackers_for(db, product.id, kind)
    assert tracker.respond_contact_id is None
    assert acks == []


# ------------------------------------------------- R5 K6: the ack is queued after the commit


def test_k6_the_ack_is_queued_only_once_the_ticket_is_committed(db, env, monkeypatch):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    user_id, contact = linked_user(db, "zzt Sales One")
    seen: list = []

    def _ack(contact_id, text, tracking_id=None):
        # Read before anything below opens a transaction of its own.
        open_transaction = db.in_transaction()
        tracker = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tracking_id).first()
        seen.append(
            {
                "open_transaction": open_transaction,
                "tracker_contact": tracker.respond_contact_id if tracker else None,
                "requesters": len(requester_rows(db, tracking_id)),
            }
        )

    monkeypatch.setattr(_svc(), "enqueue_request_ack", _ack)

    esc(db, version, line, user_id, "drawing")

    assert seen == [{"open_transaction": False, "tracker_contact": contact.id, "requesters": 1}]
