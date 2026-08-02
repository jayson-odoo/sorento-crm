"""S2b gate, part 2 - the stored verdict (AC-D8, AC-D10, AC-D11, AC-D12, the E2E
half of AC-D9, plus AC-L13 and AC-L16).

Written BEFORE the implementation. S2 built the entitlement ENGINE - a pure
function over plain values that never touches a purchase row. This file is about
the moment that answer is written down against a real complaint, which is where
every dangerous decision in the slice lives.

**AC-D14 (policy Q&A) is explicitly OUT of this file and out of S2b's gate.**

Four things shape this suite, and each is a place the plan is wrong or silent:

1. **"One assessment per complaint product line" cannot be right.** A Water Closet
   resolves to THREE terms simultaneously - ceramic body (lifetime, crack and leak
   only, installation included), flushing fittings and seat cover, each with its
   own expiry and its own installation answer. A table with one row and one
   ``term_id`` per line can hold exactly one of them, so CS would see one part's
   answer and dispatch on it. The whole reason ``resolve`` returns a sequence is
   that no product has one answer. So an assessment is one row per
   (complaint product line, TERM), unique on that pair.

2. **AC-D8's auto-created Registration must not buy a third year of cover.** The
   Booster Pump's clause 26 bonus is 12 months on a 24 month base, earned by
   ONLINE REGISTRATION - a deliberate act by the consumer that Sorento gets
   something for. AC-D8 auto-creates a Registration when a complaint is lodged. Put
   those together naively and lodging a complaint grants a year of cover Sorento
   never sold, at exactly the moment of the claim, in the direction that makes the
   claim succeed. The system would be paying itself. So an auto-created
   registration is recorded, activates cover from the purchase date, and earns
   ZERO bonus months. See
   ``test_an_auto_created_registration_never_earns_the_registration_bonus``, which
   I consider the single most important test in this slice.

3. **AC-D8 cannot invent a purchase.** Registration is now a timestamp on a
   purchase (fork 7 renamed the table), so "auto-created if absent" can only mean
   "the purchase exists and ``registered_at`` is NULL". If no purchase is linked at
   all there is no purchase date, and inventing one - today's, the complaint's -
   fabricates the single number every verdict is computed from. The complaint
   proceeds with an ``unknown`` verdict instead. Never blocked (AC-C14).

4. **AC-D12's "recommendation" needs a home, and the honest one is both ends.**
   The provenance of the date belongs on the PURCHASE (it is a fact about the
   receipt), and the assessment SNAPSHOTS it, because the assessment is the artifact
   CS reads and a verdict that must re-join to the purchase to learn its own
   confidence gets rendered without it. Snapshotting also means correcting the
   purchase later does not retroactively re-label a verdict a human already acted
   on.

Two things this file finds missing rather than tests:

- ``complaint_product_lines`` has **no ``defect_type_id``**, and nothing else in
  this codebase carries a defect TYPE either: ``complaints.defects_discovered`` is
  free text from the ``complaints_defects_discovered`` lookup, which enumerates
  WHEN a defect was noticed ("Upon delivery after unloading"), not what it is.
  Without it, every defect-restricted term - which is exactly the lifetime ceramic
  body, the most valuable promise in the policy - answers ``unknown`` on every
  complaint forever. AC-D10 is unsatisfiable until the column exists, and no AC in
  Group D or Group L asks for it.
- ``complaint_product_lines`` has no ``consumer_purchase_line_id``. AC-L16 requires
  it and S2b is the slice that adds it, to a table the complaints module owns.

Run: venv/bin/python -m pytest tests/test_warranty_assessments.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import pathlib
import uuid
from datetime import date

import pytest

from app.models.complaints import Complaint, ComplaintProductLine
from app.models.lookup import LookupOption, LookupSet
from app.models.order import Customer
from app.models.warranty import WarrantyPolicy, WarrantyProductKind, WarrantyTerm

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

# ---------------------------------------------------------------- the contract

CONSUMER_MODELS = "app.models.consumers"
CONSUMER_SERVICE = "app.services.consumer_service"

# The stored verdict lives in the WARRANTY module, not the consumer one (fork 7):
# `warranty` owns policy, terms, kinds and assessments; `consumers` owns profiles
# and the ledger. Putting the assessment in app.models.consumers would mean
# uninstalling warranty leaves assessments behind pointing at deleted terms.
WARRANTY_MODELS = "app.models.warranty"

# One module owns writing a verdict down, for the same reason warranty_service owns
# computing one: the CS panel, the portal and the auto-assessment on intake are
# three callers, and two of them writing their own row is two answers.
ASSESSMENT_SERVICE = "app.services.warranty_assessment_service"

# AC-D17's closed set, reused: a stored verdict may only ever be one of these.
VERDICTS = frozenset({"covered", "expired", "defect_not_covered", "no_term", "unknown"})

# AC-D8. `auto_on_complaint` is the whole reason this vocabulary exists.
AUTO_SOURCE = "auto_on_complaint"
SELF_SOURCE = "self"

# AC-D12.
DATE_SOURCE_STATED = "stated"
DATE_SOURCE_OCR = "ocr"

# AC-D4's three parts, verbatim, matching what S2 seeds.
WATER_CLOSET_PARTS = ("Ceramic Body", "Flushing Fittings", "Seat Cover Soft Close")


# ----------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# ----------------------------------------------------------------------- helpers


def _module(dotted: str, why: str):
    try:
        found = importlib.util.find_spec(dotted)
    except (ImportError, ModuleNotFoundError):
        found = None
    if found is None:
        raise AssertionError(f"{dotted} does not exist. {why}")
    return importlib.import_module(dotted)


def _fn(dotted: str, name: str, signature: str):
    module = _module(dotted, f"{name}{signature} lives here.")
    fn = getattr(module, name, None)
    assert callable(fn), f"{dotted}.{name}{signature} must exist."
    return fn


def _assessment_model():
    module = _module(WARRANTY_MODELS, "S2 created it; S2b adds WarrantyAssessment.")
    cls = getattr(module, "WarrantyAssessment", None)
    assert cls is not None, (
        f"{WARRANTY_MODELS}.WarrantyAssessment must exist. It belongs to the warranty "
        "module, not the consumer one: it points at a warranty term, and uninstalling "
        "warranty must take it."
    )
    return cls


def _assess():
    return _fn(
        ASSESSMENT_SERVICE,
        "assess_complaint_line",
        "(db, complaint_product_line_id, *, as_of=None)",
    )


def _confirm():
    return _fn(
        ASSESSMENT_SERVICE,
        "confirm_assessment",
        "(db, assessment_id, *, verdict, actor_user_id, reason=None)",
    )


def _record_purchase(db, **kwargs):
    fn = _fn(
        CONSUMER_SERVICE,
        "record_purchase",
        "(db, *, purchase_date, customer_id=None, dealer_document_number=None, "
        "consumer_profile_id=None, total_value=None, currency=None, "
        "proof_attachment_id=None, registration_source=None, "
        "purchase_date_source='stated', lines=())",
    )
    return fn(db, **kwargs)


def _columns(model):
    return {c.key: c for c in model.__table__.columns}


# --------------------------------------------------------------- seed helpers


def _customer(db) -> Customer:
    row = Customer(
        id=str(uuid.uuid4()),
        customer_code=unique_code("dealer")[:50],
        customer_name=f"{TEST_PREFIX} dealer",
    )
    db.add(row)
    db.flush()
    return row


def _kind(db, name: str) -> WarrantyProductKind:
    row = WarrantyProductKind(
        id=str(uuid.uuid4()),
        code=unique_code(name.replace(" ", ""))[:64],
        name=f"{TEST_PREFIX} {name}"[:255],
    )
    db.add(row)
    db.flush()
    return row


def _policy(db) -> WarrantyPolicy:
    row = WarrantyPolicy(
        id=str(uuid.uuid4()),
        version=unique_code("v")[:32],
        effective_from=date(2000, 1, 1),
        effective_to=None,
    )
    db.add(row)
    db.flush()
    return row


def _term(db, policy, kind, part_name, **kw) -> WarrantyTerm:
    row = WarrantyTerm(
        id=str(uuid.uuid4()),
        policy_id=policy.id,
        kind_id=kind.id,
        part_name=part_name,
        duration_months=kw.get("duration_months"),
        is_lifetime=kw.get("is_lifetime", False),
        covered_defect_type_ids=kw.get("covered_defect_type_ids"),
        installation_included=kw.get("installation_included", False),
        registration_bonus_months=kw.get("registration_bonus_months"),
    )
    db.add(row)
    db.flush()
    return row


def _defect(db, label: str) -> str:
    """A defect type as a lookup option in a per-test set, returning its id."""
    lookup_set = LookupSet(
        id=str(uuid.uuid4()), set_key=unique_code("defectset")[:80], name=f"{TEST_PREFIX} defects"
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


def _complaint(db) -> Complaint:
    row = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=unique_code("CMP")[:60],
        complaint_date=date(2026, 7, 1),
        status="new",
    )
    db.add(row)
    db.flush()
    return row


def _complaint_line(db, complaint, *, purchase_line_id=None, defect_type_id=None, code="SRTWC8366"):
    row = ComplaintProductLine(
        id=str(uuid.uuid4()),
        complaint_id=complaint.id,
        product_code=code,
        quantity="1",
        sort_order=0,
    )
    # Set through setattr so the failure is the explicit schema assertion below
    # rather than an opaque TypeError from the constructor.
    for key, value in (
        ("consumer_purchase_line_id", purchase_line_id),
        ("defect_type_id", defect_type_id),
    ):
        if value is not None:
            assert key in _columns(ComplaintProductLine), (
                f"complaint_product_lines.{key} does not exist. See "
                "test_a_complaint_product_line_reaches_the_purchase_and_the_defect."
            )
            setattr(row, key, value)
    db.add(row)
    db.flush()
    return row


def _purchase_line_id(db, purchase) -> str:
    module = _module(CONSUMER_MODELS, "The ledger is S2b's first table.")
    cls = getattr(module, "ConsumerPurchaseLine")
    row = db.query(cls).filter(cls.purchase_id == purchase.id).first()
    assert row is not None, "record_purchase wrote no lines."
    return row.id


def _water_closet_case(db, *, purchase_date=date(2025, 10, 16), defect_ids=None):
    """One Water Closet purchase, three terms, one complaint line pointing at it.

    The shape AC-D10 describes: CS opens a complaint and must see every promise the
    product carries, not the first one the query happened to return.
    """
    dealer = _customer(db)
    kind = _kind(db, "Water Closet")
    policy = _policy(db)
    _term(
        db,
        policy,
        kind,
        "Ceramic Body",
        is_lifetime=True,
        installation_included=True,
        covered_defect_type_ids=defect_ids,
    )
    _term(db, policy, kind, "Flushing Fittings", duration_months=60)
    _term(db, policy, kind, "Seat Cover Soft Close", duration_months=24)

    purchase = _record_purchase(
        db,
        purchase_date=purchase_date,
        customer_id=dealer.id,
        dealer_document_number=unique_code("INV")[:40],
        lines=({"kind_id": kind.id, "claimed_text": "SRTWC8366", "quantity": 1},),
    )
    db.flush()
    complaint = _complaint(db)
    line = _complaint_line(db, complaint, purchase_line_id=_purchase_line_id(db, purchase))
    return complaint, line, purchase, kind, policy


# =============================================================================
# Schema - AC-L16 and the two columns nobody asked for
# =============================================================================


def test_an_assessment_records_the_computation_and_the_human_decision_separately():
    """AC-D10 and AC-D11's shape. ``computed_*`` is never overwritten."""
    columns = _columns(_assessment_model())
    for name in (
        "complaint_product_line_id",
        "term_id",
        "computed_verdict",
        "computed_expiry",
        "computed_at",
        "installation_included",
        "is_recommendation",
        "confirmed_verdict",
        "confirmed_by",
        "confirmed_at",
        "override_reason",
    ):
        assert name in columns, f"warranty_assessments.{name} is missing."

    assert {fk.target_fullname for fk in columns["complaint_product_line_id"].foreign_keys} == {
        "complaint_product_lines.id"
    }, "An assessment hangs off a complaint product LINE, never off a complaint."
    assert {fk.target_fullname for fk in columns["term_id"].foreign_keys} == {
        "warranty_terms.id"
    }
    assert columns["term_id"].nullable, (
        "`unknown` and `no_term` are real verdicts with no term behind them "
        "(AC-D17). A NOT NULL term_id makes the two answers that matter most - a "
        "calendar gap and a policy that is silent about this Kind - unstorable."
    )
    assert not columns["is_recommendation"].nullable, (
        "AC-D12: a verdict that cannot say whether its date was machine-read is a "
        "verdict CS over-trusts. NULL would render as 'no' on every screen."
    )


