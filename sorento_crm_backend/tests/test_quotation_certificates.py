"""QUOTE-CERT-TAB red tests: the quotation Certification tab, backend (UAC tests 3-9).

Written BEFORE the implementation, from `documentation/plans/certificates/quote-cert-tab-08nov-acceptance-criteria.md`
(v2, normalised matcher + suggested codes + dedupe by file). Numbers in test names follow the UAC list.

Nothing here imports the not-yet-built service at module level; each test fails at its first call
into new code (a 404 route, a missing column, a missing module).

Assumptions the coder should know about (the UAC is silent):
  * routes are mounted under the real project router prefix `/api/v1/project-sales/projects/...`.
  * the service is exercised through the routes; only its module name is pinned.
  * the export task is run with the exact `(func, args, kwargs)` the route enqueued.
  * the per-quote rows are read through `Base.metadata.tables["projects.quotation_document_certificates"]`.

Postgres only via `blank_session`; every chain is seeded here. The storage read seam is
`AttachmentService.get_file_content_for`, patched to return PDFs generated in-test.
"""
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from ._pg_fixture import blank_session
from .test_certificate_pdf_service import image_only_pdf, table_pdf
from .test_project_quotation_pdf import _attachment, _issue, _product, _setup
from .test_project_spec_sheet import _client, _document, _line, _restore, _scope, _wc_set

VIEW_ONLY = ["projects.projects.view"]
EDIT_NO_CERT_VIEW = [
    "projects.projects.view",
    "projects.projects.edit",
    "projects.projects.manage",
    "projects.projects.delete",
]
# Adding a certificate by hand also needs the register's view right (the picker reads the register).
EDIT_SLUGS = EDIT_NO_CERT_VIEW + ["master_data.certificates.view"]
DEFAULTS = EDIT_SLUGS + ["master_data.certificates.edit"]
PENDING = "/api/v1/pending-actions"
FUTURE = date.today() + timedelta(days=400)
PAST = date.today() - timedelta(days=30)


def _uid() -> str:
    return str(uuid.uuid4())


# ------------------------------------------------------------------ seed helpers


@pytest.fixture
def files(monkeypatch):
    """The storage seam: attachment id -> PDF bytes. A missing id raises, like an unreadable object."""
    from app.services.resources_service import AttachmentService

    store: dict[str, bytes] = {}

    def read(self, attachment):
        try:
            return store[str(attachment.id)]
        except KeyError:
            raise FileNotFoundError(str(attachment.id))

    monkeypatch.setattr(AttachmentService, "get_file_content_for", read)
    return store


def _pdf(*codes: str) -> bytes:
    return table_pdf([[(code, ["description"], 30) for code in codes]])


def _draft(db):
    """A document with NO issue: products a and b as lines, and a WC set line."""
    env = _setup(db)
    document = _document(db, env)
    scope = _scope(db, env, document)
    tok = _uid()[:6].upper()
    a = _product(db, env["category"].id, env["uom"], description="zzt a", code=f"ZZT{tok}WB1515")
    b = _product(db, env["category"].id, env["uom"], description="zzt b", code=f"ZZT{tok}WC8355")
    wc_set, pedestal, valve, hose = _wc_set(db, env)
    line_a = _line(db, env, scope, {"product_id": a.id})
    _line(db, env, scope, {"product_id": b.id})
    _line(db, env, scope, {"product_set_id": wc_set.id})
    return {
        **env,
        "document": document,
        "scope": scope,
        "a": a,
        "b": b,
        "line_a": line_a,
        "ped": pedestal,
        "valve": valve,
        "hose": hose,
    }


def _cert(
    db,
    c,
    files,
    *,
    scheme="ZZT5",
    covers=(),
    pdf=None,
    valid_until=FUTURE,
    status="active",
    company_id=None,
    file_hash=None,
    attachment=None,
    link_source="manual",
):
    """A certificate with a current revision. `covers` = [(product, model_code|None, source|None)]."""
    from app.models.certificate import Certificate, CertificateProduct, CertificateRevision

    cert = Certificate(
        id=_uid(),
        company_id=company_id or c["company_id"],
        scheme=scheme,
        certificate_number=f"ZZT-{_uid()[:8]}",
        status=status,
    )
    db.add(cert)
    db.flush()
    att = attachment
    if att is None and pdf is not None:
        att = _attachment(db, c["company_id"], name=f"{_uid()[:6]}.pdf")
        att.file_hash = file_hash
        db.flush()
        files[str(att.id)] = pdf
    elif att is not None and pdf is not None:
        files[str(att.id)] = pdf
    rev = CertificateRevision(
        id=_uid(),
        certificate_id=cert.id,
        revision_no=1,
        attachment_id=att.id if att is not None else None,
        valid_until=valid_until,
        is_current=True,
        source="manual",
    )
    db.add(rev)
    db.flush()
    cert.current_revision_id = rev.id
    cps = {}
    for product, code, source in covers:
        cp = CertificateProduct(
            id=_uid(),
            certificate_id=cert.id,
            product_id=product.id,
            source=link_source,
            model_code=code,
            model_code_source=source,
        )
        db.add(cp)
        cps[product.id] = cp
    db.flush()
    return SimpleNamespace(cert=cert, rev=rev, att=att, cps=cps, id=cert.id)


def _new_revision(db, cr, files, pdf):
    """A renewal: a new current revision with its own file."""
    from app.models.certificate import CertificateRevision

    cr.rev.is_current = False
    att = _attachment(db, cr.cert.company_id or "", name=f"{_uid()[:6]}.pdf")
    files[str(att.id)] = pdf
    rev = CertificateRevision(
        id=_uid(),
        certificate_id=cr.cert.id,
        revision_no=2,
        attachment_id=att.id,
        valid_until=FUTURE,
        is_current=True,
        source="manual",
    )
    db.add(rev)
    db.flush()
    cr.cert.current_revision_id = rev.id
    db.flush()
    return rev


@contextmanager
def _api(db, c, slugs=EDIT_SLUGS):
    from app.models.base import company_scope

    db.commit()
    with company_scope(db, frozenset({c["company_id"]})):
        client, originals = _client(db, c["owner"], slugs=slugs)
        try:
            yield client
        finally:
            _restore(originals)


def _u(c, suffix="", document=None):
    return (
        f"/api/v1/project-sales/projects/{c['project'].id}/quotation-documents/"
        f"{(document or c['document']).id}/certificates{suffix}"
    )


def _items(client, c):
    r = client.get(_u(c))
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _ids(items):
    return [i["certificate_id"] for i in items]


def _markers(db, c):
    from app.database import Base

    table = Base.metadata.tables["projects.quotation_document_certificates"]
    db.expire_all()
    return [
        dict(r)
        for r in db.execute(select(table).where(table.c.document_id == c["document"].id)).mappings().all()
    ]


def _lapse(db, parked_id):
    from app.models.sla import SlaFormAction

    db.query(SlaFormAction).filter(SlaFormAction.id == parked_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)}, synchronize_session=False
    )
    db.commit()


def _remove_key(c, certificate_id):
    """One pending action per certificate of a quote: `<document id>:<certificate id>`."""
    return f"{c['document'].id}:{certificate_id}"


def _park_remove(client, c, certificate_id):
    return client.post(
        PENDING,
        json={
            "action_key": "quotation_certificate.remove",
            "entity_type": "quotation_certificate",
            "entity_id": _remove_key(c, certificate_id),
            "payload": {},
        },
    )


def _remove(client, db, c, certificate_id):
    parked = _park_remove(client, c, certificate_id)
    assert parked.status_code == 202, parked.text
    _lapse(db, parked.json()["id"])
    current = client.get(
        f"{PENDING}/current",
        params={"entity_type": "quotation_certificate", "entity_id": _remove_key(c, certificate_id)},
    )
    assert current.status_code == 200, current.text
    db.expire_all()


def _box(page=1, x=0.1, y=0.2, w=0.3, h=0.05, product_id=None):
    return {"page": page, "x": x, "y": y, "w": w, "h": h, "product_id": product_id}


def _code_of(r):
    return r.json().get("code")


def test_00_the_service_module_exists():
    import app.services.quotation_certificate_service  # noqa: F401


