"""S2b gate, part 1 - the consumers module and the purchase ledger (Group L).

Written BEFORE the implementation. Every failure here should name a missing
module, column, function or seed. Nothing in this file is green on arrival; the
guards that pass by construction live in ``tests/test_consumer_ledger_guards.py``
so this file's red count reads as real work outstanding.

The seven forks in ``documentation/plans/after-sales/OPEN-consumer-ledger-grill.md``
are all RESOLVED and this file encodes them. Where an AC is silent, the decision is
taken here and asserted rather than left to the implementer, because an answer
nobody wrote down gets re-decided by the next person in the opposite direction.

Six things shape this suite, and each is a place the obvious implementation is
wrong:

1. **``respond_contacts.id`` is TEXT.** The plan's DDL prints
   ``respond_contact_id uuid UNIQUE REFERENCES respond_contacts(id)``, and that
   cannot be built: a uuid column cannot foreign-key a text one. This is the exact
   trap S1 hit with ``respond_contacts.user_id`` (AC-A2, AC-F2b-1) and the plan
   walked straight back into it. See
   ``test_the_respond_contact_link_is_text_because_respond_contacts_id_is_text``.

2. **The profile holds no phone, so "dedupe on E.164 phone" has no column to
   dedupe on.** Identity lives on ``respond_contacts``, whose ``phone_number`` is
   unique on the RAW string - so ``0166372304`` and ``+60166372304`` are already
   two rows there, and a profile keyed 1:1 on the contact inherits the split
   AC-L8 exists to prevent. The ledger therefore needs its own normalised phone
   column, uniquely indexed, and ``ensure_profile`` must resolve on THAT rather
   than on whatever the contact row happens to spell. See
   ``test_three_spellings_of_one_phone_resolve_to_one_profile``.

3. **Nothing promotes a provisional profile today.** AC-L6 says "the first time
   that phone completes an OTP login", and the only code that completes an OTP
   login is ``PortalService.verify_otp``. If S2b does not call the promotion from
   there, ``is_provisional`` is true forever and AC-L7's honest headline count
   degrades to "everyone is provisional", silently. The test drives the real OTP
   path rather than calling the promotion directly, because calling it directly
   would pass while the property it protects is false.

4. **Anonymisation must sever reachability, not just blank a name.** The person is
   reachable through ``respond_contact_id``, and clearing the name while leaving
   that FK in place is erasure theatre. The purchase must survive and still
   resolve cover. What this file CANNOT do is scrub ``respond_contacts`` itself -
   that row is shared with complaints, chat history and SLA, and deleting it is a
   different and much larger decision. Recorded, not decided here.

5. **Two receipts sharing a dealer and a date but only one document number are NOT
   duplicates under a partial index, and both write.** That is correct - the
   alternative refuses a real second purchase - but it means the ledger holds
   near-duplicates by design and the review list is the only thing that catches
   them. Asserted as behaviour so nobody "fixes" it into a rejection.

6. **A false collision links a complaint to the WRONG purchase.** "Link, never
   reject" makes the normaliser's aggressiveness a warranty-dating risk, not just
   a tidiness one: two genuinely different documents that normalise alike put the
   second complaint on the first purchase's date. The normaliser is pinned to the
   three spellings AC-L8's sibling case names and nothing looser.

Decisions taken here because the AC is silent:

- **``consumer_purchases`` is company-scoped as well as ``consumer_profiles``.**
  AC-L29 scopes only the profile, but the profile is NULLABLE on a purchase and
  the purchase is the row cover resolves from. An unscoped ledger lets Mocha's CS
  read Sorento's dealer sell-through. Lines are NOT separately scoped - they are
  reachable only through the header, and a second copy of the same fact can
  disagree with the first (the same reasoning ``warranty_terms`` already uses).
- **A merged profile is retained with ``merged_into_id`` set, not deleted.** Split
  is out of scope, so the losing row need never be revived - but "where did this
  consumer go" must be answerable, and a deleted row cannot answer it.
- **Value is OMITTED, not nulled, without the permission.** ``None`` reads as "the
  receipt showed no total", which is a different fact from "you may not see it".
- **A purchase written with no identity does not silently acquire one later.**
  Back-linking on a phone match would attach a stranger's receipt to a household
  that shares a number. Recorded as a gap, not implemented as magic.

Run: venv/bin/python -m pytest tests/test_consumer_ledger.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import pathlib
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

from app.models.base import CompanyScopedMixin
from app.models.access import RespondContact
from app.models.order import Customer
from app.models.portal import PortalOtpCode
from app.models.resources import Attachment

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

# ---------------------------------------------------------------- the contract
#
# Names S2b is expected to add, as constants so the implementer reads the whole
# contract on one screen and a rename is one edit.

# Fork 7: the ledger is its OWN module. Not core (core is exactly one module today,
# `base`, and consumer data would be the first domain data in it), and not part of
# `warranty` - uninstalling the warranty engine must not take the consumer list.
CONSUMER_MODELS = "app.models.consumers"
CONSUMER_SERVICE = "app.services.consumer_service"
CONSUMER_MANIFEST = "app.modules.consumers.manifest"

# S2 shipped four warranty TABLES and no warranty MODULE. AC-L1 requires `warranty`
# to declare a dependency on `consumers`, which it cannot do without a manifest, so
# S2b creates one. Until it exists the warranty tables are ungoverned by the App
# Store: they can be neither installed, disabled nor purged.
WARRANTY_MANIFEST = "app.modules.warranty.manifest"

CONSUMERS_MODULE_KEY = "consumers"
WARRANTY_MODULE_KEY = "warranty"

# AC-L1, verbatim.
CONSUMERS_DEPENDENCIES = frozenset({"base", "product", "order"})

# AC-L24. Off by default: retail prices must not appear on every CS screen where a
# dealer's own staff might be shoulder-reading during a support call.
VALUE_PERMISSION = "consumers.purchase_value.view"

# Fork 6. One purpose, and no marketing flag anywhere - a field nobody may lawfully
# act on is worse than no field.
CONSENT_PURPOSE = "warranty_service"

# Where a registration came from. `auto_on_complaint` is the AC-D8 path and is the
# reason this vocabulary exists at all: see tests/test_warranty_assessments.py,
# which pins that an automatic registration earns no bonus months.
REGISTRATION_SOURCES = ("self", "auto_on_complaint", "smc", "ecommerce")

# AC-L8's three spellings of one Malaysian mobile.
PHONE_SPELLINGS = ("0166372304", "+60166372304", "60 166372304")
PHONE_E164 = "+60166372304"


# ----------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# ----------------------------------------------------------------------- helpers


def _module(dotted: str, why: str):
    """Import a module S2b is expected to add, or fail naming the contract."""
    try:
        found = importlib.util.find_spec(dotted)
    except (ImportError, ModuleNotFoundError):
        found = None
    if found is None:
        raise AssertionError(f"{dotted} does not exist. {why}")
    return importlib.import_module(dotted)


def _models():
    return _module(
        CONSUMER_MODELS,
        "S2b adds consumer_profiles, consumer_purchases and consumer_purchase_lines. "
        "They are one module because they are one lifecycle, and they are NOT in "
        "app/models/warranty.py: fork 7 put the ledger in its own module so "
        "uninstalling warranty leaves the consumer list standing.",
    )


def _model(name: str):
    module = _models()
    cls = getattr(module, name, None)
    assert cls is not None, f"{CONSUMER_MODELS}.{name} must exist."
    return cls


def _fn(dotted: str, name: str, signature: str):
    module = _module(dotted, f"{name}{signature} lives here.")
    fn = getattr(module, name, None)
    assert callable(fn), f"{dotted}.{name}{signature} must exist."
    return fn


def _svc(name: str, signature: str):
    return _fn(CONSUMER_SERVICE, name, signature)


def _columns(model):
    return {c.key: c for c in model.__table__.columns}


def _column(model, name: str):
    columns = _columns(model)
    assert name in columns, (
        f"{model.__tablename__}.{name} is missing. See the constant block at the top "
        "of this file for what it is for."
    )
    return columns[name]


# --------------------------------------------------------------- seed helpers
#
# Real rows in the blank schema. Postgres enforces the foreign keys sqlite ignored,
# so every parent is created for real.


def _customer(db, name: str = "dealer") -> Customer:
    row = Customer(
        id=str(uuid.uuid4()),
        customer_code=unique_code(name)[:50],
        customer_name=f"{TEST_PREFIX} {name}",
    )
    db.add(row)
    db.flush()
    return row


def _contact(db, phone: str | None = None, name: str | None = None) -> RespondContact:
    """A respond_contacts row whose id is deliberately NOT a uuid.

    ``respond_contacts.id`` is TEXT with a uuid-shaped default, so a test seeding a
    uuid there would keep passing against a uuid FK column - which is precisely the
    bug this file exists to catch.
    """
    row = RespondContact(
        id=unique_code("contact").lower(),
        phone_number=phone or f"+60{uuid.uuid4().int % 10**9:09d}",
        name=name or f"{TEST_PREFIX} contact",
    )
    db.add(row)
    db.flush()
    return row


def _attachment(db, *, file_hash: str | None = None) -> Attachment:
    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename=f"{unique_code('receipt')}.jpg",
        stored_filename=f"{unique_code('receipt')}.jpg",
        file_path=f"receipt/{uuid.uuid4().hex}.jpg",
        file_hash=file_hash,
    )
    db.add(row)
    db.flush()
    return row


def _kind(db, name: str = "Water Closet"):
    from app.models.warranty import WarrantyProductKind

    row = WarrantyProductKind(
        id=str(uuid.uuid4()),
        code=unique_code(name.replace(" ", ""))[:64],
        name=f"{TEST_PREFIX} {name}"[:255],
    )
    db.add(row)
    db.flush()
    return row


def _profile(db, *, phone: str = PHONE_E164, full_name: str | None = None, **kw):
    """A profile written directly, for tests about a profile that already exists."""
    cls = _model("ConsumerProfile")
    row = cls(
        id=str(uuid.uuid4()),
        full_name=full_name or f"{TEST_PREFIX} Ong Mei Ling",
        consent_purpose=CONSENT_PURPOSE,
    )
    for key, value in {"phone_e164": phone, **kw}.items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    return row


def _record_purchase(db, **kwargs):
    """``record_purchase`` with the arguments every caller must supply."""
    fn = _svc(
        "record_purchase",
        "(db, *, purchase_date, customer_id=None, dealer_document_number=None, "
        "consumer_profile_id=None, total_value=None, currency=None, "
        "proof_attachment_id=None, registration_source=None, "
        "purchase_date_source='stated', lines=())",
    )
    return fn(db, **kwargs)


def _headers_for(db, *, customer_id, document_norm, purchase_date) -> int:
    """Count headers matching a dedupe key. Scoped - never counts the whole table."""
    cls = _model("ConsumerPurchase")
    return (
        db.query(cls)
        .filter(cls.customer_id == customer_id)
        .filter(cls.dealer_document_number_norm == document_norm)
        .filter(cls.purchase_date == purchase_date)
        .count()
    )


# =============================================================================
# Module and ownership - AC-L1, AC-L2, AC-L3
# =============================================================================


def test_a_consumers_module_declares_itself_with_the_dependencies_ac_l1_names():
    """AC-L1. Fork 7's whole point, expressed the way this repo expresses modules.

    A manifest, not a bootstrap shim: ``app/modules/<key>/manifest.py`` is what
    ``discover_manifests`` reads, what seeds ``app_modules_catalog``, and what makes
    the router guard resolvable. A ``bootstrap.py`` declaring ``MODULE_KEY`` alone
    is invisible to all three.
    """
    manifest = _module(
        CONSUMER_MANIFEST,
        "Fork 7: the ledger is its own installable module. Without a manifest the "
        "key never reaches app_modules_catalog, so it can be neither installed nor "
        "guarded nor purged.",
    )
    assert getattr(manifest, "MODULE_KEY", None) == CONSUMERS_MODULE_KEY
    assert frozenset(getattr(manifest, "DEPENDENCIES", ())) == CONSUMERS_DEPENDENCIES, (
        "AC-L1 names deps base, product, order exactly. `warranty` must NOT be one "
        "of them - the dependency runs the other way, and declaring it both ways is "
        "a cycle the install resolver refuses."
    )
    assert getattr(manifest, "IS_CORE", False) is False, (
        "Core stays exactly one module (`base`). Consumer data would be the first "
        "domain data in core, and a direct-selling tenant would never install it."
    )
    assert getattr(manifest, "GUARD_KEY", None) == CONSUMERS_MODULE_KEY, (
        "Routers are wrapped by discover_module_routers using GUARD_KEY. Without it "
        "the consumer endpoints answer for a tenant that never installed the module."
    )
    assert getattr(manifest, "USE_API_KEY_GUARD", False) is True, (
        "require_module_enabled_with_api_key, not the JWT-only guard: n8n and the "
        "MCP server reach the ledger with X-API-Key."
    )


def test_warranty_is_a_module_and_declares_a_dependency_on_consumers():
    """AC-L1's second half, and a gap S2 left open.

    S2 shipped four warranty TABLES and no module key at all, so `warranty` is
    absent from ``app_modules_catalog`` and cannot declare a dependency on anything.
    The dependency direction is the fork-7 ruling: warranty needs the ledger,
    the ledger does not need warranty.
    """
    manifest = _module(
        WARRANTY_MANIFEST,
        "S2 created warranty_product_kinds / warranty_kind_rules / warranty_policies "
        "/ warranty_terms but no module key, so the App Store cannot see them. "
        "AC-L1 requires `warranty` to declare a dependency on `consumers`, which "
        "needs a manifest to declare it in.",
    )
    assert getattr(manifest, "MODULE_KEY", None) == WARRANTY_MODULE_KEY
    deps = frozenset(getattr(manifest, "DEPENDENCIES", ()))
    assert CONSUMERS_MODULE_KEY in deps, (
        "warranty depends on consumers (fork 7). Assessments are per purchase line, "
        f"so the engine cannot answer without the ledger. Found {sorted(deps)}."
    )
    assert WARRANTY_MODULE_KEY not in frozenset(
        getattr(_module(CONSUMER_MANIFEST, ""), "DEPENDENCIES", ())
    ), "The dependency is one-way. Both directions is a cycle."


def test_core_stays_exactly_one_module():
    """AC-L1's last clause. `base` is core and nothing else becomes core.

    Checked against the discovered manifests rather than the hardcoded list,
    because that is what actually seeds ``app_modules_catalog.is_core``.
    """
    from app.modules.runtime.discovery import discover_manifests

    found = discover_manifests()
    core = sorted(key for key, mf in found.items() if getattr(mf, "is_core", False))
    assert core in ([], ["base"]), (
        f"More than the base module claims core: {core}. Core is a promise that "
        "every tenant carries the thing forever."
    )
    assert CONSUMERS_MODULE_KEY in found, (
        "discover_manifests() does not see the consumers module. It is what seeds "
        "app_modules_catalog and what mounts the guarded router."
    )
    assert WARRANTY_MODULE_KEY in found, (
        "discover_manifests() does not see the warranty module."
    )


def test_installing_warranty_installs_consumers_first(db):
    """AC-L1 as behaviour: the resolver must plan the ledger before the engine."""
    from app.modules.runtime.installer import load_dependency_graph
    from app.modules.runtime.resolver import resolve_install_plan

    graph = load_dependency_graph(db)
    assert CONSUMERS_MODULE_KEY in graph, (
        "app_modules_catalog has no `consumers` row. _ensure_catalog_rows seeds from "
        "the merged manifests, so a missing manifest is a missing catalog row."
    )
    assert WARRANTY_MODULE_KEY in graph, "app_modules_catalog has no `warranty` row."

    plan = resolve_install_plan(graph, [WARRANTY_MODULE_KEY])
    assert CONSUMERS_MODULE_KEY in plan, "Installing warranty must pull in consumers."
    assert plan.index(CONSUMERS_MODULE_KEY) < plan.index(WARRANTY_MODULE_KEY), (
        f"Dependencies install first. Got {plan}."
    )


def test_consumers_cannot_be_uninstalled_while_warranty_is_installed(db):
    """AC-L2's other direction, which is the one that protects the engine.

    AC-L2 asserts the ledger survives losing warranty. The converse must NOT hold:
    removing the ledger under a live warranty engine leaves assessments pointing at
    purchase lines that no longer exist.
    """
    from app.modules.runtime.installer import load_dependency_graph
    from app.modules.runtime.resolver import installed_modules_blocking_uninstall

    graph = load_dependency_graph(db)
    for key in (CONSUMERS_MODULE_KEY, WARRANTY_MODULE_KEY):
        assert key in graph, (
            f"app_modules_catalog has no `{key}` row, so the resolver raises rather "
            "than answering. Both manifests must exist before this question means "
            "anything."
        )
    blocking = installed_modules_blocking_uninstall(
        graph, CONSUMERS_MODULE_KEY, {CONSUMERS_MODULE_KEY, WARRANTY_MODULE_KEY}
    )
    assert WARRANTY_MODULE_KEY in blocking, (
        "warranty must block uninstalling consumers. Found "
        f"{blocking or 'nothing blocking'}."
    )

    # And the reverse: warranty comes out cleanly.
    assert (
        installed_modules_blocking_uninstall(
            graph, WARRANTY_MODULE_KEY, {CONSUMERS_MODULE_KEY, WARRANTY_MODULE_KEY}
        )
        == []
    ), "Nothing depends on warranty, so nothing may block its uninstall (AC-L2)."


def test_purging_warranty_leaves_the_consumer_ledger_standing(db):
    """AC-L2 - the uninstall test that decided fork 7.

    Policies, terms, kinds and assessments go; the ledger and the consumer list do
    not. This is the whole justification for the module split, so it is asserted on
    real rows through the real purge dispatcher rather than by reading a handler.
    """
    from app.models.warranty import WarrantyPolicy, WarrantyProductKind
    from app.services.module_purge_service import purge_module_data

    kind = _kind(db)
    policy = WarrantyPolicy(
        id=str(uuid.uuid4()), version=unique_code("v")[:32], effective_from=date(2000, 1, 1)
    )
    db.add(policy)

    dealer = _customer(db)
    profile = _profile(db)
    purchase = _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=dealer.id,
        dealer_document_number="INV-001",
        consumer_profile_id=profile.id,
        lines=({"kind_id": kind.id, "claimed_text": "SRTWC8366"},),
    )
    db.flush()
    purchase_id, profile_id = purchase.id, profile.id

    purge_module_data(db, WARRANTY_MODULE_KEY)

    profile_cls, purchase_cls, line_cls = (
        _model("ConsumerProfile"),
        _model("ConsumerPurchase"),
        _model("ConsumerPurchaseLine"),
    )
    assert db.query(profile_cls).filter(profile_cls.id == profile_id).first() is not None, (
        "Purging warranty deleted a consumer profile. Fork 7 exists to stop exactly "
        "this: the consumer list is the strategic asset and it outlives the engine."
    )
    assert db.query(purchase_cls).filter(purchase_cls.id == purchase_id).first() is not None, (
        "Purging warranty deleted a purchase. A lifetime ceramic claim years later "
        "needs the receipt, whether or not the engine is installed today."
    )
    assert (
        db.query(line_cls).filter(line_cls.purchase_id == purchase_id).count() == 1
    ), "Purging warranty deleted the purchase lines."
    assert (
        db.query(WarrantyProductKind).filter(WarrantyProductKind.id == kind.id).first() is None
    ), "Purging warranty must actually remove the warranty tables."


def test_the_value_permission_is_gated_on_the_consumers_module():
    """AC-L24 + AC-L1. A slug whose prefix maps to no module is never module-gated.

    ``module_for_permission`` returns None for an unmapped prefix, which means the
    permission stays live for a tenant that never installed the module.
    """
    from app.rbac.permission_registry import PERMISSION_REGISTRY
    from app.modules.runtime.permission_module_map import module_for_permission

    slugs = {entry["slug"] for entry in PERMISSION_REGISTRY}
    assert VALUE_PERMISSION in slugs, (
        f"{VALUE_PERMISSION} is not in PERMISSION_REGISTRY, so it can never be "
        "granted, and code that checks it denies everybody forever (AC-L24)."
    )
    assert module_for_permission(VALUE_PERMISSION) == CONSUMERS_MODULE_KEY, (
        "The `consumers` prefix is unmapped in permission_module_map, so the "
        "permission survives uninstalling the module."
    )


# =============================================================================
# The profile - AC-L4, AC-L29
# =============================================================================


def test_the_three_ledger_tables_exist_with_the_names_the_plan_declares():
    """AC-L4, AC-L11. Names matter: ``warranty_registrations`` is renamed.

    "Warranty Registration" survives only as the glossary term for the ACT, which
    is now ``consumer_purchases.registered_at``. A table by the old name would
    re-create the person-shaped model fork 2 rejected.
    """
    module = _models()
    tables = {
        getattr(module, name).__tablename__
        for name in ("ConsumerProfile", "ConsumerPurchase", "ConsumerPurchaseLine")
        if getattr(module, name, None) is not None
    }
    assert tables == {
        "consumer_profiles",
        "consumer_purchases",
        "consumer_purchase_lines",
    }, f"Found {sorted(tables)}."

    from app.database import Base

    assert "warranty_registrations" not in Base.metadata.tables, (
        "`warranty_registrations` is renamed `consumer_purchases` (fork 7). Both "
        "existing means two answers to 'when was this registered'."
    )


def test_a_profile_is_one_to_one_with_a_respond_contact():
    """AC-L4. Identity stays on ``respond_contacts``; the profile is a satellite.

    Nullable, because fork 1's majority case is a staff-typed phone that never
    authenticated and therefore has no contact row of its own yet.
    """
    column = _column(_model("ConsumerProfile"), "respond_contact_id")
    assert column.unique or any(
        set(c.columns.keys()) == {"respond_contact_id"}
        for c in _model("ConsumerProfile").__table__.constraints
        if hasattr(c, "columns")
    ), (
        "respond_contact_id must be UNIQUE - AC-L4 says 1:1. Two profiles on one "
        "contact splits a person's history in half and nothing detects it."
    )
    assert column.nullable, (
        "A provisional profile created from a staff-typed phone may have no contact "
        "row yet (AC-L5). NOT NULL here makes the majority case unwritable."
    )
    assert {fk.target_fullname for fk in column.foreign_keys} == {"respond_contacts.id"}


def test_the_respond_contact_link_is_text_because_respond_contacts_id_is_text():
    """The plan's DDL is WRONG and this is the test that says so.

    ``consumer_profiles.respond_contact_id uuid REFERENCES respond_contacts(id)``
    cannot be created: ``respond_contacts.id`` is ``Text``. Postgres refuses the
    foreign key outright, and the natural instinct - "every other id here is a
    uuid" - is what produces the error. S1 hit this exact wall with
    ``respond_contacts.user_id`` (users.id is TEXT) and recorded it; the S2b DDL
    walked back into it.
    """
    assert isinstance(RespondContact.__table__.c.id.type, (Text, String)), (
        "This test's premise changed: respond_contacts.id is no longer text."
    )
    column = _column(_model("ConsumerProfile"), "respond_contact_id")
    assert not isinstance(column.type, PG_UUID), (
        "consumer_profiles.respond_contact_id is declared uuid, matching the plan's "
        "DDL. respond_contacts.id is TEXT, so this foreign key cannot be created. "
        "Use Text/String - see app.models.access.RespondContact and the S1 note on "
        "respond_contacts.user_id."
    )
    assert isinstance(column.type, (Text, String))


def test_a_profile_carries_its_own_normalised_phone():
    """AC-L8 needs a column to be unique on, and the contact row is not it.

    ``respond_contacts.phone_number`` is unique on the RAW string, so
    ``0166372304`` and ``+60166372304`` already coexist there as two rows. A
    profile keyed only 1:1 on the contact inherits that split, and the "one
    profile per person" property AC-L8 asks for is unreachable. So the ledger
    stores the E.164 form itself and dedupes on it.
    """
    column = _column(_model("ConsumerProfile"), "phone_e164")
    assert isinstance(column.type, (Text, String))
    table = _model("ConsumerProfile").__table__
    unique_single = {
        tuple(c.columns.keys())
        for c in list(table.constraints) + list(table.indexes)
        if getattr(c, "unique", False)
    }
    assert ("phone_e164",) in unique_single or column.unique, (
        "phone_e164 must be uniquely indexed. Dedupe 'at write time' enforced only "
        "in Python loses the race the moment two intake paths run at once, and the "
        "duplicate is silent."
    )


def test_a_profile_carries_the_consent_fields_and_no_marketing_flag():
    """Fork 6. Warranty and service only, and the notice version is recorded.

    ``consent_notice_version`` exists because PDPA 2010 s.7(2) requires the
    collection notice in Bahasa Malaysia AND English, and "which wording did this
    person actually see" is unanswerable without it.
    """
    columns = _columns(_model("ConsumerProfile"))
    for name in ("consent_purpose", "consent_notice_version", "consent_recorded_at"):
        assert name in columns, f"consumer_profiles.{name} is missing (fork 6)."
    assert not columns["consent_purpose"].nullable, (
        "consent_purpose is NOT NULL: a profile whose purpose is unknown is a "
        "profile nobody may lawfully use for anything."
    )
    assert "marketing_consent" not in columns, (
        "Fork 6 removed it. A marketing flag under a warranty-service consent is a "
        "field nobody may act on, and its presence is an invitation to act on it."
    )


def test_addresses_is_jsonb_because_a_consumer_may_own_several_properties():
    """AC-L4. One person, several houses, each with its own purchases."""
    column = _column(_model("ConsumerProfile"), "addresses")
    assert isinstance(column.type, JSONB), (
        "addresses must be JSONB, not text or a single varchar. A consumer with two "
        "properties is the ordinary case, not the exception."
    )


def test_the_ledger_is_company_scoped_and_the_profile_is_audited():
    """AC-L29, extended to the purchase because the AC stops one table short.

    The profile is PDPA-relevant so it is audited and scoped. The PURCHASE is
    scoped too, and the AC does not say so: ``consumer_profile_id`` is nullable
    (fork 2), so an unscoped purchase table is a ledger with rows belonging to no
    company - which is how Mocha's CS ends up reading Sorento's dealer
    sell-through. Lines are NOT separately scoped: they are reachable only through
    the header, and a second copy of the same fact can disagree with the first.
    """
    profile_cls, purchase_cls, line_cls = (
        _model("ConsumerProfile"),
        _model("ConsumerPurchase"),
        _model("ConsumerPurchaseLine"),
    )
    assert issubclass(profile_cls, CompanyScopedMixin), "AC-L29: profiles are scoped."
    assert issubclass(purchase_cls, CompanyScopedMixin), (
        "consumer_purchases must be company-scoped. The profile link is nullable, so "
        "the purchase is the only row carrying the company for a staff-reported sale."
    )
    assert not issubclass(line_cls, CompanyScopedMixin), (
        "Lines are reachable only through the header. Scoping them again is a second "
        "copy of the same fact that can disagree with the first."
    )
    assert getattr(profile_cls, "__audit_track__", False) is True, (
        "AC-L29: consumer_profiles carries audit listeners. Personal data changing "
        "with no record of who changed it is the thing PDPA asks about."
    )


# =============================================================================
# Provisional until verified - AC-L5 to AC-L10
# =============================================================================


def test_a_staff_typed_phone_creates_a_provisional_profile(db):
    """AC-L5. The majority case: nobody authenticated, and that is normal.

    On most complaints the consumer never logs in - staff type their details into a
    message. That population is exactly the one the ledger exists to capture, so it
    must be writable, and it must be labelled.
    """
    ensure = _svc(
        "ensure_profile",
        "(db, *, phone, full_name=None, respond_contact_id=None, provisional=True)",
    )
    profile = ensure(db, phone="016-637 2304", full_name=f"{TEST_PREFIX} Ong Mei Ling")
    db.flush()
    assert profile.is_provisional is True
    assert profile.confirmed_at is None
    assert profile.phone_e164 == PHONE_E164
    assert profile.consent_purpose == CONSENT_PURPOSE, (
        "Even a staff-typed profile records the purpose it was collected for. A NULL "
        "purpose is a row nobody may lawfully use."
    )


@pytest.mark.parametrize(
    "raw,expected,why",
    [
        ("0166372304", PHONE_E164, "national form, the one staff actually type"),
        ("+60166372304", PHONE_E164, "already E.164"),
        ("60 166372304", PHONE_E164, "country code, no plus, embedded space"),
        ("016-637 2304", PHONE_E164, "the form printed on a business card"),
        ("+6591234567", "+6591234567", "a Singapore number is not rewritten to +60"),
        ("", None, "empty is not a phone"),
        (None, None, "absent is not a phone"),
        ("not a phone", None, "junk normalises to nothing, never to '+60'"),
    ],
)
def test_a_phone_is_normalised_to_e164_before_anything_is_written(raw, expected, why):
    """AC-L8 as a pinned case table.

    The junk row matters most: a normaliser that strips non-digits and prefixes
    ``+60`` turns "not a phone" into ``+60``, and every unparseable intake then
    dedupes onto ONE shared profile holding a dozen strangers' purchases.
    """
    normalise = _fn(
        CONSUMER_SERVICE, "normalize_phone_e164", "(raw, *, default_region='MY')"
    )
    assert normalise(raw) == expected, why


def test_three_spellings_of_one_phone_resolve_to_one_profile(db):
    """AC-L8. The property, not just the function.

    Asserted through ``ensure_profile`` rather than the normaliser alone, because
    normalising correctly and then looking up on the raw string is a real and
    invisible way to fail this.
    """
    ensure = _svc(
        "ensure_profile",
        "(db, *, phone, full_name=None, respond_contact_id=None, provisional=True)",
    )
    ids = set()
    for spelling in PHONE_SPELLINGS:
        ids.add(ensure(db, phone=spelling, full_name=f"{TEST_PREFIX} Ong Mei Ling").id)
        db.flush()
    assert len(ids) == 1, (
        f"{PHONE_SPELLINGS} produced {len(ids)} profiles. One person, one history."
    )

    cls = _model("ConsumerProfile")
    assert db.query(cls).filter(cls.phone_e164 == PHONE_E164).count() == 1


def test_an_otp_login_promotes_the_provisional_profile(db):
    """AC-L6, driven through the REAL OTP path.

    This is the test that decides whether AC-L7 means anything. Promotion is
    specified as "the first time that phone completes an OTP login", and the only
    code in this repo that completes one is ``PortalService.verify_otp``. If S2b
    ships ``promote_profile_on_otp`` and nothing calls it, ``is_provisional`` stays
    true forever, the headline count degrades to "everyone is provisional", and a
    unit test on the promotion function alone would pass throughout.
    """
    from app.services.portal_service import PortalService, _hash_otp, _utcnow

    contact = _contact(db, phone=PHONE_E164)
    profile = _profile(db, phone=PHONE_E164, respond_contact_id=contact.id, is_provisional=True)
    db.add(
        PortalOtpCode(
            id=str(uuid.uuid4()),
            contact_id=contact.id,
            space_id="9911",
            code_hash=_hash_otp("123456"),
            expires_at=_utcnow() + timedelta(minutes=5),
            attempts=0,
        )
    )
    db.flush()

    PortalService(db).verify_otp(contact.id, "9911", "123456")
    db.refresh(profile)

    assert profile.is_provisional is False, (
        "A completed OTP login did not promote the profile. Nothing in "
        "portal_service calls the promotion, so is_provisional is true forever and "
        "AC-L7's honest count silently becomes 'everyone is provisional'."
    )
    assert profile.confirmed_at is not None, "Promotion must record when it happened."


def test_a_conflicting_name_goes_to_a_review_queue_and_never_auto_merges(db):
    """AC-L9. `Miss Ong daughter` arriving on a phone holding `Ong Mei Ling`.

    A household shares a number, so a name change on a known phone is genuinely
    ambiguous: same person spelt differently, or a second person on one handset. An
    auto-merge picks one silently and the purchase history becomes a fiction.
    """
    ensure = _svc(
        "ensure_profile",
        "(db, *, phone, full_name=None, respond_contact_id=None, provisional=True)",
    )
    first = ensure(db, phone=PHONE_E164, full_name=f"{TEST_PREFIX} Ong Mei Ling")
    db.flush()
    original_name = first.full_name

    second = ensure(db, phone=PHONE_E164, full_name=f"{TEST_PREFIX} Miss Ong daughter")
    db.flush()

    assert second.id == first.id, "One phone, one profile - the conflict is on the NAME."
    db.refresh(first)
    assert first.full_name == original_name, (
        "The incoming name overwrote the stored one. AC-L9 forbids resolving this "
        "automatically in either direction."
    )

    review_cls = _model("ConsumerProfileReview")
    rows = db.query(review_cls).filter(review_cls.profile_id == first.id).all()
    assert len(rows) == 1, (
        f"Expected exactly one review-queue row for the name conflict, found "
        f"{len(rows)}. Without it the conflict is discarded and nobody ever decides."
    )
    assert f"{TEST_PREFIX} Miss Ong daughter" in (rows[0].incoming_name or ""), (
        "The review row must carry the name that arrived, or the human deciding it "
        "has nothing to decide between."
    )
    assert rows[0].resolved_at is None


def test_provisional_profiles_are_excluded_from_the_headline_count(db):
    """AC-L7. "We have N consumers" stays honest.

    Scoped to the two rows this test creates: the local database is a copy of
    production, and a count over the whole table would be meaningless.
    """
    count = _fn(
        CONSUMER_SERVICE,
        "count_consumers",
        "(db, *, include_provisional=False, profile_ids=None)",
    )
    confirmed = _profile(
        db, phone="+60111111111", is_provisional=False, confirmed_at=datetime.utcnow()
    )
    provisional = _profile(db, phone="+60222222222", is_provisional=True)
    db.flush()
    scope = [confirmed.id, provisional.id]

    assert count(db, profile_ids=scope) == 1, (
        "The headline count includes provisional profiles. Staff typing a phone must "
        "not inflate 'we have N consumers'."
    )
    assert count(db, include_provisional=True, profile_ids=scope) == 2


def test_merging_moves_the_purchases_to_the_surviving_profile(db):
    """AC-L10. Merge is in scope; split is not.

    The losing row is RETAINED with ``merged_into_id`` set rather than deleted. The
    AC is silent, and deletion makes "where did this consumer go" unanswerable -
    which is the question somebody asks the day after a merge went wrong.
    """
    merge = _fn(
        CONSUMER_SERVICE, "merge_profiles", "(db, *, surviving_id, losing_id, actor_user_id=None)"
    )
    dealer = _customer(db)
    kind = _kind(db)
    surviving = _profile(db, phone="+60333333333")
    losing = _profile(db, phone="+60444444444")
    purchase = _record_purchase(
        db,
        purchase_date=date(2025, 1, 5),
        customer_id=dealer.id,
        dealer_document_number="INV-777",
        consumer_profile_id=losing.id,
        lines=({"kind_id": kind.id, "claimed_text": "SRTWC8366"},),
    )
    db.flush()

    merge(db, surviving_id=surviving.id, losing_id=losing.id)
    db.flush()
    db.refresh(purchase)
    db.refresh(losing)

    assert purchase.consumer_profile_id == surviving.id, (
        "The purchase did not follow the surviving profile (AC-L10)."
    )
    assert losing.merged_into_id == surviving.id, (
        "The losing profile must record where it went. Deleting it makes an "
        "erroneous merge undiagnosable, and split is out of scope so there is no "
        "second chance."
    )


def test_a_merged_profile_is_excluded_from_the_headline_count(db):
    """AC-L7 plus AC-L10. Retaining the losing row must not double-count a person."""
    count = _fn(
        CONSUMER_SERVICE,
        "count_consumers",
        "(db, *, include_provisional=False, profile_ids=None)",
    )
    merge = _fn(
        CONSUMER_SERVICE, "merge_profiles", "(db, *, surviving_id, losing_id, actor_user_id=None)"
    )
    surviving = _profile(db, phone="+60555555555", is_provisional=False)
    losing = _profile(db, phone="+60666666666", is_provisional=False)
    db.flush()
    scope = [surviving.id, losing.id]
    assert count(db, profile_ids=scope) == 2

    merge(db, surviving_id=surviving.id, losing_id=losing.id)
    db.flush()
    assert count(db, profile_ids=scope) == 1, (
        "A merged-away profile still counts as a consumer. One person, one count."
    )


# =============================================================================
# Consent and erasure - fork 6
# =============================================================================


def test_consent_purpose_is_warranty_service_only(db):
    """Fork 6, as a closed vocabulary rather than a free-text column.

    The one-way door is deliberate: service-only consent means these profiles can
    never be broadcast to without fresh consent from each person. A second value
    appearing quietly in one intake path is how that door gets propped open.
    """
    module = _module(CONSUMER_SERVICE, "The consent vocabulary lives beside the writer.")
    purposes = getattr(module, "CONSENT_PURPOSES", None)
    assert purposes is not None, (
        "consumer_service.CONSENT_PURPOSES must be declared. A free-text purpose "
        "column is a lawful-basis field with no lawful basis."
    )
    assert frozenset(purposes) == frozenset({CONSENT_PURPOSE}), (
        f"Fork 6 permits exactly one purpose. Found {sorted(purposes)}. Adding "
        "marketing needs fresh consent per person, not a new enum member."
    )


def test_anonymising_strips_the_person_and_keeps_the_purchase(db):
    """Fork 6's erasure ruling, and the half that is easy to get wrong.

    A lifetime ceramic warranty may be claimed years later, so the commercial and
    warranty record survives while the person does not. Deleting the profile row
    would cascade or orphan the purchase; blanking the name alone would leave the
    person perfectly reachable.
    """
    anonymise = _fn(CONSUMER_SERVICE, "anonymise_profile", "(db, profile_id, *, actor_user_id=None)")
    dealer = _customer(db)
    kind = _kind(db)
    contact = _contact(db, phone="+60777777777")
    profile = _profile(
        db,
        phone="+60777777777",
        respond_contact_id=contact.id,
        full_name=f"{TEST_PREFIX} Ong Mei Ling",
        email="ong@example.invalid",
        addresses=[{"line1": "12 Jalan Test"}],
    )
    purchase = _record_purchase(
        db,
        purchase_date=date(2020, 3, 1),
        customer_id=dealer.id,
        dealer_document_number="INV-888",
        consumer_profile_id=profile.id,
        lines=({"kind_id": kind.id, "claimed_text": "SRTWC8366"},),
    )
    db.flush()
    purchase_id = purchase.id

    anonymise(db, profile.id)
    db.flush()
    db.refresh(profile)

    assert profile.anonymised_at is not None
    assert not profile.full_name, "The name survived anonymisation."
    assert not profile.email, "The email survived anonymisation."
    assert not profile.addresses, "The addresses survived anonymisation."
    assert not profile.phone_e164, (
        "The phone survived anonymisation, so the person is still reachable and "
        "still dedupes - which means the NEXT intake re-attaches them by phone and "
        "quietly re-identifies the row that was erased."
    )

    purchase_cls = _model("ConsumerPurchase")
    kept = db.query(purchase_cls).filter(purchase_cls.id == purchase_id).first()
    assert kept is not None, (
        "Erasure deleted the purchase. Fork 6 retains it: a lifetime ceramic claim "
        "years later needs the date of sale."
    )
    assert kept.purchase_date == date(2020, 3, 1), "The warranty-bearing date must survive."


def test_an_anonymised_profile_is_unreachable_through_its_contact_link(db):
    """Fork 6, the part the plan does not spell out.

    ``respond_contact_id`` is the identity link. Leaving it set after erasure means
    one join re-identifies the person from the phone number on ``respond_contacts``,
    so the erasure is cosmetic.

    What this test deliberately does NOT assert: that ``respond_contacts`` itself is
    scrubbed. That row is shared with complaints, chat history, SLA tracking and the
    portal, and deleting it is a far larger decision than S2b owns. Severing the
    ledger's link is what S2b can honestly promise, and the residual reachability
    through other modules is a recorded gap, not a solved problem.
    """
    anonymise = _fn(CONSUMER_SERVICE, "anonymise_profile", "(db, profile_id, *, actor_user_id=None)")
    contact = _contact(db, phone="+60888888888", name=f"{TEST_PREFIX} Ong Mei Ling")
    profile = _profile(db, phone="+60888888888", respond_contact_id=contact.id)
    db.flush()

    anonymise(db, profile.id)
    db.flush()
    db.refresh(profile)

    assert profile.respond_contact_id is None, (
        "The contact link survived erasure. One join from consumer_profiles to "
        "respond_contacts recovers the name and the phone, so nothing was erased."
    )


# =============================================================================
# The purchase: header and lines - AC-L11, AC-L12, AC-L14, AC-L15
# =============================================================================


def test_a_purchase_header_carries_the_dealer_the_document_and_the_receipt():
    """AC-L14. The receipt is RETAINED, never discarded after extraction."""
    columns = _columns(_model("ConsumerPurchase"))
    for name in (
        "customer_id",
        "dealer_document_number",
        "dealer_document_number_norm",
        "purchase_date",
        "total_value",
        "currency",
        "proof_attachment_id",
        "registered_at",
        "registration_source",
        "dedupe_pending",
        "policy_id",
        "purchase_number",
    ):
        assert name in columns, f"consumer_purchases.{name} is missing (AC-L14)."

    assert not columns["purchase_date"].nullable, (
        "purchase_date is the only thing cover is computed from. A nullable one "
        "makes every verdict on that row `unknown` and nothing says why."
    )
    assert {fk.target_fullname for fk in columns["proof_attachment_id"].foreign_keys} == {
        "attachments.id"
    }, "The receipt is an attachment row, retained (AC-L14)."
    assert {fk.target_fullname for fk in columns["customer_id"].foreign_keys} == {
        "customers.id"
    }


def test_consumer_profile_id_is_nullable_because_cover_attaches_to_the_product():
    """AC-L12 / fork 2. The consumer link is ADVISORY.

    Policy clause 6 attaches cover to the product and its purchase date, not to a
    person. A NOT NULL here would force every staff-reported purchase to invent a
    consumer, and would break the new occupant of a house that changed hands.
    """
    column = _column(_model("ConsumerPurchase"), "consumer_profile_id")
    assert column.nullable, (
        "consumer_profile_id must be nullable (fork 2). Cover resolves from the "
        "purchase alone."
    )


def test_one_receipt_writes_one_header_and_several_lines(db):
    """AC-L11. Sean's `SRTWC8366 x 1 / SRTWC8152 x 1` under one document.

    The earlier flat shape forced dedupe per line, where a misread quantity or an
    unresolved variant produces a near-duplicate nobody can adjudicate.
    """
    dealer = _customer(db)
    wc, basin = _kind(db, "Water Closet"), _kind(db, "Wash Basin")
    purchase = _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=dealer.id,
        dealer_document_number="INV-1001",
        total_value="1899.00",
        currency="MYR",
        lines=(
            {"kind_id": wc.id, "claimed_text": "SRTWC8366", "quantity": 1},
            {"kind_id": basin.id, "claimed_text": "SRTWC8152", "quantity": 1},
        ),
    )
    db.flush()

    line_cls = _model("ConsumerPurchaseLine")
    lines = db.query(line_cls).filter(line_cls.purchase_id == purchase.id).all()
    assert len(lines) == 2, f"One receipt, two products, one header. Found {len(lines)} lines."
    assert (
        _headers_for(
            db,
            customer_id=dealer.id,
            document_norm=purchase.dealer_document_number_norm,
            purchase_date=date(2025, 10, 16),
        )
        == 1
    )


def test_a_line_carries_a_kind_a_nullable_product_and_the_claimed_text():
    """AC-L15 and AC-L36. ``product_id`` is nullable; the Kind is SNAPSHOTTED.

    ``SRTWC8152`` matches three real variants and resolves to none of them, so cover
    must be decidable from the Kind alone (AC-C17). A NOT NULL product_id would make
    the ordinary receipt unwritable.

    The Kind is carried twice on purpose (AC-L36). ``kind_code`` is NOT NULL and is what
    keeps the line assessable and readable forever; ``kind_id`` is the live link and is
    NULLABLE with ON DELETE SET NULL. This version first required ``kind_id`` NOT NULL,
    which contradicted ``test_purging_warranty_leaves_the_consumer_ledger_standing``:
    no ON DELETE action preserves a child row whose column is NOT NULL, so purging
    warranty could not leave the ledger standing, which is the entire reason fork 7 put
    the ledger outside the warranty module. Deferring the constraint made both tests
    green while a real purge still failed at COMMIT - a green test masking a production
    failure. The ledger is a historical record of what was bought and must not lose its
    meaning because a module was uninstalled.
    """
    columns = _columns(_model("ConsumerPurchaseLine"))
    for name in (
        "purchase_id", "product_id", "kind_id", "kind_code", "claimed_text", "quantity", "line_value"
    ):
        assert name in columns, f"consumer_purchase_lines.{name} is missing (AC-L15)."
    assert columns["product_id"].nullable, "The variant is routinely unresolved (AC-C17)."
    assert not columns["kind_code"].nullable, (
        "kind_code is what cover resolves from once the Kind row may be gone. A line "
        "with no Kind at all cannot be assessed and would silently produce no verdict."
    )
    assert columns["kind_id"].nullable, (
        "kind_id must go NULL when a warranty purge removes the Kind (AC-L2, AC-L36); "
        "kind_code is what survives."
    )
    assert not columns["purchase_id"].nullable
    assert {fk.target_fullname for fk in columns["kind_id"].foreign_keys} == {
        "warranty_product_kinds.id"
    }


def test_a_purchase_number_is_issued_and_carries_its_year(db):
    """The plan's ``CP{year}-`` prefix. Human-quotable, and unique."""
    dealer = _customer(db)
    kind = _kind(db)
    purchase = _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=dealer.id,
        dealer_document_number="INV-2002",
        lines=({"kind_id": kind.id},),
    )
    db.flush()
    assert purchase.purchase_number, "Every purchase gets a quotable number."
    assert purchase.purchase_number.startswith("CP2025"), (
        f"Expected a CP{{year}}- number for a 2025 purchase, got "
        f"{purchase.purchase_number!r}. The year is the PURCHASE's, not today's: a "
        "2015 receipt entered in 2026 numbered CP2026 reads as a 2026 sale on every "
        "report that groups by the number."
    )
    assert _column(_model("ConsumerPurchase"), "purchase_number").unique or any(
        tuple(c.columns.keys()) == ("purchase_number",)
        for c in _model("ConsumerPurchase").__table__.constraints
        if hasattr(c, "columns")
    )


