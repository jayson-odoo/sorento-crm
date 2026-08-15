"""Entity resolution returns every company's current Container Status workbook.

The scenario this pins (Journey Actor C): a dealer contact who buys from both
Mocha and Sorento asks "send me the container status list". The system already
knows which companies that contact belongs to (`respond_contact_companies`).
It must find a current workbook in EACH company and label each one, so the
contact (or the agent on their behalf) can say which one they meant - never
silently pick one, and never return two files that look identical.

``_resolve_with_domain_hint`` (`app/api/v1/system/references.py`) is the
short-circuit a document request actually takes for a hint like "container
status" (AC-C3) - it is exercised directly here rather than through the whole
`_resolve_input` dispatcher, mirroring the plan's own test list.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import text

from app.api.v1.system.references import _resolve_with_domain_hint
from app.models.base import set_company_scope
from app.models.company import Company, RespondContactCompany
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.container_status_document import ensure_attachment_type
from app.services.contact_access_type_service import ContactAccessTypeService

from tests._pg_fixture import blank_session, unique_code

SORENTO_ID = DEFAULT_COMPANY_ID
MOCHA_ID = "00000000-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        session.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
        session.flush()
        yield session


def _workbook(db, *, uploaded_at: datetime, company_id: str | None) -> str:
    """A live Container Status attachment owned by ``company_id``."""
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


def _resolve(db):
    """Run the short-circuit resolver for the "container status" hint."""
    return _resolve_with_domain_hint(db, "container status", [], "")


# --- AC-C1 / AC-C2 / AC-C3 --------------------------------------------------


def test_c1_c2_two_companies_each_current_yields_two_attributed_matches(db):
    now = datetime(2026, 8, 7, 10, 0, 0)
    sorento_wb = _workbook(db, uploaded_at=now, company_id=SORENTO_ID)
    mocha_wb = _workbook(db, uploaded_at=now, company_id=MOCHA_ID)
    db.commit()

    set_company_scope(db, frozenset({SORENTO_ID, MOCHA_ID}))
    result = _resolve(db)

    matches = [m for res in result["resolutions"] for m in res["matches"]]
    assert len(matches) == 2, "a contact granted both companies must see both currents"

    by_id = {m["uuid"]: m for m in matches}
    assert set(by_id) == {sorento_wb, mocha_wb}

    # AC-C2 - distinct company_id AND company_name, at the match level.
    assert by_id[sorento_wb]["company_id"] == SORENTO_ID
    assert by_id[sorento_wb]["company_name"] == "Sorento"
    assert by_id[mocha_wb]["company_id"] == MOCHA_ID
    assert by_id[mocha_wb]["company_name"] == "Mocha"
    assert by_id[sorento_wb]["company_id"] != by_id[mocha_wb]["company_id"]

    # ... and again inside `display`, for renderers that only read `display`.
    assert by_id[sorento_wb]["display"]["company_id"] == SORENTO_ID
    assert by_id[sorento_wb]["display"]["company_name"] == "Sorento"
    assert by_id[mocha_wb]["display"]["company_id"] == MOCHA_ID
    assert by_id[mocha_wb]["display"]["company_name"] == "Mocha"


def test_c3_the_domain_hint_short_circuit_is_the_path_exercised(db):
    """A document request actually takes this path - resolved is False (2
    matches for one term is ambiguous by count) but each is distinguishable."""
    now = datetime(2026, 8, 7, 10, 0, 0)
    _workbook(db, uploaded_at=now, company_id=SORENTO_ID)
    _workbook(db, uploaded_at=now, company_id=MOCHA_ID)
    db.commit()

    set_company_scope(db, frozenset({SORENTO_ID, MOCHA_ID}))
    result = _resolve(db)

    assert result["domain_hint"] == "container status"
    assert result["domain_hint_attachment_type_name"] == "Container Status"
    res = result["resolutions"][0]
    assert res["ambiguous"] is True
    assert len(res["matches"]) == 2
    company_names = {m["company_name"] for m in res["matches"]}
    assert company_names == {"Sorento", "Mocha"}


# --- AC-C4 -------------------------------------------------------------------


def test_c4_a_single_company_contact_sees_only_its_own_workbook(db):
    """Mocha's workbook must never be visible to a Sorento-only scope."""
    now = datetime(2026, 8, 7, 10, 0, 0)
    sorento_wb = _workbook(db, uploaded_at=now, company_id=SORENTO_ID)
    _workbook(db, uploaded_at=now, company_id=MOCHA_ID)
    db.commit()

    set_company_scope(db, frozenset({SORENTO_ID}))
    result = _resolve(db)

    matches = [m for res in result["resolutions"] for m in res["matches"]]
    assert len(matches) == 1
    assert matches[0]["uuid"] == sorento_wb
    assert matches[0]["company_id"] == SORENTO_ID
    assert matches[0]["company_name"] == "Sorento"


