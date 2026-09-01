"""External API for product attachment linking."""
import html
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external.attachments import (
    ProductAttachmentLinkRequest,
    ProductAttachmentLinkRequestAny,
    ProductAttachmentBulkLinkRequest,
    ProductAttachmentBulkLinkResponse,
    ProductAttachmentBulkLinkItem,
)
from app.schemas.product import ProductAttachmentCreate, ProductAttachmentResponse
from app.services.product_service import ProductAttachmentService
from app.services.product_code_resolution import resolve_codes_to_products

#: The ONE resolver. Pinned by tests: re-adding a private code matcher here is
#: exactly how this path and the promotion path drifted apart.
_resolve_codes = resolve_codes_to_products
from app.services.attachment_field_link_service import AttachmentFieldLinkService
from app.models.certificate import CERTIFICATE_SOURCE_AI
from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment, AttachmentType
from app.api.v1.external.utils import scope_to_attachment_company
from app.services.attachment_notification_helper import (
    build_attachment_detail_url,
    build_product_detail_url,
    notify_after_external_attachment_entity,
)
from app.services.certificate_service import CertificateService

router = APIRouter()
logger = logging.getLogger(__name__)

# Where the ING-6 "cert-bearing type, but no usable identity" note is filed.
_CERT_LOG_CHANNEL = "n8n"
_CERT_LOG_ENDPOINT = "/api/v1/external/product-attachments"


def _notify_product_attachment_external(
    db: Session,
    *,
    attachment_id: str,
    notify_user_id: str | None,
    mode: str,
    product_code: str | None = None,
    product_id: str | None = None,
    linked_codes: list[str] | None = None,
) -> None:
    """Notify attachment uploaders / notify_user_id after successful external product - attachment link."""
    if mode == "single" and product_id and product_code is not None:
        pc = product_code or "-"
        summary_plain = (
            f'Your file was linked to product "{pc}" in Sorento CRM'
        )
        summary_html = (
            f"<p>Your file was linked to product <strong>{html.escape(pc)}</strong> in Sorento CRM.</p>"
        )
        notify_after_external_attachment_entity(
            db,
            [attachment_id],
            notify_user_id,
            notif_type="external_product_attachment_linked",
            title=f"Product attachment linked: {pc}",
            summary_plain=summary_plain,
            summary_html=summary_html,
            entity_url=build_product_detail_url(str(product_id)),
            entity_link_text="Open product in Sorento CRM",
        )
        return

    if mode == "bulk":
        codes = linked_codes or []
        codes_str = ", ".join(codes[:30]) if codes else "-"
        summary_plain = (
            "Your file was linked to product(s) in Sorento CRM "
            f"Products: {codes_str}."
        )
        summary_html = (
            "<p>Your file was linked to product(s) in Sorento CRM "
            f"<p>Products: <strong>{html.escape(codes_str)}</strong>.</p>"
        )
        notify_after_external_attachment_entity(
            db,
            [attachment_id],
            notify_user_id,
            notif_type="external_product_attachment_linked",
            title="Product attachment(s) linked",
            summary_plain=summary_plain,
            summary_html=summary_html,
            entity_url=build_attachment_detail_url(attachment_id),
            entity_link_text="View attachment in Sorento CRM",
        )


def _normalize_product_code(s: str) -> str:
    """Remove spaces and normalize for matching (case-insensitive)."""
    if not s:
        return ""
    return (s or "").replace(" ", "").strip().lower()


# --------------------------------------------------------------- certificates
def _attachment_is_cert_bearing(db: Session, attachment) -> bool:
    """ING-4, the load-bearing guard.

    Cert fields are honoured ONLY when the attachment's TYPE is flagged
    cert-bearing. A Technical Specifications sheet quoting "cert PPS 0119" must
    not mint a certificate, and the decision is made here - server-side - never
    in the extraction prompt.
    """
    type_id = getattr(attachment, "attachment_type_id", None)
    if not type_id:
        return False
    return bool(
        db.query(AttachmentType.is_certificate)
        .filter(AttachmentType.id == str(type_id))
        .scalar()
    )


def _missing_identity_field(payload: ProductAttachmentLinkRequestAny) -> str | None:
    """Which half of the identity key is absent, if either.

    Identity is ``scheme + certificate_number``; without both there is nothing
    to upsert against, so the products are still linked and the reason is logged
    (ING-6) rather than the whole call failing.
    """
    if not (payload.certificate_number or "").strip():
        return "certificate_number"
    if not (payload.scheme or "").strip():
        return "scheme"
    return None


