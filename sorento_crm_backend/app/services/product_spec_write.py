"""The one place spec values are written. Everything else asks this module.

`spec.values`, `spec.provenance` and `spec.rendered_text` are assigned HERE and nowhere
else. Two callers reach them - derivation rebuilding a whole row, and a person setting
one key by hand - and until now each owned its own copy of the merge rule, so "a value a
reviewer set survives re-derivation" was true in one of them and subtly false in the
other. One writer makes the rule mechanically greppable rather than a judgement call.

Three things live here because they are the same decision seen from different angles:

  * `merge_authored_over` - what a person set outranks what the rules read, including
    when what they set was "this product does not have this spec" (a tombstone).
  * `write_spec_row`      - the column assignment, the rendered sentence and the status,
    computed in one place so precedence cannot drift between callers.
  * `apply_spec_values`   - the authored write, fanned out to every company copy of the
    code and re-derived in the same transaction so a disagreement surfaces in the same
    click rather than on the next catalogue run.

Plan: `PLAN-spec-authoring-verification.md` (C9). UAC: AC-F.1 to AC-F.13.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.models.product import Product
from app.models.product_spec import ProductSpecException, ProductSpecifications
from app.services.error_handler import AppException
from app.services.product_spec_rendering import render_spec_sentence

logger = logging.getLogger(__name__)

# Who counts as a person. Membership in this set is the only "did someone set this"
# test in the codebase: a bare equality against the single string below would silently
# treat a supplier-submitted entry as machine-derived everywhere that test runs.
# `supplier` has no writer in this milestone; it is reserved for the supplier portal.
# `flyer` joins this set in the bulk flyer-ingestion slice after PRs 1-4, once the
# promote migration has re-stamped the legacy entries, and not before (AC-F.7):
# derivation writes `source='flyer'` itself on every run today, so an early flip would
# badge a machine read as a person's own work.
AUTHORED_SOURCES: frozenset[str] = frozenset({"human", "supplier"})

DEFAULT_AUTHORED_SOURCE = "human"

CONFLICT_REASON = "human_override_conflict"

# Columns this module owns, watched by the bypass backstop below.
WRITTEN_COLUMNS = ("values", "provenance", "rendered_text")

_SANCTIONED_ATTR = "_spec_write_sanctioned"
_BYPASS_KEY = "_spec_write_bypasses"
_BACKSTOP_REGISTERED = False


# --------------------------------------------------------------------------- #
# canonical values hash
# --------------------------------------------------------------------------- #
def _canonical_value(raw):
    """One stored value, reduced to something two callers can compare.

    Tagged rather than bare so a number and its own string spelling cannot collide.
    """
    if raw is None:
        return None
    # bool BEFORE the numeric branch: bool is a subclass of int in Python, so a naive
    # numeric test turns True into the number 1.
    if isinstance(raw, bool):
        return ["bool", raw]
    if isinstance(raw, (int, float, Decimal)):
        try:
            # `format(..., "f")` is load-bearing: a bare `.normalize()` renders 407.0 as
            # "4.07E+2", which does not equal the "407" that the int 407 produces.
            return ["num", format(Decimal(str(raw)).normalize(), "f")]
        except (InvalidOperation, ValueError):
            return ["str", str(raw).strip()]
    if isinstance(raw, (list, tuple)):
        items = [_canonical_value(item) for item in raw]
        items = [item for item in items if item is not None]
        # Order-insensitive: 408 stored arrays are sets of features, and re-ordering one
        # is not an edit anybody made.
        items.sort(key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
        return ["list", items]
    if isinstance(raw, Mapping):
        return ["map", {str(k): _canonical_value(v) for k, v in sorted(raw.items())}]
    text = str(raw).strip()
    # Case is PRESERVED. A case change is a real edit a person can see, so hiding it
    # would suppress a legitimate re-verify later.
    return ["str", text] if text else None


def _canonical_entry(entry) -> dict | None:
    """`{"value": ..., "unit": ...}` reduced, or None when the key says nothing.

    A bare scalar stored under a key is read as its value, defensively.
    """
    if isinstance(entry, Mapping):
        raw, unit = entry.get("value"), entry.get("unit")
    else:
        raw, unit = entry, None

    value = _canonical_value(raw)
    if value is None:
        return None

    canonical = {"v": value}
    # A missing unit, a null one and an empty one all mean the same thing: the key
    # carries no unit. A present one is the system's spelling, not a person's, so it
    # folds.
    text = str(unit).strip().casefold() if unit is not None else ""
    if text:
        canonical["u"] = text
    return canonical


def canonical_values_hash(values: Mapping) -> str:
    """A sha256 over the VALUES alone, never provenance.

    Provenance is deliberately not an argument. A re-stamped evidence string or a
    source change must not move the hash, or PR 3's verification would be withdrawn by
    edits nobody made to the data itself. A key whose value normalises to nothing is
    dropped entirely, so a pre-seeded blank can never collide with a tombstone.
    """
    canonical: dict[str, dict] = {}
    for key, entry in (values or {}).items():
        reduced = _canonical_entry(entry)
        if reduced is not None:
            canonical[str(key)] = reduced
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


# --------------------------------------------------------------------------- #
# the merge
# --------------------------------------------------------------------------- #
def _is_authored(entry) -> bool:
    return isinstance(entry, Mapping) and entry.get("source") in AUTHORED_SOURCES


def authored_keys(provenance: Mapping | None) -> set[str]:
    """Every key a person has answered, tombstones included."""
    return {key for key, entry in (provenance or {}).items() if _is_authored(entry)}


def merge_authored_over(
    derived_values: Mapping,
    derived_provenance: Mapping,
    existing_values: Mapping | None,
    existing_provenance: Mapping | None,
) -> tuple[dict, dict, list[dict]]:
    """Lay what a person set over what the rules read. Returns (values, provenance, conflicts).

    Three shapes of authored entry, and the second is the one that used to go wrong:

      * a tombstone (`absent`) - the key is removed from values even though derivation
        produced one, and NO conflict is raised. Derivation re-derives that key every
        run, so flagging it would park a permanent unresolvable row in a table whose
        contract is exceptions only.
      * an authored value - it stays in force, and a derivation that disagrees with it
        after normalisation is raised once as a conflict rather than applied.
      * authored provenance with no value and no `absent` flag - treated as a tombstone.
        This is the shape the old merge resurrected: it kept the provenance entry but
        fell through to derivation's value, so the derived answer came back badged as
        set by the person who had just removed it.
    """
    values = dict(derived_values or {})
    provenance = dict(derived_provenance or {})
    stored_values = existing_values or {}
    conflicts: list[dict] = []

    for key, entry in (existing_provenance or {}).items():
        if not _is_authored(entry):
            continue
        provenance[key] = entry

        if entry.get("absent") or key not in stored_values:
            values.pop(key, None)
            continue

        stored = stored_values[key]
        proposed = (derived_values or {}).get(key)
        values[key] = stored
        if proposed is not None and _canonical_entry(proposed) != _canonical_entry(stored):
            conflicts.append(
                {
                    "spec_key": key,
                    "reason": CONFLICT_REASON,
                    "proposed": proposed,
                    "stored": stored,
                }
            )

    return values, provenance, conflicts


# --------------------------------------------------------------------------- #
# the write
# --------------------------------------------------------------------------- #
_UNCHANGED = object()


def _status_for(provenance: Mapping, has_exceptions: bool) -> str:
    """needs_review > authored > derived.

    The documented-but-never-written `approved` is not reused: it reads as a
    verification claim, and a verification is per code, not per row.
    """
    if has_exceptions:
        return "needs_review"
    if any(_is_authored(entry) for entry in (provenance or {}).values()):
        return "authored"
    return "derived"


def write_spec_row(
    spec: ProductSpecifications,
    *,
    values: Mapping,
    provenance: Mapping,
    has_exceptions: bool = False,
    derived_hash: str | None = _UNCHANGED,
) -> None:
    """Assign the row's values, provenance, sentence and status. The only such site.

    `derived_hash` takes a sentinel rather than defaulting to None so a caller can leave
    it alone (derivation stamps its fingerprint; an authored write clears it on purpose).
    """
    values = dict(values or {})
    provenance = dict(provenance or {})

    spec.values = values
    spec.provenance = provenance
    # Rendered here so the only text spec search may match can never drift from the
    # values it describes.
    spec.rendered_text = render_spec_sentence(values)
    spec.status = _status_for(provenance, has_exceptions)
    if derived_hash is not _UNCHANGED:
        spec.derived_hash = derived_hash

    _mark_sanctioned(spec, values, provenance, spec.rendered_text)


# --------------------------------------------------------------------------- #
# the authored write path
# --------------------------------------------------------------------------- #
_OPS = ("set", "absent", "revert")


def _prepare(entry: Mapping, actor: Mapping | None) -> dict:
    spec_key = str(entry.get("spec_key") or "").strip()
    if not spec_key:
        raise AppException(
            status_code=400,
            message="A specification key is required.",
            code="product_spec_bad_value",
        )

    op = str(entry.get("op") or "set").strip().lower()
    if op not in _OPS:
        raise AppException(
            status_code=400,
            message=f"\"{op}\" is not something that can be done to a specification.",
            code="product_spec_bad_value",
        )

    source = str(entry.get("source") or DEFAULT_AUTHORED_SOURCE).strip().lower()
    if source not in AUTHORED_SOURCES:
        raise AppException(
            status_code=400,
            message=f"\"{source}\" is not a source a person can write.",
            code="product_spec_bad_value",
        )

    evidence = entry.get("evidence")
    if not evidence:
        who = (actor or {}).get("email") or "a person"
        evidence = f"set by {who}"

    return {
        "spec_key": spec_key,
        "op": op,
        "value": entry.get("value"),
        "unit": entry.get("unit"),
        "source": source,
        "evidence": str(evidence),
    }


def _apply(values: dict, provenance: dict, entry: dict) -> None:
    key = entry["spec_key"]
    stamp = {"source": entry["source"], "confidence": 1.0, "evidence": entry["evidence"]}

    if entry["op"] == "revert":
        # The key goes back to derivation entirely: no value of ours, no claim of ours.
        values.pop(key, None)
        provenance.pop(key, None)
        return

    if entry["op"] == "absent":
        values.pop(key, None)
        provenance[key] = {**stamp, "absent": True}
        return

    stored: dict = {"value": entry["value"]}
    if entry["unit"]:
        stored["unit"] = entry["unit"]
    values[key] = stored
    provenance[key] = stamp


def apply_spec_values(
    db: Session,
    product_code: str,
    entries: Sequence[Mapping],
    *,
    actor: Mapping | None = None,
    commit: bool = True,
) -> dict:
    """Write what a person set onto every company copy of a code, then re-derive it.

    Batch-capable from day one. One call per key would produce one fan-out, one rendered
    sentence rebuild and one verification diff PER KEY for what the user experienced as
    a single action, so a batch of one is the narrow case rather than the shape.

    The all-companies scope is taken HERE rather than left to the caller: a code exists
    once per company and a value a person set is true of the model, not of one company's
    copy of it. `derive_for_code` deliberately does the opposite - a request-time
    re-derive stays inside its caller's isolation - so the scope is held across the
    re-derive as well, or a copy outside the caller's company would be written here and
    then left with the cleared hash this call gave it.
    """
    prepared = [_prepare(entry, actor) for entry in entries]

    # Imported at call time: derivation imports this module, and this is the one edge
    # that would close the cycle.
    from app.services.product_spec_derivation import derive_for_code

    with company_scope(db, None):
        products = db.query(Product).filter(Product.product_code == product_code).all()
        if not products:
            # Unconditional, and BEFORE the empty-batch return: an unknown code is an
            # unknown code whether or not the caller had anything to write, and a
            # 404-or-200 that turns on the length of the batch is a contract nobody can
            # code against.
            raise AppException(
                status_code=404,
                message=f"No product carries the code {product_code}.",
                code="product_not_found",
            )

        if not prepared:
            return {"product_code": product_code, "rows_written": 0, "spec_keys": []}

        existing = {
            spec.product_id: spec
            for spec in db.query(ProductSpecifications)
            .filter(ProductSpecifications.product_id.in_([p.id for p in products]))
            # Locked for the duration: two people editing different keys on one code
            # would otherwise both read the row, both write their whole `values` dict
            # back, and the second commit would erase the first with nothing recording
            # that it happened. PR 3's verify guard reads the same rows in the same
            # transaction and needs the same lock.
            .with_for_update()
            .all()
        }
        # Only the interim status until the re-derive below recomputes it, but an
        # interim state that lies is still a lie if anything reads the row first.
        has_exceptions = (
            db.query(ProductSpecException)
            .filter(
                ProductSpecException.product_code == product_code,
                ProductSpecException.resolved_at.is_(None),
            )
            .count()
            > 0
        )

        rows_written = 0
        for product in products:
            spec = existing.get(product.id)
            if spec is None:
                spec = ProductSpecifications(product_id=product.id)
                db.add(spec)

            values = dict(spec.values or {})
            provenance = dict(spec.provenance or {})
            for entry in prepared:
                _apply(values, provenance, entry)

            # `derived_hash=None` is required, not tidiness: derivation's
            # skip-if-unchanged path would otherwise suppress the conflict computation
            # and leave the rendered sentence describing the old values.
            write_spec_row(
                spec,
                values=values,
                provenance=provenance,
                has_exceptions=has_exceptions,
                derived_hash=None,
            )
            rows_written += 1

        db.flush()
        # In the caller's transaction, so a conflict surfaces in the same click.
        derive_for_code(db, product_code, commit=False)

    if commit:
        db.commit()

    return {
        "product_code": product_code,
        "rows_written": rows_written,
        "spec_keys": [entry["spec_key"] for entry in prepared],
    }


# --------------------------------------------------------------------------- #
# the bypass backstop
# --------------------------------------------------------------------------- #
def _mark_sanctioned(spec, values, provenance, rendered_text) -> None:
    """Record WHAT this write put on the row, not merely that a write happened.

    The mark holds the objects themselves rather than their `id()`s. A dict that has
    been replaced can be freed and its address handed straight to its replacement, so an
    id comparison would occasionally sanction the very hand assignment this exists to
    catch.
    """
    setattr(spec, _SANCTIONED_ATTR, (values, provenance, rendered_text))


def _is_sanctioned(spec) -> bool:
    """True only while the row still carries exactly what `write_spec_row` put there.

    Per write, not per flush. `write_spec_row(...)` followed by a hand assignment and a
    commit is the shape a future contributor writes, and clearing a boolean at the next
    flush would let that through unreported: the hand assignment inherits the mark the
    sanctioned write left behind.

    An in-place mutation of the same dict is invisible here, but it is equally invisible
    to SQLAlchemy - a plain JSONB column has no change tracking - so there is nothing to
    report either way.
    """
    mark = getattr(spec, _SANCTIONED_ATTR, None)
    if mark is None:
        return False
    values, provenance, rendered_text = mark
    return (
        spec.values is values
        and spec.provenance is provenance
        and spec.rendered_text == rendered_text
    )


def _bypassed_columns(spec: ProductSpecifications, *, pending: bool) -> list[str]:
    state = inspect(spec)
    names: list[str] = []
    for name in WRITTEN_COLUMNS:
        history = state.attrs[name].history
        if not history.has_changes():
            continue
        # A row created empty and populated through the service a moment later is the
        # ordinary creation path, so an insert only counts when it carries content.
        if pending and not any(history.added or []):
            continue
        names.append(name)
    return names


def register_spec_write_backstop() -> None:
    """Log any write to the owned columns made around `write_spec_row`.

    A backstop, not the guard. The guard is the review rule that says those three
    columns are assigned in this module only; this is what tells us when something got
    past it, in production, without blocking a write that has already been decided.
    Idempotent, mirroring `register_product_spec_listeners`.
    """
    global _BACKSTOP_REGISTERED
    if _BACKSTOP_REGISTERED:
        return

    @event.listens_for(Session, "before_flush")
    def _collect(session, flush_context, instances):  # noqa: ANN001
        # Best-effort, like the report below. Reading attribute history can emit a lazy
        # load on an expired attribute or raise `ObjectDeletedError` on a row someone
        # else removed, and a diagnostic that 500s the write it only meant to observe
        # inverts its own purpose.
        try:
            pending = set(session.new)
            for obj in list(session.new) + list(session.dirty):
                if not isinstance(obj, ProductSpecifications):
                    continue
                if _is_sanctioned(obj):
                    continue
                columns = _bypassed_columns(obj, pending=obj in pending)
                if columns:
                    session.info.setdefault(_BYPASS_KEY, []).append(
                        (str(getattr(obj, "product_id", "") or ""), columns)
                    )
        except Exception:  # pragma: no cover - a backstop never blocks a write
            logger.warning("spec write backstop could not inspect the flush", exc_info=True)

    @event.listens_for(Session, "after_soft_rollback")
    def _discard(session, previous_transaction):  # noqa: ANN001
        # A write that was rolled back never happened, and reporting it against the
        # next commit would name the wrong caller. The limit: this drops EVERY pending
        # report on the session, so a rolled-back savepoint also discards bypasses
        # collected against the transaction around it. A missed warning is the cheap
        # side of that trade; tracking per-savepoint state is not worth it in a
        # diagnostic.
        session.info.pop(_BYPASS_KEY, None)

    @event.listens_for(Session, "after_commit")
    def _report(session):  # noqa: ANN001
        bypasses = session.info.pop(_BYPASS_KEY, None)
        if not bypasses:
            return
        try:
            for product_id, columns in bypasses:
                logger.warning(
                    "spec write bypass: %s written on product %s outside product_spec_write",
                    ", ".join(columns),
                    product_id,
                )
        except Exception:  # pragma: no cover - a post-commit side effect never raises
            pass

    _BACKSTOP_REGISTERED = True
