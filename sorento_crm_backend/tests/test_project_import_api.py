"""Project import: routes, permissions, company scope (AC-PI-08..11, 39..41).

RED tests, written before `app/api/v1/projects/project_import.py` exists
(PLAN-project-import-12nov.md, "Routes"). The real app over a `blank_session` (Postgres);
auth and the company scope are overridden, permissions are granted per test.

Kill tests in this file: 403 without the permission on every route, 404 for a run of
another company, and no customer / project / person name in any log line.
"""
from __future__ import annotations

import logging

import pytest

from tests.fixtures.project_import.build_so_summary import (
    FIELDS,
    HEADER_BY_FIELD,
    MONTHLY_SHEETS,
    SUMMARY_SHEET,
    build_workbook,
)

from ._project_import_support import (  # noqa: F401  fixtures
    MARKER,
    XLSX,
    api_client,
    make_book,
    memory_storage,
    new_run,
    row,
    seed_company,
    seed_customer,
    world,
)

BASE = "/api/v1/projects/import"
VIEW = "projects.import.view"
RUN = "projects.import.run"
BOTH = {VIEW, RUN}


def _upload(client, content, name="SO SUMMARY 2026.xlsx", ctype=XLSX):
    return client.post(f"{BASE}/runs", files={"file": (name, content, ctype)})


def _small_book():
    return make_book({"JAN'26": [
        row("PS26-0001"),
        row("PS26-0002", customer="CUSTOMER 002 SDN BHD", project_name="PROJECT 2"),
    ]})


# --------------------------------------------------------------------------- registry


def test_ac_pi_39_both_permissions_are_registered():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {p["slug"] for p in PERMISSION_REGISTRY}
    assert VIEW in slugs
    assert RUN in slugs


# --------------------------------------------------------------------------- AC-PI-39


ROUTES = [
    ("get", "/runs", VIEW),
    ("post", "/runs", RUN),
    ("get", "/runs/{id}", VIEW),
    ("put", "/runs/{id}/columns", RUN),
    ("get", "/runs/{id}/lines?kind=customer", VIEW),
    ("put", "/runs/{id}/lines", RUN),
    ("put", "/runs/{id}/lines/bulk", RUN),
    ("post", "/runs/{id}/preview", RUN),
    ("get", "/runs/{id}/rows", VIEW),
    ("post", "/runs/{id}/import", RUN),
]


def _call(client, method, path, run_id):
    url = BASE + path.replace("{id}", str(run_id))
    if method == "post" and path == "/runs":
        return _upload(client, _small_book())
    body = {
        "/runs/{id}/columns": {"sheets": ["JAN'26"], "columns": HEADER_BY_FIELD},
        "/runs/{id}/lines": {"kind": "customer", "customer_value_key": "",
                             "value_key": "CUSTOMER 001 SDN BHD", "action": "skip",
                             "target_id": None, "new_title": None},
        "/runs/{id}/lines/bulk": {"kind": "customer", "keys": [["", "CUSTOMER 001 SDN BHD"]],
                                  "action": "skip", "target_id": None, "new_title": None},
    }.get(path)
    if method in ("put", "post"):
        return getattr(client, method)(url, json=body or {})
    return getattr(client, method)(url)


@pytest.mark.parametrize("method,path,slug", ROUTES)
def test_ac_pi_39_every_route_refuses_without_its_permission(world, api_client, method, path,
                                                              slug):
    w = world
    run = new_run(w, _small_book())
    w.db.commit()
    # Holding only the OTHER permission is still a refusal for this route.
    others = BOTH - {slug}
    for granted in (set(), others):
        if slug == VIEW and granted == {RUN}:
            continue  # run-holders are not promised read access by the UAC; skip that cell
        client = api_client(w.db, w.admin_id, w.company_id, granted)
        response = _call(client, method, path, run.id)
        assert response.status_code == 403, (method, path, granted, response.text)


@pytest.mark.parametrize("method,path,slug", [r for r in ROUTES if r[2] == VIEW])
def test_ac_pi_39_view_routes_answer_with_the_view_permission(world, api_client, method, path,
                                                               slug):
    w = world
    run = new_run(w, _small_book())
    w.db.commit()
    client = api_client(w.db, w.admin_id, w.company_id, {VIEW})
    response = _call(client, method, path, run.id)
    assert response.status_code == 200, response.text


# --------------------------------------------------------------------------- AC-PI-40


@pytest.mark.parametrize("method,path,slug", [r for r in ROUTES if r[1] != "/runs"])
def test_ac_pi_40_a_run_of_another_company_reads_as_404(world, api_client, method, path, slug):
    from app.models.base import company_scope
    from app.services.project_import import service

    w = world
    other = seed_company(w.db, "Other")
    with company_scope(w.db, frozenset({other})):
        foreign = service.create_run(w.db, company_id=other, user_id=w.admin_id,
                                     filename="theirs.xlsx", content=_small_book())
    w.db.commit()

    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    response = _call(client, method, path, foreign.id)
    assert response.status_code == 404, (method, path, response.text)


