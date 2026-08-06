"""Certificate expiry reminders (group REM): the automation trigger, its
context, its rule facts and its batch stamp.

Postgres only, on an isolated blank schema whose writes are discarded. Every
test seeds its own chain - attachment type, attachment, category, uom, product,
certificate, revision, coverage - under a ZZTREM marker. Nothing is borrowed
from an existing table: CI's database has no data, so a ``LIMIT 1`` off
``certificates`` there returns None and everything built on it collapses.

The one thing these tests are really guarding is the EXACT-DATE contract: a
reminder fires on the boundary day and on no other day. There is deliberately no
catch-up window (REM-7), so an off-by-one here is a reminder that never arrives.
"""
from datetime import date, timedelta
from typing import Any

import pytest

from app.models.automation import Automation
from app.models.certificate import (
    CERTIFICATE_STATUS_ACTIVE,
    CERTIFICATE_STATUS_ARCHIVED,
    Certificate,
    CertificateProduct,
    CertificateRevision,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.services import automation_triggers
from app.services.automation_service import _EXPIRY_BATCH_SPECS, AutomationService
from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTREM"
TRIGGER = "days_before_certificate_expiry"
TZ = "Asia/Kuala_Lumpur"


# --------------------------------------------------------------------- fixtures
@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def chain(db) -> dict[str, Any]:
    attachment_type = AttachmentType(
        type_name=f"{MARKER} Certification",
        allowed_extensions="pdf",
        max_file_size_mb=10,
        is_certificate=True,
    )
    category = ProductCategory(
        category_code=unique_code(MARKER), category_name=f"{MARKER} category"
    )
    uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name=f"{MARKER} unit")
    db.add_all([attachment_type, category, uom])
    db.flush()
    return {"attachment_type": attachment_type, "category": category, "uom": uom}


def _today(db) -> date:
    """Today as the trigger sees it, so a test can never drift off the boundary."""
    return automation_triggers._today_in_tz(TZ)


def _product(db, chain, stem: str) -> Any:
    product = Product(
        product_code=unique_code(f"{MARKER}-{stem}"),
        product_name=f"{MARKER} {stem}",
        category_id=chain["category"].id,
        base_uom_id=chain["uom"].id,
        list_price=10,
    )
    db.add(product)
    db.flush()
    return product


def _attachment(db, chain, name: str) -> Any:
    attachment = Attachment(
        attachment_type_id=chain["attachment_type"].id,
        original_filename=f"{MARKER}-{name}.pdf",
        stored_filename=f"{MARKER}-{name}.pdf",
        file_path=f"https://cdn.example/{MARKER}/{name}.pdf",
    )
    db.add(attachment)
    db.flush()
    return attachment


def _certificate(
    db,
    chain,
    *,
    number: str,
    valid_until: date | None,
    scheme: str = f"{MARKER}PPS",
    certifying_body: str = "IKRAM",
    status: str = CERTIFICATE_STATUS_ACTIVE,
    products: int = 0,
    superseded_valid_until: date | None = None,
) -> Any:
    """Certificate + its current revision (+ an optional superseded one)."""
    certificate = Certificate(
        attachment_type_id=chain["attachment_type"].id,
        scheme=scheme,
        certificate_number=f"{MARKER}-{number}",
        certifying_body=certifying_body,
        issuer=f"{MARKER} issuer",
        title=f"{MARKER} certification",
        status=status,
    )
    db.add(certificate)
    db.flush()

    revision_no = 1
    if superseded_valid_until is not None:
        db.add(
            CertificateRevision(
                certificate_id=certificate.id,
                revision_no=revision_no,
                attachment_id=_attachment(db, chain, f"{number}-r1").id,
                valid_until=superseded_valid_until,
                is_current=False,
            )
        )
        db.flush()
        revision_no += 1

    current = CertificateRevision(
        certificate_id=certificate.id,
        revision_no=revision_no,
        attachment_id=_attachment(db, chain, f"{number}-r{revision_no}").id,
        valid_from=date(2024, 1, 1),
        valid_until=valid_until,
        is_current=True,
    )
    db.add(current)
    db.flush()
    certificate.current_revision_id = current.id

    for i in range(products):
        db.add(
            CertificateProduct(
                certificate_id=certificate.id,
                product_id=_product(db, chain, f"{number}-{i}").id,
            )
        )
    db.flush()
    return certificate


def _fire(db, days_before: int) -> list[Any]:
    return automation_triggers.fire(db, TRIGGER, {"days_before": days_before}, TZ)


def _numbers(matches) -> set[str]:
    return {m.context["certificate"]["certificate_number"] for m in matches}


# ------------------------------------------------------------------ registration
def test_trigger_is_registered_with_the_certificate_fact_source():
    """REM-1 / REM-6: config takes days_before and conditions_json can read
    certificate facts."""
    spec = next(s for s in automation_triggers.list_specs() if s.type == TRIGGER)
    assert spec.fact_sources == ("certificate",)
    assert "days_before" in spec.config_schema["properties"]
    assert automation_triggers.fact_sources_for(TRIGGER) == ("certificate",)