def test_an_assessment_is_one_row_per_part_not_one_per_line():
    """The plan says "one per complaint product line" and that cannot be built.

    A Water Closet carries three promises at once and they disagree on all four
    dimensions. One row with one ``term_id`` holds one of the three, so CS sees
    "covered" for the ceramic body and dispatches a technician for a seat cover
    whose two years ran out - or the reverse, and refuses a lifetime claim.

    The correction: one row per (complaint product line, term), unique on the pair,
    so re-assessing cannot double-write and each part can be confirmed or
    overridden on its own.
    """
    table = _assessment_model().__table__
    pairs = {
        tuple(c.columns.keys())
        for c in list(table.constraints) + list(table.indexes)
        if getattr(c, "unique", False)
    }
    assert ("complaint_product_line_id", "term_id") in pairs, (
        "No unique constraint on (complaint_product_line_id, term_id). Without it "
        "re-assessing a line silently doubles the verdicts CS reads, and the plan's "
        "'one per complaint product line' collapses a Water Closet's three "
        f"simultaneous promises into one. Found: {sorted(pairs)}"
    )


def test_a_complaint_product_line_reaches_the_purchase_and_the_defect():
    """AC-L16, plus the column AC-D10 needs and no AC asks for.

    ``consumer_purchase_line_id`` is AC-L16: cover is per product and per part, so
    the assessment reaches its purchase DATE through the line, not through the
    complaint.

    ``defect_type_id`` is the gap. AC-D5 makes the defect part of entitlement, and
    S2 seeded the ``complaints_defect_type`` vocabulary for it - but nothing on a
    complaint points at that set. ``complaints.defects_discovered`` is the
    ``complaints_defects_discovered`` lookup, which says WHEN a defect was noticed
    ("Upon delivery after unloading"), not what it is. Without this column the
    engine is called with ``defect_type_id=None`` on every complaint, so the
    lifetime ceramic body - the most valuable promise in the policy - returns
    ``unknown`` forever and AC-D10 shows CS a verdict that is never an answer.
    """
    columns = _columns(ComplaintProductLine)
    assert "consumer_purchase_line_id" in columns, (
        "complaint_product_lines.consumer_purchase_line_id is missing (AC-L16)."
    )
    assert columns["consumer_purchase_line_id"].nullable, (
        "A complaint routinely arrives before any receipt does. NOT NULL here would "
        "block intake, which AC-C14 forbids."
    )
    assert {
        fk.target_fullname for fk in columns["consumer_purchase_line_id"].foreign_keys
    } == {"consumer_purchase_lines.id"}

    assert "defect_type_id" in columns, (
        "complaint_product_lines.defect_type_id is missing. AC-D5 makes the defect "
        "type part of entitlement and S2 seeded the complaints_defect_type "
        "vocabulary, but no complaint column points at it - so every "
        "defect-restricted term, including the lifetime ceramic body, answers "
        "`unknown` on every complaint. AC-D10 cannot be satisfied without it."
    )
    assert {fk.target_fullname for fk in columns["defect_type_id"].foreign_keys} == {
        "lookup_options.id"
    }, "The defect vocabulary is lookup_options, NOT lookup_values (which does not exist)."