# ------------------------------------------------------------------ 3 list


def test_03_list_distinct_certificates_with_shared_cert_set_parts_and_order(files):
    from app.models.company import Company

    with blank_session() as db:
        c = _draft(db)
        other = Company(id=_uid(), name="ZZT Other", code=f"ZZ{_uid()[:6]}", is_active=True)
        db.add(other)
        db.flush()
        pdf = _pdf("WB 1515", "WC 8355")
        shared = _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], "WB 1515", "manual"), (c["b"], "WC 8355", "manual")], pdf=pdf)
        part = _cert(db, c, files, scheme="ZZT2", covers=[(c["ped"], "PED 1234", "manual")], pdf=_pdf("PED 1234"))
        first = _cert(db, c, files, scheme="ZZT0", covers=[(c["valve"], "AV 5678", "manual")], pdf=_pdf("AV 5678"))
        archived = _cert(db, c, files, scheme="ZZT3", covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"), status="archived")
        foreign = _cert(db, c, files, scheme="ZZT4", covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"), company_id=other.id)
        unrelated_product = _product(db, c["category"].id, c["uom"], description="zzt unrelated")
        unrelated = _cert(db, c, files, scheme="ZZT6", covers=[(unrelated_product, "UN 1111", "manual")], pdf=_pdf("UN 1111"))
        with _api(db, c) as client:
            items = _items(client, c)
            assert _ids(items) == [first.id, shared.id, part.id], _ids(items)
            row = next(i for i in items if i["certificate_id"] == shared.id)
            assert [p["product_code"] for p in row["products"]] == sorted([c["a"].product_code, c["b"].product_code])
            assert row["source"] == "auto"
            assert row["has_file"] is True
            assert row["validity_state"] == "valid"
            assert row["also_filed_as"] == []
            for gone in (archived.id, foreign.id, unrelated.id):
                assert gone not in _ids(items)
            body = client.get(_u(c)).json()
            assert body["can_edit"] is True and body["can_edit_defaults"] is False
        with _api(db, c, DEFAULTS) as client:
            assert client.get(_u(c)).json()["can_edit_defaults"] is True
        with _api(db, c, VIEW_ONLY) as client:
            assert client.get(_u(c)).json()["can_edit"] is False


def test_03_a_removed_product_drops_its_auto_certificate(files):
    from app.models.projects import ProjectQuotationLine

    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c) as client:
            assert _ids(_items(client, c)) == [cr.id]
            db.query(ProjectQuotationLine).filter(ProjectQuotationLine.id == c["line_a"].id).delete()
            db.commit()
            assert _items(client, c) == []


def test_03_validity_states(files):
    with blank_session() as db:
        c = _draft(db)
        valid = _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        expired = _cert(db, c, files, scheme="ZZT2", covers=[(c["b"], "WC 8355", "manual")], pdf=_pdf("WC 8355"), valid_until=PAST)
        unknown = _cert(db, c, files, scheme="ZZT3", covers=[(c["ped"], "PED 1234", "manual")], pdf=_pdf("PED 1234"), valid_until=None)
        with _api(db, c) as client:
            by = {i["certificate_id"]: i for i in _items(client, c)}
            assert by[valid.id]["validity_state"] == "valid"
            assert by[expired.id]["validity_state"] == "expired"
            assert by[unknown.id]["validity_state"] == "unknown"
            # CERT-9: default send rule
            assert by[valid.id]["send_to_customer"] is True
            assert by[expired.id]["send_to_customer"] is False


# ------------------------------------------------------------------ 3b dedupe by file (CERT-15)


def test_05_same_file_hash_is_one_row_with_the_valid_latest_certificate_as_representative(files):
    with blank_session() as db:
        c = _draft(db)
        pdf = _pdf("WB 1515", "WC 8355")
        expired = _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], "WB 1515", "manual")], pdf=pdf, valid_until=PAST, file_hash="zzt-h1")
        soon = _cert(db, c, files, scheme="ZZT2", covers=[(c["b"], "WC 8355", "manual")], pdf=pdf, valid_until=date.today() + timedelta(days=100), file_hash="zzt-h1")
        late = _cert(db, c, files, scheme="ZZT3", covers=[(c["a"], "WB 1515", "manual")], pdf=pdf, valid_until=date.today() + timedelta(days=300), file_hash="zzt-h1")
        with _api(db, c) as client:
            items = _items(client, c)
            assert _ids(items) == [late.id], items
            row = items[0]
            assert {x["certificate_id"] for x in row["also_filed_as"]} == {expired.id, soon.id}
            assert {"scheme", "certificate_number"} <= set(row["also_filed_as"][0])
            assert {p["product_code"] for p in row["products"]} == {c["a"].product_code, c["b"].product_code}


def test_05_same_attachment_without_a_hash_is_one_row_and_remove_hides_every_member(files):
    with blank_session() as db:
        c = _draft(db)
        first = _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        second = _cert(db, c, files, scheme="ZZT2", covers=[(c["b"], "WB 1515", "manual")], attachment=first.att)
        other = _cert(db, c, files, scheme="ZZT3", covers=[(c["ped"], "PED 1234", "manual")], pdf=_pdf("PED 1234"))
        with _api(db, c) as client:
            items = _items(client, c)
            assert len(items) == 2
            merged = next(i for i in items if i["certificate_id"] in (first.id, second.id))
            assert len(merged["also_filed_as"]) == 1
            _remove(client, db, c, merged["certificate_id"])
            assert _ids(_items(client, c)) == [other.id]
            rows = _markers(db, c)
            assert {r["certificate_id"] for r in rows} == {first.id, second.id}
            assert all(r["included"] is False for r in rows)


# ------------------------------------------------------------------ 4 add and remove


def test_04_add_is_201_idempotent_and_listed_as_manual(files):
    with blank_session() as db:
        c = _draft(db)
        manual = _cert(db, c, files, scheme="ZZT9", pdf=_pdf("NOTHING 1"))
        with _api(db, c) as client:
            assert _items(client, c) == []
            r = client.post(_u(c), json={"certificate_id": manual.id})
            assert r.status_code == 201, r.text
            assert r.json()["certificate_id"] == manual.id
            assert r.json()["source"] == "manual"
            assert r.json()["marked"]["state"] == "none"
            again = client.post(_u(c), json={"certificate_id": manual.id})
            assert again.status_code == 201, again.text
            assert _ids(_items(client, c)) == [manual.id]
            assert len(_markers(db, c)) == 1


def test_04_add_refuses_inactive_foreign_and_unknown_certificates(files):
    from app.models.company import Company

    with blank_session() as db:
        c = _draft(db)
        other = Company(id=_uid(), name="ZZT Other", code=f"ZZ{_uid()[:6]}", is_active=True)
        db.add(other)
        db.flush()
        archived = _cert(db, c, files, status="archived", pdf=_pdf("X 1"))
        foreign = _cert(db, c, files, company_id=other.id, pdf=_pdf("X 1"))
        with _api(db, c) as client:
            for cid in (archived.id, foreign.id, _uid()):
                r = client.post(_u(c), json={"certificate_id": cid})
                assert r.status_code == 404, r.text
                assert _code_of(r) == "certificate_not_found"
            assert client.post(_u(c), json={"certificate_id": "not-a-uuid"}).status_code in (404, 422)
            assert client.post(_u(c), json={}).status_code == 422


def test_04_pending_remove_commits_included_false_for_auto_and_deletes_a_manual_row(files):
    with blank_session() as db:
        c = _draft(db)
        auto = _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        manual = _cert(db, c, files, scheme="ZZT2", pdf=_pdf("NOTHING 1"))
        with _api(db, c) as client:
            assert client.post(_u(c), json={"certificate_id": manual.id}).status_code == 201
            parked = _park_remove(client, c, auto.id)
            assert parked.status_code == 202, parked.text
            assert auto.id in _ids(_items(client, c)), "nothing applies until the window lapses"
            _lapse(db, parked.json()["id"])
            client.get(f"{PENDING}/current", params={"entity_type": "quotation_certificate", "entity_id": _remove_key(c, auto.id)})
            db.expire_all()
            row = next(r for r in _markers(db, c) if r["certificate_id"] == auto.id)
            assert row["included"] is False and row["source"] == "auto"
            _remove(client, db, c, manual.id)
            assert manual.id not in [r["certificate_id"] for r in _markers(db, c)]
            assert _items(client, c) == []
            # re-including a removed certificate puts it back
            back = client.post(_u(c), json={"certificate_id": auto.id})
            assert back.status_code == 201, back.text
            assert _ids(_items(client, c)) == [auto.id]


