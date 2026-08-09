"""S7b gate, part 3 - the MUST-NOTs (AC-P0a, AC-P2c, AC-P3a, AC-P6a, AC-P11, AC-X4).

Written BEFORE the implementation. The other two files say what S7b must DO. This
one says what it must not do, and every entry is a thing that would pass every
behavioural test in the slice while being wrong.

Six guards:

1. **No sqlite anywhere in the new suite.** This repo has been bitten twice: a
   mostly-zero UUID coerced to the integer 1 under NUMERIC affinity, and a fixture
   rewriting `col.type` on the process-global metadata that broke tests in files
   containing no sqlite at all. The rule is in PRINCIPLES.md and is enforced here so
   a future contributor cannot reintroduce it quietly.

2. **No EXCLUDE constraint on `warranty_policies` (AC-P2c).** The constraint that
   would express AC-P2b needs `btree_gist`, which is *available* but NOT installed
   on the dev database and whose creatability on the managed production instance is
   unverified. A migration that might be refused at deploy time is a worse trade
   than a service guard on a table with two writers and tens of rows. This guard
   exists so a later reviewer cannot "tighten" AC-P2b into a deploy outage without
   deleting a test that says why.

3. **The duration/lifetime XOR is a DATABASE constraint, not only a service rule
   (AC-P3a)** - and it must be on the MODEL, not only in the migration. CI builds
   its schema from `Base.metadata.create_all` (`scripts/bootstrap_env`) and stamps
   alembic at head without running migration bodies, so a constraint that exists
   only in `331_warranty_config.py` is absent from every test database and from
   every fresh install.

4. **One ranking, reachable from the tester (AC-P6a).** Asserted with the AST, and
   the detector is proved against `warranty_service.py` itself in the same test, so
   a guard that silently stopped detecting anything cannot pass.

5. **The router is mounted under the warranty module guard (AC-P0a).** Also AST,
   also with a positive control - the existing `complaints` mount - so the detector
   is known to work before its absence is treated as a finding.

6. **The permission slugs exist and are granted (AC-P11, AC-X4).** `sync_permissions`
   seeds a slug and grants it to NOBODY, so a migration that only calls it ships a
   feature every non-admin is locked out of. The grant half is asserted against the
   migration source, because CI's database is bootstrapped from the ORM and never
   runs a migration body - a DB-level assertion would be green on a machine that had
   run the migration and red on the one that gates the merge.

Run: venv/bin/python -m pytest tests/test_warranty_config_guards.py -q -p no:randomly
"""
from __future__ import annotations

import ast
import pathlib
import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DatabaseError

from app.models.warranty import (
    WarrantyKindRule,
    WarrantyPolicy,
    WarrantyProductKind,
    WarrantyTerm,
)

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

BACKEND = pathlib.Path(__file__).resolve().parents[1]
TESTS = BACKEND / "tests"
VERSIONS = BACKEND / "alembic" / "versions"

# The one module that owns the ranking (AC-P6a).
RANKING_OWNER = BACKEND / "app" / "services" / "warranty_service.py"

# Everything S7b adds that could plausibly grow a second ranking. The tester route
# is the whole reason this guard exists.
NEW_BACKEND_FILES = (
    BACKEND / "app" / "services" / "warranty_config_service.py",
    BACKEND / "app" / "schemas" / "warranty_config.py",
    BACKEND / "app" / "api" / "v1" / "warranty" / "__init__.py",
    BACKEND / "app" / "api" / "v1" / "warranty" / "policies.py",
    BACKEND / "app" / "api" / "v1" / "warranty" / "terms.py",
    BACKEND / "app" / "api" / "v1" / "warranty" / "kinds.py",
    BACKEND / "app" / "api" / "v1" / "warranty" / "kind_rules.py",
)

# The route modules whose dependency declarations AC-P11 constrains.
ROUTE_FILES = tuple(f for f in NEW_BACKEND_FILES if "api/v1/warranty" in f.as_posix())

# The two new test files. NOT this one: it names sqlite in prose, which is the
# point of it, and a scanner that read itself would report its own docstring.
NEW_TEST_FILES = (
    TESTS / "test_warranty_config_api.py",
    TESTS / "test_warranty_config_ranking.py",
)