# --- AC-C6 -------------------------------------------------------------------


def test_c6_the_none_scope_all_companies_path_returns_one_per_company(db):
    """AC-C6. `scope=None` is the documented backward-compat path: an
    `X-API-Key` caller with no `contact_id` / `space_id` (n8n's legacy call
    shape). This is a DELIBERATE behaviour change from the old single-global-
    workbook design: that caller used to get exactly one workbook back; now,
    with one current workbook per company, it gets ONE PER COMPANY, each
    attributed, and the resolver reports the result as ambiguous rather than
    silently guessing one. A caller that wants a single answer must pass
    contact identity (`contact_id` + `space_id`) so the scope narrows to that
    contact's own companies (AC-C1/AC-C4) - that is the intended escape
    hatch, not a bug to route around here.
    """
    now = datetime(2026, 8, 7, 10, 0, 0)
    sorento_wb = _workbook(db, uploaded_at=now, company_id=SORENTO_ID)
    mocha_wb = _workbook(db, uploaded_at=now, company_id=MOCHA_ID)
    db.commit()

    set_company_scope(db, None)
    result = _resolve(db)

    res = result["resolutions"][0]
    assert res["resolved"] is False
    assert res["ambiguous"] is True
    assert len(res["matches"]) == 2

    by_id = {m["uuid"]: m for m in res["matches"]}
    assert set(by_id) == {sorento_wb, mocha_wb}
    assert by_id[sorento_wb]["company_name"] == "Sorento"
    assert by_id[mocha_wb]["company_name"] == "Mocha"


# --- the real contact path end to end ---------------------------------------


def _workspace(db, space_id: str):
    from app.models.respond_workspace import RespondWorkspace

    ws = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=space_id,
        name=f"ZZT {space_id}",
        api_key_ciphertext="zzt-not-a-real-key",
    )
    db.add(ws)
    db.flush()
    return ws


def test_contact_granted_both_companies_resolves_both_company_ids(db):
    """Pins the mapping the captain's "contact with access to both gets two
    results" claim rests on: `ContactAccessTypeService.resolve_contact_company_ids`
    (the same lookup `company_scope_resolver._resolve_api_key_scope` calls)."""
    from app.models.access import RespondContact

    ws = _workspace(db, unique_code("space"))
    contact = RespondContact(
        id=unique_code("CONTACT"),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name="ZZT Dual Company Contact",
        respond_io_id=unique_code("rio"),
        workspace_id=ws.id,
    )
    db.add(contact)
    db.flush()
    db.add(RespondContactCompany(respond_contact_id=contact.id, company_id=SORENTO_ID))
    db.add(RespondContactCompany(respond_contact_id=contact.id, company_id=MOCHA_ID))
    db.commit()

    company_ids = ContactAccessTypeService(db).resolve_contact_company_ids(
        contact.respond_io_id, ws.space_id
    )

    assert set(company_ids) == {SORENTO_ID, MOCHA_ID}


def test_contact_granted_one_company_resolves_only_that_company(db):
    from app.models.access import RespondContact

    ws = _workspace(db, unique_code("space"))
    contact = RespondContact(
        id=unique_code("CONTACT"),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name="ZZT Single Company Contact",
        respond_io_id=unique_code("rio"),
        workspace_id=ws.id,
    )
    db.add(contact)
    db.flush()
    db.add(RespondContactCompany(respond_contact_id=contact.id, company_id=SORENTO_ID))
    db.commit()

    company_ids = ContactAccessTypeService(db).resolve_contact_company_ids(
        contact.respond_io_id, ws.space_id
    )

    assert company_ids == [SORENTO_ID]