# ------------------------------------------------------------------ REM-1 exact date
def test_matches_only_on_the_exact_boundary_day(db, chain):
    today = _today(db)
    _certificate(db, chain, number="BOUNDARY", valid_until=today + timedelta(days=30))

    assert _numbers(_fire(db, 30)) == {f"{MARKER}-BOUNDARY"}
    # Day-1 and day+1 windows must not see it: no catch-up, no early warning.
    assert _numbers(_fire(db, 29)) == set()
    assert _numbers(_fire(db, 31)) == set()


def test_a_certificate_expiring_tomorrow_does_not_match_a_thirty_day_window(db, chain):
    today = _today(db)
    _certificate(db, chain, number="TOMORROW", valid_until=today + timedelta(days=1))
    assert _numbers(_fire(db, 30)) == set()
    assert _numbers(_fire(db, 1)) == {f"{MARKER}-TOMORROW"}


def test_already_expired_certificates_never_match(db, chain):
    today = _today(db)
    _certificate(db, chain, number="GONE", valid_until=today - timedelta(days=30))
    for days in (0, 7, 30, 90):
        assert _numbers(_fire(db, days)) == set()


# ------------------------------------------------------------------ REM-2 exclusions
def test_archived_certificates_are_never_reminded(db, chain):
    """LIF-2: archived is terminal for reminder purposes, whatever the dates say."""
    today = _today(db)
    _certificate(
        db,
        chain,
        number="ARCHIVED",
        valid_until=today + timedelta(days=30),
        status=CERTIFICATE_STATUS_ARCHIVED,
    )
    _certificate(db, chain, number="LIVE", valid_until=today + timedelta(days=30))

    assert _numbers(_fire(db, 30)) == {f"{MARKER}-LIVE"}


def test_null_valid_until_is_inert(db, chain):
    """A missing date is never treated as "no expiry" - and never as a match."""
    _certificate(db, chain, number="NODATE", valid_until=None)
    for days in (0, 7, 30, 90):
        assert _numbers(_fire(db, days)) == set()


def test_a_superseded_revision_window_never_fires(db, chain):
    """The renewal moved the expiry out; revision 1's old date must be dead."""
    today = _today(db)
    _certificate(
        db,
        chain,
        number="RENEWED",
        superseded_valid_until=today + timedelta(days=30),
        valid_until=today + timedelta(days=400),
    )
    assert _numbers(_fire(db, 30)) == set()
    assert _numbers(_fire(db, 400)) == {f"{MARKER}-RENEWED"}


def test_a_certificate_with_no_current_revision_is_skipped(db, chain):
    certificate = Certificate(
        attachment_type_id=chain["attachment_type"].id,
        scheme=f"{MARKER}PPS",
        certificate_number=f"{MARKER}-NOREV",
        status=CERTIFICATE_STATUS_ACTIVE,
    )
    db.add(certificate)
    db.flush()
    for days in (0, 7, 30, 90):
        assert _numbers(_fire(db, days)) == set()


# ------------------------------------------------------------------ REM-3 90 / 30 / 7
def test_three_windows_produce_three_independent_reminders(db, chain):
    """Three automation rows, no new code: each window sees only its own day."""
    today = _today(db)
    for days in (90, 30, 7):
        _certificate(
            db, chain, number=f"W{days}", valid_until=today + timedelta(days=days)
        )

    assert _numbers(_fire(db, 90)) == {f"{MARKER}-W90"}
    assert _numbers(_fire(db, 30)) == {f"{MARKER}-W30"}
    assert _numbers(_fire(db, 7)) == {f"{MARKER}-W7"}


def test_a_multi_certificate_day_yields_one_match_per_certificate(db, chain):
    """Four certificates really do share 23 Dec 2026 in live data; grouping into
    one email is the sender's job, so the trigger must emit all four."""
    today = _today(db)
    for i in range(4):
        _certificate(db, chain, number=f"SAMEDAY{i}", valid_until=today + timedelta(days=90))

    matches = _fire(db, 90)
    assert len(matches) == 4
    assert {m.source_kind for m in matches} == {"certificate"}


# ------------------------------------------------------------------ REM-4 context
def test_context_carries_the_internal_deep_link_and_the_facts(db, chain):
    today = _today(db)
    certificate = _certificate(
        db,
        chain,
        number="CONTEXT",
        valid_until=today + timedelta(days=7),
        certifying_body="JBC",
        products=3,
    )

    match = _fire(db, 7)[0]
    ctx = match.context["certificate"]
    assert ctx["scheme"] == f"{MARKER}PPS"
    assert ctx["certificate_number"] == f"{MARKER}-CONTEXT"
    assert ctx["certifying_body"] == "JBC"
    assert ctx["valid_until"] == (today + timedelta(days=7)).isoformat()
    assert ctx["days_until_expiry"] == 7
    assert ctx["covered_product_count"] == 3
    assert match.context["today"] == today.isoformat()
    assert match.source_id == str(certificate.id)

    # Staff recipients get the in-system page, never a public /view?token= link.
    assert ctx["link"].endswith(f"/master-data-management/certificates/{certificate.id}")
    assert "/view?token=" not in ctx["link"]


