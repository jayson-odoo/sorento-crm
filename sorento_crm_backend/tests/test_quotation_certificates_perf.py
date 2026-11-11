"""CERT-TAB-UX: the Certification tab list stays fast at the owner's quote size (34 certificates).

Owner, 11 Nov 2026: "the loading of certification quite long". Measured on this seed before the fix
(see PLAN-cert-tab-ux-11nov.md "Findings": 79 statements, 94 ms): the warm list ran one SELECT per certificate for its
current revision, one per revision for its attachment and one per certificate whose product had no
code yet, so the statement count grew with the list. These tests pin a bound that does not.
"""
from __future__ import annotations

import time

from sqlalchemy import event

from ._pg_fixture import blank_session
from .test_project_quotation_pdf import _product
from .test_project_spec_sheet import _line
from .test_quotation_certificates import _api, _cert, _draft, _items, _pdf, files, reads  # noqa: F401

SIZE = 34


def _seed(db, c, files_store):
    """SIZE products on the quote, one certificate each: a third with a typed code, a third whose
    code is suggested from the file, a third whose code is not printed (no suggestion)."""
    certs = []
    for i in range(SIZE):
        product = _product(db, c["category"].id, c["uom"], description=f"zzt p{i}", code=f"ZZTP{i:03d}WX{8000 + i}")
        _line(db, c, c["scope"], {"product_id": product.id})
        kind = i % 3
        code = f"WX {8000 + i}"
        if kind == 0:
            covers, pdf = [(product, code, "manual")], _pdf("AA 1", code, "BB 2")
        elif kind == 1:
            covers, pdf = [(product, None, None)], _pdf("AA 1", f"WX{8000 + i}", "BB 2")
        else:
            covers, pdf = [(product, None, None)], _pdf("AA 1", "BB 2")
        certs.append(_cert(db, c, files_store, scheme=f"ZZT{i % 4}", covers=covers, pdf=pdf, link_source="ai"))
    return certs


class _Counter:
    def __init__(self, engine):
        self.engine = engine
        self.count = 0

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._hit)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute", self._hit)

    def _hit(self, *args, **kwargs):
        self.count += 1


def test_perf_warm_list_reads_no_file_and_a_bounded_number_of_statements(files, reads):
    with blank_session() as db:
        c = _draft(db)
        _seed(db, c, files)
        engine = db.get_bind().engine if hasattr(db.get_bind(), "engine") else db.get_bind()
        with _api(db, c) as client:
            t0 = time.perf_counter()
            cold = _items(client, c)
            cold_s = time.perf_counter() - t0
            assert len(cold) == SIZE
            reads.clear()
            with _Counter(engine) as counter:
                t0 = time.perf_counter()
                warm = _items(client, c)
                warm_s = time.perf_counter() - t0
            print(f"\nCERT-TAB-UX perf: cold {cold_s * 1000:.0f} ms, warm {warm_s * 1000:.0f} ms, "
                  f"warm statements {counter.count}")
            assert len(warm) == SIZE
            assert reads == [], "a warm list reads no certificate file"
            # Auth + permissions + a fixed set of list queries; not one per certificate.
            assert counter.count <= 40, counter.count
            assert warm_s < 1.0, warm_s


def test_perf_the_list_route_is_not_queued_behind_exports():
    """A warm list does no PDF work, so it must not wait its turn behind a PDF export (`@heavy`
    lets one heavy request run per worker at a time)."""
    from app.api.v1.projects import quotation_certificates as routes

    assert getattr(routes.list_certificates, "heavy", False) is False


def test_perf_a_cold_list_holds_one_file_at_a_time(files, monkeypatch):
    """Why the list may drop `@heavy`: a first look reads each file, resolves its row and lets the
    bytes go before the next, so one list never holds every file of the quote at once."""
    from app.services import quotation_certificate_service as svc

    held: list[int] = []
    groups: list = []
    original = svc._row

    def spy(db, group, quoted, markers):
        groups.append(group)
        out = original(db, group, quoted, markers)
        held.append(sum(1 for g in groups if isinstance(g._file, (bytes, bytearray))))
        return out

    monkeypatch.setattr(svc, "_row", spy)
    with blank_session() as db:
        c = _draft(db)
        _seed(db, c, files)
        with _api(db, c) as client:
            assert len(_items(client, c)) == SIZE
    assert held and max(held) == 1, held


# ---------------------------------------------------------------- crew browser pass, 11 Nov
# A certificate whose file is missing from storage was fetched again on every list load (~150 ms
# a file on the dev copy) because the miss was never remembered. The list now remembers it for the
# revision (with a retry after MISS_RETRY), so a warm list never calls storage.

LATENCY = 0.15


def _slow_misses(monkeypatch, store):
    """Every storage read takes LATENCY and the files are gone, like the dev copy."""
    import time as _time

    from app.services.resources_service import AttachmentService

    seen: list[str] = []

    def read(self, attachment):
        seen.append(str(attachment.id))
        _time.sleep(LATENCY)
        raise FileNotFoundError(str(attachment.id))

    monkeypatch.setattr(AttachmentService, "get_file_content_for", read)
    store.clear()
    return seen


def test_perf_a_missing_file_is_remembered_and_the_warm_list_never_calls_storage(files, monkeypatch):
    with blank_session() as db:
        c = _draft(db)
        _seed(db, c, files)
        seen = _slow_misses(monkeypatch, files)
        with _api(db, c) as client:
            t0 = time.perf_counter()
            cold = _items(client, c)
            cold_s = time.perf_counter() - t0
            assert len(cold) == SIZE and len(seen) == SIZE
            assert {i["marked"]["state"] for i in cold} == {"no_file"}
            seen.clear()
            t0 = time.perf_counter()
            warm = _items(client, c)
            warm_s = time.perf_counter() - t0
            print(f"\nCERT-TAB-UX missing files: cold {cold_s * 1000:.0f} ms, warm {warm_s * 1000:.0f} ms")
            assert seen == [], "a remembered miss is not fetched again"
            assert {i["marked"]["state"] for i in warm} == {"no_file"}
            assert warm_s < 1.0, warm_s


def test_perf_a_remembered_miss_is_retried_after_it_expires(files, monkeypatch):
    from datetime import datetime, timedelta

    from app.services import quotation_certificate_service as svc

    with blank_session() as db:
        c = _draft(db)
        _seed(db, c, files)
        seen = _slow_misses(monkeypatch, files)
        with _api(db, c) as client:
            _items(client, c)
            seen.clear()
            later = datetime.utcnow() + svc.MISS_RETRY + timedelta(minutes=1)
            monkeypatch.setattr(svc, "_utcnow", lambda: later)
            _items(client, c)
            assert len(seen) == SIZE
