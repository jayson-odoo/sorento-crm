"""`scripts/backfill_spec_embeddings.py` - the first embed for rows that already exist.

The producer (issue #139) only covers spec rows written from now on. The catalogue's
existing rows have never been embedded and never will be by a listener, so the backfill
is a separate one-shot run, and this pins the three properties an operator has to be
able to trust before pointing it at production: a dry run writes nothing, a real run
queues one event per row with something to say, and a second run does nothing for rows
that are already covered.

`embed_products` is stubbed out for the whole file. The listener is registered globally
by whichever test file ran first, and a drain firing on the seed data would put events
in the queue that the script did not put there - which is exactly what these counts are
about.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.services.embedding_service as embedding_service
import app.services.product_spec_change_listener as listener
from app.models.embeddings import EmbeddingDocument, EmbeddingQueue
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications
from tests._pg_fixture import blank_session

import scripts.backfill_spec_embeddings as backfill

_REFS: dict = {}


@pytest.fixture
def db(monkeypatch):
    with blank_session() as s:
        monkeypatch.setattr(
            embedding_service, "enqueue_job", lambda *a, **k: SimpleNamespace(id="zzt-job")
        )
        monkeypatch.setattr(listener, "embed_products", lambda ids: None)
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-BF-KS", category_name="ZZT-BF-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-BF-PCS", uom_name="Piece")
        s.add_all([cat, uom])
        s.flush()
        _REFS.update({"cat": cat.id, "uom": uom.id})
        yield s


def _spec(db, code: str, sentence: str | None) -> ProductSpecifications:
    product = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        list_price=Decimal("1.00"),
    )
    db.add(product)
    db.flush()
    spec = ProductSpecifications(
        id=str(uuid.uuid4()),
        product_id=product.id,
        values={},
        provenance={},
        rendered_text=sentence,
    )
    db.add(spec)
    db.flush()
    return spec


def _queued_ids(db) -> list[str]:
    return sorted(
        row.source_id
        for row in db.query(EmbeddingQueue)
        .filter(EmbeddingQueue.source_type == "product_spec")
        .all()
    )


def test_the_dry_run_is_the_default_and_a_real_run_needs_saying_so():
    """A backfill over 22,805 rows is not something to start by accident, so the flag
    is on the side that writes, not the side that reports."""
    parser = backfill.build_parser()

    assert parser.parse_args([]).apply is False
    assert parser.parse_args(["--apply"]).apply is True


def test_a_dry_run_reports_the_work_and_writes_nothing(db):
    first = _spec(db, "ZZT-BF-1", "A sorento kitchen sink.")
    second = _spec(db, "ZZT-BF-2", "A sorento water closet.")

    result = backfill.run(db, dry_run=True)

    assert result["dry_run"] is True
    assert result["queued"] == 2, "it still has to report the work it would do"
    assert _queued_ids(db) == [], "a dry run must not queue anything"
    # The rows it read are untouched: a report-only run does not roll back the caller's
    # session out from under them either.
    assert sorted(row.id for row in db.query(ProductSpecifications).all()) == sorted(
        [first.id, second.id]
    )


def test_a_real_run_queues_one_event_per_row_with_a_sentence(db):
    first = _spec(db, "ZZT-BF-3", "A sorento kitchen sink.")
    second = _spec(db, "ZZT-BF-4", "A sorento water closet.")
    _spec(db, "ZZT-BF-5", None)
    _spec(db, "ZZT-BF-6", "   ")

    result = backfill.run(db, dry_run=False)

    assert result["scanned"] == 4
    assert result["no_sentence"] == 2, "an empty sentence embeds to a vector near everything"
    assert result["queued"] == 2
    assert _queued_ids(db) == sorted([first.product_id, second.product_id])


def test_a_row_already_waiting_in_the_queue_is_not_queued_twice(db):
    _spec(db, "ZZT-BF-7", "A sorento kitchen sink.")
    backfill.run(db, dry_run=False)

    result = backfill.run(db, dry_run=False)

    assert result["already_queued"] == 1
    assert result["queued"] == 0
    assert len(_queued_ids(db)) == 1, "a resumed run must not re-queue what is still pending"


def test_a_row_the_worker_has_already_embedded_is_left_alone(db):
    spec = _spec(db, "ZZT-BF-8", "A sorento kitchen sink.")
    backfill.run(db, dry_run=False)
    _worker_has_embedded(db, spec)

    result = backfill.run(db, dry_run=False)

    assert result["already_current"] == 1
    assert result["queued"] == 0


def test_a_document_older_than_the_row_is_queued_again(db):
    """The other half of "already current": a document that describes a sentence the
    row has since moved past is exactly what the backfill is for."""
    spec = _spec(db, "ZZT-BF-9", "A sorento kitchen sink.")
    _worker_has_embedded(db, spec, at=_source_time(spec) - timedelta(days=1))

    result = backfill.run(db, dry_run=False)

    assert result["already_current"] == 0
    assert result["queued"] == 1


def test_every_row_is_reached_at_a_batch_of_one(db):
    """The keyset paging, at the size that catches an off-by-one. Paging by OFFSET
    would skip rows here, because each committed enqueue changes what the next page's
    filter matches."""
    codes = ["ZZT-BF-P1", "ZZT-BF-P2", "ZZT-BF-P3"]
    expected = sorted(_spec(db, code, f"A sorento {code}.").product_id for code in codes)

    result = backfill.run(db, dry_run=False, batch_size=1)

    assert result["queued"] == 3
    assert _queued_ids(db) == expected


def test_the_limit_caps_the_run_and_reports_where_it_stopped(db):
    for index in range(3):
        _spec(db, f"ZZT-BF-L{index}", f"A sorento sink {index}.")

    result = backfill.run(db, dry_run=False, limit=2)

    assert result["scanned"] == 2
    assert result["queued"] == 2
    assert result["last_id"] is not None, "a capped run must say where to resume from"
    assert len(_queued_ids(db)) == 2


def test_a_run_resumes_after_the_id_it_is_given(db):
    specs = sorted(
        [_spec(db, f"ZZT-BF-R{index}", f"A sorento sink {index}.") for index in range(3)],
        key=lambda row: row.id,
    )

    result = backfill.run(db, dry_run=False, start_after=specs[0].id)

    assert result["scanned"] == 2
    assert _queued_ids(db) == sorted(row.product_id for row in specs[1:])


def _source_time(spec: ProductSpecifications) -> datetime:
    return spec.updated_at or spec.created_at


def _worker_has_embedded(db, spec: ProductSpecifications, at: datetime | None = None) -> None:
    """Stand in for the embedding worker: the document it writes carries the spec row's
    own timestamp, which is what makes "already current" answerable without re-rendering
    the sentence."""
    db.add(
        EmbeddingDocument(
            id=str(uuid.uuid4()),
            source_type="product_spec",
            source_id=spec.product_id,
            body_text=spec.rendered_text or "",
            source_hash="zzt-hash",
            source_updated_at=at or _source_time(spec),
            is_active=True,
        )
    )
    db.query(EmbeddingQueue).filter(EmbeddingQueue.source_type == "product_spec").delete()
    db.commit()
