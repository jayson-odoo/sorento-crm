"""SCM engine simulation harness - the API layer over ``scripts/scm_sim``.

``scripts/scm_sim`` (world.py / scenarios.py / runner.py / compare.py / snapshot.py) is a
CLI-first harness: 38 frozen scenarios, a dedicated ``sorento_scm_sim`` database, and two
JSON files (``snapshots/current.json`` the last run, ``baselines/baseline.json`` the blessed
reference). This module gives the FE a way to drive the SAME harness without a shell -
reading the two JSON files for the grid, and calling ``runner.run_once`` / copying the
baseline file for the two write actions. Every diff below is computed with
``compare.py``'s own walk/group functions, never a re-implementation of them.

``scripts`` has no ``__init__.py`` (an implicit namespace package) and is only importable
when the backend's own root directory is on ``sys.path`` - true for ``python -m
scripts.scm_sim`` (which inserts it itself) but NOT true for the FastAPI process, whose
console-script entry point (``venv/bin/uvicorn``) puts its OWN directory on
``sys.path[0]``, not the caller's cwd. This module inserts the backend root once, at
import time, before touching ``scripts.scm_sim`` - the only place in the app that needs to.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from scripts.scm_sim.compare import _group_for, _walk_diff, load_json  # noqa: E402
from scripts.scm_sim.runner import (  # noqa: E402
    BASELINE_PATH,
    SNAPSHOT_PATH,
    expected_db_name,
)
from scripts.scm_sim.runner import run_once as _run_once  # noqa: E402
from scripts.scm_sim.scenarios import BY_CODE, SCENARIOS  # noqa: E402

from app.services.error_handler import AppException  # noqa: E402

#: The rec fields the overview grid needs per scenario - a slice of the much bigger
#: recommendation row the snapshot carries, per the FE contract (only what the grid
#: renders; the diff endpoint below returns the full blob for detail).
_REC_SUMMARY_FIELDS = ("rec_type", "recommended_qty", "rounded_qty", "triggered_reason",
                       "cash_impact")


def _mtime_iso(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _load_or_empty(path: Path) -> dict:
    if not path.exists():
        return {}
    return load_json(path)


def _is_sim_db_active() -> bool:
    """Does THIS process's own database connection name the dedicated sim database.

    Reads the already-created engine (bound at process startup to whatever
    ``DATABASE_URL`` the process was launched with) rather than re-parsing the env, so the
    answer matches what a query against ``db`` would actually hit.
    """
    from app.database import engine

    return (engine.url.database or "") == expected_db_name()


def _rec_summary(entry: Optional[dict]) -> Optional[dict]:
    """The first recommendation's grid-relevant fields, or ``None`` when the scenario
    produced none (a legitimate outcome - e.g. SIM-P038 must produce zero)."""
    if not entry:
        return None
    recs = entry.get("recommendations") or []
    if not recs:
        return None
    first = recs[0]
    return {k: first.get(k) for k in _REC_SUMMARY_FIELDS}


def _snapshot_inputs(entry: Optional[dict], *, segment: str) -> dict[str, Any]:
    """The grid's INPUT-side columns - what the engine actually saw, read off a snapshot
    entry (the CURRENT run, falling back to the blessed baseline - see ``list_scenarios``)
    rather than off the ``ScenarioSpec`` it was seeded from. In every scenario the two
    agree (the engine never mutates stock/committed/on-order while planning), but reading
    the snapshot is the honest source: it is what a REAL Reorder Planning row would show
    for this SKU, which is the whole point of this column - letting the user eyeball the
    sim grid against the real planning page.

    ``on_hand`` / ``committed`` / ``spo_incoming`` come from ``net_position`` (present for
    every scenario that has ever been planned, even the ones with no recommendation -
    SIM-P031, SIM-P038). ``po_open`` is informational-only (ADR/migration 337 - the PO book
    never nets against demand) and only ever appears inside a recommendation's frozen
    ``inputs.po_ordered``, so a scenario with no recommendation reads 0, not null - the
    honest reading is "no open PO was seen", not "unknown".
    """
    net = (entry or {}).get("net_position") or {}
    recs = (entry or {}).get("recommendations") or []
    po_open = None
    if recs:
        po_open = (recs[0].get("inputs") or {}).get("po_ordered")
    return {
        "on_hand": net.get("quantity_on_hand"),
        "committed": net.get("committed"),
        "spo_incoming": net.get("on_order"),
        "po_open": po_open if po_open is not None else 0,
        # Order Inquiry vs Sales Order (M8 target model): project-segment demand is
        # sourced from the Order Inquiry feed, dealer-segment from Sales Orders.
        "demand_label": "OI" if segment == "project" else "SO",
    }


def _scenario_status(code: str, baseline: dict, current: dict, baseline_exists: bool) -> tuple[str, list[dict]]:
    """``(status, diffs)`` for one scenario, using ``compare.py``'s own walk + grouping.

    ``diffs`` is the full field-level list (``[{path, old, new, group}]``); the overview
    list only needs the deduplicated group names, the per-scenario diff endpoint needs the
    whole thing, so this is computed once and both callers slice what they need.
    """
    if not baseline_exists:
        return "NO_BASELINE", []
    in_baseline = code in baseline
    in_current = code in current
    if not in_baseline:
        return "NEW", []
    if not in_current:
        return "GONE", []
    diffs = [
        {"path": path, "old": old, "new": new, "group": _group_for(path)}
        for path, old, new in _walk_diff(baseline[code], current[code])
    ]
    if not diffs:
        return "SAME", diffs
    return "CHANGED", diffs


def get_overview(db) -> dict[str, Any]:
    baseline_exists = BASELINE_PATH.exists()
    current_exists = SNAPSHOT_PATH.exists()
    sim_db_active = _is_sim_db_active()

    latest_run_id = None
    if sim_db_active:
        latest_run_id = _latest_run_id(db)

    return {
        "sim_db_active": sim_db_active,
        "baseline_exists": baseline_exists,
        "baseline_blessed_at": _mtime_iso(BASELINE_PATH),
        "current_exists": current_exists,
        "current_run_at": _mtime_iso(SNAPSHOT_PATH),
        "latest_run_id": latest_run_id,
        "scenario_count": len(SCENARIOS),
    }


def _latest_run_id(db) -> Optional[str]:
    """Best-effort: the most recent ``scm.reorder_run`` row on THIS (sim) database.

    Never raises - a missing/renamed table on a not-yet-``init``'d sim database is a
    perfectly normal state for this to be called against, and the overview must still
    render.
    """
    from sqlalchemy import text

    from app.services.company_scope_sql import company_sql_predicate

    try:
        co, co_params = company_sql_predicate(db, "company_id", param_prefix="simov")
        where = f"WHERE {co}" if co else ""
        row = db.execute(text(f"""
            SELECT id FROM scm.reorder_run
            {where}
            ORDER BY started_at DESC NULLS LAST, created_at DESC
            LIMIT 1
        """), co_params).first()
        return str(row[0]) if row else None
    except Exception:  # noqa: BLE001 - best-effort read, never fails the overview
        db.rollback()
        return None


def list_scenarios() -> list[dict[str, Any]]:
    baseline_exists = BASELINE_PATH.exists()
    baseline = _load_or_empty(BASELINE_PATH)
    current = _load_or_empty(SNAPSHOT_PATH)

    out: list[dict[str, Any]] = []
    for spec in SCENARIOS:
        status, diffs = _scenario_status(spec.code, baseline, current, baseline_exists)
        changed_groups = sorted({d["group"] for d in diffs}) if status == "CHANGED" else []
        # Current wins; fall back to the blessed baseline (e.g. a fresh checkout that has
        # a baseline fixture but no run yet) so the input columns are never blank just
        # because nobody has pressed "Run simulation" in this checkout.
        snapshot_entry = current.get(spec.code) or baseline.get(spec.code)
        out.append({
            "code": spec.code,
            "title": spec.title,
            "segment": spec.segment,
            "policy": spec.policy,
            "expected_note": spec.expected_note,
            "inputs": _snapshot_inputs(snapshot_entry, segment=spec.segment),
            "current": _rec_summary(current.get(spec.code)),
            "baseline": _rec_summary(baseline.get(spec.code)) if baseline_exists else None,
            "status": status,
            "changed_groups": changed_groups,
        })
    return out


def get_scenario_diff(code: str) -> dict[str, Any]:
    if code not in BY_CODE:
        raise AppException(404, f"Unknown scenario {code!r}.")

    baseline_exists = BASELINE_PATH.exists()
    baseline = _load_or_empty(BASELINE_PATH)
    current = _load_or_empty(SNAPSHOT_PATH)

    status, diffs = _scenario_status(code, baseline, current, baseline_exists)
    return {
        "code": code,
        "status": status,
        "diffs": diffs,
        "current": current.get(code),
        "baseline": baseline.get(code) if baseline_exists else None,
    }


def is_sim_db_active() -> bool:
    return _is_sim_db_active()


def run_simulation(*, bless_baseline: bool) -> dict[str, Any]:
    """Wipe + reseed + run the engine + snapshot (``runner.run_once``), then read back the
    run's own roll-up counts from ``scm.reorder_run.run_log``.

    ``runner.guard_sim_db`` (called inside ``run_once``) raises ``SystemExit`` on anything
    but the sim database - a ``BaseException`` FastAPI's own exception middleware does not
    catch, so it is translated to a 500 here defensively. The caller (the route) is
    expected to have ALREADY checked ``is_sim_db_active()`` and returned 409 before this is
    ever reached; this is the last-line-of-defence, not the primary guard.
    """
    try:
        result = _run_once(bless=bless_baseline)
    except SystemExit as exc:
        raise AppException(500, f"Simulation run failed: {exc}") from exc

    run_id = result["run_id"]
    return {"run_id": run_id, "blessed": bless_baseline, **_run_log_counts(run_id)}


def _run_log_counts(run_id: str) -> dict[str, Any]:
    """Read the just-finished run's own summary counts straight off its row - the same
    ``run_log`` shape ``reorder_runs.py`` reports for every other run in this system."""
    from sqlalchemy import text

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT run_log FROM scm.reorder_run WHERE id = :id"), {"id": run_id}
        ).first()
    finally:
        db.close()
    log = (row[0] if row else None) or {}
    return {
        "buy_count": int(log.get("buy", 0)),
        "disposition_count": int(log.get("disposition", 0)),
        "exception_count": int(log.get("exceptions", 0)),
        "total_cash_impact": float(log.get("total_cash_impact", 0.0)),
        "recommendation_count": int(log.get("recommendation_count", 0)),
    }


def bless_baseline() -> dict[str, Any]:
    if not SNAPSHOT_PATH.exists():
        raise AppException(400, "Run a simulation first - there is no current run to bless.")
    current = load_json(SNAPSHOT_PATH)
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(SNAPSHOT_PATH.read_text())
    _ = current  # loaded only to fail loudly on corrupt JSON before overwriting the baseline
    return {"blessed": True, "baseline_blessed_at": _mtime_iso(BASELINE_PATH)}
