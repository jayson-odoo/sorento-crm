"""Forecast and reporting maths (UAC Group I).

**Three numbers, never blended** (AC-I1). That is the whole design, and it is a reaction to
what the spreadsheets do today:

- **Pipeline** -- open quotations at their CURRENT version total, falling back to the
  registration estimate where nothing is quoted yet. Current version only: a revised
  quotation counted at every version would appear two or three times at different prices.
- **Weighted** -- pipeline times the per-status probability (AC-I2), tuned on the status
  record with no deploy. Project-level, so three scopes on one project share one percentage:
  the percentage describes how likely the PROJECT is to land.
- **Committed** -- recorded PO amounts. Won work is committed and NOT pipeline; counting it
  in both is the double-count that makes a forecast add up to more than the business.

Year bucketing applies to Committed by default (AC-I2a). Pipeline and Weighted are bucketed
too, but under their own keys, so a UI physically cannot stack a three-year-out guess on top
of banked revenue in one column. Projects with no derivable delivery year are reported under
``undated`` rather than dropped: dropped rows make the buckets disagree with the totals, and
the first person who adds up the columns stops trusting the report.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.projects import (
    OUTCOME_LOST,
    OUTCOME_WON,
    Project,
    ProjectPurchaseOrder,
    ProjectQuotation,
    ProjectQuotationVersion,
    ProjectSalesProfile,
    QUOTATION_OUTCOME_OPEN,
)
from app.models.status import Status

_CENTS = Decimal("0.01")
_HUNDRED = Decimal("100")
DEFAULT_DELIVERY_LAG_MONTHS = 30


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(_CENTS)


# ------------------------------------------------------------------ delivery year


def delivery_lag_months(db: Session) -> int:
    """AC-I3. DB -> default, the same resolution order the complaint notify tiers use."""
    from app.models.user import SystemSetting

    row = db.query(SystemSetting.project_delivery_lag_months).first()
    if row and row[0]:
        return int(row[0])
    return DEFAULT_DELIVERY_LAG_MONTHS


def delivery_year(
    db: Session, *, project: Project, lag_months: Optional[int] = None
) -> Optional[int]:
    """AC-I3. An explicit window WINS wherever set.

    Returns None when there is neither a window nor a launch date. Not "this year": bucketing
    an unknown into the current year is how a forecast quietly claims revenue it has no basis
    for at all.
    """
    profile = (
        db.query(ProjectSalesProfile)
        .filter(ProjectSalesProfile.project_id == project.id)
        .first()
    )
    if profile is None:
        return None
    if profile.expected_delivery_from:
        return profile.expected_delivery_from.year
    if profile.expected_delivery_to:
        return profile.expected_delivery_to.year
    if not profile.launch_date:
        return None

    months = lag_months if lag_months is not None else delivery_lag_months(db)
    launch: date = profile.launch_date
    total = launch.month - 1 + months
    return launch.year + total // 12


# ------------------------------------------------------------------- the numbers


def _open_quotation_totals(db: Session, project_ids: List[str]) -> Dict[str, Decimal]:
    """Per project: the sum of its OPEN quotations at their current version.

    Current is MAX(version_no) (AC-E3a), so this resolves it the same way every other reader
    does rather than trusting a pointer that does not exist.
    """
    if not project_ids:
        return {}

    highest = (
        db.query(
            ProjectQuotationVersion.quotation_id.label("quotation_id"),
            func.max(ProjectQuotationVersion.version_no).label("version_no"),
        )
        .group_by(ProjectQuotationVersion.quotation_id)
        .subquery()
    )
    rows = (
        db.query(
            ProjectQuotation.project_id,
            func.coalesce(func.sum(ProjectQuotationVersion.total_amount), 0),
        )
        .join(
            ProjectQuotationVersion,
            ProjectQuotationVersion.quotation_id == ProjectQuotation.id,
        )
        .join(
            highest,
            (highest.c.quotation_id == ProjectQuotationVersion.quotation_id)
            & (highest.c.version_no == ProjectQuotationVersion.version_no),
        )
        .filter(
            ProjectQuotation.project_id.in_(project_ids),
            ProjectQuotation.outcome == QUOTATION_OUTCOME_OPEN,
        )
        .group_by(ProjectQuotation.project_id)
        .all()
    )
    return {row[0]: _money(row[1]) for row in rows}


def _quoted_project_ids(db: Session, project_ids: List[str]) -> set:
    """Projects with ANY quotation, open or not.

    Used to decide whether the registration estimate still counts: once a project has been
    priced, the estimate is superseded, and adding both would count one project twice -- once
    as a guess and once as a price.
    """
    if not project_ids:
        return set()
    return {
        row[0]
        for row in db.query(ProjectQuotation.project_id)
        .filter(ProjectQuotation.project_id.in_(project_ids))
        .distinct()
        .all()
    }


def _committed_by_project(db: Session, project_ids: List[str]) -> Dict[str, Decimal]:
    if not project_ids:
        return {}
    rows = (
        db.query(
            ProjectPurchaseOrder.project_id,
            func.coalesce(func.sum(ProjectPurchaseOrder.po_amount), 0),
        )
        .filter(ProjectPurchaseOrder.project_id.in_(project_ids))
        .group_by(ProjectPurchaseOrder.project_id)
        .all()
    )
    return {row[0]: _money(row[1]) for row in rows}


def _probabilities(db: Session) -> Dict[str, Decimal]:
    """Per project-status win probability, clamped to 0..100.

    Clamped because a probability over 100 is a typo, and letting it through prints a
    weighted figure LARGER than the pipeline it came from, which discredits the whole report.
    """
    out: Dict[str, Decimal] = {}
    for row in (
        db.query(Status.id, Status.win_probability)
        .filter(Status.entity_type == "project")
        .all()
    ):
        if row[1] is None:
            continue
        percent = Decimal(row[1])
        out[row[0]] = min(max(percent, Decimal("0")), _HUNDRED)
    return out


def _live_projects(db: Session, company_id: str) -> List[Project]:
    """Everything not commercially closed.

    A lost or dormant project contributes nothing to any of the three numbers, and leaving it
    in would make the pipeline grow every time something is lost.
    """
    return (
        db.query(Project)
        .filter(
            Project.company_id == company_id,
            Project.outcome.notin_([OUTCOME_LOST]),
        )
        .all()
    )


def forecast(db: Session, *, company_id: str) -> Dict[str, Any]:
    """The three numbers plus their year buckets (AC-I1, AC-I2, AC-I2a)."""
    projects = _live_projects(db, company_id)
    ids = [p.id for p in projects]

    open_totals = _open_quotation_totals(db, ids)
    quoted = _quoted_project_ids(db, ids)
    committed = _committed_by_project(db, ids)
    probabilities = _probabilities(db)
    lag = delivery_lag_months(db)

    estimates: Dict[str, Decimal] = {}
    if ids:
        estimates = {
            row[0]: _money(row[1])
            for row in db.query(
                ProjectSalesProfile.project_id, ProjectSalesProfile.estimated_sales_value
            )
            .filter(ProjectSalesProfile.project_id.in_(ids))
            .all()
        }

    totals = {"pipeline": Decimal("0.00"), "weighted": Decimal("0.00"), "committed": Decimal("0.00")}
    buckets: Dict[int, Dict[str, Decimal]] = {}
    undated = {"pipeline": Decimal("0.00"), "weighted": Decimal("0.00"), "committed": Decimal("0.00")}

    for project in projects:
        pipeline = open_totals.get(project.id)
        if pipeline is None:
            # Nothing OPEN. The estimate only stands in for a project that was never priced
            # at all -- a fully-decided project is committed, not pipeline.
            pipeline = Decimal("0.00") if project.id in quoted else estimates.get(project.id, Decimal("0.00"))

        percent = probabilities.get(project.status_id or "", Decimal("0"))
        weighted = (pipeline * percent / _HUNDRED).quantize(_CENTS)
        banked = committed.get(project.id, Decimal("0.00"))

        totals["pipeline"] += pipeline
        totals["weighted"] += weighted
        totals["committed"] += banked

        year = delivery_year(db, project=project, lag_months=lag)
        target = undated if year is None else buckets.setdefault(
            year,
            {"pipeline": Decimal("0.00"), "weighted": Decimal("0.00"), "committed": Decimal("0.00")},
        )
        target["pipeline"] += pipeline
        target["weighted"] += weighted
        target["committed"] += banked

    return {
        "pipeline": totals["pipeline"].quantize(_CENTS),
        "weighted": totals["weighted"].quantize(_CENTS),
        "committed": totals["committed"].quantize(_CENTS),
        "project_count": len(projects),
        "by_year": [
            {"year": year, **{k: v.quantize(_CENTS) for k, v in values.items()}}
            for year, values in sorted(buckets.items())
        ],
        "undated": {k: v.quantize(_CENTS) for k, v in undated.items()},
    }


# ----------------------------------------------------------------- conversion


def conversion(db: Session, *, company_id: str) -> Dict[str, Any]:
    """AC-I5. Outcomes rolled to projects, so a partial win is not a full win.

    The denominator is DECIDED projects only. A project still being quoted is not a loss, and
    including it would make the rate improve simply by finishing things.

    ``rate`` is None rather than 0 with nothing decided: 0% says we lose everything, which is
    a different and much worse claim than "we have not finished anything yet".
    """
    rows = (
        db.query(Project.outcome, func.count(Project.id))
        .filter(Project.company_id == company_id)
        .group_by(Project.outcome)
        .all()
    )
    counts = {row[0]: int(row[1]) for row in rows}
    won = counts.get(OUTCOME_WON, 0)
    lost = counts.get(OUTCOME_LOST, 0)
    decided = won + lost
    rate = (
        (Decimal(won) / Decimal(decided) * _HUNDRED).quantize(_CENTS) if decided else None
    )
    return {
        "won": won,
        "lost": lost,
        "decided": decided,
        "open": sum(count for outcome, count in counts.items() if outcome not in (OUTCOME_WON, OUTCOME_LOST)),
        "rate": rate,
    }


def loss_reason_counts(db: Session, *, company_id: str) -> List[Dict[str, Any]]:
    """AC-I4. Counted on the QUOTATION, where the reason is actually recorded, so a project
    that lost two scopes for two different reasons reports both."""
    from app.services.project_quotation_service import loss_reasons

    labels = {row["value"]: row["label"] for row in loss_reasons(db)}
    rows = (
        db.query(ProjectQuotation.loss_reason, func.count(ProjectQuotation.id))
        .join(Project, Project.id == ProjectQuotation.project_id)
        .filter(
            Project.company_id == company_id,
            ProjectQuotation.loss_reason.isnot(None),
        )
        .group_by(ProjectQuotation.loss_reason)
        .order_by(func.count(ProjectQuotation.id).desc())
        .all()
    )
    return [
        {"reason": row[0], "label": labels.get(row[0], row[0]), "count": int(row[1])}
        for row in rows
    ]


def by_salesperson(db: Session, *, company_id: str) -> List[Dict[str, Any]]:
    """AC-I4. The same three numbers per owner, so the rows add up to the headline.

    Computed by re-running the per-project maths rather than with a second SQL shape: two
    implementations of the same arithmetic drift, and the version management reads is the one
    that must not.
    """
    from app.models.user import User

    projects = _live_projects(db, company_id)
    ids = [p.id for p in projects]
    open_totals = _open_quotation_totals(db, ids)
    quoted = _quoted_project_ids(db, ids)
    committed = _committed_by_project(db, ids)
    probabilities = _probabilities(db)

    estimates: Dict[str, Decimal] = {}
    if ids:
        estimates = {
            row[0]: _money(row[1])
            for row in db.query(
                ProjectSalesProfile.project_id, ProjectSalesProfile.estimated_sales_value
            )
            .filter(ProjectSalesProfile.project_id.in_(ids))
            .all()
        }

    per_owner: Dict[str, Dict[str, Any]] = {}
    for project in projects:
        owner = project.owner_user_id or ""
        row = per_owner.setdefault(
            owner,
            {
                "owner_user_id": owner or None,
                "owner_name": None,
                "project_count": 0,
                "pipeline": Decimal("0.00"),
                "weighted": Decimal("0.00"),
                "committed": Decimal("0.00"),
            },
        )
        pipeline = open_totals.get(project.id)
        if pipeline is None:
            pipeline = Decimal("0.00") if project.id in quoted else estimates.get(project.id, Decimal("0.00"))
        percent = probabilities.get(project.status_id or "", Decimal("0"))

        row["project_count"] += 1
        row["pipeline"] += pipeline
        row["weighted"] += (pipeline * percent / _HUNDRED).quantize(_CENTS)
        row["committed"] += committed.get(project.id, Decimal("0.00"))

    owner_ids = [oid for oid in per_owner if oid]
    if owner_ids:
        for user in db.query(User).filter(User.id.in_(owner_ids)).all():
            per_owner[user.id]["owner_name"] = user.name or user.email

    return sorted(
        (
            {**row, **{k: row[k].quantize(_CENTS) for k in ("pipeline", "weighted", "committed")}}
            for row in per_owner.values()
        ),
        key=lambda row: row["pipeline"],
        reverse=True,
    )