def test_warranty_assessments_are_in_a_migration_not_only_on_the_model():
    """The ADR-0012 failure: a model with no migration is green here and absent live."""
    versions = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
    sources = [p.read_text(encoding="utf-8", errors="ignore") for p in versions.glob("*.py")]
    assert any(
        "warranty_assessments" in src and "create_table" in src for src in sources
    ), "No alembic revision creates warranty_assessments."
    assert any(
        "consumer_purchase_line_id" in src and "add_column" in src for src in sources
    ), (
        "No alembic revision adds complaint_product_lines.consumer_purchase_line_id. "
        "create_all builds it from the model, so the suite passes and production has "
        "no column."
    )


# =============================================================================
# Computing the verdict - AC-D10
# =============================================================================


def test_a_water_closet_line_gets_one_assessment_per_part(db):
    """AC-D4 through to storage. Three promises, three rows, three verdicts."""
    _, line, _, _, _ = _water_closet_case(db)
    rows = _assess()(db, line.id, as_of=date(2026, 7, 1))
    db.flush()

    parts = sorted(
        r.term.part_name if getattr(r, "term", None) else r.part_name for r in rows
    )
    assert len(rows) == 3, (
        f"Expected three assessments for a Water Closet, got {len(rows)}. Storing one "
        "means CS dispatches on whichever part the query returned first."
    )
    assert parts == sorted(WATER_CLOSET_PARTS)


