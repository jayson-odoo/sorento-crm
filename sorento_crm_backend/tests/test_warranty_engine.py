"""S2 gate - the deterministic warranty entitlement engine (AC-D1 to AC-D7, AC-D15).

S2 is the slice whose whole virtue is that it is boring and provable. It answers one
question - "what cover does this thing carry" - from four lookup tables and a date,
and it answers it the same way every time. So the golden set is written here as
failing tests before a line of implementation exists (`PRINCIPLES.md` step 4).

**S2b is out of scope and nothing here touches it.** `consumer_profiles`,
`consumer_purchases`, `consumer_purchase_lines`, `warranty_assessments`, AC-D8's
auto-created Registration, AC-D9's E2E half, AC-D10 to AC-D12 and AC-D14 all belong
to the consumer module or to an AI surface. What makes the split real is the
signature: ``resolve`` takes plain values, never a purchase row, so the engine can
be proven with no consumer table in existence.

Seven things shape this suite, and every one of them is a place the AC is silent or
self-contradictory. They are decided here rather than left to the implementer,
because an entitlement engine that answers "not covered" for a reason nobody wrote
down is worse than one that refuses to answer.

1. **A gap in the policy calendar is not an absence of cover.** AC-D6 says
   entitlement is judged against the policy in force ON THE PURCHASE DATE. It says
   nothing about a purchase date that falls in no policy window, which is one
   mistyped ``effective_from`` away at all times. An implementation that returns an
   empty list there is indistinguishable, at the CS screen, from "this product has
   no cover" - a wrong answer given to a customer because of a data-entry hole. So
   ``resolve`` NEVER returns an empty sequence: no policy yields exactly one entry
   with verdict ``unknown``, a policy with no term for the kind yields ``no_term``,
   and neither may be reported as ``expired``.

2. **The golden set is dated BEFORE Warranty Policy v15 exists.** Five of the seven
   golden rows are purchases from 2015, 2024 and 2025; the policy is Version 15,
   March 2026. Read strictly, rule 1 above then makes five golden rows ``unknown``
   and the slice cannot satisfy its own acceptance test. The resolution is in the
   DATA, not in the algorithm: the v15 row is seeded backdated, as the only policy
   Sorento has on record, so it is genuinely in force for those purchases. The
   alternative - clamping an out-of-range date to the nearest policy - was rejected
   because it silently judges a 2015 purchase by 2026 terms, which is the one thing
   AC-D6 exists to forbid.

3. **Two overlapping policy windows make the engine non-deterministic**, and
   overlapping windows are reachable by ordinary data entry (nothing in the schema
   prevents them). Pinned: the policy with the LATEST ``effective_from`` answers,
   ties broken on ``id``, and the answering ``policy_id`` is reported on every
   verdict so an overlap is diagnosable from the output instead of invisible.

4. **Empty means "all defects", which is the footgun this codebase has already been
   bitten by** (an empty rule-engine ``rules[]`` matching everything silently). It
   is kept, because a term with no defect restriction is the normal case and forcing
   every row to enumerate every defect would be worse - but empty, NULL and
   populated-but-not-matching are pinned as three distinct behaviours, and a defect
   the caller did not state can never convict a restricted term.

5. **Kind resolution must be total and deterministic or the whole engine is not.**
   AC-D2 gives four match types and a ``priority`` column and says "most specific
   wins" without saying what specificity means or which way ``priority`` sorts. Both
   are declared as data here (``KIND_RULE_SPECIFICITY``, higher priority wins) so
   two rules can never leave the answer to row order.

6. **The expiry date itself is covered.** The golden set says "covered to
   2030-10-16" and never says whether the 16th is inside or outside. The
   customer-favourable reading is taken: ``as_of <= expiry`` is covered. It follows
   that the golden row "Sensor Tap ... expired 2025-06-01" is loose language - that
   term EXPIRES on 2025-06-01 and the claim is refused from 2025-06-02.

7. **Month arithmetic clamps, it never rolls forward.** 31 January plus one month is
   29 February, not 2 March. A rolling implementation gives a customer a day of
   cover they were not sold, or takes one away, depending on the month.

Everything runs on Postgres via ``blank_session`` - never sqlite, which coerces a
mostly-zero uuid to an integer under NUMERIC affinity. Rows are marked with
``TEST_PREFIX`` and discarded by the outer rollback; nothing is counted across a
shared table.

Run: venv/bin/python -m pytest tests/test_warranty_engine.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import pathlib
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.models.lookup import LookupOption, LookupSet

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

# ---------------------------------------------------------------- the contract
#
# Names S2 is expected to add. They are constants rather than inline strings so the
# implementer can read the whole contract in one screen, and so a rename is one edit.

# The four tables are one module because they are one concept with one lifecycle:
# a Kind is meaningless without the rules that reach it, and a Term without the
# policy that dates it. Splitting them across files is how the policy window ends up
# being read in two places.
WARRANTY_MODELS = "app.models.warranty"

# One module owns the algorithm. Three callers are already known (the CS verdict
# panel in S2b, the consumer portal in S3, the AI policy answer in S2b+), and the
# moment two of them compute an expiry the answers diverge.
WARRANTY_SERVICE = "app.services.warranty_service"

# The v15 seed. A script, not a runtime path: the policy is a document Sorento
# publishes, not something the app derives.
SEED_MODULE = "scripts.seed_warranty_policy_v15"

# AC-D5 needs a defect-type vocabulary and there is no such thing in this codebase
# today. The nearest existing set, ``complaints_defects_discovered``, enumerates WHEN
# a defect was noticed ("Upon delivery after unloading"), not WHAT it is. So S2 seeds
# its own set - see test_the_seed_creates_the_defect_type_vocabulary.
DEFECT_TYPE_SET_KEY = "complaints_defect_type"

# The five verdicts from the plan's schema comment, pinned so a sixth cannot appear
# quietly in one branch of the algorithm.
VERDICTS = frozenset({"covered", "expired", "defect_not_covered", "no_term", "unknown"})

# AC-D2's four match types.
KIND_RULE_MATCH_TYPES = ("category", "model_prefix", "model_list", "series")

# "Most specific wins", made concrete. An explicit model list is an enumeration of
# exactly which things it covers; a prefix covers a family; a series is a marketing
# grouping that spans families; a category is the whole merchandise bucket and is
# brand-split besides (ADR-0010). Declared as a constant, not inferred from
# behaviour, because it is the thing a later reader must not re-decide by accident.
KIND_RULE_SPECIFICITY = ("model_list", "model_prefix", "series", "category")

# Asia/Kuala_Lumpur, fixed UTC+8, no DST. Mirrors sla_service.MALAYSIA_TZ.
MALAYSIA_TZ = timezone(timedelta(hours=8))

# The 12 kinds AC-D1 names outright, out of the 31 it claims.
NAMED_KINDS = (
    "Water Closet",
    "Urinal Bowl",
    "Squatting Pan",
    "Electronic Seat Cover",
    "Intelligent Water Closet",
    "Tankless Water Closet",
    "Wash Basin",
    "LED Mirror",
    "Bathroom Furniture",
    "Mirror Cabinet",
    "Stop Valve",
    "Sensor Tap",
)

# AC-D4's three parts of a Water Closet, verbatim.
WATER_CLOSET_PARTS = ("Ceramic Body", "Flushing Fittings", "Seat Cover Soft Close")

# The oldest purchase date in the golden set. See point 2 in the module docstring.
OLDEST_GOLDEN_PURCHASE = date(2015, 1, 1)


# ----------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# ----------------------------------------------------------------------- helpers


def _module(dotted: str, why: str):
    """Import a module S2 is expected to add, or fail naming the contract."""
    if importlib.util.find_spec(dotted) is None:
        raise AssertionError(f"{dotted} does not exist. {why}")
    return importlib.import_module(dotted)


def _models():
    return _module(
        WARRANTY_MODELS,
        "S2 adds warranty_product_kinds, warranty_kind_rules, warranty_policies and "
        "warranty_terms. They are one concept with one lifecycle and belong in one "
        "models module.",
    )


def _model(name: str):
    module = _models()
    cls = getattr(module, name, None)
    assert cls is not None, f"{WARRANTY_MODELS}.{name} must exist."
    return cls


def _fn(dotted: str, name: str, signature: str):
    module = _module(dotted, f"{name}{signature} lives here.")
    fn = getattr(module, name, None)
    assert callable(fn), f"{dotted}.{name}{signature} must exist."
    return fn


def _resolve():
    return _fn(
        WARRANTY_SERVICE,
        "resolve",
        "(db, *, kind_id, purchase_date, defect_type_id=None, registered=False, as_of=None)",
    )


def _resolve_kind():
    return _fn(
        WARRANTY_SERVICE,
        "resolve_kind",
        "(db, *, product_code=None, category_code=None, product_name=None)",
    )


def _resolve_replacement():
    return _fn(
        WARRANTY_SERVICE,
        "resolve_replacement",
        "(*, source_expiry, source_is_lifetime=False, replaced_on, as_of=None)",
    )


def _seed():
    module = _module(
        SEED_MODULE,
        "AC-D1 seeds 31 Kinds plus the v15 policy and its terms. A seed is a script, "
        "not a runtime path: the policy is a document Sorento publishes.",
    )
    fn = getattr(module, "seed", None)
    assert callable(fn), f"{SEED_MODULE}.seed(db) must exist."
    return fn


def _columns(model):
    return {c.key: c for c in model.__table__.columns}


def _field(entry, name: str):
    """Read a field off a verdict, whether it is an object or a mapping.

    The FIELD NAMES are the contract; the container is not. A dataclass, a pydantic
    model and a dict are all acceptable and none of them should cost a red test.
    """
    if isinstance(entry, dict):
        assert name in entry, f"verdict is missing field {name!r}: {entry!r}"
        return entry[name]
    assert hasattr(entry, name), f"verdict is missing field {name!r}: {entry!r}"
    return getattr(entry, name)


def _by_part(result) -> dict:
    return {_field(e, "part_name"): e for e in result}


def _verdicts(result) -> list:
    return [_field(e, "verdict") for e in result]


# --------------------------------------------------------------- seed helpers
#
# Each one builds real rows in the blank schema. Postgres enforces the foreign keys
# sqlite ignored, so every parent is created for real.


def _kind(db, name: str = "kind", *, code: str | None = None):
    cls = _model("WarrantyProductKind")
    row = cls(
        id=str(uuid.uuid4()),
        code=(code or unique_code(name))[:64],
        name=f"{TEST_PREFIX} {name}"[:255],
    )
    db.add(row)
    db.flush()
    return row


def _policy(
    db,
    *,
    version: str | None = None,
    effective_from: date = date(2000, 1, 1),
    effective_to: date | None = None,
    policy_text: str | None = None,
):
    cls = _model("WarrantyPolicy")
    row = cls(
        id=str(uuid.uuid4()),
        version=(version or unique_code("v"))[:32],
        effective_from=effective_from,
        effective_to=effective_to,
        policy_text=policy_text,
    )
    db.add(row)
    db.flush()
    return row


def _term(
    db,
    policy,
    kind,
    part_name: str = "Body",
    *,
    duration_months: int | None = None,
    is_lifetime: bool = False,
    covered_defect_type_ids=None,
    installation_included: bool = False,
    registration_bonus_months: int | None = None,
    exclusions: str | None = None,
):
    cls = _model("WarrantyTerm")
    row = cls(
        id=str(uuid.uuid4()),
        policy_id=policy.id,
        kind_id=kind.id,
        part_name=part_name,
        duration_months=duration_months,
        is_lifetime=is_lifetime,
        covered_defect_type_ids=covered_defect_type_ids,
        installation_included=installation_included,
        registration_bonus_months=registration_bonus_months,
        exclusions=exclusions,
    )
    db.add(row)
    db.flush()
    return row


def _rule(db, kind, match_type: str, match_value: str, *, priority: int = 0):
    cls = _model("WarrantyKindRule")
    row = cls(
        id=str(uuid.uuid4()),
        kind_id=kind.id,
        match_type=match_type,
        match_value=match_value,
        priority=priority,
    )
    db.add(row)
    db.flush()
    return row


def _defect(db, label: str) -> str:
    """A defect type as a lookup option, returning its id.

    Scoped to a per-test set so nothing collides with the real
    ``complaints_defects_discovered`` rows, and so no assertion here ever counts
    across a shared table.
    """
    key = unique_code("defectset")[:80]
    lookup_set = LookupSet(
        id=str(uuid.uuid4()),
        set_key=key,
        name=f"{TEST_PREFIX} defect types",
    )
    db.add(lookup_set)
    db.flush()
    option = LookupOption(
        id=str(uuid.uuid4()),
        set_id=lookup_set.id,
        value=f"{TEST_PREFIX}-{label}"[:150],
        label=label[:255],
        sort_order=0,
    )
    db.add(option)
    db.flush()
    return option.id


def _simple_case(
    db,
    *,
    effective_from: date = date(2000, 1, 1),
    effective_to: date | None = None,
    part_name: str = "Body",
    **term_kw,
):
    """One kind, one policy, one term. The shape most algorithm tests need."""
    kind = _kind(db)
    policy = _policy(db, effective_from=effective_from, effective_to=effective_to)
    term = _term(db, policy, kind, part_name, **term_kw)
    return kind, policy, term


@contextmanager
def _without_the_xor_constraint(db):
    """Seed a term shape the DATABASE refuses but the ENGINE must still answer about
    (AC-P27).

    S7b added `ck_warranty_terms_duration_xor_lifetime` (AC-P3a / AC-P19) to
    `WarrantyTerm.__table_args__`, so a term with neither a duration nor lifetime -
    and one with both - can no longer be written through the ORM. Two tests below
    exist precisely to ask what the engine ANSWERS about those rows, and after the
    constraint they failed at `_term()`'s flush, never at an assertion.

    **Strict at write, tolerant at read** - the same layer split AC-P24 already ruled
    for match types. The constraint stops an admin creating a term that can never be
    judged; `_judge_term`'s two branches are DEFENCE, and defence must outlive the
    guard that makes it rare:

      - 41 `warranty_terms` rows were written before this constraint existed;
      - a seed script, a migration backfill and a psql session all bypass the
        service, and a future migration can drop the constraint entirely;
      - a branch unreachable through the ORM today is not unreachable in the
        database, and if the guard ever goes these branches are the only thing left.

    So the seeding mechanism changes and the assertions do not. Used by exactly two
    tests; anything else wanting this is describing a shape the product forbids.

    Contained by the transaction, not by this helper. `blank_session` runs every test
    inside one outer transaction that is rolled back at teardown, and Postgres DDL is
    transactional - so the DROP dies with the test that issued it and the next test
    meets the constraint again. It is deliberately NOT re-added on the way out:
    re-adding validates existing rows, and the row this helper exists to seed is
    exactly the one that would fail that validation.

    That containment was verified rather than assumed, by running both tests below
    together with `test_warranty_config_guards.py`'s raw-INSERT rejection test in the
    same session and confirming the third still gets its CheckViolation. A leak here
    would silently disarm the guard for every test that ran afterwards - the same
    shape as the shared-metadata leak in PRINCIPLES.md's sqlite ruling, where the
    breakage surfaced only in a full-suite run, in a file that touched nothing
    related.
    """
    db.execute(
        sa.text(
            "ALTER TABLE warranty_terms "
            "DROP CONSTRAINT IF EXISTS ck_warranty_terms_duration_xor_lifetime"
        )
    )
    yield


def _only(result):
    assert len(result) == 1, f"expected exactly one verdict, got {len(result)}: {result!r}"
    return result[0]


# =============================================================================
# Schema - AC-D1, AC-D2, AC-D3
# =============================================================================


def test_the_four_warranty_tables_exist_with_the_names_the_plan_declares():
    """AC-D1, AC-D2, AC-D3. Four tables, and only these four in S2.

    ``warranty_assessments`` is deliberately absent: it hangs off
    ``complaint_product_lines`` and belongs to S2b with the consumer module. Its
    absence is asserted in ``tests/test_warranty_scope_guard.py`` so this file stays
    entirely red.
    """
    expected = {
        "WarrantyProductKind": "warranty_product_kinds",
        "WarrantyKindRule": "warranty_kind_rules",
        "WarrantyPolicy": "warranty_policies",
        "WarrantyTerm": "warranty_terms",
    }
    for class_name, table in expected.items():
        cls = _model(class_name)
        assert cls.__tablename__ == table, (
            f"{class_name}.__tablename__ is {cls.__tablename__!r}, expected {table!r}."
        )


def test_a_kind_is_addressable_by_a_stable_code_and_shows_a_consumer_label():
    """AC-D1 plus the consumer chooser it exists to feed.

    ``code`` is what a seed re-runs against and what a rule is read beside; ``name``
    is internal; ``consumer_label`` is what a homeowner is shown, which is a
    different string from either (ADR-0010: the Kind is the level a Consumer
    recognises).
    """
    columns = _columns(_model("WarrantyProductKind"))
    for name in ("code", "name", "consumer_label", "sort_order", "is_active"):
        assert name in columns, f"warranty_product_kinds.{name} is missing (AC-D1)."
    assert not columns["code"].nullable, (
        "warranty_product_kinds.code must be NOT NULL - it is the seed's idempotence "
        "key, and a null one makes the seed create duplicates on every run."
    )
    table = _model("WarrantyProductKind").__table__
    unique_on_code = (
        bool(columns["code"].unique)
        or any(
            set(c.columns.keys()) == {"code"}
            for c in table.constraints
            if isinstance(c, sa.UniqueConstraint)
        )
        or any(ix.unique and set(ix.columns.keys()) == {"code"} for ix in table.indexes)
    )
    assert unique_on_code, (
        "warranty_product_kinds.code must be UNIQUE (the plan's schema block). "
        "Without it the seed's upsert has nothing to be idempotent against."
    )


def test_kind_rules_carry_match_type_value_and_priority_and_point_at_a_kind():
    """AC-D2. The mapping layer is data, not a column on products."""
    cls = _model("WarrantyKindRule")
    columns = _columns(cls)
    for name in ("kind_id", "match_type", "match_value", "priority"):
        assert name in columns, f"warranty_kind_rules.{name} is missing (AC-D2)."
    assert "warranty_product_kinds.id" in {
        fk.target_fullname for fk in columns["kind_id"].foreign_keys
    }, "warranty_kind_rules.kind_id must foreign-key warranty_product_kinds.id."


def test_policies_are_versioned_and_dated_and_keep_the_document():
    """AC-D6 plus BRD Req #12.

    ``effective_from`` is NOT NULL because a policy with no start date cannot be "in
    force on the purchase date" at all; ``effective_to`` is nullable because exactly
    one policy is current at any time and it has no end yet.
    """
    columns = _columns(_model("WarrantyPolicy"))
    for name in ("version", "effective_from", "effective_to", "policy_text", "source_attachment_id"):
        assert name in columns, f"warranty_policies.{name} is missing (AC-D6)."
    assert not columns["effective_from"].nullable, (
        "warranty_policies.effective_from must be NOT NULL. A null start date makes "
        "'the policy in force on the purchase date' unanswerable, and the row would "
        "silently never match."
    )
    assert columns["effective_to"].nullable, (
        "warranty_policies.effective_to must be nullable - the current policy has no "
        "end date, and forcing a sentinel like 9999-12-31 puts a magic value in the "
        "comparison."
    )
    assert "attachments.id" in {
        fk.target_fullname for fk in columns["source_attachment_id"].foreign_keys
    }, (
        "warranty_policies.source_attachment_id must foreign-key attachments.id - "
        "the PDF is the evidence behind policy_text (BRD Req #12)."
    )


def test_terms_carry_part_duration_defect_scope_installation_and_bonus():
    """AC-D3, the four dimensions ADR-0010 says an integer cannot hold."""
    columns = _columns(_model("WarrantyTerm"))
    for name in (
        "policy_id",
        "kind_id",
        "part_name",
        "duration_months",
        "is_lifetime",
        "covered_defect_type_ids",
        "installation_included",
        "registration_bonus_months",
        "qualifications",
        "exclusions",
    ):
        assert name in columns, f"warranty_terms.{name} is missing (AC-D3)."

    assert columns["duration_months"].nullable, (
        "warranty_terms.duration_months must be nullable - a lifetime term has no "
        "number of months."
    )
    assert not columns["installation_included"].nullable, (
        "warranty_terms.installation_included must be NOT NULL. It decides who pays "
        "for the callout (clause 15); a null would be rendered as 'no' by every "
        "consumer of it and nobody would notice."
    )
    for target, name in (("warranty_policies.id", "policy_id"), ("warranty_product_kinds.id", "kind_id")):
        assert target in {fk.target_fullname for fk in columns[name].foreign_keys}, (
            f"warranty_terms.{name} must foreign-key {target}."
        )


def test_covered_defect_type_ids_is_a_uuid_array():
    """AC-D3 / AC-D5. The plan's schema says ``uuid[]`` and it should stay uuid[].

    A ``varchar[]`` holds the same characters and cannot be compared to a uuid
    column without a cast, which is how a defect-scope check ends up silently
    matching nothing. Postgres will not catch it: an array column carries no foreign
    key either way (see the note in the report - a deleted defect type narrows a
    term's scope with nothing to stop it).
    """
    column = _columns(_model("WarrantyTerm"))["covered_defect_type_ids"]
    assert isinstance(column.type, sa.ARRAY), (
        f"warranty_terms.covered_defect_type_ids must be an ARRAY, got {column.type!r}. "
        "A term covers a SET of defects; a comma-joined string is not a set."
    )
    rendered = column.type.compile(dialect=postgresql.dialect())
    assert rendered == "UUID[]", (
        f"warranty_terms.covered_defect_type_ids compiles to {rendered}, expected "
        "UUID[] (the plan's schema block)."
    )


def test_the_warranty_tables_are_in_a_migration_not_only_on_the_model():
    """The ADR-0012 failure, pinned.

    ``blank_session`` builds the schema from ``Base.metadata``, so a model with no
    migration behind it passes every other test in this file and is absent in
    production.
    """
    versions = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
    sources = [p.read_text(encoding="utf-8", errors="ignore") for p in versions.glob("*.py")]
    missing = [
        table
        for table in (
            "warranty_product_kinds",
            "warranty_kind_rules",
            "warranty_policies",
            "warranty_terms",
        )
        if not any(table in src and "create_table" in src for src in sources)
    ]
    assert not missing, (
        "No alembic revision creates " + ", ".join(missing) + ". A table that exists "
        "only on the model is green in every test here and absent in production."
    )


# =============================================================================
# Kind resolution - AC-D2, and the precedence AC-D2 does not state
# =============================================================================


def test_a_kind_resolves_from_a_category_code(db):
    """AC-D2, the broadest rule. ``match_value`` is a ``product_categories.code``."""
    resolve_kind = _resolve_kind()
    kind = _kind(db, "wc")
    _rule(db, kind, "category", "SRT-WC")
    got = resolve_kind(db, product_code="SRTWC8152-RL", category_code="SRT-WC")
    assert got is not None and got.id == kind.id, (
        "A category rule did not resolve. ADR-0010: SRT-WC / CB-WC / M-WC / BRT-WC "
        "are four brands of the same physical thing, so category is how most "
        "products reach a Kind."
    )


def test_a_kind_resolves_from_a_model_prefix(db):
    resolve_kind = _resolve_kind()
    kind = _kind(db, "wc")
    _rule(db, kind, "model_prefix", "SRTWC")
    got = resolve_kind(db, product_code="SRTWC8152-RL-RG")
    assert got is not None and got.id == kind.id


def test_a_kind_resolves_from_an_explicit_model_list(db):
    """AC-D2's ``SRTMCB8071-BL, SRTMCB6071-BL, SRTMCB5060-BL, SRTMCB5061-BL``.

    Four codes in one ``match_value``: the AC prints them as a comma-separated list
    and the column is ``text``, so that is the shape. Whitespace after the commas is
    in the AC too, and must not defeat the match.
    """
    resolve_kind = _resolve_kind()
    kind = _kind(db, "mirror cabinet")
    _rule(
        db,
        kind,
        "model_list",
        "SRTMCB8071-BL, SRTMCB6071-BL, SRTMCB5060-BL, SRTMCB5061-BL",
    )
    for code in ("SRTMCB8071-BL", "SRTMCB5061-BL"):
        got = resolve_kind(db, product_code=code)
        assert got is not None and got.id == kind.id, f"{code} did not resolve."
    assert resolve_kind(db, product_code="SRTMCB9999-BL") is None, (
        "A model list is an enumeration, not a prefix - a code that is not in it "
        "must not match it."
    )


def test_a_kind_resolves_from_a_named_series(db):
    """AC-D2's *Honeycomb Series*, and a gap in the schema.

    THERE IS NO SERIES COLUMN. ``products`` carries code, name, category and brand
    and nothing else that could hold a series, so a ``series`` rule has nothing to
    compare against unless it reads the product NAME. That is the reading pinned
    here: case-insensitive substring of ``product_name``. It is a decision this file
    takes because the AC names a match type the schema cannot satisfy - see the
    report.
    """
    resolve_kind = _resolve_kind()
    kind = _kind(db, "honeycomb basin")
    _rule(db, kind, "series", "Honeycomb")
    got = resolve_kind(
        db, product_code="SRTWB1234", product_name="Wash Basin honeycomb series 600mm"
    )
    assert got is not None and got.id == kind.id, (
        "A series rule did not match on product_name. There is no products.series "
        "column, so the name is the only place the series can be read from."
    )


def test_matching_ignores_case(db):
    """Product codes arrive from OCR, WhatsApp and staff typing. Case is noise."""
    resolve_kind = _resolve_kind()
    kind = _kind(db, "wc")
    _rule(db, kind, "model_prefix", "SRTWC")
    got = resolve_kind(db, product_code="srtwc8152-rl")
    assert got is not None and got.id == kind.id


def test_kind_resolution_needs_no_products_row(db):
    """AC-C17's payoff, which is the reason the Kind layer exists at all.

    ``SRTWC8152`` matches three real variants and resolves to none of them. If Kind
    resolution required a ``products`` row, cover could not be decided until CS had
    pinned the variant - and deciding cover BEFORE the exact model is known is the
    entire justification for the extra layer (ADR-0010).
    """
    resolve_kind = _resolve_kind()
    kind = _kind(db, "wc")
    _rule(db, kind, "model_prefix", "SRTWC")
    got = resolve_kind(db, product_code="SRTWC8152")
    assert got is not None and got.id == kind.id, (
        "Kind resolution must work from a raw claimed code alone, with no product "
        "row and no category."
    )


def test_no_matching_rule_returns_none_rather_than_raising(db):
    """Nothing in this journey blocks (AC-C14). An unknown code is a normal event."""
    resolve_kind = _resolve_kind()
    _kind(db, "wc")
    assert resolve_kind(db, product_code="ZZT-NOTHING-MATCHES-THIS") is None


def test_the_specificity_order_is_declared_as_data():
    """AC-D2 says "most specific wins" and never says what specificity is.

    Pinned as a constant rather than inferred from behaviour, because the order has
    to survive somebody adding a fifth match type: a new type with no declared rank
    is a silent coin flip, while a new entry in this tuple is a decision somebody
    made on purpose.
    """
    module = _module(WARRANTY_SERVICE, "The specificity order lives beside the algorithm.")
    declared = getattr(module, "KIND_RULE_SPECIFICITY", None)
    assert declared is not None, (
        f"{WARRANTY_SERVICE}.KIND_RULE_SPECIFICITY must exist and be "
        f"{KIND_RULE_SPECIFICITY}."
    )
    assert tuple(declared) == KIND_RULE_SPECIFICITY, (
        f"KIND_RULE_SPECIFICITY is {tuple(declared)}, expected {KIND_RULE_SPECIFICITY}: "
        "a model list enumerates exactly what it covers, a prefix covers a family, a "
        "series spans families, and a category is the whole brand-split merchandise "
        "bucket."
    )
    assert set(declared) == set(KIND_RULE_MATCH_TYPES), (
        "Every match type must have a declared rank, or a rule of that type competes "
        "with an undefined specificity."
    )


@pytest.mark.parametrize(
    "narrow,broad",
    [
        ("model_list", "model_prefix"),
        ("model_prefix", "series"),
        ("series", "category"),
        ("model_list", "category"),
    ],
)
def test_the_narrower_match_type_wins_at_equal_priority(db, narrow, broad):
    """AC-D2 "most specific wins", exercised pair by pair.

    Both rules match the same product at the same ``priority``. Without a declared
    order this is decided by row order, which is to say by insertion accident.
    """
    resolve_kind = _resolve_kind()
    values = {
        "model_list": "SRTWC8152-RL",
        "model_prefix": "SRTWC",
        "series": "Honeycomb",
        "category": "SRT-WC",
    }
    narrow_kind = _kind(db, f"narrow-{narrow}")
    broad_kind = _kind(db, f"broad-{broad}")
    _rule(db, broad_kind, broad, values[broad], priority=0)
    _rule(db, narrow_kind, narrow, values[narrow], priority=0)

    got = resolve_kind(
        db,
        product_code="SRTWC8152-RL",
        category_code="SRT-WC",
        product_name="Honeycomb Series water closet",
    )
    assert got is not None, f"{narrow} vs {broad}: nothing resolved."
    assert got.id == narrow_kind.id, (
        f"{broad} beat {narrow}. KIND_RULE_SPECIFICITY puts {narrow} first."
    )


def test_an_explicit_priority_outranks_match_type_specificity(db):
    """The ``priority`` column has to mean something or it would not be there.

    Pinned: a HIGHER number wins, and it is consulted before specificity. That makes
    ``priority`` the escape hatch for the one row where the general rule is wrong -
    a single model that belongs to a different Kind than its category implies -
    without rewriting the ranking for everybody. The direction is a decision this
    file takes: the AC says only "priority int, most specific wins".
    """
    resolve_kind = _resolve_kind()
    listed = _kind(db, "listed")
    boosted = _kind(db, "boosted")
    _rule(db, listed, "model_list", "SRTWC8152-RL", priority=0)
    _rule(db, boosted, "category", "SRT-WC", priority=10)

    got = resolve_kind(db, product_code="SRTWC8152-RL", category_code="SRT-WC")
    assert got is not None and got.id == boosted.id, (
        "A priority-10 category rule lost to a priority-0 model list. Higher "
        "priority wins and is consulted before match-type specificity."
    )


def test_the_longest_prefix_wins_among_prefix_rules(db):
    """Two prefixes both match; one is strictly more specific than the other.

    ``SRTWC`` and ``SRTWC8152`` both match ``SRTWC8152-RL``. Same match type, same
    priority - specificity cannot break it, so length does. Without this the answer
    depends on which row Postgres happens to return first.
    """
    resolve_kind = _resolve_kind()
    broad = _kind(db, "all-wc")
    narrow = _kind(db, "wc8152")
    _rule(db, broad, "model_prefix", "SRTWC")
    _rule(db, narrow, "model_prefix", "SRTWC8152")
    got = resolve_kind(db, product_code="SRTWC8152-RL")
    assert got is not None and got.id == narrow.id, (
        "The shorter prefix won. Among rules of the same type and priority, the "
        "longest matched value is the more specific one."
    )


def test_two_indistinguishable_rules_still_resolve_the_same_way_every_time(db):
    """The last tie, and the reason the engine is called deterministic.

    Two model-list rules, same priority, same specificity, same matched length,
    different Kinds. This is bad data - but it is reachable data, and the two things
    the engine must not do are raise (a complaint would stop) and answer differently
    on two calls (CS and the portal would disagree about the same product).

    Pinned tie-break: the kind ``code``, ascending. Arbitrary, total, and stable
    across processes, which is all a tie-break has to be.
    """
    resolve_kind = _resolve_kind()
    first = _kind(db, "tie", code=f"{TEST_PREFIX}-AAA-tie")
    second = _kind(db, "tie", code=f"{TEST_PREFIX}-BBB-tie")
    _rule(db, second, "model_list", "SRTWC8152-RL", priority=0)
    _rule(db, first, "model_list", "SRTWC8152-RL", priority=0)

    got = resolve_kind(db, product_code="SRTWC8152-RL")
    assert got is not None, "An ambiguous mapping must not stop resolution."
    assert got.id == first.id, (
        "Two indistinguishable rules must break on kind code ascending, not on row "
        "order."
    )
    again = resolve_kind(db, product_code="SRTWC8152-RL")
    assert again.id == got.id, "Two calls disagreed. The engine is not deterministic."


# =============================================================================
# The policy in force - AC-D6, and the two holes AC-D6 leaves
# =============================================================================


def test_the_policy_in_force_on_the_purchase_date_answers_not_todays(db):
    """AC-D6, the heart of it.

    An old purchase and a newer policy that both name the same Kind and part. The
    verdict must come from the OLD policy: clause 16 lets Sorento amend the document
    without notice, so judging by today's would retroactively change what somebody
    already bought.
    """
    resolve = _resolve()
    kind = _kind(db, "wc")
    old = _policy(db, version="ZZTv14", effective_from=date(2010, 1, 1), effective_to=date(2019, 12, 31))
    new = _policy(db, version="ZZTv15", effective_from=date(2020, 1, 1))
    _term(db, old, kind, "Flushing Fittings", duration_months=24)
    _term(db, new, kind, "Flushing Fittings", duration_months=60)

    entry = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(2015, 1, 1), as_of=date(2016, 1, 1))
    )
    assert _field(entry, "expiry") == date(2017, 1, 1), (
        "The 2020 policy's 5 years was applied to a 2015 purchase. Entitlement is "
        "judged against the terms in force ON THE PURCHASE DATE (AC-D6)."
    )
    assert _field(entry, "policy_id") == old.id, (
        "The verdict does not report which policy answered, so an argument about a "
        "verdict cannot be settled without re-running the engine."
    )
    assert new.id != old.id


def test_republishing_a_policy_does_not_change_an_existing_verdict(db):
    """AC-D6's second half, as behaviour rather than as a snapshot column.

    The durable half - snapshotting ``policy_id`` onto the purchase - is S2b's. What
    S2 owns is that resolve is a pure function of the purchase date, so publishing a
    newer policy TODAY cannot move an old answer.
    """
    resolve = _resolve()
    kind = _kind(db, "wc")
    old = _policy(db, effective_from=date(2010, 1, 1), effective_to=date(2019, 12, 31))
    _term(db, old, kind, "Flushing Fittings", duration_months=24)

    before = _only(resolve(db, kind_id=kind.id, purchase_date=date(2015, 1, 1), as_of=date(2016, 1, 1)))
    new = _policy(db, effective_from=date(2020, 1, 1))
    _term(db, new, kind, "Flushing Fittings", duration_months=1)
    after = _only(resolve(db, kind_id=kind.id, purchase_date=date(2015, 1, 1), as_of=date(2016, 1, 1)))

    assert _field(before, "expiry") == _field(after, "expiry") == date(2017, 1, 1), (
        "Publishing a new policy changed an old purchase's expiry."
    )
    assert _field(before, "verdict") == _field(after, "verdict")


def test_an_open_ended_policy_covers_every_date_after_it_starts(db):
    """``effective_to IS NULL`` is the current policy. It has not ended."""
    resolve = _resolve()
    kind, policy, _ = _simple_case(
        db, effective_from=date(2026, 3, 1), effective_to=None, duration_months=24
    )
    entry = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(2026, 6, 1), as_of=date(2026, 6, 2))
    )
    assert _field(entry, "verdict") == "covered"
    assert _field(entry, "policy_id") == policy.id


@pytest.mark.parametrize("purchase", [date(2020, 1, 1), date(2024, 12, 31)])
def test_the_policy_window_includes_both_of_its_own_dates(db, purchase):
    """Neither end of the window is specified. Both are pinned inclusive.

    A purchase made on the day a policy took effect is governed by that policy - the
    alternative leaves a one-day hole at every version change, and a hole in the
    calendar is an ``unknown`` verdict handed to a customer for no reason.
    """
    resolve = _resolve()
    kind, policy, _ = _simple_case(
        db, effective_from=date(2020, 1, 1), effective_to=date(2024, 12, 31), duration_months=24
    )
    entry = _only(resolve(db, kind_id=kind.id, purchase_date=purchase, as_of=purchase))
    assert _field(entry, "policy_id") == policy.id, (
        f"A purchase on {purchase} fell outside its own policy window. Both "
        "effective_from and effective_to are inclusive."
    )


def test_a_purchase_date_in_no_policy_window_is_unknown_not_uncovered(db):
    """The hole AC-D6 does not mention, and the worst wrong answer in the slice.

    A purchase dated before every policy on record (or in a gap between two) is a
    question the engine CANNOT answer. Returning an empty list makes the CS screen
    render "no cover" - the customer is refused because of a data-entry gap, and
    nothing anywhere says so.
    """
    resolve = _resolve()
    kind, _, _ = _simple_case(
        db, effective_from=date(2026, 3, 1), effective_to=None, duration_months=24
    )
    result = resolve(db, kind_id=kind.id, purchase_date=date(2015, 1, 1), as_of=date(2026, 6, 1))
    assert len(result) >= 1, (
        "resolve returned nothing for a purchase outside every policy window. An "
        "empty sequence is read as 'not covered' by every caller."
    )
    entry = _only(result)
    assert _field(entry, "verdict") == "unknown", (
        f"Expected 'unknown', got {_field(entry, 'verdict')!r}. No policy in force "
        "means the engine has no terms to judge by - which is not the same as the "
        "cover having run out."
    )
    assert _field(entry, "term_id") is None
    assert _field(entry, "expiry") is None


def test_a_policy_with_no_term_for_this_kind_is_no_term_not_unknown(db):
    """The other degenerate case, and it is a DIFFERENT one.

    ``unknown`` means "we have no policy for that date"; ``no_term`` means "we have
    the policy and it says nothing about this Kind". The first is a calendar gap to
    fix, the second is a scope question for Sorento. Collapsing them loses the only
    signal that says which.
    """
    resolve = _resolve()
    kind = _kind(db, "unmentioned")
    other = _kind(db, "mentioned")
    policy = _policy(db, effective_from=date(2000, 1, 1))
    _term(db, policy, other, "Body", duration_months=24)

    entry = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(2024, 1, 1), as_of=date(2024, 6, 1))
    )
    assert _field(entry, "verdict") == "no_term", (
        f"Expected 'no_term', got {_field(entry, 'verdict')!r}."
    )
    assert _field(entry, "policy_id") == policy.id, (
        "no_term must still report the policy that was consulted - that is what "
        "distinguishes it from unknown."
    )


def test_overlapping_policies_resolve_to_the_latest_effective_from(db):
    """Nothing prevents two windows containing the same date, so pin the winner.

    Two policies, both in force on the purchase date. Without a rule the answer
    depends on row order and the same complaint can be judged two ways on two page
    loads. Pinned: the most recently published applicable policy answers - the later
    ``effective_from`` - because that is the one a human would have believed was
    current when the sale happened.
    """
    resolve = _resolve()
    kind = _kind(db, "wc")
    older = _policy(db, effective_from=date(2020, 1, 1), effective_to=date(2029, 12, 31))
    newer = _policy(db, effective_from=date(2023, 1, 1), effective_to=date(2029, 12, 31))
    _term(db, older, kind, "Body", duration_months=12)
    _term(db, newer, kind, "Body", duration_months=60)

    entry = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(2024, 1, 1), as_of=date(2024, 6, 1))
    )
    assert _field(entry, "policy_id") == newer.id, (
        "Overlapping windows must resolve to the latest effective_from, "
        "deterministically."
    )
    assert _field(entry, "expiry") == date(2029, 1, 1)


def test_resolve_never_returns_an_empty_sequence(db):
    """The invariant behind the two tests above, stated once as itself.

    Every caller renders this list. There is no rendering of "[]" that does not read
    as "no cover", so the engine may never produce one.
    """
    resolve = _resolve()
    kind = _kind(db, "orphan")
    assert len(resolve(db, kind_id=kind.id, purchase_date=date(2024, 1, 1), as_of=date(2024, 6, 1))) >= 1, (
        "No policies at all, and resolve returned nothing. It must say 'unknown'."
    )


# =============================================================================
# The algorithm - AC-D4, AC-D5, AC-D9, and the date arithmetic nobody specified
# =============================================================================


def _water_closet(db, *, purchase_ok_from=date(2000, 1, 1)):
    """AC-D4's three simultaneous promises, as data."""
    kind = _kind(db, "water closet")
    policy = _policy(db, effective_from=purchase_ok_from)
    crack = _defect(db, "Crack line")
    leak = _defect(db, "Leakage")
    _term(
        db,
        policy,
        kind,
        "Ceramic Body",
        is_lifetime=True,
        covered_defect_type_ids=[crack, leak],
        installation_included=True,
    )
    _term(db, policy, kind, "Flushing Fittings", duration_months=60, installation_included=False)
    _term(db, policy, kind, "Seat Cover Soft Close", duration_months=24, installation_included=False)
    return kind, policy, {"crack": crack, "leak": leak}


def test_a_water_closet_returns_one_verdict_per_part(db):
    """AC-D4. Three answers, never one.

    Any shape that collapses a product to a single verdict is wrong: the parts
    expire on different dates, cover different defects and differ on who pays for
    the visit. A single answer has to discard two of the three.
    """
    resolve = _resolve()
    kind, _, defects = _water_closet(db)
    result = resolve(
        db,
        kind_id=kind.id,
        purchase_date=date(2025, 10, 16),
        defect_type_id=defects["leak"],
        as_of=date(2026, 1, 1),
    )
    assert len(result) == 3, f"Expected three verdicts, got {len(result)}: {result!r}"
    assert set(_by_part(result)) == set(WATER_CLOSET_PARTS)


def test_each_part_carries_its_own_expiry_and_its_own_installation_answer(db):
    """AC-D3 + AC-D4 + clause 15. Installation is what decides who pays."""
    resolve = _resolve()
    kind, _, defects = _water_closet(db)
    parts = _by_part(
        resolve(
            db,
            kind_id=kind.id,
            purchase_date=date(2025, 10, 16),
            defect_type_id=defects["leak"],
            as_of=date(2026, 1, 1),
        )
    )
    assert _field(parts["Ceramic Body"], "expiry") is None
    assert _field(parts["Ceramic Body"], "installation_included") is True
    assert _field(parts["Flushing Fittings"], "expiry") == date(2030, 10, 16)
    assert _field(parts["Flushing Fittings"], "installation_included") is False
    assert _field(parts["Seat Cover Soft Close"], "expiry") == date(2027, 10, 16)
    assert _field(parts["Seat Cover Soft Close"], "installation_included") is False


def test_every_verdict_is_one_of_the_five_declared_values(db):
    resolve = _resolve()
    kind, _, defects = _water_closet(db)
    result = resolve(
        db,
        kind_id=kind.id,
        purchase_date=date(2025, 10, 16),
        defect_type_id=defects["leak"],
        as_of=date(2026, 1, 1),
    )
    unexpected = set(_verdicts(result)) - VERDICTS
    assert not unexpected, f"Undeclared verdict value(s): {sorted(unexpected)}."


def test_the_order_of_the_verdicts_is_stable(db):
    """Three verdicts get rendered as a list, and a list needs an order.

    Pinned as ``part_name`` ascending: a total order that needs no extra column, and
    one that happens to read correctly for a water closet (Ceramic Body, Flushing
    Fittings, Seat Cover). Without it the CS panel reshuffles between page loads.
    """
    resolve = _resolve()
    kind, _, defects = _water_closet(db)
    result = resolve(
        db,
        kind_id=kind.id,
        purchase_date=date(2025, 10, 16),
        defect_type_id=defects["leak"],
        as_of=date(2026, 1, 1),
    )
    names = [_field(e, "part_name") for e in result]
    assert names == sorted(names), f"Verdicts are not ordered by part name: {names}."


def test_the_expiry_date_itself_is_still_covered(db):
    """The boundary the golden set does not state, decided for the customer.

    "Covered to 2030-10-16" is read as inclusive: a claim ON the expiry date is
    covered, and the refusal starts the next day. The opposite reading takes a day
    of cover away from somebody who was sold five years, and no document says it
    should.
    """
    resolve = _resolve()
    kind, _, _ = _simple_case(db, duration_months=60)
    on_expiry = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(2025, 10, 16), as_of=date(2030, 10, 16))
    )
    assert _field(on_expiry, "verdict") == "covered", (
        "A claim made ON the expiry date was refused. The boundary is inclusive."
    )
    day_after = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(2025, 10, 16), as_of=date(2030, 10, 17))
    )
    assert _field(day_after, "verdict") == "expired"
    assert _field(day_after, "expiry") == date(2030, 10, 16), (
        "An expired term must still report its expiry date - CS needs to tell the "
        "customer by how much they missed it."
    )


