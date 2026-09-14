"""Product combos: the catalogue package a product is sold as (S1, D1).

UAC: `documentation/plans/dealer-kit/price-tag-combos-acceptance-criteria.md`
(AC-S1-2, AC-S1-3, AC-S1-5, AC-S1-6, AC-S1-7, AC-S1-8).

Written test-FIRST (PRINCIPLES.md Phase 2). Neither `app/models/product_combo.py`
nor the routes exist yet, so the model import below fails the WHOLE FILE with one
`ImportError` at collection - every case here is red for that one reason until S1
lands, not for six unrelated ones.

Route contract (the frontend already mocks it, Phase 1, committed - the header of
`sorento_crm_frontend/.../products/services/productComboService.ts` is the
authority where it and the plan differ):

    GET    /api/v1/master-data/products/{id}/combos          -> {"data": [...]}
    POST   /api/v1/master-data/products/{id}/combos          -> row (201), 409
    PATCH  /api/v1/master-data/product-combos/{combo_id}     -> row
    DELETE /api/v1/master-data/product-combos/{combo_id}     -> 204
    POST   /api/v1/master-data/product-combos/{id}/parts     -> row (201), 422
    PATCH  /api/v1/master-data/product-combo-parts/{id}      -> row
    DELETE /api/v1/master-data/product-combo-parts/{id}      -> 204
    GET    /api/v1/master-data/products/{id}/sold-with       -> {"data": [...]}

No dedicated permission slug (AC-X-5): reads take `master_data.products.view`,
writes take `master_data.products.edit`. Combos are company scoped THROUGH the
host, so a caller scoped elsewhere gets 404 on the host, never an empty list.

Auth + scope pattern borrowed from `tests/test_product_companion_rules.py`, which
is the #779 precedent this slice copies.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.models.base import set_company_scope
from app.models.company import Company
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import User, UserStatus
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.user_service import UserPermissionService

# THE red import. Everything below fails to collect until
# `app/models/product_combo.py` exists with these two names (PLAN D1).
from app.models.product_combo import (  # noqa: E402
    ProductCombo,
    ProductComboPart,
)

from tests._pg_fixture import blank_session, unique_code

COMBOS = "/api/v1/master-data/products/{product_id}/combos"
SOLD_WITH = "/api/v1/master-data/products/{product_id}/sold-with"
COMBO = "/api/v1/master-data/product-combos/{combo_id}"
COMBO_PARTS = "/api/v1/master-data/product-combos/{combo_id}/parts"
COMBO_PART = "/api/v1/master-data/product-combo-parts/{part_id}"

SORENTO = DEFAULT_COMPANY_ID
MOCHA = "00000000-0000-0000-0000-000000000002"
VIEW = "master_data.products.view"
EDIT = "master_data.products.edit"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _product(db, stem: str, *, company_id: str = SORENTO, class_label: str | None = None) -> Product:
    """A product and its whole FK chain.

    CI's database is empty, so the category and the uom are seeded here rather
    than borrowed - an invented FK aborts the transaction on Postgres.
    """
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("u")[:20], uom_name="Unit")
    category = ProductCategory(
        id=_uid(),
        category_code=unique_code("cat")[:50],
        category_name="ZZT combo cat",
        class_label=class_label,
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        company_id=company_id,
        product_code=unique_code(stem),
        product_name=f"ZZT {stem}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _mocha(db) -> None:
    """The second company. Not seeded by the blank schema - only Sorento is."""
    existing = db.query(Company).filter(Company.id == MOCHA).first()
    if existing is not None:
        return
    db.add(Company(id=MOCHA, name="ZZT Mocha", code=unique_code("MCH")[:20], is_active=True))
    db.flush()


def _combo(db, host: Product, name: str, *, sort_order: int = 0) -> ProductCombo:
    row = ProductCombo(
        id=_uid(),
        host_product_id=host.id,
        name=name,
        sort_order=sort_order,
    )
    db.add(row)
    db.flush()
    return row


def _part(db, combo: ProductCombo, product: Product, *, choice_group=None, sort_order=0):
    row = ProductComboPart(
        id=_uid(),
        combo_id=combo.id,
        part_product_id=product.id,
        choice_group=choice_group,
        sort_order=sort_order,
    )
    db.add(row)
    db.flush()
    return row


def _install_overrides(db, caller: dict, company_id):
    def _override_db():
        yield db

    def _override_scope(_db=Depends(get_db)):
        scope = frozenset({company_id}) if company_id else None
        set_company_scope(_db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[get_current_user_or_api_key] = lambda: caller
    app.dependency_overrides[apply_company_scope] = _override_scope


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_or_api_key, None)
    app.dependency_overrides.pop(apply_company_scope, None)


def _caller(db, allow: set[str], monkeypatch, *, company_id=SORENTO) -> TestClient:
    user = User(
        id=_uid(),
        email=f"{unique_code('combo-caller')}@zzt.test",
        name="ZZT Combo Caller",
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    db.flush()
    caller = {"id": str(user.id), "email": user.email}

    _install_overrides(db, caller, company_id)
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    return TestClient(app)


# --------------------------------------------------------------------------- AC-S1-2


def test_product_combos_create_duplicate_name_409(db, monkeypatch):
    """A host's combo names are unique: "3 in 1" twice is a 409 the modal shows inline.

    Not a 422 and not a silent second row - the catalogue names a package once,
    and two combos called the same thing on one cabinet is the marketing user
    having lost their place, which the form has to say out loud.
    """
    host = _product(db, "SRTBF11834")
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    url = COMBOS.format(product_id=host.id)

    first = client.post(url, json={"name": "3 in 1"})
    assert first.status_code == 201, first.text
    assert first.json()["name"] == "3 in 1"
    # Created EMPTY - parts are added one at a time afterwards.
    assert first.json()["parts"] == []

    second = client.post(url, json={"name": "3 in 1"})
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "COMBO_NAME_TAKEN"

    # And a DIFFERENT name on the same host is still fine.
    other = client.post(url, json={"name": "4 in 1"})
    assert other.status_code == 201, other.text


# --------------------------------------------------------------------------- AC-S1-3


def test_combo_part_refuses_host_and_duplicate(db, monkeypatch):
    """The host cannot be a part of its own combo, and no product twice.

    Both are answered inline under the picker, so both have to be a named 422
    rather than a generic integrity error the form can only render as a toast.
    """
    host = _product(db, "SRTBF11834")
    mirror = _product(db, "SRTMR502-BL")
    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    combo = client.post(COMBOS.format(product_id=host.id), json={"name": "3 in 1"}).json()
    url = COMBO_PARTS.format(combo_id=combo["id"])

    as_host = client.post(url, json={"part_product_id": host.id})
    assert as_host.status_code == 422, as_host.text
    assert as_host.json()["code"] == "COMBO_PART_IS_HOST"

    added = client.post(url, json={"part_product_id": mirror.id})
    assert added.status_code == 201, added.text
    # The row names the part by its own code, name and dimensions - the reader
    # never sees an id (AC-X-2).
    assert added.json()["code"] == mirror.product_code
    assert added.json()["product_name"] == mirror.product_name
    assert added.json()["choice_group"] is None

    again = client.post(url, json={"part_product_id": mirror.id})
    assert again.status_code == 422, again.text
    assert again.json()["code"] == "COMBO_PART_DUPLICATE"


# --------------------------------------------------------------------------- AC-S1-5


def test_combo_delete_cascades_parts(db, monkeypatch):
    """Deleting a combo takes its parts with it and leaves the products alone.

    And the second half of AC-S1-5: a part product already named by a SUBMITTED
    request line's part row is still deletable from the combo. The line keeps its
    own product reference - what the salesperson asked for is a fact about that
    request, not a live pointer into the catalogue's current packaging.
    """
    from app.models.price_tag import PriceTagRequest, PriceTagRequestLine
    # S2's table. Named here because the second half of AC-S1-5 is exactly the
    # question "does a request row pin a combo part in place?".
    from app.models.price_tag import PriceTagRequestLinePart

    host = _product(db, "SRTBF11834")
    mirror = _product(db, "SRTMR502-BL")
    combo = _combo(db, host, "3 in 1")
    part = _part(db, combo, mirror)

    from app.models.access import RespondContact

    # `price_tag_requests.contact_id` is NOT NULL, so the chain starts at a
    # contact rather than at the request.
    contact = RespondContact(
        id=_uid(), phone_number=f"+60{uuid.uuid4().hex[:9]}", name=unique_code("contact")
    )
    db.add(contact)
    db.flush()
    request = PriceTagRequest(
        id=_uid(),
        company_id=SORENTO,
        contact_id=contact.id,
        doc_number=unique_code("PT")[:40],
        status="new",
    )
    db.add(request)
    db.flush()
    line = PriceTagRequestLine(
        id=_uid(),
        request_id=request.id,
        line_type="product",
        product_id=host.id,
        combo_id=combo.id,
        quantity=1,
        sort_order=0,
    )
    db.add(line)
    db.flush()
    db.add(
        PriceTagRequestLinePart(
            id=_uid(),
            line_id=line.id,
            product_id=mirror.id,
            role=None,
            candidates=[],
            sort_order=0,
        )
    )
    db.flush()

    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    # The PART alone first: a submitted line naming the same product does not
    # pin it.
    removed = client.delete(COMBO_PART.format(part_id=part.id))
    assert removed.status_code == 204, removed.text

    # Put it back, then delete the whole combo: the parts go with it.
    part = _part(db, combo, mirror)
    deleted = client.delete(COMBO.format(combo_id=combo.id))
    assert deleted.status_code == 204, deleted.text

    assert db.query(ProductCombo).filter(ProductCombo.id == combo.id).first() is None
    assert (
        db.query(ProductComboPart).filter(ProductComboPart.combo_id == combo.id).count() == 0
    ), "deleting a combo must cascade its parts, not orphan them"
    # Neither product was touched, and the request line survives with its combo
    # reference cleared rather than being deleted along with it.
    assert db.query(Product).filter(Product.id == mirror.id).first() is not None
    db.refresh(line)
    assert line.combo_id is None
    assert (
        db.query(PriceTagRequestLinePart)
        .filter(PriceTagRequestLinePart.line_id == line.id)
        .count()
        == 1
    ), "the line keeps what the salesperson asked for even after the combo is gone"


# --------------------------------------------------------------------------- AC-S1-6


def test_sold_with_lists_hosts_across_combos(db, monkeypatch):
    """The mirror on a PART's own page names every host + combo it belongs to.

    Across hosts, not just the first one found: a basin sold with two different
    cabinets is exactly the case the read-only list exists for, and one row would
    quietly hide the other cabinet.
    """
    basin = _product(db, "SRTBS900-WH")
    cabinet_a = _product(db, "SRTBF11834")
    cabinet_b = _product(db, "SRTBF11835")
    combo_a = _combo(db, cabinet_a, "3 in 1")
    combo_b = _combo(db, cabinet_b, "4 in 1")
    _part(db, combo_a, basin, choice_group="Basin")
    _part(db, combo_b, basin, choice_group="Basin")

    # A combo on a third host that does NOT name the basin must not appear.
    other = _product(db, "SRTBF11836")
    _combo(db, other, "2 in 1")

    client = _caller(db, {VIEW}, monkeypatch)
    response = client.get(SOLD_WITH.format(product_id=basin.id))
    assert response.status_code == 200, response.text

    rows = response.json()["data"]
    assert len(rows) == 2
    assert {(row["host_code"], row["combo_name"]) for row in rows} == {
        (cabinet_a.product_code, "3 in 1"),
        (cabinet_b.product_code, "4 in 1"),
    }
    # Codes and names, because the list is rendered as "SRTBF11834 - 3 in 1".
    for row in rows:
        assert row["host_name"]
        assert row["host_product_id"] in {cabinet_a.id, cabinet_b.id}


# --------------------------------------------------------------------------- AC-S1-7


def test_combos_cross_company_404(db, monkeypatch):
    """A caller scoped to Mocha gets 404 on a Sorento host, never an empty list.

    An empty list reads as "this cabinet has no packages" and invites marketing
    to create a second set of combos on a product they cannot see. 404 says the
    product is not theirs.
    """
    _mocha(db)
    host = _product(db, "SRTBF11834", company_id=SORENTO)
    _combo(db, host, "3 in 1")

    client = _caller(db, {VIEW, EDIT}, monkeypatch, company_id=MOCHA)

    listed = client.get(COMBOS.format(product_id=host.id))
    assert listed.status_code == 404, listed.text

    # The write path is scoped through the same host resolution.
    created = client.post(COMBOS.format(product_id=host.id), json={"name": "Sneaky"})
    assert created.status_code == 404, created.text

    sold_with = client.get(SOLD_WITH.format(product_id=host.id))
    assert sold_with.status_code == 404, sold_with.text


# --------------------------------------------------------------------------- AC-S1-8


def test_business_gate_ignores_combos(db):
    """A stock question for the cabinet resolves the CABINET, with no combo read.

    The owner rejected a product set as the package object precisely because the
    chatbot searches sets. Combos must stay invisible to it: the resolver answers
    the host product alone, and never reads the combo tables on the way.
    """
    from sqlalchemy import event

    from app.models.base import company_scope
    from app.services import entity_resolver

    host = _product(db, "SRTBF11834")
    mirror = _product(db, "SRTMR502-BL")
    combo = _combo(db, host, "3 in 1")
    _part(db, combo, mirror)

    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", _record)
    try:
        with company_scope(db, frozenset({SORENTO})):
            result = entity_resolver.resolve_references(db, host.product_code)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _record)

    matches = [
        match
        for resolution in result.resolutions
        for match in resolution.matches
    ]
    assert matches, "the cabinet's own code must still resolve"
    assert {match.entity_type for match in matches} == {"product"}
    assert {match.id for match in matches} == {host.id}

    # The mirror is NOT dragged in as part of the answer, and no combo table was
    # touched to produce it.
    assert mirror.id not in {match.id for match in matches}
    combo_reads = [s for s in statements if "product_combo" in s.lower()]
    assert combo_reads == [], (
        "the resolver read the combo tables: " + "; ".join(combo_reads[:2])
    )
