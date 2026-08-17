"""The four flyer-spec-proposal routes (S2, HTTP level).

Plan: `documentation/plans/master-data/PLAN-flyer-spec-ingestion.md` section 3.4
and section 7 (captain amendment 2026-08-17). UAC:
`flyer-spec-ingestion-acceptance-criteria.md` AC-A.1, AC-A.5, AC-A.7, AC-B.1,
AC-B.2, AC-C.1 through AC-C.7 (C.2 amended), AC-F.1, AC-F.2, AC-F.5, AC-G.1
through AC-G.3.

Section F (added 2026-08-17, written RED against the still-refusing apply and
the not-yet-existing PATCH route): AC-F.1 flips a ticked `conflict` row from
refused to written (only `unchanged`/`suppressed` refuse now, superseding L7 in
part - see `test_apply_writes_a_ticked_row_that_now_conflicts_with_an_authored_value`
and its suppressed-still-refuses neighbour); AC-F.2 is the new
`PATCH .../spec-proposals/{proposal_id}` in-place value edit (validated, stamped
`edited_at`/`edited_by`, kind + batch counts recomputed); AC-F.5 is
`allowed_values` on a closed-vocabulary row in the GET payload.

Section G (added 2026-08-17b, captain amendment, written RED against the
not-yet-existing `POST .../spec-proposals/rows` and `DELETE
.../spec-proposals/{proposal_id}` and the not-yet-existing `origin` column):
AC-G.1 is a manually-added proposal row (`origin='manual'`) with its five
refusals; AC-G.2 is that a manual row applies with `source='human'` and fixed
evidence, while a flyer-read row still applies `source='flyer'`; AC-G.3 is the
hard-delete of a non-applied, non-`applied`-outcome row with the same
permission pair as every other route in this file.

Written red, against routes that did not exist yet, and green since S2 built
`app/api/v1/dealer_kit/flyer_spec_proposals.py` and mounted it. What it covers:
the list, the propose, the per-reading read and the apply, each at the HTTP
boundary - the permission pair on all four (401, and 403 for each slug missing),
the two 409s propose can answer (not read yet, already proposing), the
`status: "none"` answer for a reading nobody has proposed from, and the apply's
per-row outcomes including the ids-only body, the size ceiling and the refusal to
apply a batch that is not `proposed`.

Fixture/dependency-override pattern copied from
`tests/test_product_spec_batch_apply_route.py` and
`tests/test_product_spec_extract_route.py`: bare `TestClient(app)` (no `with`, so
the app's startup event and its company-scope listeners never register - the same
reason those two files need no company-scope plumbing), `get_db` /
`get_current_user` / `get_current_user_or_api_key` / `apply_company_scope`
overridden, `UserPermissionService.check_user_has_
permission` monkeypatched against an `allow` set. The two routes' own permission
dependencies (`require_permission`, not `_with_api_key` - see `apply_flyer_
dimensions` for the precedent AC-A.7/L9 names) resolve through `get_current_
user`, so that is the one overridden for the 401 case, not `_or_api_key`.

Field names on the wire are snake_case, NOT the dealer kit's camelCase aliases.
These payloads carry `spec_key` / `stored_value` / `data_type` rows straight into
`components/spec-proposals`, which speaks snake_case, and the UAC names every
field of these four routes in snake_case (AC-B.1, AC-B.2, AC-C.1); the PLAN records
the deviation from the dealer kit's usual convention in section 5. A handful of
assertions in this file were written camelCase before that was settled and were
corrected here - a test defect, not a change of behaviour.

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
_PATCH_PROPOSAL = "/api/v1/dealer-kit/flyer-readings/{}/spec-proposals/{}"
_DELETE_PROPOSAL = _PATCH_PROPOSAL
_ADD_ROW = "/api/v1/dealer-kit/flyer-readings/{}/spec-proposals/rows"


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
    origin: str | None = None,
) -> ProductSpecFlyerProposal:
    kwargs: dict = {}
    if origin is not None:
        # AC-G.1/G.2: `origin` (`flyer` | `manual`) does not exist on the model
        # yet - passed only by the section G tests, which is what makes THIS
        # the failure a section-G test hits (a TypeError on an unexpected
        # keyword, i.e. the missing `origin` column) rather than every other
        # test in this file that never asks for one.
        kwargs["origin"] = origin
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
        **kwargs,
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
# The permission pair on the OTHER three routes - the read, the list and the
# apply. `apply` is the one route that writes `product_specifications`, so it is
# the one where "no API-key variant" matters most: the fixture resolves both
# principals to the same user, so only a real 401 through `get_current_user`
# (which `_with_api_key` would bypass) and the two 403s in order pin it.
# --------------------------------------------------------------------------- #
def _deny_principal():
    from fastapi import HTTPException

    raise HTTPException(status_code=401, detail="Not authenticated")


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda client, reading: client.get(_GET_PROPOSALS.format(reading.id)), id="get"),
        pytest.param(lambda client, reading: client.get(_LIST_BATCHES), id="list"),
        pytest.param(
            lambda client, reading: client.post(
                _APPLY.format(reading.id), json={"proposal_ids": [str(uuid.uuid4())]}
            ),
            id="apply",
        ),
    ],
)
def test_read_list_and_apply_401_without_a_principal(api, db, call):
    from app.dependencies import get_current_user
    from app.main import app

    client, allow = api
    allow.update({_VIEW, _EDIT})
    reading = _reading(db)
    db.commit()

    app.dependency_overrides[get_current_user] = _deny_principal
    try:
        response = call(client, reading)
    finally:
        app.dependency_overrides[get_current_user] = lambda: _USER

    assert response.status_code == 401, response.text


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda client, reading: client.get(_GET_PROPOSALS.format(reading.id)), id="get"),
        pytest.param(lambda client, reading: client.get(_LIST_BATCHES), id="list"),
        pytest.param(
            lambda client, reading: client.post(
                _APPLY.format(reading.id), json={"proposal_ids": [str(uuid.uuid4())]}
            ),
            id="apply",
        ),
    ],
)
def test_read_list_and_apply_403_name_page_view_when_it_is_the_missing_permission(api, db, call):
    client, allow = api
    allow.add(_EDIT)  # products.edit present, page.view missing
    reading = _reading(db)
    db.commit()

    response = call(client, reading)

    assert response.status_code == 403, response.text
    assert _VIEW in response.text
    assert _EDIT not in response.text, "must name the FIRST missing permission, not both"


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda client, reading: client.get(_GET_PROPOSALS.format(reading.id)), id="get"),
        pytest.param(lambda client, reading: client.get(_LIST_BATCHES), id="list"),
        pytest.param(
            lambda client, reading: client.post(
                _APPLY.format(reading.id), json={"proposal_ids": [str(uuid.uuid4())]}
            ),
            id="apply",
        ),
    ],
)
def test_read_list_and_apply_403_name_products_edit_when_it_is_the_missing_permission(api, db, call):
    client, allow = api
    allow.add(_VIEW)  # page.view present, products.edit missing
    reading = _reading(db)
    db.commit()

    response = call(client, reading)

    assert response.status_code == 403, response.text
    assert _EDIT in response.text


def test_apply_403_without_products_edit_writes_nothing(api, db):
    """The refusal happens before the body is read: a well-formed apply naming a
    real `new` row, from somebody holding only the dealer-kit slug, leaves the
    product master untouched and the row unstamped."""
    client, allow = api
    allow.add(_VIEW)
    product = _product(db, "ZZT-FLYRT-AUTHW", "SORENTO ONE PIECE WC ZZT-FLYRT-AUTHW")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-AUTHW", commit=True)
    reading = _reading(db, cards=[_card("ZZT-FLYRT-AUTHW", "Washdown. S-Trap outlet 250mm")])
    batch = _batch(db, reading)
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(_APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]})

    assert response.status_code == 403, response.text
    assert "trap_type" not in (_spec_of(db, product.id).values or {})
    db.expire_all()
    assert db.query(ProductSpecFlyerProposal).filter_by(id=proposal.id).one().outcome is None


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
    assert group["product_code"] == "ZZT-FLYRT-GET1"
    proposal = group["proposals"][0]
    assert proposal["spec_key"] == "trap_type"
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
    """The ceiling is the SERVICE's, and it says so in words.

    There is one guard, not two: the request schema declares no `max_length`, so this
    request reaches `apply_batch` and is refused by `MAX_ROWS` with a sentence naming
    both numbers. A schema ceiling would 422 first with pydantic's "List should have at
    most 5000 items" and that sentence would be unreachable, which is why this asserts
    the message and the code rather than only the status.
    """
    client, allow = api
    allow.update({_VIEW, _EDIT})
    reading = _reading(db)
    _batch(db, reading)
    db.commit()

    ids = [str(uuid.uuid4()) for _ in range(5001)]
    response = client.post(_APPLY.format(reading.id), json={"proposal_ids": ids})

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "product_spec_batch_too_large"
    assert body["message"] == "That is 5001 proposals. Apply at most 5000 at a time."


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
    assert refused["proposal_id"] == foreign_id
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


def test_apply_writes_a_ticked_row_that_now_conflicts_with_an_authored_value(api, db):
    """AC-F.1 (captain amendment 2026-08-17, supersedes L7): a ticked `conflict`
    row is WRITTEN, exactly like `change` - the tick plus the FE confirm dialog
    naming the overwrite count IS the confirmation. Before the amendment this
    same setup (an authored value disagreeing with the card) refused
    `conflict_not_confirmed` with no write; that is now `apply_batch`'s answer
    ONLY for `unchanged` (AC-C.2/AC-C.6) and `suppressed` (below)."""
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
    assert body["refused"] == []
    assert body["applied"][0]["spec_key"] == "seat_material"
    assert body["applied"][0]["value"] == "pp"
    stored_spec = _spec_of(db, product.id)
    assert stored_spec.values["seat_material"]["value"] == "pp"
    assert stored_spec.provenance["seat_material"]["source"] == "flyer"


def test_apply_still_refuses_a_ticked_suppressed_tombstone_as_conflict_not_confirmed(api, db):
    """AC-F.1: only `unchanged` and `suppressed` refuse now. A tombstone (a person
    said this product does NOT carry the key) must still refuse - the amendment
    widens what a tick can overwrite, it does not let a tick resurrect a removed
    specification."""
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-F1B", "SORENTO ONE PIECE WC ZZT-FLYRT-F1B")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-F1B", commit=True)
    from app.services.product_spec_write import apply_spec_values

    reading = _reading(db, cards=[_card("ZZT-FLYRT-F1B", "*PP Seat Cover")])
    batch = _batch(db, reading)
    proposal = _proposal(db, batch, product, spec_key="seat_material", value="pp", kind="new")
    db.commit()

    apply_spec_values(
        db,
        "ZZT-FLYRT-F1B",
        [{"spec_key": "seat_material", "op": "absent", "source": "human"}],
        actor=_USER,
    )
    db.commit()

    response = client.post(_APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] == []
    assert body["refused"][0]["reason"] == "conflict_not_confirmed"
    assert "seat_material" not in (_spec_of(db, product.id).values or {}), "untouched"


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
    assert body["applied"][0]["spec_key"] == "trap_type"
    assert _spec_of(db, product.id).values["trap_type"]["value"] == "s_trap"


def test_apply_writes_a_row_that_is_still_a_change_at_apply_time(api, db):
    """The `change` kind LIVE: the master holds a DERIVED value (nobody authored
    it, the key is not description-first) and the flyer says something else. It
    is neither `already_matches` nor a tombstone, so it is written and badged
    `flyer`. The two other `change` fixtures in this file are re-classified to
    `unchanged` / `conflict` before their apply, so without this one a change
    that folded `change` into the refusals would go unnoticed."""
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(
        db, "ZZT-FLYRT-CHG", "SORENTO CERAMIC ART BASIN ONLY BLACK ZZT-FLYRT-CHG"
    )
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-CHG", commit=True)
    derived = _spec_of(db, product.id)
    assert derived.values["finish"]["value"] == "black", "fixture assumption"
    assert derived.provenance["finish"]["source"] == "derived", "nobody authored it"

    reading = _reading(db, filename="ZZT-CHG-Flyer.pdf", cards=[_card("ZZT-FLYRT-CHG", "Chrome finish")])
    batch = _batch(db, reading)
    proposal = _proposal(
        db,
        batch,
        product,
        spec_key="finish",
        value="chrome",
        kind="change",
        evidence="Chrome finish",
        stored_value="black",
        stored_source="derived",
    )
    db.commit()

    response = client.post(_APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] == []
    assert body["applied"][0]["spec_key"] == "finish"
    assert body["applied"][0]["value"] == "chrome"

    stored = _spec_of(db, product.id)
    assert stored.values["finish"]["value"] == "chrome"
    assert stored.provenance["finish"]["source"] == "flyer"
    assert "Chrome finish" in stored.provenance["finish"].get("evidence", "")
    db.expire_all()
    assert db.query(ProductSpecFlyerProposal).filter_by(id=proposal.id).one().outcome == "applied"


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
    assert [row["spec_key"] for row in body["applied"]] == ["trap_type"]
    assert body["applied"][0]["product_code"] == "ZZT-FLYRT-C4-GOOD"
    assert body["refused"][0]["product_code"] == "ZZT-FLYRT-C4-BAD"
    assert _spec_of(db, good.id).values["trap_type"]["value"] == "s_trap"


# --------------------------------------------------------------------------- #
# AC-C.5 - stamps: row outcome/applied_at/applied_by, batch applied_at/applied_by/count
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


def test_reapplying_the_same_id_keeps_the_row_marked_applied(api, db):
    """The answer says `already_matches`; the ROW still says it was applied (AC-C.5).

    Ticking the same proposal twice is the ordinary second apply: the master now agrees
    with it, so the second answer is a refusal. But the refusal must not be stamped over
    the row, because the row is the record that this flyer is where the value came from.
    Overwriting it dropped `applied_count` back to 0, which flipped the batch on the list
    screen from Applied to Proposed for a request that changed nothing at all.
    """
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-C5B", "SORENTO ONE PIECE WC ZZT-FLYRT-C5B")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-C5B", commit=True)
    reading = _reading(db, cards=[_card("ZZT-FLYRT-C5B", "Washdown. S-Trap outlet 250mm")])
    batch = _batch(db, reading)
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    first = client.post(_APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]})
    assert first.status_code == 200, first.text
    assert first.json()["applied"][0]["spec_key"] == "trap_type"

    db.expire_all()
    applied_at = db.query(ProductSpecFlyerProposal).filter_by(id=proposal.id).one().applied_at

    second = client.post(_APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]})

    assert second.status_code == 200, second.text
    body = second.json()
    assert body["applied"] == []
    assert body["refused"][0]["reason"] == "already_matches"

    db.expire_all()
    stored = db.query(ProductSpecFlyerProposal).filter_by(id=proposal.id).one()
    assert stored.outcome == "applied", "a written row never un-writes itself"
    assert stored.applied_at == applied_at, "the moment it was written does not move"
    assert stored.applied_by == _USER["id"]

    stored_batch = db.query(ProductSpecFlyerBatch).filter_by(id=batch.id).one()
    assert stored_batch.applied_count == 1


# --------------------------------------------------------------------------- #
# Apply refuses a batch that is not `proposed` (second-review finding 7)
# --------------------------------------------------------------------------- #
def test_apply_refuses_409_while_the_batch_is_being_re_proposed(api, db):
    """Mid-re-propose the batch holds the OLD ids briefly and then none of them.

    Answering the apply from that window either writes rows from a superseded pass or
    comes back every-row-`not_in_batch`, which reads as a bug rather than as timing.
    """
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-REPRO", "SORENTO ONE PIECE WC ZZT-FLYRT-REPRO")
    db.commit()
    reading = _reading(db, cards=[_card("ZZT-FLYRT-REPRO", "Washdown. S-Trap outlet 250mm")])
    batch = _batch(db, reading, status="proposing")
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(_APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]})

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "FLYER_SPEC_NOT_PROPOSED"
    assert "again" in body["message"].lower()

    db.expire_all()
    assert db.query(ProductSpecFlyerProposal).filter_by(id=proposal.id).one().outcome is None


def test_apply_refuses_409_when_the_last_pass_failed(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-FAILED", "SORENTO ONE PIECE WC ZZT-FLYRT-FAILED")
    db.commit()
    reading = _reading(db, cards=[_card("ZZT-FLYRT-FAILED", "Washdown. S-Trap outlet 250mm")])
    batch = _batch(db, reading, status="failed", error_message="the rules could not be loaded")
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(_APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]})

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "FLYER_SPEC_NOT_PROPOSED"
    assert "did not finish" in body["message"]


# --------------------------------------------------------------------------- #
# One registry load per apply, not one per product (second-review finding 3)
# --------------------------------------------------------------------------- #
def test_apply_loads_the_rule_registry_once_for_a_two_product_apply(api, db, monkeypatch):
    """`configured_rules` is read ONCE for the whole request, not once per product.

    `apply_spec_values` re-derives the code it wrote, and the re-derive loads the rule
    and scope registries unless it is handed them - two registry scans per product,
    inside one transaction, for a flyer that can name two hundred of them. The counter
    is installed on BOTH namespaces (the derivation module's own global, which
    `derive_for_code` reads, and the ingest module's imported name) so it counts every
    load on the path rather than only the one the service makes.
    """
    client, allow = api
    allow.update({_VIEW, _EDIT})

    import app.services.product_spec_derivation as derivation
    import app.services.product_spec_flyer_ingest as ingest

    first = _product(db, "ZZT-FLYRT-ONCE-A", "SORENTO ONE PIECE WC ZZT-FLYRT-ONCE-A")
    second = _product(db, "ZZT-FLYRT-ONCE-B", "SORENTO ONE PIECE WC ZZT-FLYRT-ONCE-B")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-ONCE-A", commit=True)
    derive_for_code(db, "ZZT-FLYRT-ONCE-B", commit=True)

    reading = _reading(
        db,
        cards=[
            _card("ZZT-FLYRT-ONCE-A", "Washdown. S-Trap outlet 250mm"),
            _card("ZZT-FLYRT-ONCE-B", "Washdown. S-Trap outlet 250mm"),
        ],
    )
    batch = _batch(db, reading)
    p1 = _proposal(db, batch, first, spec_key="trap_type", value="s_trap", kind="new")
    p2 = _proposal(db, batch, second, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    real_rules = derivation.configured_rules
    loads: list[int] = []

    def _counting_rules(session):
        loads.append(1)
        return real_rules(session)

    monkeypatch.setattr(derivation, "configured_rules", _counting_rules)
    monkeypatch.setattr(ingest, "configured_rules", _counting_rules)

    response = client.post(
        _APPLY.format(reading.id), json={"proposal_ids": [str(p1.id), str(p2.id)]}
    )

    assert response.status_code == 200, response.text
    assert len(response.json()["applied"]) == 2
    assert len(loads) == 1, f"one load for the request, not one per product: {len(loads)}"


# --------------------------------------------------------------------------- #
# AC-F.2 - PATCH a proposal's value in place (captain amendment 2026-08-17)
# --------------------------------------------------------------------------- #
def test_patch_edits_the_value_recomputes_kind_and_refreshes_batch_counts(api, db):
    """AC-F.2 happy path: the value is validated via `value_for_registry`, stored
    on the row with `edited_at`/`edited_by`, the row's `kind` is recomputed
    against the LIVE spec row (not the stale propose-time snapshot), and the
    batch's per-kind counts move with it. Editing to a value equal to what is
    stored flips the row to `unchanged`, which then refuses `already_matches` on
    apply exactly as a pass that read it that way from the start would - the
    edit changes what was proposed, never the idempotency guarantee (AC-C.6)."""
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(
        db, "ZZT-FLYRT-F2A", "SORENTO CERAMIC ART BASIN ONLY BLACK ZZT-FLYRT-F2A"
    )
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-F2A", commit=True)
    assert _spec_of(db, product.id).values["finish"]["value"] == "black", "fixture assumption"

    reading = _reading(db, cards=[_card("ZZT-FLYRT-F2A", "Chrome finish")])
    batch = _batch(
        db, reading, status="proposed", proposal_count=1, product_count=1, change_count=1
    )
    proposal = _proposal(
        db,
        batch,
        product,
        spec_key="finish",
        value="chrome",
        kind="change",
        stored_value="black",
        stored_source="derived",
    )
    db.commit()

    response = client.patch(
        _PATCH_PROPOSAL.format(reading.id, proposal.id), json={"value": "black"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["value"] == "black"
    assert body["kind"] == "unchanged"
    assert body.get("edited") is True

    db.expire_all()
    stored = db.query(ProductSpecFlyerProposal).filter_by(id=proposal.id).one()
    assert stored.value == "black"
    assert stored.kind == "unchanged"
    assert stored.edited_at is not None
    assert stored.edited_by == _USER["id"]

    stored_batch = db.query(ProductSpecFlyerBatch).filter_by(id=batch.id).one()
    assert stored_batch.change_count == 0
    assert stored_batch.unchanged_count == 1

    get_response = client.get(_GET_PROPOSALS.format(reading.id))
    assert get_response.status_code == 200, get_response.text
    proposal_row = get_response.json()["groups"][0]["proposals"][0]
    assert proposal_row["value"] == "black"
    assert proposal_row["kind"] == "unchanged"
    assert proposal_row.get("edited") is True

    apply_response = client.post(
        _APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]}
    )
    assert apply_response.status_code == 200, apply_response.text
    apply_body = apply_response.json()
    assert apply_body["applied"] == []
    assert apply_body["refused"][0]["reason"] == "already_matches"


def test_patch_keeps_a_two_tone_finish_as_a_list_and_apply_writes_both(api, db):
    """A multi-value row (finish is the one key that may hold two values at once,
    "Rose Gold + Matt Black" on 23 cards). PATCHing a list stores the list, the
    row is classified against the live master as a list, and apply writes BOTH
    tones - not the first one alone, which is what a `value_for_registry` that
    collapsed every list would silently do."""
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-MV1", "SORENTO ONE PIECE WC ZZT-FLYRT-MV1")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-MV1", commit=True)
    assert "finish" not in (_spec_of(db, product.id).values or {}), "fixture assumption"

    reading = _reading(db, cards=[_card("ZZT-FLYRT-MV1", "Rose Gold + Matt Black")])
    batch = _batch(db, reading, status="proposed", proposal_count=1, product_count=1, new_count=1)
    proposal = _proposal(
        db, batch, product, spec_key="finish", value=["rose_gold", "chrome"], kind="new"
    )
    db.commit()

    response = client.patch(
        _PATCH_PROPOSAL.format(reading.id, proposal.id), json={"value": ["rose_gold", "black"]}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["value"] == ["rose_gold", "black"]
    assert body["kind"] == "new"

    db.expire_all()
    stored = db.query(ProductSpecFlyerProposal).filter_by(id=proposal.id).one()
    assert stored.value == ["rose_gold", "black"]

    apply_response = client.post(
        _APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]}
    )
    assert apply_response.status_code == 200, apply_response.text
    apply_body = apply_response.json()
    assert apply_body["refused"] == []
    assert sorted(apply_body["applied"][0]["value"]) == ["black", "rose_gold"]
    written = _spec_of(db, product.id).values["finish"]["value"]
    assert sorted(written) == ["black", "rose_gold"]


def test_patch_refuses_a_list_on_a_single_value_key_and_a_bad_tone_in_a_list(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-MV2", "SORENTO ONE PIECE WC ZZT-FLYRT-MV2")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-MV2", commit=True)
    reading = _reading(db, cards=[_card("ZZT-FLYRT-MV2", "Washdown")])
    batch = _batch(db, reading, status="proposed", proposal_count=2, product_count=1, new_count=2)
    single = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    multi = _proposal(db, batch, product, spec_key="finish", value=["rose_gold"], kind="new")
    db.commit()

    response = client.patch(
        _PATCH_PROPOSAL.format(reading.id, single.id), json={"value": ["s_trap", "p_trap"]}
    )
    assert response.status_code == 400, response.text

    response = client.patch(
        _PATCH_PROPOSAL.format(reading.id, multi.id), json={"value": ["rose_gold", "purple"]}
    )
    assert response.status_code == 400, response.text
    assert "purple" in response.text

    db.expire_all()
    assert db.query(ProductSpecFlyerProposal).filter_by(id=single.id).one().value == "s_trap"
    assert db.query(ProductSpecFlyerProposal).filter_by(id=multi.id).one().value == ["rose_gold"]


def test_apply_writes_a_one_tone_list_as_the_tone_itself(api, db):
    """`value_for_registry` stores a one-element list as the value: a re-derivation
    of the same words produces the scalar, and the two must not be different
    answers to "is this unchanged"."""
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-MV3", "SORENTO ONE PIECE WC ZZT-FLYRT-MV3")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-MV3", commit=True)
    reading = _reading(db, cards=[_card("ZZT-FLYRT-MV3", "Rose Gold")])
    batch = _batch(db, reading)
    proposal = _proposal(db, batch, product, spec_key="finish", value=["rose_gold"], kind="new")
    db.commit()

    response = client.post(_APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]})

    assert response.status_code == 200, response.text
    assert response.json()["refused"] == []
    assert _spec_of(db, product.id).values["finish"]["value"] == "rose_gold"


def test_patch_refuses_400_for_a_value_outside_the_closed_vocabulary(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-F2B", "SORENTO ONE PIECE WC ZZT-FLYRT-F2B")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-F2B", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.patch(
        _PATCH_PROPOSAL.format(reading.id, proposal.id), json={"value": "vacuum"}
    )

    assert response.status_code == 400, response.text
    body = response.json()
    assert "vacuum" in body["message"]

    db.expire_all()
    assert (
        db.query(ProductSpecFlyerProposal).filter_by(id=proposal.id).one().value == "s_trap"
    ), "a refused edit must not touch the stored row"


def test_patch_refuses_409_while_the_batch_is_not_proposed(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-F2C", "SORENTO ONE PIECE WC ZZT-FLYRT-F2C")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-F2C", "Washdown")])
    batch = _batch(db, reading, status="proposing")
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.patch(
        _PATCH_PROPOSAL.format(reading.id, proposal.id), json={"value": "p_trap"}
    )

    assert response.status_code == 409, response.text


def test_patch_refuses_409_when_the_row_is_already_applied(api, db):
    from datetime import datetime, timezone

    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-F2D", "SORENTO ONE PIECE WC ZZT-FLYRT-F2D")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-F2D", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    proposal.outcome = "applied"
    proposal.applied_at = datetime.now(timezone.utc).replace(tzinfo=None)
    proposal.applied_by = _USER["id"]
    db.add(proposal)
    db.commit()

    response = client.patch(
        _PATCH_PROPOSAL.format(reading.id, proposal.id), json={"value": "p_trap"}
    )

    assert response.status_code == 409, response.text


def test_patch_401s_without_a_principal(api, db):
    from app.dependencies import get_current_user
    from app.main import app
    from fastapi import HTTPException

    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-F2E", "SORENTO ONE PIECE WC ZZT-FLYRT-F2E")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-F2E", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    def _deny():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = _deny
    try:
        response = client.patch(
            _PATCH_PROPOSAL.format(reading.id, proposal.id), json={"value": "p_trap"}
        )
    finally:
        app.dependency_overrides[get_current_user] = lambda: _USER

    assert response.status_code == 401, response.text


def test_patch_403_names_page_view_when_it_is_the_missing_permission(api, db):
    client, allow = api
    allow.add(_EDIT)  # products.edit present, page.view missing
    product = _product(db, "ZZT-FLYRT-F2F", "SORENTO ONE PIECE WC ZZT-FLYRT-F2F")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-F2F", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.patch(
        _PATCH_PROPOSAL.format(reading.id, proposal.id), json={"value": "p_trap"}
    )

    assert response.status_code == 403, response.text
    assert _VIEW in response.text
    assert _EDIT not in response.text, "must name the FIRST missing permission, not both"


def test_patch_403_names_products_edit_when_it_is_the_missing_permission(api, db):
    client, allow = api
    allow.add(_VIEW)  # page.view present, products.edit missing
    product = _product(db, "ZZT-FLYRT-F2G", "SORENTO ONE PIECE WC ZZT-FLYRT-F2G")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-F2G", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.patch(
        _PATCH_PROPOSAL.format(reading.id, proposal.id), json={"value": "p_trap"}
    )

    assert response.status_code == 403, response.text
    assert _EDIT in response.text


# --------------------------------------------------------------------------- #
# AC-F.5 - GET carries allowed_values for a closed-vocabulary key
# --------------------------------------------------------------------------- #
def test_get_proposals_carries_allowed_values_for_closed_vocabulary_and_null_for_others(api, db):
    """A closed-vocabulary key (`trap_type`, enum) carries the merged registry
    vocabulary so the edit widget on the review page needs no second call
    (AC-F.5); a numeric key (`dim_length`) carries none, because there is no
    dropdown to populate."""
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-F5A", "SORENTO ONE PIECE WC ZZT-FLYRT-F5A")
    reading = _reading(
        db,
        cards=[_card("ZZT-FLYRT-F5A", "Washdown. S-Trap outlet 250mm. D: L680xW375xH770mm")],
    )
    batch = _batch(
        db, reading, status="proposed", proposal_count=2, product_count=1, new_count=2
    )
    _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    _proposal(db, batch, product, spec_key="dim_length", value=680, unit="mm", kind="new")
    db.commit()

    response = client.get(_GET_PROPOSALS.format(reading.id))

    assert response.status_code == 200, response.text
    proposals = {row["spec_key"]: row for row in response.json()["groups"][0]["proposals"]}

    trap = proposals["trap_type"]
    assert trap["allowed_values"] == ["s_trap", "p_trap"]

    dim = proposals["dim_length"]
    assert dim.get("allowed_values") in (None, [])


# --------------------------------------------------------------------------- #
# AC-G.1 - POST a manual proposal row onto an existing product group
# --------------------------------------------------------------------------- #
def test_add_row_creates_a_manual_proposal_with_a_live_kind_and_refreshes_counts(api, db):
    """AC-G.1 happy path: the row is created with `origin='manual'`, `kind`
    computed live (not copied from anywhere - there is nothing to copy from),
    `edited_by` stamped, and the batch's counts move with it. The product must
    already have a row in this batch - the review page only offers "Add
    specification" inside an existing product group (AC-G.4)."""
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-G1A", "SORENTO ONE PIECE WC ZZT-FLYRT-G1A")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-G1A", commit=True)
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G1A", "Washdown")])
    batch = _batch(
        db, reading, status="proposed", proposal_count=1, product_count=1, new_count=1
    )
    _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(
        _ADD_ROW.format(reading.id),
        json={"product_id": str(product.id), "spec_key": "seat_material", "value": "pp"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["spec_key"] == "seat_material"
    assert body["value"] == "pp"
    assert body["kind"] == "new"
    assert body.get("origin") == "manual"

    db.expire_all()
    row = (
        db.query(ProductSpecFlyerProposal)
        .filter_by(batch_id=batch.id, product_id=product.id, spec_key="seat_material")
        .one()
    )
    assert row.origin == "manual"
    assert row.edited_by == _USER["id"]
    assert row.kind == "new"

    stored_batch = db.query(ProductSpecFlyerBatch).filter_by(id=batch.id).one()
    assert stored_batch.proposal_count == 2
    assert stored_batch.new_count == 2


def test_add_row_refuses_409_while_the_batch_is_not_proposed(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-G1B", "SORENTO ONE PIECE WC ZZT-FLYRT-G1B")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G1B", "Washdown")])
    batch = _batch(db, reading, status="proposing")
    _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(
        _ADD_ROW.format(reading.id),
        json={"product_id": str(product.id), "spec_key": "seat_material", "value": "pp"},
    )

    assert response.status_code == 409, response.text