def test_the_assessment_carries_what_cs_must_see_before_dispatch(db):
    """AC-D10: term matched, expiry, and whether installation is included.

    "Time remaining" is derivable from the expiry and is a rendering job; whether
    the callout is chargeable is NOT derivable from anything else on the row, and
    getting it wrong bills a customer inside warranty.
    """
    _, line, _, _, _ = _water_closet_case(db, purchase_date=date(2025, 10, 16))
    rows = {r.term_id: r for r in _assess()(db, line.id, as_of=date(2026, 7, 1))}
    db.flush()

    by_part = {}
    for row in rows.values():
        term = db.query(WarrantyTerm).filter(WarrantyTerm.id == row.term_id).first()
        by_part[term.part_name] = row

    ceramic = by_part["Ceramic Body"]
    assert ceramic.computed_verdict == "covered"
    assert ceramic.computed_expiry is None, "Lifetime cover has no expiry."
    assert ceramic.installation_included is True, (
        "The ceramic body includes installation (clause 15). Losing it makes a "
        "covered callout chargeable."
    )

    fittings = by_part["Flushing Fittings"]
    assert fittings.computed_expiry == date(2030, 10, 16)
    assert fittings.installation_included is False
    assert fittings.computed_at is not None, "A verdict must say when it was computed."
    assert set(r.computed_verdict for r in rows.values()) <= VERDICTS


