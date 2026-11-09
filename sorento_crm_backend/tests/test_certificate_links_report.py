"""CERT-LINK-CLEANUP red tests: the "Certificate links to check" report, the check job, Confirm and Remove.

Card `documentation/plans/certificates/CARD-cert-link-cleanup-08nov.md` R1-R7, owner answers Q1-Q3 (8 Nov).
Reuses the API harness of tests/test_certificate_api.py (blank scratch schema, superadmin principal).
"""
from __future__ import annotations

import pymupdf
import pytest

from app.models.audit import AuditLog
from app.models.certificate import Certificate, CertificateProduct
from app.models.product import Product

from .test_certificate_api import EXTERNAL, _cert_payload, env  # noqa: F401  (fixture + helper)

LINKS = "/api/v1/master-data/certificate-links"


def _pdf(lines):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for i, line in enumerate(lines):
        page.insert_text((60, 100 + 20 * i), line, fontsize=11)
    out = doc.tobytes()
    doc.close()
    return out


def _blank():
    doc = pymupdf.open()
    doc.new_page()
    out = doc.tobytes()
    doc.close()
    return out


@pytest.fixture
def files(monkeypatch):
    """Attachment id -> bytes. A missing id raises, like a storage miss."""
    store: dict[str, bytes] = {}

    def fake(self, attachment):
        data = store.get(str(attachment.id))
        if data is None:
            raise Exception("no file")
        return data

    from app.services.resources_service import AttachmentService

    monkeypatch.setattr(AttachmentService, "get_file_content_for", fake)
    return store


def _certificate(env, files, number, lines, codes, products, *, scanned=False):
    """Seed via the ingest with a scan (printed check skipped) so every product links, then put the
    real text in place: an AI-linked certificate whose links the report must judge."""
    for code in products:
        env.product("L", code=code)
    attachment = env.attachment(env.attachment_type(is_certificate=True, name="Certification"), number)
    files[str(attachment.id)] = _blank()
    payload = _cert_payload(attachment, [], certificate_number=number)
    payload["products"] = codes
    r = env.client.post(EXTERNAL, json=payload)
    assert r.status_code == 200, r.text
    files[str(attachment.id)] = _blank() if scanned else _pdf(lines)
    return env.db.query(Certificate).filter(Certificate.certificate_number == number).one()


def _run_check(env, certificate_ids=None):
    from app.services import certificate_link_report_service as report

    report.check_certificates(env.db, certificate_ids or report.pending_certificate_ids(env.db))
    env.db.expire_all()


