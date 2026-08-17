"""Who vouched for a code's specs, what withdrew that, and the queue of what is left.

Three things live here because they are one question asked from three angles:

  * `verification_block` / `verification_blocks` - the state a screen shows, DERIVED
    from the ledger rows and never stored (AC-D.2). A read never re-hashes values to
    decide the pill.
  * `verify_code` / `unverify_code` (and their bulk loops) - the only writers of that
    ledger. Bulk is a loop over the single-code function rather than a second path, so
    the bulk button can never become the way to stamp what the single button refuses
    (AC-D.16).
  * `invalidate_on_values_change` - the hook both spec writers call after their write
    loop, so a stamp cannot outlive the values it was made against (AC-D.3).

Plus `worklist`, the list the reviewer actually works from.

Nothing here writes `spec.values` / `spec.provenance` / `spec.rendered_text`: those
belong to `app/services/product_spec_write.py` and nowhere else.

Plan: `PLAN-spec-authoring-verification.md` (C5, C6, C7, C11). UAC: AC-D.1 to AC-D.26.
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime

from sqlalchemy import Text, and_, case, column, func, literal, literal_column, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.base import company_scope, get_company_scope
from app.models.product import Brand, Product, ProductCategory
from app.models.product_spec import (
    ProductSpecException,
    ProductSpecRegistry,
    ProductSpecVerification,
    ProductSpecifications,
)
from app.services.company_scope import build_company_predicate
from app.services.product_spec_write import canonical_values_hash, lock_product_code

# `supplier` arrives with the supplier portal in milestone 2. The party is a parameter
# everywhere rather than an assumption, so an internal withdrawal cannot reach a
# supplier's stamp (AC-D.26) and the invalidation hook can deliberately ignore it.
PARTY_INTERNAL = "internal"

REASON_VALUES_CHANGED = "values_changed"
REASON_MANUAL_UNVERIFY = "manual_unverify"

STATE_UNVERIFIED = "unverified"
STATE_VERIFIED = "verified"
STATE_NEEDS_REVERIFY = "needs_reverify"

SORT_DEFAULT = "default"
SORT_COVERAGE = "coverage"
SORT_CODE = "code"

# The keys a VerificationBlock carries, exactly. The frontend contract block in
# `specVerificationService.ts` lists the same set.
_EMPTY_BLOCK: dict = {
    "state": STATE_UNVERIFIED,
    "verified_by_name": None,
    "verified_at": None,
    "invalidated_at": None,
    "invalidated_reason": None,
    "invalidated_by_name": None,
    "invalidated_diff": None,
}


def _display_name(actor: Mapping | None) -> str | None:
    """A name a person recognises. A no-FK text user id cannot be joined for one."""
    actor = actor or {}
    return (actor.get("name") or "").strip() or actor.get("email") or None


def _actor_id(actor: Mapping | None) -> str | None:
    raw = (actor or {}).get("id")
    return str(raw) if raw is not None else None


# --------------------------------------------------------------------------- #
# the hash a stamp is made against
# --------------------------------------------------------------------------- #
def current_values_hash(db: Session, product_code: str) -> str:
    """The canonical hash of what this code's specs currently say.

    Read all-companies and from the lowest product id: every copy of a code holds the
    same values by construction (the authored write fans out, derivation fans out), so
    which copy the caller can see must not change the hash they are asked to echo back.
    A code with no spec row at all hashes the empty set rather than raising - "nothing
    is recorded" is a state a person can verify.
    """
    with company_scope(db, None):
        values = (
            db.query(ProductSpecifications.values)
            .join(Product, Product.id == ProductSpecifications.product_id)
            .filter(Product.product_code == product_code)
            .order_by(Product.id)
            .limit(1)
            .scalar()
        )
    return canonical_values_hash(values or {})


# --------------------------------------------------------------------------- #
# state, derived (AC-D.2)
# --------------------------------------------------------------------------- #
def _state_expr():
    """The four-branch rule of AC-D.2, in SQL, in ONE place.

    Every caller - the block a screen renders, the worklist's ordering, its state
    filter and its summary - reads the state from this expression, so the pill and the
    order can never disagree about what a row is.
    """
    return case(
        (ProductSpecVerification.invalidated_at.is_(None), literal(STATE_VERIFIED)),
        (
            ProductSpecVerification.invalidated_reason == REASON_MANUAL_UNVERIFY,
            literal(STATE_UNVERIFIED),
        ),
        else_=literal(STATE_NEEDS_REVERIFY),
    )


def _latest_select(party: str, product_codes: Sequence[str] | None = None):
    """One row per code: the active stamp if there is one, else the newest history row.

    DISTINCT ON rather than a per-code query, because the worklist needs this for a
    whole page and the ledger is small (at most one active row per code per party plus
    whatever has been withdrawn).
    """
    stmt = (
        select(
            ProductSpecVerification.product_code.label("product_code"),
            ProductSpecVerification.verified_by_name.label("verified_by_name"),
            ProductSpecVerification.verified_at.label("verified_at"),
            ProductSpecVerification.invalidated_at.label("invalidated_at"),
            ProductSpecVerification.invalidated_reason.label("invalidated_reason"),
            ProductSpecVerification.invalidated_by_name.label("invalidated_by_name"),
            ProductSpecVerification.invalidated_diff.label("invalidated_diff"),
            _state_expr().label("state"),
        )
        .where(ProductSpecVerification.party == party)
        .distinct(ProductSpecVerification.product_code)
        .order_by(
            ProductSpecVerification.product_code,
            # An active row always wins, whatever its dates say.
            ProductSpecVerification.invalidated_at.is_(None).desc(),
            ProductSpecVerification.verified_at.desc(),
            ProductSpecVerification.created_at.desc(),
        )
    )
    if product_codes is not None:
        stmt = stmt.where(ProductSpecVerification.product_code.in_(list(product_codes)))
    return stmt


def _block(row: Mapping | None) -> dict:
    if row is None:
        return dict(_EMPTY_BLOCK)
    return {
        "state": row["state"],
        "verified_by_name": row["verified_by_name"],
        "verified_at": row["verified_at"],
        "invalidated_at": row["invalidated_at"],
        "invalidated_reason": row["invalidated_reason"],
        "invalidated_by_name": row["invalidated_by_name"],
        "invalidated_diff": row["invalidated_diff"],
    }


def verification_blocks(
    db: Session, product_codes: Sequence[str], party: str = PARTY_INTERNAL
) -> dict[str, dict]:
    """One VerificationBlock per code, in one query. Unknown codes read unverified."""
    codes = list(dict.fromkeys(product_codes))
    blocks = {code: dict(_EMPTY_BLOCK) for code in codes}
    if not codes:
        return blocks
    for row in db.execute(_latest_select(party, codes)).mappings():
        blocks[row["product_code"]] = _block(row)
    return blocks


def verification_block(db: Session, product_code: str, party: str = PARTY_INTERNAL) -> dict:
    return verification_blocks(db, [product_code], party)[product_code]


# --------------------------------------------------------------------------- #
# invalidation, when the values move under a stamp (AC-D.3)
# --------------------------------------------------------------------------- #
def _same_entry(spec_key: str, was, now) -> bool:
    """Whether one key says the same thing on both sides.

    Hashing the single key rather than reaching for the write module's private
    per-entry helper keeps ONE module knowing that 407 and "407.0" are the same value.
    """
    return canonical_values_hash({spec_key: was}) == canonical_values_hash({spec_key: now})


def _changed_entries(before: Mapping | None, after: Mapping | None) -> list[dict]:
    """The was/now pairs a person needs to re-check, sorted so the diff is stable."""
    before = before or {}
    after = after or {}
    changed = []
    for spec_key in sorted(set(before) | set(after)):
        was = before.get(spec_key)
        now = after.get(spec_key)
        if _same_entry(spec_key, was, now):
            continue
        changed.append({"spec_key": spec_key, "was": was, "now": now})
    return changed


def invalidate_on_values_change(
    db: Session,
    product_code: str,
    *,
    before_values: Mapping | None,
    after_values: Mapping | None,
) -> bool:
    """Withdraw every active stamp for a code whose values just moved. Returns whether it did.

    Party-agnostic by construction: a supplier's stamp was made against the same values
    an internal one was, so a write that moves them invalidates both. `invalidated_by_*`
    stays null because no person did this.

    Compared on the canonical hash rather than on equality, so a re-stamped evidence
    string or a re-ordered feature list is not an edit anybody made.
    """
    if canonical_values_hash(before_values or {}) == canonical_values_hash(after_values or {}):
        return False

    rows = (
        db.query(ProductSpecVerification)
        .filter(
            ProductSpecVerification.product_code == product_code,
            ProductSpecVerification.invalidated_at.is_(None),
        )
        .all()
    )
    if not rows:
        return False

    stamped_at = datetime.utcnow()
    diff = {"changed": _changed_entries(before_values, after_values)}
    for row in rows:
        row.invalidated_at = stamped_at
        row.invalidated_reason = REASON_VALUES_CHANGED
        row.invalidated_diff = diff
        row.invalidated_by_user_id = None
        row.invalidated_by_name = None
    db.flush()
    return True


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #
def _serialise_exception(row: ProductSpecException) -> dict:
    return {
        "id": str(row.id),
        "spec_key": row.spec_key,
        "reason": row.reason,
        "proposed": row.proposed,
        "stored": row.stored,
    }


def _open_exceptions(db: Session, product_code: str) -> list[ProductSpecException]:
    return (
        db.query(ProductSpecException)
        .filter(
            ProductSpecException.product_code == product_code,
            ProductSpecException.resolved_at.is_(None),
        )
        .order_by(ProductSpecException.spec_key)
        .all()
    )


def verify_code(
    db: Session,
    product_code: str,
    *,
    values_hash: str,
    actor: Mapping | None,
    party: str = PARTY_INTERNAL,
) -> dict:
    """Stamp one code, or say precisely why not. Never raises for a guard.

    The route turns `values_changed` / `exceptions_open` into the two distinguishable
    409s (AC-D.4); a refusal is an outcome here rather than an exception so the bulk
    loop reports per code instead of failing the batch.

    The code's spec rows are locked FOR UPDATE - the same lock `apply_spec_values`
    takes - and the hash, the open exceptions and the active stamp are all re-read
    inside it, so a write landing between the screen rendering and this call is caught
    rather than stamped over. Does not commit; the caller owns the transaction.
    """
    with company_scope(db, None):
        products = db.query(Product).filter(Product.product_code == product_code).all()
        if not products:
            return {
                "product_code": product_code,
                "outcome": "not_found",
                "values_hash": canonical_values_hash({}),
                "verification": dict(_EMPTY_BLOCK),
                "exceptions": [],
            }

        # A code with no spec row at all has nothing to lock FOR UPDATE, so two
        # concurrent verifies of such a code would both pass the reads below. The
        # advisory lock is held to the end of the transaction and is keyed on the code
        # itself, so the serialisation does not depend on a row existing. The writers
        # take the SAME lock, from the same helper, or a first write could still land
        # between the reads below.
        lock_product_code(db, product_code)

        specs = (
            db.query(ProductSpecifications)
            .filter(ProductSpecifications.product_id.in_([p.id for p in products]))
            .order_by(ProductSpecifications.product_id)
            .with_for_update()
            .all()
        )
        current = canonical_values_hash((specs[0].values if specs else None) or {})

        if current != values_hash:
            return {
                "product_code": product_code,
                "outcome": "values_changed",
                "values_hash": current,
                "verification": verification_block(db, product_code, party),
                "exceptions": [],
            }

        open_rows = _open_exceptions(db, product_code)
        if open_rows:
            return {
                "product_code": product_code,
                "outcome": "exceptions_open",
                "values_hash": current,
                "verification": verification_block(db, product_code, party),
                "exceptions": [_serialise_exception(row) for row in open_rows],
            }

        outcome = "verified"
        try:
            # A savepoint, because the partial unique index is what actually enforces
            # "one active stamp per code per party": two requests can both pass the
            # read above, and the loser must come back as already_verified rather than
            # poisoning the caller's whole transaction.
            with db.begin_nested():
                db.add(
                    ProductSpecVerification(
                        id=str(uuid.uuid4()),
                        product_code=product_code,
                        party=party,
                        verified_by_user_id=_actor_id(actor),
                        verified_by_name=_display_name(actor),
                        verified_at=datetime.utcnow(),
                        values_hash=current,
                    )
                )
                db.flush()
        except IntegrityError:
            outcome = "already_verified"

        return {
            "product_code": product_code,
            "outcome": outcome,
            "values_hash": current,
            "verification": verification_block(db, product_code, party),
            "exceptions": [],
        }


def verify_codes_bulk(
    db: Session,
    items: Sequence[Mapping],
    *,
    actor: Mapping | None,
    party: str = PARTY_INTERNAL,
) -> list[dict]:
    """The same guards, code by code. COMMITS PER CODE; the caller must not commit again.

    Two departures from "loop, and let the caller commit once", both about a batch of
    up to 500:

      * the codes are locked in `product_code` order, so two bulk runs over overlapping
        selections queue behind each other instead of deadlocking, and a run racing
        `derive_all` (which walks its chunk in whatever order it was handed) can only
        wait, never cross;
      * each code commits as it is decided, which releases that code's locks at once
        and, more to the point, matches the contract: the response is per-code
        outcomes, so a code that fails at 400 must not silently un-stamp the 399 the
        reviewer was already told were done.

    Results come back in INPUT order whatever order they ran in, because that is the
    order the screen listed them in.
    """
    results: dict[int, dict] = {}
    ordered = sorted(enumerate(items), key=lambda pair: str(pair[1].get("product_code") or ""))
    for index, item in ordered:
        results[index] = verify_code(
            db,
            str(item.get("product_code") or ""),
            values_hash=str(item.get("values_hash") or ""),
            actor=actor,
            party=party,
        )
        db.commit()
    return [results[index] for index in range(len(items))]


# --------------------------------------------------------------------------- #
# unverify (AC-D.20, D.21, D.26)
# --------------------------------------------------------------------------- #
def _latest_row(db: Session, product_code: str, party: str) -> ProductSpecVerification | None:
    """The active stamp if there is one, else the newest row. Same rule as the block."""
    return (
        db.query(ProductSpecVerification)
        .filter(
            ProductSpecVerification.product_code == product_code,
            ProductSpecVerification.party == party,
        )
        .order_by(
            ProductSpecVerification.invalidated_at.is_(None).desc(),
            ProductSpecVerification.verified_at.desc(),
            ProductSpecVerification.created_at.desc(),
        )
        .first()
    )


def unverify_code(
    db: Session,
    product_code: str,
    *,
    actor: Mapping | None,
    party: str = PARTY_INTERNAL,
) -> dict:
    """Withdraw a stamp. No hash compare and no exception gate: a claim is being removed.

    Lands on `unverified`, never needs-re-verify - a withdrawal has no diff, and a
    re-verify prompt with an empty diff would misrepresent it. `verified_by` /
    `verified_at` stay exactly where they are, so the row still answers who vouched for
    this and who took it back. Idempotent: a code with no history, or one already
    withdrawn, is a no-op rather than an error.
    """
    row = _latest_row(db, product_code, party)
    if row is None or row.invalidated_reason == REASON_MANUAL_UNVERIFY:
        return {
            "product_code": product_code,
            "outcome": "no_change",
            "verification": verification_block(db, product_code, party),
        }

    # An active stamp, or one the system already withdrew because values moved: either
    # way the person is saying "treat this as never verified", so the pending re-check
    # is dismissed with it (AC-D.21) and the withdrawal's own time is what the row
    # carries.
    row.invalidated_at = datetime.utcnow()
    row.invalidated_reason = REASON_MANUAL_UNVERIFY
    row.invalidated_diff = None
    row.invalidated_by_user_id = _actor_id(actor)
    row.invalidated_by_name = _display_name(actor)
    db.flush()

    return {
        "product_code": product_code,
        "outcome": "unverified",
        "verification": verification_block(db, product_code, party),
    }


def unverify_codes_bulk(
    db: Session,
    product_codes: Sequence[str],
    *,
    actor: Mapping | None,
    party: str = PARTY_INTERNAL,
) -> list[dict]:
    """Withdraw a batch. COMMITS PER CODE, in code order, for the reasons
    `verify_codes_bulk` gives; results come back in the order the caller asked for."""
    results: dict[int, dict] = {}
    for index, code in sorted(enumerate(product_codes), key=lambda pair: str(pair[1])):
        results[index] = unverify_code(db, code, actor=actor, party=party)
        db.commit()
    return [results[index] for index in range(len(product_codes))]


# --------------------------------------------------------------------------- #
# the worklist
# --------------------------------------------------------------------------- #
def _have_expr():
    """How many specs this product actually holds, counted in the row's own JSON.

    A tombstoned key is not in `values` at all (the write path removes it), so it is
    already excluded; the `->'value'` test drops a key whose entry says nothing.
    """
    empty_object = literal_column("'{}'::jsonb")
    json_null = literal_column("'null'::jsonb")
    entry = (
        func.jsonb_each(func.coalesce(ProductSpecifications.values, empty_object))
        .table_valued(column("key", Text), column("value", JSONB))
        .alias("spec_entry")
    )
    return (
        select(func.count())
        .select_from(entry)
        .where(func.jsonb_typeof(func.coalesce(entry.c.value["value"], json_null)) != "null")
        .scalar_subquery()
    )


def _class_label_expr():
    """The class as every surface here reads it: what the specs say, else the category's.

    One definition, because the list column, the class facet/filter and the registry's
    `applies_when` gate must agree about what class a product is. They did not: the gate
    read `values['class']` alone, so a product whose class comes from its category (the
    common case - derivation only writes `class` when it reads one) failed every gated
    key and was told it needs fewer specs than it does.
    """
    return func.coalesce(
        ProductSpecifications.values["class"]["value"].astext, ProductCategory.class_label
    )


def _gate_value_expr(gate_key: str):
    """What a registry gate compares against. `class` has a second source; nothing else does."""
    if gate_key == "class":
        return _class_label_expr()
    return ProductSpecifications.values[gate_key]["value"].astext


def _applicable_expr(db: Session):
    """How many specs this product OUGHT to hold, from the registry, inline in the SQL.

    The registry is read once per request and folded into the statement as one CASE per
    gated key (52 keys today, 7 of them gated), so coverage costs no extra round trip
    per code - which is the whole reason `keys-for-product` is not called here (AC-D.7).

    A gated key counts only when the gate's own key holds a permitted value. That is
    deliberately STRICTER than `applicable_keys_for_code`, and the two are asking
    different questions: the picker offers a key when nothing contradicts it, because
    absence of a word is not evidence of absence; a denominator that counted every key
    whose gate is merely unknown would tell a reviewer a kitchen sink is missing a
    trap type.
    """
    ungated = 0
    gated_cases = []
    for row in (
        db.query(ProductSpecRegistry).filter(ProductSpecRegistry.is_active.is_(True)).all()
    ):
        clauses = []
        for gate_key, permitted in (row.applies_when or {}).items():
            allowed = [str(value).strip().lower() for value in (permitted or [])]
            if not allowed:
                # An empty list is no constraint at all, not an impossible one.
                continue
            clauses.append(func.lower(_gate_value_expr(gate_key)).in_(allowed))
        if not clauses:
            ungated += 1
            continue
        gated_cases.append(case((and_(*clauses), 1), else_=0))

    expression = literal(ungated)
    for gated in gated_cases:
        expression = expression + gated
    return expression


def _open_exceptions_expr():
    return (
        select(func.count())
        .select_from(ProductSpecException)
        .where(
            ProductSpecException.product_code == Product.product_code,
            ProductSpecException.resolved_at.is_(None),
        )
        .scalar_subquery()
    )


def _state_rank(state_column):
    """Needs-re-verify first, verified last (C6)."""
    return case(
        (state_column == STATE_NEEDS_REVERIFY, literal(0)),
        (state_column == STATE_VERIFIED, literal(2)),
        else_=literal(1),
    )


def worklist(
    db: Session,
    *,
    page: int = 1,
    limit: int = 25,
    query: str | None = None,
    state: str | None = None,
    class_label: str | None = None,
    include_discontinued: bool = False,
    sort: str = SORT_DEFAULT,
    direction: str = "asc",
    party: str = PARTY_INTERNAL,
) -> dict:
    """The list a reviewer works from: one row per code, in the caller's companies.

    A code exists once per company, so the list is de-duplicated to the lowest product
    id in scope - the row still carries a real `product_id` so clicking it opens a page
    the caller can actually see.

    `summary` counts the same set the list does MINUS the state filter, so "Verified N
    of M" stays honest while the reviewer is filtered down to what is left (AC-D.6).
    `classes` are the class filter's own options: the registry's `class` key is
    open-vocabulary and holds no allowed_values, so the labels have to come from the
    same expression the list groups by.

    PR NOTES - worklist cost (C7 set the threshold at p95 400 ms).

    Three statements plus the ledger read, in this shape for a measured reason. The
    slim projection (code, class, state) answers the facet, the progress line, the
    total AND the page's ordering; the coverage subquery, the 52-CASE applicable
    expression, the open-exception count and the values a row's hash is taken over are
    then fetched for the 25 codes on the page and nothing else.

    Measured on the prod-copy database, Sorento scope, page 1, 8,820 live codes,
    `time.perf_counter` around the whole call, 3 runs after one warm-up:

    | shape                                   | limit=25       | limit=50       |
    |-----------------------------------------|----------------|----------------|
    | one heavy subquery, scanned three times | 125/126/123 ms | 120/120/144 ms |
    | slim summary + heavy page query         | 197/181/163 ms | 251/156/156 ms |
    | slim ordering + page-only hydration     | 74/74/71 ms    | 94/85/73 ms    |

    The middle row is the change as first prescribed at review, and it is SLOWER. The
    summary and the count were never paying for the heavy expressions: Postgres prunes
    the unused output columns of a subquery it cannot pull up, and per-statement timing
    put them at 30 ms and 33 ms against the fat subquery. The page query was the whole
    cost, 130 ms of it, because those expressions were evaluated for all 8,820
    candidate rows before LIMIT threw 8,795 of them away. So: order and paginate on the
    slim set, then hydrate - ordering measures 35 ms and hydrating 25 codes 4 ms.

    Output is unchanged: `data`, `pagination` and `summary` were compared row for row
    against the previous implementation across eight parameter shapes (default, page 2,
    state filter, both coverage directions, code desc, search, include_discontinued).

    One shape got slower, deliberately: a class-filtered page went from 42-44 ms to
    72-143 ms, because `classes` is computed over the set the class filter has NOT
    narrowed. That is what stops the dropdown emptying itself, and it stays far inside
    the 400 ms threshold.
    """
    class_label_expr = _class_label_expr()
    latest = _latest_select(party).subquery("latest_verification")
    state_expr = func.coalesce(latest.c.state, literal(STATE_UNVERIFIED))

    # The caller's scope, applied by hand rather than left to the session listener: the
    # de-duplication below wraps the products select in a subquery, and a predicate
    # that silently stopped applying there would widen the list to every company.
    filters = []
    scope_predicate = build_company_predicate(Product, get_company_scope(db))
    if scope_predicate is not None:
        filters.append(scope_predicate)
    if not include_discontinued:
        filters.append(Product.is_discontinued.is_(False))
    if query:
        wild = f"%{query.strip()}%"
        filters.append(or_(Product.product_code.ilike(wild), Product.product_name.ilike(wild)))

    slim_columns = [
        Product.product_code.label("product_code"),
        class_label_expr.label("class_label"),
        state_expr.label("state"),
        func.row_number()
        .over(partition_by=Product.product_code, order_by=Product.id)
        .label("copy_rank"),
    ]
    if sort == SORT_COVERAGE:
        # The only ordering key that is not already slim. Added on demand rather than
        # always, so the default order pays nothing for a sort nobody asked for.
        slim_columns.append(_have_expr().label("have"))

    slim_candidates = (
        select(*slim_columns)
        .select_from(Product)
        .outerjoin(ProductSpecifications, ProductSpecifications.product_id == Product.id)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .outerjoin(latest, latest.c.product_code == Product.product_code)
        .where(*filters)
        .subquery("worklist_slim_candidates")
    )
    slim = (
        select(slim_candidates)
        .where(slim_candidates.c.copy_rank == 1)
        .subquery("worklist_slim")
    )

    # One aggregate answers three questions. Grouped by BOTH state and class because
    # the facet must ignore the class filter that the summary and the total obey:
    # filtering to a class must not empty the dropdown that did the filtering. So
    # `classes` is computed after the discontinued and search filters and before the
    # class and state ones.
    facet = db.execute(
        select(slim.c.state, slim.c.class_label, func.count()).group_by(
            slim.c.state, slim.c.class_label
        )
    ).all()

    classes = sorted({label for _state, label, _count in facet if label is not None})
    summary = {"total": 0, "verified": 0, "needs_reverify": 0, "unverified": 0}
    for row_state, row_class, count in facet:
        if class_label and row_class != class_label:
            continue
        summary[row_state] += count
        summary["total"] += count
    # The state filter narrows the list but not the summary, so the total it would
    # have counted is already in hand.
    total = summary.get(state, 0) if state else summary["total"]

    listing = select(slim.c.product_code)
    if class_label:
        listing = listing.where(slim.c.class_label == class_label)
    if state:
        listing = listing.where(slim.c.state == state)

    descending = str(direction or "asc").lower() == "desc"

    def _ordered(col):
        return col.desc() if descending else col.asc()

    if sort == SORT_COVERAGE:
        order_by = [_ordered(slim.c.have), slim.c.product_code.asc()]
    elif sort == SORT_CODE:
        order_by = [_ordered(slim.c.product_code)]
    else:
        # The default order is a narrative rather than a sort key ("what needs looking
        # at, grouped so one class is reviewed at a time"), so `direction` does not
        # reverse it.
        order_by = [
            _state_rank(slim.c.state),
            slim.c.class_label.asc().nullslast(),
            slim.c.product_code.asc(),
        ]

    page_codes = list(
        db.execute(
            listing.order_by(*order_by).limit(limit).offset(max(page - 1, 0) * limit)
        ).scalars()
    )

    return {
        "data": _hydrate_page(db, page_codes, filters, class_label_expr, state_expr, latest, party),
        "pagination": {"total": total, "page": page, "limit": limit},
        "summary": summary,
        "classes": classes,
    }


def _page_values_hashes(db: Session, page_codes: Sequence[str]) -> dict[str, str]:
    """The hash each row echoes back, read from the copy `current_values_hash` reads.

    The listing is company-scoped and de-duplicates to the lowest product id IN SCOPE;
    `current_values_hash` and `verify_code` read the lowest product id of ALL companies.
    Those are usually the same row, and when they are not (a scoped re-derive can move
    one copy without the other) a row hashed from the scoped copy is refused by the
    verify guard for ever, with a "changed while you were reviewing" that no reload can
    clear. One small unscoped read per page keeps exactly ONE answer to "what does this
    code currently say".
    """
    if not page_codes:
        return {}
    with company_scope(db, None):
        rows = db.execute(
            select(Product.product_code, ProductSpecifications.values)
            .select_from(Product)
            .outerjoin(ProductSpecifications, ProductSpecifications.product_id == Product.id)
            .where(Product.product_code.in_(list(page_codes)))
            .distinct(Product.product_code)
            .order_by(Product.product_code, Product.id)
        ).all()
    return {code: canonical_values_hash(values or {}) for code, values in rows}


def _hydrate_page(
    db: Session,
    page_codes: Sequence[str],
    filters: list,
    class_label_expr,
    state_expr,
    latest,
    party: str,
) -> list[dict]:
    """Everything a row shows, for the codes on this page and no others.

    Split out from `worklist` because it is where the expensive expressions live, and
    keeping them off the ordering query is the whole point: coverage, the open-exception
    count and the per-code hash are computed for 25 codes rather than 8,820.
    """
    if not page_codes:
        return []

    inner = (
        select(
            Product.id.label("product_id"),
            Product.product_code.label("product_code"),
            Product.product_name.label("product_name"),
            Product.is_discontinued.label("is_discontinued"),
            class_label_expr.label("class_label"),
            Brand.brand_name.label("brand_name"),
            _have_expr().label("have"),
            _applicable_expr(db).label("applicable"),
            _open_exceptions_expr().label("open_exceptions"),
            state_expr.label("state"),
            func.row_number()
            .over(partition_by=Product.product_code, order_by=Product.id)
            .label("copy_rank"),
        )
        .select_from(Product)
        .outerjoin(ProductSpecifications, ProductSpecifications.product_id == Product.id)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .outerjoin(Brand, Brand.id == Product.brand_id)
        .outerjoin(latest, latest.c.product_code == Product.product_code)
        .where(*filters, Product.product_code.in_(list(page_codes)))
        .subquery("worklist_candidates")
    )
    rows = select(inner).where(inner.c.copy_rank == 1)

    by_code = {row["product_code"]: row for row in db.execute(rows).mappings().all()}
    blocks = verification_blocks(db, list(page_codes), party)
    hashes = _page_values_hashes(db, page_codes)

    data = []
    # The page query answers in whatever order it likes; the ordering query already
    # decided, so the codes are put back in ITS order rather than re-sorted here.
    for code in page_codes:
        row = by_code.get(code)
        if row is None:
            continue
        data.append(
            {
                "product_id": str(row["product_id"]),
                "product_code": row["product_code"],
                "product_name": row["product_name"],
                "class_label": row["class_label"],
                "brand_name": row["brand_name"],
                "is_discontinued": bool(row["is_discontinued"]),
                "coverage": {"have": row["have"], "applicable": row["applicable"]},
                "open_exceptions": row["open_exceptions"],
                # NOT hashed from the row above: that is the in-scope copy, and the
                # verify guard compares against the all-companies one.
                "values_hash": hashes[row["product_code"]],
                "verification": blocks[row["product_code"]],
            }
        )
    return data
