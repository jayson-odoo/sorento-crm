"""Hardening pass over S5/S6 (self-review, 2026-07-28).

Every test here was written to reproduce a defect found by reading the shipped code against
the way the rest of the system behaves, not by re-testing what the feature tests already
cover. Each one fails on the code as shipped.

The theme is **background and cross-company execution**. The feature tests all run inside a
request-shaped session where conftest defaults the company scope to Sorento, so a whole class
of production behaviour -- the daily sweep's unscoped session, a second company's user
reaching a project by id -- was never exercised at all.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import UNSET
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-hard"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    # `User.status` defaults to INACTIVE at the model level (invite-then-activate), so a test
    # user has to say ACTIVE out loud to stand for a working salesperson.
    user_id = _uid()
    db.add(
        User(id=user_id, email=f"{user_id}@zzt.test", name=name, status="ACTIVE")
    )
    db.flush()
    return user_id


def _project(db, company_id, owner, *, title=None, idle_days=0):
    from app.services.project_service import register_project

    project = register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=title or f"{MARKER} {uuid.uuid4().hex[:10]}",
        owner_user_id=owner,
    )
    db.flush()
    project.last_meaningful_activity_at = datetime.utcnow() - timedelta(days=idle_days)
    db.flush()
    return project


@pytest.fixture()
def seeded():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        yield db, str(company_id), owner


# ---------------------------------------------------------------- 1. the sweep's session


def test_the_staleness_sweep_works_on_an_unscoped_session(seeded):
    """The daily sweep runs from the scheduler on a bare ``SessionLocal()``, which has NO
    company scope. Company scoping is FAIL-CLOSED: an UNSET scope resolves to ``false()``, so
    ``db.query(Project)`` returns zero rows and the sweep reports ``scanned: 0`` for ever
    while looking perfectly healthy in the logs.

    Every other background job in the codebase says `set_company_scope(db, None)` first
    (export_tasks, import_tasks). This one did not.

    The test harness hid it: conftest defaults every session's scope to Sorento, so the
    feature tests were exercising a request-shaped session the scheduler never has.
    """
    from app.models.base import set_company_scope
    from app.services import project_staleness_service as svc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, idle_days=400)
    db.commit()

    # Reproduce the scheduler's session exactly: scope UNSET, nothing set by a dependency.
    set_company_scope(db, UNSET)
    summary = svc.sweep(db, notify=False)

    assert summary["scanned"] >= 1, (
        "the sweep saw no projects at all -- fail-closed scoping means it must widen the "
        "scope itself, the way every other background job does"
    )
    db.expire_all()
    assert svc.is_unattended(project) or int(project.stale_level or 0) == 3


# ---------------------------------------------------------------- 2 + 3. Committed money


def _po(db, project, *, amount=None, line_total=None, po_number=None):
    from app.models.projects import ProjectPurchaseOrder, ProjectPurchaseOrderLine

    po = ProjectPurchaseOrder(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        po_number=po_number or f"{MARKER}-{uuid.uuid4().hex[:6]}",
        po_source="contractor_direct",
        po_date=date(2026, 7, 1),
        po_amount=Decimal(amount) if amount is not None else None,
    )
    db.add(po)
    db.flush()
    if line_total is not None:
        db.add(
            ProjectPurchaseOrderLine(
                id=_uid(),
                company_id=project.company_id,
                po_id=po.id,
                description=f"{MARKER} tiles",
                unit_price=Decimal(line_total),
                quantity=Decimal("1"),
                line_total=Decimal(line_total),
            )
        )
        db.flush()
    return po


def test_committed_counts_a_po_that_only_has_lines(seeded):
    """`po_total` is the module's own rule: the LINES when there are any, else the header
    amount. The forecast summed `po_amount` alone, so a PO entered line by line with no header
    figure -- which is what the PO lines editor produces -- contributed exactly zero to
    Committed.

    Committed is the one number in the report that is supposed to be banked money. Silently
    understating it is worse than a missing feature, because somebody will act on it.
    """
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    _po(db, project, amount=None, line_total="120000.00")
    db.flush()

    numbers = fc.forecast(db, company_id=company_id)
    assert numbers["committed"] == Decimal("120000.00")


def test_committed_prefers_lines_over_a_stale_header_amount(seeded):
    """Same precedence as `po_total`, so the forecast and the PO detail page can never print
    two different figures for one PO."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    _po(db, project, amount="99000.00", line_total="120000.00")
    db.flush()

    numbers = fc.forecast(db, company_id=company_id)
    assert numbers["committed"] == Decimal("120000.00")