# AC-P11, verbatim. Eight slugs, and no ninth.
WARRANTY_SLUGS = (
    "warranty.policies.view",
    "warranty.policies.add",
    "warranty.policies.edit",
    "warranty.policies.delete",
    "warranty.kinds.view",
    "warranty.kinds.add",
    "warranty.kinds.edit",
    "warranty.kinds.delete",
)

# AC-P23, named rather than left to the implementer. view/add/edit reach the four
# management-shaped roles (migration 236's precedent); the two `.delete` slugs reach
# admin and director ONLY, because deleting a Policy cascades its Terms and deleting
# a Kind is refused precisely because it would rewrite the policy document.
GRANT_ROLES = ("admin", "director", "management", "manager")
DELETE_ROLES = ("admin", "director")
DELETE_SLUGS = ("warranty.policies.delete", "warranty.kinds.delete")

# AC-P3a / AC-P19 name the constraint, so the name is part of the contract: a
# migration rollback and a reviewer both address it by name.
XOR_CONSTRAINT = "ck_warranty_terms_duration_xor_lifetime"


# ------------------------------------------------------------------- helpers


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _source(path: pathlib.Path) -> str:
    assert path.exists(), (
        f"{path.relative_to(BACKEND)} does not exist. The plan pins the S7b backend "
        "layout; this file is part of it."
    )
    return path.read_text(encoding="utf-8")


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(_source(path), filename=str(path))


def _defined_names(tree: ast.Module) -> set[str]:
    """Every name this module DEFINES: functions, classes, module-level assignments.

    Definitions, not references - a route that CALLS `resolve_kind_match` is the
    goal; a route that DEFINES its own `_RuleMatch` is the failure.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _referenced_names(tree: ast.Module) -> set[str]:
    """Every bare name and attribute name the module mentions."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def _include_router_calls(tree: ast.Module):
    """Every `*.include_router(...)` call in the module, as (kwargs dict, node)."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "include_router":
            out.append(node)
    return out


def _mounted_with_module_guard(tree: ast.Module, prefix: str, module_key: str) -> bool:
    """True when a router is included at `prefix` under the module guard for
    `module_key`. Structural, not textual: a prefix that appears in a comment or a
    guard called on a different mount must not count."""
    for call in _include_router_calls(tree):
        kwargs = {kw.arg: kw.value for kw in call.keywords}
        got_prefix = kwargs.get("prefix")
        if not (isinstance(got_prefix, ast.Constant) and got_prefix.value == prefix):
            continue
        deps = kwargs.get("dependencies")
        if deps is None:
            return False
        for dep in ast.walk(deps):
            if not isinstance(dep, ast.Call):
                continue
            inner = dep.func
            name = inner.attr if isinstance(inner, ast.Attribute) else getattr(inner, "id", None)
            if name != "require_module_enabled_with_api_key":
                continue
            if any(
                isinstance(a, ast.Constant) and a.value == module_key for a in dep.args
            ):
                return True
        return False
    return False


def _string_collections(tree: ast.Module) -> list[frozenset[str]]:
    """Every tuple / list / set literal made entirely of string constants.

    AC-P23 is about WHICH roles a slug reaches, and that is a pairing between two
    collections inside a migration body. Reading the pairing itself would mean
    interpreting the migration's control flow, so the gate asserts the weaker,
    checkable thing: the role sets it names. A migration that grants delete to all
    four roles has no `{admin, director}` literal in it at all.

    Proved against migration 236 below, whose `_GRANT_ROLE_SLUGS` is exactly the
    four-role shape the plan tells the implementer to copy.
    """
    out: list[frozenset[str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            continue
        values = [
            e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
        if values and len(values) == len(node.elts):
            out.append(frozenset(values))
    return out


def _migration_sources() -> dict[pathlib.Path, str]:
    return {p: p.read_text(encoding="utf-8", errors="ignore") for p in VERSIONS.glob("*.py")}


def _grants_a_role_permission(source: str) -> bool:
    """True when a migration writes a role->permission grant.

    Deliberately a substring test on the TABLE name rather than a regex over SQL:
    the insert is spelled several ways across this repo (raw text, op.execute, a
    helper loop) and the one thing they share is naming `user_role_permissions`.
    Proved against migration 236 in the test below, which is the shape the plan
    tells the implementer to follow.

    Lower-cased once, on the whole source. The first version of this helper asked
    for `"INSERT INTO user_role_permissions" in source.upper()`, which can never
    match: `.upper()` uppercases the table name too. It failed its own positive
    control, which is the entire reason that control is here.
    """
    lowered = source.lower()
    return "user_role_permissions" in lowered and "insert" in lowered


# =============================================================================
# Guard 1 - no sqlite anywhere in the new suite
# =============================================================================


def _sqlite_literals(tree: ast.Module) -> set[str]:
    """Every string literal that NAMES the sqlite dialect or a sqlite URL.

    An AST walk over literals rather than a substring scan of the file, so a
    docstring that says "never sqlite" (which every file in this suite does say, on
    purpose) is not a violation while `create_engine("sqlite:///:memory:")` and
    `@compiles(JSONB, "sqlite")` both are.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip().lower()
            if value == "sqlite" or value.startswith("sqlite:"):
                found.add(node.value)
    return found


