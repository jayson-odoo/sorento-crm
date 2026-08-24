"""Integration tests for AutomationService._execute conditions_json filtering +
expiry-batch stamping (promotion-expiry trigger).

Mirrors tests/test_automation_service.py - runs against the Postgres dev DB,
isolated by direct-engine cleanup, no SMTP send. Covers:

  - a Sorento conditions_json (accessLevels contains_any [sorento_*] OR name
    contains "Sorento") keeps ONLY Sorento promos; Cabana promos are filtered out;
  - empty conditions_json -> all promos flow;
  - a match carrying no fact_sources / an unset trigger keeps all (covered by the
    empty-tree path - the promotion trigger always carries fact_sources);
  - stamp-first: kept promos get expiry_notified_at + a SHARED expiry_notify_batch_id
    before send; filtered-out promos are NOT stamped;
  - a re-run mints a FRESH batch id;
  - the grouped _send_grouped ctx carries batch_link + expiry_notify_batch_id
    (asserted via the rendered email body).
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta
from typing import Iterator

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.automation import Automation
from app.models.email_template import EmailTemplate
from app.models.marketing import Promotion
from app.models.notification import Notification, NotificationDelivery
from app.models.user import User
from app.services.sla_service import MALAYSIA_TZ


def _wipe():
    """Delete ONLY the rows this file creates. Runs BOTH before and after each
    test so a leftover active 7-day-expiry promo can't leak into another
    shared-DB test's match count (the promotion trigger matches by end_date,
    ignoring description).

    CRITICAL: every delete is SCOPED to this file's test rows. This DB is the
    local prod-copy dev DB (per CLAUDE.md) - an unscoped ``DELETE FROM
    automations`` here wipes the developer's real automations. Test automations
    are uniquely named with the ``(cond)`` marker; test promotions/templates use
    the ``CondPromo`` / ``tpl-cond-`` prefixes; notifications/runs are scoped by
    joining back to those automations."""
    from sqlalchemy import text

    from app.database import engine

    with engine.connect() as conn:
        # Scope notifications + deliveries to runs of THIS FILE's automations only.
        conn.execute(
            text(
                """
                DELETE FROM notification_deliveries WHERE notification_id IN (
                    SELECT id FROM notifications
                    WHERE source_entity_type = 'automation_run'
                      AND source_entity_id IN (
                          SELECT id FROM automation_runs WHERE automation_id IN (
                              SELECT id FROM automations WHERE name LIKE '%(cond)%'
                          )
                      )
                )
                """
            )
        )
        conn.execute(
            text(
                """
                DELETE FROM notifications
                WHERE source_entity_type = 'automation_run'
                  AND source_entity_id IN (
                      SELECT id FROM automation_runs WHERE automation_id IN (
                          SELECT id FROM automations WHERE name LIKE '%(cond)%'
                      )
                  )
                """
            )
        )
        conn.execute(
            text(
                "DELETE FROM automation_runs WHERE automation_id IN "
                "(SELECT id FROM automations WHERE name LIKE '%(cond)%')"
            )
        )
        conn.execute(text("DELETE FROM automations WHERE name LIKE '%(cond)%'"))
        conn.execute(text("DELETE FROM email_templates WHERE code LIKE 'tpl-cond-%'"))
        # Our CondPromo rows ONLY. Deleting another file's rows (the sibling's
        # 'Test Promo%') is forbidden under concurrent execution: on a separate
        # xdist worker that file is asserting on them right now. Isolation from
        # the sibling comes from the disjoint _UNIQUE_OFFSET date window instead.
        conn.execute(text("DELETE FROM promotions WHERE description LIKE 'CondPromo%'"))
        # Marked test users last (after their automations + notifications above).
        conn.execute(text("DELETE FROM users WHERE email LIKE 'condtest-%@test.local'"))
        conn.commit()


@pytest.fixture(autouse=True)
def _clean_state():
    _wipe()
    yield
    _wipe()


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


# The promotion-expiry trigger matches EVERY active promo whose end_date is
# exactly ``days_before`` out - including real promos on the shared prod-copy dev
# DB. Push this file's test promos ~10 years out (and the automation's target to
# match) so no real promo can ever collide with the assertions on match count.
#
# This value MUST stay disjoint from tests/test_automation_service.py's 3650 by
# more than the largest ``days_until_end`` either file uses (about 30), so the two
# files' expiry-matcher windows can never overlap when they run concurrently on
# separate xdist workers under ``--dist loadfile``.
_UNIQUE_OFFSET = 3950


def _malaysia_today():
    return datetime.now(MALAYSIA_TZ).date()


def _mk_template(db: Session) -> EmailTemplate:
    t = EmailTemplate(
        id=str(uuid.uuid4()),
        code=f"tpl-cond-{uuid.uuid4().hex[:8]}",
        name="Promo expiry reminder (cond)",
        subject="Expiring promos",
        body_html=(
            "<p>Hi {{ recipient.name }},</p>"
            "<ul>{% for p in promotions %}<li>{{ p.name }}</li>{% endfor %}</ul>"
            "<a href='{{ batch_link }}'>View batch {{ expiry_notify_batch_id }}</a>"
        ),
        body_text=None,
        is_active=True,
    )
    db.add(t)
    db.flush()
    return t


def _mk_promo(db: Session, *, name: str, access_levels: list[str], days_until_end: int) -> Promotion:
    today = _malaysia_today()
    p = Promotion(
        id=str(uuid.uuid4()),
        description=name,
        start_date=today - timedelta(days=3),
        end_date=today + timedelta(days=_UNIQUE_OFFSET + days_until_end),
        is_active=True,
        access_levels=access_levels,
    )
    db.add(p)
    db.flush()
    return p


def _mk_user(db: Session) -> User:
    """A marked test user so the executor has a system user to author the
    outgoing Notification rows. CI's Postgres starts empty (no seed users), so
    ``_resolve_owner_user_id`` would otherwise return None and ``_enqueue_email``
    would raise ``No system user available``. Email carries the ``condtest-``
    marker so ``_wipe`` can scope its cleanup."""
    u = User(
        id=str(uuid.uuid4()),
        email=f"condtest-{uuid.uuid4().hex[:8]}@test.local",
        name="Cond Test User",
        status="ACTIVE",
        is_trashed=False,
    )
    db.add(u)
    db.flush()
    return u


def _mk_automation(
    db: Session, *, template: EmailTemplate, conditions_json: dict | None, days_before: int = 7
) -> Automation:
    creator = _mk_user(db)
    a = Automation(
        id=str(uuid.uuid4()),
        name="Promo expiry (cond)",
        enabled=True,
        trigger_type="days_before_promotion_end",
        trigger_config={"days_before": _UNIQUE_OFFSET + days_before},
        action_type="send_email",
        email_template_id=str(template.id),
        recipient_config={
            "user_ids": [],
            "role_ids": [],
            "include_promotion_owner": False,
            "extra_emails": ["digest@example.com"],
        },
        conditions_json=conditions_json,
        group_matches=True,
        schedule_type="manual",
        run_time=time(9, 0),
        timezone="Asia/Kuala_Lumpur",
        created_by_user_id=str(creator.id),
    )
    db.add(a)
    db.flush()
    return a


def _no_smtp(monkeypatch):
    from app.services import notification_email
    import app.services.queue_service as queue_service

    monkeypatch.setattr(notification_email, "send_notification_email", lambda *a, **kw: None)
    monkeypatch.setattr(notification_email, "send_notification_email_multi", lambda *a, **kw: None)
    # Stub enqueue so the `notifications` queue's in-process immediate-drain
    # daemon thread is never spawned - otherwise a lingering drainer flips a
    # sibling shared-DB test's delivery rows pending -> queued (a known flake).
    # These tests assert on match/stamp/body, never on delivery status.
    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **kw: None)


_SORENTO_OR_NAME = {
    "kind": "group",
    "combinator": "or",
    "rules": [
        {
            "kind": "condition",
            "fact": "promotion.accessLevels",
            "operator": "contains_any",
            "valueKind": "literal",
            "value": ["sorento_dealer", "sorento_office"],
        },
        {
            "kind": "condition",
            "fact": "promotion.name",
            "operator": "contains",
            "valueKind": "literal",
            "value": "Sorento",
        },
    ],
}


def _sent_promotion_ids(db: Session, run_id: str) -> set[str]:
    notifs = (
        db.query(Notification)
        .filter(
            Notification.source_entity_type == "automation_run",
            Notification.source_entity_id == run_id,
        )
        .all()
    )
    ids: set[str] = set()
    for n in notifs:
        data = dict(getattr(n, "data") or {})
        ids.update(str(x) for x in (data.get("promotion_ids") or []))
    return ids


def test_conditions_filter_keeps_only_sorento(db, monkeypatch):
    from app.services.automation_service import AutomationService

    _no_smtp(monkeypatch)
    template = _mk_template(db)
    sorento_by_level = _mk_promo(db, name="CondPromo Sorento-by-level", access_levels=["sorento_dealer"], days_until_end=7)
    sorento_by_name = _mk_promo(db, name="CondPromo Sorento Special", access_levels=["cabana_dealer"], days_until_end=7)
    cabana = _mk_promo(db, name="CondPromo Cabana Clearout", access_levels=["cabana_dealer"], days_until_end=7)
    db.commit()

    automation = _mk_automation(db, template=template, conditions_json=_SORENTO_OR_NAME)
    db.commit()

    result = AutomationService(db).run_now(str(automation.id))
    assert result["status"] == "success"
    # Two Sorento promos kept (one by level, one by name); Cabana filtered out.
    assert result["summary"]["matches"] == 2

    sent = _sent_promotion_ids(db, result["run_id"])
    assert str(sorento_by_level.id) in sent
    assert str(sorento_by_name.id) in sent
    assert str(cabana.id) not in sent


def test_empty_conditions_keeps_all(db, monkeypatch):
    from app.services.automation_service import AutomationService

    _no_smtp(monkeypatch)
    template = _mk_template(db)
    p1 = _mk_promo(db, name="CondPromo All-A", access_levels=["sorento_dealer"], days_until_end=7)
    p2 = _mk_promo(db, name="CondPromo All-B", access_levels=["cabana_dealer"], days_until_end=7)
    db.commit()

    automation = _mk_automation(db, template=template, conditions_json=None)
    db.commit()

    result = AutomationService(db).run_now(str(automation.id))
    assert result["summary"]["matches"] == 2
    sent = _sent_promotion_ids(db, result["run_id"])
    assert {str(p1.id), str(p2.id)} <= sent


def test_stamp_first_shared_batch_only_on_kept(db, monkeypatch):
    from app.services.automation_service import AutomationService

    _no_smtp(monkeypatch)
    template = _mk_template(db)
    sorento = _mk_promo(db, name="CondPromo Sorento-Stamp", access_levels=["sorento_dealer"], days_until_end=7)
    cabana = _mk_promo(db, name="CondPromo Cabana-Stamp", access_levels=["cabana_dealer"], days_until_end=7)
    db.commit()

    automation = _mk_automation(db, template=template, conditions_json=_SORENTO_OR_NAME)
    db.commit()

    AutomationService(db).run_now(str(automation.id))

    db.expire_all()
    kept = db.query(Promotion).filter(Promotion.id == sorento.id).first()
    skipped = db.query(Promotion).filter(Promotion.id == cabana.id).first()

    assert kept.expiry_notify_batch_id is not None
    assert kept.expiry_notified_at is not None
    # Filtered-out promo is NOT stamped.
    assert skipped.expiry_notify_batch_id is None
    assert skipped.expiry_notified_at is None


def test_rerun_mints_fresh_batch_id(db, monkeypatch):
    from app.services.automation_service import AutomationService

    _no_smtp(monkeypatch)
    template = _mk_template(db)
    sorento = _mk_promo(db, name="CondPromo Sorento-Rerun", access_levels=["sorento_dealer"], days_until_end=7)
    db.commit()

    automation = _mk_automation(db, template=template, conditions_json=_SORENTO_OR_NAME)
    db.commit()

    AutomationService(db).run_now(str(automation.id))
    db.expire_all()
    first_batch = db.query(Promotion).filter(Promotion.id == sorento.id).first().expiry_notify_batch_id
    assert first_batch is not None

    AutomationService(db).run_now(str(automation.id))
    db.expire_all()
    second_batch = db.query(Promotion).filter(Promotion.id == sorento.id).first().expiry_notify_batch_id
    assert second_batch is not None
    assert second_batch != first_batch  # fresh batch on re-run


def test_grouped_ctx_carries_batch_link_and_id(db, monkeypatch):
    from app.services.automation_service import AutomationService

    _no_smtp(monkeypatch)
    template = _mk_template(db)
    sorento = _mk_promo(db, name="CondPromo Sorento-Ctx", access_levels=["sorento_dealer"], days_until_end=7)
    db.commit()

    automation = _mk_automation(db, template=template, conditions_json=_SORENTO_OR_NAME)
    db.commit()

    result = AutomationService(db).run_now(str(automation.id))
    db.expire_all()
    batch_id = db.query(Promotion).filter(Promotion.id == sorento.id).first().expiry_notify_batch_id

    notifs = (
        db.query(Notification)
        .filter(
            Notification.source_entity_type == "automation_run",
            Notification.source_entity_id == result["run_id"],
        )
        .all()
    )
    assert notifs
    body = str(dict(getattr(notifs[0], "data") or {}).get("body_html") or "")
    # The rendered body used {{ batch_link }} + {{ expiry_notify_batch_id }} - the
    # ctx must have carried both. batch_link ends with the batch id.
    assert str(batch_id) in body
    assert "expiry_notify_batch_id=" in body