def test_a_recorded_po_stays_committed_even_if_the_project_ends_up_lost(seeded):
    """A PO is money the contractor already committed to. If the remaining scopes are then
    lost, the project's derived outcome becomes `lost` -- and the forecast dropped the whole
    project, taking its banked PO out of Committed with it.

    Pipeline and Weighted are right to ignore a lost project (there is nothing left to win).
    Committed is not: it reports what was ordered, and orders do not un-happen.
    """
    from app.models.projects import OUTCOME_LOST
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    _po(db, project, amount="80000.00")
    project.outcome = OUTCOME_LOST
    db.flush()

    numbers = fc.forecast(db, company_id=company_id)
    assert numbers["committed"] == Decimal("80000.00")
    # ...while the speculative pair correctly ignores it.
    assert numbers["pipeline"] == Decimal("0.00")
    assert numbers["weighted"] == Decimal("0.00")


def test_committed_by_year_also_counts_a_lines_only_po(seeded):
    """The year buckets have to agree with the headline, or the first person who adds up the
    column stops trusting the page."""
    from app.models.projects import ProjectSalesProfile
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    db.add(
        ProjectSalesProfile(
            project_id=project.id,
            launch_date=date(2026, 1, 1),
            expected_delivery_from=date(2027, 3, 1),
        )
    )
    _po(db, project, amount=None, line_total="45000.00")
    db.flush()

    numbers = fc.forecast(db, company_id=company_id)
    by_year = {row["year"]: row for row in numbers["by_year"]}
    assert by_year[2027]["committed"] == Decimal("45000.00")
    assert numbers["committed"] == Decimal("45000.00")


# ---------------------------------------------------------------- 6. re-breach alerting


def test_a_second_floor_breach_at_a_new_price_alerts_again(seeded):
    """The dedup key was the line id alone, so the FIRST breach on a line silenced every later
    one. A line re-priced above its floor and then dropped below it again is a NEW decision
    management has to approve; suppressing it because "same line" means the second give-away
    is invisible.

    Still deduplicated per (line, price), so a repeated save at the same price does not
    re-alert.
    """
    from app.models.projects import Project
    from app.services import project_notify_service as notify

    db, company_id, owner = seeded
    project = db.query(Project).filter(Project.id == _project(db, company_id, owner).id).first()

    line_id = _uid()
    first = {
        "line_id": line_id,
        "quotation_id": _uid(),
        "unit_price": Decimal("80.00"),
        "floor_value": Decimal("100.00"),
        "floor_level": "product",
    }
    again_lower = {**first, "unit_price": Decimal("70.00")}

    key_first = notify.floor_breach_dedup_key(first)
    key_again = notify.floor_breach_dedup_key(again_lower)
    key_repeat = notify.floor_breach_dedup_key(dict(first))

    assert key_first != key_again, "a breach at a NEW price must be able to alert again"
    assert key_first == key_repeat, "the same breach twice must stay deduplicated"


def test_a_lost_project_with_a_po_is_not_counted_as_a_live_pursuit(seeded):
    """The lost-with-a-PO rows are folded in for Committed only. `project_count` answers "how
    many are we chasing", so counting them would answer it with the ones we lost."""
    from app.models.projects import OUTCOME_LOST
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    live = _project(db, company_id, owner, title=f"{MARKER} still chasing")
    lost = _project(db, company_id, owner, title=f"{MARKER} lost but paid")
    _po(db, lost, amount="50000.00")
    lost.outcome = OUTCOME_LOST
    db.flush()

    numbers = fc.forecast(db, company_id=company_id)
    assert numbers["project_count"] == 1, "the lost project was counted as a live pursuit"
    assert numbers["committed"] == Decimal("50000.00")
    assert live.outcome == "open"