def test_add_row_refuses_404_for_a_key_the_registry_does_not_define(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-G1C", "SORENTO ONE PIECE WC ZZT-FLYRT-G1C")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G1C", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(
        _ADD_ROW.format(reading.id),
        json={
            "product_id": str(product.id),
            "spec_key": "zzt_not_a_real_key",
            "value": "anything",
        },
    )

    assert response.status_code == 404, response.text
    # A missing ROUTE also 404s with no `code` at all ({"detail": "Not Found"}),
    # so the status alone would pass before the route exists. Assert the body
    # shape too, or this test is green for the wrong reason until the route is
    # built and stays green for the wrong reason after it, if the real route
    # answered some other way.
    body = response.json()
    assert body.get("code") == "flyer_spec_unknown_key"
    assert "zzt_not_a_real_key" in body.get("message", "")


def test_add_row_refuses_404_for_a_product_not_in_this_batch(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    in_batch = _product(db, "ZZT-FLYRT-G1D-IN", "SORENTO ONE PIECE WC ZZT-FLYRT-G1D-IN")
    outside = _product(db, "ZZT-FLYRT-G1D-OUT", "SORENTO ONE PIECE WC ZZT-FLYRT-G1D-OUT")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G1D-IN", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    _proposal(db, batch, in_batch, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(
        _ADD_ROW.format(reading.id),
        json={"product_id": str(outside.id), "spec_key": "seat_material", "value": "pp"},
    )

    assert response.status_code == 404, response.text
    # Same reason as above: pin the body's `code`, reusing the apply route's own
    # `not_in_batch` (AC-C.1) rather than inventing a second name for one fact.
    body = response.json()
    assert body.get("code") == "not_in_batch"


def test_add_row_refuses_400_for_a_value_outside_the_closed_vocabulary(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-G1E", "SORENTO ONE PIECE WC ZZT-FLYRT-G1E")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-G1E", commit=True)
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G1E", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(
        _ADD_ROW.format(reading.id),
        json={"product_id": str(product.id), "spec_key": "seat_material", "value": "titanium"},
    )

    assert response.status_code == 400, response.text
    body = response.json()
    assert "titanium" in body["message"]