def test_a_claim_on_the_purchase_date_is_covered(db):
    """Day zero. Cover activates from the date of purchase (ADR-0010, BRD)."""
    resolve = _resolve()
    kind, _, _ = _simple_case(db, duration_months=24)
    entry = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(2025, 10, 16), as_of=date(2025, 10, 16))
    )
    assert _field(entry, "verdict") == "covered"


@pytest.mark.parametrize(
    "purchase,months,expiry,why",
    [
        (date(2024, 1, 31), 1, date(2024, 2, 29), "31 Jan + 1 month clamps to 29 Feb in a leap year"),
        (date(2023, 1, 31), 1, date(2023, 2, 28), "and to 28 Feb otherwise - never 3 March"),
        (date(2024, 2, 29), 12, date(2025, 2, 28), "29 Feb + 12 months clamps to 28 Feb"),
        (date(2024, 2, 29), 48, date(2028, 2, 29), "and lands exactly on the next leap day"),
        (date(2025, 10, 31), 60, date(2030, 10, 31), "a 31st that exists in the target month is untouched"),
        (date(2024, 1, 1), 300, date(2049, 1, 1), "25 years as 300 months, the kitchen sink case"),
    ],
)
def test_month_arithmetic_clamps_and_never_rolls_forward(db, purchase, months, expiry, why):
    """Nothing in the AC says what "+ N months" means on a 31st or a leap day.

    Naive arithmetic (add 30 days, or roll the overflow into the next month) gives a
    customer a different expiry than the one printed on their receipt, in the
    direction nobody can predict. Clamping to the last valid day of the target month
    is the only reading that keeps "5 years" meaning the same day-of-month.
    """
    resolve = _resolve()
    kind, _, _ = _simple_case(db, duration_months=months)
    entry = _only(resolve(db, kind_id=kind.id, purchase_date=purchase, as_of=purchase))
    assert _field(entry, "expiry") == expiry, why