def test_the_sqlite_detector_actually_detects():
    """A guard that stopped detecting would pass forever. Prove it first, on both
    shapes this repo was actually bitten by, and prove it does NOT fire on prose."""
    assert _sqlite_literals(ast.parse('create_engine("sqlite:///:memory:")'))
    assert _sqlite_literals(ast.parse('@compiles(JSONB, "sqlite")\ndef f(*a): pass'))
    assert not _sqlite_literals(ast.parse('"""Runs on Postgres - never sqlite."""'))
    assert not _sqlite_literals(ast.parse("engine = create_engine(settings.database_url)"))


@pytest.mark.parametrize("path", NEW_TEST_FILES, ids=lambda p: p.name)
def test_no_new_test_builds_a_sqlite_engine(path):
    """PRINCIPLES.md, hard rule. Two concrete failures this caused in this repo:
    sqlite's NUMERIC affinity coerced the mostly-zero Sorento company id to the
    integer 1, and a fixture rewriting a shared `Base.metadata` column type leaked
    into other tests' `create_all` schema - surfacing only in a full-suite run, in a
    file that touched no sqlite.
    """
    found = _sqlite_literals(_tree(path))
    assert not found, (
        f"{path.name} names the sqlite dialect ({sorted(found)}). Backend tests run "
        "on Postgres ONLY, via tests/_pg_fixture.py."
    )


@pytest.mark.parametrize("path", NEW_BACKEND_FILES, ids=lambda p: p.name)
def test_no_new_backend_module_names_the_sqlite_dialect(path):
    """The same rule one layer down. A `@compiles(..., "sqlite")` shim in a service
    is a production file that only exists to make a test substrate work."""
    found = _sqlite_literals(_tree(path))
    assert not found, f"{path.name} names the sqlite dialect ({sorted(found)})."


@pytest.mark.parametrize("path", NEW_TEST_FILES, ids=lambda p: p.name)
def test_no_new_test_uses_sessionlocal_directly(path):
    """`SessionLocal` writes to the real database and does not roll back. The local
    database is a copy of production; an earlier suite destroyed real records this
    way."""
    assert "SessionLocal" not in _source(path), (
        f"{path.name} uses SessionLocal. Use blank_session() or pg_session()."
    )


# =============================================================================
# Guard 2 - AC-P2c: no EXCLUDE constraint, and no btree_gist
# =============================================================================


def test_the_policy_table_declares_no_exclusion_constraint():
    """AC-P2c, at the model. `btree_gist` is available but NOT installed on the dev
    database, and whether `CREATE EXTENSION` is permitted on the managed production
    instance is not something this slice can verify.

    Recorded, measured and revisitable - not forgotten. Delete this test only
    together with a measurement showing `btree_gist` is creatable on prod.
    """
    kinds = {type(c).__name__ for c in WarrantyPolicy.__table__.constraints}
    assert "ExcludeConstraint" not in kinds, (
        "warranty_policies grew an EXCLUDE constraint. It needs btree_gist, which is "
        "not installed on the dev database and unverified on prod - a migration that "
        "may be refused at deploy time. AC-P2c: the service guard stands until "
        "btree_gist is confirmed creatable."
    )


