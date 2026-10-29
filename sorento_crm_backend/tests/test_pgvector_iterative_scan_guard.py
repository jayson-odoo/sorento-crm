"""PGVECTOR-GUARD: `SET LOCAL hnsw.iterative_scan` only on pgvector >= 0.8.

The GUC does not exist before pgvector 0.8; sending it there raises and aborts the
transaction, which broke record search and entity resolution. The guard reads the
extension version once per process and skips the SET (one WARNING) when unsupported.
The database is faked here: what matters is which statements get sent.
"""
from __future__ import annotations

import logging
import pathlib

import pytest

import app.services.embedding_indexes as ei


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeDb:
    def __init__(self, version):
        self.version = version
        self.sent: list[str] = []

    def execute(self, stmt, *a, **kw):
        sql = str(stmt)
        self.sent.append(sql)
        if "pg_extension" in sql:
            return _Result(self.version)
        if "iterative_scan" in sql and not ei._version_supports_iterative_scan(self.version):
            raise AssertionError(f"unrecognized configuration parameter sent to pgvector {self.version}")
        return _Result(None)

    def sets(self) -> list[str]:
        return [s for s in self.sent if "iterative_scan" in s]

    def version_reads(self) -> int:
        return sum("pg_extension" in s for s in self.sent)


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.setattr(ei, "_ITERATIVE_SCAN_SUPPORTED", None, raising=False)


@pytest.mark.parametrize("version", ["0.8.0", "0.8.2", "0.9.1", "0.10.0", "1.0"])
def test_supported_version_issues_the_set(version):
    db = _FakeDb(version)
    ei.set_iterative_scan(db)
    assert db.sets() == ["SET LOCAL hnsw.iterative_scan = relaxed_order"]


@pytest.mark.parametrize("version", ["0.7.4", "0.5.1", "0.7", None, "", "dev"])
def test_unsupported_or_unknown_version_skips_the_set(version):
    db = _FakeDb(version)
    ei.set_iterative_scan(db)
    assert db.sets() == []


def test_version_is_read_once_per_process():
    db = _FakeDb("0.8.2")
    for _ in range(3):
        ei.set_iterative_scan(db)
    assert db.version_reads() == 1
    assert len(db.sets()) == 3

    old = _FakeDb("0.7.4")
    ei._ITERATIVE_SCAN_SUPPORTED = None
    for _ in range(3):
        ei.set_iterative_scan(old)
    assert old.version_reads() == 1
    assert old.sets() == []


def test_unsupported_logs_one_warning_per_process(caplog):
    db = _FakeDb("0.7.4")
    with caplog.at_level(logging.WARNING, logger=ei.logger.name):
        for _ in range(4):
            ei.set_iterative_scan(db)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "0.7.4" in warnings[0].getMessage()


def test_supported_logs_no_warning(caplog):
    with caplog.at_level(logging.WARNING, logger=ei.logger.name):
        ei.set_iterative_scan(_FakeDb("0.8.2"))
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_entity_resolver_routes_through_the_guard(monkeypatch):
    import app.services.entity_resolver as er

    db = _FakeDb("0.7.4")
    er._iterative_scan_for(db, frozenset({"promotion"}))
    assert db.sets() == []

    ei._ITERATIVE_SCAN_SUPPORTED = None
    db = _FakeDb("0.8.2")
    er._iterative_scan_for(db, frozenset({"promotion"}))
    assert db.sets() == ["SET LOCAL hnsw.iterative_scan = relaxed_order"]


def test_no_raw_iterative_scan_set_outside_the_guard():
    """Every caller goes through `embedding_indexes.set_iterative_scan` (both #1967 sites included)."""
    app_dir = pathlib.Path(ei.__file__).resolve().parents[1]
    offenders = [
        str(p.relative_to(app_dir))
        for p in app_dir.rglob("*.py")
        if p.name != "embedding_indexes.py" and "hnsw.iterative_scan" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_real_server_narrowed_record_search_keeps_the_transaction_usable():
    """On the real server, whatever its pgvector version: the non-hot narrowed search returns and the
    transaction survives it. On pgvector < 0.8 this raised `invalid configuration parameter name`."""
    from sqlalchemy import text

    from app.services.embedding_service import EmbeddingReadService
    from tests._pg_fixture import blank_session

    with blank_session() as db:
        hits = EmbeddingReadService(db).search_current([1.0] + [0.0] * 1535, top_k=5, source_type="promotion")
        assert hits == []
        assert db.execute(text("SELECT 1")).scalar() == 1