def test_a_lifetime_term_never_expires(db):
    """AC-D4. "Lifetime" is not a number of months and must not be turned into one.

    The fixture policy is backdated to 1990 so the 1995 purchase sits INSIDE a window.
    As first written it used the default `effective_from` of 2000-01-01, which put the
    purchase before its own policy and made this test demand `covered` for exactly the
    shape `test_a_purchase_date_in_no_policy_window_is_unknown_not_uncovered` demands
    `unknown` for. No implementation could satisfy both. The point here is that lifetime
    survives 65 years, not that a purchase outside every window is covered.
    """
    resolve = _resolve()
    kind, _, _ = _simple_case(
        db, effective_from=date(1990, 1, 1), is_lifetime=True, duration_months=None
    )
    entry = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(1995, 5, 5), as_of=date(2060, 1, 1))
    )
    assert _field(entry, "verdict") == "covered"
    assert _field(entry, "expiry") is None
    assert _field(entry, "is_lifetime") is True


def test_a_term_with_neither_a_duration_nor_lifetime_is_unknown(db):
    """A data state the schema permits and the algorithm divides by.

    ``duration_months`` is nullable and ``is_lifetime`` defaults false, so a
    half-entered term is one forgotten field away. Two plausible implementations are
    both wrong: adding NULL months raises (a 500 on a complaint), and treating NULL
    as zero months tells the customer their cover expired on the day they bought it.
    ``unknown`` is the only honest answer, and it must not raise.
    """
    resolve = _resolve()
    with _without_the_xor_constraint(db):
        kind, _, _ = _simple_case(db, duration_months=None, is_lifetime=False)
    entry = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(2024, 1, 1), as_of=date(2024, 6, 1))
    )
    assert _field(entry, "verdict") == "unknown", (
        f"Got {_field(entry, 'verdict')!r} for a term with no duration and no "
        "lifetime flag. 'expired' would refuse a customer because of a blank field."
    )
    assert _field(entry, "expiry") is None


