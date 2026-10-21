"""EXPLORE-1021: a held listed scheme re-scopes its certificates to the product asked NOW.

Turn 1 "span cert for <A>" holds the scheme entity (listed cert_scheme) with the certificate ids
`head/scheme_index` read for A. Turn 2 "and <B>?" (set product B, the scheme held) must narrow the
certificate fetch to B's certificates of the scheme, never A's (`resolve_gate.listed_scheme_resolutions`
trusts the entity's `certificate_uuids`). Codes are synthetic.
"""
from __future__ import annotations

import uuid

import pytest

from tests.chatbot.test_chat_state_r6_s3_ops_decide import _turns, applied  # noqa: F401
from tests.chatbot.test_chat_state_seam import _op
from tests.chatbot.test_closed_lists_scheme_index import (  # noqa: F401 - fixtures used by name
    _file_ask, _file_fetches, _scheme, seeded, session_factory, stub_access,
)

A, B = "ZZFC2043", "ZZFC2044"


def _seed_two(session_factory) -> dict[str, dict[str, str]]:
    from app.models.certificate import Certificate, CertificateRevision
    from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
    from app.models.resources import Attachment, AttachmentType
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._pg_fixture import unique_code

    db = session_factory()
    cat = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT FC", company_id=DEFAULT_COMPANY_ID)
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    kind = AttachmentType(id=str(uuid.uuid4()), type_name="ZZT Certification", description="c", allowed_extensions="pdf", is_certificate=True)
    db.add_all([cat, uom, kind])
    db.flush()
    out: dict[str, dict[str, str]] = {}
    for code in (A, B):
        p = Product(id=str(uuid.uuid4()), product_code=code, product_name=f"ZZT {code}", category_id=cat.id,
                    base_uom_id=uom.id, list_price=1, company_id=DEFAULT_COMPANY_ID)
        db.add(p)
        att = Attachment(id=str(uuid.uuid4()), original_filename=f"{code}_SPAN.pdf", stored_filename=uuid.uuid4().hex,
                         file_path=f"https://cdn.test/{code}.pdf", attachment_type_id=kind.id, is_deleted=False,
                         company_id=DEFAULT_COMPANY_ID)
        db.add(att)
        db.flush()
        db.add(ProductAttachment(id=str(uuid.uuid4()), product_id=p.id, attachment_id=att.id, company_id=DEFAULT_COMPANY_ID))
        cert = Certificate(id=str(uuid.uuid4()), attachment_type_id=kind.id, scheme="ZZSPAN",
                           certificate_number=uuid.uuid4().hex[:10], status="active", company_id=None)
        db.add(cert)
        db.flush()
        db.add(CertificateRevision(id=str(uuid.uuid4()), certificate_id=cert.id, revision_no=1, attachment_id=att.id, is_current=True))
        out[code] = {"product": p.id, "cert": cert.id}
    db.commit()
    return out


def _product(code):
    return {"raw": code, "hint": "product", "canonical_code": code, "current_message": True, "confident": True}


def _run(session_factory, stub_access, monkeypatch):
    ids = _seed_two(session_factory)
    a1 = _file_ask(_product(A), _scheme("zzspan", "ZZSPAN"))
    a1["state_changes"] = [_op("set", "product"), _op("set", "attachment_type")]
    a2 = _file_ask(_product(B))
    a2["state_changes"] = [_op("set", "product")]
    (_r1, c1), (_r2, c2) = _turns(session_factory, stub_access, monkeypatch,
                                  [(f"zzspan cert for {A}", a1), (f"and {B}?", a2)])
    return ids, _file_fetches(c1), _file_fetches(c2)


def test_explore1021_guard_turn_one_narrows_to_the_first_products_certificates(session_factory, seeded, stub_access, monkeypatch, applied):
    ids, f1, _f2 = _run(session_factory, stub_access, monkeypatch)
    assert f1 and f1[0].get("certificate_ids") == [ids[A]["cert"]], f1


def test_explore1021_the_held_scheme_rescopes_to_the_product_asked_now(session_factory, seeded, stub_access, monkeypatch, applied):
    ids, _f1, f2 = _run(session_factory, stub_access, monkeypatch)
    assert len(applied) >= 2, "the state path did not run"
    assert f2, "turn 2 made no attachment fetch"
    cert_ids = f2[0].get("certificate_ids") or []
    assert f2[0].get("product_ids") == [ids[B]["product"]], f2[0]
    assert ids[A]["cert"] not in cert_ids, ("the first product's certificate rode the second product's fetch", cert_ids)
    assert cert_ids == [ids[B]["cert"]], ("expected the second product's SPAN certificate", cert_ids, f2[0])