def test_a_purchase_with_no_identity_does_not_silently_acquire_one_later(db):
    """The AC is silent and this pins the safe answer.

    Fork 2 lets a purchase carry no profile. Fork 1 dedupes profiles on phone. Put
    together, the tempting behaviour is "when a profile appears for that phone,
    back-link the orphan purchases" - and that is wrong: a household shares a
    number, so it attaches a stranger's receipt to whoever authenticates first, and
    it does so invisibly, years later, at the moment they log in.

    So: no implicit back-link. Attaching an orphan purchase to a profile is a
    deliberate act by CS. Recorded as a gap rather than solved, because nothing in
    Group L asks for the CS surface that would do it.
    """
    ensure = _svc(
        "ensure_profile",
        "(db, *, phone, full_name=None, respond_contact_id=None, provisional=True)",
    )
    dealer = _customer(db)
    kind = _kind(db)
    purchase = _record_purchase(
        db,
        purchase_date=date(2024, 2, 2),
        customer_id=dealer.id,
        dealer_document_number="INV-3003",
        lines=({"kind_id": kind.id},),
    )
    db.flush()
    assert purchase.consumer_profile_id is None

    ensure(db, phone=PHONE_E164, full_name=f"{TEST_PREFIX} Ong Mei Ling")
    db.flush()
    db.refresh(purchase)
    assert purchase.consumer_profile_id is None, (
        "An orphan purchase acquired a profile the moment one appeared. A shared "
        "household number makes that a stranger's receipt on somebody's record."
    )