def _rows(env, **params):
    r = env.client.get(LINKS, params={"limit": 100, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _by_code(body):
    return {row["product_code"]: row for row in body["data"]}


def test_unchecked_links_read_checking_and_count_as_pending(env, files):
    cert = _certificate(env, files, "RPT-1", ["Model 14A"], ["SV-14A-CP", "BRD7711CP"], ["SV-14A-CP", "BRD7711CP"])
    body = _rows(env, certificate_ids=str(cert.id))
    assert {row["verdict"] for row in body["data"]} == {"pending"}
    assert body["summary"]["pending"] == 2


def test_check_stamps_found_check_and_not_found(env, files):
    """Crew ruling 8 Nov: the short `14A` is Check, never Found; `11C` inside `BRD7711CP` is not on a
    boundary; the longer `CSK14A` printed on its own row is Found."""
    cert = _certificate(
        env,
        files,
        "RPT-2",
        ["SPAN stop valve", "Model 14A DN20", "Model 11C DN15", "Model CSK14A"],
        ["14A", "BRD7711CP", "CSK14A"],
        ["SV-14A-CP", "CSK14A-BL", "BRD7711CP"],
    )
    for link in env.db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id):
        if link.product.product_code == "BRD7711CP":
            link.model_code = "11C"
    env.db.commit()
    _run_check(env)
    rows = _by_code(_rows(env, certificate_ids=str(cert.id), verdict="found,check,not_found"))
    assert rows["SV-14A-CP"]["verdict"] == "check"
    assert rows["CSK14A-BL"]["verdict"] == "found"
    assert rows["BRD7711CP"]["verdict"] == "not_found"
    row = rows["SV-14A-CP"]
    assert row["certificate_number"] == "RPT-2" and row["scheme"] == "PPS"
    assert row["source"] == "ai" and row["model_code"] == "14A"
    assert row["certificate_type"] and row["product_name"]


def test_scanned_and_missing_files(env, files):
    scan = _certificate(env, files, "RPT-3", [], ["SV-14A-CP"], ["SV-14A-CP"], scanned=True)
    gone = _certificate(env, files, "RPT-4", ["x"], ["SV-15A-CP"], ["SV-15A-CP"])
    files.pop(str(gone.current_revision.attachment_id))
    _run_check(env)
    assert _rows(env, certificate_ids=str(scan.id))["data"][0]["verdict"] == "scanned"
    assert _rows(env, certificate_ids=str(gone.id))["data"][0]["verdict"] == "no_file"


def test_filters_by_verdict_certificate_and_source(env, files):
    a = _certificate(env, files, "RPT-5", ["Model 14A"], ["14A", "BRD7711CP"], ["SV-14A-CP", "BRD7711CP"])
    b = _certificate(env, files, "RPT-6", ["Model SV7788B"], ["SV7788B"], ["SV7788B-CP"])
    _run_check(env)
    body = _rows(env, verdict="not_found")
    assert [row["product_code"] for row in body["data"]] == ["BRD7711CP"]
    assert body["pagination"]["total"] == 1
    assert {row["certificate_id"] for row in _rows(env, certificate_ids=str(b.id))["data"]} == {str(b.id)}
    assert len(_rows(env, verdict="found,not_found")["data"]) == 2
    assert _rows(env, source="manual")["data"] == []
    assert _rows(env)["summary"] == {"found": 1, "check": 1, "not_found": 1, "scanned": 0, "no_file": 0, "pending": 0}
    assert a.id


def test_query_searches_product_code_name_and_certificate_number(env, files):
    _certificate(env, files, "RPT-7", ["Model 14A"], ["14A"], ["SV-14A-CP"])
    _certificate(env, files, "RPT-8", ["Model 77B"], ["77B"], ["SV-77B-CP"])
    assert [r["product_code"] for r in _rows(env, query="77b")["data"]] == ["SV-77B-CP"]
    assert [r["certificate_number"] for r in _rows(env, query="RPT-7")["data"]] == ["RPT-7"]


def test_sorts_from_an_allowlist(env, files):
    _certificate(env, files, "RPT-9", ["Model 14A"], ["14A"], ["SV-14A-CP", "AB-14A", "ZZ-14A"])
    codes = [r["product_code"] for r in _rows(env, sort="product_code", dir="desc")["data"]]
    assert codes == sorted(codes, reverse=True)
    assert _rows(env, sort="not_a_column")["data"]  # unknown sort is ignored, never a 500


def test_a_changed_code_or_revision_reads_checking_again(env, files):
    cert = _certificate(env, files, "RPT-10", ["Model 14A"], ["14A"], ["SV-14A-CP"])
    _run_check(env)
    (link,) = env.db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id).all()
    link.model_code, link.model_code_source = "SV-14A-CP", "manual"
    env.db.commit()
    assert _rows(env, certificate_ids=str(cert.id))["data"][0]["verdict"] == "pending"
    _run_check(env, [str(cert.id)])
    assert _rows(env, certificate_ids=str(cert.id))["data"][0]["verdict"] == "not_found"


def test_check_route_queues_only_certificates_with_pending_links(env, files, monkeypatch):
    stale = _certificate(env, files, "RPT-11", ["Model 14A"], ["14A"], ["SV-14A-CP"])
    fresh = _certificate(env, files, "RPT-12", ["Model 77B"], ["77B"], ["SV-77B-CP"])
    _run_check(env, [str(fresh.id)])
    queued = []
    from app.services import certificate_link_report_service as report

    monkeypatch.setattr(report, "enqueue_job", lambda func, *a, **k: queued.append((func, a, k)))
    r = env.client.post(f"{LINKS}/check")
    assert r.status_code == 200, r.text
    assert r.json() == {"queued": 1}
    (func, args, kwargs) = queued[0]
    assert kwargs.get("queue_name") == "flyer_read"
    assert list(args[0]) == [str(stale.id)]
    assert kwargs.get("job_id", "").startswith("certificate-link-check-")