def test_add_row_refuses_409_for_a_duplicate_product_spec_key_row(api, db):
    """The row for (product, spec_key) already exists - the flyer proposed it, and
    the answer is to edit that row (AC-F.2 PATCH), not add a second one."""
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-G1F", "SORENTO ONE PIECE WC ZZT-FLYRT-G1F")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G1F", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(
        _ADD_ROW.format(reading.id),
        json={"product_id": str(product.id), "spec_key": "trap_type", "value": "p_trap"},
    )

    assert response.status_code == 409, response.text


def test_add_row_401s_without_a_principal(api, db):
    from app.dependencies import get_current_user
    from app.main import app
    from fastapi import HTTPException

    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-G1G", "SORENTO ONE PIECE WC ZZT-FLYRT-G1G")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G1G", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    def _deny():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = _deny
    try:
        response = client.post(
            _ADD_ROW.format(reading.id),
            json={"product_id": str(product.id), "spec_key": "seat_material", "value": "pp"},
        )
    finally:
        app.dependency_overrides[get_current_user] = lambda: _USER

    assert response.status_code == 401, response.text


def test_add_row_403_names_page_view_when_it_is_the_missing_permission(api, db):
    client, allow = api
    allow.add(_EDIT)  # products.edit present, page.view missing
    product = _product(db, "ZZT-FLYRT-G1H", "SORENTO ONE PIECE WC ZZT-FLYRT-G1H")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G1H", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(
        _ADD_ROW.format(reading.id),
        json={"product_id": str(product.id), "spec_key": "seat_material", "value": "pp"},
    )

    assert response.status_code == 403, response.text
    assert _VIEW in response.text
    assert _EDIT not in response.text, "must name the FIRST missing permission, not both"