def test_a_lifetime_term_ignores_a_duration_that_was_also_filled_in(db):
    """Both fields set is contradictory data. Lifetime wins - it is the longer promise
    and the one the policy document actually prints."""
    resolve = _resolve()
    with _without_the_xor_constraint(db):
        kind, _, _ = _simple_case(db, is_lifetime=True, duration_months=12)
    entry = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(2010, 1, 1), as_of=date(2026, 1, 1))
    )
    assert _field(entry, "verdict") == "covered"
    assert _field(entry, "expiry") is None


# ------------------------------------------------------------ defect scope, AC-D5


def test_a_defect_outside_a_restricted_term_is_defect_not_covered(db):
    """AC-D5, the golden set's third row.

    The lifetime ceramic body covers cracking and leaking and nothing else, so a
    broken holder is refused by that term even though it never expires. Date and
    defect are two independent gates.
    """
    resolve = _resolve()
    crack = _defect(db, "Crack line")
    holder = _defect(db, "Holder broken")
    kind, _, _ = _simple_case(
        db, part_name="Ceramic Body", is_lifetime=True, covered_defect_type_ids=[crack]
    )
    entry = _only(
        resolve(
            db,
            kind_id=kind.id,
            purchase_date=date(2025, 1, 1),
            defect_type_id=holder,
            as_of=date(2026, 1, 1),
        )
    )
    assert _field(entry, "verdict") == "defect_not_covered", (
        f"Got {_field(entry, 'verdict')!r}. A lifetime term that never expires can "
        "still refuse a defect it does not cover."
    )