def test_re_assessing_a_line_does_not_duplicate_the_verdicts(db):
    """Idempotence. CS reopening a complaint must not double the panel."""
    _, line, _, _, _ = _water_closet_case(db)
    assess = _assess()
    assess(db, line.id, as_of=date(2026, 7, 1))
    db.flush()
    rows = assess(db, line.id, as_of=date(2026, 7, 2))
    db.flush()

    cls = _assessment_model()
    stored = db.query(cls).filter(cls.complaint_product_line_id == line.id).count()
    assert stored == 3, f"Re-assessing produced {stored} rows for three parts."
    assert len(rows) == 3


def test_re_assessing_never_discards_a_human_decision(db):
    """AC-D11's real teeth. Recompute must not quietly delete an override.

    A delete-and-rewrite recompute is the obvious implementation and it destroys the
    confirmed verdict, the reason and the name of whoever took responsibility for
    it - silently, on the next page load.
    """
    _, line, _, _, _ = _water_closet_case(db)
    assess = _assess()
    rows = assess(db, line.id, as_of=date(2026, 7, 1))
    db.flush()
    target = rows[0]
    _confirm()(
        db,
        target.id,
        verdict="expired",
        actor_user_id="cs-user",
        reason=f"{TEST_PREFIX} dealer confirmed a later purchase date",
    )
    db.flush()
    assessment_id = target.id

    assess(db, line.id, as_of=date(2026, 7, 5))
    db.flush()

    cls = _assessment_model()
    kept = db.query(cls).filter(cls.id == assessment_id).first()
    assert kept is not None, (
        "Re-assessing deleted the row a human had confirmed. The override, its "
        "reason and its author are gone and nothing records that they existed."
    )
    assert kept.confirmed_verdict == "expired"
    assert kept.override_reason


def test_a_line_with_no_purchase_still_gets_one_unknown_verdict(db):
    """AC-D17's rule, applied to storage. An empty panel reads as "not covered".

    A complaint routinely arrives before any receipt does (AC-C14), and CS opening
    it must see "we cannot tell yet", not a blank section they will read as a
    refusal.
    """
    complaint = _complaint(db)
    line = _complaint_line(db, complaint)
    rows = _assess()(db, line.id, as_of=date(2026, 7, 1))
    db.flush()

    assert len(rows) == 1, "Never an empty sequence, and never more than one unknown."
    assert rows[0].computed_verdict == "unknown"
    assert rows[0].term_id is None
    assert rows[0].confirmed_verdict is None


# =============================================================================
# AC-D8 - the auto-created Registration, and the year it must not give away
# =============================================================================


def test_lodging_a_complaint_registers_an_unregistered_purchase(db):
    """AC-D8. Registration is never a precondition of cover (ADR-0010).

    Policy clause 3(b) says a product must be registered before a claim is
    processed; the BRD says cover activates from the purchase date. BRD wins, so
    the registration is created rather than demanded.
    """
    ensure = _fn(
        ASSESSMENT_SERVICE, "ensure_registration_on_complaint", "(db, complaint_id)"
    )
    complaint, _, purchase, _, _ = _water_closet_case(db)
    assert purchase.registered_at is None

    ensure(db, complaint.id)
    db.flush()
    db.refresh(purchase)

    assert purchase.registered_at is not None, (
        "Lodging a complaint did not register the purchase (AC-D8)."
    )
    assert purchase.registration_source == AUTO_SOURCE, (
        "An automatic registration must say it was automatic. Without the "
        "distinction it is indistinguishable from a consumer who registered online, "
        "and the clause 26 bonus follows that distinction."
    )


def test_registering_twice_does_not_move_the_registration_date(db):
    """AC-D8, idempotence. Two complaints on one purchase is the ordinary case."""
    ensure = _fn(
        ASSESSMENT_SERVICE, "ensure_registration_on_complaint", "(db, complaint_id)"
    )
    complaint, _, purchase, _, _ = _water_closet_case(db)
    ensure(db, complaint.id)
    db.flush()
    db.refresh(purchase)
    first = purchase.registered_at

    ensure(db, complaint.id)
    db.flush()
    db.refresh(purchase)
    assert purchase.registered_at == first, "The registration date must not drift."