def test_no_migration_installs_btree_gist_or_excludes_a_policy_range():
    """The same ruling, at the place it would actually be violated."""
    offenders = [
        path.name
        for path, source in _migration_sources().items()
        if "btree_gist" in source.lower()
        or ("EXCLUDE USING" in source.upper() and "warranty_policies" in source)
    ]
    assert not offenders, (
        "These migrations reach for btree_gist / an exclusion constraint: "
        f"{offenders}. AC-P2c rules it out with a measurement; re-measure before "
        "overturning it."
    )


def test_the_live_database_has_no_exclusion_constraint_on_warranty_policies(db):
    """And at the database, because a constraint added by hand on a server is
    invisible to both checks above."""
    rows = db.execute(
        sa.text(
            "SELECT conname FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = 'warranty_policies' AND c.contype = 'x'"
        )
    ).fetchall()
    assert rows == [], f"warranty_policies carries an exclusion constraint: {rows}"


# =============================================================================
# Guard 3 - AC-P3a: the XOR is enforced by the database, from the MODEL
# =============================================================================


def test_the_duration_xor_lifetime_check_constraint_is_declared_on_the_model():
    """AC-P19 (was AC-P3a), and the reason it must be on the MODEL and not only in
    the migration:
    CI builds its schema with `Base.metadata.create_all` and then STAMPS alembic at
    head without running the migration bodies (`scripts/bootstrap_env`). A
    constraint declared only in `331_warranty_config.py` therefore exists on the
    developer's machine and on prod, and on no test database anywhere - so the test
    below would pass locally and prove nothing in CI.
    """
    names = {c.name for c in WarrantyTerm.__table__.constraints if c.name}
    assert XOR_CONSTRAINT in names, (
        f"{XOR_CONSTRAINT} is not declared on WarrantyTerm.__table_args__. "
        f"Declared constraints: {sorted(n for n in names)}"
    )


def test_a_migration_adds_the_check_constraint_too():
    """The model covers fresh databases; the migration covers the ones that already
    exist - including prod, whose 41 rows were measured against it on 2026-08-09."""
    hits = [
        path.name
        for path, source in _migration_sources().items()
        if XOR_CONSTRAINT in source
    ]
    assert hits, (
        f"No alembic revision creates {XOR_CONSTRAINT}. A constraint that exists only "
        "on the model is green in every test here and absent on the live database."
    )


@pytest.mark.parametrize(
    "duration_months,is_lifetime,why",
    [
        (60, True, "both a duration and lifetime"),
        (None, False, "neither a duration nor lifetime"),
        (0, False, "a zero-month duration"),
        (-12, False, "a negative duration"),
    ],
)
def test_the_database_itself_rejects_a_term_that_is_neither_or_both(
    db, duration_months, is_lifetime, why
):
    """AC-P3a. The service guard is the message; the constraint is the truth.

    Written as a RAW INSERT on purpose: the service is not the only writer. A seed
    script, a migration backfill and a psql session all bypass it, and a term that
    records neither a duration nor lifetime answers `unknown` on every complaint
    forever (the engine's own ruling).
    """
    kind = WarrantyProductKind(
        id=str(uuid.uuid4()), code=unique_code("kind")[:64], name=f"{TEST_PREFIX} kind"
    )
    db.add(kind)
    policy = WarrantyPolicy(
        id=str(uuid.uuid4()), version=unique_code("v")[:32], effective_from=date(2020, 1, 1)
    )
    db.add(policy)
    db.flush()

    savepoint = db.begin_nested()
    raised = False
    try:
        db.execute(
            sa.text(
                "INSERT INTO warranty_terms "
                "(id, policy_id, kind_id, part_name, duration_months, is_lifetime, "
                " installation_included) "
                "VALUES (:id, :policy_id, :kind_id, :part_name, :duration_months, "
                ":is_lifetime, false)"
            ),
            {
                "id": str(uuid.uuid4()),
                "policy_id": policy.id,
                "kind_id": kind.id,
                "part_name": f"{TEST_PREFIX} part",
                "duration_months": duration_months,
                "is_lifetime": is_lifetime,
            },
        )
    except DatabaseError:
        raised = True
    finally:
        savepoint.rollback()

    assert raised, (
        f"The database accepted a term with {why}. AC-P3a: enforced in the service "
        f"AND as {XOR_CONSTRAINT}."
    )


