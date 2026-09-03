"""Fulfilment Priority: one policy, used at both moments it applies.

AC-H5 says the ranking that decides what goes on a container and the ranking that decides which
purchase-order line a shipment draws down are the SAME policy, and that two policies for the two
moments is a defect. That is easy to say and easy to lose: the Loading Plan grew its factor
assembly privately, and the allocation suggestion would have grown its own beside it. Two
implementations agreeing today is not the same as one implementation, and the day they disagree
is the day a planner is told two different things about the same purchase order.

So the assembly lives here, and both callers import it. The generic scorer (`rank_score`,
`Factor`) stays in `cash_ranking`; this module is the SCM-specific part - which factors exist,
where their values come from, and how a purchase order's demand class is resolved.

The factors:

  * `po_document_sequence` - the order the buyer already reads off the list. Sequence, not date:
    two orders raised the same day still have an order.
  * `demand_class`      - project versus dealer, resolved through the SO<->PO claim.
  * `need_by_date`      - sooner is higher.
  * `document_age`      - older document is higher, which is the same helper read the other way.
  * `customer_credit`   - shorter payment terms are higher. Only a SALES-ORDER demand row can
    carry it (see `factors_for_demand_rows`); a purchase-order candidate never does.

Every factor degrades gracefully: a value we do not have is ABSENT, not zero. `rank_score`
divides by the weight of the factors actually present, so an absent factor lowers nobody's score
- it just stops being part of the comparison. Demand is the one place where "nothing" is a real
value rather than a gap: no claimed sales order behind a purchase order is a demand of 0.0 and
PRESENT, because a purchase order owed to a customer has to be able to outrank one owed to
nobody. Only a resolved class the policy does not weight is absent (see `demand_value`).

**Two shapes, one policy.** `factors_for_candidates` assembles a PURCHASE-ORDER candidate
(`po_line_id`, `po_number`, `expected_date`, `po_date`, class through `scm.order_link_claim`).
`factors_for_demand_rows` assembles a SALES-ORDER demand row, which has no purchase order behind
it at all. They are siblings on purpose: forcing sales-order demand through the PO-shaped
signature would mean inventing a `po_line_id`, which is exactly the two-implementations defect
this module exists to prevent. What they SHARE is the part that must never fork - the policy row,
`rank_score`, and the absent-is-dropped rule.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.scm import PriorityPolicy, ReorderRun
from app.services.error_handler import AppException
from app.services.scm.cash_ranking import Factor, rank_score

#: The factor keys a policy may weight. Adding a fifth is a row in `scm.priority_policy.factors`
#: plus a value here; it is never a schema change (AC-H6 applies the same rule to demand classes).
FACTOR_KEYS = (
    "po_document_sequence",
    "demand_class",
    "need_by_date",
    "document_age",
    "customer_credit",
)

#: What a policy-less database ranks by. Sequence only: with no policy row the tenant has said
#: nothing about what demand is worth, so the fallback ranks by the order the buyer already
#: reads off the list rather than inventing a weighting.
DEFAULT_WEIGHTS = {"po_document_sequence": 1.0}

#: What migration 374 seeds as the active policy, and what a fresh install seeds directly (311).
#: Here so tests and the PR can quote one source. With demand at 3.0 against sequence at 1.0 the
#: score bands do not overlap: project [0.75, 1.0], retail [0.30, 0.55], nothing owed [0, 0.25].
#: So a line owed to a customer always outranks one owed to nobody, and document sequence orders
#: the lines inside each band. The migrations keep the literals rather than importing this, so
#: they stay standalone; changing one means changing both.
SEEDED_WEIGHTS = {
    "po_document_sequence": 1.0,
    "demand_class": 3.0,
    "need_by_date": 0.0,
    "document_age": 0.0,
}

#: What each resolved demand class is worth, seeded alongside `SEEDED_WEIGHTS`.
SEEDED_CLASS_WEIGHTS = {"project": 1.0, "retail": 0.4}

#: The policy migration 385 seeds and switches on, after the captain asked for "a fair policy".
#:
#: The rule it replaces weighted `po_document_sequence` alone, which no sales-order line can
#: carry, so every board row scored 0.00 and the ranking ranked nothing. This one weights what
#: a demand row actually has - and keeps what the purchase-order path already relied on, because
#: ONE policy serves three moments and a change made for the board reaches container loading:
#:
#:   * `need_by_date` 3.0   - the captain's "delivery date", and the strongest voice. It
#:                              outweighs document age and credit together, so a sooner
#:                              delivery wins even against an older document from a prompter
#:                              payer.
#:   * `demand_class` 3.0   - KEPT at what migration 374 deliberately switched on. On the
#:                              board it separates nothing (every row is project-class by
#:                              construction) and only shifts every score by the same amount;
#:                              on the purchase-order path it is what keeps a line owed to a
#:                              customer ahead of one owed to nobody.
#:   * `document_age` 1.0   - the captain's "document date", older first.
#:   * `customer_credit` 1.0 - shorter payment terms first. Absent for a purchase-order
#:                              candidate, and absent for a customer nobody has assessed, which
#:                              in both cases means DROPPED from the average rather than zeroed.
#:   * `po_document_sequence` 1.0 - the buyer's original rule, kept as the tie-break it always
#:                              should have been. Absent on every board row, so it costs the
#:                              board nothing.
#:
#: Reversible by flipping back: the migration leaves the previous row present and inactive.
FAIR_POLICY_NAME = "Fair fulfilment priority (delivery date, document date, customer credit)"
FAIR_WEIGHTS = {
    "po_document_sequence": 1.0,
    "demand_class": 3.0,
    "need_by_date": 3.0,
    "document_age": 1.0,
    "customer_credit": 1.0,
}
FAIR_CLASS_WEIGHTS = {"project": 1.0, "retail": 0.4}

#: The named what-if the fulfilment board offers (PLAN 13.5, recommendation 3 then 2).
#:
#: It is NOT a second active policy - the partial unique index allows exactly one, and two
#: policies for two moments is the defect this module prevents. It is a weighting a planner may
#: ask the board to RANK BY so the captain can see what a fairer rule would do to real orders
#: before anybody switches it on. A previewed ranking is labelled and is never persisted.
#:
#: Weighted only on what a sales-order demand row can carry. `demand_class` stays at zero on
#: purpose: every board row is project-class by construction, so weighting it adds a constant to
#: every score and separates nothing.
BOARD_PREVIEW_NAME = "Fulfilment board preview (delivery date, document date, customer credit)"
BOARD_PREVIEW_WEIGHTS = {
    "po_document_sequence": 0.0,
    "demand_class": 0.0,
    "need_by_date": 3.0,
    "document_age": 1.0,
    "customer_credit": 1.0,
}
BOARD_PREVIEW_CLASS_WEIGHTS = dict(SEEDED_CLASS_WEIGHTS)


def active_policy(db: Session) -> Optional[PriorityPolicy]:
    """The one active policy, or None. A partial unique index makes "one" true at the DB level."""
    return (
        db.query(PriorityPolicy)
        .filter(PriorityPolicy.is_active.is_(True))
        .order_by(PriorityPolicy.created_at)
        .first()
    )


def policy_by_name(db: Session, name: str) -> Optional[PriorityPolicy]:
    """A policy by name, ACTIVE OR NOT.

    The preview reads an inactive row (13.5): a what-if has to be readable without being
    switched on, or asking "what would this do" means activating it for container loading and
    stock assignment as well.
    """
    if not name:
        return None
    return (
        db.query(PriorityPolicy)
        .filter(PriorityPolicy.name == name)
        .order_by(PriorityPolicy.created_at)
        .first()
    )


def policy_weights(policy: Optional[PriorityPolicy]) -> tuple[dict, dict]:
    """`(factor weights, demand-class weights)` for a policy, or the documented default."""
    if policy is None:
        return dict(DEFAULT_WEIGHTS), {}
    return dict(policy.factors or {}), dict(policy.demand_class_weights or {})


# --------------------------------------------------------------------------- #
# Fulfilment policy admin (PLAN-demo-followups-19aug-ladder-v2.md C1/C2)
# --------------------------------------------------------------------------- #

#: The date every install starts its TBA line on. Mirrors the literal migration 443 seeds as
#: `server_default`, kept here (not imported) for the same "migrations stay standalone"
#: reason 385 states.
DEFAULT_TBA_DATE_FROM = date(2029, 1, 1)

#: What `reorder_coverage_until` / `tba_date_from` / `transfer_days` answer for a
#: policy-less database. `reorder_coverage_until` defaults to None - a fresh install has no
#: coverage limit set, never a guessed date. `tba_date_from` cannot default to None: the
#: column is NOT NULL and "no TBA line" would let a 2030 placeholder compete for real stock.
#: `transfer_days` is 0 (31 Aug ruling, R-B): the flat 2-day transfer charge
#: `front_planning_engine.TRANSFER_DAYS` used to hard-code is retired, and an unconfigured
#: install charges nothing rather than guessing a number nobody set.
#: The site pool's share step defaults (fulfilment feedback batch, S1, 2 Sep ruling R-B,
#: migration 460): a database that never set them charges 50% kept for dealers with a
#: 30-day immediate window, the values the plan documents.
#: The overdue grace defaults (R-O, 3 Sep 2026, migration 464): a late document counts as
#: supply landing 14 days out, and one more than 90 days late counts as nothing (R31 kept
#: for the dead).
FULFILMENT_SETTINGS_DEFAULTS = {
    "reorder_coverage_until": None,
    "tba_date_from": DEFAULT_TBA_DATE_FROM,
    "transfer_days": 0,
    "immediate_window_days": 30,
    "pool_share_pct": 50,
    "overdue_grace_days": 14,
    "overdue_dead_days": 90,
}

#: What the admin screen shows when NO policy has ever been activated (a database that
#: predates migration 385, or a blank test schema). The seeded "fair" weights, not the bare
#: `DEFAULT_WEIGHTS` sequence-only fallback `policy_weights` gives the engine - a planner
#: opening this screen for the first time should see what a fresh install would actually be
#: ranking by, not an empty policy nobody chose.
_NO_POLICY_NAME = "Fulfilment priority (no policy activated yet)"


def fulfilment_settings(policy: Optional[PriorityPolicy]) -> dict:
    """`{reorder_coverage_until, tba_date_from, transfer_days, immediate_window_days,
    pool_share_pct, overdue_grace_days, overdue_dead_days}` for a policy, or the documented
    default.

    A sibling of `policy_weights` for the ladder's calendar dates and its transfer charge:
    one place reads them off the active row, so the admin screen and the engine cannot come
    to different views of how far purchasing covers, where TBA starts, what a bin
    transfer costs, and how much of the site pool a project line may share. Every numeric
    field is read None-safe - a row written before its migration (or a database still
    mid-migration on another branch) reads the documented default rather than raising.
    """
    if policy is None:
        return dict(FULFILMENT_SETTINGS_DEFAULTS)
    return {
        "reorder_coverage_until": policy.reorder_coverage_until,
        "tba_date_from": policy.tba_date_from or DEFAULT_TBA_DATE_FROM,
        "transfer_days": (
            int(policy.transfer_days) if policy.transfer_days is not None else 0
        ),
        "immediate_window_days": (
            int(policy.immediate_window_days)
            if policy.immediate_window_days is not None
            else FULFILMENT_SETTINGS_DEFAULTS["immediate_window_days"]
        ),
        "pool_share_pct": (
            int(policy.pool_share_pct)
            if policy.pool_share_pct is not None
            else FULFILMENT_SETTINGS_DEFAULTS["pool_share_pct"]
        ),
        "overdue_grace_days": (
            int(policy.overdue_grace_days)
            if getattr(policy, "overdue_grace_days", None) is not None
            else FULFILMENT_SETTINGS_DEFAULTS["overdue_grace_days"]
        ),
        "overdue_dead_days": (
            int(policy.overdue_dead_days)
            if getattr(policy, "overdue_dead_days", None) is not None
            else FULFILMENT_SETTINGS_DEFAULTS["overdue_dead_days"]
        ),
    }


def plan_link_horizon(db: Session, *, run_id: Optional[str] = None) -> Optional[date]:
    """How far out the reorder plan planned - and therefore how far out a link may reach.

    `PLAN-scm-oi-handshake.md` section 11 (captain, 27 Aug 2026). Every path that ties a
    document to an order-inquiry row takes a date to link up to, and the one a caller that
    names none falls back to is THIS: the reorder run's own "Plan until"
    (`scm.reorder_run.plan_horizon_date`), the date its netting stopped at.

    NOT `scm.priority_policy.reorder_coverage_until`, which this read until S2 of the
    27 August review corrected it. That field is the ladder's BUY-NOW line - "a line
    required AFTER this date is proposed Buy now" (`front_planning_engine`, and the
    column's own comment) - so the rows beyond it are exactly the ones the engine ordered
    bought, and using it as the link horizon meant the purchase order raised FOR those
    rows could never be linked BACK to them. The two dates say opposite things about the
    same rows; `reorder_coverage_until` is left alone, doing its own job.

    `run_id` names the run a caller is answering for - a purchase-order confirm knows the
    run its draft was drafted off, and that run's horizon is the one the buy was sized
    under, not whatever has planned since. An unknown run falls back to the ladder below,
    so one place answers "which date" however the caller arrived.

    Otherwise: the LATEST COMPLETED run for the company. Latest, because that is the plan
    in force; completed, because a run still going has produced nothing to buy to and a
    failed one produced nothing at all. Its own `plan_horizon_date` is taken as it stands,
    NULL included - a run that named no horizon planned every open line, so no horizon is
    in force, and reaching back to an older run's date would link to a horizon nobody is
    planning to any more.

    `None` when no run has ever completed. That is "no horizon is in force", not "guess
    one": a fresh install has never been asked how far out it plans, and inventing a date
    would refuse links nobody asked to have refused.
    """
    if run_id:
        named = db.query(ReorderRun).filter(ReorderRun.id == str(run_id)).first()
        if named is not None:
            return named.plan_horizon_date
    latest = (
        db.query(ReorderRun)
        .filter(ReorderRun.status == "completed")
        # The same ordering `reorder_run_service` lists runs by. `id` last because every
        # row of one transaction shares one `now()`, so `created_at` can tie.
        .order_by(
            func.coalesce(ReorderRun.finished_at, ReorderRun.created_at).desc(),
            ReorderRun.created_at.desc(),
            ReorderRun.id.desc(),
        )
        .first()
    )
    return latest.plan_horizon_date if latest is not None else None


def fulfilment_priority_as_dict(policy: Optional[PriorityPolicy]) -> dict:
    """The admin screen's whole answer for one policy row: weights, class weights and the
    ladder-v2 settings - in the shape `FulfilmentPriorityPolicy` serialises. Shared by the GET
    route and by the response built after a PUT writes a new revision, so the two can never
    format a row differently."""
    if policy is None:
        weights, class_weights = dict(FAIR_WEIGHTS), dict(FAIR_CLASS_WEIGHTS)
    else:
        weights, class_weights = policy_weights(policy)
    return {
        "name": policy.name if policy is not None else _NO_POLICY_NAME,
        "factors": weights,
        "demand_class_weights": class_weights,
        **fulfilment_settings(policy),
        "exists": policy is not None,
    }


def create_revision(
    db: Session,
    *,
    name: str,
    factors: Mapping[str, float],
    demand_class_weights: Mapping[str, float],
    reorder_coverage_until: Optional[date],
    tba_date_from: Optional[date] = None,
    transfer_days: Optional[int] = None,
    immediate_window_days: Optional[int] = None,
    pool_share_pct: Optional[int] = None,
    overdue_grace_days: Optional[int] = None,
    overdue_dead_days: Optional[int] = None,
    notes: Optional[str] = None,
) -> PriorityPolicy:
    """Write a NEW policy revision and activate it. Never mutates an old row.

    The `PriorityPolicy` docstring is explicit that history matters here - a planner is
    judged against what the board ranked by at the time, so a save that rewrote the active
    row in place would let that answer change retroactively under them. The partial unique
    index (`uq_scm_priority_policy_one_active`) allows exactly one active row, so the old one
    is deactivated in the SAME flush that activates the new one - the moment between the two
    statements never has zero or two active rows for another request to observe as this
    session's own uncommitted work, and the caller's `db.commit()` makes it durable.

    Two concurrent PUTs are the case that matters: without a lock, both could read the same
    active row, both UPDATE it false, and both INSERT a new active row, with the second
    INSERT losing to `uq_scm_priority_policy_one_active` as an unhandled `IntegrityError` -
    an ugly 500 for what is really "you and someone else saved at the same time". The active
    row is SELECTed FOR UPDATE first so the second PUT blocks behind the first's commit
    instead of racing it. That lock has nothing to hold when no row is active at all (a
    fresh install, or the sliver of time between one transaction's UPDATE and its INSERT),
    so the insert is wrapped in a savepoint too: any `IntegrityError` there is caught and
    turned into a 409 asking the caller to reload, never a 500.

    Flushes but does not commit - the caller (the PUT route) commits, so a mid-transaction
    failure elsewhere in the same request leaves no half-activated revision.
    """
    db.execute(text("SELECT id FROM scm.priority_policy WHERE is_active FOR UPDATE"))
    db.execute(text("UPDATE scm.priority_policy SET is_active = false WHERE is_active"))
    revision = PriorityPolicy(
        name=name,
        is_active=True,
        factors=dict(factors),
        demand_class_weights=dict(demand_class_weights),
        reorder_coverage_until=reorder_coverage_until,
        tba_date_from=tba_date_from or DEFAULT_TBA_DATE_FROM,
        transfer_days=transfer_days if transfer_days is not None else 0,
        immediate_window_days=(
            immediate_window_days
            if immediate_window_days is not None
            else FULFILMENT_SETTINGS_DEFAULTS["immediate_window_days"]
        ),
        pool_share_pct=(
            pool_share_pct
            if pool_share_pct is not None
            else FULFILMENT_SETTINGS_DEFAULTS["pool_share_pct"]
        ),
        overdue_grace_days=(
            overdue_grace_days
            if overdue_grace_days is not None
            else FULFILMENT_SETTINGS_DEFAULTS["overdue_grace_days"]
        ),
        overdue_dead_days=(
            overdue_dead_days
            if overdue_dead_days is not None
            else FULFILMENT_SETTINGS_DEFAULTS["overdue_dead_days"]
        ),
        notes=notes,
    )
    savepoint = db.begin_nested()
    try:
        db.add(revision)
        db.flush()
        savepoint.commit()
    except IntegrityError as exc:
        savepoint.rollback()
        raise AppException(
            status_code=409,
            message=(
                "The fulfilment priority policy changed under you. Reload the page and "
                "try again."
            ),
            code="scm_priority_policy_conflict",
        ) from exc
    return revision


def save_fulfilment_priority(db: Session, body) -> PriorityPolicy:
    """The whole of what a `PUT /policies/fulfilment-priority` means, in the service layer.

    The router used to hold this: it read the active revision, applied the TBA freshness
    rule against it and called `create_revision`. That is business logic in an HTTP handler,
    which the layering rule forbids (a router does HTTP and Pydantic and nothing else), and
    it also put the one rule that needs BOTH the submitted value and the active one in the
    only place neither the sheet nor a test can reach without a TestClient.

    **The TBA rule is about MOVING THE LINE BACK, not about the value** (AC-S1-2 as
    corrected 30 Aug). A date in the past turns every open order into a placeholder - every
    line dated on or after it stops taking supply - so a CHANGE to a past date is refused.
    An UNCHANGED resubmission of a date that has quietly passed is not that move, and
    refusing it locked the whole panel: the screen sends the record back whole, so no
    weight, no coverage date and no class weight could be saved again until somebody also
    picked a new TBA date.

    Flushes but does not commit, exactly as `create_revision` does - the caller commits.
    """
    current = active_policy(db)
    if (
        body.tba_date_from is not None
        and body.tba_date_from < date.today()
        and (current is None or current.tba_date_from != body.tba_date_from)
    ):
        raise AppException(
            status_code=422,
            message="TBA date from must be today or later.",
            code="tba_date_from_in_the_past",
        )
    if body.transfer_days is not None and body.transfer_days < 0:
        raise AppException(
            status_code=422,
            message="Transfer days must be zero or greater.",
            code="transfer_days_negative",
        )
    return create_revision(
        db,
        name=current.name if current is not None else FAIR_POLICY_NAME,
        factors=body.factors,
        demand_class_weights=body.demand_class_weights,
        reorder_coverage_until=body.reorder_coverage_until,
        # An omitted `tba_date_from` keeps the date the active revision already carries -
        # the same "the body did not say, so nothing changes" the name and notes get. The
        # column is NOT NULL, so `create_revision` supplies the default only when there is
        # no active revision to copy from.
        tba_date_from=(
            body.tba_date_from
            if body.tba_date_from is not None
            else (current.tba_date_from if current is not None else None)
        ),
        # Same "not said, so unchanged" shape as `tba_date_from` - an omitted value keeps
        # the active revision's own, and a fresh install with no active revision gets the
        # column default of 0 through `create_revision`.
        transfer_days=(
            body.transfer_days
            if body.transfer_days is not None
            else (current.transfer_days if current is not None else None)
        ),
        # Same "not said, so unchanged" shape - the range check (0-365 / 0-100) already
        # ran in `FulfilmentPriorityWrite._check`, so nothing left to validate here.
        immediate_window_days=(
            body.immediate_window_days
            if body.immediate_window_days is not None
            else (current.immediate_window_days if current is not None else None)
        ),
        pool_share_pct=(
            body.pool_share_pct
            if body.pool_share_pct is not None
            else (current.pool_share_pct if current is not None else None)
        ),
        # R-O's two, same "not said, so unchanged" shape - the range check (0-365 each)
        # already ran in `FulfilmentPriorityWrite._check`.
        overdue_grace_days=(
            body.overdue_grace_days
            if body.overdue_grace_days is not None
            else (
                getattr(current, "overdue_grace_days", None)
                if current is not None
                else None
            )
        ),
        overdue_dead_days=(
            body.overdue_dead_days
            if body.overdue_dead_days is not None
            else (
                getattr(current, "overdue_dead_days", None)
                if current is not None
                else None
            )
        ),
        notes=current.notes if current is not None else None,
    )


def demand_class_by_po(db: Session, po_numbers: set[str]) -> dict[str, str]:
    """The demand class of the sales orders each purchase order is feeding.

    Through `scm.order_link_claim`, which is where the SO<->PO pairing lives. A purchase order
    nobody has claimed against is simply missing from the result; `demand_value` turns that into
    a demand of 0.0, because nothing owed is a value and not a gap.
    """
    if not po_numbers:
        return {}
    from app.services.company_scope_sql import company_sql_predicate

    predicate, params = company_sql_predicate(db, "c.company_id", param_prefix="p")
    rows = db.execute(
        text(
            f"""
            SELECT c.po_number, so.demand_class, count(*) AS n
              FROM scm.order_link_claim c
              JOIN sales_orders so ON so.so_number = c.so_number
             WHERE c.po_number = ANY(:nums)
               AND so.demand_class IS NOT NULL
               AND {predicate or 'true'}
             GROUP BY c.po_number, so.demand_class
             ORDER BY c.po_number, n DESC
            """
        ),
        {"nums": list(po_numbers), **params},
    ).mappings().all()
    out: dict[str, str] = {}
    for r in rows:
        out.setdefault(str(r["po_number"]), str(r["demand_class"]))
    return out


def demand_value(
    classes: dict[str, str], class_weights: dict[str, float], po_number: str
) -> Optional[float]:
    """The demand factor value for one purchase order.

    No claimed sales order behind the purchase order is a demand of NOTHING owed, so it is
    0.0 and PRESENT: that is what lets a purchase order feeding a customer outrank one
    feeding no one. A resolved class the policy does not weight is still absent, because
    then the policy has not said what it is worth.
    """
    klass = classes.get(po_number)
    if klass is None:
        return 0.0
    w = class_weights.get(klass)
    return float(w) if w is not None else None


def sequence_values(candidates: Sequence[dict]) -> dict[str, float]:
    """1.0 for the oldest purchase-order document, sliding to 0.0 for the newest.

    Keyed by `po_number`. Ties share a value, so a same-day pair is not split by an accident of
    row order.
    """
    ordered: list[str] = []
    for c in candidates:
        key = str(c.get("po_number") or "")
        if key not in ordered:
            ordered.append(key)
    n = len(ordered)
    if n <= 1:
        return {k: 1.0 for k in ordered}
    return {k: 1.0 - (i / (n - 1)) for i, k in enumerate(ordered)}


def date_values(candidates: Sequence[dict], key: str) -> dict[str, Optional[float]]:
    """Sooner is higher, over the span present in this candidate set. Keyed by `po_line_id`."""
    dates = [c[key] for c in candidates if c.get(key)]
    if not dates:
        return {}
    lo, hi = min(dates), max(dates)
    span = (hi - lo).days or 1
    return {
        str(c["po_line_id"]): (1.0 - ((c[key] - lo).days / span)) if c.get(key) else None
        for c in candidates
    }


def factors_for(
    weights: dict,
    *,
    sequence: Optional[float],
    demand_weight: Optional[float],
    need_by: Optional[float],
    age: Optional[float],
) -> list[Factor]:
    """The four factors, each carrying its weight and whether it had a value at all."""
    values = {
        "po_document_sequence": sequence,
        "demand_class": demand_weight,
        "need_by_date": need_by,
        "document_age": age,
    }
    return [
        Factor(key=k, weight=float(weights.get(k, 0.0) or 0.0), value=v, present=v is not None)
        for k, v in values.items()
    ]


def factors_for_candidates(db: Session, candidates: Sequence[dict]) -> dict[str, list[Factor]]:
    """Factors per `po_line_id` for a set of candidate purchase-order lines.

    The whole assembly in one call, so a caller that only wants "rank these PO lines by the
    active policy" cannot accidentally build three quarters of it. Candidates are dicts carrying
    `po_line_id`, `po_number`, `expected_date` and `po_date` - the shape both the Loading Plan
    and the allocation suggestion already work in.
    """
    weights, class_weights = policy_weights(active_policy(db))
    classes = demand_class_by_po(
        db, {str(c["po_number"]) for c in candidates if c.get("po_number")}
    )
    sequence = sequence_values(candidates)
    need_by = date_values(candidates, "expected_date")
    ages = date_values(candidates, "po_date")

    out: dict[str, list[Factor]] = {}
    for c in candidates:
        line_id = str(c["po_line_id"])
        out[line_id] = factors_for(
            weights,
            sequence=sequence.get(str(c.get("po_number") or "")),
            demand_weight=demand_value(classes, class_weights, str(c.get("po_number") or "")),
            need_by=need_by.get(line_id),
            age=ages.get(line_id),
        )
    return out


# --------------------------------------------------------------------------- #
# Sales-order demand rows (PLAN-fulfilment-planning-from-autocount-so 13.5)
# --------------------------------------------------------------------------- #

#: What a demand row can carry, in the order the board shows the chips. Two of these can never
#: separate anything and are listed anyway, because leaving them out would hide WHY:
#: `po_document_sequence` is structurally absent (a sales-order line has no purchase order), and
#: `demand_class` is constant on a board whose population is project-class by construction.
DEMAND_FACTOR_KEYS = (
    "po_document_sequence",
    "demand_class",
    "need_by_date",
    "document_age",
    "customer_credit",
)


def _ascending_values(values: Sequence[Optional[float]]) -> list[Optional[float]]:
    """Normalize so the SMALLEST present value scores 1.0 and the largest 0.0.

    Absent stays absent - `None` in, `None` out - because `rank_score` drops it from both sums
    and an unknown is not a bad score. When every present value is equal they all score 1.0
    (span of zero), which is the same answer `date_values` gives a same-day set: a factor
    nobody differs on separates nobody, and it must not invent an order.
    """
    present = [v for v in values if v is not None]
    if not present:
        return [None for _ in values]
    lo, hi = min(present), max(present)
    span = (hi - lo) or 1.0
    return [None if v is None else 1.0 - ((v - lo) / span) for v in values]


def _day_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, date):
        return float(value.toordinal())
    try:
        return float(date.fromisoformat(str(value)[:10]).toordinal())
    except ValueError:
        return None


def payment_terms_by_customer(
    db: Session, customer_ids: Sequence[str]
) -> dict[str, Optional[int]]:
    """`customers.payment_terms_days`, which exists in the database but not on the ORM model.

    Read the same guarded way `project_so_draft_service._credit_limit` reads `credit_limit`,
    and for the same reason: a scratch schema built from the models alone does not have the
    column, and an unguarded statement would poison the surrounding transaction rather than
    answering "nobody has assessed this customer". A customer the column has no value for is
    ABSENT, never best and never worst.

    This is the ONE place the credit signal is sourced, so the AR-feed swap the captain
    actually wants - `1 - (outstanding / credit_limit)` clamped to [0, 1], once an invoice or
    receivables feed exists - changes this function and the weight in `factors`, and nothing
    else. `credit_limit` is deliberately not used today: it reaches 8 of 11,166 open project
    lines, so a factor keyed on it would rank essentially nothing.
    """
    ids = [str(cid) for cid in customer_ids if cid]
    if not ids:
        return {}
    present = db.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'customers' "
            "AND column_name = 'payment_terms_days'"
        )
    ).first()
    if not present:
        return {}
    # `id` is a real `uuid` column and the ids arrive as text, so the array is cast rather
    # than compared straight: `uuid = text` has no operator and Postgres refuses it.
    rows = db.execute(
        text(
            "SELECT id, payment_terms_days FROM customers "
            "WHERE id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"ids": ids},
    ).all()
    return {
        str(row[0]): (int(row[1]) if row[1] is not None else None) for row in rows
    }


def factors_for_demand_rows(
    db: Session,
    rows: Sequence[Mapping[str, Any]],
    *,
    weights: Optional[Mapping[str, Any]] = None,
    class_weights: Optional[Mapping[str, Any]] = None,
) -> dict[str, list[Factor]]:
    """Factors per `row_key` for a set of competing SALES-ORDER demand rows.

    The sibling of `factors_for_candidates`, and the whole assembly in one call for the same
    reason: a caller that only wants "rank these demand rows by the policy" cannot accidentally
    build three quarters of it.

    Each row is a mapping carrying `row_key`, `required_date`, `order_date`,
    `payment_terms_days` and `demand_class`. The mapping, decided by the captain:

      * `need_by_date`    <- `sales_order_lines.required_date`, sooner is higher.
      * `document_age`    <- `sales_orders.order_date`, OLDER is higher. The sales order's own
        date, not the customer's PO date: that is the document the row IS, and the
        AutoCount-sourced book carries no customer PO on the core order at all.
      * `customer_credit` <- `customers.payment_terms_days`, SHORTER is higher. No terms
        recorded is ABSENT: a customer nobody has assessed is not thereby the safest or the
        riskiest, and silently treating an unknown as either is how a ranking starts lying.
      * `demand_class`    <- the policy's weight for the row's class, ABSENT when the row has no
        class or the policy does not weight it. Note the difference from the purchase-order
        shape, where "no claimed sales order" is a real value of 0.0: a demand row IS the sales
        order, so there is no "owed to nobody" case to score.
      * `po_document_sequence` is ALWAYS absent. A sales-order line has no purchase order.

    Values are normalized ACROSS THE ROWS PASSED IN, the way `date_values` normalizes across a
    candidate set: a rank only ever means "against the others competing for this stock", and a
    score normalized against the whole book would be dominated by orders not in the fight. So
    the caller passes one cell's contributors, not the world.

    `weights` / `class_weights` override the active policy. That is what a preview is: the
    board ranks by a named alternative without activating it, and nothing is persisted.
    """
    if weights is None or class_weights is None:
        policy_factors, policy_classes = policy_weights(active_policy(db))
        weights = policy_factors if weights is None else weights
        class_weights = policy_classes if class_weights is None else class_weights

    need_by = _ascending_values([_day_number(r.get("required_date")) for r in rows])
    # Older document is higher, and `_ascending_values` already gives 1.0 to the SMALLEST
    # value, which for a date is the earliest one. So the day number goes straight in.
    # Negating it hands the top score to the NEWEST document - the exact opposite of what
    # "document age" means - and the ranking then reads plausibly while being backwards.
    ages = _ascending_values([_day_number(r.get("order_date")) for r in rows])
    credit = _ascending_values(
        [
            None if r.get("payment_terms_days") is None
            else float(r["payment_terms_days"])
            for r in rows
        ]
    )

    out: dict[str, list[Factor]] = {}
    for index, row in enumerate(rows):
        klass = row.get("demand_class")
        class_weight = class_weights.get(klass) if klass else None
        values = {
            "po_document_sequence": None,
            "demand_class": None if class_weight is None else float(class_weight),
            "need_by_date": need_by[index],
            "document_age": ages[index],
            "customer_credit": credit[index],
        }
        keys = list(DEMAND_FACTOR_KEYS) + [
            key for key in weights if key not in DEMAND_FACTOR_KEYS
        ]
        out[str(row["row_key"])] = [
            Factor(
                key=key,
                weight=float(weights.get(key, 0.0) or 0.0),
                value=values.get(key),
                present=values.get(key) is not None,
            )
            for key in keys
        ]
    return out


def discriminates_nothing(factors_by_row: Mapping[str, Sequence[Factor]]) -> bool:
    """True when this policy cannot separate these rows at all.

    Two ways that happens, and the board has to report both rather than show a
    plausible-looking order it did not earn:

      * every weighted factor is ABSENT on every row - which is what the live seeded rule does
        to a board, weighting only `po_document_sequence`, so `rank_score` divides by a zero
        denominator and answers 0.0 for everybody;
      * a weighted factor is present but holds the SAME value on every row, which is what
        `demand_class` does on a board whose population is project-class by construction.

    A single row is trivially unseparable and reports True, which is honest: there is nothing
    for a ranking to have decided.
    """
    seen: dict[str, set[float]] = {}
    for factors in factors_by_row.values():
        for factor in factors:
            if factor.weight <= 0 or not factor.present or factor.value is None:
                continue
            seen.setdefault(factor.key, set()).add(round(float(factor.value), 9))
    return not any(len(values) > 1 for values in seen.values())


def scores_for(factors_by_row: Mapping[str, Sequence[Factor]]) -> dict[str, float]:
    """`rank_score` per row. The generic scorer, never a second copy of the arithmetic."""
    return {key: rank_score(list(factors)) for key, factors in factors_by_row.items()}


def raw_facts_for_demand_row(row: Mapping[str, Any]) -> dict[str, Optional[str]]:
    """The ABSOLUTE fact behind each of a demand row's factors, as the planner would say it.

    A normalised 0.00 beside a normalised 1.00 explains nothing on its own - and on a policy
    that weights nothing a demand row carries, every score is 0.00 and the chips read as a
    broken feature rather than as a rule saying nothing. What answers "why does that order
    outrank mine" is the fact itself: this line is due on the 1st and yours on the 4th, this
    order was raised in 2024 and yours this year, this customer pays in 30 days and yours in 90.

    Returned beside the factors rather than inside `Factor`, because `Factor.as_dict()` is
    FROZEN into `scm.reorder_run` / loading-plan rows by three other callers, and widening a
    persisted shape to serve a screen is how a display concern ends up in stored history.

    Text, not typed values: each factor's fact is a different kind of thing (a date, a term in
    days, a class name) and the screen only ever prints it.
    """
    terms = row.get("payment_terms_days")
    klass = row.get("demand_class")
    return {
        # No purchase order behind a sales-order line, so there is no sequence to state.
        "po_document_sequence": None,
        "demand_class": str(klass) if klass else None,
        "need_by_date": _iso_or_none(row.get("required_date")),
        "document_age": _iso_or_none(row.get("order_date")),
        "customer_credit": f"{int(terms)} days" if terms is not None else None,
    }


def _iso_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10] or None