# ---------------------------------------------------------------- 7. "my pipeline" by name


def test_a_salesperson_name_resolves_to_a_user_uuid(seeded):
    """`crm_projects_list` filters "my pipeline" on `owner_user_ids`, a UUID -- and NOTHING in
    the system could produce one from a name: the entity resolver had no user probe, and the
    slimmed tool payload (rightly) no longer carries owner UUIDs.

    So "what is Ali working on" was unanswerable in both directions. A filter the agent cannot
    reach is the same as an absent filter, except it looks present in the tool description.
    """
    from app.services.entity_resolver import resolve_references

    db, _company_id, _owner = seeded
    ali = _user(db, "Zzt Hardening Aliyah")
    db.flush()

    result = resolve_references(
        db,
        ["Zzt Hardening Aliyah"],
        allowed_entity_types=["user"],
        enable_embedding_fallback=False,
    )
    resolved = {m.uuid for r in result.resolutions for m in r.matches}
    assert ali in resolved


def test_an_inactive_user_is_not_offered_as_an_owner(seeded):
    """A departed salesperson's name must not resolve: the answer "Ali has 12 live projects"
    about somebody who left is worse than "I could not find Ali"."""
    from app.models.user import User
    from app.services.entity_resolver import resolve_references

    db, _company_id, _owner = seeded
    gone_id = _uid()
    db.add(
        User(
            id=gone_id,
            email=f"{gone_id}@zzt.test",
            name="Zzt Hardening Departed",
            status="INACTIVE",
        )
    )
    db.flush()

    result = resolve_references(
        db,
        ["Zzt Hardening Departed"],
        allowed_entity_types=["user"],
        enable_embedding_fallback=False,
    )
    assert gone_id not in {m.uuid for r in result.resolutions for m in r.matches}


def test_the_owner_filter_params_are_registered_for_coercion():
    """Without these entries the resolved UUID never reaches the tool call, so the model passes
    the literal name into a UUID param and the backend 400s."""
    from app.services.ai_assistant_service import _UUID_PARAM_ENTITY_TYPES

    assert _UUID_PARAM_ENTITY_TYPES.get("owner_user_ids") == "user"
    assert _UUID_PARAM_ENTITY_TYPES.get("owner_user_id") == "user"


def test_a_name_in_the_owner_filter_is_substituted_before_dispatch(seeded):
    """The whole chain, end to end: the model writes the name it was shown in `owner_name`, and
    what leaves the dispatcher is a UUID the backend will accept. Anything unresolved is passed
    through untouched so the backend reports it instead of us dropping the filter silently.
    """
    from app.services.ai_assistant_service import AIAssistantChatService
    from app.services.entity_resolver import ResolutionResult

    db, _company_id, _owner = seeded
    ali = _user(db, "Zzt Hardening Dispatch Ali")
    db.flush()

    service = AIAssistantChatService.__new__(AIAssistantChatService)
    service.db = db  # type: ignore[attr-defined]

    out, subs = service._coerce_uuid_args(
        {"owner_user_ids": ["Zzt Hardening Dispatch Ali"], "limit": 20},
        # Nothing pre-resolved this turn, so the focused fallback has to carry it.
        ResolutionResult(tokens=[], resolutions=[], elapsed_ms=0.0),
    )
    assert out["owner_user_ids"] == [ali]
    assert out["limit"] == 20
    assert subs and subs[0]["param"] == "owner_user_ids"

    passthrough, _ = service._coerce_uuid_args(
        {"owner_user_ids": ["Nobody By That Name At All"]},
        ResolutionResult(tokens=[], resolutions=[], elapsed_ms=0.0),
    )
    assert passthrough["owner_user_ids"] == ["Nobody By That Name At All"]


