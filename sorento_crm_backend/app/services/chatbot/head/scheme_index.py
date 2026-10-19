"""SCHEME-INDEX (CHAT-CLOSED-LISTS, crew T2, 17 Oct 2026): a listed certificate scheme is an
index into certificates, never a filter that empties a product's answer (owner c04 / c19).

"span certificate" was read as the listed scheme SPAN alone. The leg became `{"certificate":
{"scheme": "SPAN"}}`, the product held no SPAN certificate, and nothing was sent. Under the
gate, a scheme pick about products (named in the message, else held by the conversation) is
checked against the explicit link: product, attachment, certificate revision, certificate
scheme. Holding one, the scheme stays and narrows the files, with the certificate kind beside
it and the held products carried into the fetch. Holding none, the pick becomes the
certificate kind, so every certificate file of the products is sent. With no product at all
("which item has PPS cert") the verdict is left as it was. Data only: no word is read.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def names_own_class(entities: list[dict[str, Any]]) -> bool:
    """True when the message names its own subject by class: a current-message entity the
    parser hinted `category` or `product_type`. Parser hints only, no word is read."""
    return any(
        e.get("current_message") is not False and str(e.get("hint") or "").strip().lower() in ("category", "product_type")
        for e in entities
        if isinstance(e, dict)
    )


def _asked_product_ids(db: "Session", said: list[dict[str, Any]], held: list[dict[str, Any]]) -> tuple[list[str], bool]:
    """The products the ask is about and whether the message named them itself."""
    from app.models.product import Product, chat_searchable_products

    codes = [
        str(e.get("canonical_code")).strip()
        for e in said
        if str(e.get("hint") or "").strip().lower() == "product" and str(e.get("canonical_code") or "").strip()
    ]
    if codes:
        rows = db.query(Product.id).filter(Product.product_code.in_(codes), chat_searchable_products()).all()
        return [str(pid) for (pid,) in rows], True
    if names_own_class(said):
        # The message is about its own class, not the products an earlier turn still holds.
        return [], False
    return [str(p["uuid"]) for p in held if isinstance(p, dict) and p.get("uuid")], False


def _held_certificates(db: "Session", product_ids: list[str], scheme: str) -> list[str]:
    """The certificates of the scheme filed against the products' own attachments."""
    from sqlalchemy import func

    from app.models.certificate import Certificate, CertificateRevision
    from app.models.product import ProductAttachment

    rows = (
        db.query(Certificate.id)
        .join(CertificateRevision, CertificateRevision.certificate_id == Certificate.id)
        .join(ProductAttachment, ProductAttachment.attachment_id == CertificateRevision.attachment_id)
        .filter(ProductAttachment.product_id.in_(product_ids), func.lower(Certificate.scheme) == scheme.casefold())
        .distinct()
        .all()
    )
    return sorted(str(cid) for (cid,) in rows)


# Every id rides one GET query string (h11's request line holds about 400): the same 200 cap
# as product_predicate_service._CERTIFICATE_ID_CAP, restated rather than imported.
_CERTIFICATE_ID_CAP = 200


def _scheme_certificates(db: "Session", scheme: str) -> list[str]:
    """The scheme's active certificates in the session's company scope: the read goes
    through the scoped session, so another company's certificate never appears."""
    from sqlalchemy import func

    from app.models.certificate import Certificate

    rows = (
        db.query(Certificate.id)
        .filter(func.lower(Certificate.scheme) == scheme.casefold(), Certificate.status == "active")
        .order_by(Certificate.id)
        .limit(_CERTIFICATE_ID_CAP)
        .all()
    )
    return [str(cid) for (cid,) in rows]


def _kind_item(db: "Session", scheme: str, kinds: dict[str, str]) -> str | None:
    """The certificate kind the scheme's own certificates are filed under, else the only
    (or first) kind listed."""
    from sqlalchemy import func

    from app.models.certificate import Certificate
    from app.models.resources import AttachmentType

    for code, name in (
        db.query(AttachmentType.code, AttachmentType.type_name)
        .join(Certificate, Certificate.attachment_type_id == AttachmentType.id)
        .filter(func.lower(Certificate.scheme) == scheme.casefold())
        .order_by(AttachmentType.type_name)
        .all()
    ):
        for key in (code, name):
            item = kinds.get(str(key or "").strip().casefold())
            if item:
                return item
    listed = sorted(set(kinds.values()))
    return listed[0] if listed else None