def test_an_auto_created_registration_never_earns_the_registration_bonus(db):
    """The most dangerous interaction in this slice, pinned.

    Clause 26 gives the Automatic Water Booster Pump 2 years, plus 12 months for
    ONLINE REGISTRATION - a deliberate act by the consumer, which Sorento gets
    consumer data for. AC-D8 auto-creates a Registration the moment a complaint is
    lodged.

    Compose them without thinking and the system grants a third year of cover at the
    exact moment of the claim, in the direction that makes the claim succeed, on a
    product Sorento sold with two. Nobody would ever see it happen: the assessment
    would simply read "covered to 2027" on a pump bought in 2024.

    The ruling: ``registered_at`` records that a registration EXISTS, which is what
    AC-D8 and clause 3(b) are about. ``registration_source`` records whether a human
    chose to register, which is what clause 26 pays for. Only the second earns
    months.
    """
    ensure = _fn(
        ASSESSMENT_SERVICE, "ensure_registration_on_complaint", "(db, complaint_id)"
    )
    module = _module(ASSESSMENT_SERVICE, "The bonus rule lives beside the assessor.")
    earning = getattr(module, "BONUS_EARNING_REGISTRATION_SOURCES", None)
    assert earning is not None, (
        "BONUS_EARNING_REGISTRATION_SOURCES must be declared as data. A boolean "
        "`registered` derived inline from `registered_at is not None` is the bug: it "
        "cannot tell a consumer's deliberate act from our own auto-stamp."
    )
    assert AUTO_SOURCE not in frozenset(earning), (
        "An auto-created registration is in the bonus-earning set. Lodging a "
        "complaint would buy the complainant a year of cover Sorento never sold."
    )

    dealer = _customer(db)
    pump = _kind(db, "Automatic Water Booster Pump")
    policy = _policy(db)
    _term(db, policy, pump, "Pump", duration_months=24, registration_bonus_months=12)
    purchase = _record_purchase(
        db,
        purchase_date=date(2024, 6, 1),
        customer_id=dealer.id,
        dealer_document_number=unique_code("INV")[:40],
        lines=({"kind_id": pump.id, "claimed_text": "BOOSTER"},),
    )
    db.flush()
    complaint = _complaint(db)
    line = _complaint_line(db, complaint, purchase_line_id=_purchase_line_id(db, purchase))

    ensure(db, complaint.id)
    db.flush()
    rows = _assess()(db, line.id, as_of=date(2026, 7, 1))
    db.flush()

    assert len(rows) == 1
    assert rows[0].computed_expiry == date(2026, 6, 1), (
        f"Expected the two-year term to end 2026-06-01, got {rows[0].computed_expiry}. "
        "An auto-created registration bought a third year at the moment of the claim."
    )


def test_a_consumer_who_registered_online_does_earn_the_bonus(db):
    """AC-D9, the E2E half. The bonus is modelled, not ignored - it just has to be earned."""
    dealer = _customer(db)
    pump = _kind(db, "Automatic Water Booster Pump")
    policy = _policy(db)
    _term(db, policy, pump, "Pump", duration_months=24, registration_bonus_months=12)
    purchase = _record_purchase(
        db,
        purchase_date=date(2024, 6, 1),
        customer_id=dealer.id,
        dealer_document_number=unique_code("INV")[:40],
        registration_source=SELF_SOURCE,
        lines=({"kind_id": pump.id, "claimed_text": "BOOSTER"},),
    )
    db.flush()
    assert purchase.registered_at is not None, (
        "A self-registration must stamp registered_at at the moment it happens."
    )

    complaint = _complaint(db)
    line = _complaint_line(db, complaint, purchase_line_id=_purchase_line_id(db, purchase))
    rows = _assess()(db, line.id, as_of=date(2026, 7, 1))
    db.flush()

    assert rows[0].computed_expiry == date(2027, 6, 1), (
        f"Online registration must extend 2y to 3y (clause 26). Got "
        f"{rows[0].computed_expiry}."
    )
    assert rows[0].computed_verdict == "covered"


def test_registration_is_never_a_precondition_of_cover(db):
    """ADR-0010, the departure from policy clause 3(b), as behaviour.

    An unregistered purchase inside its base term is COVERED. Anything that reads
    "unregistered" as "not covered" refuses a claim the BRD grants.
    """
    dealer = _customer(db)
    pump = _kind(db, "Automatic Water Booster Pump")
    policy = _policy(db)
    _term(db, policy, pump, "Pump", duration_months=24, registration_bonus_months=12)
    purchase = _record_purchase(
        db,
        purchase_date=date(2025, 6, 1),
        customer_id=dealer.id,
        dealer_document_number=unique_code("INV")[:40],
        lines=({"kind_id": pump.id},),
    )
    db.flush()
    assert purchase.registered_at is None

    complaint = _complaint(db)
    line = _complaint_line(db, complaint, purchase_line_id=_purchase_line_id(db, purchase))
    rows = _assess()(db, line.id, as_of=date(2026, 7, 1))
    db.flush()
    assert rows[0].computed_verdict == "covered"
    assert rows[0].computed_expiry == date(2027, 6, 1)


