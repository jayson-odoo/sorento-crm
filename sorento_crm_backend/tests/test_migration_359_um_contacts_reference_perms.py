"""Migration 359's GRANTS, exercised rather than assumed.

UAC6a.3 / UAC6a.4 / UAC6c.3 of
`documentation/plans/security/user-management-read-gates-acceptance-criteria.md`.

The point of the acceptance criterion is that registering a slug is not the
deliverable - granting it is. Migration 298's docstring is explicit that a new
permission reaches no existing role automatically, so a slug registered and
never granted turns the route it protects into a permanent 403 for everyone but
admin/superadmin (who bypass `check_user_has_permission` outright and would
therefore hide the defect from exactly the person testing it).

Two grant strategies are under test and they fail in different ways:

* `user_management.contacts.view` uses a HARDCODED role list, so its failure
  mode is a role named in the list that this install does not have. The
  migration must skip it with a log line, not crash - and the local database
  proves that case is real rather than hypothetical, because it carries `admin`
  and no `superadmin` row at all.
* `user_management.reference_data.view` DERIVES its role set in SQL from ten
  consumer slugs, so its failure mode is the derivation being wrong. A role
  holding one consumer slug must get the grant and a role holding none must not:
  that pair is what proves the SELECT, and neither half proves it alone. Two of
  the ten (`user_management.contacts.view`, `user_management.access_agents.view`)
  front in-package screens reading the same catalogs, and contacts.view is granted
  by this very migration - so the derivation has to run after that grant, which
  test_a_role_granted_contacts_view_in_this_run_also_derives_reference_data pins.

Everything runs against a blank Postgres schema (`blank_session`) inside a
transaction that is rolled back, and every role/permission is seeded by this
file. Asserting against the live database would only prove what this developer's
prod-copy happens to hold; CI's database is empty, where `LIMIT 1` off
`user_roles` is `None` and the dependent INSERT dies on a NOT NULL FK. Shape of
the harness (`_load_migration` + `MigrationContext` + `Operations.context`)
copied from tests/test_migration_311_pr_approve_grants.py.

Run: pytest tests/test_migration_359_um_contacts_reference_perms.py -q
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models.user import UserPermission, UserRole, UserRolePermission

from ._pg_fixture import blank_session

CONTACTS_VIEW = "user_management.contacts.view"
REFERENCE_DATA_VIEW = "user_management.reference_data.view"

# The ten consuming screens' view slugs. Copied deliberately rather than
# imported from the migration: if someone edits that list, this test should
# disagree with them and make them say so, not silently follow along.
CONSUMER_SLUGS = [
    "forms.forms.view",
    "marketing.promotions.view",
    "master_data.brands.view",
    "master_data.products.view",
    "resource.attachments.view",
    "resource.attachment_directories.view",
    "resource.attachment_types.view",
    CONTACTS_VIEW,
    "user_management.access_agents.view",
    # Transitive: CertificateDetail mounts AttachmentDetailModal, which reads the
    # access-type catalog unconditionally. Completes that modal's four mount
    # points; the other three are already above.
    "master_data.certificates.view",
]

# The subset of the migration's hardcoded contacts list that this test seeds.
# `superadmin` is deliberately NOT here - see
# test_a_role_named_in_the_list_but_absent_from_the_install_is_skipped.
SEEDED_CONTACTS_ROLES = [
    "admin",
    "director",
    "warehouse_manager",
    "integration_n8n",
]

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "359_um_contacts_reference_perms.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_359", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(db) -> None:
    module = _load_migration()
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        module.upgrade()


# ------------------------------------------------------------------ seeding


def _role(db, slug: str) -> str:
    """A role with the given slug. `name` is UNIQUE on Postgres, so it carries a
    marker suffix - two tests seeding "Admin" would otherwise collide."""
    row = UserRole(
        id=str(uuid.uuid4()),
        slug=slug,
        name=f"ZZT {slug} {uuid.uuid4().hex[:8]}",
        is_trashed=False,
    )
    db.add(row)
    db.flush()
    return row.id


def _permission(db, slug: str) -> str:
    """Seeded through the ORM so the model's defaults fill every NOT NULL column.

    Seeded BEFORE the migration runs on purpose: the migration's own
    `sync_permissions()` would create these slugs, but only after the derivation
    query has already read the grants, so a role's consumer grant has to exist
    first to be derivable. `sync_permissions` skips a slug that already exists,
    so pre-seeding does not double-insert.
    """
    row = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug)
    db.add(row)
    db.flush()
    return row.id


def _grant(db, role_id: str, permission_id: str) -> None:
    db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role_id, permission_id=permission_id))
    db.flush()


def _holds(db, role_id: str, slug: str) -> bool:
    return bool(
        db.execute(
            text(
                "SELECT 1 FROM user_role_permissions urp "
                "JOIN user_permissions p ON p.id = urp.permission_id "
                "WHERE urp.role_id = :r AND p.slug = :slug"
            ),
            {"r": role_id, "slug": slug},
        ).first()
    )


def _grant_count(db, slug: str) -> int:
    return db.execute(
        text(
            "SELECT count(*) FROM user_role_permissions urp "
            "JOIN user_permissions p ON p.id = urp.permission_id "
            "WHERE p.slug = :slug"
        ),
        {"slug": slug},
    ).scalar()


@pytest.fixture()
def seeded():
    """A blank schema holding: four of the migration's named contacts roles (and
    NOT `superadmin`), one role per consumer slug already holding that slug, and
    one bystander role holding a `user_management` slug that is not a consumer.

    The bystander is the control for both halves - it must gain neither grant.
    """
    with blank_session() as db:
        roles = {slug: _role(db, slug) for slug in SEEDED_CONTACTS_ROLES}

        consumers: dict[str, str] = {}
        for consumer_slug in CONSUMER_SLUGS:
            permission_id = _permission(db, consumer_slug)
            role_id = _role(db, f"zzt_consumer_{consumer_slug.replace('.', '_')}")
            _grant(db, role_id, permission_id)
            consumers[consumer_slug] = role_id

        # Holds a real permission, just not a consuming one. Without a grant of
        # its own it would fall out of the derivation JOIN for the trivial
        # reason, which would not test the WHERE clause.
        bystander = _role(db, f"zzt_bystander_{uuid.uuid4().hex[:8]}")
        _grant(db, bystander, _permission(db, "user_management.teams.view"))

        db.flush()
        yield db, {"roles": roles, "consumers": consumers, "bystander": bystander}


# --------------------------------------------------------------- UAC6a.1/6c.1


def test_both_slugs_exist_after_upgrade(seeded):
    db, _ = seeded
    _run_upgrade(db)

    found = {
        row[0]
        for row in db.execute(
            text("SELECT slug FROM user_permissions WHERE slug = ANY(:slugs)"),
            {"slugs": [CONTACTS_VIEW, REFERENCE_DATA_VIEW]},
        )
    }
    assert found == {CONTACTS_VIEW, REFERENCE_DATA_VIEW}


# ------------------------------------------------------------------- UAC6a.3


def test_contacts_view_is_granted_to_every_named_role_present(seeded):
    """Registration without a grant is the failure mode this AC exists for."""
    db, fixtures = seeded
    _run_upgrade(db)

    missing = [s for s in SEEDED_CONTACTS_ROLES if not _holds(db, fixtures["roles"][s], CONTACTS_VIEW)]
    assert not missing, (
        f"{missing} are named in the migration's contacts list but were not granted "
        f"{CONTACTS_VIEW} - the routes it gates are now a permanent 403 for them"
    )


# ------------------------------------------------------------------- UAC6a.4


def test_a_role_named_in_the_list_but_absent_from_the_install_is_skipped(seeded):
    """`superadmin` is in the migration's hardcoded list and is NOT a row in this
    database - the local prod-copy carries `admin` only. That is not a
    hypothetical edge: it is what this install actually looks like, so the skip
    path is the normal path here. It must log and continue, never crash, and the
    roles that DO exist must still be granted in the same run."""
    db, fixtures = seeded
    assert (
        db.execute(text("SELECT 1 FROM user_roles WHERE slug = 'superadmin'")).first()
        is None
    ), "the fixture must not seed superadmin - the absent-role path is the point"

    _run_upgrade(db)  # must not raise

    assert _holds(db, fixtures["roles"]["admin"], CONTACTS_VIEW), (
        "an absent role aborted the grant loop before the present ones were reached"
    )


def test_the_migration_chain_still_reports_exactly_one_head():
    """UAC6a.4 - a second head is a merge nobody asked for, and it only shows up
    at deploy time."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = pathlib.Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()

    assert len(heads) == 1, f"expected a single head, found {heads}"