def test_check_route_does_not_queue_the_same_set_twice(env, files, monkeypatch):
    """Security review S3: links stay pending until the job runs; a second visit must not stack jobs."""
    _certificate(env, files, "RPT-11B", ["Model 14A"], ["14A"], ["SV-14A-CP"])
    queued = []
    from app.services import certificate_link_report_service as report

    monkeypatch.setattr(report, "enqueue_job", lambda func, *a, **k: queued.append(k["job_id"]))
    monkeypatch.setattr(report, "_already_queued", lambda job_id: job_id in queued)
    assert env.client.post(f"{LINKS}/check").json() == {"queued": 1}
    assert env.client.post(f"{LINKS}/check").json() == {"queued": 1}
    assert len(queued) == 1


def test_an_empty_check_list_checks_nothing(env, files):
    """The worker runs with the scope off: an empty list must never widen to every pending link."""
    from app.services import certificate_link_report_service as report

    _certificate(env, files, "RPT-11C", ["Model 14A"], ["14A"], ["SV-14A-CP"])
    assert report.check_certificates(env.db, []) == {"certificates": 0, "links": 0}


def test_confirm_flips_source_to_manual_and_writes_one_audit_row_per_link(env, files):
    cert = _certificate(env, files, "RPT-13", ["Model 14A"], ["14A", "BRD7711CP"], ["SV-14A-CP", "BRD7711CP"])
    links = env.db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id).all()
    ids = [str(link.id) for link in links]
    r = env.client.post(f"{LINKS}/confirm", json={"ids": ids})
    assert r.status_code == 200, r.text
    assert r.json() == {"confirmed": 2}
    env.db.expire_all()
    assert {link.source for link in env.db.query(CertificateProduct).filter(CertificateProduct.id.in_(ids))} == {"manual"}
    rows = env.db.query(AuditLog).filter(AuditLog.event == "certificate_link_confirmed").all()
    assert len(rows) == 2
    assert all(row.old_values["source"] == "ai" and row.new_values["source"] == "manual" for row in rows)
    assert {row.root_entity_type for row in rows} == {"product"}
    # Confirmed links leave the default (AI only) view.
    assert _rows(env, certificate_ids=str(cert.id), source="ai")["data"] == []


def test_confirm_of_an_unknown_id_is_404_and_changes_nothing(env, files):
    cert = _certificate(env, files, "RPT-14", ["Model 14A"], ["14A"], ["SV-14A-CP"])
    (link,) = env.db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id).all()
    r = env.client.post(f"{LINKS}/confirm", json={"ids": [str(link.id), "11111111-2222-4333-8444-555566667777"]})
    assert r.status_code == 404
    env.db.expire_all()
    assert env.db.get(CertificateProduct, str(link.id)).source == "ai"


def test_remove_is_a_destructive_pending_action_that_unlinks_and_audits(env, files):
    from app.services.form_action_registry import action_for

    cert = _certificate(env, files, "RPT-15", ["Model 14A"], ["BRD7711CP"], ["BRD7711CP"])
    (link,) = env.db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id).all()
    attachment_id = cert.current_revision.attachment_id
    assert env.projection(attachment_id)
    action = action_for("certificate_link.remove")
    assert action.permission == "master_data.certificates.edit"
    assert action.window == "destructive"
    action.execute(env.db, {"entity_id": str(link.id), "requested_by_id": None})
    env.db.expire_all()
    assert env.db.get(CertificateProduct, str(link.id)) is None
    assert env.projection(attachment_id) == []
    assert env.db.query(AuditLog).filter(AuditLog.event == "file_unlinked").count() == 1


def test_remove_of_an_unknown_link_is_404(env, files):
    from app.services.error_handler import AppException
    from app.services.form_action_registry import action_for

    with pytest.raises(Exception) as caught:
        action_for("certificate_link.remove").execute(
            env.db, {"entity_id": "11111111-2222-4333-8444-555566667777", "requested_by_id": None}
        )
    assert getattr(caught.value, "status_code", None) == 404 or isinstance(caught.value, AppException)


@pytest.mark.parametrize(
    "method,path,body",
    [("get", "", None), ("post", "/confirm", {"ids": []}), ("post", "/check", None)],
)
def test_routes_deny_a_user_without_grants(env, method, path, body):
    env.act_as_plain_user()
    r = getattr(env.client, method)(f"{LINKS}{path}", **({"json": body} if body is not None else {}))
    assert r.status_code == 403


