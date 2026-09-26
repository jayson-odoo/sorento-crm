"""Phase 3 fix B1: `sales_seed_service.run()` must commit.

`run()` only flushed, and `main.py`'s startup block does `db.close()` (never `db.commit()`)
after calling it - closing a session with an open, uncommitted transaction rolls it back, so
the seeded status graph, lost-reason lookup set and numbering rule never survived the boot
that created them.

Isolated on the blank scratch schema: `blank_session()` joins with `create_savepoint`, so a
`commit()` inside `run()` lands on a savepoint the test can see, and the outer rollback still
discards everything. The first version of this test deleted and re-seeded the REAL shared
graph with committed writes; `sales.opportunities.status_id` is ON DELETE SET NULL, so that
blanked the stage of every opportunity in the database and would race every other sales
test under xdist. Nothing here touches shared rows.

The proof: after `run()`, a `rollback()` of whatever is still open. A committing `run()`
leaves nothing open, so the rows survive; a flush-only `run()` loses them to that rollback.
"""
from __future__ import annotations

from app.models.lookup import LookupSet
from app.models.numbering import DocumentNumberingRule
from app.models.status import Status
from app.services.sales import sales_seed_service as svc
from tests._pg_fixture import blank_session


def test_fix_b1_seed_commits_so_it_survives_a_rollback():
    with blank_session() as db:
        summary = svc.run(db)
        assert summary["opportunity_statuses"] > 0, "a blank schema should have been seeded"

        # What `main.py` effectively does next: the session ends without a commit of its
        # own. Anything `run()` left uncommitted is gone after this.
        db.rollback()

        assert (
            db.query(Status).filter(Status.entity_type == svc.SALES_OPPORTUNITY_ENTITY).count()
            > 0
        ), "the stage graph did not survive the rollback: run() never committed"
        assert (
            db.query(LookupSet).filter(LookupSet.set_key == svc.LOST_REASON_SET_KEY).first()
            is not None
        )
        assert (
            db.query(DocumentNumberingRule)
            .filter(DocumentNumberingRule.doc_type == svc.OPPORTUNITY_NUMBERING["doc_type"])
            .first()
            is not None
        )