def test_04_parking_a_remove_needs_the_edit_right_and_a_listed_certificate(files):
    with blank_session() as db:
        c = _draft(db)
        auto = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        unlisted = _cert(db, c, files, scheme="ZZT8", pdf=_pdf("X 1"))
        with _api(db, c, VIEW_ONLY) as client:
            assert _park_remove(client, c, auto.id).status_code == 403
        with _api(db, c) as client:
            refused = _park_remove(client, c, unlisted.id)
            assert 400 <= refused.status_code < 500 and refused.status_code != 403, refused.text


# ------------------------------------------------------------------ 5 boxes, codes, states


def _detail(client, c, cid):
    r = client.get(_u(c, f"/{cid}"))
    assert r.status_code == 200, r.text
    return r.json()


def test_05_default_boxes_are_found_by_the_model_code_and_cached(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WC 1", "WB 1515", "WC 2"))
        with _api(db, c) as client:
            d = _detail(client, c, cr.id)
            assert d["box_source"] == "default"
            assert len(d["boxes"]) == 1
            assert d["boxes"][0]["product_id"] == c["a"].id
            assert d["revision_id"] == cr.rev.id and d["has_text"] is True and d["page_count"] == 1
            prod = d["products"][0]
            assert prod["code_used"] == "WB 1515" and prod["state"] == "found"
            assert prod["model_code_source"] == "manual" and prod["number_only"] is False
            assert prod["product_code"] == c["a"].product_code and "coverage_id" in prod
            assert d["marked"] == {"count": 1, "state": "found"}
            db.expire_all()
            cache = cr.cps[c["a"].id].boxes
            assert cache["revision_id"] == cr.rev.id and cache["source"] == "auto"
            assert cache["code"] == "WB 1515" and len(cache["boxes"]) == 1


def test_05_the_product_code_itself_is_never_searched(files):
    with blank_session() as db:
        c = _draft(db)
        # The file prints the product code verbatim and nothing qualifies as a suggestion.
        cr = _cert(db, c, files, covers=[(c["a"], None, None)], pdf=_pdf(c["a"].product_code))
        with _api(db, c) as client:
            d = _detail(client, c, cr.id)
            assert d["boxes"] == []


def test_05_a_cached_box_is_used_when_current_and_recomputed_when_stale_or_the_code_changed(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        cp = cr.cps[c["a"].id]
        sentinel = [_box(x=0.01, y=0.01, w=0.02, h=0.02, product_id=c["a"].id)]
        with _api(db, c) as client:
            cp.boxes = {"revision_id": cr.rev.id, "code": "WB 1515", "source": "auto", "has_text": True, "boxes": sentinel}
            db.commit()
            assert _detail(client, c, cr.id)["boxes"][0]["x"] == pytest.approx(0.01)
            # stale revision: recomputed from the file
            cp.boxes = {"revision_id": _uid(), "code": "WB 1515", "source": "auto", "has_text": True, "boxes": sentinel}
            db.commit()
            assert _detail(client, c, cr.id)["boxes"][0]["x"] != pytest.approx(0.01)
            # auto cache for another code: recomputed
            cp.boxes = {"revision_id": cr.rev.id, "code": "OLD 9999", "source": "auto", "has_text": True, "boxes": sentinel}
            db.commit()
            assert _detail(client, c, cr.id)["boxes"][0]["x"] != pytest.approx(0.01)
            # a manual cache is trusted whatever the code says
            cp.boxes = {"revision_id": cr.rev.id, "code": "OLD 9999", "source": "manual", "has_text": True, "boxes": sentinel}
            db.commit()
            d = _detail(client, c, cr.id)
            assert d["boxes"][0]["x"] == pytest.approx(0.01)
            assert d["marked"]["state"] == "edited"


def test_05_a_new_revision_invalidates_the_quote_override_and_the_cache(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c) as client:
            put = client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "quote", "boxes": [_box()]})
            assert put.status_code == 200, put.text
            assert _detail(client, c, cr.id)["box_source"] == "quote"
            _new_revision(db, cr, files, _pdf("AA 1", "WB 1515"))
            db.commit()
            d = _detail(client, c, cr.id)
            assert d["box_source"] == "default"
            assert d["revision_id"] != cr.rev.id
            assert len(d["boxes"]) == 1 and d["boxes"][0]["y"] != pytest.approx(0.2)


def test_05_a_suggested_code_is_persisted_on_first_read_and_its_box_is_just_marked(files):
    # CERT-TAB-UX (owner, 11 Nov): no "Suggested, check" state; a guessed code's box is "found".
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], None, None)], pdf=_pdf("XX 1", "WB 1515"))
        cp = cr.cps[c["a"].id]
        with _api(db, c) as client:
            row = _items(client, c)[0]
            assert row["marked"]["state"] == "found" and row["marked"]["count"] == 1
            db.expire_all()
            assert cp.model_code == "WB 1515" and cp.model_code_source == "ai"
            d = _detail(client, c, cr.id)
            assert d["products"][0]["state"] == "found"
            assert d["products"][0]["model_code_source"] == "ai"


def test_05_a_manual_code_is_never_overwritten_by_a_suggestion(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "NOPE 9", "manual")], pdf=_pdf("WB 1515"))
        cp = cr.cps[c["a"].id]
        with _api(db, c) as client:
            row = _items(client, c)[0]
            assert row["marked"] == {"count": 0, "state": "not_found"}
            db.expire_all()
            assert cp.model_code == "NOPE 9" and cp.model_code_source == "manual"


def test_05_no_code_and_no_suggestion_is_code_needed_with_no_box(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], None, None)], pdf=_pdf("ZZ 9", "QQ 12"))
        with _api(db, c) as client:
            row = _items(client, c)[0]
            assert row["marked"] == {"count": 0, "state": "code_needed"}
            d = _detail(client, c, cr.id)
            assert d["boxes"] == [] and d["products"][0]["state"] == "code_needed"
            assert d["products"][0]["code_used"] in (None, "")


def test_05_number_only_codes_are_flagged_not_blocked(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "1515", "manual")], pdf=_pdf("1515"))
        with _api(db, c) as client:
            d = _detail(client, c, cr.id)
            assert d["products"][0]["number_only"] is True
            assert len(d["boxes"]) == 1


def test_05_marked_state_values(files):
    with blank_session() as db:
        c = _draft(db)
        found = _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        no_file = _cert(db, c, files, scheme="ZZT2", covers=[(c["b"], "WC 8355", "manual")], pdf=None)
        no_text = _cert(db, c, files, scheme="ZZT3", covers=[(c["ped"], "PED 1234", "manual")], pdf=image_only_pdf())
        not_found = _cert(db, c, files, scheme="ZZT4", covers=[(c["valve"], "AV 5678", "manual")], pdf=_pdf("OTHER 1"))
        none = _cert(db, c, files, scheme="ZZT5", pdf=_pdf("OTHER 2"))
        edited = _cert(db, c, files, scheme="ZZT6", covers=[(c["hose"], "FH 4321", "manual")], pdf=_pdf("FH 4321"))
        with _api(db, c) as client:
            assert client.post(_u(c), json={"certificate_id": none.id}).status_code == 201
            put = client.put(_u(c, f"/{edited.id}/boxes"), json={"scope": "quote", "boxes": [_box(), _box(y=0.5)]})
            assert put.status_code == 200, put.text
            by = {i["certificate_id"]: i["marked"] for i in _items(client, c)}
            assert by[found.id] == {"count": 1, "state": "found"}
            assert by[no_file.id]["state"] == "no_file"
            assert by[no_text.id]["state"] == "no_text" and by[no_text.id]["count"] == 0
            assert by[not_found.id] == {"count": 0, "state": "not_found"}
            assert by[none.id]["state"] == "none"
            assert by[edited.id] == {"count": 2, "state": "edited"}