def index_scheme(
    db: "Session", verdict: dict[str, Any], held_products: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """The verdict with its scheme pick read as an index, and a trace note; the verdict
    unchanged (and no note) when the rule does not apply."""
    from app.services.chatbot_prompt_vars import closed_list_items

    entities = [e for e in verdict.get("entities") or [] if isinstance(e, dict)]
    said = [e for e in entities if e.get("current_message") is not False]
    schemes = [e for e in said if e.get("listed") == "cert_scheme" and str(e.get("canonical_code") or "").strip()]
    if not schemes:
        return verdict, None
    product_ids, named = _asked_product_ids(db, said, held_products)
    if not product_ids:
        return verdict, None
    scheme = str(schemes[0]["canonical_code"]).strip()
    kind = _kind_item(db, scheme, closed_list_items(db).get("cert_kind", {}))
    # With no certificate kind listed there is none to add beside the scheme; the held
    # products still stay the subject.
    has_kind = kind is None or any(e.get("listed") == "cert_kind" for e in said)
    kind_entity = {**schemes[0], "canonical_code": kind, "listed_item": kind, "listed": "cert_kind"}
    # Added beside a kept scheme, the kind is its own entity: reconciliation keys on `raw`,
    # so it must not share the scheme's word (or it is retyped with it).
    added_kind = {**kind_entity, "raw": kind}
    held = _held_certificates(db, product_ids, scheme)
    if held:
        # The certificates the scheme names for these products, read here through the link,
        # are the scheme's resolution (`resolve_gate`): its word is never a record lookup.
        # Typed `certificate`, the kind its rows are; the certificate kind beside it stays
        # the file leg.
        entities = [{**e, "hint": "certificate", "certificate_uuids": held} if e is schemes[0] else e for e in entities]
        carried = [] if named else [
            {"raw": p.get("canonical_code") or p.get("raw"), "hint": "product", "canonical_code": p.get("canonical_code"),
             "current_message": True, "confident": True}
            for p in held_products
            if isinstance(p, dict) and p.get("uuid") and p.get("canonical_code")
        ]
        out = [*carried, *entities, *([] if has_kind else [added_kind])]
        note = {"scheme": scheme, "held_by_products": True, "carried": len(carried)}
    else:
        # HELD-WITHOUT-SCHEME (crew ruling (b)): the products stay the subject and the scheme's
        # certificates the filter; the engine says plainly that none is on record.
        certificates = _scheme_certificates(db, scheme)
        if certificates:
            entities = [{**e, "hint": "certificate", "certificate_uuids": certificates} if e is schemes[0] else e for e in entities]
        carried = [] if named else [
            {"raw": p.get("canonical_code") or p.get("raw"), "hint": "product", "canonical_code": p.get("canonical_code"),
             "current_message": True, "confident": True}
            for p in held_products
            if isinstance(p, dict) and p.get("uuid") and p.get("canonical_code")
        ]
        out = [*carried, *entities, *([] if has_kind else [added_kind])]
        codes = [str(e.get("canonical_code")).strip() for e in [*carried, *said] if str(e.get("hint") or "").strip().lower() == "product" and str(e.get("canonical_code") or "").strip()]
        note = {"scheme": scheme, "held_by_products": False, "none_match": True, "products": list(dict.fromkeys(codes))}
    return {**verdict, "entities": out}, note


def scheme_without_product(db: "Session", verdict: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """SCHEME-NO-PRODUCT: a listed scheme pick asked as a file ask with no product named or
    held (any product entity, said or carried, leaves the verdict as it is). The scheme's own
    active certificates in the contact's companies become the fetch's filter (read through the scoped session, so another company's never appears); the tool's
    own row limit bounds the reply. The verdict unchanged (and no note) otherwise; with no
    certificate of the scheme in scope, the verdict unchanged and a `none_in_scope` note."""
    if verdict.get("domain_hint") != "product_attachment":
        return verdict, None
    entities = [e for e in verdict.get("entities") or [] if isinstance(e, dict)]
    said = [e for e in entities if e.get("current_message") is not False]
    schemes = [e for e in said if e.get("listed") == "cert_scheme" and str(e.get("canonical_code") or "").strip()]
    if not schemes or any(str(e.get("hint") or "").strip().lower() == "product" for e in entities):
        return verdict, None
    scheme = str(schemes[0]["canonical_code"]).strip()
    certificates = _scheme_certificates(db, scheme)
    if not certificates:
        # The scheme list is the same for every company, so a scheme can be listed with no
        # certificate of it in this contact's scope: said plainly by the engine, nothing sent.
        return verdict, {"scheme": scheme, "held_by_products": False, "products": 0, "certificates": 0, "none_in_scope": True}
    # Left typed as the attachment-type pick it is, so the ask stays a file ask: typed
    # `certificate` it would read as the set "which products have this certificate". A product
    # carried from an open pick is added later and skipped there (`with_carried_entities`).
    out = [{**e, "certificate_uuids": certificates} if e is schemes[0] else e for e in entities]
    return {**verdict, "entities": out}, {"scheme": scheme, "held_by_products": False, "products": 0, "certificates": len(certificates)}
