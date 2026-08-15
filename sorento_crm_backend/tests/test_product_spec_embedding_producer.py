"""The producer for the `product_spec` embedding leg (issue #139).

`enqueue_spec_embedding` has existed since the consumer was built and has never had a
caller, so `embedding_queue` has never held a single `product_spec` row. These tests pin
the producer that closes that: listeners on `ProductSpecifications` that collect the
affected product ids during flush and drain them AFTER the writer's commit.

The drain deliberately opens its own `SessionLocal`, which would otherwise reach the
real database from a test. The `db` fixture points that factory at the same blank-schema
connection the test reads from, so the queue rows the drain writes are the ones the test
asserts on and the outer rollback still discards them. `enqueue_job` is stubbed for the
same reason: `queue_event` enqueues an RQ job inline and Redis is not part of what is
under test here.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

import app.database as app_database
import app.services.embedding_service as embedding_service
import app.services.product_spec_change_listener as listener
import app.tasks.product_spec_tasks as product_spec_tasks
from app.models.base import company_scope
from app.models.company import Company
from app.models.embeddings import EmbeddingQueue
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_change_listener import register_product_spec_listeners
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_write import apply_spec_values
from app.services import queue_service
from tests._pg_fixture import blank_session

_REFS: dict = {}
_ACTOR = {"email": "spec.producer@example.com"}
_UNSET = object()


@pytest.fixture
def db(monkeypatch):
    with blank_session() as s:
        connection = s.get_bind()

        def _session_on_the_blank_schema(**_kwargs):
            return Session(bind=connection, join_transaction_mode="create_savepoint")

        monkeypatch.setattr(app_database, "SessionLocal", _session_on_the_blank_schema)
        monkeypatch.setattr(
            embedding_service, "enqueue_job", lambda *a, **k: SimpleNamespace(id="zzt-job")
        )
        register_product_spec_listeners()
        _fixtures(s)
        yield s


def _fixtures(db) -> None:
    cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-EP-KS", category_name="ZZT-EP-KS")
    # Deliberately unclassified: `backfill_category_signals` leaves a code it cannot map
    # without a class, which is how a product ends up with nothing to say about itself.
    blank = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-EP-NONE", category_name="ZZT-EP-NONE")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-EP-PCS", uom_name="Piece")
    brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-EP-SRT", brand_name="Sorento")
    second = Company(id=str(uuid.uuid4()), name="ZZT EP Second Co", code="ZZT-EP2")
    db.add_all([cat, blank, uom, brand, second])
    db.flush()
    backfill_category_signals(db)
    _REFS.update(
        {
            "cat": cat.id,
            "blank_cat": blank.id,
            "uom": uom.id,
            "brand": brand.id,
            "company2": second.id,
        }
    )


def _product(
    db,
    code: str,
    description: str | None = "SORENTO S/STEEL KITCHEN SINK (1000X500X140MM)",
    *,
    company_id=None,
    category_id: str | None = None,
    brand_id: str | None = _UNSET,
) -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=category_id or _REFS["cat"],
        base_uom_id=_REFS["uom"],
        brand_id=_REFS["brand"] if brand_id is _UNSET else brand_id,
        list_price=Decimal("1.00"),
    )
    if company_id is not None:
        row.company_id = company_id
    db.add(row)
    db.flush()
    return row


def _queued_ids(db) -> list[str]:
    return sorted(
        row.source_id
        for row in db.query(EmbeddingQueue)
        .filter(EmbeddingQueue.source_type == "product_spec")
        .all()
    )


# --------------------------------------------------------------------------- #
# S1 - the producer exists, and it fires after the commit
# --------------------------------------------------------------------------- #
def test_a_derived_write_queues_one_event_per_product_row(db):
    """AC1. The fan-out is per ROW: a code exists once per company and each copy has
    its own spec row, so each carries its own document."""
    with company_scope(db, None):
        first = _product(db, "ZZT-EP-1")
        second = _product(db, "ZZT-EP-1", company_id=_REFS["company2"])
        derive_for_code(db, "ZZT-EP-1")

        assert _queued_ids(db) == [], "nothing may be queued before the writer commits"

        db.commit()

        assert _queued_ids(db) == sorted([first.id, second.id])


def test_an_authored_write_queues_one_event_per_row(db):
    """The second writer. `apply_spec_values` rewrites the sentence on every company
    copy, so every copy's index entry is stale and every one has to be re-queued."""
    _product(db, "ZZT-EP-2")
    derive_for_code(db, "ZZT-EP-2")
    db.commit()
    _drain(db)

    apply_spec_values(
        db,
        "ZZT-EP-2",
        [{"spec_key": "material", "op": "set", "value": "brass"}],
        actor=_ACTOR,
    )
    db.commit()

    product_ids = [p.id for p in db.query(Product).filter(Product.product_code == "ZZT-EP-2").all()]
    assert _queued_ids(db) == sorted(product_ids)