def test_05_patching_the_coverage_code_confirms_or_types_it_and_resets_the_cache(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "ai")], pdf=_pdf("WB 1515", "WB 1516"))
        cp = cr.cps[c["a"].id]
        cp.boxes = {"revision_id": cr.rev.id, "code": "WB 1515", "source": "auto", "has_text": True, "boxes": []}
        db.flush()
        url = f"/api/v1/master-data/certificates/{cr.id}/products/{cp.id}"
        with _api(db, c, EDIT_SLUGS) as client:
            denied = client.patch(url, json={"confirm": True})
            assert denied.status_code == 403, denied.text
        with _api(db, c, DEFAULTS) as client:
            ok = client.patch(url, json={"confirm": True})
            assert ok.status_code == 200, ok.text
            db.expire_all()
            assert cp.model_code == "WB 1515" and cp.model_code_source == "manual"
            typed = client.patch(url, json={"model_code": "  WB 1516  "})
            assert typed.status_code == 200, typed.text
            db.expire_all()
            assert cp.model_code == "WB 1516" and cp.model_code_source == "manual"
            assert cp.boxes is None, "CERT-7: a changed code resets the cache"
            cleared = client.patch(url, json={"model_code": ""})
            assert cleared.status_code == 200, cleared.text
            db.expire_all()
            assert cp.model_code is None
            assert client.patch(url, json={"model_code": "x" * 61}).status_code == 422
            detail = client.get(f"/api/v1/master-data/certificates/{cr.id}")
            assert detail.status_code == 200, detail.text
            body = detail.json()
            coverage = body.get("covered_products") or body.get("products")
            assert coverage and all("model_code" in row for row in coverage)


# ------------------------------------------------------------------ 6 PUT / DELETE boxes


def test_06_quote_scope_by_a_quote_editor_and_delete_drops_the_override(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c) as client:
            put = client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "quote", "boxes": [_box(), _box(y=0.6)]})
            assert put.status_code == 200, put.text
            body = put.json()
            assert body["box_source"] == "quote" and len(body["boxes"]) == 2
            assert body["marked"]["state"] == "edited"
            gone = client.delete(_u(c, f"/{cr.id}/boxes"), params={"scope": "quote"})
            assert gone.status_code == 200, gone.text
            assert gone.json()["box_source"] == "default"


def test_06_default_scope_needs_certificates_edit(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c, EDIT_SLUGS) as client:
            r = client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "default", "boxes": [_box(product_id=c["a"].id)]})
            assert r.status_code == 403, r.text


def test_06_default_write_stores_manual_boxes_per_product_and_drops_the_quote_override(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(
            db,
            c,
            files,
            covers=[(c["a"], "WB 1515", "manual"), (c["b"], "WC 8355", "manual")],
            pdf=_pdf("WB 1515", "WC 8355"),
        )
        with _api(db, c, DEFAULTS) as client:
            assert client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "quote", "boxes": [_box()]}).status_code == 200
            r = client.put(
                _u(c, f"/{cr.id}/boxes"),
                json={"scope": "default", "boxes": [_box(product_id=c["a"].id), _box(y=0.5, product_id=c["a"].id)]},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["box_source"] == "default" and len(body["boxes"]) == 2
            db.expire_all()
            a_cache, b_cache = cr.cps[c["a"].id].boxes, cr.cps[c["b"].id].boxes
            assert a_cache["source"] == "manual" and len(a_cache["boxes"]) == 2
            assert a_cache["revision_id"] == cr.rev.id
            assert b_cache["source"] == "manual" and b_cache["boxes"] == []


def test_06_default_boxes_need_a_covered_and_quoted_product(files):
    with blank_session() as db:
        c = _draft(db)
        elsewhere = _product(db, c["category"].id, c["uom"], description="zzt elsewhere")
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual"), (elsewhere, "EL 1111", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c, DEFAULTS) as client:
            for pid in (None, elsewhere.id, _uid()):
                r = client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "default", "boxes": [_box(product_id=pid)]})
                assert r.status_code == 422, r.text
                assert _code_of(r) == "certificate_box_product_invalid"


@pytest.mark.parametrize(
    "bad",
    [
        {"x": -0.1},
        {"y": 1.2},
        {"w": 0},
        {"h": 0},
        {"x": 0.9, "w": 0.3},
        {"y": 0.95, "h": 0.1},
        {"page": 0},
    ],
)
def test_06_a_box_outside_the_page_is_422(files, bad):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c) as client:
            box = {**_box(), **bad}
            r = client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "quote", "boxes": [box]})
            assert r.status_code == 422, r.text
            assert _code_of(r) == "certificate_box_invalid" or "detail" in r.json() or "message" in r.json()


def test_06_more_than_200_boxes_or_an_unknown_scope_is_422(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c) as client:
            many = [_box(y=0.001 * (i % 90)) for i in range(201)]
            assert client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "quote", "boxes": many}).status_code == 422
            assert client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "nonsense", "boxes": []}).status_code == 422


# ------------------------------------------------------------------ 7 file and permissions


def test_07_file_serves_a_listed_certificate_pdf_inline_and_404s_otherwise(files):
    with blank_session() as db:
        c = _draft(db)
        pdf = _pdf("WB 1515")
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=pdf)
        unlisted = _cert(db, c, files, scheme="ZZT8", pdf=_pdf("X 1"))
        with _api(db, c, VIEW_ONLY) as client:
            r = client.get(_u(c, f"/{cr.id}/file"))
            assert r.status_code == 200, r.text
            assert r.headers["content-type"].startswith("application/pdf")
            assert r.headers["content-disposition"].lower().startswith("inline")
            assert r.content == pdf
            assert client.get(_u(c, f"/{unlisted.id}/file")).status_code == 404
            assert client.get(_u(c, f"/{unlisted.id}")).status_code == 404
            assert client.get(_u(c, f"/{_uid()}/file")).status_code == 404


def test_07_reads_need_read_and_writes_need_edit(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c, []) as client:
            for url in (_u(c), _u(c, f"/{cr.id}"), _u(c, f"/{cr.id}/file")):
                assert client.get(url).status_code == 403, url
        with _api(db, c, VIEW_ONLY) as client:
            assert client.get(_u(c)).status_code == 200
            assert client.post(_u(c), json={"certificate_id": cr.id}).status_code == 403
            assert client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "quote", "boxes": []}).status_code == 403
            assert client.delete(_u(c, f"/{cr.id}/boxes"), params={"scope": "quote"}).status_code == 403
            assert client.patch(_u(c, f"/{cr.id}"), json={"send_to_customer": True}).status_code == 403


def test_07_unknown_project_or_document_is_404(files):
    with blank_session() as db:
        c = _draft(db)
        with _api(db, c) as client:
            url = f"/api/v1/project-sales/projects/{c['project'].id}/quotation-documents/{_uid()}/certificates"
            assert client.get(url).status_code == 404
            url = f"/api/v1/project-sales/projects/{_uid()}/quotation-documents/{c['document'].id}/certificates"
            assert client.get(url).status_code == 404


def test_07_patch_send_to_customer_overrides_the_default_rule_and_null_restores_it(files):
    with blank_session() as db:
        c = _draft(db)
        expired = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"), valid_until=PAST)
        with _api(db, c) as client:
            assert _items(client, c)[0]["send_to_customer"] is False
            r = client.patch(_u(c, f"/{expired.id}"), json={"send_to_customer": True})
            assert r.status_code == 200, r.text
            assert r.json()["send_to_customer"] is True
            r = client.patch(_u(c, f"/{expired.id}"), json={"send_to_customer": None})
            assert r.json()["send_to_customer"] is False


# ------------------------------------------------------------------ 8 issue freezes the list