def test_a_company_name_also_coerces_through_the_same_fallback(seeded):
    """Finding 8, which the owner filter only exposed: the fallback was handed the value as a
    free-text QUERY, so `extract_candidate_tokens` (code-like tokens only, plus names after a
    "customer is" marker) reduced a bare company name to nothing and the fallback returned []
    for every name it was ever asked about -- developers, suppliers, customers alike. Only
    values already resolved earlier in the turn ever coerced.

    Pinned on a developer party as well as a user so a later refactor of the user path cannot
    quietly re-narrow the shared one.
    """
    from app.models.projects import ProjectParty
    from app.services.ai_assistant_service import AIAssistantChatService
    from app.services.entity_resolver import ResolutionResult

    db, company_id, _owner = seeded
    party_id = _uid()
    db.add(
        ProjectParty(
            id=party_id,
            company_id=company_id,
            name="Zzt Hardening Damai Land Sdn Bhd",
            party_type="developer",
        )
    )
    db.flush()

    service = AIAssistantChatService.__new__(AIAssistantChatService)
    service.db = db  # type: ignore[attr-defined]

    out, _subs = service._coerce_uuid_args(
        {"developer_party_ids": ["Zzt Hardening Damai Land Sdn Bhd"]},
        ResolutionResult(tokens=[], resolutions=[], elapsed_ms=0.0),
    )
    assert out["developer_party_ids"] == [party_id]


# ---------------------------------------------------------------- 9 + 10. the ladder's edges


def test_winning_a_project_takes_it_off_the_unattended_list(seeded):
    """The sweep only ever SELECTED open projects, and nothing else clears the ladder except a
    human posting an activity. So a project that reached Unattended and was then won kept
    `stale_level = 3` for ever: the list badge says the project nobody is chasing is the one we
    just won, and -- worse -- the Unattended badge is what a manager acts on, so the one signal
    that a project is being neglected pointed at a project that had been closed.

    `evaluate` already answers "not on the ladder" for a decided project. The sweep simply
    never asked it about one.
    """
    from app.models.projects import OUTCOME_WON
    from app.services import project_staleness_service as svc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, idle_days=400)
    db.commit()
    svc.sweep(db, notify=False)
    db.expire_all()
    assert int(project.stale_level or 0) == 3  # arrange: genuinely neglected first

    project.outcome = OUTCOME_WON
    db.commit()

    summary = svc.sweep(db, notify=False)
    db.expire_all()
    assert int(project.stale_level or 0) == 0, "a won project is still flagged unattended"
    assert project.stale_reason is None
    assert project.stale_since is None
    assert summary["cleared"] >= 1


def test_a_project_that_goes_quiet_a_second_time_alerts_again(seeded):
    """The dedup key was `<project>:stale:<level>`, so the level-1 nudge could only ever fire
    ONCE in a project's life. Update the project, let it go quiet again three months later, and
    the nudge is silently swallowed as a duplicate of the one from last quarter.

    The key now carries the episode (the moment the project went quiet), so a repeated sweep
    inside one episode still dedupes -- which is the actual thing it was protecting against.
    """
    from app.services import project_staleness_service as svc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, idle_days=400)

    first = svc.stale_dedup_key(project, level=1)
    # Same episode, swept again tomorrow: must stay identical or the sweep re-sends daily.
    assert svc.stale_dedup_key(project, level=1) == first

    # Somebody updates it, it goes quiet again from a NEW anchor.
    project.stale_since = None
    project.last_meaningful_activity_at = datetime.utcnow() - timedelta(days=30)
    db.flush()
    second_episode = svc.stale_dedup_key(project, level=1)
    assert second_episode != first, "the second period of neglect could never alert"
    # And the rungs stay distinct within one episode.
    assert svc.stale_dedup_key(project, level=2) != second_episode


# ---------------------------------------------------------------- 11 + 12. forecast plumbing


def test_the_forecast_survives_a_company_whose_only_project_is_lost(seeded):
    """`_lost_projects_with_committed_money` carried `~Project.id.in_(live_ids) if live_ids else
    True`, which hands a bare Python ``True`` to `filter()` when nothing is live -- and the
    exclusion is redundant anyway, since the live set excludes lost projects by definition.

    The first company to reach this state is a real one: a brand-new company whose first
    project was lost after a partial PO, or any company early enough to have one row.
    """
    from app.models.projects import OUTCOME_LOST
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    lost = _project(db, company_id, owner, title=f"{MARKER} only ever lost")
    _po(db, lost, amount="15000.00")
    lost.outcome = OUTCOME_LOST
    db.flush()

    numbers = fc.forecast(db, company_id=company_id)
    assert numbers["committed"] == Decimal("15000.00")
    assert numbers["pipeline"] == Decimal("0.00")
    assert numbers["project_count"] == 0


