"""`sales_agent_service` ownership-group helpers - PLAN-demo-followups-19aug-ladder-v2.md C3.

`agents_for_group` (who is in an ownership group) and `group_of_warehouse_code` (which group a
warehouse code names) are pure reads the ladder (workstream E) will build the borrow-donor
surfacing on. Postgres only, via `blank_session`, `ZZT`-marked rows.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.sales_agent import SalesAgent
from app.services.scm import sales_agent_service as svc
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _seed(db, code: str, **kwargs) -> SalesAgent:
    row = SalesAgent(id=str(uuid.uuid4()), sales_agent=code, source="manual", **kwargs)
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------------- #
# group_of_warehouse_code
# --------------------------------------------------------------------------- #

def test_the_suffix_after_the_first_hyphen_is_the_group():
    assert svc.group_of_warehouse_code("BRW-BB") == "BB"
    assert svc.group_of_warehouse_code("MWH-BB") == "BB"
    assert svc.group_of_warehouse_code("DC1-HP") == "HP"


def test_only_the_first_hyphen_splits_a_multi_hyphen_code():
    assert svc.group_of_warehouse_code("BRW-BB-RSV") == "BB-RSV"


def test_a_plain_site_code_has_no_group():
    """A pool code (`BRW`, `MWH`, ...) carries no ownership group - it is a pool, not
    anyone's stock."""
    assert svc.group_of_warehouse_code("BRW") is None
    assert svc.group_of_warehouse_code("") is None
    assert svc.group_of_warehouse_code(None) is None


def test_the_group_is_upper_cased():
    assert svc.group_of_warehouse_code("brw-bb") == "BB"


# --------------------------------------------------------------------------- #
# agents_for_group
# --------------------------------------------------------------------------- #

def test_agents_for_group_finds_every_matching_agent(db):
    a = _seed(db, unique_code("TERA"), location_group="BB")
    b = _seed(db, unique_code("JEREMY"), location_group="BB")
    other = _seed(db, unique_code("SEAN"), location_group="HP")

    found = {agent.id for agent in svc.agents_for_group(db, "BB")}
    assert found == {a.id, b.id}
    assert other.id not in found


def test_agents_for_group_is_normalised(db):
    agent = _seed(db, unique_code("CINDY"), location_group="BB")

    found = {a.id for a in svc.agents_for_group(db, "  bb  ")}
    assert agent.id in found


def test_agents_for_group_of_none_or_blank_is_empty(db):
    _seed(db, unique_code("UNGROUPED"))  # location_group stays NULL

    assert svc.agents_for_group(db, None) == []
    assert svc.agents_for_group(db, "   ") == []


def test_agents_for_group_ignores_ungrouped_agents(db):
    _seed(db, unique_code("NOGROUP"))

    assert svc.agents_for_group(db, "BB") == []


# --------------------------------------------------------------------------- #
# normalize_location_group
# --------------------------------------------------------------------------- #

def test_normalize_location_group_trims_and_upper_cases():
    assert svc.normalize_location_group("  bb  ") == "BB"
    assert svc.normalize_location_group("") is None
    assert svc.normalize_location_group(None) is None