def _log_certificate_not_created(
    db: Session,
    *,
    attachment_id: str,
    cert_fields: dict,
    missing_field: str,
    created_by: str | None,
) -> None:
    """ING-6: record WHY no certificate was created, on the attachment.

    Filed as ``failed`` with an ``error_code`` even though the product linking
    succeeded: the linking is not what went wrong, and a compliance owner
    hunting "why is this PDF not in the register" needs it to surface in the
    failed filter rather than blend into a wall of successes.
    """
    try:
        from app.schemas.integration import IntegrationLogCreate
        from app.services.integration_service import IntegrationLogService

        IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel=_CERT_LOG_CHANNEL,
                business_table="attachments",
                business_id=str(attachment_id),
                direction="inbound",
                endpoint=_CERT_LOG_ENDPOINT,
                http_method="POST",
                request_payload=json.dumps(cert_fields, default=str),
                status="failed",
                error_code="certificate_not_created",
                error_message=(
                    "Certificate fields were supplied on a cert-bearing attachment type, "
                    f"but '{missing_field}' was blank, so no certificate was created. "
                    "The attachment was still linked to its products."
                ),
                created_by=created_by,
            )
        )
    except Exception as e:  # noqa: BLE001 - a log must never fail the link
        logger.warning(
            "Certificate skip log failed for attachment=%s: %s", attachment_id, e, exc_info=True
        )


def _resolve_product_codes(db: Session, codes: list[str]) -> tuple[list[tuple[str, object, str]], list[str]]:
    """Adapter over the ONE resolver, kept for this module's existing call shape.

    Returns ``([(requested_code, product, via)], unmatched_codes)``. The tiers,
    the substring behaviour and the product-set expansion all live in
    ``app.services.product_code_resolution`` so that this path and the promotion
    path cannot drift apart again - they used to, and the same flyer code could
    link a file here and fail to create a promotion there.

    ``allow_prefix=True``: this is the certificate-linking leg of the
    attachment-link path (PLAN-shared-brand-attachments.md S1), so a
    certificate reading "SRTBV - BRASS BALL VALVE" resolves to the family it
    names.

    Company isolation still comes from the session: the caller pinned it to the
    attachment's company, so a same-coded product or set in another company never
    resolves (SEC-1).
    """
    resolved = _resolve_codes(db, codes, allow_prefix=True)
    matched = [(m.requested_code, m.product, m.via) for m in resolved.matches]
    return matched, list(resolved.unmatched)

