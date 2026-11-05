"""TAG-TEMPLATE-DELETE-CONFIRM: deleting a tag template archives it.

PLAN: documentation/plans/dealer-kit/PLAN-tag-template-delete-confirm-05nov.md

A hard delete used to take every version, every product/combo link (ON DELETE CASCADE) and every
request line's template (SET NULL) with the row. Now the DELETE route stamps `archived_at`: the
row, its versions and every link stay, so the template can be restored, while the list, the
request designer's published list and the product/combo pickers stop offering it.

`GET /tag-templates/{id}/usage` is what the confirm dialog reads to say how many products, combos
and requests use the template.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app  # noqa: E402  (first app import)
from app.models.dealer_kit import (
    ComboTagTemplate,
    ProductTagTemplate,
    TagTemplate,
    TagTemplateVersion,
)
from app.services.dealer_kit import product_tag_template_service, tag_template_service
from tests._pg_fixture import unique_code
from tests.test_product_combos import _combo, _product
from tests.test_tag_template_bulk_delete import _SORENTO, _create_template, api  # noqa: F401

BASE = "/api/v1/dealer-kit/tag-templates"


def _publish(client: TestClient, template_id: str) -> None:
    res = client.post(f"{BASE}/{template_id}/publish", json={})
    assert res.status_code == 200, res.text


def _request_line(db, product_id: str, template_id: str) -> str:
    from app.models.access import RespondContact
    from app.models.price_tag import PriceTagRequest, PriceTagRequestLine

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("contact"),
    )
    db.add(contact)
    db.flush()
    request = PriceTagRequest(
        id=str(uuid.uuid4()),
        company_id=_SORENTO,
        contact_id=contact.id,
        doc_number=unique_code("PT")[:40],
        status="new",
    )
    db.add(request)
    db.flush()
    line = PriceTagRequestLine(
        id=str(uuid.uuid4()),
        request_id=request.id,
        line_type="product",
        product_id=product_id,
        tag_template_id=template_id,
        quantity=1,
        sort_order=0,
    )
    db.add(line)
    db.flush()
    return line.id


def _used_template(db, client: TestClient) -> tuple[str, str, str, str]:
    """A published price tag template linked to two products, one combo and one request line."""
    template_id = _create_template(client)
    _publish(client, template_id)
    first = _product(db, "TTD1")
    second = _product(db, "TTD2")
    combo = _combo(db, first, "Set")
    db.add_all(
        [
            ProductTagTemplate(product_id=first.id, template_id=template_id),
            ProductTagTemplate(product_id=second.id, template_id=template_id),
            ComboTagTemplate(combo_id=combo.id, template_id=template_id),
        ]
    )
    db.flush()
    line_id = _request_line(db, first.id, template_id)
    db.commit()
    return template_id, first.id, combo.id, line_id


def test_delete_route_archives_and_keeps_row_versions_links_and_request_line(api):
    from app.models.price_tag import PriceTagRequestLine

    db, _as, _scope = api
    with TestClient(app) as client:
        template_id, product_id, combo_id, line_id = _used_template(db, client)

        res = client.delete(f"{BASE}/{template_id}")
        assert res.status_code == 204, res.text

    db.expire_all()
    row = db.query(TagTemplate).filter(TagTemplate.id == template_id).first()
    assert row is not None
    assert row.archived_at is not None
    assert row.published_version_id is not None
    assert db.query(TagTemplateVersion).filter(TagTemplateVersion.template_id == template_id).count() == 1
    assert db.query(ProductTagTemplate).filter(ProductTagTemplate.template_id == template_id).count() == 2
    assert db.query(ComboTagTemplate).filter(ComboTagTemplate.template_id == template_id).count() == 1
    assert db.get(PriceTagRequestLine, line_id).tag_template_id == template_id


def test_list_and_published_list_hide_an_archived_template(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        kept = _create_template(client)
        archived = _create_template(client)
        _publish(client, kept)
        _publish(client, archived)
        assert client.delete(f"{BASE}/{archived}").status_code == 204

        listed = {t["id"] for t in client.get(BASE).json()}
        published = {t["id"] for t in client.get(BASE, params={"published": "true"}).json()}
        detail = client.get(f"{BASE}/{archived}")

    assert kept in listed and archived not in listed
    assert kept in published and archived not in published
    assert detail.status_code == 404


def test_product_and_combo_pickers_hide_an_archived_template(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        template_id, product_id, combo_id, _line = _used_template(db, client)
        assert client.delete(f"{BASE}/{template_id}").status_code == 204

    db.expire_all()
    assert product_tag_template_service.linked_items(db, product_id) == []
    assert product_tag_template_service.linked_combo_items(db, combo_id) == []
    assert product_tag_template_service.published_links(db, [product_id]).get(product_id, []) == []


def test_bulk_delete_archives_too(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        a = _create_template(client)
        b = _create_template(client)

    assert tag_template_service.bulk_delete(db, [a, b]) == {"deleted": 2}
    db.expire_all()
    rows = db.query(TagTemplate).filter(TagTemplate.id.in_([a, b])).all()
    assert len(rows) == 2
    assert all(row.archived_at is not None for row in rows)


def test_deleting_an_archived_template_again_is_a_404(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        template_id = _create_template(client)
        assert client.delete(f"{BASE}/{template_id}").status_code == 204
        assert client.delete(f"{BASE}/{template_id}").status_code == 404


def test_usage_counts_products_combos_and_requests(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        template_id, _product_id, _combo_id, _line = _used_template(db, client)
        unused = _create_template(client)

        used = client.get(f"{BASE}/{template_id}/usage")
        none = client.get(f"{BASE}/{unused}/usage")
        missing = client.get(f"{BASE}/{uuid.uuid4()}/usage")

    assert used.status_code == 200, used.text
    assert used.json() == {"products": 2, "combos": 1, "requests": 1}
    assert none.json() == {"products": 0, "combos": 0, "requests": 0}
    assert missing.status_code == 404


def test_saving_a_products_template_set_keeps_the_link_to_an_archived_template(api):
    """The product page only sees live templates, so its save must not drop (or keep the default
    on) a link to an archived one: that link is what a restore brings back."""
    db, _as, _scope = api
    with TestClient(app) as client:
        archived, live, added = (_create_template(client) for _ in range(3))
        for template_id in (archived, live, added):
            _publish(client, template_id)
    product = _product(db, "TTD3")
    db.add_all(
        [
            ProductTagTemplate(
                product_id=product.id, template_id=archived, default_list=True, default_selling=True
            ),
            ProductTagTemplate(product_id=product.id, template_id=live),
        ]
    )
    db.commit()
    tag_template_service.delete_template(db, archived)

    product_tag_template_service.set_product_templates(
        db, product.id, [live, added], user_id=None, default_template_id=added
    )
    db.commit()
    db.expire_all()

    # PRICETAG-COMBO-FORMAT: the default is two per-type flags; the legacy default_template_id
    # sets both on a template with no price type.
    links = {
        link.template_id: (link.default_list, link.default_selling)
        for link in db.query(ProductTagTemplate).filter(ProductTagTemplate.product_id == product.id)
    }
    assert links == {archived: (False, False), live: (False, False), added: (True, True)}
    items = product_tag_template_service.linked_items(db, product.id)
    assert {i["id"]: i["is_default"] for i in items} == {live: False, added: True}