def test_a_second_identical_derivation_queues_nothing(db):
    """AC2, and the whole reason the collect step reads the attribute history.

    `write_spec_row` assigns `rendered_text` unconditionally, so a re-derivation marks
    the row dirty and fires `after_update` even when the sentence it wrote is
    byte-identical. Clearing the fingerprint is what forces that second pass: without
    it `derive_for_code` short-circuits and there is nothing to prove.
    """
    _product(db, "ZZT-EP-3")
    derive_for_code(db, "ZZT-EP-3")
    db.commit()
    _drain(db)

    spec = db.query(ProductSpecifications).join(
        Product, Product.id == ProductSpecifications.product_id
    ).filter(Product.product_code == "ZZT-EP-3").one()
    before = spec.rendered_text
    assert (before or "").strip(), "the fixture must render a sentence or this proves nothing"

    spec.derived_hash = None
    db.flush()
    derive_for_code(db, "ZZT-EP-3")
    db.commit()

    assert spec.rendered_text == before, "the sentence must be unchanged for this test to mean anything"
    assert _queued_ids(db) == [], "an unchanged sentence cannot change the document, so it must not queue"


def test_a_write_that_leaves_the_sentence_alone_queues_nothing(db):
    """The discriminating half of AC2: an UPDATE that genuinely happened, on a row
    whose sentence did not move. A producer that collected every dirty spec row would
    queue here, and it would queue on every provenance-only and status-only pass the
    catalogue takes."""
    _product(db, "ZZT-EP-6")
    derive_for_code(db, "ZZT-EP-6")
    db.commit()
    _drain(db)

    spec = db.query(ProductSpecifications).join(
        Product, Product.id == ProductSpecifications.product_id
    ).filter(Product.product_code == "ZZT-EP-6").one()
    spec.provenance = {**(spec.provenance or {}), "zzt_marker": {"source": "test"}}
    db.commit()

    assert _queued_ids(db) == []


def test_a_rolled_back_write_queues_nothing(db):
    """The drain hangs off `after_commit`, so work that never committed never queues."""
    _product(db, "ZZT-EP-4")
    derive_for_code(db, "ZZT-EP-4")
    db.rollback()

    assert _queued_ids(db) == []


def test_a_spec_row_with_no_sentence_queues_nothing(db):
    """S3. An empty sentence embeds to a vector that sits near everything, so the
    product would surface for every query. `enqueue_spec_embedding` already refuses
    one; this pins that the producer does not route around it."""
    _product(
        db,
        "ZZT-EP-5",
        description=None,
        category_id=_REFS["blank_cat"],
        brand_id=None,
    )
    derive_for_code(db, "ZZT-EP-5")
    db.commit()

    spec = db.query(ProductSpecifications).join(
        Product, Product.id == ProductSpecifications.product_id
    ).filter(Product.product_code == "ZZT-EP-5").one()
    assert not (spec.rendered_text or "").strip(), "the fixture must render nothing or this proves nothing"
    assert _queued_ids(db) == []


# --------------------------------------------------------------------------- #
# S3 - containment. A post-commit side effect that raises would 500 an operation
# that already succeeded, and the retry takes the idempotent path without ever
# backfilling the work it missed.
# --------------------------------------------------------------------------- #
def _three_derived_products(db, stem: str) -> list[str]:
    ids = []
    for index in range(3):
        code = f"ZZT-EP-{stem}-{index}"
        ids.append(_product(db, code).id)
        derive_for_code(db, code)
    return sorted(ids)


