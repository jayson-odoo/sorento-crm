"""The staleness ladder (UAC Group H: AC-H3, AC-H4, AC-H6).

A project nobody has touched is the failure mode the client actually described: not a wrong
number in a report, but a development that quietly stopped being pursued while everybody
assumed somebody else was on it. This service decides when to say something, to whom, and
how loudly.

**Two triggers, in priority order (AC-H3).**

1. **An overdue next action.** The next action is derived -- the due date of the project's
   earliest open task -- so a project worked on yesterday that carries a task which was due
   three weeks ago is not idle, it is LATE. That is the primary trigger, because it is a
   promise somebody made and missed.
2. **Inactivity.** The backstop, for projects with no open task at all. Nobody promised
   anything, which is its own problem.

A project with an in-date open task is left alone regardless of how quiet it has been:
having a plan IS the work, and nagging somebody who has a site visit booked for Thursday is
how a tool teaches people to ignore it.

**One threshold, three rungs (AC-H6).** The rung's ``stale_after_days`` is the nudge point;
twice it warns the owner and copies management; three times marks the project Unattended.
Multiples rather than three separately configured numbers because an admin who tunes one
number should get a coherent ladder, not an ordering bug.

**Nothing here ever reassigns anything, and no rung changes anybody's permissions.** Level 3
changes what everyone can SEE: the badge is the signal a manager acts on. Asking to take a
project over (AC-C7's join request / dispute) is open at every rung -- it doubles as the
recourse for a registration this project blocked, and a blocked registrant cannot wait for
somebody else's project to go stale. A manager still decides, explicitly, with a reason, and
the history keeps the original registrant. An ownership change nobody chose is how a pipeline
tool loses the sales team.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.base import set_company_scope
from app.models.projects import OUTCOME_OPEN, Project
from app.models.status import Status

logger = logging.getLogger(__name__)

LEVEL_NONE = 0
LEVEL_NUDGE = 1
LEVEL_WARN = 2
LEVEL_UNATTENDED = 3

REASON_OVERDUE_TASK = "overdue_task"
REASON_NO_ACTIVITY = "no_activity"

# "Management" is defined once for the whole module, in project_notify_service (G20).


def _thresholds_by_status(db: Session) -> Dict[str, Optional[int]]:
    return {
        str(row[0]): row[1]
        for row in db.query(Status.id, Status.stale_after_days)
        .filter(Status.entity_type == "project")
        .all()
    }


def threshold_for(db: Session, *, project: Project) -> Optional[int]:
    """The rung's threshold in days, or None when this rung never goes stale.

    None is not "use a default": a terminal rung has nothing to chase, and an admin who
    cleared the number on a rung meant it.
    """
    if not project.status_id:
        return None
    row = (
        db.query(Status.stale_after_days)
        .filter(Status.id == str(project.status_id))
        .first()
    )
    return row[0] if row else None


def _level_for(days: int, threshold: int) -> int:
    if days >= threshold * 3:
        return LEVEL_UNATTENDED
    if days >= threshold * 2:
        return LEVEL_WARN
    if days >= threshold:
        return LEVEL_NUDGE
    return LEVEL_NONE


def evaluate(
    db: Session,
    *,
    project: Project,
    threshold: Optional[int] = None,
    next_action: Optional[Dict[str, Any]] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """What rung is this project on right now, and why.

    Pure read: computes, never writes. ``sweep`` owns the writing so the arithmetic can be
    tested without a transaction and reused by the list serializer.

    ``threshold`` and ``next_action`` are injectable so the sweep can resolve both in bulk
    for a thousand projects rather than per row.
    """
    blank = {"level": LEVEL_NONE, "reason": None, "since": None, "days": 0}

    # A decided project is not neglected. Checked on OUTCOME as well as the rung, because a
    # scope can be lost while the funnel position was never updated -- exactly the sort of
    # project this ladder would otherwise chase hardest.
    if project.outcome != OUTCOME_OPEN:
        return blank

    if threshold is None:
        threshold = threshold_for(db, project=project)
    if not threshold or threshold <= 0:
        return blank

    today = today or date.today()
    if next_action is None:
        from app.services.project_task_service import next_action_for_projects

        next_action = next_action_for_projects(db, [str(project.id)]).get(str(project.id), {})

    # 1. The promise somebody missed.
    due = (next_action or {}).get("next_action_date")
    if due:
        overdue_days = (today - due).days
        if overdue_days >= threshold:
            return {
                "level": _level_for(overdue_days, threshold),
                "reason": REASON_OVERDUE_TASK,
                "since": datetime.combine(due, datetime.min.time()),
                "days": overdue_days,
            }
        # An in-date task is a live plan: it takes the project off the ladder entirely
        # rather than deferring to the inactivity clock underneath.
        return blank

    # 2. The backstop: no open task carrying a date at all.
    if (next_action or {}).get("open_task_count") and not due:
        # Open work exists but nobody committed to a day for it. Fall through to
        # inactivity: "chase the PO, no date" is not a commitment, so the quiet still counts.
        pass

    anchor = project.last_meaningful_activity_at or project.created_at
    if anchor is None:
        return blank
    idle_days = (datetime.utcnow() - anchor).days
    level = _level_for(idle_days, threshold)
    if not level:
        return blank
    return {
        "level": level,
        "reason": REASON_NO_ACTIVITY,
        "since": anchor,
        "days": idle_days,
    }


def stale_dedup_key(project: Project, *, level: int) -> str:
    """One alert per project per rung per EPISODE of neglect.

    The key used to be `<project>:stale:<level>`, which reads as "do not send the same thing
    twice" but actually means "send the level-1 nudge at most once in this project's lifetime".
    A project that is chased back to life and then goes quiet again three months later is a NEW
    problem, and its nudge was being swallowed as a duplicate of the one from last quarter.

    The episode is the moment the project went quiet (`stale_since`, which the sweep stamps as
    the project steps onto the ladder), falling back to the activity anchor so the key is stable
    before that stamp exists. Repeated sweeps inside one episode therefore still dedupe, which
    is the thing the key was protecting against in the first place.
    """
    episode = (
        project.stale_since or project.last_meaningful_activity_at or project.created_at
    )
    stamp = episode.date().isoformat() if episode else "unknown"
    return f"{project.id}:stale:{level}:{stamp}"


def is_unattended(project: Project) -> bool:
    """AC-H6. The badge: this project is visibly neglected, and a manager should look at it.

    NOT a permission gate. Asking to take a project over (AC-C7's join request / dispute) is
    open at every rung, because it is also the recourse for a registration this project
    blocked -- and a blocked registrant cannot wait for somebody else's project to go stale.
    What level 3 changes is what everyone can SEE.
    """
    return int(project.stale_level or 0) >= LEVEL_UNATTENDED


# ------------------------------------------------------------------ the sweep


def sweep(db: Session, *, notify: bool = True) -> Dict[str, int]:
    """Walk every open project (plus anything still carrying a rung) and move each one up or
    off the ladder (AC-H5).

    Runs on the EXISTING scheduled-task heartbeat (`project_staleness_sweep`), so there is
    no new scheduler. Notifies only on a level CHANGE: a daily sweep that re-sends at the
    same rung every morning is how an alert becomes a filter rule.
    """
    summary = {"scanned": 0, "raised": 0, "cleared": 0, "unchanged": 0, "notified": 0}

    # Widen the company scope to ALL companies before reading anything.
    #
    # This is not optional bookkeeping: company scoping is fail-closed, and the scheduler
    # hands us a bare `SessionLocal()` whose scope is UNSET, which resolves to `false()`.
    # Without this line the sweep selects zero projects, stamps nothing, notifies nobody and
    # logs a perfectly healthy `scanned: 0` for ever. Every other background job in the
    # codebase does the same thing (`export_tasks`, `import_tasks`).
    #
    # All companies is the correct scope for a company-agnostic nightly job: the ladder is
    # per project, and a project belongs to exactly one company already.
    set_company_scope(db, None)

    # Open projects, PLUS any project still carrying a rung. The second half is not
    # bookkeeping: nothing else clears the ladder except a human posting an activity, so a
    # project that reached Unattended and was then won or lost kept `stale_level = 3` for ever
    # -- the list badge accused the team of neglecting the deal they had just won, and the
    # Unattended rung is the signal a manager acts on.
    #
    # `evaluate` already answers "not on the ladder" for a decided project, so these rows fall
    # out through the normal cleared path with no special case.
    projects: List[Project] = (
        db.query(Project)
        .filter(or_(Project.outcome == OUTCOME_OPEN, Project.stale_level > 0))
        .all()
    )
    if not projects:
        return summary

    thresholds = _thresholds_by_status(db)
    raised: List[Any] = []
    from app.services.project_task_service import next_action_for_projects

    next_actions = next_action_for_projects(db, [str(p.id) for p in projects])
    today = date.today()

    for project in projects:
        summary["scanned"] += 1
        result = evaluate(
            db,
            project=project,
            threshold=thresholds.get(str(project.status_id)),
            next_action=next_actions.get(str(project.id), {}),
            today=today,
        )
        was = int(project.stale_level or 0)
        now = int(result["level"])
        if now == was:
            summary["unchanged"] += 1
            continue

        project.stale_level = now
        project.stale_reason = result["reason"]
        # Keep the original entry moment across a climb: the useful fact is when the
        # project went quiet, not when the ladder last noticed.
        project.stale_since = result["since"] if now else None
        if now > was:
            summary["raised"] += 1
            raised.append((project, now, result))
        else:
            summary["cleared"] += 1

    # Commit the LADDER before attempting a single notification. The first real sweep proved
    # why: the recipient query raised, which poisoned the session, and this commit then died
    # with InFailedSqlTransaction -- so a broken mailer discarded forty correctly-identified
    # stale projects. State first, side effects second.
    db.commit()

    if notify:
        for project, level, result in raised:
            # Per-project try/rollback rather than one savepoint around the lot. A savepoint
            # is the wrong tool here because NotificationService commits internally, which
            # closes the nested transaction under it ("Can't operate on closed transaction
            # inside context manager"). Rolling back a poisoned session before the next
            # attempt gives the isolation the savepoint was reaching for, and the ladder is
            # already committed above so there is nothing left to lose.
            try:
                if _notify(db, project=project, level=level, result=result):
                    summary["notified"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "project staleness notify failed: project=%s level=%s (%s)",
                    project.id,
                    level,
                    exc,
                )
            finally:
                # Clears an aborted transaction left by a failed statement inside the
                # notification, so project two is not punished for project one.
                if not db.is_active:
                    db.rollback()

    logger.info("Project staleness sweep: %s", summary)
    return summary


def _message(project: Project, level: int, result: Dict[str, Any]) -> Dict[str, str]:
    days = result.get("days") or 0
    if result.get("reason") == REASON_OVERDUE_TASK:
        why = f"its next action is {days} days overdue"
    else:
        why = f"nobody has touched it for {days} days"

    if level == LEVEL_NUDGE:
        return {
            "title": f"{project.project_code} needs an update",
            "body": f"{project.title}: {why}. Log what happened, or set the next action.",
        }
    if level == LEVEL_WARN:
        return {
            "title": f"{project.project_code} is falling behind",
            "body": (
                f"{project.title}: {why}. Your manager has been copied on this one. "
                "Update it or hand it over."
            ),
        }
    return {
        "title": f"{project.project_code} is unattended",
        "body": (
            f"{project.title}: {why}. It is now flagged to everyone as unattended, and a "
            "colleague can ask to take it over. Nothing has been reassigned -- a manager decides."
        ),
    }


def _notify(db: Session, *, project: Project, level: int, result: Dict[str, Any]) -> bool:
    """Tell the owner, and management from level 2 up.

    Best-effort: the ladder state is already committed by the caller, and a notification
    backend that is down must not roll back a sweep that correctly identified 40 neglected
    projects. Same rule as every other post-state side effect in this codebase.
    """
    try:
        from app.services.notification_service import NotificationService

        text = _message(project, level, result)
        service = NotificationService(db)
        from app.services.project_notify_service import management_user_ids

        recipients = [project.owner_user_id] if project.owner_user_id else []
        if level >= LEVEL_WARN:
            recipients.extend(management_user_ids(db))

        sent = False
        for user_id in {r for r in recipients if r}:
            service.create_with_channel_preferences(
                user_id=str(user_id),
                type="project_stale",
                title=text["title"],
                body=text["body"],
                data={
                    "project_id": str(project.id),
                    "project_code": project.project_code,
                    "level": level,
                    "reason": result.get("reason"),
                },
                source_entity_type="project",
                source_entity_id=str(project.id),
                # One notification per project per rung, so a re-run after a crash mid-sweep
                # cannot double-send.
                dedup_key=stale_dedup_key(project, level=level),
                event_type="project_stale",
                send_in_app=True,
                send_email=level >= LEVEL_WARN,
            )
            sent = True
        return sent
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "project staleness notify failed: project=%s level=%s (%s)",
            project.id,
            level,
            exc,
        )
        return False
