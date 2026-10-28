"""FILTER-MULTISELECT PR3: Complaints (Status, Assigned to), Tickets (Status, Priority, Category, Source)
and Campaigns (Status) take several values (OR within a filter, AND across). Complaints' Assigned to
keeps its `__unassigned__` pseudo-value, which OR-combines with a real assignee. Complaints root cause
and resolution are already multi (one guard). Red first; Postgres only; rows seeded here.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.complaints import Complaint
from app.models.marketing import CampaignType, MarketingCampaign
from app.models.tickets import Ticket
from app.services.user_service import UserPermissionService
from tests._multi_filter_client import get, ok_ids, open_client
from tests._pg_fixture import blank_session, unique_code

COMPLAINTS = "/api/v1/complaints-management/complaints/"
TICKETS = "/api/v1/tickets-management/tickets"
CAMPAIGNS = "/api/v1/marketing/campaigns/"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"admin"})
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _ids(s, *keys):
    return {s[k].id for k in keys}


# ---- Complaints ---------------------------------------------------------------------------------------

def _complaint(db, tag, label, status, assignee):
    row = Complaint(id=str(uuid.uuid4()), complaint_number=f"{tag}-{label}", status=status, assigned_to=assignee,
                    complaint_date=date(2026, 6, 1))
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def complaints(db):
    tag = unique_code("CP", alpha=True)
    return dict(
        tag=tag,
        r1=_complaint(db, tag, "1", "new", "resp-a"), r2=_complaint(db, tag, "2", "in_progress", "resp-b"),
        r3=_complaint(db, tag, "3", "resolved", None), r4=_complaint(db, tag, "4", "new", "resp-b"),
    )


def _cp(client, s, pairs):
    resp = get(client, COMPLAINTS, [("limit", 200), ("query", s["tag"]), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


def test_complaint_status_union_single_and_repeated(client, complaints):
    s = complaints
    assert _cp(client, s, [("status", "new,resolved")]) == _ids(s, "r1", "r3", "r4")
    assert _cp(client, s, [("status", "in_progress")]) == _ids(s, "r2")
    assert _cp(client, s, [("status", "in_progress"), ("status", "resolved")]) == _ids(s, "r2", "r3")


def test_complaint_assignee_union_single_and_repeated(client, complaints):
    s = complaints
    assert _cp(client, s, [("assigned_to", "resp-a,resp-b")]) == _ids(s, "r1", "r2", "r4")
    assert _cp(client, s, [("assigned_to", "resp-a")]) == _ids(s, "r1")
    assert _cp(client, s, [("assigned_to", "resp-a"), ("assigned_to", "resp-b")]) == _ids(s, "r1", "r2", "r4")


def test_complaint_unassigned_pseudo_value_or_combines_with_a_real_assignee(client, complaints):
    s = complaints
    assert _cp(client, s, [("assigned_to", "__unassigned__")]) == _ids(s, "r3")
    assert _cp(client, s, [("assigned_to", "__unassigned__,resp-a")]) == _ids(s, "r3", "r1")


def test_complaint_filters_and_across_each_other(client, complaints):
    s = complaints
    got = _cp(client, s, [("status", "new,resolved"), ("assigned_to", "__unassigned__,resp-b")])
    assert got == _ids(s, "r3", "r4")


def test_complaint_root_cause_already_takes_several_ids(client, complaints):
    s = complaints
    resp = get(client, COMPLAINTS, [("query", s["tag"]), ("root_cause_ids", f"{uuid.uuid4()},{uuid.uuid4()}")])
    assert resp.status_code == 200, resp.text


# ---- Tickets ------------------------------------------------------------------------------------------

def _ticket(db, tag, label, status, priority, category, source):
    row = Ticket(id=str(uuid.uuid4()), ticket_number=f"{tag}-{label}", title=f"ZZT {tag} {label}", status=status,
                 priority=priority, category=category, source_channel=source, raised_by_kind="user")
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def tickets(db):
    tag = unique_code("TK", alpha=True)
    return dict(
        tag=tag,
        r1=_ticket(db, tag, "1", "draft", "high", "question", "manual"),
        r2=_ticket(db, tag, "2", "open", "low", "bug", "ai_assistant"),
        r3=_ticket(db, tag, "3", "closed", "medium", "request", "whatsapp_respond"),
        r4=_ticket(db, tag, "4", "open", "high", "bug", "manual"),
    )


def _tk(client, s, pairs):
    resp = get(client, TICKETS, [("limit", 200), ("q", s["tag"]), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


@pytest.mark.parametrize("param,union,expect,single,single_expect", [
    ("status", "draft,closed", ("r1", "r3"), "open", ("r2", "r4")),
    ("priority", "high,low", ("r1", "r2", "r4"), "medium", ("r3",)),
    ("category", "question,request", ("r1", "r3"), "bug", ("r2", "r4")),
    ("source_channel", "ai_assistant,whatsapp_respond", ("r2", "r3"), "manual", ("r1", "r4")),
])
def test_ticket_filters_union_single_and_repeated(client, tickets, param, union, expect, single, single_expect):
    s = tickets
    assert _tk(client, s, [(param, union)]) == _ids(s, *expect)
    assert _tk(client, s, [(param, single)]) == _ids(s, *single_expect)
    a, b = union.split(",")
    assert _tk(client, s, [(param, a), (param, b)]) == _ids(s, *expect)


def test_ticket_filters_and_across_each_other(client, tickets):
    s = tickets
    got = _tk(client, s, [("status", "open,closed"), ("priority", "high,medium"), ("category", "bug,request")])
    assert got == _ids(s, "r3", "r4")


# ---- Campaigns ----------------------------------------------------------------------------------------

@pytest.fixture
def campaigns(db):
    ctype = CampaignType(id=str(uuid.uuid4()), type_code=unique_code("ct"), type_name="ZZT type")
    db.add(ctype)
    db.flush()
    out = {}
    for key, status in (("r1", "planning"), ("r2", "active"), ("r3", "completed"), ("r4", "active")):
        row = MarketingCampaign(id=str(uuid.uuid4()), campaign_code=unique_code("cm"), campaign_name=f"ZZT {key}",
                                campaign_type_id=ctype.id, start_date=date(2026, 6, 1), status=status)
        db.add(row)
        db.flush()
        out[key] = row
    return out


def _cm(client, pairs):
    return ok_ids(get(client, CAMPAIGNS, [("limit", 200), *pairs]))


def test_campaign_status_union_single_and_repeated(client, campaigns):
    s = campaigns
    assert _cm(client, [("status", "planning,completed")]) == _ids(s, "r1", "r3")
    assert _cm(client, [("status", "active")]) == _ids(s, "r2", "r4")
    assert _cm(client, [("status", "planning"), ("status", "completed")]) == _ids(s, "r1", "r3")


def test_campaign_status_stays_case_insensitive_and_all_means_everything(client, campaigns):
    s = campaigns
    assert _cm(client, [("status", "Planning,ACTIVE")]) == _ids(s, "r1", "r2", "r4")
    assert _cm(client, [("status", "all")]) >= _ids(s, "r1", "r2", "r3", "r4")