def test_a_failing_enqueue_neither_fails_the_commit_nor_loses_the_others(db, monkeypatch):
    """AC3. The write that triggered this has already committed, so the only thing
    left to decide is whether the caller hears about a failure they cannot act on."""
    ids = _three_derived_products(db, "BOOM")
    doomed = ids[0]
    original = embedding_service.EmbeddingEventService.queue_event

    def _boom_for_one(self, *, source_id, **kwargs):
        if source_id == doomed:
            raise RuntimeError("simulated queue_event failure")
        return original(self, source_id=source_id, **kwargs)

    monkeypatch.setattr(embedding_service.EmbeddingEventService, "queue_event", _boom_for_one)

    db.commit()  # must not raise

    assert _queued_ids(db) == ids[1:], "one id failing must not take the rest of the batch with it"


def test_a_half_written_enqueue_is_discarded_rather_than_carried(db, monkeypatch):
    """`queue_event` adds and flushes before it can fail, and the drain reuses one
    session for the batch. Without the rollback between products, that half-finished
    row would be committed by the NEXT product's `queue_event` - a queue row with no
    RQ job behind it, which nothing would ever process or clean up. The doomed id is
    the FIRST in the drain's order so there is a later commit to carry it."""
    ids = _three_derived_products(db, "HALF")
    doomed = ids[0]
    original = embedding_service.EmbeddingEventService.queue_event

    def _flush_then_boom(self, *, source_type, source_id, event_type, **kwargs):
        if source_id == doomed:
            self.db.add(
                EmbeddingQueue(
                    source_type=source_type,
                    source_id=source_id,
                    event_type=event_type,
                    event_version=1,
                    payload={},
                    status="pending",
                )
            )
            self.db.flush()
            raise RuntimeError("simulated failure after the flush")
        return original(
            self, source_type=source_type, source_id=source_id, event_type=event_type, **kwargs
        )

    monkeypatch.setattr(embedding_service.EmbeddingEventService, "queue_event", _flush_then_boom)

    db.commit()

    assert _queued_ids(db) == ids[1:]


# --------------------------------------------------------------------------- #
# S2 - the volume split, mirroring the re-derive twin in
# tests/test_product_spec_change_listener.py
# --------------------------------------------------------------------------- #
def _ids(prefix: str, n: int) -> set[str]:
    return {f"zzt-ep-{prefix}-{i}" for i in range(n)}


def test_above_the_threshold_enqueues_and_skips_the_inline_drain(monkeypatch):
    enqueued: list[list[str]] = []
    inline_calls: list[list[str]] = []
    monkeypatch.setattr(
        listener, "_enqueue_embed", lambda ids: (enqueued.append(sorted(ids)), True)[1]
    )
    monkeypatch.setattr(listener, "embed_products_inline", lambda ids: inline_calls.append(sorted(ids)))

    ids = _ids("ABOVE", listener.INLINE_ENQUEUE_LIMIT + 1)
    listener.embed_products(ids)

    assert len(enqueued) == 1
    assert enqueued[0] == sorted(ids), "the whole batch goes to the worker, not a slice of it"
    assert inline_calls == [], "above the threshold, a successful enqueue must skip the inline drain"


def test_at_the_threshold_drains_inline_without_enqueuing(monkeypatch):
    enqueue_calls: list[int] = []
    inline_calls: list[list[str]] = []
    monkeypatch.setattr(listener, "_enqueue_embed", lambda ids: enqueue_calls.append(1) or True)
    monkeypatch.setattr(listener, "embed_products_inline", lambda ids: inline_calls.append(sorted(ids)))

    listener.embed_products(_ids("AT", listener.INLINE_ENQUEUE_LIMIT))

    assert enqueue_calls == [], "exactly at the limit, one person's edit stays inline"
    assert len(inline_calls) == 1


def test_an_empty_batch_does_nothing(monkeypatch):
    enqueue_calls: list[int] = []
    inline_calls: list[int] = []
    monkeypatch.setattr(listener, "_enqueue_embed", lambda ids: enqueue_calls.append(1) or True)
    monkeypatch.setattr(listener, "embed_products_inline", lambda ids: inline_calls.append(1))

    listener.embed_products(set())

    assert enqueue_calls == []
    assert inline_calls == []