def test_a_defect_inside_a_restricted_term_is_then_judged_on_the_date(db):
    """The gate is a gate, not the answer. Passing it hands over to the date."""
    resolve = _resolve()
    leak = _defect(db, "Leakage")
    kind, _, _ = _simple_case(db, duration_months=24, covered_defect_type_ids=[leak])
    covered = _only(
        resolve(
            db,
            kind_id=kind.id,
            purchase_date=date(2025, 1, 1),
            defect_type_id=leak,
            as_of=date(2026, 1, 1),
        )
    )
    assert _field(covered, "verdict") == "covered"
    expired = _only(
        resolve(
            db,
            kind_id=kind.id,
            purchase_date=date(2015, 1, 1),
            defect_type_id=leak,
            as_of=date(2026, 1, 1),
        )
    )
    assert _field(expired, "verdict") == "expired"


def test_an_empty_defect_list_covers_every_defect(db):
    """The schema comment says "empty = all defects", and it is kept.

    This is the same shape as the rule-engine footgun already recorded here (an
    empty ``rules[]`` matching everything silently), so it is pinned explicitly
    rather than left to be rediscovered: a term with no restriction is the normal
    case, and forcing every row to enumerate every defect would be worse.
    """
    resolve = _resolve()
    anything = _defect(db, "Rust")
    kind, _, _ = _simple_case(db, duration_months=24, covered_defect_type_ids=[])
    entry = _only(
        resolve(
            db,
            kind_id=kind.id,
            purchase_date=date(2025, 1, 1),
            defect_type_id=anything,
            as_of=date(2026, 1, 1),
        )
    )
    assert _field(entry, "verdict") == "covered", (
        "An empty covered_defect_type_ids restricted the term. Empty means every "
        "defect, per the schema comment."
    )