def test_the_check_constraint_still_admits_the_two_shapes_that_are_legal(db):
    """The other half, and the one that turns a constraint into an outage if it is
    written slightly wrong. AC-P3a measured all 41 live rows against it before the
    constraint was written; both shapes below are among them."""
    kind = WarrantyProductKind(
        id=str(uuid.uuid4()), code=unique_code("kind")[:64], name=f"{TEST_PREFIX} kind"
    )
    db.add(kind)
    policy = WarrantyPolicy(
        id=str(uuid.uuid4()), version=unique_code("v")[:32], effective_from=date(2020, 1, 1)
    )
    db.add(policy)
    db.flush()

    db.add(
        WarrantyTerm(
            id=str(uuid.uuid4()),
            policy_id=policy.id,
            kind_id=kind.id,
            part_name="Ceramic Body",
            is_lifetime=True,
            duration_months=None,
        )
    )
    db.add(
        WarrantyTerm(
            id=str(uuid.uuid4()),
            policy_id=policy.id,
            kind_id=kind.id,
            part_name="Flushing Fittings",
            is_lifetime=False,
            duration_months=60,
        )
    )
    db.flush()


# =============================================================================
# Guard 4 - AC-P6a: exactly one ranking, and the tester reaches it
# =============================================================================

# The names that constitute "a ranking". Defining any of them outside
# warranty_service.py is a second implementation of AC-D20's total order.
RANKING_NAMES = (
    "_RuleMatch",
    "_matched_length",
    "KIND_RULE_SPECIFICITY",
    "_SPECIFICITY_RANK",
    "sort_key",
    "rank_kind_matches",
    "resolve_kind_match",
)


def test_the_ranking_detector_actually_detects():
    """Positive control. The detector is only worth having if it finds the ranking
    where the ranking demonstrably is."""
    defined = _defined_names(_tree(RANKING_OWNER))
    for name in ("_RuleMatch", "_matched_length", "KIND_RULE_SPECIFICITY", "_SPECIFICITY_RANK"):
        assert name in defined, (
            f"{name} is not detected as defined in warranty_service.py, so this "
            "guard is not detecting anything and its silence means nothing."
        )


@pytest.mark.parametrize("path", NEW_BACKEND_FILES, ids=lambda p: p.name)
def test_no_new_module_defines_its_own_ranking(path):
    """AC-P6a. "A tester with its own ranking agrees with production right up to the
    day it matters." """
    defined = _defined_names(_tree(path))
    duplicated = sorted(defined & set(RANKING_NAMES))
    assert not duplicated, (
        f"{path.name} defines {duplicated}. AC-P6a: the tester runs the PRODUCTION "
        "ranking, not a copy of it - `warranty_service` owns it."
    )


def test_the_tester_route_reaches_the_production_ranking():
    """The other half of the same guard: not duplicating it is worthless if the
    route answers from something else entirely."""
    kind_rules = BACKEND / "app" / "api" / "v1" / "warranty" / "kind_rules.py"
    service = BACKEND / "app" / "services" / "warranty_config_service.py"
    referenced = set()
    for path in (kind_rules, service):
        referenced |= _referenced_names(_tree(path))
    assert referenced & {"rank_kind_matches", "resolve_kind_match"}, (
        "Neither the kind-rules route nor warranty_config_service mentions "
        "rank_kind_matches / resolve_kind_match. The tester must answer from "
        "warranty_service's ranking (AC-P6a)."
    )


# =============================================================================
# Guard 5 - AC-P0a: mounted under the warranty module, with a working prefix
# =============================================================================


def test_the_mount_detector_actually_detects():
    """Positive control against an existing mount, so an absent warranty mount is a
    finding rather than a broken detector."""
    tree = _tree(BACKEND / "app" / "api" / "v1" / "__init__.py")
    assert _mounted_with_module_guard(tree, "/complaints-management", "complaints"), (
        "The detector cannot see the existing complaints mount, so it cannot be "
        "trusted about the warranty one."
    )
    assert not _mounted_with_module_guard(tree, "/complaints-management", "warranty")


