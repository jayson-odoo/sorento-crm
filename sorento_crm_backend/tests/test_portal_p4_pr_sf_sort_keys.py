"""PORTAL-P4-REQUESTS S3 red tests (P4-23): every column of the Purchase Request and Sponsorship Form list sorts.

`_build_request_list_query` knows only submitted_at, request_date, created_at, customer_name and project_title;
any other key (status, request_number, revision_no, purpose, sponsor_subject, sales_type, requested_by,
assigned_to_name, handled_by_name) silently sorts by submitted_at. Each case seeds three headers whose requested
order is the REVERSE of their id order, with submitted_at NULL (so an ignored sort falls back to the id
tie-break, id asc) - a sort that is ignored therefore fails on every case, asc and desc alike. The column ids are
the ones PurchaseRequestsList.tsx sends as `sort` (status is the column id of approval_status).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.procurement import PurchaseRequestHeader
from app.models.sla import ConversationSLATracking, SLAPolicy
from app.models.user import User
from app.services.procurement_service import PurchaseRequestService
from tests._pg_fixture import pg_session

MARKER = "ZZT-P4PRSORT"
COMMON = [
    "request_number",
    "revision_no",
    "status",
    "sales_type",
    "requested_by",
    "assigned_to_name",
    "handled_by_name",
    # already sortable today: kept so the contract is the full column set
    "submitted_at",
    "created_at",
    "customer_name",
    "project_title",
]
CASES = [("purchase_request", c) for c in COMMON + ["purpose"]] + [
    ("sponsorship_form", c) for c in COMMON + ["sponsor_subject"]
]
APPROVAL = {1: "approved", 2: "pending", 3: "rejected"}
WORD = {1: "aaa", 2: "bbb", 3: "ccc"}


def _seed(db, kind, column, direction):
    ids = sorted(str(uuid.uuid4()) for _ in range(3))
    ranks = [3 - i for i in range(3)] if direction == "asc" else [i + 1 for i in range(3)]
    users = [
        User(id=str(uuid.uuid4()), email=f"{uuid.uuid4()}@zzt.test", name=f"{MARKER} {WORD[r]}") for r in ranks
    ]
    db.add_all(users)
    policy = SLAPolicy(id=str(uuid.uuid4()), code=f"{MARKER}-{uuid.uuid4().hex[:6]}", name=f"{MARKER} policy")
    db.add(policy)
    db.flush()
    base = datetime(2026, 1, 1)
    for i, hid in enumerate(ids):
        r = ranks[i]
        db.add(
            PurchaseRequestHeader(
                id=hid,
                request_type=kind,
                request_number=f"{MARKER}-{WORD[r]}-{uuid.uuid4().hex[:4]}",
                customer_name=f"{MARKER} cust {WORD[r]}",
                project_title=f"{MARKER} proj {WORD[r]}",
                purpose=f"{MARKER} purpose {WORD[r]}",
                sponsor_subject=f"{WORD[r]} subject",
                sales_type=["cash_sales", "dealer", "project"][r - 1],
                requested_by=f"{MARKER} by {WORD[r]}",
                status="submitted",
                approval_status=APPROVAL[r],
                revision_no=r,
                created_at=base + timedelta(days=r),
                submitted_at=(base + timedelta(days=r)) if column == "submitted_at" else None,
            )
        )
    db.flush()
    for i, hid in enumerate(ids):
        db.add(
            ConversationSLATracking(
                id=str(uuid.uuid4()),
                policy_id=policy.id,
                current_tier=1,
                due_at=datetime.now() + timedelta(days=1),
                source_entity_type=kind,
                source_entity_id=hid,
                assigned_to_id=users[i].id,
                handled_by_id=users[i].id,
            )
        )
    db.flush()
    return ids


@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("kind,column", CASES)
def test_p4_23_pr_sf_list_sorts_on_every_column(kind, column, direction):
    with pg_session() as db:
        ids = _seed(db, kind, column, direction)
        out = PurchaseRequestService(db).list_requests(
            page=1,
            limit=50,
            query=MARKER,
            request_type=kind,
            sort_field=column,
            sort_dir=direction,
        )
        got = [str(r.id) for r in out["data"]]
        assert set(got) == set(ids)
        expected = list(reversed(ids))  # the fallback (submitted_at tie, id asc) would be `ids`
        assert got == expected, f"sort={column} dir={direction} kind={kind} was ignored or mis-ordered"
