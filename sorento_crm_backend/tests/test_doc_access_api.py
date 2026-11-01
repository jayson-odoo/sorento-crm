"""DOC-ACCESS-SIMPLE S1 + S2 over HTTP (DAS-BE-8 .. DAS-BE-11).

Routes mount under `/api/v1/resource-management/` (app/api/v1/__init__.py:159-160), the same prefix
as the existing attachment-type routes. Auth is the real permission layer over seeded users, switched
per request through `who["id"]`. Contacts are masked (CONTACT A ...) and every row is seeded here.
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app  # noqa: E402  MUST be first app import (circular import in guards)
from app.models.base import company_scope
from tests._fake_storage import patch_storage
from tests._knowledge_seed import (
    EXACT_VEC,
    SORENTO_COMPANY_ID,
    query_embed,
    seed_access_codes,
    seed_attachment,
    seed_chunk,
    seed_company,
    seed_reader,
    seed_type,
)
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_contact, seed_user
from sqlalchemy import text

BASE = "/api/v1/resource-management"
TYPES = f"{BASE}/attachment-types"
MATRIX = f"{BASE}/document-access"
CODES = ["dealer", "end_user", "mocha_dealer", "sorento_office"]  # catalogue order; nl_dealer is inactive


@pytest.fixture
def api(monkeypatch):
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.services import knowledge_service
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        with company_scope(db, frozenset({SORENTO_COMPANY_ID})):
            patch_storage(monkeypatch)
            monkeypatch.setattr(knowledge_service, "_enqueue", lambda attachment_id: None)
            seed_access_codes(db, CODES, inactive=["nl_dealer"])
            manager = seed_reader(
                db,
                slugs=(
                    "resource.attachment_types.view",
                    "resource.attachment_types.edit",
                    "resource.attachment_types.add",
                    "user_management.contacts.view",
                ),
            )
            viewer = seed_reader(db, slugs=("resource.attachment_types.view",))
            contacts_only = seed_reader(db, slugs=("user_management.contacts.view",))
            nobody = seed_reader(db, slugs=())
            who = {"id": manager}

            def _db():
                yield db

            def _user():
                return {"id": who["id"], "email": "k@test.com"}

            app.dependency_overrides[get_db] = _db
            app.dependency_overrides[get_current_user] = _user
            app.dependency_overrides[get_current_user_or_api_key] = _user
            app.dependency_overrides[apply_company_scope] = lambda: frozenset({SORENTO_COMPANY_ID})
            try:
                with TestClient(app) as c:
                    yield type(
                        "Api",
                        (),
                        {"c": c, "db": db, "who": who, "manager": manager, "viewer": viewer,
                         "contacts_only": contacts_only, "nobody": nobody},
                    )
            finally:
                app.dependency_overrides.clear()


def _grant(db, user_id, company_id):
    from app.models.company import UserCompany

    db.add(UserCompany(id=str(uuid.uuid4()), user_id=user_id, company_id=company_id))
    db.flush()


def _file(db, att_type, name, levels, *, company_id=SORENTO_COMPANY_ID, deleted=False):
    att = seed_attachment(db, att_type, name, company_id=company_id)
    att.access_levels = list(levels)
    att.is_deleted = deleted
    if company_id is None:
        att.company_id = None
    db.flush()
    return att


def _contact(db, name, codes, companies=(SORENTO_COMPANY_ID,), *, agent=True, respond_id=None):
    c = seed_contact(db, agent_enabled=agent)
    db.execute(text("UPDATE respond_contacts SET name = :n WHERE id = :i"), {"n": name, "i": c["pk"]})
    if respond_id:
        db.execute(text("UPDATE respond_contacts SET respond_io_id = :r WHERE id = :i"), {"r": respond_id, "i": c["pk"]})
        c["respond_id"] = respond_id
    for code in codes:
        db.execute(text("INSERT INTO respond_contact_access_types (contact_id, access_type_code) VALUES (:c, :k)"), {"c": c["pk"], "k": code})
    for co in companies:
        db.execute(
            text("INSERT INTO respond_contact_companies (id, respond_contact_id, company_id) VALUES (:i, :c, :co)"),
            {"i": str(uuid.uuid4()), "c": c["pk"], "co": co},
        )
    db.flush()
    return c


def _rows(res):
    assert res.status_code == 200, res.text
    return {r["id"]: r for r in res.json()["rows"]}


def _body(**extra):
    return {"type_name": f"ZZTK Doc {uuid.uuid4().hex[:6]}", "allowed_extensions": "pdf,docx", **extra}


# ---------------------------------------------------------------- DAS-BE-8


def test_put_ai_ticks_saves_and_returns(api):
    t = api.c.post(f"{TYPES}/", json=_body()).json()

    res = api.c.put(f"{TYPES}/{t['id']}", json={"ai_read_staff": True, "ai_read_codes": ["dealer"]})

    assert res.status_code == 200, res.text
    assert (res.json()["ai_read_staff"], res.json()["ai_read_codes"]) == (True, ["dealer"])
    # Partial update: omitted fields are untouched.
    res = api.c.put(f"{TYPES}/{t['id']}", json={"description": "renamed only"})
    assert (res.json()["ai_read_staff"], res.json()["ai_read_codes"]) == (True, ["dealer"])
    got = api.c.get(f"{TYPES}/{t['id']}").json()
    assert (got["ai_read_staff"], got["ai_read_codes"]) == (True, ["dealer"])


def test_create_accepts_the_two_ai_fields_and_defaults_them(api):
    plain = api.c.post(f"{TYPES}/", json=_body()).json()
    ticked = api.c.post(f"{TYPES}/", json=_body(ai_read_staff=True, ai_read_codes=["end_user"])).json()

    assert (plain["ai_read_staff"], plain["ai_read_codes"]) == (False, [])
    assert (ticked["ai_read_staff"], ticked["ai_read_codes"]) == (True, ["end_user"])


@pytest.mark.parametrize("codes", [["zz_unknown"], ["dealer", "nl_dealer"]])
def test_put_unknown_or_inactive_code_400(api, codes):
    t = api.c.post(f"{TYPES}/", json=_body()).json()

    res = api.c.put(f"{TYPES}/{t['id']}", json={"ai_read_codes": codes})

    assert res.status_code == 400, res.text
    bad = next(c for c in codes if c in ("zz_unknown", "nl_dealer"))
    assert bad in json.dumps(res.json()), "the message names the code"
    assert api.c.get(f"{TYPES}/{t['id']}").json()["ai_read_codes"] == [], "nothing was saved"


def test_put_dedupes_and_orders(api):
    t = api.c.post(f"{TYPES}/", json=_body()).json()

    res = api.c.put(f"{TYPES}/{t['id']}", json={"ai_read_codes": ["sorento_office", "dealer", "sorento_office", "end_user"]})

    assert res.status_code == 200, res.text
    assert res.json()["ai_read_codes"] == ["dealer", "end_user", "sorento_office"]


def test_put_direct_access(api):
    t = api.c.post(f"{TYPES}/", json=_body()).json()
    assert t["is_direct_access"] is False

    res = api.c.put(f"{TYPES}/{t['id']}", json={"is_direct_access": True})

    assert res.status_code == 200, res.text
    assert res.json()["is_direct_access"] is True
    assert api.c.get(f"{TYPES}/{t['id']}").json()["is_direct_access"] is True


def test_put_requires_edit_permission(api):
    t = api.c.post(f"{TYPES}/", json=_body()).json()
    api.who["id"] = api.viewer

    for payload in ({"ai_read_staff": True}, {"ai_read_codes": ["dealer"]}, {"is_direct_access": True}):
        assert api.c.put(f"{TYPES}/{t['id']}", json=payload).status_code == 403

    api.who["id"] = api.manager
    got = api.c.get(f"{TYPES}/{t['id']}").json()
    assert (got["ai_read_staff"], got["ai_read_codes"], got["is_direct_access"]) == (False, [], False)


def test_response_has_no_ai_audience(api):
    t = api.c.post(f"{TYPES}/", json=_body(ai_read_staff=True)).json()
    listed = api.c.get(f"{TYPES}/", params={"limit": 100}).json()["data"]

    assert "ai_audience" not in t
    assert "ai_audience" not in api.c.get(f"{TYPES}/{t['id']}").json()
    assert "ai_audience" not in api.c.put(f"{TYPES}/{t['id']}", json={"ai_read_staff": False}).json()
    assert all("ai_audience" not in r for r in listed)


# ---------------------------------------------------------------- DAS-BE-9


def test_matrix_rows_counts_and_reach(api):
    from app.models.access import ContactAttachmentType

    db = api.db
    t = seed_type(db, staff=True, codes=["dealer"])
    t.is_shared = True
    t.is_direct_access = True
    _file(db, t, "a.pdf", ["dealer", "end_user"])
    _file(db, t, "b.DOCX", ["end_user"])
    _file(db, t, "c.xlsx", ["dealer"])  # filed, not readable
    _file(db, t, "d.pdf", ["dealer"], deleted=True)  # deleted: counted nowhere
    empty = seed_type(db, staff=False, codes=[])
    for _ in range(2):
        pk = _contact(db, "CONTACT A", [])["pk"]
        db.add(ContactAttachmentType(contact_id=pk, attachment_type_id=str(t.id)))
    db.flush()

    res = api.c.get(MATRIX)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["contact"] is None
    assert body["access_types"] == [{"code": c, "name": c.replace("_", " ").title()} for c in CODES], "active only, sort order"
    rows = _rows(res)
    row = rows[str(t.id)]
    assert row["type_name"] == t.type_name
    assert (row["is_shared"], row["is_direct_access"], row["grant_count"]) == (True, True, 2)
    assert (row["file_count"], row["readable_count"]) == (3, 2)
    assert (row["ai_read_staff"], row["ai_read_codes"]) == (True, ["dealer"])
    assert row["reach"] == {"dealer": 1, "end_user": 2, "mocha_dealer": 0, "sorento_office": 0}
    assert row["preview"] is None
    assert (rows[str(empty.id)]["file_count"], rows[str(empty.id)]["readable_count"]) == (0, 0)


def test_matrix_requires_view_permission(api):
    api.who["id"] = api.contacts_only
    assert api.c.get(MATRIX).status_code == 403
    api.who["id"] = api.nobody
    assert api.c.get(MATRIX).status_code == 403
    api.who["id"] = api.viewer
    assert api.c.get(MATRIX).status_code == 200


def test_matrix_counts_only_granted_companies(api):
    db = api.db
    mocha, stranger = seed_company(db, "Mocha Co"), seed_company(db, "Stranger Co")
    t = seed_type(db, staff=True, codes=["dealer"])
    _file(db, t, "mine.pdf", ["dealer"])
    _file(db, t, "granted.pdf", ["dealer"], company_id=mocha)
    _file(db, t, "stranger.pdf", ["dealer"], company_id=stranger)
    _grant(db, api.manager, SORENTO_COMPANY_ID)
    _grant(db, api.manager, mocha)

    plain = _rows(api.c.get(MATRIX))[str(t.id)]
    wide = _rows(api.c.get(MATRIX, params={"company_scope": "grants"}))[str(t.id)]

    assert plain["file_count"] == 1, "without the flag the active company only"
    assert (wide["file_count"], wide["readable_count"]) == (2, 2), "with it every granted company, never the stranger's"


# ---------------------------------------------------------------- DAS-BE-10


def _preview_world(api):
    """A type for each verdict, a contact holding dealer + end_user in Sorento and Mocha."""
    db = api.db
    mocha = seed_company(db, "Mocha Co")
    _grant(db, api.manager, SORENTO_COMPANY_ID)
    _grant(db, api.manager, mocha)
    contact = _contact(db, "CONTACT A", ["dealer", "end_user"], [SORENTO_COMPANY_ID, mocha])
    types = {
        "reads": seed_type(db, staff=False, codes=["dealer"]),
        "off": seed_type(db, staff=False, codes=[]),
        "staff_only": seed_type(db, staff=True, codes=[]),
        "not_ticked": seed_type(db, staff=False, codes=["mocha_dealer"]),
        "no_documents": seed_type(db, staff=False, codes=["dealer"]),
    }
    for k in ("off", "staff_only", "not_ticked"):
        _file(db, types[k], f"{k}.pdf", CODES)
    _file(db, types["no_documents"], "sheet.xlsx", CODES)
    return db, mocha, contact, types


def test_preview_contact_block(api):
    db, mocha, contact, _ = _preview_world(api)

    res = api.c.get(MATRIX, params={"contact_id": contact["pk"], "company_scope": "grants"})

    assert res.status_code == 200, res.text
    block = res.json()["contact"]
    assert block["id"] == contact["pk"] and block["name"] == "CONTACT A"
    assert (block["runs_as"], block["agent_on"], block["blocked"]) == ("contact", True, None)
    assert block["access_types"] == ["dealer", "end_user"]
    assert sorted(c["id"] for c in block["companies"]) == sorted([SORENTO_COMPANY_ID, mocha])
    assert all(c["name"] for c in block["companies"])

    off_contact = _contact(db, "CONTACT B", ["end_user"], agent=False)
    block = api.c.get(MATRIX, params={"contact_id": off_contact["pk"]}).json()["contact"]
    assert block["agent_on"] is False


def test_preview_verdicts_each_kind(api):
    db, mocha, contact, types = _preview_world(api)
    _file(db, types["reads"], "ok.pdf", ["dealer"])

    rows = _rows(api.c.get(MATRIX, params={"contact_id": contact["pk"], "company_scope": "grants"}))

    verdicts = {k: rows[str(t.id)]["preview"]["verdict"] for k, t in types.items()}
    assert verdicts == {"reads": "reads", "off": "off", "staff_only": "staff_only", "not_ticked": "not_ticked", "no_documents": "no_documents"}
    reads = rows[str(types["reads"].id)]["preview"]
    assert (reads["reads"], reads["total"], reads["no_shared_code"], reads["other_company"]) == (1, 1, 0, 0)


def test_preview_counts_split_the_rest(api):
    db, mocha, contact, types = _preview_world(api)
    stranger = seed_company(db, "Stranger Co")
    _grant(db, api.manager, stranger)
    t = types["reads"]
    _file(db, t, "ok.pdf", ["dealer"])
    _file(db, t, "shared.pdf", ["dealer"], company_id=None)
    _file(db, t, "wrong_code.pdf", ["mocha_dealer"])
    _file(db, t, "elsewhere.docx", ["dealer"], company_id=stranger)
    _file(db, t, "sheet.xlsx", ["dealer"])
    _file(db, t, "gone.pdf", ["dealer"], deleted=True)

    pv = _rows(api.c.get(MATRIX, params={"contact_id": contact["pk"], "company_scope": "grants"}))[str(t.id)]["preview"]

    assert (pv["reads"], pv["total"], pv["no_shared_code"], pv["other_company"]) == (2, 4, 1, 1)


def test_preview_blocked_contacts(api):
    db, mocha, contact, types = _preview_world(api)
    no_code = _contact(db, "CONTACT C", [])
    no_company = _contact(db, "CONTACT D", ["dealer"], [])
    shared_id = f"ZZT-amb-{uuid.uuid4().hex[:8]}"
    _contact(db, "CONTACT E", ["dealer"], respond_id=shared_id)
    ambiguous = _contact(db, "CONTACT E", ["dealer"], respond_id=shared_id)

    for who, expect in ((no_code, "no_access_type"), (no_company, "no_company"), (ambiguous, "ambiguous")):
        res = api.c.get(MATRIX, params={"contact_id": who["pk"], "company_scope": "grants"})
        assert res.status_code == 200, res.text
        assert res.json()["contact"]["blocked"] == expect
        assert {r["preview"]["verdict"] for r in res.json()["rows"]} == {expect}


def test_preview_a_contact_that_runs_as_staff(api):
    db, mocha, contact, types = _preview_world(api)
    seed_user(db, contact_pk=contact["pk"], slugs=("resource.attachments.view",))
    staff_type = seed_type(db, staff=True, codes=["dealer"])
    _file(db, staff_type, "s.pdf", ["dealer"])
    codes_type = seed_type(db, staff=False, codes=["dealer"])
    _file(db, codes_type, "c.pdf", ["dealer"])

    res = api.c.get(MATRIX, params={"contact_id": contact["pk"], "company_scope": "grants"})

    assert res.json()["contact"]["runs_as"] == "staff"
    rows = _rows(res)
    assert rows[str(staff_type.id)]["preview"]["verdict"] == "staff_reads"
    assert rows[str(codes_type.id)]["preview"]["verdict"] == "not_for_staff"


def test_preview_requires_contacts_view(api):
    contact = _contact(api.db, "CONTACT A", ["dealer"])
    api.who["id"] = api.viewer

    assert api.c.get(MATRIX, params={"contact_id": contact["pk"]}).status_code == 403
    assert api.c.get(MATRIX).status_code == 200, "without a contact the view permission is enough"
    api.who["id"] = api.manager
    assert api.c.get(MATRIX, params={"contact_id": contact["pk"]}).status_code == 200


def test_preview_reads_matches_search_for_contact(api):
    """Parity: the preview's `reads` equals the distinct documents search_for_contact can return."""
    from app.services import knowledge_service as ks
    from app.services.chatbot.agent.access import _active_access_codes

    db, mocha, contact, types = _preview_world(api)
    t = types["reads"]
    stranger = seed_company(db, "Stranger Co")
    _grant(db, api.manager, stranger)
    made = [
        _file(db, t, "p1.pdf", ["dealer"]),
        _file(db, t, "p2.pdf", ["dealer", "end_user"], company_id=mocha),
        _file(db, t, "p3.pdf", ["dealer"], company_id=None),
        _file(db, t, "p4.pdf", ["end_user"]),
        _file(db, t, "p5.docx", ["dealer"], company_id=stranger),
    ]
    for att in made:
        seed_chunk(db, att, EXACT_VEC, text=f"passage of {att.original_filename}", company_id=att.company_id)

    pv = _rows(api.c.get(MATRIX, params={"contact_id": contact["pk"], "company_scope": "grants"}))[str(t.id)]["preview"]

    with company_scope(db, frozenset({SORENTO_COMPANY_ID, mocha})):
        out = ks.search_for_contact(
            db, access_codes=_active_access_codes(db, contact["pk"]), query="q", embed=query_embed, top_k=ks.MAX_TOP_K
        )
    returned = {p["text"] for p in out["passages"]}
    assert returned == {"passage of p1.pdf", "passage of p2.pdf", "passage of p3.pdf"}
    assert pv["reads"] == len(returned) == 3


