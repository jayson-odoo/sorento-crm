"""SLA KPI aggregations for the management dashboard (TCK-32).

Reads conversation_sla_tracking + conversation_sla_event_log. Scope partitions
conversation vs form SLA on source_entity_type. Met/breach is split per clock
(response vs resolution): response met <=> responded_at <= due_at (never-responded
past due = breach); resolution met <=> resolved_at <= due_at_resolution.

Aggregate scalars (counts, sums, met/breach) are computed set-based via SQL
case(); medians are computed in Python over a single windowed fetch (one query,
not N+1). escalation manual/auto split comes from event_log.trigger.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Optional

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.models.sla import ConversationSLATracking, ConversationSLAEventLog
from app.models.user import User
from app.services.form_sla_service import FORM_SLA_TYPES
from app.services.sla_scope import not_voided


def _scope_conditions(scope: str):
    """Filter conditions on ConversationSLATracking for the given scope."""
    if scope == "form":
        return [ConversationSLATracking.source_entity_type.in_(FORM_SLA_TYPES)]
    if scope == "conversation":
        return [
            or_(
                ConversationSLATracking.source_entity_type.is_(None),
                ConversationSLATracking.source_entity_type.notin_(FORM_SLA_TYPES),
            )
        ]
    return []  # all


def _parse(dt: Optional[str]) -> Optional[datetime]:
    if not dt:
        return None
    d = datetime.fromisoformat(str(dt).replace("Z", "+00:00"))
    if d.tzinfo is not None:
        d = d.astimezone(timezone.utc).replace(tzinfo=None)
    return d


def _base_filters(scope, date_from, date_to, entity_type, assignee_id):
    # Voided stages are out of EVERY dashboard number (UAC F4a). A stage cancelled
    # because the contact revised the form underneath it was never anyone's to miss:
    # counting it inflates the breach total on every revision. It keeps
    # `void_reason` so the exclusion is explainable rather than invisible, and the row
    # is still readable as history. One funnel - summary, leaderboard, tasks and trend
    # all come through here.
    conds = [not_voided()] + list(_scope_conditions(scope))
    df, dt = _parse(date_from), _parse(date_to)
    if df:
        conds.append(ConversationSLATracking.initiated_at >= df)
    if dt:
        conds.append(ConversationSLATracking.initiated_at <= dt)
    if entity_type:
        conds.append(ConversationSLATracking.source_entity_type == entity_type)
    if assignee_id:
        conds.append(ConversationSLATracking.assigned_to_id == assignee_id)
    return conds


def _now() -> datetime:
    return datetime.utcnow()


def _response_met_expr():
    return case(
        (and_(ConversationSLATracking.is_responded.is_(True),
              ConversationSLATracking.responded_at <= ConversationSLATracking.due_at), 1),
        else_=0,
    )


def _response_breach_expr(now):
    return case(
        (and_(ConversationSLATracking.is_responded.is_(True),
              ConversationSLATracking.responded_at > ConversationSLATracking.due_at), 1),
        (and_(ConversationSLATracking.is_responded.is_(False),
              ConversationSLATracking.due_at < now), 1),
        else_=0,
    )


def _resolution_met_expr():
    return case(
        (and_(ConversationSLATracking.is_resolved.is_(True),
              ConversationSLATracking.due_at_resolution.isnot(None),
              ConversationSLATracking.resolved_at <= ConversationSLATracking.due_at_resolution), 1),
        else_=0,
    )


def _resolution_breach_expr(now):
    return case(
        (and_(ConversationSLATracking.is_resolved.is_(True),
              ConversationSLATracking.due_at_resolution.isnot(None),
              ConversationSLATracking.resolved_at > ConversationSLATracking.due_at_resolution), 1),
        (and_(ConversationSLATracking.is_resolved.is_(False),
              ConversationSLATracking.due_at_resolution.isnot(None),
              ConversationSLATracking.due_at_resolution < now), 1),
        else_=0,
    )


def kpi_summary(db: Session, *, scope="all", date_from=None, date_to=None,
                entity_type=None, assignee_id=None) -> dict[str, Any]:
    now = _now()
    conds = _base_filters(scope, date_from, date_to, entity_type, assignee_id)

    row = (
        db.query(
            func.count(ConversationSLATracking.id).label("opened"),
            func.sum(case((ConversationSLATracking.is_responded.is_(True), 1), else_=0)).label("responded"),
            func.sum(case((ConversationSLATracking.is_resolved.is_(True), 1), else_=0)).label("resolved"),
            # MECE stage partition (each task lands in exactly one; resolved takes
            # priority so a resolve-without-recorded-response still sums correctly).
            func.sum(case((ConversationSLATracking.is_resolved.is_(True), 1), else_=0)).label("stage_resolved"),
            func.sum(case(
                (and_(ConversationSLATracking.is_resolved.is_(False),
                      ConversationSLATracking.is_responded.is_(True)), 1),
                else_=0,
            )).label("stage_responded_open"),
            func.sum(case(
                (and_(ConversationSLATracking.is_resolved.is_(False),
                      ConversationSLATracking.is_responded.is_(False)), 1),
                else_=0,
            )).label("stage_pending"),
            func.sum(_response_met_expr()).label("resp_met"),
            func.sum(_response_breach_expr(now)).label("resp_breach"),
            func.sum(_resolution_met_expr()).label("reso_met"),
            func.sum(_resolution_breach_expr(now)).label("reso_breach"),
            # Subset-scoped timeliness: among RESPONDED tasks, late = responded after due;
            # among RESOLVED tasks, late = resolved after resolution due. Denominator is
            # the subset (responded / resolved), not the whole population - distinct from
            # resp_met/resp_breach whose breach also counts never-responded-past-due.
            func.sum(case(
                (and_(ConversationSLATracking.is_responded.is_(True),
                      ConversationSLATracking.responded_at > ConversationSLATracking.due_at), 1),
                else_=0,
            )).label("resp_late"),
            func.sum(case(
                (and_(ConversationSLATracking.is_resolved.is_(True),
                      ConversationSLATracking.due_at_resolution.isnot(None),
                      ConversationSLATracking.resolved_at > ConversationSLATracking.due_at_resolution), 1),
                else_=0,
            )).label("reso_late"),
            # Open-work at-risk drilldown: within each OPEN stage, is it still within
            # its live clock (vs now) or already overdue but unfinished?
            # Pending (awaiting response) -> response clock (due_at).
            func.sum(case(
                (and_(ConversationSLATracking.is_resolved.is_(False),
                      ConversationSLATracking.is_responded.is_(False),
                      ConversationSLATracking.due_at.isnot(None),
                      ConversationSLATracking.due_at < now), 1),
                else_=0,
            )).label("pending_overdue"),
            # Responded-but-unresolved -> resolution clock (due_at_resolution).
            func.sum(case(
                (and_(ConversationSLATracking.is_resolved.is_(False),
                      ConversationSLATracking.is_responded.is_(True),
                      ConversationSLATracking.due_at_resolution.isnot(None),
                      ConversationSLATracking.due_at_resolution < now), 1),
                else_=0,
            )).label("responded_open_overdue"),
            func.avg(ConversationSLATracking.response_time).label("avg_resp"),
            func.avg(ConversationSLATracking.resolution_duration).label("avg_reso"),
        )
        .filter(*conds)
        .one()
    )

    # Medians (Python over a single windowed fetch).
    rt = [float(r[0]) for r in db.query(ConversationSLATracking.response_time)
          .filter(*conds, ConversationSLATracking.response_time.isnot(None)).all()]
    rd = [float(r[0]) for r in db.query(ConversationSLATracking.resolution_duration)
          .filter(*conds, ConversationSLATracking.resolution_duration.isnot(None)).all()]

    # Escalations split by trigger (join event log -> tracking in scope/window).
    esc_rows = (
        db.query(ConversationSLAEventLog.trigger, func.count(ConversationSLAEventLog.id))
        .join(ConversationSLATracking, ConversationSLAEventLog.sla_tracking_id == ConversationSLATracking.id)
        .filter(ConversationSLAEventLog.event_type == "escalation", *conds)
        .group_by(ConversationSLAEventLog.trigger)
        .all()
    )
    esc = {str(t or "auto"): int(c) for t, c in esc_rows}

    def pct(met, breach):
        d = (met or 0) + (breach or 0)
        return round(100.0 * (met or 0) / d, 1) if d else None

    opened = int(row.opened or 0)

    def pct_of_total(n):
        return round(100.0 * (n or 0) / opened, 1) if opened else None

    stage_pending = int(row.stage_pending or 0)
    stage_responded_open = int(row.stage_responded_open or 0)
    stage_resolved = int(row.stage_resolved or 0)

    responded = int(row.responded or 0)
    resolved = int(row.resolved or 0)
    responded_overdue = int(row.resp_late or 0)
    resolved_overdue = int(row.reso_late or 0)
    responded_within = int(row.resp_met or 0)
    resolved_within = int(row.reso_met or 0)

    # Open-work at-risk: within = stage subset minus the overdue rows (null-due rows
    # have no breach clock, so they count as on-track/within).
    pending_overdue = int(row.pending_overdue or 0)
    pending_within = stage_pending - pending_overdue
    responded_open_overdue = int(row.responded_open_overdue or 0)
    responded_open_within = stage_responded_open - responded_open_overdue

    def pct_of(n, d):
        return round(100.0 * (n or 0) / d, 1) if d else None

    return {
        "scope": scope,
        "opened": opened,
        "responded": responded,
        "resolved": resolved,
        # Subset-scoped timeliness drilldown: within-due vs overdue among the
        # responded / resolved subsets (MECE within each subset).
        "responded_within": responded_within,
        "responded_overdue": responded_overdue,
        "resolved_within": resolved_within,
        "resolved_overdue": resolved_overdue,
        "pct_responded_within": pct_of(responded_within, responded),
        "pct_resolved_within": pct_of(resolved_within, resolved),
        # Open-work at-risk drilldown (within live clock vs overdue-but-open).
        "pending_within": pending_within,
        "pending_overdue": pending_overdue,
        "responded_open_within": responded_open_within,
        "responded_open_overdue": responded_open_overdue,
        "pct_pending_within": pct_of(pending_within, stage_pending),
        "pct_responded_open_within": pct_of(responded_open_within, stage_responded_open),
        # MECE stage partition over the total (opened). Sums to opened.
        "stage_pending": stage_pending,
        "stage_responded_open": stage_responded_open,
        "stage_resolved": stage_resolved,
        "pct_stage_pending": pct_of_total(stage_pending),
        "pct_stage_responded_open": pct_of_total(stage_responded_open),
        "pct_stage_resolved": pct_of_total(stage_resolved),
        "escalated": sum(esc.values()),
        "escalated_auto": esc.get("auto", 0),
        "escalated_manual": esc.get("manual", 0),
        "response_met": int(row.resp_met or 0),
        "response_breach": int(row.resp_breach or 0),
        "resolution_met": int(row.reso_met or 0),
        "resolution_breach": int(row.reso_breach or 0),
        "pct_response_met": pct(row.resp_met, row.resp_breach),
        "pct_resolution_met": pct(row.reso_met, row.reso_breach),
        "avg_response_time_hours": round(float(row.avg_resp), 2) if row.avg_resp is not None else None,
        "avg_resolution_time_hours": round(float(row.avg_reso), 2) if row.avg_reso is not None else None,
        "median_response_time_hours": round(median(rt), 2) if rt else None,
        "median_resolution_time_hours": round(median(rd), 2) if rd else None,
    }


def kpi_leaderboard(db: Session, *, scope="all", date_from=None, date_to=None,
                    entity_type=None, limit=50) -> list[dict[str, Any]]:
    now = _now()
    conds = _base_filters(scope, date_from, date_to, entity_type, None)
    rows = (
        db.query(
            ConversationSLATracking.assigned_to_id.label("uid"),
            func.count(ConversationSLATracking.id).label("total"),
            func.sum(case((ConversationSLATracking.is_resolved.is_(True), 1), else_=0)).label("resolved"),
            func.avg(ConversationSLATracking.response_time).label("avg_resp"),
            func.avg(ConversationSLATracking.resolution_duration).label("avg_reso"),
            func.sum(_response_breach_expr(now)).label("resp_breach"),
            func.sum(_resolution_breach_expr(now)).label("reso_breach"),
        )
        .filter(*conds, ConversationSLATracking.assigned_to_id.isnot(None))
        .group_by(ConversationSLATracking.assigned_to_id)
        .order_by(func.count(ConversationSLATracking.id).desc())
        .limit(limit)
        .all()
    )
    uids = [r.uid for r in rows]
    names = {
        u.id: (u.name or u.email)
        for u in db.query(User).filter(User.id.in_(uids)).all()
    } if uids else {}
    return [
        {
            "assignee_id": r.uid,
            "assignee_name": names.get(r.uid) or "-",
            "total": int(r.total or 0),
            "resolved": int(r.resolved or 0),
            "avg_response_time_hours": round(float(r.avg_resp), 2) if r.avg_resp is not None else None,
            "avg_resolution_time_hours": round(float(r.avg_reso), 2) if r.avg_reso is not None else None,
            "breach_count": int((r.resp_breach or 0) + (r.reso_breach or 0)),
        }
        for r in rows
    ]


def _escalates_at_expr():
    """When the next auto-escalation clock expires for an OPEN tracker.

    Open + not-yet-responded -> the response clock (due_at) is what escalates.
    Open + responded, not resolved -> the resolution clock (due_at_resolution).
    Resolved -> NULL (nothing left to escalate). Mirrors the breach detection in
    sla_service.list_due_escalations; there is no stored "next escalation" column.
    """
    T = ConversationSLATracking
    return case(
        (T.is_resolved.is_(True), None),
        (T.is_responded.is_(False), T.due_at),
        else_=T.due_at_resolution,
    )


# FE column accessorKey -> sortable SQL. Computed keys (assignee_name, *_met,
# escalates_at) are handled specially in kpi_tasks; the rest map to a plain column.
_TASK_SORT_COLUMNS = {
    "source_entity_type": ConversationSLATracking.source_entity_type,
    "current_tier": ConversationSLATracking.current_tier,
    "current_tier_started_at": ConversationSLATracking.current_tier_started_at,
    "response_due": ConversationSLATracking.due_at,
    "resolution_due": ConversationSLATracking.due_at_resolution,
    "response_time_hours": ConversationSLATracking.response_time,
    "resolution_time_hours": ConversationSLATracking.resolution_duration,
}

_ESC_WINDOW_HOURS = {"1h": 1, "4h": 4, "24h": 24}


def _task_view_conditions(view: str, state: str, now):
    """Card-driven drilldown filters for the task list.

    view  -> which slice (mirrors the dashboard cards):
        all            : no extra filter
        responded      : is_responded (response clock; completed)
        resolved       : is_resolved   (resolution clock; completed)
        pending        : open, awaiting response (response clock vs now)
        responded_open : open, responded but unresolved (resolution clock vs now)
    state -> within | overdue | all, scoped to that view's clock. Within/overdue
    use the SAME predicates as the summary cards so list totals reconcile.
    """
    T = ConversationSLATracking
    conds: list = []
    if view == "responded":
        conds.append(T.is_responded.is_(True))
        if state == "within":
            conds.append(T.responded_at <= T.due_at)
        elif state == "overdue":
            conds.append(T.responded_at > T.due_at)
    elif view == "resolved":
        conds.append(T.is_resolved.is_(True))
        if state == "within":
            conds += [T.due_at_resolution.isnot(None), T.resolved_at <= T.due_at_resolution]
        elif state == "overdue":
            conds += [T.due_at_resolution.isnot(None), T.resolved_at > T.due_at_resolution]
    elif view == "pending":
        conds += [T.is_resolved.is_(False), T.is_responded.is_(False)]
        if state == "within":
            conds.append(or_(T.due_at.is_(None), T.due_at >= now))
        elif state == "overdue":
            conds += [T.due_at.isnot(None), T.due_at < now]
    elif view == "responded_open":
        conds += [T.is_resolved.is_(False), T.is_responded.is_(True)]
        if state == "within":
            conds.append(or_(T.due_at_resolution.is_(None), T.due_at_resolution >= now))
        elif state == "overdue":
            conds += [T.due_at_resolution.isnot(None), T.due_at_resolution < now]
    return conds


def kpi_tasks(db: Session, *, scope="all", date_from=None, date_to=None,
              entity_type=None, assignee_id=None, view="all", state="all",
              sort=None, dir="desc", esc_window="all",
              page=1, limit=25) -> dict[str, Any]:
    T = ConversationSLATracking
    now = _now()
    conds = _base_filters(scope, date_from, date_to, entity_type, assignee_id)
    conds += _task_view_conditions(view, state, now)

    esc_expr = _escalates_at_expr()
    # "Escalating by when" filter: restrict to OPEN trackers whose next-escalation
    # clock falls in the window. `overdue` = already past due (escalation imminent
    # / firing); Nh = due within the next N hours.
    if esc_window and esc_window != "all":
        conds += [T.is_resolved.is_(False), esc_expr.isnot(None)]
        if esc_window == "overdue":
            conds.append(esc_expr < now)
        elif esc_window in _ESC_WINDOW_HOURS:
            conds += [esc_expr >= now, esc_expr <= now + timedelta(hours=_ESC_WINDOW_HOURS[esc_window])]

    base = db.query(T).filter(*conds)
    total = base.count()

    # Sort: whitelisted column, computed expr, or joined assignee name. Falls back
    # to initiated_at desc. Deterministic tie-breaker on id keeps pagination stable.
    q = base
    order_col = None
    if sort == "assignee_name":
        q = q.outerjoin(User, T.assigned_to_id == User.id)
        order_col = func.coalesce(User.name, User.email)
    elif sort == "escalates_at":
        order_col = esc_expr
    elif sort == "response_met":
        order_col = _response_met_expr()
    elif sort == "resolution_met":
        order_col = _resolution_met_expr()
    elif sort in _TASK_SORT_COLUMNS:
        order_col = _TASK_SORT_COLUMNS[sort]

    if order_col is not None:
        primary = order_col.desc() if str(dir).lower() == "desc" else order_col.asc()
    else:
        primary = T.initiated_at.desc()
    rows = (
        q.order_by(primary, T.id.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    uids = [t.assigned_to_id for t in rows if t.assigned_to_id]
    names = {
        u.id: (u.name or u.email)
        for u in db.query(User).filter(User.id.in_(uids)).all()
    } if uids else {}
    # Per-task escalation split.
    tids = [t.id for t in rows]
    esc_map: dict[str, dict[str, int]] = {}
    if tids:
        for tid, trig, cnt in (
            db.query(ConversationSLAEventLog.sla_tracking_id, ConversationSLAEventLog.trigger, func.count(ConversationSLAEventLog.id))
            .filter(ConversationSLAEventLog.event_type == "escalation", ConversationSLAEventLog.sla_tracking_id.in_(tids))
            .group_by(ConversationSLAEventLog.sla_tracking_id, ConversationSLAEventLog.trigger)
            .all()
        ):
            esc_map.setdefault(str(tid), {})[str(trig or "auto")] = int(cnt)

    def _resp_met(t):
        return bool(t.is_responded and t.responded_at and t.due_at and t.responded_at <= t.due_at)

    def _reso_met(t):
        return bool(t.is_resolved and t.resolved_at and t.due_at_resolution and t.resolved_at <= t.due_at_resolution)

    def _iso(dt):
        return dt.isoformat() if dt is not None else None

    def _escalates_at(t):
        # Same rule as _escalates_at_expr, in Python for the payload.
        if t.is_resolved:
            return None
        return t.due_at if not t.is_responded else t.due_at_resolution

    data = []
    for t in rows:
        e = esc_map.get(str(t.id), {})
        data.append({
            "tracking_id": str(t.id),
            "source_entity_type": t.source_entity_type,
            "source_entity_id": t.source_entity_id,
            "current_tier": t.current_tier,
            "current_tier_started_at": _iso(t.current_tier_started_at),
            "response_due": _iso(t.due_at),
            "resolution_due": _iso(t.due_at_resolution),
            "escalates_at": _iso(_escalates_at(t)),
            "assignee_id": t.assigned_to_id,
            "assignee_name": names.get(t.assigned_to_id) or "-",
            "response_time_hours": float(t.response_time) if t.response_time is not None else None,
            "resolution_time_hours": float(t.resolution_duration) if t.resolution_duration is not None else None,
            "is_resolved": bool(t.is_resolved),
            "response_met": _resp_met(t),
            "resolution_met": _reso_met(t),
            "escalations_auto": e.get("auto", 0),
            "escalations_manual": e.get("manual", 0),
        })
    return {"data": data, "total": total, "page": page, "limit": limit}


def kpi_trend(db: Session, *, scope="all", date_from=None, date_to=None,
              entity_type=None, bucket="day") -> list[dict[str, Any]]:
    conds = _base_filters(scope, date_from, date_to, entity_type, None)
    day = func.date(ConversationSLATracking.initiated_at)
    rows = (
        db.query(
            day.label("bucket"),
            func.count(ConversationSLATracking.id).label("opened"),
            func.sum(case((ConversationSLATracking.is_resolved.is_(True), 1), else_=0)).label("resolved"),
        )
        .filter(*conds)
        .group_by(day)
        .order_by(day)
        .all()
    )
    return [
        {"bucket": str(r.bucket), "opened": int(r.opened or 0), "resolved": int(r.resolved or 0)}
        for r in rows
    ]