def test_08_issue_freezes_the_sendable_list_and_later_edits_do_not_change_it(files):
    from app.models.base import company_scope

    with blank_session() as db:
        c = _draft(db)
        sendable = _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        expired = _cert(db, c, files, scheme="ZZT2", covers=[(c["b"], "WC 8355", "manual")], pdf=_pdf("WC 8355"), valid_until=PAST)
        forced = _cert(db, c, files, scheme="ZZT3", covers=[(c["ped"], "PED 1234", "manual")], pdf=_pdf("PED 1234"), valid_until=PAST)
        with _api(db, c) as client:
            assert client.patch(_u(c, f"/{forced.id}"), json={"send_to_customer": True}).status_code == 200
            db.commit()
            issue = _issue(db, c["document"], c["owner"])
            db.flush()
            db.refresh(issue)
            frozen = issue.certificates
            assert [f["certificate_id"] for f in frozen] == [sendable.id, forced.id]
            first = frozen[0]
            assert set(first) >= {"certificate_id", "revision_id", "attachment_id", "scheme", "certificate_number", "boxes"}
            assert first["revision_id"] == sendable.rev.id and first["attachment_id"] == sendable.att.id
            assert len(first["boxes"]) == 1
            before = json.dumps(issue.certificates, sort_keys=True)
            # edits after the issue
            assert client.put(_u(c, f"/{sendable.id}/boxes"), json={"scope": "quote", "boxes": [_box(), _box(y=0.7)]}).status_code == 200
            _new_revision(db, sendable, files, _pdf("ZZ 1"))
            _remove(client, db, c, sendable.id)
            db.refresh(issue)
            assert json.dumps(issue.certificates, sort_keys=True) == before


# ------------------------------------------------------------------ 9 export


class _Fake:
    def __init__(self):
        self.uploads = []

    def upload_file(self, file_content, file_path, content_type=None, **_):
        self.uploads.append((file_path, file_content, content_type))
        return file_path, f"https://cdn.zzt.test/{file_path}"


@pytest.fixture
def queued(monkeypatch):
    calls = []

    def enqueue(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return type("_Job", (), {"id": "zzt-job"})()

    monkeypatch.setattr("app.services.queue_service.enqueue_job", enqueue)
    return calls


def _run_task(db, queued_call):
    from unittest.mock import patch

    from app.tasks import export_tasks

    backend = _Fake()
    func, args, kwargs = queued_call
    assert func.__name__ == "generate_quotation_certificates_pdf"
    with patch.object(export_tasks, "SessionLocal", lambda: db), patch.object(
        export_tasks, "get_backend", lambda _p: backend
    ), patch.object(export_tasks, "default_provider", lambda: "s3"), patch.object(db, "close", lambda: None):
        result = func(*args, **kwargs)
    return result, backend


def _pages(pdf_bytes):
    import pymupdf

    return len(pymupdf.open(stream=pdf_bytes, filetype="pdf"))


def test_09_export_queues_a_download_and_renders_the_live_list_with_boxes_burned_in(files, queued):
    import pymupdf

    from app.models.download import UserDownload

    with blank_session() as db:
        c = _draft(db)
        pdf1, pdf2 = _pdf("WB 1515"), _pdf("WC 8355")
        _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], "WB 1515", "manual")], pdf=pdf1)
        _cert(db, c, files, scheme="ZZT2", covers=[(c["b"], "WC 8355", "manual")], pdf=pdf2)
        with _api(db, c) as client:
            r = client.post(_u(c, "/export"), json={"issue_id": None})
            assert r.status_code == 202, r.text
            download_id = r.json()["download_id"]
            assert len(queued) == 1
            result, backend = _run_task(db, queued[0])
            assert result["status"] == "ready", result
            (key, content, ctype) = backend.uploads[0]
            assert ctype == "application/pdf" and content[:5] == b"%PDF-"
            assert _pages(content) == 2
            base = sum(len(p.get_drawings()) for p in pymupdf.open(stream=pdf1, filetype="pdf"))
            base += sum(len(p.get_drawings()) for p in pymupdf.open(stream=pdf2, filetype="pdf"))
            burned = sum(len(p.get_drawings()) for p in pymupdf.open(stream=content, filetype="pdf"))
            assert burned == base + 2, "one burned box per certificate"
            row = db.query(UserDownload).filter(UserDownload.id == download_id).one()
            assert row.filename == f"{c['document'].document_no} Certificates.pdf"
            assert sorted(files.values(), key=len) == sorted([pdf1, pdf2], key=len), "stored files untouched"


def test_09_export_of_an_issue_uses_its_snapshot_and_names_the_revision(files, queued):
    from app.models.download import UserDownload

    with blank_session() as db:
        c = _draft(db)
        first = _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c) as client:
            db.commit()
            issue = _issue(db, c["document"], c["owner"])
            db.commit()
            late = _cert(db, c, files, scheme="ZZT2", covers=[(c["b"], "WC 8355", "manual")], pdf=_pdf("WC 8355"))
            db.commit()
            live = client.post(_u(c, "/export"), json={"issue_id": None})
            assert live.status_code == 202, live.text
            snap = client.post(_u(c, "/export"), json={"issue_id": issue.id})
            assert snap.status_code == 202, snap.text
            live_result, live_backend = _run_task(db, queued[0])
            snap_result, snap_backend = _run_task(db, queued[1])
            assert _pages(live_backend.uploads[0][1]) == 2
            assert _pages(snap_backend.uploads[0][1]) == 1
            name = db.query(UserDownload).filter(UserDownload.id == snap.json()["download_id"]).one().filename
            assert name.startswith(f"{c['document'].document_no} ") and name.endswith(" Certificates.pdf")
            assert name != f"{c['document'].document_no} Certificates.pdf"


def test_09_a_file_carried_by_two_certificates_is_exported_once(files, queued):
    with blank_session() as db:
        c = _draft(db)
        pdf = _pdf("WB 1515", "WC 8355")
        _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], "WB 1515", "manual")], pdf=pdf, file_hash="zzt-same")
        _cert(db, c, files, scheme="ZZT2", covers=[(c["b"], "WC 8355", "manual")], pdf=pdf, file_hash="zzt-same")
        with _api(db, c) as client:
            assert client.post(_u(c, "/export"), json={"issue_id": None}).status_code == 202
            result, backend = _run_task(db, queued[0])
            assert result["status"] == "ready", result
            assert _pages(backend.uploads[0][1]) == 1


def test_09_an_unreadable_file_is_skipped_and_named_in_the_job_result(files, queued):
    with blank_session() as db:
        c = _draft(db)
        good = _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        bad = _cert(db, c, files, scheme="ZZT2", covers=[(c["b"], "WC 8355", "manual")], pdf=_pdf("WC 8355"))
        del files[str(bad.att.id)]
        with _api(db, c) as client:
            assert client.post(_u(c, "/export"), json={"issue_id": None}).status_code == 202
            result, backend = _run_task(db, queued[0])
            assert result["status"] == "ready", result
            assert _pages(backend.uploads[0][1]) == 1
            assert bad.cert.certificate_number in json.dumps(result)
            assert good.cert.certificate_number not in json.dumps(result)


def test_09_export_with_nothing_to_export_is_422(files, queued):
    with blank_session() as db:
        c = _draft(db)
        with _api(db, c) as client:
            r = client.post(_u(c, "/export"), json={"issue_id": None})
            assert r.status_code == 422, r.text
            assert _code_of(r) == "quotation_certificates_empty"
            assert queued == []


# ------------------------------------------------------------------ 10 verified listing (CERT-16)


def _unverified(db, c, files, **kw):
    """A towel-rail style product linked by AI to a text certificate that never prints its code."""
    kw.setdefault("covers", [(c["a"], None, None)])
    kw.setdefault("pdf", _pdf("ZZ 9", "QQ 12"))
    return _cert(db, c, files, link_source="ai", **kw)


def test_16_an_ai_link_whose_code_is_not_on_the_certificate_is_listed_unverified_and_last(files):
    with blank_session() as db:
        c = _draft(db)
        grey = _unverified(db, c, files, scheme="ZZT0")
        ok = _cert(db, c, files, scheme="ZZT1", covers=[(c["b"], "WC 8355", "manual")], pdf=_pdf("WC 8355"), link_source="ai")
        with _api(db, c) as client:
            items = _items(client, c)
            assert _ids(items) == [ok.id, grey.id]
            assert items[0]["verified"] is True and items[0]["marked"]["state"] == "found"
            assert items[1]["verified"] is False
            assert items[1]["marked"] == {"count": 0, "state": "not_on_certificate"}
            assert items[1]["send_to_customer"] is False
            assert _detail(client, c, grey.id)["verified"] is False


