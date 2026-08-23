"""Lines added one at a time keep the order they were added in.

CI failure 32619943876: `test_a_line_that_still_carries_a_typed_letter_keeps_it`
asserted `["A", "2"]` and got `["1", "A"]` - the two lines came back swapped.

Neither ordering key separated them. `sort_order` defaults to 0 and the per-row
`upsert_line` path never assigned one (only `replace_lines` wrote the array
position), and the `created_at` tiebreaker ties as well, because Postgres freezes
`now()` for the whole transaction: rows written in one request share a timestamp
to the microsecond. With both keys equal the order was whatever the plan yielded.

That is a customer-facing bug rather than a test bug - an issued quotation could
renumber its lines between two renders of the same document - so the guarantee is
pinned here rather than left to the assertion in the PDF test that happened to
catch it.
"""
from __future__ import annotations

from sqlalchemy import text

from tests._pg_fixture import blank_session
from app.models.projects import ProjectQuotationLine


def test_postgres_gives_rows_written_in_one_transaction_the_same_now():
    """The premise, stated so a future reader does not have to rediscover it.

    If this ever fails, `created_at` has become a real tiebreaker and the comments
    in `list_lines` are misleading rather than wrong.
    """
    with blank_session() as db:
        db.execute(
            text("create table zz_now (id serial primary key, at timestamp not null default now())")
        )
        db.execute(text("insert into zz_now default values"))
        db.execute(text("insert into zz_now default values"))
        first, second = db.execute(text("select at from zz_now order by id")).scalars().all()

    assert first == second


def _line_order(db, version_id: str) -> list[int]:
    from app.services.project_quotation_service import list_lines

    return [line.sort_order for line in list_lines(db, version_id)]


def test_each_line_added_on_its_own_takes_the_next_position(monkeypatch):
    """The fix: the per-row path assigns a position instead of leaving every line at 0."""
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        from tests.test_project_quotation_pdf import _setup, _product, MARKER
        from app.services import project_quotation_document_service as qdocs

        env = _setup(db)
        owner = env["owner"]
        product = _product(db, env["category"].id, env["uom"], description=f"{MARKER} WC")
        document = qdocs.create_document(db, project=env["project"], actor_user_id=owner)
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
        )
        version = quotes.current_version(db, scope.id)

        for label in ("A", None, "C"):
            quotes.upsert_line(
                db,
                version=version,
                actor_user_id=owner,
                payload={
                    "product_id": product.id,
                    "unit_price": "250.00",
                    "quantity": "1",
                    "item_label": label,
                },
            )

        positions = _line_order(db, version.id)
        labels = [line.item_label for line in quotes.list_lines(db, version.id)]

    # Distinct and ascending: no two lines share a position, so nothing depends on
    # a tiebreaker at all.
    assert positions == sorted(positions)
    assert len(set(positions)) == 3
    assert labels == ["A", None, "C"]


def test_lines_already_stored_at_the_same_position_still_read_back_in_one_order():
    """Legacy rows: written before the fix, they tie on BOTH keys forever.

    Their order cannot be recovered - the information was never stored - but it can
    at least stop moving, which is what the `id` tiebreaker buys. A quotation issued
    to a customer reads the same on every render.
    """
    from app.services.project_quotation_service import list_lines

    with blank_session() as db:
        from tests.test_project_quotation_pdf import _setup, _product, MARKER
        from app.services import project_quotation_document_service as qdocs
        from app.services import project_quotation_service as quotes

        env = _setup(db)
        owner = env["owner"]
        product = _product(db, env["category"].id, env["uom"], description=f"{MARKER} WC")
        document = qdocs.create_document(db, project=env["project"], actor_user_id=owner)
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
        )
        version = quotes.current_version(db, scope.id)
        for label in ("A", "B", "C"):
            quotes.upsert_line(
                db,
                version=version,
                actor_user_id=owner,
                payload={
                    "product_id": product.id,
                    "unit_price": "250.00",
                    "quantity": "1",
                    "item_label": label,
                },
            )
        db.flush()
        # Force the pre-fix shape: every line at 0, sharing one timestamp.
        db.query(ProjectQuotationLine).filter(
            ProjectQuotationLine.version_id == version.id
        ).update({"sort_order": 0}, synchronize_session=False)
        db.execute(
            text(
                "update quotation_lines set created_at = timestamp '2026-01-01 00:00:00' "
                "where version_id = :v"
            ),
            {"v": version.id},
        )
        db.expire_all()

        reads = [[line.id for line in list_lines(db, version.id)] for _ in range(5)]

    assert all(read == reads[0] for read in reads), (
        "legacy lines tied on sort_order and created_at came back in different "
        "orders across reads: the ordering has no total key"
    )
