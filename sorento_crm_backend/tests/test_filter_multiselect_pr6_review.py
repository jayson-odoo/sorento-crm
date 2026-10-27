"""FILTER-MULTISELECT PR6 review round. Free-text values (agent name, location, project title) ride repeated
params and are read whole: a value containing a comma matches exactly, two values union. A project titled
"Alpha, Beta" never matches projects titled "Alpha" or "Beta". The summary's State counts are taken before the
State filter. Attachments: several companies that are both in the caller's scope. AcknowledgeFilter.location caps
each value, not the whole string. Postgres only; seeded here.
"""
from __future__ import annotations

import pytest

from app.models.base import company_scope
from app.models.project_so import INQUIRY_ACTIONED, INQUIRY_PLACED, INQUIRY_RAISED
from app.models.sales_agent import SalesAgent
from app.schemas.project_order_inquiry import AcknowledgeFilter
from app.services import project_seed_service
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session
from tests.test_oi_multi_filters import HEADERS, LINES, TAG, _order, _sorento, _uid, _user

COMMA_AGENT = "ZZT Smith, John"
COMMA_LOC = "ZZT-LOC, A"
COMMA_TITLE = "ZZT Alpha, Beta"


@pytest.fixture
def world():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        user = _user(db, f"{TAG} u")
        spec = {
            "a": (COMMA_AGENT, COMMA_LOC, COMMA_TITLE, INQUIRY_RAISED),
            "b": ("ZZT Plain", "ZZT-LOC-B", "ZZT Alpha", INQUIRY_ACTIONED),
            "c": ("ZZT Other", "ZZT LOC C", "ZZT Beta", INQUIRY_PLACED),
        }
        orders = {}
        for key, (agent_name, loc, title, state) in spec.items():
            agent = SalesAgent(id=_uid(), company_id=company_id, sales_agent=agent_name)
            db.add(agent)
            db.flush()
            o = _order(db, company_id, user, key, state=state, location=loc, agent=agent, project=None, supplier=None)
            o["project"].title = title
            orders[key] = o
        db.commit()
        yield db, company_id, orders


@pytest.fixture
def client(world, monkeypatch):
    db, company_id, _ = world
    with company_scope(db, frozenset({company_id})):
        with open_client(db, monkeypatch, scope=frozenset({company_id})) as (c, _a):
            yield c


def _headers(client, world, *pairs):
    ours = {x["inquiry"].id: k for k, x in world[2].items()}
    resp = get(client, HEADERS, [("limit", 100), ("state", "all"), *pairs])
    assert resp.status_code == 200, resp.text
    return {ours[r["id"]] for r in resp.json()["data"] if r["id"] in ours}


def _lines(client, world, *pairs):
    ours = {x["row"].id: k for k, x in world[2].items()}
    resp = get(client, LINES, [("limit", 100), *pairs])
    assert resp.status_code == 200, resp.text
    return {ours[r["id"]] for r in resp.json()["data"] if r["id"] in ours}


# ---- 1. headers Agent, 2. lines Location: comma-containing free text -----------------------------------------

def test_headers_agent_with_a_comma_matches_exactly_and_unions(client, world):
    assert _headers(client, world, ("agent", COMMA_AGENT)) == {"a"}
    assert _headers(client, world, ("agent", COMMA_AGENT), ("agent", "ZZT Plain")) == {"a", "b"}


def test_lines_location_with_a_comma_matches_exactly_and_unions(client, world):
    assert _lines(client, world, ("location", COMMA_LOC)) == {"a"}
    assert _lines(client, world, ("location", COMMA_LOC), ("location", "ZZT-LOC-B")) == {"a", "b"}


# ---- 3. headers Project, 4. lines Project ---------------------------------------------------------------------

def test_headers_project_with_a_comma_does_not_match_its_pieces(client, world):
    assert _headers(client, world, ("project", COMMA_TITLE)) == {"a"}
    assert _headers(client, world, ("project", "ZZT Alpha")) == {"b"}
    assert _headers(client, world, ("project", "ZZT Alpha"), ("project", "ZZT Beta")) == {"b", "c"}


def test_lines_project_unions_titles_and_reads_a_comma_title_whole(client, world):
    assert _lines(client, world, ("project", "ZZT Alpha"), ("project", "ZZT Beta")) == {"b", "c"}
    assert _lines(client, world, ("project", COMMA_TITLE)) == {"a"}
    assert _lines(client, world, ("project", COMMA_TITLE), ("project", "ZZT Beta")) == {"a", "c"}


# ---- 5. Summary State counts ignore the State filter ----------------------------------------------------------

def test_summary_state_counts_do_not_change_when_a_state_is_picked(client, world):
    def counts(*pairs):
        by_state = get(client, f"{LINES}/summary", list(pairs)).json()["by_state"]
        return {k: v for k, v in by_state.items() if k != "total"}  # `total` is the filtered row count

    base = counts()
    assert base["raised"] == base["actioned"] == base["placed"] == 1
    assert counts(("state", "raised")) == base
    assert counts(("state", "raised"), ("state", "actioned")) == base


# ---- 7. AcknowledgeFilter.location caps each value ---------------------------------------------------------------

def test_acknowledge_filter_location_caps_each_value_not_the_whole_string():
    a, b = "A" * 150, "B" * 150
    assert AcknowledgeFilter(location=f"{a},{b}").location == f"{a},{b}"
    with pytest.raises(Exception):
        AcknowledgeFilter(location="C" * 201)