# =============================================================================
# Dedupe: link, never reject - AC-L17 to AC-L21
# =============================================================================


def test_the_dedupe_index_is_partial_over_the_three_columns():
    """AC-L17. Partial, so an incomplete key still writes.

    A plain unique index over three nullable columns is not the same thing and is
    not what was decided: in Postgres NULLs do not collide, so a plain index would
    look partial while still constraining nothing, and the first NOT NULL added to
    tidy it up would start REJECTING the incomplete rows AC-L20 requires.
    """
    table = _model("ConsumerPurchase").__table__
    candidates = [
        ix
        for ix in table.indexes
        if ix.unique
        and tuple(c.name for c in ix.columns)
        == ("customer_id", "dealer_document_number_norm", "purchase_date")
    ]
    assert candidates, (
        "No unique index on (customer_id, dealer_document_number_norm, "
        f"purchase_date). Found: "
        f"{[(ix.name, tuple(c.name for c in ix.columns), ix.unique) for ix in table.indexes]}"
    )
    index = candidates[0]
    where = index.dialect_options["postgresql"].get("where")
    assert where is not None, (
        "The dedupe index must be PARTIAL (AC-L17). Without a WHERE clause an "
        "incomplete key relies on Postgres NULL semantics for the same effect, and "
        "the moment anyone adds NOT NULL the incomplete rows start being rejected."
    )
    columns = _columns(_model("ConsumerPurchase"))
    assert columns["customer_id"].nullable and columns["dealer_document_number_norm"].nullable, (
        "Two thirds of the key must stay nullable: the dealer is routinely "
        "unresolved and OCR routinely finds no document number (AC-L20)."
    )


