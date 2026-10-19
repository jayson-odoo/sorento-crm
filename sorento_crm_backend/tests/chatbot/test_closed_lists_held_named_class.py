"""HELD-OVER-NAMED-CLASS (CHAT-CLOSED-LISTS, TRAIN cp0-41147cbf9f, 7a655af8fa, c026f64f50; synthetic codes).

A message that names its own subject by CLASS (a current-message entity hinted `category` or
`product_type`) plus a scheme or a brand, and no product code, is not about the products the
conversation still holds from an unrelated earlier turn. The held products used to become the
subject, the engine replaced the class fetch's answer with "<held>: no SPAN certificate on
record." / "<held>: none on record with <brand>", and the correct files were thrown away.
"""
from __future__ import annotations

import uuid

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.certificate import Certificate, CertificateRevision
from app.models.product import Brand, Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from tests._pg_fixture import unique_code
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_closed_lists_scheme_held_none import (  # noqa: F401
    SCHEME, _file_ask, _kind, _product, _scheme as _scheme_pick, _stock, _text, _turns, seeded, stub_access,
)


def _seed(session_factory) -> dict[str, str]:
    db = session_factory()
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    cert_type = AttachmentType(
        id=str(uuid.uuid4()), type_name="ZZT Certification", description="Certification by Purchasing",
        allowed_extensions="pdf", is_certificate=True,
    )
    brand = Brand(id=str(uuid.uuid4()), brand_code="ZZSORENTO", brand_name="ZZSORENTO", company_id=DEFAULT_COMPANY_ID)
    cats = {
        key: ProductCategory(
            id=str(uuid.uuid4()), category_code=unique_code(key.upper())[:50], category_name=name, class_label=name, search_synonyms=[name], company_id=DEFAULT_COMPANY_ID,
        )
        for key, name in (("wb", "ZZ Wash Basin"), ("sh", "shower"), ("av", "angle valve"))
    }
    db.add_all([uom, cert_type, brand, *cats.values()])
    db.flush()
    backfill_category_signals(db)
    seed_spec_registry(db)
    ids: dict[str, str] = {}

    def product(code: str, cat: str, *, brand_row=None, cert: bool = False) -> None:
        p = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"ZZT {code}", description=f"SORENTO {cats[cat].class_label.upper()} {code}", is_active=True, category_id=cats[cat].id, base_uom_id=uom.id,
            list_price=1, company_id=DEFAULT_COMPANY_ID, brand_id=brand_row.id if brand_row else None,
        )
        db.add(p)
        db.flush()
        derive_for_code(db, code)
        ids[code] = p.id
        if not cert:
            return
        att = Attachment(
            id=str(uuid.uuid4()), original_filename=f"{code}_{SCHEME}.pdf", stored_filename=uuid.uuid4().hex,
            file_path=f"https://cdn.test/{code}.pdf", attachment_type_id=cert_type.id, is_deleted=False, company_id=DEFAULT_COMPANY_ID,
        )
        db.add(att)
        db.flush()
        db.add(ProductAttachment(id=str(uuid.uuid4()), product_id=p.id, attachment_id=att.id, company_id=DEFAULT_COMPANY_ID))
        c = Certificate(
            id=str(uuid.uuid4()), attachment_type_id=cert_type.id, scheme=SCHEME, certificate_number=uuid.uuid4().hex[:10],
            status="active", company_id=None,
        )
        db.add(c)
        db.flush()
        db.add(CertificateRevision(id=str(uuid.uuid4()), certificate_id=c.id, revision_no=1, attachment_id=att.id, is_current=True))
        ids[f"cert:{code}"] = c.id

    product("ZZWB1", "wb")
    product("ZZCWB1", "wb")
    product("ZZSH1", "sh", cert=True)
    product("ZZAV1", "av", brand_row=brand, cert=True)
    product("ZZAV2", "av", brand_row=brand, cert=True)
    db.commit()
    return ids


def _category(raw: str, canonical=None) -> dict:
    """As the real parses read: hint `category`, the customer's own word, canonical code null or a slug."""
    return {"raw": raw, "hint": "category", "canonical_code": canonical, "current_message": True, "confident": True}


def _kind_pick(raw: str = "cert") -> dict:
    """The real parse's kind pick ("span", "cert"): attachment_type, canonical `certificate`."""
    return {"raw": raw, "hint": "attachment_type", "canonical_code": "certificate", "listed_item": "ZZT Certification",
            "current_message": True, "confident": True}


def _ask(*entities: dict) -> dict:
    return {**_file_ask(*entities), "entity_op": "replace_combine"}


def _scheme(word: str = SCHEME) -> dict:
    return _scheme_pick(word)


def _brand() -> dict:
    return {"raw": "ZZSORENTO", "hint": "brand", "canonical_code": "ZZSORENTO", "current_message": True, "confident": True}


def _product_fetches(calls) -> list[dict]:
    return [a for n, a in calls if n == "crm_master_product_attachments_list"]


def test_a_scheme_over_a_named_class_is_not_about_the_held_product(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory)

    (_r1, _c1), (r2, c2) = _turns(
        session_factory, stub_access, monkeypatch,
        [("ZZWB1", _stock(_product("ZZWB1"))),
         ("Shower span cert", _ask(_category("shower"), _kind_pick("span")))],
    )

    text = _text(r2)
    assert not text.startswith("ZZWB1:"), (text, c2)
    fetches = _product_fetches(c2)
    assert fetches, (text, c2)
    assert all(args.get("product_ids") != [ids["ZZWB1"]] for args in fetches), c2


def test_a_brand_over_a_named_class_is_not_about_the_held_product(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory)

    (_r1, _c1), (r2, c2) = _turns(
        session_factory, stub_access, monkeypatch,
        [("ZZCWB1", _stock(_product("ZZCWB1"))),
         ("sorento angle valve cert", _ask(_brand(), _category("angle valve", "angle_valve"), _kind_pick()))],
    )

    text = _text(r2)
    assert "none on record" not in text, (text, c2)
    assert not text.startswith("ZZCWB1:"), text
    fetches = _product_fetches(c2)
    assert fetches, (text, c2)
    assert all(args.get("product_ids") != [ids["ZZCWB1"]] for args in fetches), c2


def test_guard_no_class_entity_still_takes_the_held_path(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)

    (_r1, _c1), (r2, _c2) = _turns(
        session_factory, stub_access, monkeypatch,
        [("ZZWB1", _stock(_product("ZZWB1"))), ("Span certificate", _file_ask(_scheme(), _kind()))],
    )

    assert _text(r2) == f"ZZWB1: no {SCHEME} certificate on record.", _text(r2)
