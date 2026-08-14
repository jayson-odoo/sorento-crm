"""TEMPORARY evidence transcript for the test phase. Deleted after the run.

Prints a human-readable end-to-end demonstration of the per-company Container
Status behaviour against the real Postgres blank schema. Not a permanent test.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app  # noqa: E402  (must be first app import)

from app.api.v1.system.references import _resolve_with_domain_hint
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.base import set_company_scope
from app.models.company import Company
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.company_scope_resolver import apply_company_scope
from app.services.container_status_document import (
    TYPE_NAME,
    ensure_attachment_type,
    enforce_single_current,
)

from tests._pg_fixture import blank_session, unique_code

SORENTO_ID = DEFAULT_COMPANY_ID
MOCHA_ID = "00000000-0000-0000-0000-000000000002"
ENDPOINT = "/api/v1/procurement/packing-lists/container-status/latest"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


def _workbook(db, *, uploaded_at: datetime, company_id: str | None) -> str:
    type_id = ensure_attachment_type(db)
    att_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO attachments (
                id, attachment_type_id, original_filename, stored_filename,
                file_path, mime_type, uploaded_at, is_deleted, company_id
            ) VALUES (:id, :t, :n, :n, :k, :m, :u, false, :c)
            """
        ),
        {
            "id": att_id,
            "t": type_id,
            "n": "Container Status 2026.xlsx",
            "k": f"import-sources/{unique_code('key')}/Container Status 2026.xlsx",
            "m": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "u": uploaded_at,
            "c": company_id,
        },
    )
    db.flush()
    return att_id


def _state(db) -> list[tuple]:
    return db.execute(
        text(
            """
            SELECT COALESCE(c.name, '<NULL company>'), a.uploaded_at, a.is_deleted, a.id
            FROM attachments a
            JOIN attachment_types t ON t.id = a.attachment_type_id
            LEFT JOIN companies c ON c.id = a.company_id
            WHERE t.type_name = :name
            ORDER BY c.name NULLS FIRST, a.uploaded_at
            """
        ),
        {"name": TYPE_NAME},
    ).all()


def _print_state(db, label):
    print(f"\n  {label}")
    print(f"  {'company':<10} {'uploaded_at':<21} {'state':<8} id")
    for name, up, deleted, att_id in _state(db):
        state = "TRASHED" if deleted else "LIVE"
        print(f"  {name:<10} {str(up):<21} {state:<8} {att_id[:8]}...")


def test_transcript_per_company_single_current_and_resolve():
    with blank_session() as db:
        db.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
        db.flush()

        print("\n" + "=" * 76)
        print("SCENARIO 1: a Mocha upload can no longer trash Sorento's current workbook")
        print("=" * 76)
        sorento_wb = _workbook(db, uploaded_at=datetime(2026, 6, 1, 9, 0, 0), company_id=SORENTO_ID)
        _workbook(db, uploaded_at=datetime(2026, 7, 1, 9, 0, 0), company_id=MOCHA_ID)
        mocha_new = _workbook(db, uploaded_at=datetime(2026, 7, 15, 9, 0, 0), company_id=MOCHA_ID)
        _print_state(db, "Before enforce_single_current (Mocha just uploaded a newer sheet):")
        trashed = enforce_single_current(db)
        print(f"\n  enforce_single_current() trashed {trashed} row(s)")
        _print_state(db, "After (newest survives WITHIN each company):")
        live = {r[3] for r in _state(db) if not r[2]}
        assert live == {sorento_wb, mocha_new}, "Sorento's current must survive a Mocha upload"

        print("\n" + "=" * 76)
        print("SCENARIO 2: tie within one company resolves by id; other company untouched")
        print("=" * 76)
        tie = datetime(2026, 7, 15, 9, 0, 0)
        a = _workbook(db, uploaded_at=tie, company_id=MOCHA_ID)
        b = _workbook(db, uploaded_at=tie, company_id=MOCHA_ID)
        enforce_single_current(db)
        winner = max(a, b, mocha_new)
        _print_state(db, "After a same-timestamp double upload in Mocha:")
        live = {r[3] for r in _state(db) if not r[2]}
        assert sorento_wb in live and len(live) == 2

        print("\n" + "=" * 76)
        print("SCENARIO 3: contact granted BOTH companies resolves 'container status'")
        print("=" * 76)
        db.commit()
        set_company_scope(db, frozenset({SORENTO_ID, MOCHA_ID}))
        result = _resolve_with_domain_hint(db, "container status", [], "")
        res = result["resolutions"][0]
        matches = res["matches"]
        print(f"\n  resolved={res.get('resolved')} ambiguous={res.get('ambiguous')}"
              f" matches={len(matches)}")
        for m in matches:
            print("  match:", json.dumps(
                {k: m.get(k) for k in ("uuid", "company_id", "company_name")}, indent=None))
            print("    display:", json.dumps(m.get("display"), default=str)[:200])
        assert len(matches) == 2
        assert {m["company_name"] for m in matches} == {"Sorento", "Mocha"}
        print("\n  -> TWO results, one per company, each labelled. " )


def test_transcript_latest_route_is_company_aware(monkeypatch):
    monkeypatch.setattr(
        "app.services.storage_router.resolve_signed_url",
        lambda key, provider=None, expires_in=3600: f"https://cdn.test/{key}?sig=zzt",
    )
    with blank_session() as db:
        db.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
        db.flush()

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        def _as(company_id: str):
            async def _override_scope():
                scope = frozenset({company_id})
                set_company_scope(db, scope)
                return scope

            app.dependency_overrides[apply_company_scope] = _override_scope

        principal = {"id": str(uuid.uuid4()), "email": "zzt-evidence@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
        try:
            print("\n" + "=" * 76)
            print("SCENARIO 4: GET " + ENDPOINT)
            print("            answers from the caller's ACTIVE COMPANY, no new parameter")
            print("=" * 76)
            _workbook(db, uploaded_at=datetime(2026, 8, 7, 10, 0, 0), company_id=SORENTO_ID)
            _workbook(db, uploaded_at=datetime(2026, 8, 7, 10, 0, 0), company_id=MOCHA_ID)
            db.commit()

            for cid, cname in ((SORENTO_ID, "Sorento"), (MOCHA_ID, "Mocha")):
                _as(cid)
                with TestClient(app) as c:
                    res = c.get(ENDPOINT)
                body = res.json()
                print(f"\n  as {cname} staff -> HTTP {res.status_code}")
                print("  " + json.dumps(
                    {k: body.get(k) for k in
                     ("filename", "company_id", "company_name", "attachment_id", "uploaded_at")},
                    indent=None))
                assert res.status_code == 200
                assert body["company_name"] == cname
            print("\n  -> same URL, each staff session gets its own company's workbook.")
        finally:
            app.dependency_overrides.clear()