@pytest.mark.parametrize(
    "spelling", ["INV-001", "inv 001", "INV001", "  INV-001  ", "Inv/001"]
)
def test_the_document_number_normaliser_collides_the_spellings_of_one_document(spelling):
    """The dedupe key is only as good as this function.

    Case, spacing and separators are exactly what varies between an OCR read, a
    staff retype and the dealer's own printing, and none of them mean a different
    document.

    The risk this creates is real and is accepted rather than hidden: under "link,
    never reject" a FALSE collision does not refuse anything, it attaches the second
    complaint to the FIRST purchase - and therefore to the first purchase's DATE. So
    an over-eager normaliser mis-dates a warranty rather than annoying somebody. The
    rule is deliberately limited to case, whitespace and separators; it must not
    strip leading zeros or a year segment, which genuinely distinguish documents.
    """
    normalise = _fn(CONSUMER_SERVICE, "normalize_document_number", "(raw)")
    assert normalise(spelling) == "INV001", (
        f"{spelling!r} must normalise with the other spellings of the same document."
    )
    assert normalise("INV-0001") != normalise("INV-001"), (
        "Leading zeros are part of a document number, not noise."
    )
    assert normalise(None) is None and normalise("") is None, (
        "An absent number normalises to NULL, never to the empty string: '' would "
        "collide every unnumbered receipt from one dealer on one day into one row."
    )


