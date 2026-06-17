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

from datetime import datetime, timezone
from statistics import median
from typing import Any, Optional

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.models.sla import ConversationSLATracking, ConversationSLAEventLog
from app.models.user import User
from app.services.form_sla_service import FORM_SLA_TYPES


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
    conds = list(_scope_conditions(scope))
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
            func.sum(_response_met_expr()).label("resp_met"),
            func.sum(_response_breach_expr(now)).label("resp_breach"),
            func.sum(_resolution_met_expr()).label("reso_met"),
            func.sum(_resolution_breach_expr(now)).label("reso_breach"),
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

    return {
        "scope": scope,
        "opened": int(row.opened or 0),
        "responded": int(row.responded or 0),
        "resolved": int(row.resolved or 0),
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
            "assignee_name": names.get(r.uid) or "—",
            "total": int(r.total or 0),
            "resolved": int(r.resolved or 0),
            "avg_response_time_hours": round(float(r.avg_resp), 2) if r.avg_resp is not None else None,
            "avg_resolution_time_hours": round(float(r.avg_reso), 2) if r.avg_reso is not None else None,
            "breach_count": int((r.resp_breach or 0) + (r.reso_breach or 0)),
        }
        for r in rows
    ]


def kpi_tasks(db: Session, *, scope="all", date_from=None, date_to=None,
              entity_type=None, assignee_id=None, page=1, limit=25) -> dict[str, Any]:
    now = _now()
    conds = _base_filters(scope, date_from, date_to, entity_type, assignee_id)
    base = db.query(ConversationSLATracking).filter(*conds)
    total = base.count()
    rows = (
        base.order_by(ConversationSLATracking.initiated_at.desc())
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

    data = []
    for t in rows:
        e = esc_map.get(str(t.id), {})
        data.append({
            "tracking_id": str(t.id),
            "source_entity_type": t.source_entity_type,
            "source_entity_id": t.source_entity_id,
            "current_tier": t.current_tier,
            "assignee_id": t.assigned_to_id,
            "assignee_name": names.get(t.assigned_to_id) or "—",
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