def _link_via_certificate(
    db: Session,
    attachment,
    payload: ProductAttachmentLinkRequestAny,
    codes: list[str],
    current_user: dict,
    *,
    use_bulk: bool,
):
    """ING-3: identity upsert, revision, coverage and projection in ONE transaction.

    The certificate service is the ONLY writer of ``product_attachments`` for a
    cert-bearing attachment (COV-1), so this path replaces the ordinary linking
    rather than running alongside it - the projection falls out of
    ``certificate_products`` x current revision.

    Everything composes with ``commit=False`` and a single ``db.commit()`` at the
    end, so a failure anywhere leaves neither a half-filed certificate nor a
    stranded link.
    """
    created_by = current_user["id"]
    matched, unmatched = _resolve_product_codes(db, codes)
    matched_ids = [str(getattr(product, "id")) for _code, product, _via in matched]

    service = CertificateService(db)
    existing = service.find_by_identity(payload.scheme, payload.certificate_number)
    covered_before: set[str] = (
        {str(row.product_id) for row in service.get_coverage(existing.id)}
        if existing is not None
        else set()
    )

    # A renewal leaves coverage alone by design (REV-2), so products this call
    # names that are NOT yet covered are added first - the link endpoint's job is
    # to link, and adding can only ever widen coverage, never shrink it. Done
    # BEFORE the upsert so the revision's review rules see the real covered count.
    if existing is not None:
        to_add = [pid for pid in matched_ids if pid not in covered_before]
        if to_add:
            service.add_coverage(
                str(existing.id),
                to_add,
                source=CERTIFICATE_SOURCE_AI,
                created_by=created_by,
                commit=False,
            )

    certificate = service.upsert_from_extraction(
        scheme=payload.scheme,
        certificate_number=payload.certificate_number,
        attachment_id=str(getattr(attachment, "id")),
        attachment_type_id=(
            str(getattr(attachment, "attachment_type_id"))
            if getattr(attachment, "attachment_type_id", None)
            else None
        ),
        certifying_body=payload.certifying_body,
        issuer=payload.issuer,
        title=payload.title,
        issued_at=payload.issued_at,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        product_ids=matched_ids,
        unmatched_products=unmatched,
        # ING-7: the raw reader output, so a wrong date stays attributable.
        extracted_json=json.loads(json.dumps(payload.certificate_fields(), default=str)),
        source=CERTIFICATE_SOURCE_AI,
        created_by=created_by,
        commit=False,
    )
    certificate_id = str(certificate.id)
    db.commit()

    linked: list[ProductAttachmentBulkLinkItem] = []
    already_linked: list[str] = []
    for code, product, via in matched:
        product_code = str(getattr(product, "product_code", "") or "") or code
        if str(getattr(product, "id")) in covered_before:
            already_linked.append(product_code)
        else:
            linked.append(
                ProductAttachmentBulkLinkItem(
                    product_id=str(getattr(product, "id")),
                    product_code=product_code,
                    via=via,
                )
            )

    # Field links and notifications are best-effort fan-out, exactly as on the
    # plain path: the certificate is already committed and must not be undone by
    # a downstream hiccup.
    field_link_service = AttachmentFieldLinkService(db)
    for _code, product, _via in matched:
        try:
            field_link_service.apply_template_to_row(
                attachment,
                "product",
                str(getattr(product, "id")),
                override_keys=payload.field_keys,
                created_by=created_by,
            )
            db.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Field-link fan-out failed for attachment=%s product=%s: %s",
                payload.attachment_id,
                getattr(product, "id", None),
                e,
                exc_info=True,
            )

    try:
        if use_bulk:
            _notify_product_attachment_external(
                db,
                attachment_id=payload.attachment_id,
                notify_user_id=payload.notify_user_id,
                mode="bulk",
                linked_codes=[x.product_code for x in linked] + already_linked,
            )
        elif matched:
            _notify_product_attachment_external(
                db,
                attachment_id=payload.attachment_id,
                notify_user_id=payload.notify_user_id,
                mode="single",
                product_code=str(getattr(matched[0][1], "product_code", "") or ""),
                product_id=str(getattr(matched[0][1], "id")),
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("External product attachment notification failed: %s", e, exc_info=True)

    if use_bulk:
        return ProductAttachmentBulkLinkResponse(
            attachment_id=payload.attachment_id,
            linked=linked,
            skipped_product_codes=unmatched,
            already_linked=already_linked,
        )

    # Single-code form: answer with the projection row the certificate service
    # wrote, so the legacy node keeps receiving the shape it always has. One code
    # can name several products; `matched` is ordered by product_code, so the row
    # echoed back is a stable representative of the set, not a random one. The
    # certificate covers all of them either way.
    if matched:
        row = (
            db.query(ProductAttachment)
            .filter(
                ProductAttachment.attachment_id == payload.attachment_id,
                ProductAttachment.product_id == str(getattr(matched[0][1], "id")),
            )
            .first()
        )
        if row is not None:
            return ProductAttachmentService(db).get_product_attachment(str(row.id))
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "Invalid product_code. The certificate "
            f"{payload.scheme} {payload.certificate_number} ({certificate_id}) was filed, "
            "but the product code matched nothing."
        ),
    )