def test_a_second_receipt_with_the_same_key_links_to_the_existing_header(db):
    """AC-L18. A second complaint months later citing a receipt already held."""
    dealer = _customer(db)
    kind = _kind(db)
    first = _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=dealer.id,
        dealer_document_number="INV-001",
        lines=({"kind_id": kind.id, "claimed_text": "SRTWC8366"},),
    )
    db.flush()
    second = _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=dealer.id,
        dealer_document_number="inv 001",
        lines=({"kind_id": kind.id, "claimed_text": "SRTWC8366"},),
    )
    db.flush()

    assert second.id == first.id, (
        "The second citation created a second header. The ledger now double-counts "
        "one purchase and value reporting inflates."
    )
    assert (
        _headers_for(
            db,
            customer_id=dealer.id,
            document_norm=first.dealer_document_number_norm,
            purchase_date=date(2025, 10, 16),
        )
        == 1
    )


def test_a_key_collision_is_never_rejected(db):
    """AC-L19. The packing-list precedent does NOT apply here.

    Rejecting on a triple match was right for a staff import. Here the submitter is
    a consumer with a broken toilet, and refusing their complaint because we think
    we have seen their receipt is not a thing this system may do.
    """
    dealer = _customer(db)
    kind = _kind(db)
    _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=dealer.id,
        dealer_document_number="INV-001",
        lines=({"kind_id": kind.id},),
    )
    db.flush()

    # Must not raise, must not return None.
    again = _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=dealer.id,
        dealer_document_number="INV-001",
        lines=({"kind_id": kind.id},),
    )
    db.flush()
    assert again is not None, "A collision returns the existing purchase, never nothing."