# ---------------------------------------------------------------- DAS-BE-11


def _docs(api, type_id, **params):
    return api.c.get(f"{MATRIX}/{type_id}/documents", params=params)


def test_documents_list_verdicts_and_pagination(api):
    db, mocha, contact, types = _preview_world(api)
    stranger = seed_company(db, "Stranger Co")
    _grant(db, api.manager, stranger)
    t = types["reads"]
    t.is_shared = False
    _file(db, t, "a.pdf", ["dealer"])
    _file(db, t, "b.pdf", ["mocha_dealer"])
    _file(db, t, "c.docx", ["dealer"], company_id=stranger)
    _file(db, t, "d.pdf", ["dealer"], company_id=None)
    _file(db, t, "e.pdf", ["dealer"])
    _file(db, t, "skip.xlsx", ["dealer"])
    _file(db, t, "gone.pdf", ["dealer"], deleted=True)

    plain = _docs(api, t.id, company_scope="grants").json()
    assert (plain["total"], plain["page"], plain["limit"]) == (5, 1, 50)
    assert [i["original_filename"] for i in plain["items"]] == ["a.pdf", "b.pdf", "c.docx", "d.pdf", "e.pdf"]
    item = plain["items"][0]
    assert set(item) >= {"id", "original_filename", "access_levels", "company_name", "ai_read_status", "verdict"}
    assert item["access_levels"] == ["dealer"] and item["verdict"] is None
    assert plain["items"][3]["company_name"] is None, "shared"
    assert plain["items"][0]["company_name"]

    pv = _docs(api, t.id, contact_id=contact["pk"], company_scope="grants").json()
    assert [i["verdict"] for i in pv["items"]] == ["reads", "no_shared_code", "other_company", "reads", "reads"]

    page2 = _docs(api, t.id, page=2, limit=2, company_scope="grants").json()
    assert [i["original_filename"] for i in page2["items"]] == ["c.docx", "d.pdf"]
    assert page2["total"] == 5 and page2["limit"] == 2

    assert _docs(api, t.id, limit=201).status_code == 422

    blocked = _contact(db, "CONTACT C", [])
    verdicts = {i["verdict"] for i in _docs(api, t.id, contact_id=blocked["pk"]).json()["items"]}
    assert verdicts == {"no_access_type"}


def test_documents_unknown_type_404(api):
    assert _docs(api, uuid.uuid4()).status_code == 404


def test_documents_permissions(api):
    t = seed_type(db := api.db, staff=True)
    contact = _contact(db, "CONTACT A", ["dealer"])
    api.who["id"] = api.contacts_only
    assert _docs(api, t.id).status_code == 403
    api.who["id"] = api.viewer
    assert _docs(api, t.id).status_code == 200
    assert _docs(api, t.id, contact_id=contact["pk"]).status_code == 403
