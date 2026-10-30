"""PORTAL-P4-REQUESTS S2 red tests (P4-23): every column of the Complaint list sorts on the server.

`_build_list_query` knows only eight keys; any other column id silently falls back to complaint_date
(left NULL here, so the fallback is id asc). Each case seeds three rows whose requested order is the
REVERSE of their id order, so an ignored sort fails on every case, asc and desc alike.
Column ids are the `accessorKey`s of ComplaintsList.tsx.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.complaints import Complaint
from app.models.download import UserDownload
from app.models.entity_attachment import EntityAttachmentLink
from app.models.resources import Attachment
from app.models.sla import ConversationSLATracking, SLAPolicy
from app.models.user import User
from app.services.complaints_service import ComplaintService
from tests._pg_fixture import pg_session

MARKER = "ZZT-P4CSORT"
COLUMNS = [
    "complaint_number",
    "complaint_type",
    "project_title",
    "handled_by_name",
    "attachments",
    "print_count",
    # sortable today: kept so the contract is the full column set
    "delivery_order_number",
    "customer_name",
    "product_code",
    "salesperson",
    "status",
    "assigned_to",
    "created_at",
]


def _seed(db, direction):
    ids = sorted(str(uuid.uuid4()) for _ in range(3))
    ranks = [3 - i for i in range(3)] if direction == "asc" else [i + 1 for i in range(3)]
    viewer = User(id=str(uuid.uuid4()), email=f"{uuid.uuid4()}@zzt.test", name=f"{MARKER} viewer")
    users = [
        User(id=str(uuid.uuid4()), email=f"{uuid.uuid4()}@zzt.test", name=f"{MARKER} {'aaa bbb ccc'.split()[r - 1]}")
        for r in ranks
    ]
    db.add_all([viewer, *users])
    policy = SLAPolicy(id=str(uuid.uuid4()), code=f"{MARKER}-{uuid.uuid4().hex[:6]}", name=f"{MARKER} policy")
    db.add(policy)
    db.flush()
    base = datetime(2026, 1, 1)
    for i, cid in enumerate(ids):
        rank = ranks[i]
        letter = "xyz"[rank - 1]
        db.add(
            Complaint(
                id=cid,
                complaint_number=f"{MARKER}-{letter}-{uuid.uuid4().hex[:4]}",
                delivery_order_number=f"{MARKER}-DO-{letter}",
                complaint_type=f"{MARKER}-T{letter}",
                project_title=f"{MARKER}-PJ{letter}",
                customer_name=f"{MARKER}-C{letter}",
                product_code=f"{MARKER}-P{letter}",
                salesperson=f"{MARKER}-S{letter}",
                assigned_to=f"{MARKER}-A{letter}",
                status=["new", "rejected", "updated"][rank - 1],
                created_at=base + timedelta(days=rank),
            )
        )
    db.flush()
    for i, cid in enumerate(ids):
        db.add(
            ConversationSLATracking(
                id=str(uuid.uuid4()),
                policy_id=policy.id,
                current_tier=1,
                due_at=datetime.now() + timedelta(days=1),
                source_entity_type="complaint",
                source_entity_id=cid,
                assigned_to_id=users[i].id,
                handled_by_id=users[i].id,
            )
        )
        for _ in range(ranks[i]):
            db.add(
                UserDownload(
                    id=str(uuid.uuid4()),
                    user_id=viewer.id,
                    kind="complaint_pdf",
                    source_entity_type="complaint",
                    source_entity_id=cid,
                    status="ready",
                )
            )
            att = Attachment(
                id=str(uuid.uuid4()),
                original_filename="f.jpg",
                stored_filename="f.jpg",
                file_path="https://cdn.test/f.jpg",
            )
            db.add(att)
            db.flush()
            db.add(EntityAttachmentLink(entity_type="complaint", entity_id=cid, attachment_id=att.id))
    db.flush()
    return ids, viewer.id


@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("column", COLUMNS)
def test_p4_23_complaint_list_sorts_on_every_column(column, direction):
    with pg_session() as db:
        ids, viewer_id = _seed(db, direction)
        out = ComplaintService(db).list_complaints(
            page=1,
            limit=50,
            query=MARKER,
            sort_field=column,
            sort_dir=direction,
            viewer_user_id=viewer_id,
        )
        got = [str(r["id"]) for r in out["data"]]
        assert set(got) == set(ids)
        assert got == list(reversed(ids)), f"sort={column} dir={direction} was ignored or mis-ordered"