def test_a_null_defect_list_behaves_exactly_like_an_empty_one(db):
    """NULL and ``{}`` are different values in Postgres and the same intent here.

    Nobody will maintain the distinction: an array column populated by a seed, an
    admin form and a migration will end up holding both. Pinning them as identical
    is the only way that does not eventually refuse a claim because a row held NULL
    where its neighbour held ``{}``.
    """
    resolve = _resolve()
    anything = _defect(db, "Rust")
    kind, _, _ = _simple_case(db, duration_months=24, covered_defect_type_ids=None)
    entry = _only(
        resolve(
            db,
            kind_id=kind.id,
            purchase_date=date(2025, 1, 1),
            defect_type_id=anything,
            as_of=date(2026, 1, 1),
        )
    )
    assert _field(entry, "verdict") == "covered"


def test_a_defect_nobody_stated_cannot_convict_a_restricted_term(db):
    """``defect_type_id`` is optional, because a complaint can arrive without one.

    AC-C14 says nothing blocks submission, so an unclassified line reaches the
    engine routinely. Treating "not stated" as "not in the list" refuses a customer
    for a question they were never asked; treating it as "in the list" promises
    cover that may not exist. ``unknown`` for the restricted term is the third
    answer, and it is the honest one.
    """
    resolve = _resolve()
    crack = _defect(db, "Crack line")
    kind = _kind(db, "wc")
    policy = _policy(db)
    _term(db, policy, kind, "Ceramic Body", is_lifetime=True, covered_defect_type_ids=[crack])
    _term(db, policy, kind, "Flushing Fittings", duration_months=60)

    parts = _by_part(
        resolve(db, kind_id=kind.id, purchase_date=date(2025, 1, 1), defect_type_id=None, as_of=date(2026, 1, 1))
    )
    assert _field(parts["Ceramic Body"], "verdict") == "unknown", (
        f"Got {_field(parts['Ceramic Body'], 'verdict')!r} for a defect-scoped term "
        "with no stated defect. Neither 'covered' nor 'defect_not_covered' is "
        "knowable here."
    )
    assert _field(parts["Flushing Fittings"], "verdict") == "covered", (
        "An unrestricted term does not need the defect type and must still answer."
    )


# ------------------------------------------------------ registration bonus, AC-D9


def test_the_registration_bonus_applies_only_when_registered(db):
    """AC-D9, clause 26: 2 + 1 years with online registration.

    Registration is never a precondition of cover (ADR-0010, BRD over clause 3(b)) -
    it only ever lengthens it.
    """
    resolve = _resolve()
    kind, _, _ = _simple_case(db, duration_months=24, registration_bonus_months=12)

    unregistered = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(2025, 1, 1), registered=False, as_of=date(2025, 6, 1))
    )
    assert _field(unregistered, "expiry") == date(2027, 1, 1), "Unregistered is 2 years."

    registered = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(2025, 1, 1), registered=True, as_of=date(2025, 6, 1))
    )
    assert _field(registered, "expiry") == date(2028, 1, 1), "Registered is 3 years."


def test_registered_defaults_to_false(db):
    """The default must be the shorter cover.

    Defaulting to registered would quietly promise a year Sorento never sold, on
    every call that forgets the argument.
    """
    resolve = _resolve()
    kind, _, _ = _simple_case(db, duration_months=24, registration_bonus_months=12)
    entry = _only(resolve(db, kind_id=kind.id, purchase_date=date(2025, 1, 1), as_of=date(2025, 6, 1)))
    assert _field(entry, "expiry") == date(2027, 1, 1)


def test_a_null_bonus_is_zero_months(db):
    """Most terms have no bonus and the column is nullable. NULL + 24 must not raise."""
    resolve = _resolve()
    kind, _, _ = _simple_case(db, duration_months=24, registration_bonus_months=None)
    entry = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(2025, 1, 1), registered=True, as_of=date(2025, 6, 1))
    )
    assert _field(entry, "expiry") == date(2027, 1, 1)


def test_a_bonus_on_a_lifetime_term_changes_nothing(db):
    """A meaningless combination the schema permits, and the AC never mentions.

    Adding twelve months to a promise with no end is not an error worth refusing -
    it is a data-entry oddity. Lifetime absorbs it and the term still never expires.
    """
    resolve = _resolve()
    kind, _, _ = _simple_case(db, is_lifetime=True, registration_bonus_months=12)
    entry = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(2025, 1, 1), registered=True, as_of=date(2099, 1, 1))
    )
    assert _field(entry, "verdict") == "covered"
    assert _field(entry, "expiry") is None


# --------------------------------------------------------------- as_of, and today


def test_warranty_today_is_the_malaysian_date():
    """Which day it is decides an expiring claim, and Sorento's day is UTC+8.

    Computed from UTC, the engine calls it yesterday for the first eight hours of
    every Malaysian day - so a claim made at 9am on the expiry date would be refused.
    Exposed as a function so ``as_of`` has one default and every caller shares it.
    """
    today = _fn(WARRANTY_SERVICE, "warranty_today", "() -> date")
    assert today() == datetime.now(MALAYSIA_TZ).date(), (
        "warranty_today() is not the Malaysian date. Mirror sla_service.MALAYSIA_TZ."
    )


def test_as_of_defaults_to_today(db):
    """Omitting ``as_of`` must equal passing today, or every test here proves nothing
    about the production call, which never passes one."""
    resolve = _resolve()
    today = _fn(WARRANTY_SERVICE, "warranty_today", "() -> date")
    kind, _, _ = _simple_case(db, duration_months=300)
    implicit = _only(resolve(db, kind_id=kind.id, purchase_date=date(2024, 1, 1)))
    explicit = _only(resolve(db, kind_id=kind.id, purchase_date=date(2024, 1, 1), as_of=today()))
    assert _field(implicit, "verdict") == _field(explicit, "verdict") == "covered"
    assert _field(implicit, "expiry") == _field(explicit, "expiry") == date(2049, 1, 1)


# =============================================================================
# AC-D15 - clause 17 is modelled and NOT enforced
# =============================================================================


def test_resolve_takes_no_installation_context_argument(db):
    """AC-D15. 23 of 50 live Complaints are Project cases.

    Clause 17 restricts cover to residential installations. Read literally, none of
    those 23 are covered - so the restriction is recorded in the policy text and the
    engine does not act on it, pending Sorento's ruling. The cheapest way to make
    that structural rather than a promise is for the function to have nowhere to put
    the answer: no usage, no customer type, no residential flag in the signature.
    """
    resolve = _resolve()
    banned = {
        "usage",
        "usage_type",
        "customer_type",
        "installation_type",
        "site_type",
        "is_residential",
        "residential",
        "commercial",
        "is_project",
        "project",
    }
    present = banned.intersection(inspect.signature(resolve).parameters)
    assert not present, (
        f"resolve() accepts {sorted(present)}. AC-D15 says clause 17 is modelled but "
        "NOT enforced - a parameter for it is an enforcement point waiting for its "
        "first branch."
    )


def test_a_commercial_purchase_is_judged_exactly_like_a_residential_one(db):
    """The behavioural half of AC-D15.

    There is no way to tell the engine this went into a hotel, and that is the point.
    Asserted as a normal covered verdict on a term whose own exclusions text names
    the restriction: the text is carried, and nothing reads it.
    """
    resolve = _resolve()
    kind, _, _ = _simple_case(
        db,
        duration_months=60,
        exclusions=(
            "Clause 17: warranty applies to residential installations only. "
            "Commercial and industrial use excluded. NOT ENFORCED pending ruling."
        ),
    )
    entry = _only(
        resolve(db, kind_id=kind.id, purchase_date=date(2025, 1, 1), as_of=date(2026, 1, 1))
    )
    assert _field(entry, "verdict") == "covered", (
        "A term carrying the clause-17 exclusion text was refused. The text is "
        "modelled; the restriction is not applied."
    )


# =============================================================================
# AC-D7 - a replacement inherits the remaining cover
# =============================================================================