def test_16_unverified_rows_stay_out_of_the_snapshot_and_the_export(files, queued):
    with blank_session() as db:
        c = _draft(db)
        _unverified(db, c, files, scheme="ZZT0")
        _cert(db, c, files, scheme="ZZT1", covers=[(c["b"], "WC 8355", "manual")], pdf=_pdf("WC 8355"), link_source="ai")
        with _api(db, c) as client:
            assert client.post(_u(c, "/export"), json={"issue_id": None}).status_code == 202
            result, backend = _run_task(db, queued[0])
            assert _pages(backend.uploads[0][1]) == 1
            db.commit()
            issue = _issue(db, c["document"], c["owner"])
            db.flush()
            db.refresh(issue)
            assert len(issue.certificates) == 1


def test_16_only_unverified_rows_means_nothing_to_export(files, queued):
    with blank_session() as db:
        c = _draft(db)
        _unverified(db, c, files)
        with _api(db, c) as client:
            r = client.post(_u(c, "/export"), json={"issue_id": None})
            assert r.status_code == 422 and _code_of(r) == "quotation_certificates_empty"


def test_16_ticking_include_sends_an_unverified_row(files):
    with blank_session() as db:
        c = _draft(db)
        grey = _unverified(db, c, files)
        with _api(db, c) as client:
            r = client.patch(_u(c, f"/{grey.id}"), json={"send_to_customer": True})
            assert r.status_code == 200 and r.json()["send_to_customer"] is True
            assert r.json()["verified"] is False
            db.commit()
            issue = _issue(db, c["document"], c["owner"])
            db.flush()
            db.refresh(issue)
            assert [f["certificate_id"] for f in issue.certificates] == [grey.id]


def test_16_drawing_a_box_makes_the_row_verified(files):
    with blank_session() as db:
        c = _draft(db)
        grey = _unverified(db, c, files)
        with _api(db, c) as client:
            assert client.put(_u(c, f"/{grey.id}/boxes"), json={"scope": "quote", "boxes": [_box()]}).status_code == 200
            row = _items(client, c)[0]
            assert row["verified"] is True and row["marked"] == {"count": 1, "state": "edited"}
            assert row["send_to_customer"] is True


def test_16_scans_manual_links_and_hand_added_rows_are_always_verified(files):
    with blank_session() as db:
        c = _draft(db)
        scan = _unverified(db, c, files, scheme="ZZT1", pdf=image_only_pdf())
        manual_link = _cert(db, c, files, scheme="ZZT2", covers=[(c["b"], "NOPE 1", "manual")], pdf=_pdf("OTHER 1"))
        added = _cert(db, c, files, scheme="ZZT3", pdf=_pdf("OTHER 2"))
        with _api(db, c) as client:
            assert client.post(_u(c), json={"certificate_id": added.id}).status_code == 201
            by = {i["certificate_id"]: i for i in _items(client, c)}
            assert by[scan.id]["verified"] is True and by[scan.id]["marked"]["state"] == "no_text"
            assert by[manual_link.id]["verified"] is True and by[manual_link.id]["marked"]["state"] == "not_found"
            assert by[added.id]["verified"] is True


# ------------------------------------------------------------------ 11 fix round 1


@pytest.fixture
def reads(monkeypatch, files):
    """Counts storage reads per attachment id on top of the `files` seam."""
    from app.services.resources_service import AttachmentService

    inner = AttachmentService.get_file_content_for
    seen: list[str] = []

    def counted(self, attachment):
        seen.append(str(attachment.id))
        return inner(self, attachment)

    monkeypatch.setattr(AttachmentService, "get_file_content_for", counted)
    return seen


def test_b1_a_hand_added_certificate_on_a_draft_without_lines_lists(files):
    from app.models.projects import ProjectQuotationLine

    with blank_session() as db:
        c = _draft(db)
        db.query(ProjectQuotationLine).delete()
        db.commit()
        cr = _cert(db, c, files, pdf=_pdf("NOTHING 1"))
        with _api(db, c) as client:
            assert _items(client, c) == []
            assert client.post(_u(c), json={"certificate_id": cr.id}).status_code == 201
            assert _ids(_items(client, c)) == [cr.id]


def test_m1_a_scan_and_a_text_file_with_no_suggestion_are_read_once(files, reads):
    with blank_session() as db:
        c = _draft(db)
        scan = _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], None, None)], pdf=image_only_pdf(), link_source="ai")
        blank = _cert(db, c, files, scheme="ZZT2", covers=[(c["b"], None, None)], pdf=_pdf("ZZ 9", "QQ 12"), link_source="ai")
        with _api(db, c) as client:
            first = _items(client, c)
            assert {str(scan.att.id), str(blank.att.id)} <= set(reads)
            reads.clear()
            second = _items(client, c)
            assert reads == [], "the negative result is cached for the revision"
            assert [(i["certificate_id"], i["marked"]["state"]) for i in first] == [
                (i["certificate_id"], i["marked"]["state"]) for i in second
            ]
            by = {i["certificate_id"]: i for i in second}
            assert by[scan.id]["marked"]["state"] == "no_text" and by[scan.id]["verified"] is True
            assert by[blank.id]["verified"] is False


def test_m1_the_detail_reuses_the_cached_page_count_and_text_flag(files, reads):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c) as client:
            _items(client, c)
            reads.clear()
            d = _detail(client, c, cr.id)
            assert d["page_count"] == 1 and d["has_text"] is True
            assert reads == []


def test_m3_a_reader_can_queue_the_certificates_pdf(files, queued):
    with blank_session() as db:
        c = _draft(db)
        _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c, VIEW_ONLY) as client:
            r = client.post(_u(c, "/export"), json={"issue_id": None})
            assert r.status_code == 202, r.text
            assert len(queued) == 1


def test_m2_the_heavy_routes_are_marked():
    from app.api.v1.projects import quotation_certificates as routes

    # The list is not heavy any more (CERT-TAB-UX, tests/test_quotation_certificates_perf.py).
    for name in ("read_certificate", "read_certificate_file", "put_certificate_boxes"):
        assert getattr(getattr(routes, name), "heavy", False) is True, name


def test_m2_unreadable_file_is_treated_like_no_file(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], None, None)], pdf=_pdf("WB 1515"), link_source="ai")
        del files[str(cr.att.id)]
        with _api(db, c) as client:
            row = _items(client, c)[0]
            assert row["verified"] is True and row["marked"]["state"] == "no_file"


def test_m5_clearing_the_send_flag_with_no_marker_creates_no_row(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c) as client:
            r = client.patch(_u(c, f"/{cr.id}"), json={"send_to_customer": None})
            assert r.status_code == 200, r.text
            assert _markers(db, c) == []


def test_m6_the_issue_counts_only_certificates_with_a_file(files):
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        c = _draft(db)
        _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        nofile = _cert(db, c, files, scheme="ZZT2", covers=[(c["b"], "WC 8355", "manual")], pdf=None)
        with _api(db, c) as client:
            assert client.patch(_u(c, f"/{nofile.id}"), json={"send_to_customer": True}).status_code == 200
            db.commit()
            issue = _issue(db, c["document"], c["owner"])
            db.flush()
            db.refresh(issue)
            assert len(issue.certificates) == 2
            assert qdocs.serialize_issue(db, issue)["certificates_count"] == 1


@pytest.mark.parametrize("bad", [{"x": float("nan")}, {"w": float("inf")}, {"h": float("-inf")}, {"product_id": "x" * 40}, {"product_id": "not-a-uuid"}, {"page": 2001}])
def test_l1_l2_non_finite_numbers_and_bad_ids_are_refused(bad):
    from app.services import quotation_certificate_service as certs
    from app.services.error_handler import AppException

    with pytest.raises(AppException) as exc:
        certs.validate_boxes([{**_box(), **bad}])
    assert exc.value.status_code == 422 and exc.value.code == "certificate_box_invalid"