def test_two_receipts_sharing_a_dealer_and_a_date_but_not_a_number_both_write(db):
    """The consequence of a PARTIAL index, pinned so nobody "fixes" it.

    Same dealer, same day, one receipt with a document number and one without: they
    are NOT duplicates under the index and both rows are written. That is correct -
    a consumer really can buy twice from one shop in one day, and the alternative
    silently swallows the second purchase - but it means near-duplicates exist by
    design and the ``dedupe_pending`` review list is the only thing that catches
    them.
    """
    dealer = _customer(db)
    kind = _kind(db)
    numbered = _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=dealer.id,
        dealer_document_number="INV-001",
        lines=({"kind_id": kind.id},),
    )
    unnumbered = _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=dealer.id,
        dealer_document_number=None,
        lines=({"kind_id": kind.id},),
    )
    db.flush()

    assert numbered.id != unnumbered.id, (
        "The unnumbered receipt was absorbed into the numbered one. Two different "
        "purchases became one, and the second product's cover now runs from the "
        "wrong header."
    )
    assert unnumbered.dedupe_pending is True, (
        "An incomplete key must be flagged for the CS review list (AC-L20), or "
        "near-duplicates accumulate with nothing pointing at them."
    )


def test_an_incomplete_key_writes_and_flags_dedupe_pending(db):
    """AC-L20. Never blocks (AC-C14). The dealer is routinely unresolved."""
    kind = _kind(db)
    purchase = _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=None,
        dealer_document_number=None,
        lines=({"kind_id": kind.id},),
    )
    db.flush()
    assert purchase.id, "An unresolvable dealer must not stop the intake."
    assert purchase.dedupe_pending is True

    review = _fn(CONSUMER_SERVICE, "list_dedupe_pending", "(db, *, purchase_ids=None)")
    pending = review(db, purchase_ids=[purchase.id])
    assert [p.id for p in pending] == [purchase.id], (
        "The flagged row must be reachable as a list, or the flag is a column "
        "nobody ever reads."
    )


