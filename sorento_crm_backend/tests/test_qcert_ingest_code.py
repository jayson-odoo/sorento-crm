"""QUOTE-CERT-TAB red tests: the ingest stores the printed code as a Suggested model_code (CERT-14).

`_link_via_certificate` (app/api/v1/external/product_attachments.py) stores each matched product's
`requested_code` as `certificate_products.model_code` with `model_code_source = 'ai'`, except when the
match came `via == prefix` (no longer reached on this path, CERT-LINK-CLEANUP) and never over a
`manual` code. Reuses the ingest harness of tests/test_certificate_api.py.
"""
from __future__ import annotations

from typing import Any

from app.models.certificate import Certificate, CertificateProduct

from .test_certificate_api import EXTERNAL, _cert_payload, env  # noqa: F401  (fixture + helper)


def _coverage(env, number) -> list[Any]:
    cert = env.db.query(Certificate).filter(Certificate.certificate_number == number).one()
    env.db.expire_all()
    return env.db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id).all()


def test_ingest_stores_the_requested_code_as_an_ai_model_code(env):
    attachment = env.attachment(env.attachment_type(is_certificate=True, name="Certification"), "qcert-ing")
    product = env.product("QING", code="ZZTQCERT8355")
    payload = _cert_payload(attachment, [product], certificate_number="QCERT-ING-1")
    payload["products"] = ["ZZTQCERT8355"]
    r = env.client.post(EXTERNAL, json=payload)
    assert r.status_code == 200, r.text
    (row,) = _coverage(env, "QCERT-ING-1")
    assert row.model_code == "ZZTQCERT8355" and row.model_code_source == "ai"


def test_ingest_no_longer_links_a_family_prefix(env):
    """CERT-LINK-CLEANUP R8 (owner Q2 (a), 8 Nov): the family-prefix tier is off for certificates, so
    a family head links nothing and is reported unmatched (it used to link the family code-less)."""
    attachment = env.attachment(env.attachment_type(is_certificate=True, name="Certification"), "qcert-pfx")
    env.product("QPFX", code="ZZTFAMILY7-RL")
    payload = _cert_payload(attachment, [], certificate_number="QCERT-ING-2")
    payload["products"] = ["ZZTFAMILY7 - FAMILY NAME"]
    r = env.client.post(EXTERNAL, json=payload)
    assert r.status_code == 200, r.text
    assert _coverage(env, "QCERT-ING-2") == []
    assert r.json()["skipped_product_codes"] == ["ZZTFAMILY7 - FAMILY NAME"]


def test_ingest_never_overwrites_a_manual_code(env):
    attachment = env.attachment(env.attachment_type(is_certificate=True, name="Certification"), "qcert-man")
    product = env.product("QMAN", code="ZZTQMAN1111")
    payload = _cert_payload(attachment, [product], certificate_number="QCERT-ING-3")
    payload["products"] = ["ZZTQMAN1111"]
    assert env.client.post(EXTERNAL, json=payload).status_code == 200
    (row,) = _coverage(env, "QCERT-ING-3")
    row.model_code, row.model_code_source = "MAN 1111", "manual"
    env.db.commit()
    again = env.client.post(EXTERNAL, json=payload)
    assert again.status_code == 200, again.text
    (row,) = _coverage(env, "QCERT-ING-3")
    assert row.model_code == "MAN 1111" and row.model_code_source == "manual"


def test_ingest_keeps_a_manual_default_box_cache_when_the_ai_code_changes(env):
    attachment = env.attachment(env.attachment_type(is_certificate=True, name="Certification"), "qcert-cache")
    product = env.product("QCACHE", code="ZZTQCACHE5555")
    payload = _cert_payload(attachment, [product], certificate_number="QCERT-ING-4")
    payload["products"] = ["ZZTQCACHE5555"]
    assert env.client.post(EXTERNAL, json=payload).status_code == 200
    (row,) = _coverage(env, "QCERT-ING-4")
    cache = {"revision_id": "r", "code": "ZZTQCACHE5555", "source": "manual", "has_text": True, "boxes": []}
    row.boxes = cache
    env.db.commit()
    payload["products"] = ["zztqcache5555"]
    assert env.client.post(EXTERNAL, json=payload).status_code == 200
    (row,) = _coverage(env, "QCERT-ING-4")
    assert row.boxes == cache
