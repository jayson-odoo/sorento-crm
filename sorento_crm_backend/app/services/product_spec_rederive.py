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

from app.models.product_spec import ProductSpecRegistry, ProductSpecSearchPolicy

logger = logging.getLogger(__name__)

# The run is in-process state on purpose: it is progress for whoever pressed the button,
# not a record. What SURVIVES is the fingerprint below, written when a run finishes.
_STATE_LOCK = threading.Lock()
_STATE: dict = {"status": "idle", "started_at": None, "finished_at": None, "result": None}

# Stored beside the ranking knobs rather than in its own table: one row, one number's
# worth of meaning, and it is read on exactly the same screen.
_FINGERPRINT_KEY = "_derived_rules_fingerprint"


def rules_fingerprint(db: Session) -> str:
    """A stable hash of how every key is read. Changes when any of it is edited.

    Covers the rules, the scope AND the cap, because all three decide what a product
    ends up carrying: narrowing `has_drainer` to Kitchen Sink changes 74 rows without
    touching a single rule, and dropping `dim_length`'s cap from 5000 to 500 changes
    every reading over 500 without touching a rule OR a scope - the screen has to say
    the catalogue is out of date for that too (S2).
    """
    import hashlib

    rows = (
        db.query(
            ProductSpecRegistry.spec_key,
            ProductSpecRegistry.derivation_rules,
            ProductSpecRegistry.applies_when,
            ProductSpecRegistry.max_value,
        )
        .order_by(ProductSpecRegistry.spec_key)
        .all()
    )
    payload = json.dumps(
        {
            key: {"rules": rules, "scope": scope, "max_value": str(max_value)}
            for key, rules, scope, max_value in rows
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
