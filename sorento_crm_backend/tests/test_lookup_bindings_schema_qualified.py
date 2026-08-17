"""A lookup binding is keyed by the SCHEMA-QUALIFIED table name, not the bare one.

The bare name stopped identifying a table the moment ADR-0011 moved the projects module
into its own schema: `purchase_orders`, `purchase_order_lines`, `sales_orders`,
`sales_order_lines`, `brands`, `quotations` and `quotation_lines` each now exist as a core
`public` table AND as a `projects` one, and they are different things.

Keyed on the bare name, three things break at once and none of them raise:

* binding a set to a projects column 422s, because `Base.metadata.tables.get("leads")`
  misses - a schema-qualified table is keyed `"projects.leads"`;
* a binding on core `purchase_orders.status` also polices writes to
  `projects.purchase_orders.status`, rejecting values that are perfectly valid there;
* the eligibility picker dedupes on the bare name, so one table of each colliding pair
  silently disappears from the list depending on model import order.

`Table.key` is the bare name for a default-schema table and `schema.name` for the rest,
which is exactly the distinction wanted, so every core binding keeps working unchanged.
"""
from __future__ import annotations

import pytest
from uuid import uuid4

from sqlalchemy import inspect as sa_inspect

import app.models  # noqa: F401  register every model
from app.models.procurement import PurchaseOrder
from app.models.projects import ProjectPurchaseOrder
from app.schemas.lookup import LookupBindingCreate, LookupOptionCreate, LookupSetCreate
from app.services.error_handler import AppException
from app.services.lookup_binding_service import LookupBindingService
from app.services.lookup_eligibility import _REGISTRY, all_eligibility, get_eligibility
from app.services.lookup_option_service import LookupOptionService
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_validator import _cache_clear, validate_lookup_value
from app.services.lookup_write_listener import _check
from tests._pg_fixture import blank_session

CORE_TABLE = "purchase_orders"
PROJECTS_TABLE = "projects.purchase_orders"
COLUMN = "status"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _clean_registry_and_cache():
    """The eligibility override registry short-circuits the metadata path, and the
    validator caches (tenant, table, column) for 60s. Both are module-level."""
    _REGISTRY.clear()
    _cache_clear()
    yield
    _REGISTRY.clear()
    _cache_clear()


def _bind(db, table: str, *, values: list[str]):
    """A set with ``values`` as its options, bound to ``table.status``."""
    sets = LookupSetService(db)
    # `set_key` is ^[a-z][a-z0-9_]{0,79}$, so the shared `unique_code` helper does not fit.
    s = sets.create(
        LookupSetCreate(set_key=f"zzt_{uuid4().hex[:12]}", name="ZZT PO Status")
    )
    for value in values:
        LookupOptionService(db).create(
            s.id, LookupOptionCreate(value=value, label=value.title())
        )
    LookupBindingService(db).create(
        s.id, LookupBindingCreate(table_name=table, column_name=COLUMN)
    )
    _cache_clear()
    return s


# --------------------------------------------------------------------------- #
# (a) a projects column is bindable at all
# --------------------------------------------------------------------------- #

def test_a_projects_column_is_eligible_under_its_qualified_name():
    """`_eligibility_from_metadata` looks the table up by key, so the bare name misses."""
    assert get_eligibility(PROJECTS_TABLE, COLUMN) is not None
    assert get_eligibility("projects.leads", "title") is not None


def test_binding_a_set_to_a_projects_column_is_accepted(db):
    """The 422 the review found: "not registered as a lookup-eligible column"."""
    _bind(db, PROJECTS_TABLE, values=["draft", "issued"])

    binding = LookupBindingService(db).list_for_table_column(
        None, PROJECTS_TABLE, COLUMN
    )
    assert binding is not None
    assert binding.table_name == PROJECTS_TABLE


# --------------------------------------------------------------------------- #
# (b) the two tables of a colliding pair are policed separately
# --------------------------------------------------------------------------- #

def test_a_core_binding_does_not_constrain_the_projects_table(db):
    _bind(db, CORE_TABLE, values=["draft", "issued"])

    with pytest.raises(AppException):
        validate_lookup_value(db, table=CORE_TABLE, column=COLUMN, value="whatever")

    # Same bare name, different table, no binding of its own: nothing to enforce.
    validate_lookup_value(db, table=PROJECTS_TABLE, column=COLUMN, value="whatever")


def test_a_projects_binding_does_not_constrain_the_core_table(db):
    _bind(db, PROJECTS_TABLE, values=["draft", "issued"])

    with pytest.raises(AppException):
        validate_lookup_value(db, table=PROJECTS_TABLE, column=COLUMN, value="whatever")

    validate_lookup_value(db, table=CORE_TABLE, column=COLUMN, value="whatever")


def test_the_write_listener_reads_the_qualified_name_off_the_mapper(db):
    """Defense in depth has to agree with the binding, or the binding is unenforceable.

    The listener derived its table from ``mapper.local_table.name``, so a write to
    `projects.purchase_orders` was checked against core `purchase_orders`'s binding.

    Exercised through ``_check`` directly, inside ``no_autoflush``: the row is never
    written, so its foreign keys do not have to be satisfied to test which name the
    listener reads. In production the listener runs from `before_insert`, mid-flush, which
    does not re-enter autoflush either.
    """
    _bind(db, CORE_TABLE, values=["draft", "issued"])

    with db.no_autoflush:
        project_po = ProjectPurchaseOrder(status="whatever")
        db.add(project_po)
        try:
            # Core's binding must not reach across the schema boundary.
            _check(project_po, sa_inspect(ProjectPurchaseOrder).mapper, only_changed=False)
        finally:
            db.expunge(project_po)

        core_po = PurchaseOrder(status="whatever")
        db.add(core_po)
        try:
            with pytest.raises(AppException):
                _check(core_po, sa_inspect(PurchaseOrder).mapper, only_changed=False)
        finally:
            db.expunge(core_po)


# --------------------------------------------------------------------------- #
# (c) the picker shows both halves of every colliding pair
# --------------------------------------------------------------------------- #

def test_the_eligibility_list_carries_both_tables_of_a_colliding_pair():
    keys = {(e.table_name, e.column_name) for e in all_eligibility()}

    assert (CORE_TABLE, COLUMN) in keys
    assert (PROJECTS_TABLE, COLUMN) in keys


def test_every_eligibility_key_is_unique():
    """The dedupe used to be on the bare name, so one of each pair was dropped."""
    rows = all_eligibility()
    keys = [(e.table_name, e.column_name) for e in rows]

    assert len(keys) == len(set(keys))


def test_a_qualified_table_reads_as_its_schema_and_its_name():
    """The admin screens render `table_label` and fall back to the raw `table_name`.

    Neither may show the operator a bare `Purchase Orders` for both tables, because the
    binding they are about to create only applies to one of them.
    """
    labels = {
        e.table_name: e.table_label
        for e in all_eligibility()
        if e.table_name in {CORE_TABLE, PROJECTS_TABLE}
    }

    assert labels[CORE_TABLE] == "Purchase Orders"
    assert labels[PROJECTS_TABLE] == "Projects / Purchase Orders"