def test_another_companys_links_are_invisible_and_untouchable(env, files):
    """`certificate_products` is unscoped; every read goes through the scoped certificate."""
    from tests._mc_lookup_seed import MOCHA_ID, attachment_type, certificate, certificate_product, product, seed_mocha

    seed_mocha(env.db)
    from app.models.base import set_company_scope

    set_company_scope(env.db, frozenset({MOCHA_ID}))
    type_id = attachment_type(env.db).id
    p = product(env.db, company_id=MOCHA_ID)
    cert = certificate(env.db, company_id=MOCHA_ID, attachment_type_id=type_id)
    link_id = str(certificate_product(env.db, certificate_id=cert.id, product_id=p.id).id)
    env.db.commit()
    from app.services import certificate_link_report_service as report

    assert any(row["id"] == link_id for row in report.list_links(env.db)["data"])  # seen in its own company
    # The API pins the incumbent company only (see the env fixture).
    assert all(row["id"] != link_id for row in _rows(env)["data"])
    assert env.client.post(f"{LINKS}/confirm", json={"ids": [link_id]}).status_code == 404
    # Remove at park time: refused before anything is parked (security review B1).
    parked = env.client.post(
        "/api/v1/pending-actions",
        json={"action_key": "certificate_link.remove", "entity_type": "certificate_link", "entity_id": link_id},
    )
    assert parked.status_code == 404, parked.text
    # Remove at commit time, under the incumbent scope: 404 and the row stays.
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from app.services.form_action_registry import action_for

    set_company_scope(env.db, frozenset({DEFAULT_COMPANY_ID}))
    with pytest.raises(Exception) as caught:
        action_for("certificate_link.remove").execute(env.db, {"entity_id": link_id, "requested_by_id": None})
    assert getattr(caught.value, "status_code", None) == 404
    set_company_scope(env.db, frozenset({MOCHA_ID}))
    assert env.db.query(CertificateProduct).filter(CertificateProduct.id == link_id).count() == 1


def test_a_visible_link_parks_its_remove(env, files):
    cert = _certificate(env, files, "RPT-16", ["Model 14A"], ["BRD7711CP"], ["BRD7711CP"])
    (link,) = env.db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id).all()
    parked = env.client.post(
        "/api/v1/pending-actions",
        json={"action_key": "certificate_link.remove", "entity_type": "certificate_link", "entity_id": str(link.id)},
    )
    assert parked.status_code == 202, parked.text


def test_set_members_linked_through_a_printed_set_code_are_found(env, files):
    """Reviewer round 1 blocker: correct set coverage must never sit in the Not found view."""
    from app.models.product_set import ProductSet, ProductSetMember

    for code in ("WB-8800", "WB-8801"):
        env.product("S", code=code)
    members = env.db.query(Product).filter(Product.product_code.in_(["WB-8800", "WB-8801"])).all()
    product_set = ProductSet(set_code="SRTSET-100", name="Basin pack")
    env.db.add(product_set)
    env.db.flush()
    for order, member in enumerate(members):
        env.db.add(ProductSetMember(product_set_id=product_set.id, product_id=member.id, sort_order=order))
    env.db.flush()
    cert = _certificate(env, files, "RPT-17", ["Set SRTSET-100 basin pack"], ["SRTSET-100"], [])
    _run_check(env)
    rows = _by_code(_rows(env, certificate_ids=str(cert.id)))
    assert {code: row["verdict"] for code, row in rows.items()} == {"WB-8800": "found", "WB-8801": "found"}


def test_filters_by_certificate_type_and_status_and_lists_the_types(env, files):
    a = _certificate(env, files, "RPT-18", ["Model 14A"], ["14A"], ["SV-14A-CP"])
    b = _certificate(env, files, "RPT-19", ["Model 77B"], ["77B"], ["SV-77B-CP"])
    b.status = "archived"
    env.db.commit()
    body = _rows(env)
    assert {t["id"] for t in body["types"]} == {str(a.attachment_type_id), str(b.attachment_type_id)}
    only_a = _rows(env, attachment_type_ids=str(a.attachment_type_id))
    assert {r["certificate_number"] for r in only_a["data"]} == {"RPT-18"}
    archived = _rows(env, status="archived")
    assert {r["certificate_number"] for r in archived["data"]} == {"RPT-19"}


def test_a_certificate_already_checked_is_not_read_again(env, files, monkeypatch):
    """Reviewer round 2: a second job carrying ids an earlier job has done reads nothing."""
    from app.services import certificate_link_report_service as report

    cert = _certificate(env, files, "RPT-20", ["Model 14A"], ["14A"], ["SV-14A-CP"])
    assert report.check_certificates(env.db, [str(cert.id)]) == {"certificates": 1, "links": 1}
    reads = []
    monkeypatch.setattr(report, "_read_current_text", lambda *a: reads.append(a) or None)
    assert report.check_certificates(env.db, [str(cert.id)]) == {"certificates": 0, "links": 0}
    assert reads == []