# ------------------------------------------------------------------- UAC6c.3


def test_reference_data_is_derived_from_the_consumer_slugs(seeded):
    """One role per consumer slug, each holding only that slug. Checking the
    seven separately is what catches a typo in one entry of the migration's list;
    a single role holding all seven would be granted via any one of them and hide
    six broken entries."""
    db, fixtures = seeded
    _run_upgrade(db)

    missing = [s for s in CONSUMER_SLUGS if not _holds(db, fixtures["consumers"][s], REFERENCE_DATA_VIEW)]
    assert not missing, (
        f"roles holding {missing} did not receive {REFERENCE_DATA_VIEW} - the picker "
        "on those screens would 403 for a role fully entitled to the page"
    )


def test_neither_slug_reaches_a_role_that_qualifies_for_neither(seeded):
    """The other half of the derivation pair, plus the independence of the two
    grants. The bystander holds a real permission (`user_management.teams.view`)
    that is not a consumer slug and is not in the contacts list, so it must gain
    nothing - without this, a migration that granted to every role would pass
    every positive test above.

    The independence of the two grants is proved from the other side: a role
    seeded holding only a cross-module consumer slug qualifies for
    reference_data.view and is NOT in the contacts list, so it must not receive
    contacts.view. If the second grant silently reused the first's role set, or
    the first reused the second's, one of these two halves fails.
    """
    db, fixtures = seeded
    _run_upgrade(db)

    bystander = fixtures["bystander"]
    assert not _holds(db, bystander, CONTACTS_VIEW)
    assert not _holds(db, bystander, REFERENCE_DATA_VIEW), (
        "the derivation granted the low-privilege reference slug to a role holding "
        "none of the ten consumer slugs - it is not deriving, it is granting to all"
    )

    forms_consumer = fixtures["consumers"]["forms.forms.view"]
    assert _holds(db, forms_consumer, REFERENCE_DATA_VIEW)
    assert not _holds(db, forms_consumer, CONTACTS_VIEW), (
        "a role holding only a consuming screen's view slug was handed the contact "
        "directory - the hardcoded contacts list has picked up the derived role set"
    )


