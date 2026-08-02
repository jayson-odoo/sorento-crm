"""S2b guards that are GREEN on arrival: things that must never appear.

Everything here asserts an ABSENCE, so none of it can be red before the
implementation exists. It is split out of ``tests/test_consumer_ledger.py`` and
``tests/test_warranty_assessments.py`` for exactly that reason: those two files
are entirely red, and mixing in guards that pass by construction would make the
red count read as partial progress.

Four families:

1. **The column fork 6 removed.** ``marketing_consent`` was in the DDL because I
   put it there and nobody decided it. Consent is warranty-and-service only, so a
   marketing flag would be a field nobody may lawfully act on - and a field that
   exists eventually gets used. Adding marketing later needs fresh consent from
   each person, not a column.

2. **The word ``procurement`` already owns (AC-L3).** ``purchase_order`` /
   ``purchase_request`` / a ``purchase`` module key all run the OPPOSITE direction:
   Sorento buying from suppliers. A consumer purchase is Sorento's dealer selling
   to a homeowner. One word for both is how a query joins the wrong table.

3. **Split is out of scope (AC-L10).** Merge is in. A half-built split - one that
   moves rows but cannot decide which purchases belonged to whom - is worse than
   none, because the data it produces is confidently wrong.

4. **The purge boundary (AC-L2).** The behavioural half lives in
   ``test_consumer_ledger.py`` and runs the real dispatcher. This static half
   catches the case that behavioural test cannot: a warranty purge handler that
   names a consumer table but happens to delete nothing on the day the test ran.

Run: venv/bin/python -m pytest tests/test_consumer_ledger_guards.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import pathlib
import re

# Importing the models package registers every table on Base.metadata, which is
# what the column guards below scan.
from app import models  # noqa: F401
from app.database import Base

REPO = pathlib.Path(__file__).resolve().parents[1]

CONSUMER_TABLES = (
    "consumer_profiles",
    "consumer_purchases",
    "consumer_purchase_lines",
)


def _maybe(dotted: str):
    """Import a module if it exists yet, else None. These guards must pass before
    S2b starts AND after it lands."""
    try:
        if importlib.util.find_spec(dotted) is None:
            return None
    except (ImportError, ModuleNotFoundError):
        return None
    return importlib.import_module(dotted)


def _source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# Fork 6 - the column that must not exist
# =============================================================================


def test_no_table_anywhere_carries_a_marketing_consent_column():
    """Fork 6. A flag nobody may act on is worse than no flag.

    Scanned across ALL metadata rather than just ``consumer_profiles``: the
    temptation is to move it somewhere adjacent (the contact, a preferences table)
    rather than to drop it, and that satisfies a narrower assertion while
    reintroducing exactly the field the ruling removed.
    """
    offenders = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.name in ("marketing_consent", "marketing_opt_in", "consent_marketing")
    ]
    assert not offenders, (
        f"Marketing-consent columns present: {offenders}. Fork 6: consent is "
        "collected for warranty and service only, so this flag could never lawfully "
        "be acted on. Marketing needs fresh consent per person, captured with "
        "wording that says so."
    )


def test_the_consumer_module_never_broadcasts_to_a_provisional_profile():
    """AC-L7's second half, as a source guard.

    A provisional profile is a phone a staff member typed. It has consented to
    nothing, so it must never reach a send path. Guarded statically because the
    behavioural version needs a marketing sender that does not exist yet.
    """
    module = _maybe("app.services.consumer_service")
    if module is None:
        return
    source = _source(pathlib.Path(module.__file__)).lower()
    for word in ("respond_io_tasks", "send_text_or_template", "broadcast", "campaign"):
        assert word not in source, (
            f"app/services/consumer_service.py mentions {word!r}. The ledger is an "
            "analytics asset under fork 6's service-only consent, not a marketing "
            "list, and the send path is where that distinction gets lost."
        )


# =============================================================================
# AC-L3 - the word procurement already owns
# =============================================================================


def test_no_module_key_called_purchase_exists():
    """AC-L3. ``procurement`` runs the opposite direction and owns the word."""
    from app.modules.runtime.discovery import discover_manifests
    from app.modules.runtime.module_manifest import MODULE_MANIFEST

    keys = set(MODULE_MANIFEST) | set(discover_manifests())
    for banned in ("purchase", "purchases", "purchasing"):
        assert banned not in keys, (
            f"A module key {banned!r} exists. `procurement` is Sorento buying from "
            "suppliers; a consumer purchase is a dealer selling to a homeowner. One "
            "word for both directions is a bug waiting for a join."
        )


def test_nothing_in_the_consumer_ledger_is_named_purchase_order():
    """AC-L3, at the table and class level."""
    offenders = [
        name
        for name in Base.metadata.tables
        if name.startswith("consumer_") and ("purchase_order" in name or "_po_" in name)
    ]
    assert not offenders, f"Procurement-shaped names in the consumer ledger: {offenders}."

    for dotted in ("app.models.consumers", "app.services.consumer_service"):
        module = _maybe(dotted)
        if module is None:
            continue
        source = _source(pathlib.Path(module.__file__))
        assert "purchase_order" not in source.lower(), (
            f"{dotted} mentions purchase_order (AC-L3)."
        )


# =============================================================================
# AC-L10 - merge is in scope, split is not
# =============================================================================


def test_profile_split_is_not_implemented():
    """AC-L10. Merge only.

    A split has to decide which purchases belonged to which of two people who
    shared a phone, and nothing in the data answers that. Half-splitting produces
    confidently wrong history, which is worse than a merge somebody regrets.
    """
    module = _maybe("app.services.consumer_service")
    if module is None:
        return
    for name in dir(module):
        assert not re.match(r"^split_(profile|consumer)", name), (
            f"consumer_service.{name} exists. Split is explicitly out of scope "
            "(AC-L10) because nothing in the data says which purchases belonged to "
            "which person on a shared handset."
        )


# =============================================================================
# AC-L2 - the purge boundary, statically
# =============================================================================


def test_the_warranty_purge_never_names_a_consumer_table():
    """AC-L2's static half.

    The behavioural test in ``test_consumer_ledger.py`` runs the real dispatcher on
    real rows. This one catches what that cannot: a handler that references a
    consumer table under a condition which happened to be false during the test.
    """
    for candidate in (
        REPO / "app" / "modules" / "warranty" / "purge.py",
        REPO / "app" / "services" / "module_purge_service.py",
    ):
        if not candidate.exists():
            continue
        source = _source(candidate)
        if candidate.name == "module_purge_service.py":
            # Only the warranty handler is in scope here; a consumers handler in the
            # same file is expected to name consumer tables.
            match = re.search(
                r"def purge_warranty\b.*?(?=\ndef |\Z)", source, flags=re.DOTALL
            )
            if match is None:
                continue
            source = match.group(0)
        for table in CONSUMER_TABLES + ("ConsumerProfile", "ConsumerPurchase"):
            assert table not in source, (
                f"{candidate.name} lets a warranty purge reach {table}. AC-L2: "
                "uninstalling the engine must leave the ledger and the consumer list "
                "standing - that is the test that decided fork 7."
            )


def test_the_consumer_purge_never_reaches_complaints_or_the_engine():
    """The converse boundary. The ledger owns its three tables and nothing else.

    A consumers purge that deletes complaints would remove the customer-service
    record of a fault because somebody uninstalled a data module.
    """
    for candidate in (
        REPO / "app" / "modules" / "consumers" / "purge.py",
        REPO / "app" / "services" / "module_purge_service.py",
    ):
        if not candidate.exists():
            continue
        source = _source(candidate)
        if candidate.name == "module_purge_service.py":
            match = re.search(
                r"def purge_consumers\b.*?(?=\ndef |\Z)", source, flags=re.DOTALL
            )
            if match is None:
                continue
            source = match.group(0)
        for foreign in ("Complaint", "complaints", "warranty_terms", "WarrantyTerm"):
            assert foreign not in source, (
                f"A consumers purge reaches {foreign}. The ledger owns "
                f"{', '.join(CONSUMER_TABLES)} and nothing else."
            )


# =============================================================================
# AC-D13, extended - the abandoned column stays abandoned
# =============================================================================


def test_the_new_s2b_code_never_reads_products_warranty_months():
    """AC-D13, applied to the modules S2b adds.

    ``products.warranty_months`` is 0 of 11,415 populated and is abandoned. S2
    guards its own modules; this extends the same guard to the ledger and the
    assessor, which are the next two places somebody would reach for a
    per-product duration.
    """
    for dotted in (
        "app.models.consumers",
        "app.services.consumer_service",
        "app.services.warranty_assessment_service",
    ):
        module = _maybe(dotted)
        if module is None:
            continue
        source = _source(pathlib.Path(module.__file__))
        assert "warranty_months" not in source, (
            f"{dotted} mentions products.warranty_months. It is empty on every row "
            "and abandoned (AC-D13); cover comes from warranty_terms."
        )
