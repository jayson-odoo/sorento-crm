"""The two structural promises `PURGE_ORDER` makes, checked against the models themselves.

`tests/test_projects_module_purge.py` proves the handler empties what it lists. This file
proves the LIST is right, which is the half a behavioural test cannot reach: a table added to
`app/models/projects.py` next month and forgotten in `app/modules/projects/purge.py` survives
an uninstall-with-purge, and nothing fails. The rows just stay, in a module the tenant asked
to have removed.

Two invariants, both read off the metadata rather than restated as literals:

* **Completeness.** Every `Base` subclass DECLARED in the module's two model files appears in
  `PURGE_ORDER` exactly once. Declared, not imported: both files pull in core models
  (`SalesOrder`, `Product`) that the module must never delete, and `__module__` is what tells
  the two apart.
* **Foreign-key order.** Walking the list, a child is deleted before its parent unless the
  foreign key would have taken it anyway (`ON DELETE CASCADE`) or would have survived by
  detaching (`ON DELETE SET NULL`). The four `RESTRICT` edges called out in the handler's
  docstring are exactly the ones this catches: get one wrong and the uninstall raises
  half-way through, with the rows it already deleted gone.

The other two tests here cover the ends of the range the behavioural file does not: a core
`purchase_requests` row detaching rather than dying (only the complaint half was covered), and
purge against a database with nothing in it, which is what a tenant who never used the module
actually has.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from app.database import Base
from app.models import projects as projects_models
from app.models import project_so as project_so_models
from app.models.base import set_company_scope
from app.models.procurement import PurchaseRequestHeader
from app.models.projects import Project, ProjectLead
from tests._pg_fixture import blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"

#: The module's model files. Anything owned by `projects` is declared in one of these.
MODEL_MODULES = (projects_models, project_so_models)

#: Foreign keys the database resolves without help, so the delete ORDER cannot break on them.
#: CASCADE takes the child with the parent; SET NULL leaves it behind, detached.
SELF_RESOLVING = frozenset({"CASCADE", "SET NULL"})

#: The frontend's copy of the same list, read by the uninstall dialog. `tests/` sits at
#: <repo>/sorento_crm_backend/tests, so the repo root is two levels up.
FE_PURGE_MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "sorento_crm_frontend" / "modules" / "projects" / "purge_tables.json"
)


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({SORENTO}))
        yield session


def _declared_models() -> list[type]:
    """Every mapped class defined IN the module's model files, not merely imported by them."""
    found: list[type] = []
    for module in MODEL_MODULES:
        for obj in vars(module).values():
            if not inspect.isclass(obj) or not issubclass(obj, Base) or obj is Base:
                continue
            if getattr(obj, "__module__", None) != module.__name__:
                continue
            if not hasattr(obj, "__tablename__"):
                continue
            found.append(obj)
    return found


# --------------------------------------------------------------------------- #
# invariant 1 - completeness
# --------------------------------------------------------------------------- #

def test_every_module_model_is_in_the_purge_order():
    """A new table in the module's model files must be added to PURGE_ORDER too."""
    from app.modules.projects.purge import PURGE_ORDER

    declared = set(_declared_models())
    listed = set(PURGE_ORDER)

    missing = sorted(model.__name__ for model in declared - listed)
    assert not missing, (
        "these module-owned models would survive an uninstall-with-purge: "
        f"{missing}. Add them to PURGE_ORDER in app/modules/projects/purge.py."
    )


def test_the_purge_order_lists_nothing_the_module_does_not_own():
    """The reverse direction: purge must not reach a table declared outside the module."""
    from app.modules.projects.purge import PURGE_ORDER

    declared = set(_declared_models())
    extra = sorted(model.__name__ for model in set(PURGE_ORDER) - declared)
    assert not extra, (
        "PURGE_ORDER names models that are not declared in the projects module's own "
        f"model files, so purge would delete rows it does not own: {extra}"
    )


def test_no_model_is_listed_twice():
    """A duplicate would double-report its count and read as rows that were not there."""
    from app.modules.projects.purge import PURGE_ORDER

    seen: dict[str, int] = {}
    for model in PURGE_ORDER:
        seen[model.__name__] = seen.get(model.__name__, 0) + 1
    duplicated = sorted(name for name, count in seen.items() if count > 1)
    assert not duplicated, f"listed more than once in PURGE_ORDER: {duplicated}"

    # And the count the handler's docstring quotes stays honest.
    assert len(PURGE_ORDER) == len(_declared_models())


# --------------------------------------------------------------------------- #
# the frontend's copy of the list
# --------------------------------------------------------------------------- #