def test_a_complete_key_is_not_flagged_for_review(db):
    """The other half of AC-L20: flagging everything is the same as flagging nothing."""
    dealer = _customer(db)
    kind = _kind(db)
    purchase = _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=dealer.id,
        dealer_document_number="INV-4004",
        lines=({"kind_id": kind.id},),
    )
    db.flush()
    assert purchase.dedupe_pending is False


def test_the_same_file_uploaded_twice_is_detectable_by_its_hash(db):
    """AC-L21. Free, and independent of the key.

    The two receipts here carry DIFFERENT document numbers - the case the key
    misses and the hash catches: an OCR misread of the number on a re-upload of the
    identical photograph.
    """
    duplicates = _fn(
        CONSUMER_SERVICE, "find_purchases_by_file_hash", "(db, file_hash)"
    )
    dealer = _customer(db)
    kind = _kind(db)
    digest = (uuid.uuid4().hex + uuid.uuid4().hex)[:64]  # sha256-shaped, per-test unique
    first_file = _attachment(db, file_hash=digest)
    second_file = _attachment(db, file_hash=digest)

    a = _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=dealer.id,
        dealer_document_number="INV-005",
        proof_attachment_id=first_file.id,
        lines=({"kind_id": kind.id},),
    )
    b = _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=dealer.id,
        dealer_document_number="lNV-OO5",  # the same document, misread by OCR
        proof_attachment_id=second_file.id,
        lines=({"kind_id": kind.id},),
    )
    db.flush()

    found = {p.id for p in duplicates(db, digest)}
    assert {a.id, b.id} <= found, (
        "The identical file behind two headers is not discoverable by hash, so the "
        "one case the dedupe key structurally cannot catch has nothing catching it."
    )


