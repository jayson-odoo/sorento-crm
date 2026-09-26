"""Seed chains shared by the price tag round 9 suites.

CI's database is EMPTY, so nothing here may reach for a row that happens to
exist: every product carries its own category, brand and UoM, every request its
own contact, every design its own page and version. Codes go through
``unique_code`` so two files running in the same scratch schema cannot collide.

Kept in one module because six r9 suites need the same five chains and a copy
per file is five chances for them to drift apart.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from tests._pg_fixture import unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"

# One marketing user with the two price tag permissions, and its role. Fixed
# ids so a test can assert "this user resolved it" without threading the value
# through every helper.
MARKETER_ID = "5f1c9d64-2b8a-5c17-9d43-6e2f8a1b4c07"
MARKETER_ROLE_ID = "3a7e2c58-9f14-5b63-8e07-1d4a6b9c2f38"
MARKETER_NAME = "ZZT Marketing Mei"

# A second staff user, for "somebody who is not the assignee" cases.
OTHER_USER_ID = "8c4b1e97-6d23-5a48-b71f-0e9c3d7a5b26"


def seed_marketer(db: Session) -> None:
    """The CRM principal: a role holding view + process, assigned to one user."""
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=MARKETER_ROLE_ID,
            slug="zzt_ptag_r9_marketer",
            name="ZZT r9 Marketer",
            description="Designs price tags",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(
        User(
            id=MARKETER_ID,
            email="zzt-ptag-r9-marketer@test.com",
            name=MARKETER_NAME,
            status="ACTIVE",
        )
    )
    db.add(
        User(
            id=OTHER_USER_ID,
            email="zzt-ptag-r9-other@test.com",
            name="ZZT Other Staff",
            status="ACTIVE",
        )
    )
    db.flush()
    db.add(UserRoleAssignment(user_id=MARKETER_ID, role_id=MARKETER_ROLE_ID))
    for slug in (
        "dealer_kit.price_tag_requests.view",
        "dealer_kit.price_tag_requests.process",
    ):
        permission_id = str(uuid.uuid4())
        db.add(
            UserPermission(id=permission_id, slug=slug, name=slug, description="")
        )
        db.flush()
        db.add(
            UserRolePermission(
                id=str(uuid.uuid4()),
                role_id=MARKETER_ROLE_ID,
                permission_id=permission_id,
            )
        )
    db.commit()


def seed_portal_contact(db: Session) -> str:
    """A Respond contact whose market segment may see the price tag form
    (PLAN-portal-forms-market-segment D1: the grant moved off access types)."""
    from app.models.access import RespondContact
    from tests._portal_grant import link_contact_segment, seed_segment

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("ZZT Sales Sam"),
    )
    db.add(contact)
    db.flush()
    segment = seed_segment(db, kinds=["price_tag_request"])
    link_contact_segment(db, contact.id, segment.code)
    return contact.id


def seed_product(db: Session, *, list_price=1599.00, barcode: str | None = None):
    """A product with its OWN category, brand and UoM. Never borrowed."""
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    stem = unique_code("R9")
    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=stem,
        category_name=f"ZZT category {stem}",
    )
    brand = Brand(
        id=str(uuid.uuid4()), brand_code=stem[:50], brand_name=f"ZZT brand {stem}"
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=stem[:20], uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    product = Product(
        id=str(uuid.uuid4()),
        product_code=stem,
        product_name=f"ZZT product {stem}",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=list_price,
        barcode=barcode,
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def seed_product_photo(db: Session, product, *, is_primary: bool = True):
    """A dealer-visible product photo, as an attachment + link row."""
    from app.models.product import ProductAttachment
    from app.models.resources import Attachment

    name = unique_code("r9img")
    attachment = Attachment(
        id=str(uuid.uuid4()),
        original_filename=f"{name}.jpg",
        stored_filename=f"{name}.jpg",
        file_path=f"https://cdn.example.test/products/{name}.jpg",
        mime_type="image/jpeg",
        storage_provider="s3",
        company_id=SORENTO,
        is_deleted=False,
    )
    db.add(attachment)
    db.flush()
    db.add(
        ProductAttachment(
            product_id=product.id,
            attachment_id=attachment.id,
            is_primary=is_primary,
            sort_order=0,
            access_levels=["dealer"],
            company_id=SORENTO,
        )
    )
    db.flush()
    return attachment


def seed_asset(db: Session, *, kind: str = "decorative"):
    """A dealer-kit library asset (artwork or a brand font) and its bytes."""
    from app.models.dealer_kit import Asset
    from app.models.resources import Attachment

    name = unique_code("r9asset")
    attachment = Attachment(
        id=str(uuid.uuid4()),
        original_filename=f"{name}.png",
        stored_filename=f"{name}.png",
        file_path=f"https://cdn.example.test/assets/{name}.png",
        mime_type="image/png",
        storage_provider="s3",
        company_id=SORENTO,
        is_deleted=False,
    )
    db.add(attachment)
    db.flush()
    asset = Asset(
        id=str(uuid.uuid4()),
        attachment_id=attachment.id,
        name=name,
        kind=kind,
        company_id=SORENTO,
    )
    db.add(asset)
    db.flush()
    return asset


def tag_sheet_doc(*, tag_id: str, asset_id: str | None = None) -> dict:
    """A one sheet, one tag document naming one library asset.

    The tag's box is deliberately not at the sheet origin: a pin's fractions
    are of the TAG, so a geometry bug that reads them against the page would
    still land on the tag if the tag started at 0,0.
    """
    layers: list[dict] = [
        {
            "id": "layer-text",
            "type": "text",
            "props": {"text": "{{name}}", "fontFamily": "ZZT Brand"},
        }
    ]
    if asset_id:
        layers.append(
            {
                "id": "layer-art",
                "type": "image",
                "props": {"source": {"type": "asset", "assetId": asset_id}},
            }
        )
    return {
        "kind": "tag_sheet",
        "imposition": {"page_width_mm": 210, "page_height_mm": 297},
        "sheets": [
            {
                "id": "sheet-1",
                "tags": [
                    {
                        "id": "tag-1",
                        "request_tag_id": tag_id,
                        "x_mm": 20,
                        "y_mm": 30,
                        "width_mm": 80,
                        "height_mm": 50,
                        "layers": layers,
                    }
                ],
            }
        ],
    }


def seed_request(
    db: Session,
    contact_id: str,
    *,
    status: str = "new",
    products: list | None = None,
    print_by: str | None = None,
    assigned_to_id: str | None = None,
):
    """A SUBMITTED request (no portal_draft_at) with one line per product."""
    from app.services.price_tag_request_service import PriceTagRequestService

    products = products or []
    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact_id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "needed_by_date": date.today() + timedelta(days=7),
            "lines": [
                {"line_type": "product", "product_id": product.id}
                for product in products
            ],
        },
    )
    request.portal_draft_at = None
    if assigned_to_id:
        request.assigned_to_id = assigned_to_id
    # `print_by` is r9 S3's new column: setting it before the coder adds it is
    # an AttributeError, which is exactly the red these suites want.
    if print_by is not None:
        request.print_by = print_by
    request.status = status
    db.flush()
    db.commit()
    return request


def tags_of(line):
    """A line's tags in print order. One per line unless a Split made more."""
    return sorted(line.tags or [], key=lambda t: (t.sort_order or 0, t.id))