def test_the_warranty_router_is_mounted_under_the_warranty_module_guard():
    """AC-P0a. `lib/route-module-map.ts` gates `/master-data-management` on the
    PRODUCT module, so a warranty editor placed there survives uninstalling warranty
    and vanishes when the product module goes. The backend half of that ruling is
    this mount."""
    tree = _tree(BACKEND / "app" / "api" / "v1" / "__init__.py")
    assert _mounted_with_module_guard(tree, "/warranty-management", "warranty"), (
        "No router is included at prefix '/warranty-management' under "
        'require_module_enabled_with_api_key("warranty").'
    )


def test_the_warranty_manifest_declares_a_router_prefix():
    """AC-P0a: "manifest.ROUTER_PREFIX and EXPORT_FILES_FRONTEND are updated in the
    same slice, or the module exports a surface it does not carry."

    S2 shipped four tables and no module key; the manifest was the correction. A
    manifest whose ROUTER_PREFIX stays None after this slice claims the module has
    no HTTP surface, and the App Store's uninstall/export path believes it.
    """
    from app.modules.warranty import manifest

    assert manifest.ROUTER_PREFIX is not None, (
        "app/modules/warranty/manifest.py still has ROUTER_PREFIX = None while the "
        "module now owns /api/v1/warranty-management."
    )
    assert "warranty-management" in str(manifest.ROUTER_PREFIX)
    assert manifest.MODULE_KEY == "warranty"


def test_the_warranty_manifest_exports_the_new_backend_files():
    """A module that cannot export its own routes cannot be installed anywhere else,
    which is the whole point of the manifest."""
    from app.modules.warranty import manifest

    exported = set(manifest.EXPORT_FILES_BACKEND)
    for required in (
        "app/services/warranty_config_service.py",
        "app/schemas/warranty_config.py",
    ):
        assert required in exported, f"{required} is not in EXPORT_FILES_BACKEND."
    assert any(
        path.startswith("app/api/v1/warranty/") for path in exported
    ), "No route file under app/api/v1/warranty/ is exported."


# =============================================================================
# Guard 6 - AC-P11 / AC-X4: the slugs exist, and somebody actually holds them
# =============================================================================


def test_the_eight_warranty_slugs_are_in_the_registry():
    """AC-P11."""
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {row["slug"] for row in PERMISSION_REGISTRY}
    missing = [s for s in WARRANTY_SLUGS if s not in slugs]
    assert not missing, f"Missing from PERMISSION_REGISTRY: {missing}"


def test_there_is_no_separate_slug_for_terms_or_for_kind_rules():
    """AC-P11: "Terms ride the policies slug and kind rules ride the kinds slug - a
    rule has no life apart from the Kind it points at, and a slug nobody will ever
    grant separately is a slug that rots." """
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    warranty = {row["slug"] for row in PERMISSION_REGISTRY if row["slug"].startswith("warranty.")}
    extra = sorted(warranty - set(WARRANTY_SLUGS))
    missing = sorted(set(WARRANTY_SLUGS) - warranty)
    assert warranty == set(WARRANTY_SLUGS), (
        f"warranty.* slugs are wrong. Unexpected: {extra}. Missing: {missing}."
    )


def test_every_warranty_slug_is_gated_on_the_warranty_module():
    """AC-P0a's other half. An unmapped prefix returns None from
    `module_for_permission`, which means "never module-gated" - the permission
    survives uninstalling the module that gives it meaning."""
    from app.modules.runtime.permission_module_map import module_for_permission

    for slug in WARRANTY_SLUGS:
        assert module_for_permission(slug) == "warranty", slug


def test_the_role_grant_detector_actually_detects():
    """Positive control against `236_seed_sla_kpi_view_perm.py` - the migration the
    plan tells the implementer to follow for the grant half."""
    reference = VERSIONS / "236_seed_sla_kpi_view_perm.py"
    assert reference.exists()
    assert _grants_a_role_permission(reference.read_text(encoding="utf-8"))
    assert not _grants_a_role_permission("op.create_table('warranty_terms')")