def test_a_replacement_inherits_the_source_expiry_and_starts_no_new_term():
    """AC-D7 and the sixth golden row, at function level.

    A seat cover replaced in July 2026 under a term expiring 2027-10-16 still
    expires 2027-10-16. It is asserted as a COPY, not a recomputation: the
    difference is invisible when the two happen to coincide and is two years of free
    cover when they do not. ``warranty_assessments`` is an S2b table, so this is
    pinned on the function rather than on a row.
    """
    inherit = _resolve_replacement()
    source_expiry = date(2027, 10, 16)
    replaced_on = date(2026, 7, 15)

    got = inherit(source_expiry=source_expiry, replaced_on=replaced_on, as_of=date(2026, 8, 1))
    assert _field(got, "expiry") == source_expiry, (
        f"Expected the source expiry {source_expiry}, got {_field(got, 'expiry')}. "
        "Policy clause 6 note: the replaced Warranty Part does not carry a new "
        "warranty."
    )
    assert _field(got, "expiry") != date(2028, 7, 15), (
        "The replacement restarted the 2-year term from the replacement date."
    )
    assert _field(got, "verdict") == "covered"


def test_a_replacement_of_a_lifetime_part_stays_lifetime():
    inherit = _resolve_replacement()
    got = inherit(
        source_expiry=None,
        source_is_lifetime=True,
        replaced_on=date(2026, 7, 15),
        as_of=date(2099, 1, 1),
    )
    assert _field(got, "expiry") is None
    assert _field(got, "verdict") == "covered"


def test_a_replacement_expires_when_the_inherited_cover_does():
    """Inheriting the date means inheriting its end, including one already past.

    A part replaced under goodwill after the term ran out does not acquire cover by
    being new.
    """
    inherit = _resolve_replacement()
    got = inherit(
        source_expiry=date(2027, 10, 16),
        replaced_on=date(2026, 7, 15),
        as_of=date(2027, 10, 17),
    )
    assert _field(got, "verdict") == "expired"
    assert _field(got, "expiry") == date(2027, 10, 16)


def test_replacement_inheritance_does_not_touch_the_database():
    """It is arithmetic on values already computed, so it needs no session.

    Requiring a db here would mean re-resolving the source - which is exactly the
    recomputation AC-D7 forbids, reintroduced through the back door.
    """
    inherit = _resolve_replacement()
    parameters = inspect.signature(inherit).parameters
    assert "db" not in parameters and "session" not in parameters, (
        "resolve_replacement takes a session, which means it can re-derive the source "
        "expiry instead of copying it (AC-D7)."
    )


# =============================================================================
# AC-D1 - the seed, and the golden set against the real v15 data
# =============================================================================


def test_the_seed_creates_the_kinds_named_in_ac_d1(db):
    """AC-D1. 31 kinds from Warranty Policy v15.

    Counted inside the blank schema, which is the only place counting a whole table
    is safe: the local database is a copy of production.
    """
    seed = _seed()
    kind_cls = _model("WarrantyProductKind")
    seed(db)
    db.flush()

    names = {(row.name or "").strip().lower() for row in db.query(kind_cls).all()}
    missing = [n for n in NAMED_KINDS if n.lower() not in names and f"{n.lower()}s" not in names]
    assert not missing, f"AC-D1 names these kinds and the seed did not create them: {missing}."
    assert len(names) >= len(NAMED_KINDS), "The seed created fewer kinds than AC-D1 names."
    assert db.query(kind_cls).count() >= 31, (
        f"AC-D1 says 31 kinds; the seed created {db.query(kind_cls).count()}."
    )


def test_the_seed_is_idempotent(db):
    """It will be re-run on every environment, and twice on at least one of them."""
    seed = _seed()
    kind_cls = _model("WarrantyProductKind")
    term_cls = _model("WarrantyTerm")
    policy_cls = _model("WarrantyPolicy")

    seed(db)
    db.flush()
    counts = (db.query(kind_cls).count(), db.query(policy_cls).count(), db.query(term_cls).count())

    seed(db)
    db.flush()
    again = (db.query(kind_cls).count(), db.query(policy_cls).count(), db.query(term_cls).count())
    assert counts == again, (
        f"A second seed run changed the row counts {counts} -> {again}. It must "
        "upsert on the stable codes, not insert."
    )


def test_the_seed_creates_the_defect_type_vocabulary(db):
    """AC-D5 needs defect TYPES and this codebase has none.

    The nearest existing lookup set, ``complaints_defects_discovered``, enumerates
    WHEN a defect was noticed - "Upon delivery after unloading", "After installation
    before using". None of those is crack, leak or rust. So a term cannot express
    "crack and leak only" until S2 seeds the vocabulary it points at, and the plan's
    S3 reference to ``lookup_values(id)`` names a table that does not exist (it is
    ``lookup_options``).
    """
    seed = _seed()
    seed(db)
    db.flush()

    lookup_set = db.query(LookupSet).filter(LookupSet.set_key == DEFECT_TYPE_SET_KEY).one_or_none()
    assert lookup_set is not None, (
        f"No lookup set {DEFECT_TYPE_SET_KEY!r}. warranty_terms.covered_defect_type_ids "
        "points at lookup_options rows that nothing creates."
    )
    labels = {
        (o.label or "").lower()
        for o in db.query(LookupOption).filter(LookupOption.set_id == lookup_set.id).all()
    }
    # crack and leak scope the lifetime ceramic body (AC-D5); rust and the broken
    # holder are the defects the golden set names. All four have to exist before a
    # single golden row can be expressed.
    for needed in ("crack", "leak", "rust", "holder"):
        assert any(needed in label for label in labels), (
            f"The defect-type vocabulary has no {needed!r} option. The golden set "
            "cannot be expressed without it, and the lifetime ceramic body cannot be "
            f"scoped to crack and leak (AC-D5). Got {sorted(labels)}."
        )


def test_the_seeded_policy_is_v15_dated_and_carries_its_text(db):
    """AC-D6 + BRD Req #12. The document is what the AI is later restricted to."""
    seed = _seed()
    policy_cls = _model("WarrantyPolicy")
    seed(db)
    db.flush()

    policies = db.query(policy_cls).all()
    assert policies, "The seed created no policy row."
    v15 = [p for p in policies if "15" in (p.version or "")]
    assert v15, f"No v15 policy. Got versions {[p.version for p in policies]}."
    policy = v15[0]
    assert policy.effective_from is not None
    assert policy.policy_text, (
        "warranty_policies.policy_text is empty. It is the extracted document and "
        "the only thing AC-D14's answer may quote."
    )


def test_the_seeded_policy_is_backdated_far_enough_to_judge_the_golden_set(db):
    """The conflict between AC-D6 and the golden set, made explicit.

    Warranty Policy v15 is dated March 2026. Five of the seven golden rows are
    purchases from 2015, 2024 and 2025. If v15's ``effective_from`` is its
    publication date, then "the policy in force on the purchase date" is nothing at
    all for those rows and the engine correctly answers ``unknown`` - which fails
    its own acceptance test.

    The fix belongs in the DATA: v15 is the only policy Sorento has on record, so it
    is seeded backdated and genuinely governs those purchases. Clamping an
    out-of-range date to the nearest policy was rejected - it judges a 2015 purchase
    by 2026 terms, the one thing AC-D6 exists to forbid, and it makes a real
    calendar gap unreportable.
    """
    seed = _seed()
    policy_cls = _model("WarrantyPolicy")
    seed(db)
    db.flush()

    earliest = min(p.effective_from for p in db.query(policy_cls).all())
    assert earliest <= OLDEST_GOLDEN_PURCHASE, (
        f"The earliest seeded policy starts {earliest}, after the oldest golden "
        f"purchase {OLDEST_GOLDEN_PURCHASE}. Every golden row before that date "
        "resolves to 'unknown' and the golden set cannot pass. See the docstring."
    )


def test_the_seeded_policy_text_carries_clause_17(db):
    """AC-D15's "modelled" half. The restriction is recorded; nothing acts on it."""
    seed = _seed()
    policy_cls = _model("WarrantyPolicy")
    seed(db)
    db.flush()
    text = " ".join((p.policy_text or "") for p in db.query(policy_cls).all()).lower()
    assert "residential" in text, (
        "The seeded policy text does not mention the residential restriction. AC-D15 "
        "says clause 17 is MODELLED but not enforced - if the text is not stored, it "
        "is neither."
    )


# ----------------------------------------------------------------- the golden set
#
# Seven rows from the plan, run against the real v15 seed rather than against
# hand-built fixtures. That is deliberate: these rows are as much a test of the
# seeded policy data as of the arithmetic, and the arithmetic is already pinned
# above on fixtures this file controls.


def _seeded_kind(db, needle: str):
    """Find one seeded Kind by name, exactly if possible.

    Substring alone is not safe here: "Water Closet" is a substring of "Intelligent
    Water Closet" and "Tankless Water Closet", both of which AC-D1 also seeds, so a
    first-match-wins lookup would silently golden-test the wrong Kind. Exact wins;
    otherwise the substring must be unambiguous, and an ambiguous one fails loudly
    rather than picking.
    """
    kind_cls = _model("WarrantyProductKind")
    rows = db.query(kind_cls).all()
    wanted = needle.strip().lower()

    exact = [
        row
        for row in rows
        if (row.name or "").strip().lower() in (wanted, f"{wanted}s")
        or (row.consumer_label or "").strip().lower() in (wanted, f"{wanted}s")
    ]
    if exact:
        return exact[0]

    partial = [
        row
        for row in rows
        if wanted in (row.name or "").lower() or wanted in (row.consumer_label or "").lower()
    ]
    assert partial, f"The v15 seed has no Kind matching {needle!r}."
    assert len(partial) == 1, (
        f"{needle!r} matches {len(partial)} seeded Kinds "
        f"({[r.name for r in partial]}), and none of them is named exactly that. "
        "Name the Kind the way AC-D1 and the golden set do, so a verdict cannot be "
        "asserted against the wrong one."
    )
    return partial[0]


def _seeded_defect(db, needle: str) -> str:
    lookup_set = db.query(LookupSet).filter(LookupSet.set_key == DEFECT_TYPE_SET_KEY).one_or_none()
    assert lookup_set is not None, f"No {DEFECT_TYPE_SET_KEY!r} lookup set (see AC-D5)."
    matches = [
        o
        for o in db.query(LookupOption).filter(LookupOption.set_id == lookup_set.id).all()
        if needle.lower() in (o.label or "").lower()
    ]
    assert matches, f"The seeded defect vocabulary has no {needle!r} option."
    return matches[0].id


