"""`app.services.product_spec_flyer_ingest` + the RQ job body (S2, service level).

Plan: `documentation/plans/master-data/PLAN-flyer-spec-ingestion.md` sections 3.2
("Service `product_spec_flyer_ingest.py`") and 3.3 ("Task `flyer_spec_propose_
tasks.py`"). UAC: `flyer-spec-ingestion-acceptance-criteria.md` AC-A.1 (start_
batch half), AC-A.2, AC-A.4, AC-A.5 (the recompute half), AC-C.8.

Written before any of `app.services.product_spec_flyer_ingest`,
`app.tasks.flyer_spec_propose_tasks` or the two new models exist - every import
below fails at collection today, which IS the expected red state.

The job is run INLINE on this file's own rolled-back session, exactly the
`tests/_flyer_read.py` pattern for `read_flyer`: `_enqueue` is patched with a
recorder (AC-A.1's enqueue-seam assertion) and `propose_specs_for_flyer` /
`run_propose` are called directly with `_db=db` / `db` so the whole
start -> job -> assert round trip happens inside one Postgres transaction with
no Redis and no worker process (AC-C.8).

Card text is chosen to reuse tokens already measured against the shipped rule
tables in `tests/test_product_spec_extract_route.py` (same registry, same
`propose_from_text` rule pass) rather than inventing new vocabulary the parser
was never tuned against.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.dealer_kit import FlyerReadingRecord
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import (
    ProductSpecFlyerBatch,
    ProductSpecFlyerProposal,
    ProductSpecifications,
)
from app.services.dealer_kit import flyer_reading_service as dk_svc
from app.services.dealer_kit.flyer_extraction import FlyerCard, FlyerPage, FlyerReading
from app.services.error_handler import AppException
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from app.services.product_spec_write import apply_spec_values
from tests._pg_fixture import blank_session

_REFS: dict = {}
_USER = {"id": str(uuid.uuid4()), "email": "zzt-flyjob@zzt.test"}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-FLYJOB-KS", category_name="ZZT-FLYJOB-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-FLYJOB-PCS", uom_name="Piece")
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-FLYJOB-SRT", brand_name="Sorento")
        s.add_all([cat, uom, brand])
        s.flush()
        backfill_category_signals(s)
        _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id})
        seed_spec_registry(s, commit=False)
        s.flush()
        yield s


def _product(db, code: str, description: str) -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        brand_id=_REFS["brand"],
        list_price=Decimal("1.00"),
    )
    db.add(row)
    db.flush()
    return row


def _card(code: str, *lines: str) -> FlyerCard:
    return FlyerCard(code=code, lines=list(lines), x=0.0, y=0.0)


def _reading(db, *, filename: str = "ZZT Flyer Sample.pdf", cards, status: str = "done") -> FlyerReadingRecord:
    reading = FlyerReading(pages=[FlyerPage(number=1, width=842.0, height=1191.0, cards=list(cards))])
    record = FlyerReadingRecord(
        id=str(uuid.uuid4()),
        filename=filename,
        byte_size=1,
        sha256=uuid.uuid4().hex,
        reading_json=dk_svc.serialise(reading),
        status=status,
    )
    db.add(record)
    db.flush()
    return record


def _batch_row(db, reading, *, status: str = "proposing") -> ProductSpecFlyerBatch:
    row = ProductSpecFlyerBatch(id=str(uuid.uuid4()), flyer_reading_id=reading.id, status=status)
    db.add(row)
    db.flush()
    return row


def _proposals_for(db, batch_id: str) -> list[ProductSpecFlyerProposal]:
    return (
        db.query(ProductSpecFlyerProposal)
        .filter(ProductSpecFlyerProposal.batch_id == batch_id)
        .all()
    )


def _by_product_key(rows: list[ProductSpecFlyerProposal]) -> dict[tuple[str, str], ProductSpecFlyerProposal]:
    return {(row.product_code, row.spec_key): row for row in rows}


# --------------------------------------------------------------------------- #
# AC-A.1 - start_batch: the row, the enqueue seam, and the 409 refusals
# --------------------------------------------------------------------------- #
def test_start_batch_creates_a_proposing_row_and_calls_the_enqueue_seam(db, monkeypatch):
    import app.services.product_spec_flyer_ingest as ingest

    product = _product(db, "ZZT-FLYJOB-START", "SORENTO ONE PIECE WC ZZT-FLYJOB-START")
    reading = _reading(db, cards=[_card("ZZT-FLYJOB-START", "Washdown")])
    db.commit()

    calls = []
    monkeypatch.setattr(
        ingest, "_enqueue", lambda batch: calls.append(str(batch.id)) or "zzt-job-1"
    )

    batch = ingest.start_batch(db, reading, user_id=_USER["id"])

    assert batch.status == "proposing"
    assert batch.flyer_reading_id == reading.id
    assert calls == [str(batch.id)]

    stored = db.query(ProductSpecFlyerBatch).filter_by(id=batch.id).one()
    assert stored.status == "proposing"


def test_start_batch_refuses_409_while_the_reading_is_still_processing(db):
    import app.services.product_spec_flyer_ingest as ingest

    reading = _reading(db, cards=[], status=dk_svc.ReadingStatus.PROCESSING)
    db.commit()

    with pytest.raises(AppException) as excinfo:
        ingest.start_batch(db, reading, user_id=_USER["id"])

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "FLYER_NOT_READ_YET"
    assert "still being read" in excinfo.value.detail["message"].lower()


def test_start_batch_refuses_409_when_the_reading_failed(db):
    import app.services.product_spec_flyer_ingest as ingest

    reading = _reading(db, cards=[], status=dk_svc.ReadingStatus.FAILED)
    db.commit()

    with pytest.raises(AppException) as excinfo:
        ingest.start_batch(db, reading, user_id=_USER["id"])

    assert excinfo.value.status_code == 409
    assert "could not be read" in excinfo.value.detail["message"].lower()


# --------------------------------------------------------------------------- #
# AC-A.2 - the job body: fields, kinds, drops
# --------------------------------------------------------------------------- #
def test_run_propose_writes_a_row_with_value_unit_evidence_kind_and_stored_snapshot(db):
    from app.services.product_spec_flyer_ingest import run_propose

    product = _product(db, "ZZT-FLYJOB-NEW1", "SORENTO ONE PIECE WC ZZT-FLYJOB-NEW1")
    db.commit()
    derive_for_code(db, "ZZT-FLYJOB-NEW1", commit=True)
    reading = _reading(db, cards=[_card("ZZT-FLYJOB-NEW1", "Washdown. S-Trap outlet 250mm")])
    batch = _batch_row(db, reading)
    db.commit()

    run_propose(db, batch.id)

    rows = _by_product_key(_proposals_for(db, batch.id))
    row = rows[("ZZT-FLYJOB-NEW1", "trap_type")]
    assert row.value == "s_trap"
    assert row.kind == "new"
    assert row.stored_value is None
    assert row.stored_source is None
    assert row.evidence  # the printed words, non-empty
    assert row.product_id == product.id
    assert row.pages == [1]


def test_run_propose_stores_an_unchanged_row_rather_than_dropping_it(db):
    """Unlike `extract_spec_proposals` (which drops `unchanged` from its return),
    the STORED batch keeps every kind including `unchanged` - the review screen
    renders it read-only (UAC L4/L10)."""
    from app.services.product_spec_flyer_ingest import run_propose

    _product(db, "ZZT-FLYJOB-UNCH1", "SORENTO ONE PIECE WC (700X400X800MM) ZZT-FLYJOB-UNCH1")
    db.commit()
    derive_for_code(db, "ZZT-FLYJOB-UNCH1", commit=True)
    reading = _reading(db, cards=[_card("ZZT-FLYJOB-UNCH1", "Washdown. H800mm")])
    batch = _batch_row(db, reading)
    db.commit()

    run_propose(db, batch.id)

    rows = _by_product_key(_proposals_for(db, batch.id))
    assert rows[("ZZT-FLYJOB-UNCH1", "dim_height")].kind == "unchanged"


def test_run_propose_marks_a_differing_derived_value_as_change(db):
    """`BLACK` in the description is load-bearing, not decoration.

    It is what derives the stored `finish` the card then disagrees with; without it
    nothing derives a finish at all and the card's `chrome` reads as `new`.
    """
    from app.services.product_spec_flyer_ingest import run_propose

    _product(db, "ZZT-FLYJOB-CHG1", "SORENTO CERAMIC ART BASIN ONLY BLACK ZZT-FLYJOB-CHG1")
    db.commit()
    derive_for_code(db, "ZZT-FLYJOB-CHG1", commit=True)
    reading = _reading(db, cards=[_card("ZZT-FLYJOB-CHG1", "Chrome finish")])
    batch = _batch_row(db, reading)
    db.commit()

    run_propose(db, batch.id)

    row = _by_product_key(_proposals_for(db, batch.id))[("ZZT-FLYJOB-CHG1", "finish")]
    assert row.kind == "change"
    assert row.value == "chrome"
    assert row.stored_value == "black"


def test_run_propose_marks_a_person_authored_value_as_conflict(db):
    from app.services.product_spec_flyer_ingest import run_propose

    _product(db, "ZZT-FLYJOB-CONF1", "SORENTO ONE PIECE WC ZZT-FLYJOB-CONF1")
    db.commit()
    derive_for_code(db, "ZZT-FLYJOB-CONF1", commit=True)
    apply_spec_values(
        db,
        "ZZT-FLYJOB-CONF1",
        [{"spec_key": "seat_material", "op": "set", "value": "uf", "source": "human"}],
        actor=_USER,
    )
    reading = _reading(db, cards=[_card("ZZT-FLYJOB-CONF1", "*PP Seat Cover")])
    batch = _batch_row(db, reading)
    db.commit()

    run_propose(db, batch.id)

    row = _by_product_key(_proposals_for(db, batch.id))[("ZZT-FLYJOB-CONF1", "seat_material")]
    assert row.kind == "conflict"
    assert row.stored_value == "uf"
    assert row.stored_source == "human"


def test_run_propose_marks_a_tombstoned_key_as_suppressed(db):
    from app.services.product_spec_flyer_ingest import run_propose

    _product(db, "ZZT-FLYJOB-SUPP1", "SORENTO ONE PIECE WC ZZT-FLYJOB-SUPP1")
    db.commit()
    derive_for_code(db, "ZZT-FLYJOB-SUPP1", commit=True)
    apply_spec_values(
        db,
        "ZZT-FLYJOB-SUPP1",
        [{"spec_key": "seat_material", "op": "absent", "source": "human"}],
        actor=_USER,
    )
    reading = _reading(db, cards=[_card("ZZT-FLYJOB-SUPP1", "*PP Seat Cover")])
    batch = _batch_row(db, reading)
    db.commit()

    run_propose(db, batch.id)

    row = _by_product_key(_proposals_for(db, batch.id))[("ZZT-FLYJOB-SUPP1", "seat_material")]
    assert row.kind == "suppressed"


def test_run_propose_ignores_an_unmatched_code(db):
    from app.services.product_spec_flyer_ingest import run_propose

    reading = _reading(db, cards=[_card("ZZT-FLYJOB-NOPRODUCT", "Brass Body")])
    batch = _batch_row(db, reading)
    db.commit()

    run_propose(db, batch.id)

    assert _proposals_for(db, batch.id) == []


def test_run_propose_drops_a_code_origin_hit(db):
    """The code ends `-GY` (`code_suffix` -> finish=grey); the description instead
    states golden yellow in words, so the stored, derived finish differs from what
    the code suffix alone would say. The card's text is inert on finish, so any
    finish proposal here can only be the code-origin hit leaking through."""
    _product(db, "ZZT-FLYJOB-CODEGY-GY", "SORENTO BASIN GOLDEN YELLOW ZZT-FLYJOB-CODEGY-GY")
    db.commit()
    derive_for_code(db, "ZZT-FLYJOB-CODEGY-GY", commit=True)
    stored = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == "ZZT-FLYJOB-CODEGY-GY")
        .first()
    )
    assert stored.values["finish"]["value"] == "golden_yellow", "fixture assumption"

    from app.services.product_spec_flyer_ingest import run_propose

    reading = _reading(
        db, cards=[_card("ZZT-FLYJOB-CODEGY-GY", "Two year warranty. Please contact your dealer.")]
    )
    batch = _batch_row(db, reading)
    db.commit()

    run_propose(db, batch.id)

    rows = _by_product_key(_proposals_for(db, batch.id))
    assert ("ZZT-FLYJOB-CODEGY-GY", "finish") not in rows


def test_run_propose_drops_a_key_outside_the_products_class_scope(db):
    """`seat_material` is Water Closet only; this product derives to Tap."""
    _product(db, "ZZT-FLYJOB-TAPSCOPE", "SORENTO BASIN TAP ZZT-FLYJOB-TAPSCOPE")
    db.commit()
    derive_for_code(db, "ZZT-FLYJOB-TAPSCOPE", commit=True)

    from app.services.product_spec_flyer_ingest import run_propose

    reading = _reading(
        db, cards=[_card("ZZT-FLYJOB-TAPSCOPE", "Washdown With Rimless. *PP Seat Cover")]
    )
    batch = _batch_row(db, reading)
    db.commit()

    run_propose(db, batch.id)

    rows = _by_product_key(_proposals_for(db, batch.id))
    assert ("ZZT-FLYJOB-TAPSCOPE", "seat_material") not in rows


def test_run_propose_fills_the_batch_counts_and_stamps_finished(db):
    _product(db, "ZZT-FLYJOB-CNT-NEW", "SORENTO ONE PIECE WC ZZT-FLYJOB-CNT-NEW")
    _product(db, "ZZT-FLYJOB-CNT-CHG", "SORENTO CERAMIC ART BASIN ONLY BLACK ZZT-FLYJOB-CNT-CHG")
    db.commit()
    derive_for_code(db, "ZZT-FLYJOB-CNT-NEW", commit=True)
    derive_for_code(db, "ZZT-FLYJOB-CNT-CHG", commit=True)

    from app.services.product_spec_flyer_ingest import run_propose

    reading = _reading(
        db,
        cards=[
            _card("ZZT-FLYJOB-CNT-NEW", "Washdown. S-Trap outlet 250mm"),
            _card("ZZT-FLYJOB-CNT-CHG", "Chrome finish"),
        ],
    )
    batch = _batch_row(db, reading)
    db.commit()

    run_propose(db, batch.id)
    db.refresh(batch)

    rows = _proposals_for(db, batch.id)
    assert batch.status == "proposed"
    assert batch.finished_at is not None
    assert batch.proposal_count == len(rows)
    assert batch.product_count == len({row.product_id for row in rows})
    assert batch.new_count >= 1
    assert batch.change_count >= 1


# --------------------------------------------------------------------------- #
# AC-A.4 - the job never raises; a broken reading fails the batch
# --------------------------------------------------------------------------- #
def test_run_propose_marks_the_batch_failed_rather_than_raising(db):
    """A malformed `reading_json` breaks `report_for` -> `to_reading` ->
    `deserialise` regardless of how the coder wires the rest of the job, which is
    what makes this failure trigger implementation-agnostic."""
    reading = _reading(db, cards=[])
    reading.reading_json = {"version": 1, "pages": "not-a-list"}
    db.add(reading)
    db.commit()
    batch = _batch_row(db, reading)
    db.commit()

    from app.services.product_spec_flyer_ingest import run_propose

    result = run_propose(db, batch.id)  # must return, never raise

    assert isinstance(result, dict)
    db.refresh(batch)
    assert batch.status == "failed"
    assert batch.error_message


def test_the_task_wrapper_runs_the_job_inline_on_the_test_session(db):
    """`propose_specs_for_flyer(batch_id, _db=db)` - same seam `read_flyer` uses."""
    _product(db, "ZZT-FLYJOB-TASK1", "SORENTO ONE PIECE WC ZZT-FLYJOB-TASK1")
    db.commit()
    derive_for_code(db, "ZZT-FLYJOB-TASK1", commit=True)
    reading = _reading(db, cards=[_card("ZZT-FLYJOB-TASK1", "Washdown. S-Trap outlet 250mm")])
    batch = _batch_row(db, reading)
    db.commit()

    from app.tasks.flyer_spec_propose_tasks import propose_specs_for_flyer

    result = propose_specs_for_flyer(str(batch.id), _db=db)

    assert isinstance(result, dict)
    db.refresh(batch)
    assert batch.status == "proposed"


# --------------------------------------------------------------------------- #
# AC-A.5 - re-propose wipes and recomputes against the master as it is NOW
# --------------------------------------------------------------------------- #
def test_repropose_deletes_old_rows_and_recomputes_against_the_current_master(db):
    from app.services.product_spec_flyer_ingest import run_propose

    _product(db, "ZZT-FLYJOB-REPRO", "SORENTO CERAMIC ART BASIN ONLY BLACK ZZT-FLYJOB-REPRO")
    db.commit()
    derive_for_code(db, "ZZT-FLYJOB-REPRO", commit=True)
    reading = _reading(db, cards=[_card("ZZT-FLYJOB-REPRO", "Chrome finish")])
    batch = _batch_row(db, reading)
    db.commit()

    run_propose(db, batch.id)
    first_ids = {row.id for row in _proposals_for(db, batch.id)}
    first_row = _by_product_key(_proposals_for(db, batch.id))[("ZZT-FLYJOB-REPRO", "finish")]
    assert first_row.kind == "change"

    # The master moves: a person accepts chrome by hand before the re-propose.
    apply_spec_values(
        db,
        "ZZT-FLYJOB-REPRO",
        [{"spec_key": "finish", "op": "set", "value": "chrome", "source": "human"}],
        actor=_USER,
    )

    batch.status = "proposing"
    db.add(batch)
    db.commit()

    run_propose(db, batch.id)

    second_rows = _proposals_for(db, batch.id)
    second_ids = {row.id for row in second_rows}
    assert first_ids.isdisjoint(second_ids), "the old rows must be gone, not accumulated"
    second_row = _by_product_key(second_rows)[("ZZT-FLYJOB-REPRO", "finish")]
    # The master now already says chrome, so a fresh pass reads it as unchanged
    # rather than the stale `change` the first pass computed.
    assert second_row.kind == "unchanged"


# --------------------------------------------------------------------------- #
# Company scope - a batch belongs to the company whose flyer it was read from
# --------------------------------------------------------------------------- #
def test_a_batch_is_only_visible_under_its_own_companys_scope(db):
    """`list_batches` / `batch_for` are read under a REAL scope here, not an open one.

    The four route tests override `apply_company_scope` to a no-op (they are about the
    HTTP surface), so nothing else in this slice ever runs these two reads with a company
    filter attached - and `product_spec_flyer_batches` is an owned table, so a batch read
    from one company's flyer must not appear in another company's list. This seeds the
    reading and the batch under the incumbent company and then asks for them twice, from
    each side of the fence.
    """
    from app.models.base import company_scope
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from app.services.product_spec_flyer_ingest import batch_for, list_batches

    _product(db, "ZZT-FLYJOB-SCOPE", "SORENTO ONE PIECE WC ZZT-FLYJOB-SCOPE")
    reading = _reading(db, cards=[_card("ZZT-FLYJOB-SCOPE", "Washdown. S-Trap outlet 250mm")])
    batch = _batch_row(db, reading, status="proposed")
    db.commit()

    # Seeded under the suite's default scope, which is the incumbent company: the
    # auto-stamp is what puts the company on both rows, exactly as a real propose does.
    assert reading.company_id == DEFAULT_COMPANY_ID
    assert batch.company_id == DEFAULT_COMPANY_ID

    other = Company(
        id=str(uuid.uuid4()),
        name=f"ZZT Company B {uuid.uuid4().hex[:8]}",
        code=f"ZB{uuid.uuid4().hex[:6]}",
    )
    db.add(other)
    db.flush()

    with company_scope(db, frozenset({DEFAULT_COMPANY_ID})):
        mine = list_batches(db)
        assert [str(row.id) for row, _reading_row in mine] == [str(batch.id)]
        assert batch_for(db, reading) is not None

    db.expire_all()

    with company_scope(db, frozenset({other.id})):
        theirs = list_batches(db)
        assert [str(row.id) for row, _reading_row in theirs] == []
        assert batch_for(db, reading) is None