def test_a_role_granted_contacts_view_in_this_run_also_derives_reference_data(seeded):
    """`contacts.view` is itself a consumer slug (the contact detail page reads
    both catalogs), and this migration is what grants it. So the derivation has
    to run AFTER the contacts grant, in the same transaction, or every role that
    gains contacts.view here opens a contact detail page with an empty, 403ing
    market-segment picker.

    `director` is the case that proves it: seeded holding no permission at all,
    it can only reach reference_data.view through the contacts.view this run
    gave it.
    """
    db, fixtures = seeded
    director = fixtures["roles"]["director"]
    assert not _holds(db, director, CONTACTS_VIEW), (
        "the fixture must seed director with no grants - the in-run ordering is the point"
    )

    _run_upgrade(db)

    assert _holds(db, director, CONTACTS_VIEW)
    assert _holds(db, director, REFERENCE_DATA_VIEW), (
        "the derivation ran before the contacts grant, so roles granted contacts.view "
        "by this migration never derive reference_data.view"
    )


# ---------------------------------------------------------------- idempotency


def test_running_upgrade_twice_inserts_no_extra_rows(seeded):
    """The shared dev database gets migrations replayed across worktrees, and a
    double grant is invisible until someone counts rows on the roles screen."""
    db, _ = seeded
    _run_upgrade(db)
    first = {slug: _grant_count(db, slug) for slug in (CONTACTS_VIEW, REFERENCE_DATA_VIEW)}
    # The four named roles, plus the consumer role the fixture seeds already
    # holding contacts.view - it is one of the ten consumer slugs now.
    assert first[CONTACTS_VIEW] == len(SEEDED_CONTACTS_ROLES) + 1
    # One consumer role per slug, plus the contacts roles that derive it through
    # the contacts.view this run grants them.
    assert first[REFERENCE_DATA_VIEW] == len(CONSUMER_SLUGS) + len(SEEDED_CONTACTS_ROLES)

    _run_upgrade(db)
    second = {slug: _grant_count(db, slug) for slug in (CONTACTS_VIEW, REFERENCE_DATA_VIEW)}

    assert second == first, f"second run changed the grant counts: {first} -> {second}"


# --------------------------------------------------------------- fresh install


def test_fresh_install_with_no_consumer_grants_upgrades_cleanly():
    """UAC6a.4's other half: an install where NOTHING holds a consumer slug.

    The derivation returns an empty set, `_grant` is handed nothing, and the
    migration has to finish anyway - a `WHERE role_id = ANY('{}')` or an
    unguarded `raise` here would break every fresh install and no
    prod-copy-backed test would ever see it. The one seeded role is deliberately
    NOT in the contacts list: contacts.view is a consumer slug now, so seeding a
    role the migration grants it to would make the derivation non-empty and this
    test would stop testing the empty case.
    """
    with blank_session() as db:
        outsider = _role(db, f"zzt_fresh_install_{uuid.uuid4().hex[:8]}")
        db.flush()

        _run_upgrade(db)  # must not raise

        assert not _holds(db, outsider, CONTACTS_VIEW)
        assert _grant_count(db, REFERENCE_DATA_VIEW) == 0, (
            "reference_data.view was granted to somebody on an install where no role "
            "holds any consuming screen's view permission"
        )