def test_add_row_403_names_products_edit_when_it_is_the_missing_permission(api, db):
    client, allow = api
    allow.add(_VIEW)  # page.view present, products.edit missing
    product = _product(db, "ZZT-FLYRT-G1I", "SORENTO ONE PIECE WC ZZT-FLYRT-G1I")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G1I", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(
        _ADD_ROW.format(reading.id),
        json={"product_id": str(product.id), "spec_key": "seat_material", "value": "pp"},
    )

    assert response.status_code == 403, response.text
    assert _EDIT in response.text


# --------------------------------------------------------------------------- #
# AC-G.2 - a manual row applies source='human'; a flyer row still applies
# source='flyer' in the SAME request
# --------------------------------------------------------------------------- #
def test_apply_writes_a_manual_row_as_human_and_a_flyer_row_as_flyer_in_one_request(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-G2A", "SORENTO ONE PIECE WC ZZT-FLYRT-G2A")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-G2A", commit=True)

    reading = _reading(
        db, filename="ZZT-G2-Flyer.pdf", cards=[_card("ZZT-FLYRT-G2A", "Washdown. S-Trap outlet 250mm")]
    )
    batch = _batch(db, reading, status="proposed")
    flyer_row = _proposal(
        db, batch, product, spec_key="trap_type", value="s_trap", kind="new",
        evidence="S-TRAP OUTLET", origin="flyer",
    )
    manual_row = _proposal(
        db, batch, product, spec_key="seat_material", value="pp", kind="new", origin="manual"
    )
    db.commit()

    response = client.post(
        _APPLY.format(reading.id),
        json={"proposal_ids": [str(flyer_row.id), str(manual_row.id)]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["refused"] == []

    stored = _spec_of(db, product.id)
    assert stored.provenance["trap_type"]["source"] == "flyer"
    assert stored.provenance["trap_type"]["evidence"] == "flyer ZZT-G2-Flyer.pdf: S-TRAP OUTLET"
    assert stored.provenance["seat_material"]["source"] == "human"
    assert stored.provenance["seat_material"]["evidence"] == "set during flyer review"


# --------------------------------------------------------------------------- #
# AC-G.3 - DELETE a pending proposal row
# --------------------------------------------------------------------------- #
def test_delete_proposal_hard_deletes_a_pending_row_and_refreshes_counts(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-G3A", "SORENTO ONE PIECE WC ZZT-FLYRT-G3A")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G3A", "Washdown")])
    batch = _batch(
        db, reading, status="proposed", proposal_count=2, product_count=1, new_count=2
    )
    keep = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    doomed = _proposal(db, batch, product, spec_key="seat_material", value="pp", kind="new")
    db.commit()

    response = client.delete(_DELETE_PROPOSAL.format(reading.id, doomed.id))

    assert response.status_code == 200, response.text

    body = response.json()
    assert body["id"] == str(batch.id)
    assert body["reading_id"] == str(reading.id)
    assert body["status"] == "proposed"
    assert body["proposal_count"] == 1
    assert body["new_count"] == 1

    db.expire_all()
    assert (
        db.query(ProductSpecFlyerProposal).filter_by(id=doomed.id).first() is None
    ), "a dismissed row is HARD deleted, not tombstoned"
    assert db.query(ProductSpecFlyerProposal).filter_by(id=keep.id).first() is not None

    stored_batch = db.query(ProductSpecFlyerBatch).filter_by(id=batch.id).one()
    assert stored_batch.proposal_count == 1
    assert stored_batch.new_count == 1