def test_a_migration_seeds_the_warranty_slugs_and_grants_them_to_roles():
    """AC-P11 + AC-X4. "which means the migration does more than call
    `sync_permissions` - that seeds the slug and grants nobody."

    Asserted against the migration SOURCE rather than against the database on
    purpose: CI bootstraps its schema from the ORM and stamps alembic at head
    without executing a single migration body, so a DB assertion would be green on
    a developer's machine and prove nothing on the run that gates the merge.
    """
    candidates = {
        path: source
        for path, source in _migration_sources().items()
        if any(slug in source for slug in WARRANTY_SLUGS) or "warranty.policies" in source
    }
    assert candidates, (
        "No alembic revision mentions the warranty.* permission slugs. A permission "
        "that exists only in PERMISSION_REGISTRY reaches an existing database only "
        "when somebody remembers to run sync_permissions by hand."
    )
    granting = [path.name for path, source in candidates.items() if _grants_a_role_permission(source)]
    assert granting, (
        "A migration seeds the warranty slugs but grants them to no role "
        f"(candidates: {sorted(p.name for p in candidates)}). sync_permissions seeds "
        "the slug and grants nobody, so every non-admin is locked out of the screen "
        "the slice exists to ship (AC-X4)."
    )


def test_the_role_set_collector_actually_detects():
    """Positive control for AC-P23's structural check, against the precedent the
    plan names. If this stops seeing 236's four-role tuple, the two tests below are
    asserting nothing."""
    reference = VERSIONS / "236_seed_sla_kpi_view_perm.py"
    collections = _string_collections(ast.parse(reference.read_text(encoding="utf-8")))
    assert frozenset(GRANT_ROLES) in collections, (
        "The collector cannot see 236's _GRANT_ROLE_SLUGS, so it cannot be trusted "
        "about the warranty migration."
    )
    assert frozenset(DELETE_ROLES) not in collections
    assert _string_collections(ast.parse("x = ('a', b)")) == []


def _warranty_permission_migrations():
    """The revisions that seed the warranty slugs, as parsed trees."""
    found = {}
    for path, source in _migration_sources().items():
        if any(slug in source for slug in WARRANTY_SLUGS) or "warranty.policies" in source:
            found[path] = ast.parse(source, filename=str(path))
    return found


def test_the_migration_names_the_four_roles_that_may_configure_warranty():
    """AC-P23. `sync_permissions` seeds a slug and grants nobody, so "the provisioned
    roles" has to be spelled out or the screen ships locked to admins only - and
    admin/superadmin bypass `require_permission` entirely, which means nobody would
    ever notice in testing.
    """
    trees = _warranty_permission_migrations()
    assert trees, "No alembic revision mentions the warranty.* permission slugs."
    collections = [c for tree in trees.values() for c in _string_collections(tree)]
    assert frozenset(GRANT_ROLES) in collections, (
        f"No warranty migration names the role set {GRANT_ROLES}. Found role-shaped "
        f"literals: {[sorted(c) for c in collections if c & set(GRANT_ROLES)]}"
    )


def test_the_two_delete_slugs_are_granted_to_a_narrower_role_set():
    """AC-P23. Deleting a Policy cascades its Terms, and deleting a Kind is REFUSED
    precisely because it would rewrite the policy document (AC-P12) - so the grant
    that can do the first must not travel with the grant that reads the screen.

    Asserted structurally: a migration that hands `.delete` to all four roles
    contains no `{admin, director}` literal at all, and one that grants the delete
    slugs to nobody contains no delete-slug literal. Both are the failure this
    catches; the pairing itself is only observable once the migration has run.
    """
    trees = _warranty_permission_migrations()
    assert trees, "No alembic revision mentions the warranty.* permission slugs."
    collections = [c for tree in trees.values() for c in _string_collections(tree)]

    assert frozenset(DELETE_ROLES) in collections, (
        f"No warranty migration names the narrower delete-role set {DELETE_ROLES}. "
        "If every warranty slug is granted to the same four roles, a manager can "
        "delete a published policy and take its terms with it."
    )
    assert any(set(DELETE_SLUGS) <= c for c in collections), (
        f"No warranty migration groups {DELETE_SLUGS} together, so they cannot be "
        "granted separately from view/add/edit."
    )
    assert not any(
        (c & set(DELETE_SLUGS)) and (c & {"warranty.policies.view", "warranty.kinds.view"})
        for c in collections
    ), (
        "A single literal holds both a `.delete` slug and a `.view` slug, so they "
        "are granted as one set. AC-P23 splits them."
    )