# =============================================================================
# Value: as printed, gated - AC-L22, AC-L24, AC-L25
# =============================================================================


def test_only_the_header_carries_value_and_the_line_stays_null(db):
    """AC-L22 / fork 4. As printed, nothing more.

    Normalising a photographed third-party receipt produces false precision that
    will be wrong in a way nobody can explain, so a receipt total is never spread
    across the lines that share it.
    """
    dealer = _customer(db)
    wc, basin = _kind(db, "Water Closet"), _kind(db, "Wash Basin")
    purchase = _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=dealer.id,
        dealer_document_number="INV-6006",
        total_value="1899.00",
        currency="MYR",
        lines=(
            {"kind_id": wc.id, "claimed_text": "SRTWC8366", "quantity": 1},
            {"kind_id": basin.id, "claimed_text": "SRTWC8152", "quantity": 1},
        ),
    )
    db.flush()

    line_cls = _model("ConsumerPurchaseLine")
    values = [
        line.line_value
        for line in db.query(line_cls).filter(line_cls.purchase_id == purchase.id).all()
    ]
    assert values == [None, None], (
        f"A header total was allocated across the lines: {values}. Fork 4 forbids "
        "per-unit derivation - the receipt does not say what each item cost, and a "
        "number we invented is indistinguishable on screen from one we read."
    )
    assert str(purchase.total_value) == "1899.00"


def test_nothing_in_the_ledger_normalises_tax_or_discount():
    """Fork 4, as a source guard on the module that writes value.

    A `sst` or `discount` branch in the writer is the false-precision decision being
    re-taken quietly, and it would be invisible in behaviour tests because the
    numbers would still look plausible.
    """
    module = _module(CONSUMER_SERVICE, "The value writer lives here.")
    source = pathlib.Path(inspect.getsourcefile(module)).read_text(encoding="utf-8").lower()
    for word in ("sst", "gst", "discount_allocat", "unit_price"):
        assert word not in source, (
            f"{CONSUMER_SERVICE} mentions {word!r}. Fork 4: capture the printed "
            "total and nothing more."
        )


def test_the_value_permission_is_granted_to_nobody_by_the_seed(db):
    """AC-L24. Off by default is a property of the SEED, not of the slug.

    ``sync_permissions`` creates permissions and grants none, so the assertion is
    that the seed does not quietly attach this one to a role.
    """
    from app.models.user import UserPermission, UserRolePermission
    from app.rbac.permission_registry import sync_permissions

    sync_permissions(db)
    db.flush()
    row = db.query(UserPermission).filter(UserPermission.slug == VALUE_PERMISSION).first()
    assert row is not None, f"{VALUE_PERMISSION} was not seeded."
    grants = (
        db.query(UserRolePermission).filter(UserRolePermission.permission_id == row.id).count()
    )
    assert grants == 0, (
        f"{VALUE_PERMISSION} is pre-granted to {grants} role(s). AC-L24 says off by "
        "default: retail prices must not appear on every CS screen."
    )


def test_value_is_omitted_not_nulled_for_a_reader_without_the_permission(db):
    """AC-L24 as behaviour, and the distinction that matters.

    ``None`` means "the receipt showed no total". Absent means "you may not see it".
    Serialising the first when you mean the second tells a CS agent the dealer sold
    it for nothing.
    """
    serialize = _fn(
        CONSUMER_SERVICE, "serialize_purchase", "(purchase, *, can_view_value)"
    )
    dealer = _customer(db)
    kind = _kind(db)
    purchase = _record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        customer_id=dealer.id,
        dealer_document_number="INV-7007",
        total_value="1899.00",
        currency="MYR",
        lines=({"kind_id": kind.id},),
    )
    db.flush()

    permitted = serialize(purchase, can_view_value=True)
    assert "total_value" in permitted and str(permitted["total_value"]) == "1899.00"

    denied = serialize(purchase, can_view_value=False)
    assert "total_value" not in denied, (
        "total_value is present (probably as None) for a reader without "
        f"{VALUE_PERMISSION}. None reads as 'the receipt showed no total', which is "
        "a different fact and a wrong one."
    )
    assert "currency" not in denied, "The currency without the amount leaks nothing useful and still implies a value was held."
    assert denied.get("purchase_number") == purchase.purchase_number, (
        "Only the value is hidden. Hiding the whole purchase makes the ledger "
        "useless to the CS agent who needs the date."
    )


def test_a_value_report_states_its_coverage(db):
    """AC-L25. `value known on N of M purchases`, never a silent under-total.

    Scoped to one test-created dealer: the local database is a copy of production
    and a coverage figure over the whole table would be both meaningless and slow.
    """
    coverage = _fn(CONSUMER_SERVICE, "value_coverage", "(db, *, customer_id=None)")
    dealer = _customer(db)
    kind = _kind(db)
    _record_purchase(
        db,
        purchase_date=date(2025, 1, 1),
        customer_id=dealer.id,
        dealer_document_number="INV-8001",
        total_value="100.00",
        currency="MYR",
        lines=({"kind_id": kind.id},),
    )
    _record_purchase(
        db,
        purchase_date=date(2025, 1, 2),
        customer_id=dealer.id,
        dealer_document_number="INV-8002",
        lines=({"kind_id": kind.id},),
    )
    db.flush()

    report = coverage(db, customer_id=dealer.id)
    assert report["total"] == 2, f"Expected 2 purchases in scope, got {report!r}."
    assert report["known"] == 1, (
        "Coverage must count the purchases whose value is actually known. Reporting "
        "a total without it reads as complete when half the receipts were silent."
    )


# =============================================================================
# Reporting - AC-L28
# =============================================================================


def test_reporting_answers_per_consumer_and_per_dealer(db):
    """AC-L28. The sell-through visibility the dealer channel currently hides.

    Both directions, because they are different questions with different owners:
    "what does this consumer own" is a CS question on a live call, and "which
    consumers has this dealer sold to" is the commercial one fork 5 says Sorento
    intends to be able to answer.
    """
    per_profile = _fn(CONSUMER_SERVICE, "purchases_for_profile", "(db, profile_id)")
    per_dealer = _fn(CONSUMER_SERVICE, "purchases_for_dealer", "(db, customer_id)")

    dealer_a, dealer_b = _customer(db, "dealer-a"), _customer(db, "dealer-b")
    kind = _kind(db)
    profile = _profile(db, phone="+60999999999")
    first = _record_purchase(
        db,
        purchase_date=date(2025, 4, 1),
        customer_id=dealer_a.id,
        dealer_document_number="INV-9001",
        consumer_profile_id=profile.id,
        lines=({"kind_id": kind.id},),
    )
    second = _record_purchase(
        db,
        purchase_date=date(2025, 5, 1),
        customer_id=dealer_b.id,
        dealer_document_number="INV-9002",
        consumer_profile_id=profile.id,
        lines=({"kind_id": kind.id},),
    )
    db.flush()

    assert {p.id for p in per_profile(db, profile.id)} == {first.id, second.id}, (
        "One consumer, two dealers - AC-L28's 'which Dealers, what they own'."
    )
    assert {p.id for p in per_dealer(db, dealer_a.id)} == {first.id}


# =============================================================================
# Migrations - the ADR-0012 failure
# =============================================================================


def test_the_ledger_tables_are_in_a_migration_not_only_on_the_model():
    """``blank_session`` builds from ``Base.metadata``, so a model with no migration
    behind it passes every other test in this file and is absent in production.
    """
    versions = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
    sources = [p.read_text(encoding="utf-8", errors="ignore") for p in versions.glob("*.py")]
    missing = [
        table
        for table in ("consumer_profiles", "consumer_purchases", "consumer_purchase_lines")
        if not any(table in src and "create_table" in src for src in sources)
    ]
    assert not missing, (
        "No alembic revision creates " + ", ".join(missing) + "."
    )
    assert any(
        "consumer_purchases_dedupe" in src or "dealer_document_number_norm" in src
        for src in sources
    ), (
        "The partial dedupe index is not in any migration. create_all builds it from "
        "the model, so the test suite is green and production has no constraint."
    )