@router.post("/")
def create_product_attachment(
    payload: ProductAttachmentLinkRequestAny,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Link an attachment to one product (product_code) or many (products).
    For bulk, products are matched by product_code after removing spaces (e.g. "WC 8038" matches "WC8038").

    Optionally files the attachment into the certificate register (ING-2): the
    cert fields on the body are honoured ONLY when the attachment's type has
    ``is_certificate = true``. With no cert fields, or on a type that is not
    cert-bearing, behaviour is exactly what it was before certificates existed -
    the regression guard the 951 Technical Specifications and all Product Photos
    rows depend on (ING-4 / ING-5).
    """
    attachment = db.query(Attachment).filter(Attachment.id == payload.attachment_id).first()
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid attachment_id",
        )

    # Multi-company isolation (Group G): only match products in the attachment's
    # company. A same-coded product in another company must NOT be linked (AC-G2).
    scope_to_attachment_company(db, attachment)

    # ING-3 / ING-4 / ING-6. Anything that falls through here takes the original
    # path below, unchanged.
    if payload.has_certificate_fields() and _attachment_is_cert_bearing(db, attachment):
        missing_field = _missing_identity_field(payload)
        if missing_field is None:
            return _link_via_certificate(
                db,
                attachment,
                payload,
                (payload.products or [])
                if payload.get_use_bulk()
                else [payload.product_code or ""],
                current_user,
                use_bulk=payload.get_use_bulk(),
            )
        _log_certificate_not_created(
            db,
            attachment_id=payload.attachment_id,
            cert_fields=payload.certificate_fields(),
            missing_field=missing_field,
            created_by=current_user["id"],
        )

    if payload.get_use_bulk():
        return _link_attachment_to_products_bulk(
            db,
            payload.attachment_id,
            payload.products or [],
            current_user,
            payload.access_levels,
            notify_user_id=getattr(payload, "notify_user_id", None),
            field_keys_override=getattr(payload, "field_keys", None),
        )

    # Single link: ILIKE search on product_code (input: spaces removed, then used
    # as pattern). The pattern is a SUBSTRING, so one code names several products
    # ("WC7601" -> MWC7601-RL-S12, IBWC7601-RL-S10, ...). All of them are linked;
    # taking the first left the siblings without the file. The response stays the
    # single-row shape the n8n node has always parsed, carrying the first link -
    # `order_by(product_code)` makes "first" the same row on every call.
    normalized = _normalize_product_code(payload.product_code or "")
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product_code",
        )
    # One resolver: an exact code, a PRODUCT SET code expanded to its members, a
    # `+` split, then substring. A set code is what the flyer prints, and no
    # product carries it.
    _resolution = _resolve_codes(db, [payload.product_code or ""])
    products = [m.product for m in _resolution.matches]
    if not products:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product_code",
        )
    service = ProductAttachmentService(db)
    # The integration's principal is a real users row, so attribution is recorded.
    created_by = current_user["id"]
    field_link_service = AttachmentFieldLinkService(db)
    first_link_id: str | None = None
    linked_codes: list[str] = []
    for product in products:
        product_id = str(getattr(product, "id"))
        product_code = str(getattr(product, "product_code", "") or "")
        data = ProductAttachmentCreate(
            product_id=product_id,
            attachment_id=payload.attachment_id,
            sort_order=payload.sort_order,
            # `is_primary` is per PRODUCT (uq_product_attachment_primary is keyed
            # on product_id), and brochure_image_service clears that product's
            # previous holder, so flagging each sibling is both legal and what the
            # caller asked for: this photo is the image for every product it names.
            is_primary=payload.is_primary,
            access_levels=payload.access_levels,
            # Stamped only when a PRODUCT SET expansion put this product here, so
            # a set-created link can be found again when membership changes.
            linked_via_set_id=_resolution.product_set_id_for(product_code),
        )
        result = service.create_product_attachment(data, created_by=created_by)
        if first_link_id is None:
            # Read the id NOW, while the instance is still loaded. The commit
            # below expires it, and an expired instance carries an empty
            # ``__dict__`` - which is exactly how this route came to answer `{}`.
            first_link_id = str(result.id)
        linked_codes.append(product_code or payload.product_code or "")
        try:
            field_link_service.apply_template_to_row(
                attachment,
                "product",
                product_id,
                override_keys=payload.field_keys,
                created_by=created_by,
            )
            db.commit()
        except Exception as e:
            # Field-link fan-out must never fail the upstream link itself; the
            # link row is already committed and the user can recover via the
            # per-row Manage field links endpoint.
            logger.warning(
                "Field-link fan-out failed for attachment=%s product=%s: %s",
                payload.attachment_id,
                product_id,
                e,
                exc_info=True,
            )
    try:
        if len(products) == 1:
            _notify_product_attachment_external(
                db,
                attachment_id=payload.attachment_id,
                notify_user_id=getattr(payload, "notify_user_id", None),
                mode="single",
                product_code=linked_codes[0],
                product_id=str(getattr(products[0], "id")),
            )
        else:
            # One notification naming every product, not N notifications each
            # claiming to be the whole story.
            _notify_product_attachment_external(
                db,
                attachment_id=payload.attachment_id,
                notify_user_id=getattr(payload, "notify_user_id", None),
                mode="bulk",
                linked_codes=linked_codes,
            )
    except Exception as e:
        logger.warning("External product attachment notification failed: %s", e, exc_info=True)
    # Re-read AFTER every commit, the way the certificate path does. Returning the
    # instance the service handed back means returning one the commit has expired,
    # and FastAPI (no ``response_model`` on this route) encodes an expired ORM row
    # from its empty ``__dict__`` - so the node has been receiving `{}` all along.
    return service.get_product_attachment(first_link_id)


def _link_attachment_to_products_bulk(
    db: Session,
    attachment_id: str,
    products: list[str],
    current_user: dict,
    access_levels: list[str] | None = None,
    notify_user_id: str | None = None,
    field_keys_override: list[str] | None = None,
) -> ProductAttachmentBulkLinkResponse:
    service = ProductAttachmentService(db)
    field_link_service = AttachmentFieldLinkService(db)
    attachment_row = (
        db.query(Attachment).filter(Attachment.id == attachment_id).first()
    )
    # Multi-company isolation (Group G): restrict product matching to the
    # attachment's company. Covers the /link-products route that reaches this
    # helper directly; idempotent when create_product_attachment already scoped.
    scope_to_attachment_company(db, attachment_row)
    # The integration's principal is a real users row, so attribution is recorded.
    created_by = current_user["id"]
    linked: list[ProductAttachmentBulkLinkItem] = []
    skipped_product_codes: list[str] = []
    already_linked: list[str] = []
    seen_normalized: set[str] = set()

    for raw_code in products:
        code = (raw_code or "").strip()
        if not code:
            continue
        normalized = _normalize_product_code(code)
        if normalized in seen_normalized:
            continue
        seen_normalized.add(normalized)

        # The pattern is a SUBSTRING, so one code names several products
        # ("WC7601" -> MWC7601-RL-S12, IBWC7601-RL-S10, ...). Every one of them
        # gets the file; taking the first left the siblings without it. Ordered,
        # so a repeated call reports the same list in the same order.
        # allow_prefix=True: this is the attachment-link path
        # (PLAN-shared-brand-attachments.md S1), the only caller opted into the
        # family-head tier.
        _resolution = _resolve_codes(db, [code], allow_prefix=True)
        code_matches = _resolution.matches
        if not code_matches:
            skipped_product_codes.append(code)
            continue

        for match in code_matches:
            product = match.product
            existing = db.query(ProductAttachment).filter(
                ProductAttachment.attachment_id == attachment_id,
                ProductAttachment.product_id == product.id,
            ).first()
            product_id = str(getattr(product, "id"))
            product_code = str(getattr(product, "product_code", "") or "")
            if existing:
                already_linked.append(product_code or code)
                continue

            data = ProductAttachmentCreate(
                product_id=product_id,
                attachment_id=attachment_id,
                access_levels=access_levels,
                linked_via_set_id=match.product_set_id,
            )
            # Explicit, not scope-derived: under a SHARED attachment's
            # ALL-COMPANIES scope, the before_insert auto-stamp would
            # otherwise land every row (including a Mocha twin's) on the
            # incumbent company instead of the twin's own
            # (PLAN-shared-brand-attachments S2, AC-B8). A server-side
            # keyword, never a schema field the client could set.
            link_company_id = (
                str(getattr(product, "company_id"))
                if getattr(product, "company_id", None)
                else None
            )
            service.create_product_attachment(
                data, created_by=created_by, company_id=link_company_id
            )
            try:
                field_link_service.apply_template_to_row(
                    attachment_row or attachment_id,
                    "product",
                    product_id,
                    override_keys=field_keys_override,
                    created_by=created_by,
                )
                db.commit()
            except Exception as e:
                logger.warning(
                    "Field-link fan-out failed for attachment=%s product=%s: %s",
                    attachment_id,
                    product_id,
                    e,
                    exc_info=True,
                )
            linked.append(
                ProductAttachmentBulkLinkItem(
                    product_id=product_id,
                    product_code=product_code or code,
                    via=match.via,
                )
            )

    try:
        codes = [x.product_code for x in linked] + list(already_linked)
        _notify_product_attachment_external(
            db,
            attachment_id=attachment_id,
            notify_user_id=notify_user_id,
            mode="bulk",
            linked_codes=codes,
        )
    except Exception as e:
        logger.warning("External product attachment bulk notification failed: %s", e, exc_info=True)

    return ProductAttachmentBulkLinkResponse(
        attachment_id=attachment_id,
        linked=linked,
        skipped_product_codes=skipped_product_codes,
        already_linked=already_linked,
    )


@router.post(
    "/link-products",
    response_model=ProductAttachmentBulkLinkResponse,
    status_code=status.HTTP_200_OK,
)
def link_attachment_to_products(
    payload: ProductAttachmentBulkLinkRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Link one attachment to many products by product code.
    Products are matched by product_code after removing spaces (e.g. "WC 8038" matches "WC8038").
    """
    attachment = db.query(Attachment).filter(Attachment.id == payload.attachment_id).first()
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid attachment_id",
        )
    return _link_attachment_to_products_bulk(
        db,
        payload.attachment_id,
        payload.products,
        current_user,
        payload.access_levels,
        notify_user_id=getattr(payload, "notify_user_id", None),
        field_keys_override=getattr(payload, "field_keys", None),
    )