def test_ac_pi_40_the_runs_list_shows_only_this_companys_runs(world, api_client):
    from app.models.base import company_scope
    from app.services.project_import import service

    w = world
    mine = new_run(w, _small_book())
    other = seed_company(w.db, "Other")
    with company_scope(w.db, frozenset({other})):
        service.create_run(w.db, company_id=other, user_id=w.admin_id, filename="theirs.xlsx",
                           content=_small_book())
    w.db.commit()

    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    response = client.get(f"{BASE}/runs", params={"page": 1, "limit": 25})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [r["id"] for r in data] == [str(mine.id)]
    assert data[0]["run_no"] == "PIM-0001"


# --------------------------------------------------------------------------- AC-PI-08 / 09


def test_ac_pi_08_and_09_upload_gives_201_with_the_sheet_probe(world, api_client):
    w = world
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)

    response = _upload(client, build_workbook())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["run_no"] == "PIM-0001"
    sheets = {s["name"]: s for s in body["sheets"]}
    assert list(sheets) == [
        "JAN'26", "FEB'26", "MAC'26 ", "APR'26", "MAY'26", "JUN'26 ", SUMMARY_SHEET,
        "JUL'26 ", "AUG'26",
    ]
    assert sheets[SUMMARY_SHEET]["has_ps_heading"] is False
    assert sheets[SUMMARY_SHEET]["row_count"] == 0
    assert sheets["AUG'26"]["row_count"] == 78
    jan = sheets["JAN'26"]
    assert [c["header"] for c in jan["columns"]] == [HEADER_BY_FIELD[f] for f in FIELDS]
    # AC-PI-09: each heading resolves through import_field_alias (project_po_register).
    assert [c["field"] for c in jan["columns"]] == FIELDS
    assert all("sample" in c for c in jan["columns"])
    # AC-PI-03: the SUMMARY sheet is unticked by default.
    from app.models.job import ImportJob

    job = w.db.get(ImportJob, body["id"])
    assert [n.strip() for n in job.job_metadata["sheets"]] == [
        s.name.strip() for s in MONTHLY_SHEETS
    ]
    assert job.job_type == "project_po_register"
    assert job.job_metadata["phase"] == "draft"
    assert job.source_file_key
    # No UUID of the uploader in place of a name, and the run number is the label.
    assert body["run_no"]


@pytest.mark.parametrize("name,content,ctype", [
    ("notes.txt", b"plain text", "text/plain"),
    ("broken.xlsx", b"PK\x03\x04" + b"junk" * 100, XLSX),
])
def test_ac_pi_08_bad_uploads_give_422_with_a_plain_message(world, api_client, name, content,
                                                             ctype):
    w = world
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)

    response = _upload(client, content, name=name, ctype=ctype)

    assert response.status_code == 422, response.text
    text = response.text
    assert "Traceback" not in text
    assert "message" in response.json() or "detail" in response.json()


def test_ac_pi_08_a_file_over_10_mb_gives_422(world, api_client):
    w = world
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)

    response = _upload(client, build_workbook() + b"\0" * (10 * 1024 * 1024 + 1))

    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------- AC-PI-10


def test_ac_pi_10_a_column_choice_is_saved_and_reused_on_the_next_file(world, api_client):
    from openpyxl import Workbook
    import io

    from app.models.import_alias import ImportFieldAlias

    w = world
    wb = Workbook()
    ws = wb.active
    ws.title = "JAN'26"
    headers = [HEADER_BY_FIELD["ps_number"], "CUST NAME", HEADER_BY_FIELD["project_name"],
               HEADER_BY_FIELD["po_number"], "EXTRA COL"]
    ws.append(headers)
    ws.append(["PS26-0001", "CUSTOMER 001 SDN BHD", "PROJECT 1", "PO-1", "whatever"])
    buf = io.BytesIO()
    wb.save(buf)
    content = buf.getvalue()
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)

    first = _upload(client, content)
    assert first.status_code == 201, first.text
    run_id = first.json()["id"]
    columns = {"ps_number": headers[0], "customer": "CUST NAME",
               "project_name": headers[2], "po_number": headers[3], "ignore": "EXTRA COL"}
    saved = client.put(f"{BASE}/runs/{run_id}/columns",
                       json={"sheets": ["JAN'26"], "columns": columns})
    assert saved.status_code in (200, 204), saved.text
    aliases = w.db.query(ImportFieldAlias).filter(
        ImportFieldAlias.doc_type == "project_po_register").all()
    assert any(a.field == "customer" for a in aliases)
    assert any(a.field == "ignore" for a in aliases)

    second = _upload(client, content, name="next month.xlsx")
    assert second.status_code == 201, second.text
    cols = {c["header"]: c["field"] for c in second.json()["sheets"][0]["columns"]}
    assert cols["CUST NAME"] == "customer"
    assert cols["EXTRA COL"] == "ignore"


# --------------------------------------------------------------------------- AC-PI-11


