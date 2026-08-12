"""SCM engine simulation harness - API surface over ``scripts/scm_sim``.

The harness itself (38 frozen scenarios, a dedicated ``sorento_scm_sim`` database, two
JSON files) is documented in ``scripts/scm_sim/README.md``; this router just gives the FE
a page over the same thing so a run/bless/diff cycle does not require a shell. See
``app.services.scm.simulation_service`` for the actual read/write logic - every diff below
comes straight out of ``scripts/scm_sim/compare.py``, never a re-implementation of it.

Reading (overview, the scenario grid, one scenario's diff) works off the two JSON files on
disk and never touches the database, so it renders identically whether or not THIS process
happens to be pointed at the sim database. Running or blessing is gated: this backend
process must itself be connected to ``sorento_scm_sim`` (a dev convenience - the intended
setup runs this on a separate port with ``DATABASE_URL`` swapped), or the write is refused
with 409 rather than TRUNCATE-ing whatever database the process actually has open.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.services.error_handler import AppException
from app.services.scm import simulation_service as svc

router = APIRouter()

_VIEW = require_permission_with_api_key("scm.dashboard.view")
_RUN = require_permission_with_api_key("scm.reorder.run")


class RunSimulationRequest(BaseModel):
    bless_baseline: bool = False


@router.get("/simulation/overview")
def get_overview(
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Header strip for the page: whether this process can run (``sim_db_active``), and
    the age of the blessed baseline + last run. Works even when neither JSON file exists
    yet (a fresh checkout) - both flip to ``false``/``null`` rather than 404ing."""
    return svc.get_overview(db)


@router.get("/simulation/scenarios")
def list_scenarios(
    _user: dict = Depends(_VIEW),
):
    """Every frozen scenario, joined against the last run and the blessed baseline.

    Always returns all 38 rows (the registry is the source of the row set, not either
    JSON file) - a scenario with no run yet simply carries ``current: null``."""
    return {"data": svc.list_scenarios()}


@router.get("/simulation/scenarios/{code}/diff")
def get_scenario_diff(
    code: str,
    _user: dict = Depends(_VIEW),
):
    """Full field-level diff for one scenario, plus its whole current snapshot blob (the
    frozen inputs the engine actually saw) so the detail panel needs no second source."""
    return svc.get_scenario_diff(code)


@router.post("/simulation/run")
def run_simulation(
    payload: RunSimulationRequest = Body(default=RunSimulationRequest()),
    _user: dict = Depends(_RUN),
):
    """Wipe the sim database, reseed all 38 scenarios, run the engine once, write
    ``snapshots/current.json``. Optionally blesses the result as the new baseline in the
    same call (``bless_baseline``) - the separate ``POST /simulation/bless`` exists for
    the "inspect first, then bless" path.

    409s outright unless THIS process is connected to the dedicated sim database - the
    seed step is a blunt TRUNCATE, and it must never run against anything else."""
    if not svc.is_sim_db_active():
        raise AppException(
            409,
            "This backend is not connected to the sim database "
            f"({svc.expected_db_name()!r}). Point DATABASE_URL at it and restart before "
            "running a simulation.",
        )
    return svc.run_simulation(bless_baseline=payload.bless_baseline)


@router.post("/simulation/bless")
def bless_baseline(
    _user: dict = Depends(_RUN),
):
    """Copy the last run (``snapshots/current.json``) over the blessed baseline. Separate
    from ``run`` so a run can be inspected before it becomes the reference everything else
    is compared against."""
    return svc.bless_baseline()