def first_tag(request):
    """The request's FIRST tag: what submit mints for its first line.

    The r9 gate and every pin hang off a TAG since the combos slice, so a test
    that used to name `request.lines[0]` names this instead.
    """
    for line in sorted(request.lines, key=lambda l: (l.sort_order or 0, l.id)):
        for tag in tags_of(line):
            return tag
    return None


def attach_design(db: Session, request, *, asset_id: str | None = None, version: int = 1):
    """Give a request a tag sheet page carrying one saved version.

    Returns ``(page, doc)``. The doc binds its single placed tag to the
    request's FIRST TAG, which is what every pin and diff assertion points at -
    a document has keyed its placements by request tag since the combos slice.
    """
    from app.models.dealer_kit import Page, PageVersion

    first = first_tag(request)
    doc = tag_sheet_doc(
        tag_id=first.id if first is not None else str(uuid.uuid4()),
        asset_id=asset_id,
    )

    page = Page(
        name=f"ZZT Tags {request.doc_number}",
        slug=unique_code("tag-sheet"),
        kind="tag_sheet",
        request_id=request.id,
        company_id=SORENTO,
    )
    db.add(page)
    db.flush()
    request.page_id = page.id
    db.add(PageVersion(page_id=page.id, version=version, doc=doc))
    db.flush()
    db.commit()
    return page, doc