@pytest.mark.parametrize("missing", ["ps_number", "customer", "po_number"])
def test_ac_pi_11_preview_is_refused_while_a_required_field_has_no_column(world, api_client,
                                                                          missing):
    w = world
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    created = _upload(client, _small_book())
    run_id = created.json()["id"]
    columns = {f: h for f, h in HEADER_BY_FIELD.items() if f != missing}
    client.put(f"{BASE}/runs/{run_id}/columns", json={"sheets": ["JAN'26"], "columns": columns})

    response = client.post(f"{BASE}/runs/{run_id}/preview")

    assert response.status_code == 422, response.text
    label = {"ps_number": "PS", "customer": "CUSTOMER", "po_number": "PO"}[missing]
    assert label in response.text.upper()


# --------------------------------------------------------------------------- happy flow


def test_preview_rows_and_import_through_the_routes(world, api_client, monkeypatch):
    from app.services import queue_service

    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    run_id = _upload(client, _small_book()).json()["id"]
    assert client.put(f"{BASE}/runs/{run_id}/columns",
                      json={"sheets": ["JAN'26"], "columns": HEADER_BY_FIELD}).status_code in (200, 204)
    set_one = client.put(f"{BASE}/runs/{run_id}/lines", json={
        "kind": "customer", "customer_value_key": "", "value_key": "CUSTOMER 001 SDN BHD",
        "action": "link", "target_id": customer.id, "new_title": None})
    assert set_one.status_code == 200, set_one.text
    bulk = client.put(f"{BASE}/runs/{run_id}/lines/bulk", json={
        "kind": "project",
        "keys": [["CUSTOMER 001 SDN BHD", "PROJECT 001 SAMPLE NAME"]],
        "action": "create", "target_id": None, "new_title": "ZZT ROUTE TOWER"})
    assert bulk.status_code == 200, bulk.text
    todo = client.get(f"{BASE}/runs/{run_id}/lines", params={"kind": "customer", "status": "todo"})
    assert todo.status_code == 200
    todo_rows = todo.json()["data"] if isinstance(todo.json(), dict) else todo.json()
    assert [l["value_key"] for l in todo_rows] == ["CUSTOMER 002 SDN BHD"]

    preview = client.post(f"{BASE}/runs/{run_id}/preview")
    assert preview.status_code == 200, preview.text
    counts = preview.json()["counts"]
    assert counts.get("created") == 1
    assert counts.get("needs_review") == 1

    rows = client.get(f"{BASE}/runs/{run_id}/rows", params={"page": 1, "limit": 50})
    assert rows.status_code == 200, rows.text
    assert len(rows.json()["data"]) == 2
    only = client.get(f"{BASE}/runs/{run_id}/rows", params={"outcome": "needs_review"})
    assert [r["ps_number"] for r in only.json()["data"]] == ["PS26-0002"]

    queued = []
    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda func, *a, queue_name="imports", **k: queued.append(
                            (func.__name__, queue_name)) or type("J", (), {"id": "rq-1"})())
    from app.services.project_import import service

    monkeypatch.setattr(service, "enqueue_job", queue_service.enqueue_job, raising=False)
    started = client.post(f"{BASE}/runs/{run_id}/import")
    assert started.status_code == 202, started.text
    assert started.json()["job_id"]
    assert queued == [("process_project_import", "imports")]


# --------------------------------------------------------------------------- AC-PI-41


def test_ac_pi_41_no_name_reaches_a_log_line(world, api_client, caplog):
    w = world
    customer = seed_customer(w.db, w.company_id, "ZZT SECRETNAME DEALER")
    w.db.commit()
    content = make_book({"JAN'26": [
        row("PS26-0001", customer="CUSTOMER SECRETNAME SDN BHD",
            project_name="PROJECT SECRETNAME TOWER", salesperson="SECRETNAME SALES",
            customer_service="SECRETNAME CS", developer="SECRETNAME DEV"),
        row("PS26-0002", customer="CUSTOMER SECRETNAME SDN BHD", po_value="-"),
    ]})
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)

    with caplog.at_level(logging.DEBUG):
        run_id = _upload(client, content).json()["id"]
        client.put(f"{BASE}/runs/{run_id}/columns",
                   json={"sheets": ["JAN'26"], "columns": HEADER_BY_FIELD})
        client.put(f"{BASE}/runs/{run_id}/lines", json={
            "kind": "customer", "customer_value_key": "",
            "value_key": "CUSTOMER SECRETNAME SDN BHD", "action": "link",
            "target_id": customer.id, "new_title": None})
        client.put(f"{BASE}/runs/{run_id}/lines", json={
            "kind": "customer", "customer_value_key": "",
            "value_key": "CUSTOMER SECRETNAME SDN BHD", "action": "create",
            "target_id": None, "new_title": None})  # refused: a 422 path
        client.post(f"{BASE}/runs/{run_id}/preview")

    leaked = [r.getMessage() for r in caplog.records if "SECRETNAME" in r.getMessage().upper()]
    assert leaked == []