def test_delete_proposal_refuses_409_when_the_row_is_already_applied(api, db):
    from datetime import datetime, timezone

    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-G3B", "SORENTO ONE PIECE WC ZZT-FLYRT-G3B")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G3B", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    proposal.outcome = "applied"
    proposal.applied_at = datetime.now(timezone.utc).replace(tzinfo=None)
    proposal.applied_by = _USER["id"]
    db.add(proposal)
    db.commit()

    response = client.delete(_DELETE_PROPOSAL.format(reading.id, proposal.id))

    assert response.status_code == 409, response.text

    db.expire_all()
    assert (
        db.query(ProductSpecFlyerProposal).filter_by(id=proposal.id).first() is not None
    ), "an applied row is never deleted, hard or soft"


def test_delete_proposal_refuses_409_while_the_batch_is_not_proposed(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-G3C", "SORENTO ONE PIECE WC ZZT-FLYRT-G3C")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G3C", "Washdown")])
    batch = _batch(db, reading, status="proposing")
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.delete(_DELETE_PROPOSAL.format(reading.id, proposal.id))

    assert response.status_code == 409, response.text


def test_delete_proposal_401s_without_a_principal(api, db):
    from app.dependencies import get_current_user
    from app.main import app
    from fastapi import HTTPException

    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-G3D", "SORENTO ONE PIECE WC ZZT-FLYRT-G3D")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G3D", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    def _deny():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = _deny
    try:
        response = client.delete(_DELETE_PROPOSAL.format(reading.id, proposal.id))
    finally:
        app.dependency_overrides[get_current_user] = lambda: _USER

    assert response.status_code == 401, response.text


