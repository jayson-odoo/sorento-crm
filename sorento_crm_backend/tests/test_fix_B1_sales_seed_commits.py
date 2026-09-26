"""Phase 3 fix B1: `sales_seed_service.run()` must commit.

`run()` only flushed, and `main.py`'s startup block does `db.close()` (never `db.commit()`)
after calling it - closing a session with an open, uncommitted transaction rolls it back, so
the seeded status graph, lost-reason lookup set and numbering rule never survive the request
that created them. A SECOND session (any other request, or the next boot) sees nothing.

This clears any pre-existing seed for the entity first (committed on a throwaway session), so
`run()`'s own wholesale guard cannot short-circuit into "already seeded" and mask the bug, then
proves a session that never called `run()` itself can see the rows it produced. Cleans up after
itself: the app reseeds these additively on its own next boot, so removing them here is safe.
"""
from __future__ import annotations

from app.database import SessionLocal
from app.models.lookup import LookupOption, LookupSet
from app.models.numbering import DocumentNumberingRule
from app.models.status import Status, StatusTransition
from app.services.sales import sales_seed_service as svc


def _clear_seed(db):
    db.query(StatusTransition).filter(
        StatusTransition.entity_type == svc.SALES_OPPORTUNITY_ENTITY
    ).delete()
    db.query(Status).filter(Status.entity_type == svc.SALES_OPPORTUNITY_ENTITY).delete()
    lost_set = db.query(LookupSet).filter(LookupSet.set_key == svc.LOST_REASON_SET_KEY).first()
    if lost_set:
        db.query(LookupOption).filter(LookupOption.set_id == lost_set.id).delete()
        db.query(LookupSet).filter(LookupSet.id == lost_set.id).delete()
    db.query(DocumentNumberingRule).filter(
        DocumentNumberingRule.doc_type == svc.OPPORTUNITY_NUMBERING["doc_type"]
    ).delete()
    db.commit()


def test_fix_b1_seed_commits_so_a_second_session_sees_the_rows():
    setup_db = SessionLocal()
    try:
        _clear_seed(setup_db)
    finally:
        setup_db.close()

    seeding_db = SessionLocal()
    try:
        summary = svc.run(seeding_db)
        assert summary["opportunity_statuses"] > 0, "run() should have re-seeded the cleared graph"
    finally:
        # Closing here is the exact failure mode: a session closed with an uncommitted
        # transaction rolls it back. If `run()` committed, this close is a no-op on the
        # already-durable rows.
        seeding_db.close()

    verifying_db = SessionLocal()
    try:
        count = (
            verifying_db.query(Status)
            .filter(Status.entity_type == svc.SALES_OPPORTUNITY_ENTITY)
            .count()
        )
        assert count > 0, (
            "a second session should see the graph seeded by run() on the first - "
            "it does not, which means run() never committed"
        )
        lost_reasons_visible = (
            verifying_db.query(LookupSet)
            .filter(LookupSet.set_key == svc.LOST_REASON_SET_KEY)
            .first()
        )
        assert lost_reasons_visible is not None
        numbering_visible = (
            verifying_db.query(DocumentNumberingRule)
            .filter(DocumentNumberingRule.doc_type == svc.OPPORTUNITY_NUMBERING["doc_type"])
            .first()
        )
        assert numbering_visible is not None
    finally:
        _clear_seed(verifying_db)
        verifying_db.close()