def test_ac_d8_never_invents_a_purchase_when_none_exists(db):
    """AC-D8's boundary, and the reading S2b takes.

    Registration is a timestamp on a purchase now, so "auto-created if absent" can
    only mean "the purchase exists and registered_at is NULL". With no purchase
    there is no purchase date, and the only dates available - today's, the
    complaint's - would fabricate the single number every verdict is computed from
    and would do it in the customer's favour by years.

    So nothing is created, the complaint is not blocked, and the verdict is
    ``unknown`` until a receipt arrives.
    """
    ensure = _fn(
        ASSESSMENT_SERVICE, "ensure_registration_on_complaint", "(db, complaint_id)"
    )
    module = _module(CONSUMER_MODELS, "")
    purchase_cls = getattr(module, "ConsumerPurchase")

    complaint = _complaint(db)
    line = _complaint_line(db, complaint)
    before = db.query(purchase_cls).count()

    touched = ensure(db, complaint.id)
    db.flush()

    assert db.query(purchase_cls).count() == before, (
        "AC-D8 invented a purchase for a complaint with no receipt. Its purchase_date "
        "is then a guess, and every verdict computed from it is a guess wearing a "
        "date."
    )
    assert list(touched) == [], "Nothing was registered, so nothing is reported as registered."
    rows = _assess()(db, line.id, as_of=date(2026, 7, 1))
    db.flush()
    assert rows[0].computed_verdict == "unknown"


# =============================================================================
# AC-D11 - the override
# =============================================================================


def test_an_override_retains_the_computed_verdict_beside_it(db):
    """AC-D11. The computed value is NEVER overwritten.

    Both survive side by side because the interesting question six months later is
    "what did the engine say, and who decided otherwise" - and an overwritten row
    cannot answer either half.
    """
    _, line, _, _, _ = _water_closet_case(db)
    rows = _assess()(db, line.id, as_of=date(2026, 7, 1))
    db.flush()
    target = next(r for r in rows if r.computed_verdict == "covered")
    computed_verdict, computed_expiry = target.computed_verdict, target.computed_expiry

    updated = _confirm()(
        db,
        target.id,
        verdict="expired",
        actor_user_id="cs-user",
        reason=f"{TEST_PREFIX} dealer produced an earlier invoice",
    )
    db.flush()

    assert updated.computed_verdict == computed_verdict, (
        "The human decision overwrote the computed verdict (AC-D11 forbids it)."
    )
    assert updated.computed_expiry == computed_expiry
    assert updated.confirmed_verdict == "expired"
    assert updated.confirmed_by == "cs-user", "Somebody owns every override."
    assert updated.confirmed_at is not None
    assert updated.override_reason


def test_an_override_without_a_reason_is_refused(db):
    """AC-D11: the reason is mandatory when the human disagrees with the engine.

    Refused rather than defaulted: a blank reason stored as "" satisfies a NOT NULL
    and tells the next reader nothing, which is the failure the AC is about.
    """
    from app.services.error_handler import AppException

    _, line, _, _, _ = _water_closet_case(db)
    rows = _assess()(db, line.id, as_of=date(2026, 7, 1))
    db.flush()
    target = rows[0]
    other = "expired" if target.computed_verdict != "expired" else "covered"

    with pytest.raises(AppException):
        _confirm()(db, target.id, verdict=other, actor_user_id="cs-user", reason=None)

    db.rollback()
    cls = _assessment_model()
    kept = db.query(cls).filter(cls.id == target.id).first()
    assert kept.confirmed_verdict is None, "A refused override must leave no trace."


def test_confirming_the_computed_verdict_needs_no_reason(db):
    """AC-D10's ``[Confirm]``. Agreeing with the engine is not an override.

    Demanding a reason to agree trains CS to type "ok" and destroys the signal that
    makes the override reasons worth reading.
    """
    _, line, _, _, _ = _water_closet_case(db)
    rows = _assess()(db, line.id, as_of=date(2026, 7, 1))
    db.flush()
    target = rows[0]

    updated = _confirm()(
        db, target.id, verdict=target.computed_verdict, actor_user_id="cs-user"
    )
    db.flush()
    assert updated.confirmed_verdict == target.computed_verdict
    assert not updated.override_reason, "Agreement is not an override and stores no reason."
    assert updated.confirmed_by == "cs-user"


def test_a_stored_verdict_is_always_one_of_the_five(db):
    """AC-D17's closed set, enforced at the point a human can write into it too."""
    from app.services.error_handler import AppException

    _, line, _, _, _ = _water_closet_case(db)
    rows = _assess()(db, line.id, as_of=date(2026, 7, 1))
    db.flush()
    with pytest.raises(AppException):
        _confirm()(
            db,
            rows[0].id,
            verdict="goodwill",
            actor_user_id="cs-user",
            reason=f"{TEST_PREFIX} out of warranty but repaired anyway",
        )


# =============================================================================
# AC-D12 - an OCR date makes it a recommendation
# =============================================================================