def snapshot_proof_ready(db: Session, page, doc: dict, version: int) -> None:
    """One more ``Marked proof ready`` version, which is what a round counts.

    D4 stores ``round`` as the number of proof_ready snapshots at send time, so
    a test that wants round 2 writes two of these.
    """
    from app.models.dealer_kit import PageVersion

    db.add(
        PageVersion(
            page_id=page.id,
            version=version,
            doc=doc,
            commit_message="Marked proof ready",
        )
    )
    db.flush()
    db.commit()


def utcnow() -> datetime:
    return datetime.utcnow()


def block_respond(monkeypatch) -> list[dict]:
    """Stop a test run reaching api.respond.io, and record what it would send.

    The notifier is left REAL on purpose. Patching ``notify_salesperson`` away
    would also throw away the copy table and the ``IntegrationLog`` row, which
    are the two things several tests are about; the network call is the only
    part that must not happen. Cutting it at
    ``respond_messaging_service.send_text_or_template`` (plus the window check
    inside ``build_context_vars`` and the outbound webhook enqueue) leaves
    everything above it running for real.

    Without this a price tag suite makes live HTTPS calls from CI: the run log
    carried ``Window check: Respond.io list_messages failed ... 400 Bad
    Request`` and ``Respond.io send failed for price tag <uuid>`` on every
    transition, which is slow, flaky, and a real message away from a real
    contact the moment a token happens to be valid.

    Returns the list of sends, newest last: ``{identifier, text, use_case}``.
    """
    sent: list[dict] = []

    def _fake_send(db, *, identifier, text, use_case, context_vars=None, **_kw):
        sent.append({"identifier": identifier, "text": text, "use_case": use_case})
        return {
            "sent_as": "text",
            "response": {"id": f"zzt-msg-{len(sent)}"},
            "window_state": "open",
            "request_payload": {"message": {"type": "text", "text": text}},
        }

    monkeypatch.setattr(
        "app.services.respond_messaging_service.send_text_or_template", _fake_send
    )
    monkeypatch.setattr(
        "app.services.respond_messaging_service.build_context_vars",
        lambda db, **_kwargs: {},
    )
    monkeypatch.setattr(
        "app.services.crm_chat_outbound_webhook.enqueue_crm_chat_outbound_webhook",
        lambda *a, **k: None,
    )
    return sent


def seed_product_set(db: Session, *, members: list | None = None):
    """A set with its own code and one or more member products."""
    from app.models.product_set import ProductSet, ProductSetMember

    members = members or [seed_product(db)]
    product_set = ProductSet(
        id=str(uuid.uuid4()),
        set_code=unique_code("set"),
        name=unique_code("ZZT Set"),
        company_id=SORENTO,
    )
    db.add(product_set)
    db.flush()
    for order, product in enumerate(members):
        db.add(
            ProductSetMember(
                id=str(uuid.uuid4()),
                product_set_id=product_set.id,
                product_id=product.id,
                quantity=1,
                contributes_to_price=True,
                sort_order=order,
            )
        )
    db.flush()
    return product_set


def seed_promotion_on(db: Session, product, *, offer: str = "799.00"):
    """A live promotion that actually prices ``product`` under its list price.

    The whole chain, because the pricing engine reads all three: the promotion
    (active, inside its window), a group, and the ``promotion_products`` row
    carrying the figure.
    """
    from decimal import Decimal

    from app.models.marketing import Promotion, PromotionGroup, PromotionProduct

    promotion = Promotion(
        id=str(uuid.uuid4()),
        description=unique_code("ZZT promo"),
        is_active=True,
        company_id=SORENTO,
    )
    db.add(promotion)
    db.flush()
    group = PromotionGroup(
        id=uuid.uuid4(),
        promotion_id=promotion.id,
        group_name=unique_code("ZZT group"),
        sort_order=0,
        company_id=SORENTO,
    )
    db.add(group)
    db.flush()
    db.add(
        PromotionProduct(
            id=str(uuid.uuid4()),
            promotion_id=promotion.id,
            promotion_group_id=group.id,
            product_id=product.id,
            promo_selling_price=Decimal(offer),
            company_id=SORENTO,
        )
    )
    db.flush()
    return promotion