def test_l1_infinity_on_the_wire_is_422(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c) as client:
            body = '{"scope":"quote","boxes":[{"page":1,"x":NaN,"y":0.1,"w":0.2,"h":0.1,"product_id":null}]}'
            r = client.put(_u(c, f"/{cr.id}/boxes"), content=body, headers={"Content-Type": "application/json"})
            assert r.status_code == 422, r.text


def test_l2_a_box_page_beyond_the_file_is_422(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c) as client:
            r = client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "quote", "boxes": [_box(page=2)]})
            assert r.status_code == 422, r.text
            assert _code_of(r) == "certificate_box_invalid"
            assert client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "quote", "boxes": [_box(page=1)]}).status_code == 200


def test_l3_two_removes_on_one_quote_both_commit(files):
    with blank_session() as db:
        c = _draft(db)
        one = _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        two = _cert(db, c, files, scheme="ZZT2", covers=[(c["b"], "WC 8355", "manual")], pdf=_pdf("WC 8355"))
        keep = _cert(db, c, files, scheme="ZZT3", covers=[(c["ped"], "PED 1234", "manual")], pdf=_pdf("PED 1234"))
        with _api(db, c) as client:
            first = _park_remove(client, c, one.id)
            second = _park_remove(client, c, two.id)
            assert first.status_code == 202 and second.status_code == 202, (first.text, second.text)
            assert first.json()["id"] != second.json()["id"]
            for cert, parked in ((one, first), (two, second)):
                _lapse(db, parked.json()["id"])
                client.get(
                    f"{PENDING}/current",
                    params={"entity_type": "quotation_certificate", "entity_id": _remove_key(c, cert.id)},
                )
            db.expire_all()
            assert _ids(_items(client, c)) == [keep.id]


def test_l4_adding_a_certificate_needs_the_register_view_right(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, pdf=_pdf("NOTHING 1"))
        with _api(db, c, EDIT_NO_CERT_VIEW) as client:
            r = client.post(_u(c), json={"certificate_id": cr.id})
            assert r.status_code == 403, r.text
        with _api(db, c, EDIT_SLUGS) as client:
            assert client.post(_u(c), json={"certificate_id": cr.id}).status_code == 201


# ------------------------------------------------------------------ 12 fix round 3


def test_r3_a_new_revision_discards_the_negative_cache(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], None, None)], pdf=_pdf("ZZ 9"), link_source="ai")
        cp = cr.cps[c["a"].id]
        with _api(db, c) as client:
            assert _items(client, c)[0]["marked"]["state"] == "not_on_certificate"
            db.expire_all()
            assert cp.boxes["code"] is None and cp.boxes["revision_id"] == cr.rev.id
            _new_revision(db, cr, files, _pdf("XX 1", "WB 1515"))
            db.commit()
            row = _items(client, c)[0]
            assert row["marked"] == {"count": 1, "state": "found"}
            db.expire_all()
            assert cp.model_code == "WB 1515" and cp.model_code_source == "ai"


def test_r3_a_manual_default_drawn_on_an_old_revision_is_ignored_after_a_new_one(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c, DEFAULTS) as client:
            put = client.put(
                _u(c, f"/{cr.id}/boxes"),
                json={"scope": "default", "boxes": [_box(y=0.9, h=0.05, product_id=c["a"].id)]},
            )
            assert put.status_code == 200, put.text
            assert _items(client, c)[0]["marked"]["state"] == "edited"
            _new_revision(db, cr, files, _pdf("AA 1", "WB 1515"))
            db.commit()
            row = _items(client, c)[0]
            assert row["marked"] == {"count": 1, "state": "found"}
            d = _detail(client, c, cr.id)
            assert d["box_source"] == "default" and d["boxes"][0]["y"] != pytest.approx(0.9)


def test_r4_can_add_needs_the_edit_right_and_the_register_view_right(files):
    with blank_session() as db:
        c = _draft(db)
        with _api(db, c, EDIT_SLUGS) as client:
            body = client.get(_u(c)).json()
            assert body["can_edit"] is True and body["can_add"] is True
        with _api(db, c, EDIT_NO_CERT_VIEW) as client:
            body = client.get(_u(c)).json()
            assert body["can_edit"] is True and body["can_add"] is False
        with _api(db, c, VIEW_ONLY) as client:
            assert client.get(_u(c)).json()["can_add"] is False


# ------------------------------------------------------------------ 13 fix round 4


def _row_with_both_codes_pdf():
    # Row 1 prints WB 1515 in the model column and WC 8355 in the description: one ruled row.
    return table_pdf([[("WB 1515", ["WC 8355"], 30), ("OTHER 1", ["x"], 30)]])


def test_r4_two_products_on_one_row_are_one_box_and_one_row_counted(files, queued):
    import pymupdf

    with blank_session() as db:
        c = _draft(db)
        pdf = _row_with_both_codes_pdf()
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual"), (c["b"], "WC 8355", "manual")], pdf=pdf)
        with _api(db, c) as client:
            row = _items(client, c)[0]
            assert row["marked"] == {"count": 1, "state": "found"}
            d = _detail(client, c, cr.id)
            assert len(d["boxes"]) == 1 and d["boxes"][0]["product_id"] is None
            assert client.post(_u(c, "/export"), json={"issue_id": None}).status_code == 202
            _result, backend = _run_task(db, queued[0])
            base = sum(len(p.get_drawings()) for p in pymupdf.open(stream=pdf, filetype="pdf"))
            burned = sum(len(p.get_drawings()) for p in pymupdf.open(stream=backend.uploads[0][1], filetype="pdf"))
            assert burned == base + 1


def test_r4_a_legacy_issue_without_a_snapshot_exports_the_live_list(files, queued):
    from app.models.projects import ProjectQuotationIssue
    from app.models.download import UserDownload

    with blank_session() as db:
        c = _draft(db)
        _cert(db, c, files, scheme="ZZT1", covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        _cert(db, c, files, scheme="ZZT2", covers=[(c["b"], "WC 8355", "manual")], pdf=_pdf("WC 8355"))
        with _api(db, c) as client:
            db.commit()
            issue = _issue(db, c["document"], c["owner"])
            db.query(ProjectQuotationIssue).filter(ProjectQuotationIssue.id == issue.id).update(
                {"certificates": None}, synchronize_session=False
            )
            db.commit()
            r = client.post(_u(c, "/export"), json={"issue_id": issue.id})
            assert r.status_code == 202, r.text
            result, backend = _run_task(db, queued[0])
            assert result["status"] == "ready" and _pages(backend.uploads[0][1]) == 2
            name = db.query(UserDownload).filter(UserDownload.id == r.json()["download_id"]).one().filename
            assert name.endswith(" Certificates.pdf") and name != f"{c['document'].document_no} Certificates.pdf"


def test_r4_an_issue_frozen_with_nothing_is_422_and_stores_an_empty_list(files, queued):
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        c = _draft(db)
        with _api(db, c) as client:
            db.commit()
            issue = _issue(db, c["document"], c["owner"])
            db.flush()
            db.refresh(issue)
            assert issue.certificates == []
            assert qdocs.serialize_issue(db, issue)["certificates_count"] == 0
            r = client.post(_u(c, "/export"), json={"issue_id": issue.id})
            assert r.status_code == 422 and _code_of(r) == "quotation_certificates_empty"


def test_r4_certificates_count_is_null_for_a_legacy_issue(files):
    from app.models.projects import ProjectQuotationIssue
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        c = _draft(db)
        issue = _issue(db, c["document"], c["owner"])
        db.query(ProjectQuotationIssue).filter(ProjectQuotationIssue.id == issue.id).update(
            {"certificates": None}, synchronize_session=False
        )
        db.commit()
        db.refresh(issue)
        assert qdocs.serialize_issue(db, issue)["certificates_count"] is None


def test_r5_a_merged_box_names_its_products_and_a_default_save_gives_each_its_own(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(
            db,
            c,
            files,
            covers=[(c["a"], "WB 1515", "manual"), (c["b"], "WC 8355", "manual")],
            pdf=_row_with_both_codes_pdf(),
        )
        with _api(db, c, DEFAULTS) as client:
            (merged,) = _detail(client, c, cr.id)["boxes"]
            assert merged["product_id"] is None
            assert set(merged["product_ids"]) == {c["a"].id, c["b"].id}
            # What the editor sends: the merged box expanded to one box per product.
            box = {k: merged[k] for k in ("page", "x", "y", "w", "h")}
            payload = [{**box, "product_id": pid} for pid in merged["product_ids"]]
            r = client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "default", "boxes": payload})
            assert r.status_code == 200, r.text
            db.expire_all()
            for pid in (c["a"].id, c["b"].id):
                cache = cr.cps[pid].boxes
                assert cache["source"] == "manual" and len(cache["boxes"]) == 1
            assert _items(client, c)[0]["marked"] == {"count": 1, "state": "edited"}
            # product_ids is accepted and ignored on a quote-scope save.
            q = client.put(
                _u(c, f"/{cr.id}/boxes"),
                json={"scope": "quote", "boxes": [{**merged, "product_id": None}]},
            )
            assert q.status_code == 200, q.text


