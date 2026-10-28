"""PORTAL-P4-REQUESTS S1 red tests (P4-23): every column of the Stock Inquiry list sorts on the server.

Today `_build_list_query` knows only part of the columns and an unknown key silently falls back to
created_at, so the four columns the grid left unsortable (revision_no, assigned_to_name,
handled_by_name, print_count) return the fallback order. Each case seeds three rows whose requested
order is the REVERSE of their id order (created_at ties inside one transaction, so the fallback is
id asc) - a sort that is ignored therefore fails on every case, asc and desc alike.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.download import UserDownload
from app.models.procurement import StockInquiry
from app.models.sla import ConversationSLATracking, SLAPolicy
from app.models.user import User
from app.services.procurement_service import StockInquiryService
from tests._pg_fixture import pg_session

MARKER = "ZZT-P4SORT"
COLUMNS = [
    "revision_no",
    "assigned_to_name",
    "handled_by_name",
    "print_count",
    # already sortable today: kept in the matrix so the contract is the full column set
    "inquiry_number",
    "product_code",
    "status",
    "quantity",
]


def _seed(db, direction):
    """Three inquiries, ids ascending; column ranks run against the id order in the requested direction."""
    ids = sorted(str(uuid.uuid4()) for _ in range(3))
    viewer = User(id=str(uuid.uuid4()), email=f"{uuid.uuid4()}@zzt.test", name=f"{MARKER} viewer")
    # rank 1..3 per row: asc wants the id-last row first, desc wants the id-last row last
    ranks = [3 - i for i in range(3)] if direction == "asc" else [i + 1 for i in range(3)]
    users = [
        User(id=str(uuid.uuid4()), email=f"{uuid.uuid4()}@zzt.test", name=f"{MARKER} {'aaa bbb ccc'.split()[r - 1]}")
        for r in ranks
    ]
    db.add_all([viewer, *users])
    policy = SLAPolicy(id=str(uuid.uuid4()), code=f"{MARKER}-{uuid.uuid4().hex[:6]}", name=f"{MARKER} policy")
    db.add(policy)
    db.flush()
    rows = []
    for i, sid in enumerate(ids):
        rank = ranks[i]
        letter = "xyz"[rank - 1]
        row = StockInquiry(
            id=sid,
            inquiry_number=f"{MARKER}-{letter}-{uuid.uuid4().hex[:4]}",
            product_code=f"{MARKER}-P{letter}",
            status=["new", "rejected", "updated"][rank - 1],
            quantity=str(rank),
            revision_no=rank,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    for i, row in enumerate(rows):
        db.add(
            ConversationSLATracking(
                id=str(uuid.uuid4()),
                policy_id=policy.id,
                current_tier=1,
                due_at=datetime.now() + timedelta(days=1),
                source_entity_type="stock_inquiry",
                source_entity_id=row.id,
                assigned_to_id=users[i].id,
                handled_by_id=users[i].id,
            )
        )
        for _ in range(ranks[i]):            # rank downloads by the viewer
            db.add(
                UserDownload(
                    id=str(uuid.uuid4()),
                    user_id=viewer.id,
                    kind="stock_inquiry_pdf",
                    source_entity_type="stock_inquiry",
                    source_entity_id=row.id,
                    status="ready",
                )
            )
    db.flush()
    return ids, viewer.id


@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("column", COLUMNS)
def test_p4_23_list_sorts_on_every_column(column, direction):
    with pg_session() as db:
        ids, viewer_id = _seed(db, direction)
        out = StockInquiryService(db).list_inquiries(
            page=1,
            limit=50,
            query=MARKER,
            sort_field=column,
            sort_dir=direction,
            viewer_user_id=viewer_id,
        )
        got = [str(r.id) for r in out["data"]]
        assert set(got) == set(ids)
        expected = list(reversed(ids))  # the fallback (created_at tie, id asc) would be `ids`
        assert got == expected, f"sort={column} dir={direction} was ignored or mis-ordered"