def test_an_unreachable_queue_falls_back_to_inline_and_loses_nothing(monkeypatch):
    """AC4. Dropping the ids would leave those products' index entries stale with
    nothing recording it, so an unreachable queue costs latency, never work."""
    inline_calls: list[list[str]] = []
    monkeypatch.setattr(listener, "_enqueue_embed", lambda ids: False)
    monkeypatch.setattr(listener, "embed_products_inline", lambda ids: inline_calls.append(sorted(ids)))

    ids = _ids("FAIL", listener.INLINE_ENQUEUE_LIMIT + 1)
    listener.embed_products(ids)  # must not raise

    assert len(inline_calls) == 1
    assert inline_calls[0] == sorted(ids), "every id must still be enqueued, not just the first chunk"


def test_enqueue_embed_reports_a_dead_queue_as_false_and_never_raises(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("simulated queue failure")

    monkeypatch.setattr(queue_service, "enqueue_job", _boom)

    assert listener._enqueue_embed({"zzt-ep-boom-1"}) is False


def test_a_batch_above_the_threshold_hands_the_worker_every_changed_row(db, monkeypatch):
    """The split, from a real transaction rather than a hand-made set: 51 spec rows
    written in one commit are handed to the worker whole."""
    handed: list[list[str]] = []
    monkeypatch.setattr(
        listener, "_enqueue_embed", lambda ids: (handed.append(sorted(ids)), True)[1]
    )

    expected = []
    for index in range(listener.INLINE_ENQUEUE_LIMIT + 1):
        code = f"ZZT-EP-BATCH-{index}"
        expected.append(_product(db, code).id)
        derive_for_code(db, code)
    db.commit()

    assert len(handed) == 1
    assert handed[0] == sorted(expected)


# --------------------------------------------------------------------------- #
# S2 - the task the queue path runs
# --------------------------------------------------------------------------- #
def test_the_task_enqueues_in_chunks(monkeypatch):
    """A catalogue-sized batch must not sit in one transaction for its whole run, so
    the task takes a session per chunk. Counting the sessions is how that is visible
    from outside."""
    sessions: list[int] = []
    enqueued: list[str] = []

    class _FakeSession:
        def __enter__(self):
            sessions.append(1)
            return self

        def __exit__(self, *exc):
            return False

        def rollback(self):
            pass

        def info(self):  # pragma: no cover - never read, present for symmetry
            return {}

    monkeypatch.setattr(product_spec_tasks, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(product_spec_tasks, "company_scope", _null_scope)
    monkeypatch.setattr(
        product_spec_tasks, "enqueue_spec_embedding", lambda db, pid: enqueued.append(pid)
    )

    result = product_spec_tasks.enqueue_spec_embeddings(
        [f"zzt-ep-task-{i}" for i in range(10)], chunk_size=4
    )

    assert sessions == [1, 1, 1], "10 ids at a chunk of 4 is three chunks, so three sessions"
    assert len(enqueued) == 10, "chunking must not lose an id"
    assert result["products"] == 10
    assert result["attempted"] == 10


def test_the_task_does_not_let_one_bad_id_lose_the_rest(monkeypatch):
    enqueued: list[str] = []

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def rollback(self):
            pass

    def _one_bad(db, product_id):
        if product_id == "zzt-ep-task-2":
            raise RuntimeError("simulated enqueue failure")
        enqueued.append(product_id)

    monkeypatch.setattr(product_spec_tasks, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(product_spec_tasks, "company_scope", _null_scope)
    monkeypatch.setattr(product_spec_tasks, "enqueue_spec_embedding", _one_bad)

    result = product_spec_tasks.enqueue_spec_embeddings(
        [f"zzt-ep-task-{i}" for i in range(5)], chunk_size=2
    )

    assert len(enqueued) == 4
    assert result["attempted"] == 4
    assert result["failed"] == 1


@contextmanager
def _null_scope(db, value):
    yield


def _drain(db) -> None:
    """Discard whatever the seeding steps queued, so a test asserts on its own event.

    Deleting rather than filtering: the assertions read "these ids and no others",
    which is the point of AC1, and a filtered read could not tell one event from two.
    """
    db.query(EmbeddingQueue).filter(EmbeddingQueue.source_type == "product_spec").delete()
    db.commit()