def test_the_forecast_does_not_run_a_query_per_project(seeded):
    """`delivery_year` loaded the project's sales profile itself, inside the per-project loop,
    so the report cost one extra SELECT for every project in the company -- on a page a sales
    manager refreshes all day, and on the one table that grows for ever.

    Pinned as a RATIO rather than an absolute count so the test does not break every time a
    legitimate new query is added: doubling the projects must not change the query count at
    all. Everything else in this service is already resolved in bulk (`estimates`,
    `open_totals`, `committed`, `probabilities`); the profile lookup was the one that was not.
    """
    from sqlalchemy import event

    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    engine = db.get_bind()

    def _count_for(project_count: int) -> int:
        for _ in range(project_count):
            _project(db, company_id, owner)
        db.flush()
        seen = []

        def _tap(_conn, _cur, statement, *_a, **_k):
            seen.append(statement)

        event.listen(engine, "before_cursor_execute", _tap)
        try:
            fc.forecast(db, company_id=company_id)
        finally:
            event.remove(engine, "before_cursor_execute", _tap)
        return len(seen)

    first = _count_for(3)
    doubled = _count_for(3)  # six projects in the company by now
    assert doubled <= first, (
        f"the query count grew with the project count ({first} -> {doubled}): "
        "the forecast is doing per-project work that belongs in a bulk load"
    )


# ---------------------------------------------------------------- 13. one bad recipient


def test_one_failing_recipient_does_not_silence_the_rest_of_management(seeded, monkeypatch):
    """`_send` wrapped the WHOLE recipient loop in one try/except, so the first user whose
    delivery raised (a stale email address, a per-user preference row that fails to load)
    swallowed every remaining manager on the list.

    That is the wrong grain for a best-effort fan-out: best-effort means each recipient is
    attempted independently, not that one failure is allowed to cancel the alert. A price
    approved below floor because two of three managers never heard about it is the exact
    outcome this alert exists to prevent.
    """
    from app.services import project_notify_service as notify

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    good_one = _user(db, f"{MARKER} manager good")
    bad = _user(db, f"{MARKER} manager bad")
    good_two = _user(db, f"{MARKER} manager also good")
    db.flush()

    attempted: list[str] = []

    class _FlakyNotifications:
        def __init__(self, _db):
            pass

        def create_with_channel_preferences(self, **kwargs):
            user_id = kwargs["user_id"]
            attempted.append(user_id)
            if user_id == bad:
                raise RuntimeError("no email address on file")

    import app.services.notification_service as notification_module

    monkeypatch.setattr(
        notification_module, "NotificationService", _FlakyNotifications
    )
    monkeypatch.setattr(
        notify, "management_user_ids", lambda _db: [good_one, bad, good_two]
    )

    sent = notify.notify_floor_breach(
        db,
        project=project,
        event={
            "line_id": _uid(),
            "quotation_id": _uid(),
            "unit_price": Decimal("80.00"),
            "floor_value": Decimal("100.00"),
            "floor_level": "product",
        },
    )

    assert set(attempted) == {good_one, bad, good_two}, "it stopped at the first failure"
    assert sent == 2, "the two reachable managers must still be counted as notified"


def test_the_assistant_still_holds_the_real_entity_resolver():
    """A leaked stub reads as a production bug in somebody else's file.

    This module sorts after every `test_ai_*` file, so if one of them rebinds
    `resolve_references` without restoring it, this fails HERE with an obvious message instead
    of surfacing as "the resolver does not accept its own keyword arguments" three files later.
    """
    from app.services import ai_assistant_service, entity_resolver

    assert ai_assistant_service.resolve_references is entity_resolver.resolve_references, (
        "a test left a stubbed resolve_references installed on ai_assistant_service"
    )