def test_covered_product_count_is_zero_when_nothing_is_covered(db, chain):
    """The PPS 04224FC case: a real certificate with no coverage still reminds."""
    today = _today(db)
    _certificate(db, chain, number="NOCOVER", valid_until=today + timedelta(days=30))
    assert _fire(db, 30)[0].context["certificate"]["covered_product_count"] == 0


# ------------------------------------------------------------------ REM-6 conditions
def _filter(db, matches, tree):
    automation = Automation(
        name=f"{MARKER} filter",
        trigger_type=TRIGGER,
        conditions_json=tree,
    )
    return AutomationService(db)._filter_matches_by_conditions(automation, matches)


def test_conditions_json_can_scope_the_reminder_to_one_scheme(db, chain):
    today = _today(db)
    _certificate(db, chain, number="PPSONE", valid_until=today + timedelta(days=30))
    _certificate(
        db,
        chain,
        number="SPANONE",
        valid_until=today + timedelta(days=30),
        scheme=f"{MARKER}SPAN",
    )
    matches = _fire(db, 30)
    assert len(matches) == 2

    kept = _filter(
        db,
        matches,
        {
            "combinator": "and",
            "rules": [
                {"fact": "certificate.scheme", "operator": "eq", "value": f"{MARKER}SPAN"}
            ],
        },
    )
    assert _numbers(kept) == {f"{MARKER}-SPANONE"}


def test_an_empty_condition_tree_matches_every_certificate(db, chain):
    """The rule-engine trap, pinned: empty means everything, not nothing."""
    today = _today(db)
    _certificate(db, chain, number="EMPTY1", valid_until=today + timedelta(days=30))
    _certificate(db, chain, number="EMPTY2", valid_until=today + timedelta(days=30))
    matches = _fire(db, 30)

    assert len(_filter(db, matches, None)) == 2
    assert len(_filter(db, matches, {"combinator": "and", "rules": []})) == 2


# ------------------------------------------------------------------ REM-5 batch stamp
def test_the_batch_stamp_marks_every_kept_certificate_and_links_to_the_set(db, chain):
    today = _today(db)
    first = _certificate(db, chain, number="BATCH1", valid_until=today + timedelta(days=30))
    second = _certificate(db, chain, number="BATCH2", valid_until=today + timedelta(days=30))
    matches = _fire(db, 30)

    service = AutomationService(db)
    batch_id, batch_link = service._stamp_expiry_batch(
        matches, _EXPIRY_BATCH_SPECS[TRIGGER]
    )

    assert batch_id
    assert batch_link.endswith(
        f"/master-data-management/certificates?expiry_notify_batch_id={batch_id}"
    )
    for certificate in (first, second):
        db.refresh(certificate)
        assert str(certificate.expiry_notify_batch_id) == batch_id
        assert certificate.expiry_notified_at is not None


def test_an_unmatched_certificate_is_not_stamped(db, chain):
    today = _today(db)
    matched = _certificate(db, chain, number="STAMPED", valid_until=today + timedelta(days=30))
    untouched = _certificate(
        db, chain, number="UNSTAMPED", valid_until=today + timedelta(days=200)
    )

    AutomationService(db)._stamp_expiry_batch(_fire(db, 30), _EXPIRY_BATCH_SPECS[TRIGGER])

    db.refresh(matched)
    db.refresh(untouched)
    assert matched.expiry_notify_batch_id is not None
    assert untouched.expiry_notify_batch_id is None
    assert untouched.expiry_notified_at is None


def test_no_matches_mints_no_batch(db, chain):
    batch_id, batch_link = AutomationService(db)._stamp_expiry_batch(
        [], _EXPIRY_BATCH_SPECS[TRIGGER]
    )
    assert batch_id is None and batch_link is None


def test_a_second_run_mints_a_fresh_batch_id(db, chain):
    today = _today(db)
    certificate = _certificate(db, chain, number="RERUN", valid_until=today + timedelta(days=30))
    service = AutomationService(db)

    first_id, _ = service._stamp_expiry_batch(_fire(db, 30), _EXPIRY_BATCH_SPECS[TRIGGER])
    second_id, _ = service._stamp_expiry_batch(_fire(db, 30), _EXPIRY_BATCH_SPECS[TRIGGER])

    assert first_id != second_id
    db.refresh(certificate)
    assert str(certificate.expiry_notify_batch_id) == second_id