def test_the_frontend_purge_manifest_matches_purge_order_exactly():
    """`modules/projects/purge_tables.json` is what the uninstall dialog SHOWS an operator.

    It is a hand-maintained mirror of `PURGE_ORDER`, and nothing in the frontend build can
    notice when it drifts: the dialog would list a table purge no longer touches, or omit one
    it does, and the operator's consent would be for the wrong set of rows. Order is asserted
    too, because the dialog presents the list as the order of deletion.

    A missing file FAILS rather than skips. "The manifest is gone" is precisely the state this
    test exists to report, and a skip in CI reads as a pass.
    """
    from app.modules.projects.purge import PURGE_ORDER

    assert FE_PURGE_MANIFEST.exists(), (
        f"the frontend purge manifest is missing at {FE_PURGE_MANIFEST}. The uninstall "
        "dialog reads it, so it is part of this feature, not an optional asset."
    )
    manifest = json.loads(FE_PURGE_MANIFEST.read_text())

    assert manifest["moduleKey"] == "projects"
    assert manifest["tables"] == [model.__tablename__ for model in PURGE_ORDER], (
        "the frontend purge manifest and PURGE_ORDER have drifted. Update "
        f"{FE_PURGE_MANIFEST.name} to match app/modules/projects/purge.py, in order."
    )


# --------------------------------------------------------------------------- #
# invariant 2 - children before parents on every load-bearing foreign key
# --------------------------------------------------------------------------- #

def test_children_are_deleted_before_their_parents():
    """Every RESTRICT / NO ACTION edge inside the module points FORWARD in PURGE_ORDER.

    Reported all at once rather than on the first failure: reordering the list tends to
    break several edges together, and one name at a time turns that into a long loop.
    """
    from app.modules.projects.purge import PURGE_ORDER

    position = {model.__tablename__: index for index, model in enumerate(PURGE_ORDER)}

    violations: list[str] = []
    for index, model in enumerate(PURGE_ORDER):
        table = model.__table__
        for constraint in table.foreign_key_constraints:
            target = list(constraint.elements)[0].column.table.name
            if target == table.name or target not in position:
                # Self-references resolve within one statement; targets outside the module
                # are core tables purge never deletes, so their order here is irrelevant.
                continue
            if (constraint.ondelete or "").upper() in SELF_RESOLVING:
                continue
            if index > position[target]:
                violations.append(
                    f"{table.name} (#{index}) has a "
                    f"{constraint.ondelete or 'RESTRICT'} foreign key to {target} "
                    f"(#{position[target]}), so the parent is deleted first and the "
                    "uninstall fails part-way through"
                )

    assert not violations, "PURGE_ORDER is not children-first:\n" + "\n".join(violations)


# --------------------------------------------------------------------------- #
# the other core-to-module foreign key
# --------------------------------------------------------------------------- #

def test_purge_keeps_the_purchase_request_and_nulls_its_project_id(db):
    """`purchase_requests.project_id` detaches; the request itself is a core record.

    The complaint half of this is covered in tests/test_projects_module_purge.py. Both
    exist because ADR-0009 names exactly two core-to-module foreign keys, and a purge that
    took the purchase requests with the project would destroy procurement history for a
    module the tenant merely stopped using.
    """
    from app.modules.projects.purge import purge

    lead = ProjectLead(
        lead_code=unique_code("lead"),
        title="ZZT Purge PR Lead",
        normalised_title=unique_code("zzt purge pr"),
    )
    db.add(lead)
    db.flush()

    project = Project(
        project_code=unique_code("proj"),
        title="ZZT Purge PR Tower",
        normalised_title=unique_code("zzt purge pr tower"),
        lead_id=lead.id,
    )
    db.add(project)
    db.flush()

    request = PurchaseRequestHeader(
        request_type="purchase_request",
        request_number=unique_code("PR"),
        project_id=project.id,
        project_title="ZZT Purge PR Tower",
        customer_name="ZZT Buyer",
        status="submitted",
    )
    db.add(request)
    db.commit()
    request_id = request.id

    purge(db)
    db.commit()
    db.expire_all()

    survivor = (
        db.query(PurchaseRequestHeader)
        .filter(PurchaseRequestHeader.id == request_id)
        .one()
    )
    assert survivor.project_id is None
    # Detached, not emptied: everything typed on the form is still on it.
    assert survivor.project_title == "ZZT Purge PR Tower"
    assert survivor.customer_name == "ZZT Buyer"
    assert survivor.status == "submitted"
    assert db.query(Project).count() == 0


# --------------------------------------------------------------------------- #
# the tenant who never used the module
# --------------------------------------------------------------------------- #

def test_purge_on_an_empty_database_reports_zero_everywhere(db):
    """Uninstalling a module that was never used is a normal thing to do, not an error."""
    from app.modules.projects.purge import PURGE_ORDER, purge

    counts = purge(db)
    db.commit()

    # Every table still reports, at zero. An operator reading the uninstall result needs to
    # see what was CONSIDERED, not only what happened to be there.
    assert counts == {model.__tablename__: 0 for model in PURGE_ORDER}