# =============================================================================
# Guard 7 - AC-P11: which principal each verb accepts
# =============================================================================


def test_only_reads_accept_an_api_key_principal():
    """AC-P11: "Reads take `require_permission_with_api_key`, writes take
    `require_permission`."

    Read at the source, line by line, because a route's dependency list is not
    introspectable once FastAPI has flattened it into a solved dependency tree - and
    because scanning raw source would otherwise match the module docstring
    explaining this very rule.
    """
    offenders = []
    for path in ROUTE_FILES:
        for line in _source(path).splitlines():
            stripped = line.strip()
            if "Depends(require_permission_with_api_key" not in stripped:
                continue
            if ".view" not in stripped and "VIEW" not in stripped:
                offenders.append(f"{path.name}: {stripped}")
    assert not offenders, (
        "An API key can reach a warranty write:\n" + "\n".join(offenders) + "\n"
        "require_permission_with_api_key is documented as read-oriented, and the two "
        "write exceptions in this codebase both carry a second real-user gate at the "
        "assistant layer. Nothing in S7b has one."
    )


def test_every_warranty_route_declares_a_permission():
    """Deny by default, asserted structurally so a route added later cannot ship
    ungated just because nobody wrote a behavioural test for it."""
    ungated = []
    for path in ROUTE_FILES:
        tree = _tree(path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = [
                d for d in node.decorator_list
                if isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute)
                and d.func.attr in {"get", "post", "patch", "put", "delete"}
            ]
            if not decorators:
                continue
            referenced = _referenced_names(ast.Module(body=[node], type_ignores=[]))
            if not referenced & {"require_permission", "require_permission_with_api_key"}:
                ungated.append(f"{path.name}:{node.name}")
    assert not ungated, f"Routes with no permission dependency: {ungated}"


# =============================================================================
# Guard 8 - the hazards the rulings are written against
# =============================================================================


def test_an_assessment_survives_the_term_it_quotes():
    """AC-P8a's premise. SET NULL, not CASCADE: re-publishing a policy must not
    silently delete the verdicts a human already acted on."""
    from app.models.warranty import WarrantyAssessment

    fks = list(WarrantyAssessment.__table__.c.term_id.foreign_keys)
    assert fks and fks[0].ondelete == "SET NULL", (
        "warranty_assessments.term_id is not ON DELETE SET NULL. AC-P8a is written "
        "against SET NULL and the snapshot columns."
    )


def test_a_term_dies_with_its_policy():
    """AC-P13's premise. Terms have no life apart from the Policy that dates them."""
    fks = list(WarrantyTerm.__table__.c.policy_id.foreign_keys)
    assert fks and fks[0].ondelete == "CASCADE"


def test_terms_and_kind_rules_are_not_company_scoped():
    """AC-P9's premise, and the reason the nested route is load-bearing.

    A Term is only ever reachable through its `policy_id`; scoping it again would be
    a second copy of the same fact that can disagree with the first. Kinds and rules
    are a shared vocabulary - "Water Closet" is one physical thing whichever brand
    sells it (AC-P10). If any of these ever became scoped, AC-P9's ruling needs
    re-reading, not silently keeping.
    """
    from app.models.base import CompanyScopedMixin

    assert issubclass(WarrantyPolicy, CompanyScopedMixin), (
        "WarrantyPolicy must stay company-scoped - Sorento and Mocha publish "
        "different durations for the same product kinds."
    )
    for model in (WarrantyTerm, WarrantyProductKind, WarrantyKindRule):
        assert not issubclass(model, CompanyScopedMixin), (
            f"{model.__name__} became company-scoped. AC-P9 and AC-P10 are both "
            "written against it NOT being."
        )
