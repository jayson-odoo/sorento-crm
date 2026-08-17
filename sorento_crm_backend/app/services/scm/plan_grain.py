"""Which grain a front-planning run may be decided at, and who may write to it.

Plan grain (front-planning plan section 5.1) is an ADMIN POLICY, not a per-run selector
the buyer picks: one field in system settings, rollout default `product`. A run stamps the
configured grain at creation (`reorder_run.decision_grain`) together with the contract
version, and neither ever changes afterwards - so changing the policy affects only runs
created later, and the grain a screen shows for an existing run is its stamp, never the
live setting (AC-F09, AC-F10).

Two writes are therefore refused, and both are 409 because the request is well-formed and
the state is what makes it wrong:

* `legacy_run_read_only` - the run predates the contract (`front_planning_contract_version
  IS NULL`). Its recommendations, overrides and summary rows stay exactly as they are, and
  the buyer creates a new run to act. `decision_grain` is deliberately NOT backfilled;
  guessing which grain a historical run "meant" is the one thing that could make an old
  decision actionable twice.
* `decision_grain_mismatch` - the run is stamped at the OTHER grain. Product decisions are
  the `order_summary_row` chosen quantity; location decisions are the recommendation
  accept / adjust / reject. Exactly one of the two is actionable per run, which is what
  stops both grains ordering the same requirement.

Both services route through `assert_decision_grain` so the two refusals cannot drift apart
in wording or in status code.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.services.error_handler import AppException

PRODUCT_GRAIN = "product"
LOCATION_GRAIN = "location"
PLAN_GRAINS = (PRODUCT_GRAIN, LOCATION_GRAIN)

#: The rollout default (plan 5.1). Also what an unset / unreadable setting resolves to.
DEFAULT_PLAN_GRAIN = PRODUCT_GRAIN

#: Stamped on every run created under this contract. Bumped only if the front-planning
#: contract itself changes shape; NULL means "before the contract", i.e. legacy.
FRONT_PLANNING_CONTRACT_VERSION = 1

_GRAIN_LABEL = {
    PRODUCT_GRAIN: "Product",
    LOCATION_GRAIN: "Location",
}


def resolve_plan_grain(db: Session) -> str:
    """The configured admin policy, or the rollout default when nothing is configured."""
    from app.models.user import SystemSetting

    value = db.query(SystemSetting.plan_grain).limit(1).scalar()
    return value if value in PLAN_GRAINS else DEFAULT_PLAN_GRAIN


def is_legacy_run(run) -> bool:
    """A run created before the front-planning contract. Read-only, both grains."""
    return getattr(run, "front_planning_contract_version", None) is None


def decision_grain_of(run) -> Optional[str]:
    """The run's stamped grain, or None for a legacy run."""
    if is_legacy_run(run):
        return None
    return getattr(run, "decision_grain", None)


def assert_decision_grain(run, expected: str) -> None:
    """Refuse a decision write this run cannot own. Raises `AppException` (409)."""
    if is_legacy_run(run):
        raise AppException(
            status_code=409,
            message=(
                "This plan was created before product-and-location planning, so it is "
                "read only. Create a new plan to decide on it."
            ),
            code="legacy_run_read_only",
        )
    grain = getattr(run, "decision_grain", None)
    if grain != expected:
        raise AppException(
            status_code=409,
            message=(
                f"This plan is decided at {_GRAIN_LABEL.get(grain, grain)} grain, so a "
                f"{_GRAIN_LABEL.get(expected, expected)} decision cannot be recorded on "
                "it."
            ),
            code="decision_grain_mismatch",
        )