def test_an_ocr_purchase_date_makes_the_verdict_a_recommendation(db):
    """AC-D12. The provenance is a fact about the RECEIPT and belongs on the purchase.

    The consumer photographed a third-party document nobody can verify. A verdict
    computed from a machine read of it is a recommendation, and CS must be told so
    on the artifact they are reading.
    """
    columns = _columns(_module(CONSUMER_MODELS, "").ConsumerPurchase)
    assert "purchase_date_source" in columns, (
        "consumer_purchases.purchase_date_source is missing. AC-D12 needs to know "
        "where the date came from, and the assessment cannot invent that."
    )

    dealer = _customer(db)
    kind = _kind(db, "Wash Basin")
    policy = _policy(db)
    _term(db, policy, kind, "Body", duration_months=24)
    purchase = _record_purchase(
        db,
        purchase_date=date(2025, 6, 1),
        customer_id=dealer.id,
        dealer_document_number=unique_code("INV")[:40],
        purchase_date_source=DATE_SOURCE_OCR,
        lines=({"kind_id": kind.id},),
    )
    db.flush()
    complaint = _complaint(db)
    line = _complaint_line(db, complaint, purchase_line_id=_purchase_line_id(db, purchase))

    rows = _assess()(db, line.id, as_of=date(2026, 7, 1))
    db.flush()
    assert rows[0].is_recommendation is True, (
        "A verdict computed from an OCR-derived date is not flagged as a "
        "recommendation, so CS reads a machine's guess as a determination."
    )
    assert rows[0].confirmed_verdict is None, (
        "AC-D12: a recommendation is never auto-applied as a binding determination."
    )


def test_a_stated_purchase_date_is_not_a_recommendation(db):
    """The other half. Flagging everything is the same as flagging nothing."""
    _, line, _, _, _ = _water_closet_case(db)
    rows = _assess()(db, line.id, as_of=date(2026, 7, 1))
    db.flush()
    assert all(r.is_recommendation is False for r in rows)


def test_the_recommendation_flag_is_snapshotted_not_re_read(db):
    """AC-D12, and why the flag lives on both ends.

    When CS confirms the date with the dealer the purchase's provenance improves,
    and every verdict a human already acted on must keep saying what it said at the
    time. Re-reading the purchase would silently re-label historic decisions.
    """
    dealer = _customer(db)
    kind = _kind(db, "Wash Basin")
    policy = _policy(db)
    _term(db, policy, kind, "Body", duration_months=24)
    purchase = _record_purchase(
        db,
        purchase_date=date(2025, 6, 1),
        customer_id=dealer.id,
        dealer_document_number=unique_code("INV")[:40],
        purchase_date_source=DATE_SOURCE_OCR,
        lines=({"kind_id": kind.id},),
    )
    db.flush()
    complaint = _complaint(db)
    line = _complaint_line(db, complaint, purchase_line_id=_purchase_line_id(db, purchase))
    rows = _assess()(db, line.id, as_of=date(2026, 7, 1))
    db.flush()
    assessment_id = rows[0].id

    purchase.purchase_date_source = DATE_SOURCE_STATED
    db.flush()

    cls = _assessment_model()
    stored = db.query(cls).filter(cls.id == assessment_id).first()
    assert stored.is_recommendation is True, (
        "Correcting the purchase retro-labelled a verdict a human may already have "
        "acted on. The flag is a snapshot of what was true when it was computed."
    )


# =============================================================================
# AC-L13 - the house changed hands
# =============================================================================


def test_cover_resolves_when_the_house_changed_hands(db):
    """AC-L13 / fork 2. The consumer link is advisory; the purchase is authoritative.

    A new occupant complains about a water closet bought by somebody else, still
    inside its lifetime ceramic term. Cover must resolve from the purchase and its
    date, because policy clause 6 attaches it to the product.
    """
    profile_cls = getattr(_module(CONSUMER_MODELS, ""), "ConsumerProfile")
    previous = profile_cls(
        id=str(uuid.uuid4()),
        full_name=f"{TEST_PREFIX} previous owner",
        consent_purpose="warranty_service",
    )
    setattr(previous, "phone_e164", "+60123123123")
    db.add(previous)
    db.flush()

    dealer = _customer(db)
    kind = _kind(db, "Water Closet")
    policy = _policy(db)
    _term(db, policy, kind, "Ceramic Body", is_lifetime=True, installation_included=True)
    purchase = _record_purchase(
        db,
        purchase_date=date(2015, 1, 1),
        customer_id=dealer.id,
        dealer_document_number=unique_code("INV")[:40],
        consumer_profile_id=previous.id,
        lines=({"kind_id": kind.id},),
    )
    db.flush()

    # The complaint carries no consumer profile at all: a new occupant nobody has
    # ever met, reporting a fault on somebody else's receipt.
    complaint = _complaint(db)
    line = _complaint_line(db, complaint, purchase_line_id=_purchase_line_id(db, purchase))
    rows = _assess()(db, line.id, as_of=date(2026, 7, 1))
    db.flush()

    assert rows[0].computed_verdict == "covered", (
        "The new occupant's claim was refused because the purchase names somebody "
        "else. Fork 2: the consumer link is advisory, cover attaches to the product."
    )