def test_manual_links_are_checked_too_and_counted_outside_the_view(env, files):
    """Crew pass 8 Nov: manual links sat at Checking because the AI-only view never asked for them."""
    cert = _certificate(env, files, "RPT-21", ["Model SRTWB1515"], ["SRTWB1515"], ["SRTWB1515"])
    (link,) = env.db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id).all()
    link.source = "manual"
    env.db.commit()
    body = _rows(env, source="ai")
    assert body["summary"]["pending"] == 0
    assert body["pending_all"] == 1
    _run_check(env)
    assert _rows(env, source="manual")["data"][0]["verdict"] == "found"
    assert _rows(env, source="ai")["pending_all"] == 0


def test_confirm_reads_found_after_the_recheck(env, files):
    """Reviewer round 3: a confirmed short link must not read Check forever."""
    from app.services import certificate_link_report_service as report

    cert = _certificate(env, files, "RPT-22", ["Model 14A"], ["14A"], ["SV-14A-CP"])
    _run_check(env)
    (link,) = env.db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id).all()
    assert _rows(env, certificate_ids=str(cert.id), verdict="check")["data"][0]["id"] == str(link.id)
    assert env.client.post(f"{LINKS}/confirm", json={"ids": [str(link.id)]}).status_code == 200
    row = _rows(env, certificate_ids=str(cert.id), source="manual")["data"][0]
    assert row["verdict"] == "pending"  # the source is part of the key, so it is read again
    _run_check(env)
    assert _rows(env, certificate_ids=str(cert.id), source="manual")["data"][0]["verdict"] == "found"
    assert report.pending_link_count(env.db) == 0


def test_confirming_a_link_with_no_code_reads_found(env, files):
    """Crew re-check: most links carry no model code; a Confirm must still come back Found."""
    cert = _certificate(env, files, "RPT-23", ["Model WB 241"], ["SRTWB241"], ["SRTWB241"])
    (link,) = env.db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id).all()
    link.model_code, link.model_code_source = None, None
    env.db.commit()
    _run_check(env)
    assert env.client.post(f"{LINKS}/confirm", json={"ids": [str(link.id)]}).status_code == 200
    _run_check(env)
    assert _rows(env, certificate_ids=str(cert.id), source="manual")["data"][0]["verdict"] == "found"


def test_the_check_job_applies_rule_b_cat_over_the_catalogue(env, files):
    """A digit-led run in one catalogue family reads Found; in two families, Check."""
    for code in ("M459A-75-RG", "M460A-75-RG", "SRTWT165-QT"):
        env.product("C", code=code)
    cert = _certificate(env, files, "RPT-24", ["Model 162-QT", "Model 75-RG"], ["162-QT", "75-RG"], ["SRTWT162-QT"])
    links = {lk.product.product_code: lk for lk in env.db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id)}
    assert set(links) == {"SRTWT162-QT", "M459A-75-RG", "M460A-75-RG"}
    _run_check(env)
    rows = _by_code(_rows(env, certificate_ids=str(cert.id), verdict="found,check,not_found"))
    assert rows["SRTWT162-QT"]["verdict"] == "found"
    assert rows["M459A-75-RG"]["verdict"] == "check"
    assert rows["M460A-75-RG"]["verdict"] == "check"


def test_b_cat_reads_only_active_products_and_the_linked_products_own_family(env, files):
    """Reviewer round 5: an inactive product in a second family does not make `162-QT` ambiguous, and a
    link to an inactive product never reads Found through another family."""
    inactive_other = env.product("C", code="ORI162-QT")
    inactive_other.is_active = False
    env.db.flush()
    cert = _certificate(env, files, "RPT-25", ["Model 162-QT"], ["162-QT"], ["SRTWT162-QT", "XYZ162-QT"])
    xyz = env.db.query(Product).filter(Product.product_code == "XYZ162-QT").one()
    xyz.is_active = False
    env.db.commit()
    _run_check(env)
    rows = _by_code(_rows(env, certificate_ids=str(cert.id), verdict="found,check,not_found"))
    assert rows["SRTWT162-QT"]["verdict"] == "found"
    assert rows["XYZ162-QT"]["verdict"] == "check"