def test_delete_proposal_403_names_page_view_when_it_is_the_missing_permission(api, db):
    client, allow = api
    allow.add(_EDIT)  # products.edit present, page.view missing
    product = _product(db, "ZZT-FLYRT-G3E", "SORENTO ONE PIECE WC ZZT-FLYRT-G3E")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G3E", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.delete(_DELETE_PROPOSAL.format(reading.id, proposal.id))

    assert response.status_code == 403, response.text
    assert _VIEW in response.text
    assert _EDIT not in response.text, "must name the FIRST missing permission, not both"


def test_delete_proposal_403_names_products_edit_when_it_is_the_missing_permission(api, db):
    client, allow = api
    allow.add(_VIEW)  # page.view present, products.edit missing
    product = _product(db, "ZZT-FLYRT-G3F", "SORENTO ONE PIECE WC ZZT-FLYRT-G3F")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-G3F", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    proposal = _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.delete(_DELETE_PROPOSAL.format(reading.id, proposal.id))

    assert response.status_code == 403, response.text
    assert _EDIT in response.text


# --------------------------------------------------------------------------- #
# S7 - the ids on the wire are UUIDs, so a malformed one is a 422 and not a 500
#
# `proposal_id` and `product_id` are UUID columns in Postgres. Typed `str` they
# reached the query as-is, and the driver raised on "not-a-uuid" - a 500 for a
# request the caller got wrong, which reads as our fault and tells them nothing.
# The apply body already declared `list[UUID]`; these are the three that did not.
# --------------------------------------------------------------------------- #
def test_patch_refuses_422_for_a_proposal_id_that_is_not_a_uuid(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-S7A", "SORENTO ONE PIECE WC ZZT-FLYRT-S7A")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-S7A", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.patch(
        _PATCH_PROPOSAL.format(reading.id, "not-a-uuid"), json={"value": "p_trap"}
    )

    assert response.status_code == 422, response.text


def test_delete_refuses_422_for_a_proposal_id_that_is_not_a_uuid(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-S7B", "SORENTO ONE PIECE WC ZZT-FLYRT-S7B")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-S7B", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.delete(_DELETE_PROPOSAL.format(reading.id, "not-a-uuid"))

    assert response.status_code == 422, response.text


def test_add_row_refuses_422_for_a_product_id_that_is_not_a_uuid(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(db, "ZZT-FLYRT-S7C", "SORENTO ONE PIECE WC ZZT-FLYRT-S7C")
    reading = _reading(db, cards=[_card("ZZT-FLYRT-S7C", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    response = client.post(
        _ADD_ROW.format(reading.id),
        json={"product_id": "nope", "spec_key": "seat_material", "value": "pp"},
    )

    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------- #
# S4 - AC-G.1's `flyer_spec_key_not_applicable` (400), the refusal the line asked
# for without naming: the key is real, this product's class simply cannot carry it
# --------------------------------------------------------------------------- #
def test_add_row_refuses_400_when_the_key_cannot_apply_to_this_products_class(api, db):
    """`bowl_count` is gated `applies_when: {class: [Kitchen Sink]}` and this
    product derives as a Water Closet, so derivation's own scope gate drops it -
    the same gate the propose pass runs, which is what stops a reviewer
    hand-placing a key the pass would never have proposed.

    400 and not 404: the registry defines `bowl_count`, so "unknown key" would
    send the reader off to add something that is already there."""
    client, allow = api
    allow.update({_VIEW, _EDIT})
    # The class has to be read from the DESCRIPTION's trailing noun, not inherited
    # from the category: `_apply_scope` refuses to drop a key on the strength of a
    # category label, so a class that came from the filing code gates nothing.
    product = _product(db, "ZZT-FLYRT-S4A", "SORENTO ZZT-FLYRT-S4A ONE PIECE WC")
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-S4A", commit=True)
    reading = _reading(db, cards=[_card("ZZT-FLYRT-S4A", "Washdown")])
    batch = _batch(db, reading, status="proposed")
    _proposal(db, batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()

    derived = _spec_of(db, product.id)
    assert derived.values["class"]["value"] == "Water Closet"
    assert derived.provenance["class"]["source"] == "derived"

    response = client.post(
        _ADD_ROW.format(reading.id),
        json={"product_id": str(product.id), "spec_key": "bowl_count", "value": 2},
    )

    assert response.status_code == 400, response.text
    body = response.json()
    assert body.get("code") == "flyer_spec_key_not_applicable"

    db.expire_all()
    assert (
        db.query(ProductSpecFlyerProposal)
        .filter_by(batch_id=batch.id, spec_key="bowl_count")
        .first()
        is None
    ), "nothing is stored for a refused key"


# --------------------------------------------------------------------------- #
# S5 - a proposal id is scoped to ITS batch: the same id under another reading's
# path is 404 `not_in_batch`, on both routes that name one
# --------------------------------------------------------------------------- #
def _two_batches(db, marker: str):
    """Two readings, each with its own batch, and one proposal row under the second."""
    product = _product(db, marker, f"SORENTO ONE PIECE WC {marker}")
    first = _reading(db, filename=f"{marker}-A.pdf", cards=[_card(marker, "Washdown")])
    second = _reading(db, filename=f"{marker}-B.pdf", cards=[_card(marker, "Washdown")])
    _batch(db, first, status="proposed")
    other_batch = _batch(db, second, status="proposed")
    row = _proposal(db, other_batch, product, spec_key="trap_type", value="s_trap", kind="new")
    db.commit()
    return first, row


def test_patch_refuses_404_for_a_proposal_belonging_to_another_reading(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    reading, other_row = _two_batches(db, "ZZT-FLYRT-S5A")

    response = client.patch(
        _PATCH_PROPOSAL.format(reading.id, other_row.id), json={"value": "p_trap"}
    )

    assert response.status_code == 404, response.text
    assert response.json().get("code") == "not_in_batch"

    db.expire_all()
    assert (
        db.query(ProductSpecFlyerProposal).filter_by(id=other_row.id).one().value
        == "s_trap"
    ), "the other batch's row is untouched"


def test_delete_refuses_404_for_a_proposal_belonging_to_another_reading(api, db):
    client, allow = api
    allow.update({_VIEW, _EDIT})
    reading, other_row = _two_batches(db, "ZZT-FLYRT-S5B")

    response = client.delete(_DELETE_PROPOSAL.format(reading.id, other_row.id))

    assert response.status_code == 404, response.text
    assert response.json().get("code") == "not_in_batch"

    db.expire_all()
    assert (
        db.query(ProductSpecFlyerProposal).filter_by(id=other_row.id).first() is not None
    ), "the other batch's row is still there"


# --------------------------------------------------------------------------- #
# S6 - a description-first dimension conflict, ticked, is written as `flyer`
# --------------------------------------------------------------------------- #
def test_apply_writes_a_ticked_description_first_dimension_conflict_as_flyer(api, db):
    """AC-F.1 for the OTHER kind of `conflict`. The neighbouring test covers a
    value a person authored; this one is the description-first rule (`dim_height`
    and its five siblings), where nobody authored anything - the master's own
    description states the height and the flyer's rounded number disagrees.

    Ticking it writes the flyer's number over the derived one, badged `flyer`,
    which is an AUTHORED source: the value now survives re-derivation. The cost
    of that is stated in the UAC (AC-F.1) and PLAN section 7c - the next derive
    that reads the description raises `human_override_conflict` for this key.
    """
    client, allow = api
    allow.update({_VIEW, _EDIT})
    product = _product(
        db, "ZZT-FLYRT-S6A", "SORENTO ONE PIECE WC ZZT-FLYRT-S6A L680XW375XH770"
    )
    db.commit()
    derive_for_code(db, "ZZT-FLYRT-S6A", commit=True)

    derived = _spec_of(db, product.id)
    assert derived.values["dim_height"]["value"] == 770
    assert derived.provenance["dim_height"]["source"] == "derived", "nobody authored it"

    reading = _reading(db, cards=[_card("ZZT-FLYRT-S6A", "L680 x W375 x H790mm")])
    batch = _batch(db, reading)
    # Stored as `change`; apply re-classifies it live and finds `conflict`,
    # because `dim_height` is description-first (AC-A.3).
    proposal = _proposal(
        db,
        batch,
        product,
        spec_key="dim_height",
        value=790,
        unit="mm",
        kind="change",
        evidence="L680 x W375 x H790mm",
        stored_value=770,
        stored_unit="mm",
        stored_source="description",
    )
    db.commit()

    response = client.post(
        _APPLY.format(reading.id), json={"proposal_ids": [str(proposal.id)]}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] == []
    assert body["applied"][0]["spec_key"] == "dim_height"

    stored = _spec_of(db, product.id)
    assert stored.values["dim_height"]["value"] == 790
    assert stored.provenance["dim_height"]["source"] == "flyer"
    assert "H790" in stored.provenance["dim_height"].get("evidence", "")

    db.expire_all()
    assert (
        db.query(ProductSpecFlyerProposal).filter_by(id=proposal.id).one().outcome
        == "applied"
    )
