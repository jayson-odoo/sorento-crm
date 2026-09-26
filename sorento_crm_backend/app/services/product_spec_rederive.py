"""Re-read the catalogue after somebody changes how a specification is read.

The gap this closes: editing a derivation rule changes how a product WOULD be read, and
nothing re-reads it. Rules are saved, the screen says saved, and every search keeps
returning the old values - because the values live on 22,805 stored rows that were
derived under the old rules. Someone changed `FREE STANDING` from `floor_standing` to
`free_standing`, saved, searched, and correctly concluded the setting did nothing.

Derivation touches every product code and takes minutes, so it cannot run inside the
request. It runs on a background thread with a status anyone can poll, and the registry
carries a fingerprint of the rules it was last run against - which is what lets the UI
say "the rules have changed since this was last read" instead of leaving people to
guess.

Ticket: jayson-odoo/sorento-crm#103.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.product_spec import ProductSpecSearchPolicy

logger = logging.getLogger(__name__)

# The run is in-process state on purpose: it is progress for whoever pressed the button,
# not a record. What SURVIVES is the fingerprint below, written when a run finishes.
_STATE_LOCK = threading.Lock()
_STATE: dict = {"status": "idle", "started_at": None, "finished_at": None, "result": None}

# Stored beside the ranking knobs rather than in its own table: one row, one number's
# worth of meaning, and it is read on exactly the same screen.
_FINGERPRINT_KEY = "_derived_rules_fingerprint"


def rules_fingerprint(db: Session) -> str:
    """A stable hash of how every key is read right now. Changes when any of it does.

    The RUNNING rules, not only the stored column: the configured rules with the shipped
    fallback for a key that has none, every key's scope and cap, and
    `DERIVATION_VERSION`. A deploy that changes the shipped rules (or the engine)
    therefore moves it even when nobody edited a row, which is what lets the worker
    catch the catalogue up on start (D10, AC-S3.5). Scope and cap are in it because they
    decide what a product carries as much as a rule does: narrowing `has_drainer` to
    Kitchen Sink changes 74 rows without touching a rule.
    """
    import hashlib

    from app.services.product_spec_derivation import (
        DERIVATION_VERSION,
        configured_max_values,
        configured_rules,
        configured_scopes,
    )

    payload = json.dumps(
        {
            "version": DERIVATION_VERSION,
            "rules": configured_rules(db),
            "scopes": configured_scopes(db),
            "max_values": configured_max_values(db),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _stored_fingerprint(db: Session) -> str | None:
    row = db.query(ProductSpecSearchPolicy).filter_by(policy_key=_FINGERPRINT_KEY).first()
    return row.help_text if row is not None else None


def _store_fingerprint(db: Session, fingerprint: str) -> None:
    row = db.query(ProductSpecSearchPolicy).filter_by(policy_key=_FINGERPRINT_KEY).first()
    if row is None:
        row = ProductSpecSearchPolicy(
            policy_key=_FINGERPRINT_KEY,
            label="Rules the catalogue was last read with",
            value=0,
        )
        db.add(row)
    row.help_text = fingerprint
    db.commit()


def status(db: Session) -> dict:
    """What the catalogue is doing, and whether it is out of date."""
    with _STATE_LOCK:
        state = dict(_STATE)
    current = rules_fingerprint(db)
    stored = _stored_fingerprint(db)
    state["rules_changed_since_last_read"] = stored is not None and stored != current
    # No fingerprint at all means this has never been run from here. Say "unknown"
    # rather than "up to date": claiming freshness we cannot prove is how someone ends
    # up trusting stale values.
    state["ever_read"] = stored is not None
    return state


def _run(fingerprint: str) -> None:
    from app.database import SessionLocal
    from app.tasks.product_spec_tasks import derive_product_specs

    try:
        result = derive_product_specs(run_label="ui-rederive")
        with SessionLocal() as db:
            _store_fingerprint(db, fingerprint)
        with _STATE_LOCK:
            _STATE.update(
                status="done",
                finished_at=datetime.now(timezone.utc).isoformat(),
                result=result,
            )
        logger.info("ui re-derive finished: %s", result)
    except Exception as exc:  # noqa: BLE001 - reported to the caller, never swallowed
        logger.exception("ui re-derive failed")
        with _STATE_LOCK:
            _STATE.update(
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                result={"error": str(exc)},
            )


def start(db: Session) -> dict:
    """Kick off a catalogue re-read. Refuses to start a second one alongside the first."""
    with _STATE_LOCK:
        if _STATE["status"] == "running":
            return {"status": "running", "started_at": _STATE["started_at"]}
        _STATE.update(
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            result=None,
        )

    # Captured BEFORE the run so a rule edited while it is running does not get credited
    # to it - that would mark the catalogue fresh for rules it never read.
    fingerprint = rules_fingerprint(db)
    threading.Thread(target=_run, args=(fingerprint,), daemon=True).start()
    return {"status": "running", "started_at": _STATE["started_at"]}


# --------------------------------------------------------------------------- #
# reading runs itself (#1286, D10): after a save, and after a deploy
# --------------------------------------------------------------------------- #
def enqueue_job(func, *args, **kwargs):
    """`queue_service.enqueue_job`, looked up when called so a test can stand in for it
    and a module import never needs Redis."""
    from app.services.queue_service import enqueue_job as _enqueue

    return _enqueue(func, *args, **kwargs)


def catch_up_on_worker_start() -> bool:
    """Queue one catalogue re-read when the running rules are not the ones the catalogue
    was last read with. Returns whether it queued one. Never raises.

    Called once by `worker.py` on start, when that worker drains `imports`. A deploy
    that changes the shipped rules moves the running fingerprint, and nobody is asked to
    press anything (owner ruling, 27 Sep 2026: no re-read concept on any screen). The
    job stores the fingerprint it read with when it finishes, so the next start queues
    nothing.
    """
    from app.database import SessionLocal

    try:
        with SessionLocal() as db:
            running = rules_fingerprint(db)
            stored = _stored_fingerprint(db)
        if stored == running:
            logger.info("spec catch-up: the catalogue was read with the running rules")
            return False
        from app.tasks.product_spec_tasks import reread_catalogue

        enqueue_job(reread_catalogue, queue_name="imports", run_label="worker-start catch-up")
        logger.info("spec catch-up: rules changed since the last read, catalogue re-read queued")
        return True
    except Exception:  # noqa: BLE001 - a worker must start whatever this finds
        logger.warning("spec catch-up could not run", exc_info=True)
        return False


def reread_catalogue_and_store(run_label: str | None = None) -> dict:
    """Re-read every product, then store the fingerprint of the rules it read with.

    The fingerprint is taken BEFORE the run so a rule edited while it runs is not
    credited to it.
    """
    from app.database import SessionLocal
    from app.tasks.product_spec_tasks import derive_product_specs

    with SessionLocal() as db:
        fingerprint = rules_fingerprint(db)
    result = derive_product_specs(run_label=run_label or "catalogue re-read")
    with SessionLocal() as db:
        _store_fingerprint(db, fingerprint)
    return result


def reread_after_save(db: Session, spec_key: str, *, fingerprint_before: str) -> int:
    """Re-read exactly the products whose `spec_key` value the saved rules change.

    The save already knows which products change: it is the same comparison See what
    would change makes (`product_spec_preview.readings_for_key`). Those codes go through
    `rederive_codes`, the path a product edit takes - a few inline, many on the
    `imports` queue. Returns how many products that is, for the toast "Saved. N products
    updated." (AC-S1.16).

    The stored fingerprint moves to the new rules only when it matched the rules before
    this save: then the catalogue was current and now is again, so the worker has
    nothing to catch up. When it did not match (a deploy's catch-up is still owed), it
    is left alone so that catch-up still runs.
    """
    from app.services import product_spec_change_listener as listener
    from app.services.product_spec_derivation import (
        configured_max_values,
        configured_rules,
        configured_scopes,
    )
    from app.services.product_spec_preview import readings_for_key

    was_current = _stored_fingerprint(db) == fingerprint_before
    changed = {
        row["code"]
        for row in readings_for_key(
            db,
            spec_key,
            rules_by_key=configured_rules(db),
            scopes_by_key=configured_scopes(db),
            max_values=configured_max_values(db),
        )
        if row["before"] != row["after"]
    }
    if changed:
        listener.rederive_codes(changed)
    if was_current:
        _store_fingerprint(db, rules_fingerprint(db))
    return len(changed)