# ---------------------------------------------------------------- CERT-TAB-UX crew pass, 11 Nov


def test_ux_a_remembered_miss_does_not_hide_a_file_that_is_back(files, monkeypatch):
    """The box editor reads the file itself: when it is readable again the miss is forgotten."""
    pdf = _pdf("WB 1515")
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=pdf)
        files.pop(str(cr.att.id))
        with _api(db, c) as client:
            assert _items(client, c)[0]["marked"]["state"] == "no_file"
            files[str(cr.att.id)] = pdf
            d = _detail(client, c, cr.id)
            assert d["marked"]["state"] == "found" and len(d["boxes"]) == 1
            assert _items(client, c)[0]["marked"] == {"count": 1, "state": "found"}


def test_ux_a_product_whose_box_was_deleted_for_this_quote_is_not_marked(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(
            db,
            c,
            files,
            covers=[(c["a"], "WB 1515", "manual"), (c["b"], "WC 8355", "manual")],
            pdf=_pdf("WB 1515", "WC 8355"),
        )
        with _api(db, c) as client:
            d = _detail(client, c, cr.id)
            assert {p["state"] for p in d["products"]} == {"found"}
            keep = [b for b in d["boxes"] if b["product_id"] == c["b"].id]
            assert len(keep) == 1
            r = client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "quote", "boxes": keep})
            assert r.status_code == 200, r.text
            by = {p["product_id"]: p["state"] for p in r.json()["products"]}
            assert by[c["a"].id] == "unmarked"
            assert by[c["b"].id] == "found"
            assert _items(client, c)[0]["marked"] == {"count": 1, "state": "edited"}


def test_ux_a_merged_quote_box_keeps_both_products_marked(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(
            db,
            c,
            files,
            covers=[(c["a"], "WB 1515", "manual"), (c["b"], "WC 8355", "manual")],
            pdf=_row_with_both_codes_pdf(),
        )
        with _api(db, c) as client:
            (merged,) = _detail(client, c, cr.id)["boxes"]
            r = client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "quote", "boxes": [merged]})
            assert r.status_code == 200, r.text
            assert {p["state"] for p in r.json()["products"]} == {"found"}
            assert set(r.json()["boxes"][0]["product_ids"]) == {c["a"].id, c["b"].id}


def test_ux_an_unattributed_quote_box_leaves_product_states_alone(files):
    """A box drawn for this quote names no product, so it may be any product's: none is unmarked."""
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c) as client:
            r = client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "quote", "boxes": [_box()]})
            assert r.status_code == 200, r.text
            assert r.json()["products"][0]["state"] == "found"


def test_ux_deleting_every_box_for_this_quote_unmarks_the_product(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c) as client:
            r = client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "quote", "boxes": []})
            assert r.status_code == 200, r.text
            assert r.json()["products"][0]["state"] == "unmarked"
            assert _items(client, c)[0]["marked"] == {"count": 0, "state": "edited"}


def test_ux_a_remembered_miss_never_freezes_a_snapshot_without_its_boxes(files):
    """Reviewer round 2: issuing reads the file itself; a miss the list remembered is not trusted."""
    from app.models.projects import ProjectQuotationDocument
    from app.services import quotation_certificate_service as svc

    pdf = _pdf("WB 1515")
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=pdf)
        files.pop(str(cr.att.id))
        with _api(db, c) as client:
            assert _items(client, c)[0]["marked"]["state"] == "no_file"
        files[str(cr.att.id)] = pdf
        db.expire_all()
        document = db.get(ProjectQuotationDocument, c["document"].id)
        (entry,) = svc.snapshot(db, document)
        assert entry["attachment_id"] and len(entry["boxes"]) == 1


def test_ux_a_trusted_miss_makes_the_whole_certificate_no_file_without_reading(files, reads):
    """Reviewer round 2: one product's remembered miss and another's cleared cache must agree."""
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(
            db,
            c,
            files,
            covers=[(c["a"], "WB 1515", "manual"), (c["b"], "WC 8355", "manual")],
            pdf=_pdf("WB 1515", "WC 8355"),
        )
        pdf = files.pop(str(cr.att.id))
        with _api(db, c) as client:
            assert _items(client, c)[0]["marked"]["state"] == "no_file"
            files[str(cr.att.id)] = pdf
            cr.cps[c["b"].id].boxes = None  # a code edit or an ingest clears one product's cache
            db.commit()
            reads.clear()
            row = _items(client, c)[0]
            assert row["marked"] == {"count": 0, "state": "no_file"}
            assert reads == []


def test_ux_a_default_with_no_box_for_one_product_unmarks_only_that_product(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(
            db,
            c,
            files,
            covers=[(c["a"], "WB 1515", "manual"), (c["b"], "WC 8355", "manual")],
            pdf=_pdf("WB 1515", "WC 8355"),
        )
        with _api(db, c, DEFAULTS) as client:
            d = _detail(client, c, cr.id)
            keep = [b for b in d["boxes"] if b["product_id"] == c["b"].id]
            r = client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "default", "boxes": keep})
            assert r.status_code == 200, r.text
            by = {p["product_id"]: p["state"] for p in r.json()["products"]}
            assert by == {c["a"].id: "unmarked", c["b"].id: "edited"}


def test_ux_a_bad_product_ids_entry_is_422(files):
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(db, c, files, covers=[(c["a"], "WB 1515", "manual")], pdf=_pdf("WB 1515"))
        with _api(db, c) as client:
            for entry in ("x" * 40, "abc"):
                bad = {**_box(), "product_ids": [entry]}
                r = client.put(_u(c, f"/{cr.id}/boxes"), json={"scope": "quote", "boxes": [bad]})
                assert r.status_code == 422, (entry, r.text)


def test_ux_a_remembered_miss_never_overrides_a_file_read_in_the_same_request(files, reads):
    """Fresh review: product a's stale cache reads the file fine; b's remembered miss must not then
    turn the row into "No file"."""
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(
            db,
            c,
            files,
            covers=[(c["a"], "WB 1515", "manual"), (c["b"], "WC 8355", "manual")],
            pdf=_pdf("WB 1515", "WC 8355"),
        )
        pdf = files.pop(str(cr.att.id))
        with _api(db, c) as client:
            assert _items(client, c)[0]["marked"]["state"] == "no_file"
            files[str(cr.att.id)] = pdf
            cr.cps[c["a"].id].boxes = None  # a (read first, code order) must read the file again
            db.commit()
            row = _items(client, c)[0]
            assert row["marked"] == {"count": 2, "state": "found"}


def test_ux_a_miss_is_stamped_only_when_storage_was_asked(files, reads):
    """Fresh review: a product skipped because another product's miss was trusted keeps its cache
    untouched; no new miss is stamped without a storage call."""
    with blank_session() as db:
        c = _draft(db)
        cr = _cert(
            db,
            c,
            files,
            covers=[(c["a"], "WB 1515", "manual"), (c["b"], "WC 8355", "manual")],
            pdf=_pdf("WB 1515", "WC 8355"),
        )
        files.pop(str(cr.att.id))
        with _api(db, c) as client:
            _items(client, c)
            cr.cps[c["b"].id].boxes = None
            db.commit()
            reads.clear()
            _items(client, c)
            assert reads == []
            db.expire_all()
            assert cr.cps[c["b"].id].boxes is None