def _seeded(db):
    """Run the v15 seed and hand back the session.

    A helper rather than a fixture on purpose: before the seed module exists this
    raises, and a raise inside a fixture is reported by pytest as an ERROR rather
    than a FAILURE. A gate whose red count is diluted by errors is harder to read,
    and an error looks like a broken test rather than a missing implementation.
    """
    _seed()(db)
    db.flush()
    return db


def test_golden_water_closet_bought_2025_leaking(db):
    """Row 1. Ceramic body lifetime, fittings to 2030-10-16, seat cover to 2027-10-16."""
    resolve = _resolve()
    seeded = _seeded(db)
    kind = _seeded_kind(seeded, "Water Closet")
    parts = _by_part(
        resolve(
            seeded,
            kind_id=kind.id,
            purchase_date=date(2025, 10, 16),
            defect_type_id=_seeded_defect(seeded, "leak"),
            as_of=date(2026, 8, 1),
        )
    )
    assert set(WATER_CLOSET_PARTS).issubset(parts), (
        f"A Water Closet must return the three parts of AC-D4. Got {sorted(parts)}."
    )
    body = parts["Ceramic Body"]
    assert _field(body, "verdict") == "covered" and _field(body, "expiry") is None
    assert _field(body, "installation_included") is True

    fittings = parts["Flushing Fittings"]
    assert _field(fittings, "verdict") == "covered"
    assert _field(fittings, "expiry") == date(2030, 10, 16)
    assert _field(fittings, "installation_included") is False

    seat = parts["Seat Cover Soft Close"]
    assert _field(seat, "verdict") == "covered"
    assert _field(seat, "expiry") == date(2027, 10, 16)
    assert _field(seat, "installation_included") is False


def test_golden_water_closet_bought_2015_leaking(db):
    """Row 2. The ceramic body still answers; the other two have run out.

    This row is also the reason the seeded policy must be backdated - a 2015
    purchase has no v15 window unless it is.
    """
    resolve = _resolve()
    seeded = _seeded(db)
    kind = _seeded_kind(seeded, "Water Closet")
    parts = _by_part(
        resolve(
            seeded,
            kind_id=kind.id,
            purchase_date=date(2015, 1, 1),
            defect_type_id=_seeded_defect(seeded, "leak"),
            as_of=date(2026, 8, 1),
        )
    )
    assert _field(parts["Ceramic Body"], "verdict") == "covered"
    assert _field(parts["Flushing Fittings"], "verdict") == "expired"
    assert _field(parts["Flushing Fittings"], "expiry") == date(2020, 1, 1)
    assert _field(parts["Seat Cover Soft Close"], "verdict") == "expired"
    assert _field(parts["Seat Cover Soft Close"], "expiry") == date(2017, 1, 1)


def test_golden_water_closet_ceramic_body_holder_broken(db):
    """Row 3. Lifetime is crack and leak only, so a broken holder is refused.

    The other two parts are unaffected: this is a per-term gate, not a per-product
    one, and a broken holder may well still be covered by the fittings term.
    """
    resolve = _resolve()
    seeded = _seeded(db)
    kind = _seeded_kind(seeded, "Water Closet")
    parts = _by_part(
        resolve(
            seeded,
            kind_id=kind.id,
            purchase_date=date(2025, 10, 16),
            defect_type_id=_seeded_defect(seeded, "holder"),
            as_of=date(2026, 8, 1),
        )
    )
    assert _field(parts["Ceramic Body"], "verdict") == "defect_not_covered", (
        "The lifetime ceramic body covers cracking and leaking only (AC-D5)."
    )


def test_golden_kitchen_sink_ss304_bought_2024_rust(db):
    """Row 4. 25 years, to 2049-01-01."""
    resolve = _resolve()
    seeded = _seeded(db)
    kind = _seeded_kind(seeded, "Kitchen Sink")
    result = resolve(
        seeded,
        kind_id=kind.id,
        purchase_date=date(2024, 1, 1),
        defect_type_id=_seeded_defect(seeded, "rust"),
        as_of=date(2026, 8, 1),
    )
    expiries = {_field(e, "expiry") for e in result}
    assert date(2049, 1, 1) in expiries, (
        f"No term expiring 2049-01-01 (25 years from 2024-01-01). Got {sorted(str(e) for e in expiries)}."
    )
    covering = [e for e in result if _field(e, "expiry") == date(2049, 1, 1)]
    assert all(_field(e, "verdict") == "covered" for e in covering)


@pytest.mark.parametrize(
    "registered,expiry",
    [(False, date(2027, 1, 1)), (True, date(2028, 1, 1))],
)
def test_golden_booster_pump_registration_extends_two_years_to_three(db, registered, expiry):
    """Row 5 / AC-D9. Clause 26: 2 + 1 with online registration.

    No defect is passed, because the golden row names none. That is a real
    constraint on the seeded data: a defect-scoped pump term would answer 'unknown'
    here (a defect nobody stated cannot convict a restricted term), so the pump's
    term must carry no defect restriction unless the policy document says otherwise.
    """
    resolve = _resolve()
    seeded = _seeded(db)
    kind = _seeded_kind(seeded, "Booster Pump")
    result = resolve(
        seeded,
        kind_id=kind.id,
        purchase_date=date(2025, 1, 1),
        registered=registered,
        as_of=date(2025, 6, 1),
    )
    expiries = {_field(e, "expiry") for e in result}
    assert expiry in expiries, (
        f"registered={registered} should reach {expiry}; got {sorted(str(e) for e in expiries)}."
    )


def test_golden_seat_cover_replaced_in_2026_keeps_the_2027_expiry(db):
    """Row 6, end to end: resolve the source term, then inherit from it.

    The source expiry is not hard-coded here - it is whatever row 1 computed, so if
    the seat cover term ever changes, this row follows it instead of silently
    testing a stale constant.
    """
    resolve = _resolve()
    seeded = _seeded(db)
    inherit = _resolve_replacement()
    kind = _seeded_kind(seeded, "Water Closet")
    parts = _by_part(
        resolve(
            seeded,
            kind_id=kind.id,
            purchase_date=date(2025, 10, 16),
            defect_type_id=_seeded_defect(seeded, "leak"),
            as_of=date(2026, 7, 1),
        )
    )
    source_expiry = _field(parts["Seat Cover Soft Close"], "expiry")
    assert source_expiry == date(2027, 10, 16)

    replacement = inherit(
        source_expiry=source_expiry, replaced_on=date(2026, 7, 20), as_of=date(2026, 8, 1)
    )
    assert _field(replacement, "expiry") == date(2027, 10, 16), (
        "The replacement did not inherit the remaining cover (AC-D7)."
    )
    assert _field(replacement, "expiry") != date(2028, 7, 20), "A new 2-year term started."


def test_golden_sensor_tap_sensor_eye_bought_2024_is_expired_and_chargeable(db):
    """Row 7. Expiry 2025-06-01, installation excluded, so the callout is chargeable.

    ``Sensor Eye`` is a PART of the Sensor Tap kind, not a defect type - the golden
    row does not say which and both readings are grammatical. It is read as a part
    because that is what a warranty term is scoped to, and because a one-year sensor
    eye beside a longer body term is what the policy document describes.

    Note the golden row's wording: "expired 2025-06-01". Under the inclusive
    boundary pinned in this file the claim is COVERED on 2025-06-01 and refused from
    2025-06-02. The date in the golden set is the expiry, not the first day of
    refusal.
    """
    resolve = _resolve()
    seeded = _seeded(db)
    kind = _seeded_kind(seeded, "Sensor Tap")
    parts = _by_part(
        resolve(seeded, kind_id=kind.id, purchase_date=date(2024, 6, 1), as_of=date(2026, 8, 1))
    )
    eye = [entry for name, entry in parts.items() if "sensor eye" in (name or "").lower()]
    assert eye, f"The Sensor Tap kind has no 'Sensor Eye' term. Got parts {sorted(parts)}."
    entry = eye[0]
    assert _field(entry, "expiry") == date(2025, 6, 1)
    assert _field(entry, "verdict") == "expired"
    assert _field(entry, "installation_included") is False, (
        "Installation must be excluded, which is what makes the callout chargeable "
        "under clause 15."
    )


def test_the_sensor_eye_is_covered_on_its_expiry_date(db):
    """The same row one day earlier, so the boundary ruling is pinned on real data."""
    resolve = _resolve()
    seeded = _seeded(db)
    kind = _seeded_kind(seeded, "Sensor Tap")
    parts = _by_part(
        resolve(seeded, kind_id=kind.id, purchase_date=date(2024, 6, 1), as_of=date(2025, 6, 1))
    )
    entry = [e for name, e in parts.items() if "sensor eye" in (name or "").lower()][0]
    assert _field(entry, "verdict") == "covered"


# =============================================================================
# AC-D13 - the engine never reads products.warranty_months
# =============================================================================


def test_the_warranty_module_never_reads_products_warranty_months(db):
    """AC-D13, the half that can be enforced as a red test.

    The AC as written ("no code path reads it") is FALSE on arrival: it is a
    response field in two schemas and a registered attachment field-link. Freezing
    that inventory is ``tests/test_warranty_scope_guard.py``'s job. What belongs
    here is the narrow, checkable half - the NEW code S2 adds must not read it,
    because 0 of 11,415 rows are populated and a cover answer derived from it would
    be silently null for every product Sorento sells.
    """
    for dotted in (WARRANTY_MODELS, WARRANTY_SERVICE):
        spec = importlib.util.find_spec(dotted)
        assert spec is not None and spec.origin, f"{dotted} does not exist."
        source = pathlib.Path(spec.origin).read_text(encoding="utf-8", errors="ignore")
        assert "warranty_months" not in source, (
            f"{dotted} mentions products.warranty_months (AC-D13). It is abandoned: "
            "0 of 11,415 rows are populated, and one integer cannot hold a part, a "
            "lifetime, a defect scope and an installation answer (ADR-0010)."
        )
