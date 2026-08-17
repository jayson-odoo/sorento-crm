"""The four flyer-spec-proposal routes (S2, HTTP level).

Plan: `documentation/plans/master-data/PLAN-flyer-spec-ingestion.md` section 3.4.
UAC: `flyer-spec-ingestion-acceptance-criteria.md` AC-A.1, AC-A.5, AC-A.7, AC-B.1,
AC-B.2, AC-C.1 through AC-C.7.

None of the four routes exist yet (`app/api/v1/dealer_kit/flyer_spec_proposals.py`
is not written and not mounted), so every request below 404s today - that IS the
expected red state, mirroring `tests/test_product_spec_batch_apply_route.py` and
`tests/test_product_spec_extract_route.py`.

Fixture/dependency-override pattern copied from those two files: bare
`TestClient(app)` (no `with`, so the app's startup event and its company-scope
listeners never register - the same reason those two files need no company-scope
plumbing), `get_db` / `get_current_user` / `get_current_user_or_api_key` /
`apply_company_scope` overridden, `UserPermissionService.check_user_has_
permission` monkeypatched against an `allow` set. The two routes' own permission
dependencies (`require_permission`, not `_with_api_key` - see `apply_flyer_
dimensions` for the precedent AC-A.7/L9 names) resolve through `get_current_
user`, so that is the one overridden for the 401 case, not `_or_api_key`.

C.1-C.7 (apply) build the batch and its proposal rows DIRECTLY rather than
running the propose job first: apply operates on whatever rows are stored,
regardless of how they got there, and seeding them directly keeps each test
about the apply behaviour alone (PRINCIPLES.md: seed your own chain).
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
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from tests._pg_fixture import blank_session

_REFS: dict = {}
_USER = {"id": str(uuid.uuid4()), "email": "zzt-flyroutes@zzt.test"}

_VIEW = "dealer_kit.page.view"
_EDIT = "master_data.products.edit"

_PROPOSE = "/api/v1/dealer-kit/flyer-readings/{}/spec-proposals"
_GET_PROPOSALS = "/api/v1/dealer-kit/flyer-readings/{}/spec-proposals"
_APPLY = "/api/v1/dealer-kit/flyer-readings/{}/spec-proposals/apply"
_LIST_BATCHES = "/api/v1/dealer-kit/flyer-readings/spec-proposal-batches"


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-FLYRT-KS", category_name="ZZT-FLYRT-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-FLYRT-PCS", uom_name="Piece")
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-FLYRT-SRT", brand_name="Sorento")
        s.add_all([cat, uom, brand])
        s.flush()
        backfill_category_signals(s)
        _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id})
        seed_spec_registry(s, commit=False)
        s.flush()
        yield s


@pytest.fixture
def api(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER
    app.dependency_overrides[apply_company_scope] = lambda: None
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client, allow
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_or_api_key, None)
        app.dependency_overrides.pop(apply_company_scope, None)


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


def _reading(db, *, filename: str = "ZZT Flyer Sample.pdf", cards=(), status: str = "done") -> FlyerReadingRecord:
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


def _batch(db, reading, *, status: str = "proposed", **extra) -> ProductSpecFlyerBatch:
    row = ProductSpecFlyerBatch(id=str(uuid.uuid4()), flyer_reading_id=reading.id, status=status, **extra)
    db.add(row)
    db.flush()
    return row


def _proposal(
    db,
    batch,
    product,
    *,
    spec_key: str,
    value,
    kind: str,
    unit=None,
    evidence: str = "printed words",
    stored_value=None,
    stored_unit=None,
    stored_source=None,
    pages=(1,),
) -> ProductSpecFlyerProposal:
    row = ProductSpecFlyerProposal(
        id=str(uuid.uuid4()),
        batch_id=batch.id,
        product_id=product.id,
        product_code=product.product_code,
        pages=list(pages),
        spec_key=spec_key,
        value=value,
        unit=unit,
        evidence=evidence,
        kind=kind,
        stored_value=stored_value,
        stored_unit=stored_unit,
        stored_source=stored_source,
    )
    db.add(row)
    db.flush()
    return row


def _spec_of(db, product_id: str) -> ProductSpecifications | None:
    db.expire_all()
    return (
        db.query(ProductSpecifications)
        .filter(ProductSpecifications.product_id == product_id)
        .first()
    )


# --------------------------------------------------------------------------- #
# AC-A.1 - propose: 202 + batch row + enqueue seam; 409 not-read
# --------------------------------------------------------------------------- #
def test_propose_returns_202_with_a_proposing_batch_and_calls_the_enqueue_seam(api, db, monkeypatch):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    _product(db, "ZZT-FLYRT-PROPOSE", "SORENTO ONE PIECE WC ZZT-FLYRT-PROPOSE")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-PROPOSE", "Washdown")])
    db.commit()

    import app.services.product_spec_flyer_ingest as ingest

    calls = []
    monkeypatch.setattr(ingest, "_enqueue", lambda batch: calls.append(str(batch.id)) or "zzt-job-1")

    response = client.post(_PROPOSE.format(reading.id))

    assert response.status_code == 202, response.text
    assert len(calls) == 1

    row = (
        db.query(ProductSpecFlyerBatch)
        .filter(ProductSpecFlyerBatch.flyer_reading_id == reading.id)
        .one()
    )
    assert row.status == "proposing"
    assert str(row.id) == calls[0]


def test_propose_refuses_409_while_the_reading_is_still_processing(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    reading = _reading(db, status=dk_svc.ReadingStatus.PROCESSING)
    db.commit()

    response = client.post(_PROPOSE.format(reading.id))

    assert response.status_code == 409, response.text
    assert "still being read" in response.text.lower()


def test_propose_refuses_409_when_the_reading_failed(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    reading = _reading(db, status=dk_svc.ReadingStatus.FAILED)
    db.commit()

    response = client.post(_PROPOSE.format(reading.id))

    assert response.status_code == 409, response.text


# --------------------------------------------------------------------------- #
# AC-A.5 - a batch already proposing refuses a second propose (409)
# --------------------------------------------------------------------------- #
def test_propose_refuses_409_when_a_batch_is_already_proposing(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    reading = _reading(db)
    _batch(db, reading, status="proposing")
    db.commit()

    response = client.post(_PROPOSE.format(reading.id))

    assert response.status_code == 409, response.text


# --------------------------------------------------------------------------- #
# AC-A.7 - permission AND, in declared order; 401 with no principal
# --------------------------------------------------------------------------- #
def test_propose_401s_without_a_principal(api, db):
    from app.dependencies import get_current_user
    from app.main import app
    from fastapi import HTTPException

    client, allow = api
    allow.update({_VIEW, _EDIT})
    reading = _reading(db)
    db.commit()

    def _deny():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = _deny
    try:
        response = client.post(_PROPOSE.format(reading.id))
    finally:
        app.dependency_overrides[get_current_user] = lambda: _USER

    assert response.status_code == 401, response.text


def test_propose_403_names_page_view_when_it_is_the_missing_permission(api, db):
    client, allow = api
    allow.add(_EDIT)  # products.edit present, page.view missing
    reading = _reading(db)
    db.commit()

    response = client.post(_PROPOSE.format(reading.id))

    assert response.status_code == 403, response.text
    assert _VIEW in response.text
    assert _EDIT not in response.text, "must name the FIRST missing permission, not both"


def test_propose_403_names_products_edit_when_it_is_the_missing_permission(api, db):
    client, allow = api
    allow.add(_VIEW)  # page.view present, products.edit missing
    reading = _reading(db)
    db.commit()

    response = client.post(_PROPOSE.format(reading.id))

    assert response.status_code == 403, response.text
    assert _EDIT in response.text


def test_get_proposals_403_without_either_permission(api, db):
    client, _allow = api
    reading = _reading(db)
    db.commit()

    response = client.get(_GET_PROPOSALS.format(reading.id))

    assert response.status_code == 403, response.text


# --------------------------------------------------------------------------- #
# AC-B.1 - GET the batch: status none, and the grouped shape once proposed
# --------------------------------------------------------------------------- #
def test_get_proposals_returns_status_none_without_a_batch(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    reading = _reading(db)
    db.commit()

    response = client.get(_GET_PROPOSALS.format(reading.id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "none"
    assert body.get("groups") in (None, [])


def test_get_proposals_groups_rows_by_product_for_a_proposed_batch(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-GET1", "SORENTO ONE PIECE WC ZZT-FLYRT-GET1")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-GET1", "Washdown. S-Trap outlet 250mm")])
    batch = _batch(db, reading, status="proposed", proposal_count=1, product_count=1, new_count=1)
    _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.get(_GET_PROPOSALS.format(reading.id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "proposed"
    groups = body["groups"]
    assert len(groups) == 1
    group = groups[0]
    assert group["productCode"] == "ZZT-FLYRT-GET1"
    proposal = group["proposals"][0]
    assert proposal["specKey"] == "trap_type"
    assert proposal["value"] == "s_trap"
    assert proposal["kind"] == "new"


# --------------------------------------------------------------------------- #
# AC-B.2 - list every batch, newest first
# --------------------------------------------------------------------------- #
def test_list_batches_returns_newest_first(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    older = _reading(db, filename="ZZT Older.pdf")
    older_batch = _batch(db, older, status="proposed")
    newer = _reading(db, filename="ZZT Newer.pdf")
    newer_batch = _batch(db, newer, status="proposed")
    db.commit()

    # created_at both default to "now" inside one transaction; force the order.
    from datetime import datetime, timedelta

    older_batch.created_at = datetime.utcnow() - timedelta(days=1)
    db.add(older_batch)
    db.commit()

    response = client.get(_LIST_BATCHES)

    assert response.status_code == 200, response.text
    ids = [row["id"] for row in response.json()]
    assert ids.index(str(newer_batch.id)) < ids.index(str(older_batch.id))


# --------------------------------------------------------------------------- #
# AC-C.1 - the apply body: ids only, a count ceiling, a foreign id
# --------------------------------------------------------------------------- #
def test_apply_rejects_a_body_carrying_a_values_field(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-C1A", "SORENTO ONE PIECE WC ZZT-FLYRT-C1A")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-C1A", "Washdown. S-Trap outlet 250mm")])
    batch = _batch(db, reading)
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(
        _APPLY.format(reading.id),
        json={"proposal_ids": [str(proposal.id)], "values": {"trap_type": "s_trap"}},
    )

    assert response.status_code == 422, response.text


def test_apply_refuses_more_than_5000_ids(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    reading = _reading(db)
    _batch(db, reading)
    db.commit()

    ids = [str(uuid.uuid4()) for _ in range(5001)]
    response = client.post(_APPLY.format(reading.id), json={"proposal_ids": ids})

    assert response.status_code == 422, response.text


def test_apply_refuses_a_proposal_id_not_in_this_batch(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    reading = _reading(db)
    _batch(db, reading)
    db.commit()

    foreign_id = str(uuid.uuid4())
    response = client.post(_APPLY.format(reading.id), json={"proposal_ids": [foreign_id]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] == []
    refused = body["refused"][0]
    assert refused["proposalId"] == foreign_id
    assert refused["reason"] == "not_in_batch"


# --------------------------------------------------------------------------- #
# AC-C.2 - live re-classification against the CURRENT master, not the snapshot
# --------------------------------------------------------------------------- #
def test_apply_refuses_a_row_that_now_already_matches_the_master(api, db):
    """Stored kind was `new` at propose time; the master has since caught up
    (a person set it by hand between propose and apply). Applying it now must
    refuse `already_matches` rather than trust the stale stored kind."""
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-C2A", "SORENTO ONE PIECE WC ZZT-FLYRT-C2A")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-C2A", commit=True)
    from app.services.product_spec_write import apply_spec_values

    apply_spec_values(
        db,
        "ZZT-FLYRT-C2A",
        [{"spec_key": "trap_type", "op": "set", "value": "s_trap", "source": "human"}],
        actor=_USER,
    )
    reading = _reading(db, cards=[_card("ZZT-FLYRT-C2A", "Washdown. S-Trap outlet 250mm")])
    batch = _batch(db, reading)
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(_APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] == []
    assert body["refused"][0]["reason"] == "already_matches"


def test_apply_refuses_a_row_that_now_conflicts_with_an_authored_value(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-C2B", "SORENTO ONE PIECE WC ZZT-FLYRT-C2B")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-C2B", commit=True)
    from app.services.product_spec_write import apply_spec_values

    # At propose time this key was unset (kind=new); a person then set it by hand.
    reading = _reading(db, cards=[_card("ZZT-FLYRT-C2B", "*PP Seat Cover")])
    batch = _batch(db, reading)
    proposal = _proposal(db, batch, product, spec_key="seat_material", value="pp", kind="new")
    db.commit()

    apply_spec_values(
        db,
        "ZZT-FLYRT-C2B",
        [{"spec_key": "seat_material", "op": "set", "value": "uf", "source": "human"}],
        actor=_USER,
    )
    db.commit()

    response = client.post(_APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] == []
    assert body["refused"][0]["reason"] == "conflict_not_confirmed"
    assert _spec_of(db, product.id).values["seat_material"]["value"] == "uf", "untouched"


def test_apply_writes_a_new_row(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-C2C", "SORENTO ONE PIECE WC ZZT-FLYRT-C2C")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-C2C", commit=True)
    reading = _reading(db, cards=[_card("ZZT-FLYRT-C2C", "Washdown. S-Trap outlet 250mm")])
    batch = _batch(db, reading)
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(_APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] == []
    assert body["applied"][0]["specKey"] == "trap_type"
    assert _spec_of(db, product.id).values["trap_type"]["value"] == "s_trap"


# --------------------------------------------------------------------------- #
# AC-C.3 - one apply_spec_values call per product; entries carry source flyer,
# the registry's own unit, and evidence "flyer <filename>: <printed words>"
# --------------------------------------------------------------------------- #
def test_apply_writes_through_exactly_one_call_per_product_with_flyer_provenance(api, db, monkeypatch):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-C3A", "SORENTO ONE PIECE WC ZZT-FLYRT-C3A")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-C3A", commit=True)

    reading = _reading(
        db,
        filename="ZZT-C3-Flyer.pdf",
        cards=[_card("ZZT-FLYRT-C3A", "Washdown. D: L680xW375xH770mm. S-Trap outlet 250mm")],
    )
    batch = _batch(db, reading)
    p1 = _proposal(
        db, batch, product, spec_key="trap_type", value="s_trap", kind="new", evidence="S-TRAP OUTLET"
    )
    p2 = _proposal(
        db, batch, product, spec_key="dim_length", value=680, kind="new", unit="mm", evidence="L680"
    )
    db.commit()

    calls = []
    import app.services.product_spec_write as write_module

    real_apply = write_module.apply_spec_values

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(write_module, "apply_spec_values", _spy)

    response = client.post(
        _APPLY.format(reading.id), json={"proposal_ids": [str(p1.id), str(p2.id)]}
    )

    assert response.status_code == 200, response.text
    assert len(calls) == 1, "must write through exactly one apply_spec_values call per product"

    _, kwargs = calls[0]
    entries = kwargs.get("entries") or calls[0][0][2]
    by_key = {e["spec_key"]: e for e in entries}
    assert by_key["trap_type"]["source"] == "flyer"
    assert by_key["trap_type"]["unit"] is None
    assert by_key["trap_type"]["evidence"] == "flyer ZZT-C3-Flyer.pdf: S-TRAP OUTLET"
    assert by_key["dim_length"]["unit"] == "mm"
    assert by_key["dim_length"]["evidence"] == "flyer ZZT-C3-Flyer.pdf: L680"


# --------------------------------------------------------------------------- #
# AC-C.4 - one product's write fails; the other product still applies, 200
# --------------------------------------------------------------------------- #
def test_apply_refuses_one_products_rows_when_its_write_raises_but_still_200s(api, db, monkeypatch):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    good = _product(db, "ZZT-FLYRT-C4-GOOD", "SORENTO ONE PIECE WC ZZT-FLYRT-C4-GOOD")
    doomed = _product(db, "ZZT-FLYRT-C4-BAD", "SORENTO ONE PIECE WC ZZT-FLYRT-C4-BAD")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-C4-GOOD", commit=True)
    derive_for_code(db, "ZZT-FLYRT-C4-BAD", commit=True)

    reading = _reading(
        db,
        cards=[
            _card("ZZT-FLYRT-C4-GOOD", "Washdown. S-Trap outlet 250mm"),
            _card("ZZT-FLYRT-C4-BAD", "Washdown. S-Trap outlet 250mm"),
        ],
    )
    batch = _batch(db, reading)
    p_good = _proposal(db, batch, good, spec_key="trap_type", value="s_trap", kind="new")
    p_bad = _proposal(db, batch, doomed, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    import app.services.product_spec_write as write_module
    from app.services.error_handler import AppException

    real_apply = write_module.apply_spec_values

    def _flaky(db_arg, product_code, entries, **kwargs):
        if product_code == "ZZT-FLYRT-C4-BAD":
            raise AppException(status_code=404, message="gone", code="product_not_found")
        return real_apply(db_arg, product_code, entries, **kwargs)

    monkeypatch.setattr(write_module, "apply_spec_values", _flaky)

    response = client.post(
        _APPLY.format(reading.id), json={"proposal_ids": [str(p_good.id), str(p_bad.id)]}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["specKey"] for row in body["applied"]] == ["trap_type"]
    assert body["applied"][0]["productCode"] == "ZZT-FLYRT-C4-GOOD"
    assert body["refused"][0]["productCode"] == "ZZT-FLYRT-C4-BAD"
    assert _spec_of(db, good.id).values["trap_type"]["value"] == "s_trap"


# --------------------------------------------------------------------------- #
# AC-C.5 - stamps: row outcome/appliedAt/appliedBy, batch appliedAt/appliedBy/count
# --------------------------------------------------------------------------- #
def test_apply_stamps_the_row_and_the_batch(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-C5A", "SORENTO ONE PIECE WC ZZT-FLYRT-C5A")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-C5A", commit=True)
    reading = _reading(db, cards=[_card("ZZT-FLYRT-C5A", "Washdown. S-Trap outlet 250mm")])
    batch = _batch(db, reading)
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(_APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]})

    assert response.status_code == 200, response.text
    db.expire_all()
    stored = db.query(ProductSpecFlyerProposal).filter_by(id=proposal.id).one()
    assert stored.outcome == "applied"
    assert stored.applied_at is not None
    assert stored.applied_by == _USER["id"]

    stored_batch = db.query(ProductSpecFlyerBatch).filter_by(id=batch.id).one()
    assert stored_batch.applied_at is not None
    assert stored_batch.applied_by == _USER["id"]
    assert stored_batch.applied_count == 1


# --------------------------------------------------------------------------- #
# AC-C.6 - idempotency: an already-matching row applies as a pure no-op
# --------------------------------------------------------------------------- #
def test_reapplying_an_already_matching_row_writes_nothing(api, db, monkeypatch):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-C6A", "SORENTO ONE PIECE WC ZZT-FLYRT-C6A")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-C6A", commit=True)
    from app.services.product_spec_write import apply_spec_values

    apply_spec_values(
        db,
        "ZZT-FLYRT-C6A",
        [{"spec_key": "trap_type", "op": "set", "value": "s_trap", "source": "flyer"}],
        actor=_USER,
    )
    db.commit()
    stamped = _spec_of(db, product.id).updated_at

    reading = _reading(db, cards=[_card("ZZT-FLYRT-C6A", "Washdown. S-Trap outlet 250mm")])
    batch = _batch(db, reading)
    # A fresh propose pass over the now-matching master would classify this
    # `unchanged`, which is what a second propose+apply of the same flyer means.
    proposal = _proposal(
        db, batch, product, spec_key="trap_type", value="s_trap", kind="unchanged",
        stored_value="s_trap", stored_source="flyer",
    )
    db.commit()

    calls = []
    import app.services.product_spec_write as write_module

    real_apply = write_module.apply_spec_values
    monkeypatch.setattr(
        write_module,
        "apply_spec_values",
        lambda *a, **k: (calls.append(1), real_apply(*a, **k))[1],
    )

    response = client.post(_APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] == []
    assert body["refused"][0]["reason"] == "already_matches"
    assert calls == [], "an already-matching row must never reach apply_spec_values"
    assert _spec_of(db, product.id).updated_at == stamped
