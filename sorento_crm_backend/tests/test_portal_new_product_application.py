"""NEW-PRODUCT-APP portal surface, red-first. Owner 18 Oct: "make sure we have equivalent
portal views"; crew PQ1 (b): no Supplier and no Cost price on the portal; PQ2 (a): the
portal applicant hears through its linked staff user.

Through TestClient because mounting order matters (the generic `/submissions/{kind}`
handlers must not shadow these literal paths). Pattern: tests/test_portal_sample_request.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._pg_fixture import blank_session
from ._npa_v4_support import (
    IMAGE_FORMATS,
    REFUSED_LINE_KEYS,
    refused_value,
    SHEET_LABELS,
    downloaded_name,
    image_bytes,
    install_storage,
    label_rows,
    noon,
    open_workbook,
    seed_attachment,
    seed_attachment_type,
    sheet_values,
    text_of,
)
from ._sample_request_seed import MARKER, make_product, make_user, second_company, sorento, uid

PORTAL = "/api/v1/public/portal"
BASE = f"{PORTAL}/submissions/new_product_application"
NPA = f"{PORTAL}/new-product-application"
KIND = "new_product_application"


def _contact(db, *, granted: bool) -> str:
    from app.models.access import RespondContact
    from tests._portal_grant import grant_portal_forms, link_contact_company

    contact = RespondContact(
        id=uid(), phone_number=f"+60{uid().replace('-', '')[:9]}", name=f"{MARKER} contact"
    )
    db.add(contact)
    db.flush()
    link_contact_company(db, contact.id)
    if granted:
        grant_portal_forms(db, contact.id, [KIND])
    return contact.id


def _inquiry(db, contact_id, **over):
    from app.models.procurement import StockInquiry

    row = StockInquiry(
        id=uid(),
        inquiry_number=f"SI26-Z{uid()[:4]}",
        product_code="XY-1234-MB & XY-1234-BG",
        item_description="Kitchen sink, nanograin finish",
        project_customer=f"{MARKER} EXAMPLE DEVELOPER SDN BHD",
        project_name=f"{MARKER} EXAMPLE RESIDENCE, TOWER B",
        quantity="55",
        delivery_date="2028-01-17",
        purchasing_response="Supplier can make it, please apply for a new code.",
        status="responded",
        contact_id=contact_id,
        space_id="zzt-space",
    )
    for k, v in over.items():
        setattr(row, k, v)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def portal(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.v1.public.portal import get_portal_token
    from app.database import get_db
    from app.main import app as the_app
    from app.models.base import company_scope
    from app.models.portal import PortalToken
    from app.models.user import User
    from app.services.notification_service import NotificationService

    sent = []
    monkeypatch.setattr(
        NotificationService,
        "create_with_channel_preferences",
        lambda self, **kw: sent.append((kw.get("user_id"), kw.get("type"))),
    )

    with blank_session() as db:
        company_id = sorento(db)
        other_company = second_company(db)
        granted = _contact(db, granted=True)
        granted_b = _contact(db, granted=True)
        ungranted = _contact(db, granted=False)
        linked_user = make_user(db, f"{MARKER} linked salesman")
        db.get(User, linked_user).respond_contact_id = granted
        with company_scope(db, frozenset({company_id})):
            product = make_product(db)
        with company_scope(db, frozenset({other_company})):
            foreign = make_product(db)
        mine = _inquiry(db, granted)
        mine_open = _inquiry(db, granted, status="pending_purchasing")
        theirs = _inquiry(db, granted_b)
        db.add(
            PortalToken(
                id=uid(),
                token="zzt-token",
                contact_id=granted,
                space_id="zzt-space",
                expires_at=datetime.utcnow() + timedelta(days=30),
                verified_at=datetime.utcnow() - timedelta(minutes=5),
            )
        )
        db.commit()

        state = {"contact": granted}

        def _token():
            return PortalToken(id=uid(), contact_id=state["contact"], space_id="zzt-space")

        the_app.dependency_overrides[get_db] = lambda: db
        the_app.dependency_overrides[get_portal_token] = _token
        try:
            with TestClient(the_app, headers={"X-Portal-Token": "zzt-token"}) as c:
                yield SimpleNamespace(
                    c=c, db=db, state=state, company_id=company_id, other_company=other_company,
                    granted=granted, granted_b=granted_b, ungranted=ungranted,
                    linked_user=linked_user, product=product, foreign=foreign, mine=mine,
                    mine_open=mine_open, theirs=theirs, sent=sent,
                )
        finally:
            the_app.dependency_overrides.clear()


def _as(p, contact_id):
    p.state["contact"] = contact_id
    return p.c


def _line(p, **over):
    body = {
        "proposed_code": "XY-1234-MB",
        "description": "Kitchen sink, nanograin finish",
        "expected_qty": "55",
    }
    body.update(over)
    return body


def _create(p, contact=None, **over):
    body = {"stock_inquiry_id": p.mine.id, "customer_name": "typed", "lines": [_line(p)]}
    body.update(over)
    res = _as(p, contact or p.granted).post(BASE, json=body)
    assert res.status_code == 201, res.text
    return res.json()


# ------------------------------------------------------------------ registration


def test_kind_is_grantable_not_default_and_labelled():
    from app.services import portal_form_visibility_service as vis
    from app.services.portal_service import GRANTABLE_PORTAL_FORM_TYPES, SUPPORTED_TYPES

    assert KIND in GRANTABLE_PORTAL_FORM_TYPES
    assert KIND not in SUPPORTED_TYPES
    assert vis._KIND_LABELS[KIND] == "New Product Application"


def test_kind_has_no_revision_settings_row():
    """It has no portal revision adapter (Revise is its own move), so the revision settings
    list must not offer it (the #1763 lesson for sample_request)."""
    from app.api.v1.forms.revision_configs import REVISABLE_PORTAL_FORM_TYPES

    assert KIND not in REVISABLE_PORTAL_FORM_TYPES


ROUTES = [
    ("get", BASE, None),
    ("post", BASE, {}),
    ("get", f"{BASE}/{{id}}", None),
    ("put", f"{BASE}/{{id}}", {}),
    ("post", f"{BASE}/{{id}}/submit", None),
    ("post", f"{BASE}/{{id}}/revise", {"reason": "x"}),
    ("post", f"{BASE}/{{id}}/cancel", None),
    ("get", f"{NPA}/inquiries", None),
    ("get", f"{NPA}/prefill?stock_inquiry_id={{id}}", None),
    ("get", f"{NPA}/lookups/brands", None),
    ("get", f"{NPA}/customers?q=zzt", None),
    ("get", f"{BASE}/{{id}}/download", None),
    ("post", f"{BASE}/{{id}}/lines/{{id}}/images/copy", {"attachment_id": "x"}),
    ("delete", f"{BASE}/{{id}}/lines/{{id}}/images/{{id}}", None),
]


@pytest.mark.parametrize("method, url, body", ROUTES)
def test_no_grant_is_403_on_every_route(portal, method, url, body):
    c = _as(portal, portal.ungranted)
    url = url.replace("{id}", uid())
    res = getattr(c, method)(url, **({"json": body} if body is not None else {}))
    assert res.status_code == 403, (url, res.status_code, res.text)
    assert res.json().get("code") == "FORM_TYPE_NOT_VISIBLE"


# ------------------------------------------------------------------ create from my responded inquiry


def test_inquiries_lists_only_my_responded_ones(portal):
    res = _as(portal, portal.granted).get(f"{NPA}/inquiries")
    assert res.status_code == 200, res.text
    ids = {r["id"] for r in res.json()}
    assert portal.mine.id in ids
    assert portal.mine_open.id not in ids
    assert portal.theirs.id not in ids


def test_prefill_from_my_responded_inquiry_copies_text(portal):
    res = _as(portal, portal.granted).get(f"{NPA}/prefill", params={"stock_inquiry_id": portal.mine.id})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["customer_id"] is None
    assert body["lines"][0]["proposed_code"] == "XY-1234-MB & XY-1234-BG"


@pytest.mark.parametrize("which", ["theirs", "mine_open"])
def test_prefill_refuses_someone_elses_or_an_unanswered_inquiry(portal, which):
    target = getattr(portal, which)
    res = _as(portal, portal.granted).get(f"{NPA}/prefill", params={"stock_inquiry_id": target.id})
    assert res.status_code == 404


def test_create_links_only_my_own_inquiry(portal):
    res = _as(portal, portal.granted).post(
        BASE, json={"stock_inquiry_id": portal.theirs.id, "lines": [_line(portal)]}
    )
    assert res.status_code == 422, res.text


def test_create_is_owned_by_the_contact_and_its_linked_user(portal):
    d = _create(portal)
    assert d["source"] == "portal"
    assert d["status"] == "draft"
    assert d["application_no"].startswith("NPA-")
    assert d["applicant_id"] == portal.linked_user


# ------------------------------------------------------------------ v4 write body (AC-NPA-70) and PQ1 read side (AC-NPA-78)


def _refs(p):
    from types import SimpleNamespace

    from app.models.base import company_scope
    from app.models.procurement import Supplier
    from app.models.product import ItemType

    with company_scope(p.db, frozenset({p.company_id})):
        item_type = ItemType(id=uid(), item_type_code=f"ZZT{uid()[:6]}", item_type_name="KITCHEN SINK")
        supplier = Supplier(id=uid(), supplier_code=f"ZZT-S{uid()[:6]}", supplier_name="x")
        p.db.add_all([item_type, supplier])
        p.db.flush()
    return SimpleNamespace(
        category=p.product.category_id, uom=p.product.base_uom_id, item_type=item_type.id, supplier=supplier.id
    )


@pytest.mark.parametrize("key", REFUSED_LINE_KEYS)
def test_portal_a_removed_line_key_is_422_naming_the_field(portal, key):
    """Was "cannot set supplier or cost" (PQ1 b); v4 refuses every key the paper form dropped."""
    res = _as(portal, portal.granted).post(
        BASE, json={"lines": [_line(portal, **{key: refused_value(key, _refs(portal))})]}
    )
    assert res.status_code == 422, res.text
    assert key in res.text
    d = _create(portal)
    res = _as(portal, portal.granted).put(
        f"{BASE}/{d['id']}", json={"lines": [_line(portal, **{key: refused_value(key, _refs(portal))})]}
    )
    assert res.status_code == 422, res.text
    assert key in res.text


def test_portal_the_paper_fields_round_trip(portal):
    d = _create(
        portal,
        lines=[_line(portal, dimension="600 x 450 mm", material="Steel", thickness="1.2 mm", packing="1 per box")],
    )
    got = _as(portal, portal.granted).get(f"{BASE}/{d['id']}").json()["lines"][0]
    assert (got["dimension"], got["material"], got["thickness"], got["packing"]) == (
        "600 x 450 mm", "Steel", "1.2 mm", "1 per box",
    )
    assert got["images"] == []


def _staff_fill(p, aid, *, cost="12.50", lead="3 weeks", link=None):
    """What purchasing leaves on the record (the portal has no route to write it)."""
    from decimal import Decimal

    from app.models.new_product_application import NewProductApplication

    row = p.db.get(NewProductApplication, aid)
    row.lead_time = lead
    row.lines[0].cost_price = Decimal(cost)
    if link is not None:
        row.lines[0].opened_product_id = link
    p.db.commit()


def test_portal_detail_shows_cost_leadtime_and_the_linked_supplier_read_only(portal):
    """AC-NPA-78 (PQ1): cost, lead time and supplier are shown; group, UOM and list price never."""
    from app.models.base import company_scope
    from app.models.procurement import ProductSupplier, Supplier

    d = _create(portal)
    with company_scope(portal.db, frozenset({portal.company_id})):
        supplier = Supplier(id=uid(), supplier_code=f"ZZT-S{uid()[:6]}", supplier_name="Example Supplier Sdn Bhd")
        portal.db.add(supplier)
        portal.db.flush()
        portal.db.add(
            ProductSupplier(id=uid(), product_id=portal.product.id, supplier_id=supplier.id, is_primary_supplier=True)
        )
        portal.db.flush()
    _staff_fill(portal, d["id"], link=portal.product.id)

    got = _as(portal, portal.granted).get(f"{BASE}/{d['id']}").json()
    assert got["lead_time"] == "3 weeks"
    line = got["lines"][0]
    assert line["cost_price"] == "12.50"
    assert line["opened_supplier_name"] == "Example Supplier Sdn Bhd"
    for key in ("opened_category_name", "opened_base_uom_name", "opened_list_price", "selling_price",
                "supplier_item_code", "category_id", "base_uom_id"):
        assert key not in line, key


def test_portal_detail_carries_the_cost_keys_even_before_purchasing_fills_them(portal):
    d = _create(portal)
    got = _as(portal, portal.granted).get(f"{BASE}/{d['id']}").json()
    assert "lead_time" in got and got["lead_time"] is None
    assert "cost_price" in got["lines"][0] and got["lines"][0]["cost_price"] is None
    assert "opened_supplier_name" in got["lines"][0]


@pytest.mark.parametrize("method", ["put", "post"])
def test_portal_has_no_feedback_route(portal, method):
    d = _create(portal)
    res = getattr(_as(portal, portal.granted), method)(
        f"{BASE}/{d['id']}/feedback", json={"lead_time": "1 day"}
    )
    assert res.status_code in (404, 405), res.text


def test_lookups_list_the_brands_and_nothing_the_paper_form_dropped(portal):
    assert _as(portal, portal.granted).get(f"{NPA}/lookups/brands").status_code == 200
    for kind in ("item-groups", "uoms", "item-types", "suppliers"):
        assert _as(portal, portal.granted).get(f"{NPA}/lookups/{kind}").status_code == 404, kind


# ------------------------------------------------------------------ same rules as staff


def test_someone_elses_application_is_404(portal):
    d = _create(portal)
    c = _as(portal, portal.granted_b)
    assert c.get(f"{BASE}/{d['id']}").status_code == 404
    assert c.put(f"{BASE}/{d['id']}", json={"remark": "x"}).status_code == 404
    assert c.post(f"{BASE}/{d['id']}/submit").status_code == 404
    listed = c.get(BASE).json()
    assert d["id"] not in {r["id"] for r in listed["data"]}


def test_submit_lock_revise_cycle(portal):
    d = _create(portal)
    c = _as(portal, portal.granted)
    sub = c.post(f"{BASE}/{d['id']}/submit")
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "submitted"
    locked = c.put(f"{BASE}/{d['id']}", json={"remark": "x"})
    assert locked.status_code == 422
    assert "new_product_application_locked" in locked.text
    assert c.post(f"{BASE}/{d['id']}/revise", json={"reason": ""}).status_code == 422
    rev = c.post(f"{BASE}/{d['id']}/revise", json={"reason": "wrong UOM"})
    assert rev.status_code == 200, rev.text
    assert rev.json()["status"] == "draft"


def test_submit_names_the_missing_product_type(portal):
    d = _create(portal, lines=[_line(portal, description=None)])
    res = _as(portal, portal.granted).post(f"{BASE}/{d['id']}/submit")
    assert res.status_code == 422
    assert "Product 1: enter the product type." in res.text


def test_portal_cannot_approve_or_work_lines(portal):
    d = _create(portal)
    c = _as(portal, portal.granted)
    assert c.post(f"{BASE}/{d['id']}/approve").status_code in (404, 405)


def test_cancel_by_the_contact(portal):
    d = _create(portal)
    res = _as(portal, portal.granted).post(f"{BASE}/{d['id']}/cancel")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancelled"


def test_staff_rejection_reaches_the_linked_user(portal):
    """PQ2 (a): the portal applicant hears through its linked staff user."""
    from app.models.new_product_application import NewProductApplication
    from app.services import new_product_application_service as svc

    d = _create(portal)
    assert _as(portal, portal.granted).post(f"{BASE}/{d['id']}/submit").status_code == 200
    app_row = portal.db.get(NewProductApplication, d["id"])
    approver = make_user(portal.db, f"{MARKER} approver")
    svc.reject(portal.db, app_row, actor=svc.Actor(user_id=approver, can_approve=True), reason="no")
    portal.db.commit()
    svc.notify(portal.db, app_row, "rejected")
    assert (portal.linked_user, "new_product_application_rejected") in portal.sent


def test_portal_application_is_stamped_with_the_contacts_company(portal):
    from app.models.new_product_application import NewProductApplication

    d = _create(portal)
    row = portal.db.get(NewProductApplication, d["id"])
    assert str(row.company_id) == str(portal.company_id)
    assert row.contact_id == portal.granted


def test_review_portal_cannot_set_or_read_the_supplier_model_no(portal):
    res = _as(portal, portal.granted).post(BASE, json={"lines": [_line(portal, supplier_item_code="XY1234")]})
    assert res.status_code == 422, res.text
    d = _create(portal)
    assert "supplier_item_code" not in d["lines"][0]


# ====================================================================================
# v4: portal images, lines kept by id, Download Excel (AC-NPA-71, 73, 77, 78)
# ====================================================================================


@pytest.fixture
def store(monkeypatch, portal):
    seed_attachment_type(portal.db)
    return install_storage(monkeypatch)


def _upload(p, aid, line_id, contact=None, name="photo.png", data=None, mime="image/png"):
    return _as(p, contact or p.granted).post(
        f"{BASE}/{aid}/lines/{line_id}/images",
        files={"file": (name, data if data is not None else image_bytes(), mime)},
    )


def _images(p, aid, index=0):
    res = _as(p, p.granted).get(f"{BASE}/{aid}")
    assert res.status_code == 200, res.text
    return res.json()["lines"][index]["images"]


def test_portal_edit_keeps_the_line_id_and_its_image_and_removes_a_left_out_line(portal, store):
    d = _create(portal, lines=[_line(portal), _line(portal, proposed_code="XY-1234-BG")])
    first, second = [l["id"] for l in d["lines"]]
    assert _upload(portal, d["id"], first).status_code in (200, 201)
    link = _images(portal, d["id"])[0]["link_id"]

    res = _as(portal, portal.granted).put(
        f"{BASE}/{d['id']}", json={"lines": [_line(portal, id=first, description="Edited type")]}
    )
    assert res.status_code == 200, res.text
    lines = res.json()["lines"]
    assert [l["id"] for l in lines] == [first]
    assert lines[0]["description"] == "Edited type"
    assert [i["link_id"] for i in lines[0]["images"]] == [link]


def test_portal_a_line_id_of_another_application_is_422(portal):
    mine = _create(portal)
    other = _create(portal)
    res = _as(portal, portal.granted).put(
        f"{BASE}/{mine['id']}", json={"lines": [_line(portal, id=other["lines"][0]["id"])]}
    )
    assert res.status_code == 422, res.text


@pytest.mark.parametrize("fmt, mime, name", IMAGE_FORMATS)
def test_portal_contact_uploads_a_jpeg_png_or_webp_to_its_own_product(portal, store, fmt, mime, name):
    d = _create(portal)
    res = _upload(portal, d["id"], d["lines"][0]["id"], name=name, data=image_bytes(fmt), mime=mime)
    assert res.status_code in (200, 201), res.text
    images = _images(portal, d["id"])
    assert len(images) == 1
    assert images[0]["filename"] == name
    assert images[0]["url"] and images[0]["link_id"] and images[0]["attachment_id"]


@pytest.mark.parametrize(
    "name, mime, data",
    [("notes.txt", "text/plain", b"hello"), ("sheet.pdf", "application/pdf", b"%PDF-1.4 fake")],
)
def test_portal_anything_but_an_image_is_422(portal, store, name, mime, data):
    d = _create(portal)
    res = _upload(portal, d["id"], d["lines"][0]["id"], name=name, data=data, mime=mime)
    assert res.status_code == 422, res.text
    assert _images(portal, d["id"]) == []


def test_portal_someone_elses_application_images_are_404(portal, store):
    d = _create(portal)
    line = d["lines"][0]["id"]
    assert _upload(portal, d["id"], line).status_code in (200, 201)
    image = _images(portal, d["id"])[0]
    att, _ = seed_attachment(portal.db, store, "stock_inquiry", portal.mine.id, "s.png", image_bytes(), "image/png")
    assert _upload(portal, d["id"], line, contact=portal.granted_b).status_code == 404
    other = _as(portal, portal.granted_b)
    assert other.post(f"{BASE}/{d['id']}/lines/{line}/images/copy", json={"attachment_id": att}).status_code == 404
    assert other.delete(f"{BASE}/{d['id']}/lines/{line}/images/{image['link_id']}").status_code == 404
    assert len(_images(portal, d["id"])) == 1


def test_portal_images_are_locked_while_submitted(portal, store):
    d = _create(portal)
    line = d["lines"][0]["id"]
    assert _upload(portal, d["id"], line).status_code in (200, 201)
    link = _images(portal, d["id"])[0]["link_id"]
    assert _as(portal, portal.granted).post(f"{BASE}/{d['id']}/submit").status_code == 200
    up = _upload(portal, d["id"], line)
    rm = _as(portal, portal.granted).delete(f"{BASE}/{d['id']}/lines/{line}/images/{link}")
    for res in (up, rm):
        assert res.status_code == 422, res.text
        assert "new_product_application_locked" in res.text


def test_portal_copy_only_from_its_own_stock_inquiry_and_unlink_keeps_the_file(portal, store):
    from app.models.resources import Attachment

    d = _create(portal)  # linked to portal.mine
    line = d["lines"][0]["id"]
    mine_att, _ = seed_attachment(portal.db, store, "stock_inquiry", portal.mine.id, "site.png", image_bytes(), "image/png")
    other_att, _ = seed_attachment(portal.db, store, "stock_inquiry", portal.theirs.id, "x.png", image_bytes(), "image/png")
    c = _as(portal, portal.granted)
    before = portal.db.query(Attachment).count()

    bad = c.post(f"{BASE}/{d['id']}/lines/{line}/images/copy", json={"attachment_id": other_att})
    assert bad.status_code == 422, bad.text
    ok = c.post(f"{BASE}/{d['id']}/lines/{line}/images/copy", json={"attachment_id": mine_att})
    assert ok.status_code in (200, 201), ok.text
    images = _images(portal, d["id"])
    assert [i["attachment_id"] for i in images] == [mine_att]
    assert portal.db.query(Attachment).count() == before

    rm = c.delete(f"{BASE}/{d['id']}/lines/{line}/images/{images[0]['link_id']}")
    assert rm.status_code in (200, 204), rm.text
    assert _images(portal, d["id"]) == []
    assert portal.db.query(Attachment).filter(Attachment.id == mine_att).count() == 1


# ------------------------------------------------------------------ Download Excel, portal side


def _portal_xlsx_app(p):
    from app.models.new_product_application import NewProductApplication

    d = _create(
        p,
        customer_name="Example Developer Sdn Bhd",
        project_name="Example Residence, Tower B",
        lines=[
            _line(p, proposed_code="XY-1234-MB", description="Sink A"),
            _line(p, proposed_code="XY-1234-BG", description="Sink B"),
        ],
    )
    row = p.db.get(NewProductApplication, d["id"])
    row.created_at = noon()
    p.db.commit()
    _staff_fill(p, d["id"])
    return d


def test_portal_download_has_the_paper_sheet_with_cost_filled(portal):
    d = _portal_xlsx_app(portal)
    res = _as(portal, portal.granted).get(f"{BASE}/{d['id']}/download")
    assert res.status_code == 200, res.text
    wb = open_workbook(res.content)
    assert wb.sheetnames == ["Product 1", "Product 2"]
    for ws in wb.worksheets:
        assert [label for label, _row in label_rows(ws)] == SHEET_LABELS
    one = sheet_values(wb["Product 1"])
    assert float(text_of(one["COST:"])) == 12.5  # PQ1: cost is filled on the portal copy too
    assert text_of(one["LEADTIME:"]) == "3 weeks"
    assert text_of(one["PRODUCT CODE:"]) == "XY-1234-MB"
    assert text_of(one["DATE:"]) == "17/01/2028"


def test_portal_download_file_name_uses_the_application_number_for_the_initials(portal):
    d = _portal_xlsx_app(portal)
    res = _as(portal, portal.granted).get(f"{BASE}/{d['id']}/download")
    name = downloaded_name(res)
    assert name == (
        f"NPA_20280117_{d['application_no']}_Example Developer Sdn Bhd "
        "(XY-1234-MB Sink A) (XY-1234-BG Sink B).xlsx"
    )
    wb = open_workbook(res.content)
    assert text_of(sheet_values(wb["Product 1"])["REFF:"]) == name[: -len(".xlsx")]


def test_portal_download_of_another_contacts_application_is_404(portal):
    d = _portal_xlsx_app(portal)
    assert _as(portal, portal.granted).get(f"{BASE}/{d['id']}/download").status_code == 200
    assert _as(portal, portal.granted_b).get(f"{BASE}/{d['id']}/download").status_code == 404
    assert _as(portal, portal.granted).get(f"{BASE}/{uid()}/download").status_code == 404


def test_portal_download_is_a4_portrait_fit_to_one_page(portal):
    d = _portal_xlsx_app(portal)
    wb = open_workbook(_as(portal, portal.granted).get(f"{BASE}/{d['id']}/download").content)
    for ws in wb.worksheets:
        assert ws.page_setup.orientation == "portrait"
        assert str(ws.page_setup.paperSize) == "9"
        assert ws.sheet_properties.pageSetUpPr.fitToPage is True
        assert (ws.page_setup.fitToWidth, ws.page_setup.fitToHeight) == (1, 1)


# ------------------------------------------------------------------ inquiry attachments picker (portal)


def _inq_atts(p, inquiry_id, contact=None):
    return _as(p, contact or p.granted).get(f"{NPA}/inquiry-attachments", params={"stock_inquiry_id": inquiry_id})


def test_portal_inquiry_attachments_lists_images_of_my_responded_inquiry(portal, store):
    img, _ = seed_attachment(portal.db, store, "stock_inquiry", portal.mine.id, "site.png", image_bytes(), "image/png")
    seed_attachment(portal.db, store, "stock_inquiry", portal.mine.id, "quote.pdf", b"%PDF-1.4 fake", "application/pdf")
    res = _inq_atts(portal, portal.mine.id)
    assert res.status_code == 200, res.text
    rows = res.json()
    assert [r["attachment_id"] for r in rows] == [img]
    assert rows[0]["filename"] == "site.png" and rows[0]["content_type"] == "image/png" and rows[0]["url"]


@pytest.mark.parametrize("which", ["theirs", "mine_open"])
def test_portal_inquiry_attachments_refuses_others_or_unanswered_inquiry(portal, store, which):
    target = getattr(portal, which)
    seed_attachment(portal.db, store, "stock_inquiry", target.id, "x.png", image_bytes(), "image/png")
    assert _inq_atts(portal, portal.mine.id).status_code == 200  # the route exists for my own
    assert _inq_atts(portal, target.id).status_code == 404
