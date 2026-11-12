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


def _created_id(client, content, name="SO SUMMARY 2026.xlsx"):
    response = _upload(client, content, name=name)
    assert response.status_code == 201, response.text
    return response.json()["id"]


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

    mine = new_run(w, _small_book())
    w.db.commit()

    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    # Control: the route exists and answers for this company's own run, so the 404 below
    # is the scope refusal and not a missing route.
    control = _call(client, method, path, mine.id)
    assert control.status_code != 404, (method, path, control.text)
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
    run_id = _created_id(client, _small_book())
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
    run_id = _created_id(client, _small_book())
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
    body = todo.json()
    todo_rows = (body.get("items", body.get("data")) if isinstance(body, dict) else body)
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
        run_id = _created_id(client, content)
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


# --------------------------------------------------------------------------- round 2:
# server paging, sort and search (owner standing rules: every grid column sorts on the
# SERVER and the order holds on page 2; every list has search; a "to do" count equals the
# rows its filter shows).


def _norm(value):
    if value is None or value == "":
        return None
    return value.lower() if isinstance(value, str) else value


def _assert_sorted(values, desc):
    """Non-blank values monotonic in the asked direction; blanks grouped at one end."""
    vals = [_norm(v) for v in values]
    present = [v for v in vals if v is not None]
    assert present == sorted(present, reverse=desc), values
    blanks = [i for i, v in enumerate(vals) if v is None]
    if blanks:
        n = len(blanks)
        assert blanks in (list(range(n)), list(range(len(vals) - n, len(vals)))), values


def _assert_grouped(values):
    seen = []
    for v in values:
        if not seen or seen[-1] != v:
            assert v not in seen, values
            seen.append(v)
    return seen


def _paged(client, url, params, *, limit, key, ident):
    """(full list, page 1, page 2): page 1 + page 2 must be the first 2*limit of the full
    list, in the same order."""
    full = client.get(url, params={**params, "page": 1, "limit": 200})
    assert full.status_code == 200, full.text
    p1 = client.get(url, params={**params, "page": 1, "limit": limit})
    p2 = client.get(url, params={**params, "page": 2, "limit": limit})
    assert p1.status_code == 200 and p2.status_code == 200, (p1.text, p2.text)
    full_items, i1, i2 = full.json()[key], p1.json()[key], p2.json()[key]
    assert len(full_items) > 2 * limit - 1, "seed more rows than one page"
    assert len(i1) == limit
    assert [ident(x) for x in i1 + i2] == [ident(x) for x in full_items[: len(i1) + len(i2)]]
    assert p1.json()["total"] == full.json()["total"] == len(full_items)
    return full_items, i1, i2


def _lines_book():
    rows, n = [], 0
    for i in range(1, 9):
        for _ in range((i % 3) + 1):
            n += 1
            rows.append(row(f"PS26-{n:04d}", customer=f"CUSTOMER {i:03d} SDN BHD",
                            project_name=f"PROJECT {9 - i:03d}"))
    return make_book({"JAN'26": rows})


@pytest.fixture
def lines_world(world, api_client):
    from app.services.project_import import service

    w = world
    run = new_run(w, _lines_book())
    for i in (2, 5, 7):  # some lines set, so status and set_at vary
        service.set_line(w.db, run, kind="customer", value_key=f"CUSTOMER {i:03d} SDN BHD",
                         action="skip", user_id=w.admin_id)
    service.set_line(w.db, run, kind="project", customer_value_key="CUSTOMER 003 SDN BHD",
                     value_key="PROJECT 006", action="skip", user_id=w.admin_id)
    w.db.commit()
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    return w, run, client, f"{BASE}/runs/{run.id}/lines"


def test_ac_pi_46_lines_are_paged_as_items_and_total(lines_world):
    _w, _run, client, url = lines_world

    pages = [client.get(url, params={"kind": "customer", "page": p, "limit": 3}) for p in (1, 2, 3)]

    for r in pages:
        assert r.status_code == 200, r.text
        assert set(r.json()) >= {"items", "total"}
    assert [len(r.json()["items"]) for r in pages] == [3, 3, 2]
    assert {r.json()["total"] for r in pages} == {8}
    keys = [l["value_key"] for r in pages for l in r.json()["items"]]
    assert len(set(keys)) == 8
    line = pages[0].json()["items"][0]
    for field in ("kind", "customer_value_key", "value_key", "value_text", "customer_text",
                  "rows", "action", "target_id", "target_label", "new_title", "source",
                  "set_by_name", "set_at", "status"):
        assert field in line, field


@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("kind,sort", [
    ("customer", "value_text"), ("customer", "rows"), ("customer", "set_at"),
    ("project", "value_text"), ("project", "customer_text"), ("project", "rows"),
])
def test_ac_pi_46_lines_sort_on_the_server_and_hold_across_pages(lines_world, kind, sort,
                                                                 direction):
    _w, _run, client, url = lines_world

    full, _p1, _p2 = _paged(
        client, url, {"kind": kind, "sort": sort, "dir": direction}, limit=3, key="items",
        ident=lambda l: (l["customer_value_key"], l["value_key"]),
    )

    _assert_sorted([l[sort] for l in full], direction == "desc")


def test_ac_pi_46_lines_sort_by_status_groups_and_flips_with_dir(lines_world):
    _w, _run, client, url = lines_world

    groups = {}
    for direction in ("asc", "desc"):
        full, _p1, _p2 = _paged(
            client, url, {"kind": "customer", "sort": "status", "dir": direction}, limit=3,
            key="items", ident=lambda l: l["value_key"],
        )
        groups[direction] = _assert_grouped([l["status"] for l in full])
    assert sorted(groups["asc"]) == ["set", "todo"]
    assert groups["desc"] == list(reversed(groups["asc"]))


def test_ac_pi_46_lines_search_matches_value_or_customer_text_and_links_nothing(lines_world):
    from app.models.project_import import ProjectImportValueMap

    w, _run, client, url = lines_world
    maps_before = w.db.query(ProjectImportValueMap).count()

    customers = client.get(url, params={"kind": "customer", "query": "003 sdn"}).json()
    assert [l["value_key"] for l in customers["items"]] == ["CUSTOMER 003 SDN BHD"]
    assert customers["total"] == 1
    # "005" is CUSTOMER 005's pair (customer_text) and PROJECT 005, under CUSTOMER 004.
    projects = client.get(url, params={"kind": "project", "query": "005"}).json()
    assert sorted((l["customer_value_key"], l["value_key"]) for l in projects["items"]) == [
        ("CUSTOMER 004 SDN BHD", "PROJECT 005"),
        ("CUSTOMER 005 SDN BHD", "PROJECT 004"),
    ]
    assert projects["total"] == 2
    # Searching is reading: no line is set by it.
    assert all(l["status"] == "todo" for l in projects["items"])
    assert w.db.query(ProjectImportValueMap).count() == maps_before


def test_ac_pi_46_todo_total_equals_the_summary_count_per_kind(lines_world):
    _w, _run, client, url = lines_world

    summary = client.get(f"{url}/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert set(body) == {"customer", "project", "developer", "person"}
    for kind in ("customer", "project", "developer", "person"):
        todo = client.get(url, params={"kind": kind, "status": "todo", "limit": 1}).json()
        every = client.get(url, params={"kind": kind, "limit": 1}).json()
        assert body[kind]["todo"] == todo["total"], kind
        assert body[kind]["total"] == every["total"], kind
    assert body["customer"] == {"total": 8, "todo": 5}
    assert body["project"] == {"total": 8, "todo": 7}
    assert body["developer"] == {"total": 0, "todo": 0}


# --------------------------------------------------------------------------- rows


@pytest.fixture
def rows_world(world, api_client):
    from datetime import datetime

    from app.services.project_import import service

    w = world
    apr = [row(f"PS26-{472 + i:04d}", customer=f"CUSTOMER {10 - i:03d} SDN BHD",
               project_name=None if i % 3 == 0 else f"PROJECT {i:03d}",
               po_number=f"PO-{(i * 7) % 10:02d}{i}", po_date=datetime(2026, 4, 1 + (i * 5) % 27),
               po_value="-" if i == 4 else 100)
           for i in range(6)]
    may = [row(f"PS26-{688 + i:04d}", customer=f"CUSTOMER {20 + i:03d} SDN BHD",
               project_name=f"PROJECT {30 - i:03d}", po_number=f"PO-{i}{(i * 3) % 10}",
               po_date=None if i == 2 else datetime(2026, 5, 2 + i))
           for i in range(5)]
    may.append({"ps_number": "PS26-0693"})  # placeholder
    run = new_run(w, make_book({"APR'26": apr, "MAY'26": may}))
    service.preview(w.db, run, user_id=w.admin_id)
    w.db.commit()
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    return w, run, client, f"{BASE}/runs/{run.id}/rows"


@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("sort", ["sheet", "row_number", "ps_number", "customer", "project",
                                  "po_number", "po_date", "outcome"])
def test_ac_pi_47_rows_sort_on_the_server_and_hold_across_pages(rows_world, sort, direction):
    _w, _run, client, url = rows_world

    full, _p1, _p2 = _paged(
        client, url, {"sort": sort, "dir": direction}, limit=4, key="data",
        ident=lambda r: (r["sheet"], r["row_number"]),
    )

    assert len(full) == 12
    _assert_sorted([r[sort] for r in full], direction == "desc")


def test_ac_pi_47_rows_sort_flips_with_dir(rows_world):
    _w, _run, client, url = rows_world

    asc = client.get(url, params={"sort": "ps_number", "dir": "asc", "limit": 200}).json()["data"]
    desc = client.get(url, params={"sort": "ps_number", "dir": "desc", "limit": 200}).json()["data"]

    assert [r["ps_number"] for r in asc] == list(reversed([r["ps_number"] for r in desc]))
    assert asc[0]["ps_number"] == "PS26-0472"


# --------------------------------------------------------------------------- runs


@pytest.fixture
def runs_world(world, api_client):
    from app.services.project_import import service

    w = world
    users = [w.admin_id, seed_user_named(w, "ZZT-PIM Bella"), seed_user_named(w, "ZZT-PIM Carl")]
    made = []
    for i in range(7):
        rows_ = [row(f"PS26-{n:04d}", customer=f"CUSTOMER {n:03d} SDN BHD",
                     project_name=None if n % 2 else "PROJECT 1")
                 for n in range(1, 2 + (i * 3) % 7)]
        run = new_run(w, make_book({"JAN'26": rows_}), filename=f"run {chr(97 + (i * 5) % 7)}.xlsx",
                      user_id=users[i % 3])
        if i % 2:
            service.preview(w.db, run, user_id=users[i % 3])
        made.append(run)
    w.db.commit()
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    return w, made, users, client


def seed_user_named(w, name):
    from ._project_import_support import seed_user

    return seed_user(w.db, name)


@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("sort", ["run_no", "filename", "uploaded_by", "uploaded_at", "status",
                                  "rows", "created", "skipped", "to_review"])
def test_ac_pi_43_runs_sort_on_the_server_and_hold_across_pages(runs_world, sort, direction):
    _w, _made, _users, client = runs_world

    full, _p1, _p2 = _paged(
        client, f"{BASE}/runs", {"sort": sort, "dir": direction}, limit=3, key="data",
        ident=lambda r: r["id"],
    )

    assert len(full) == 7
    _assert_sorted([r[sort] for r in full], direction == "desc")


def test_ac_pi_43_runs_sort_by_run_no_flips_with_dir(runs_world):
    _w, _made, _users, client = runs_world

    asc = client.get(f"{BASE}/runs", params={"sort": "run_no", "dir": "asc"}).json()["data"]
    desc = client.get(f"{BASE}/runs", params={"sort": "run_no", "dir": "desc"}).json()["data"]

    assert [r["run_no"] for r in asc] == [f"PIM-{n:04d}" for n in range(1, 8)]
    assert [r["run_no"] for r in desc] == [f"PIM-{n:04d}" for n in range(7, 0, -1)]


def test_ac_pi_43_status_and_uploaded_by_filters_are_multi_select_and_combine(runs_world):
    _w, made, users, client = runs_world
    url = f"{BASE}/runs"

    def ids(params):
        r = client.get(url, params=params)
        assert r.status_code == 200, r.text
        return {x["id"] for x in r.json()["data"]}

    status_of = {str(r.id): ("previewed" if i % 2 else "draft") for i, r in enumerate(made)}
    user_of = {str(r.id): users[i % 3] for i, r in enumerate(made)}

    assert ids({"status": ["draft", "previewed"]}) == set(status_of)
    assert ids({"status": "previewed"}) == {k for k, v in status_of.items() if v == "previewed"}
    two = {users[0], users[1]}
    assert ids({"uploaded_by": list(two)}) == {k for k, v in user_of.items() if v in two}
    both = ids({"status": "previewed", "uploaded_by": list(two)})
    assert both == {k for k in status_of if status_of[k] == "previewed" and user_of[k] in two}
    assert both and both != ids({"status": "previewed"})


# --------------------------------------------------------------------------- round 3:
# the run's History (owner rule: every tracked action on a record shows in its History:
# who, when, plain action) and plain labels carried by the API.
#
# History is read through the endpoint the shared AuditTrail calls:
#   GET /api/v1/audit/logs?entity_type=<type>&entity_id=<run id>
# READING (lead to confirm): the run's entity type is `project_import_run`, the same word the
# record action `project_import_run.revert` uses, and `projects.import.view` reads it on the
# per-record path. Mapping the generic `import_jobs` type instead would open every import
# job's history to an import-view holder.
# The plain action word is the entry's `event` or `description` (either carries it).

import re as _re

HISTORY_URL = "/api/v1/audit/logs"
HISTORY_ENTITY_TYPE = "project_import_run"
_UUID = _re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", _re.I)


def _history_text(entry) -> str:
    return " ".join(str(entry.get(k) or "") for k in ("event", "description")).strip()


@pytest.fixture
def history_world(world, api_client, monkeypatch):
    from app.api.v1.audit import audit_logs
    from app.services.project_import import service

    w = world
    # The content tests read as an audit admin, so a missing entry is reported as missing
    # rather than hidden behind the per-record permission (tested on its own below).
    real_is_admin = audit_logs._is_audit_admin
    w.extra["admin_reader"] = {"on": True}
    monkeypatch.setattr(
        audit_logs, "_is_audit_admin",
        lambda db, uid: True if w.extra["admin_reader"]["on"] else real_is_admin(db, uid),
    )
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    run_id = _created_id(client, _small_book())
    assert client.put(f"{BASE}/runs/{run_id}/columns",
                      json={"sheets": ["JAN'26"], "columns": HEADER_BY_FIELD}).status_code in (200, 204)
    linked = client.put(f"{BASE}/runs/{run_id}/lines", json={
        "kind": "customer", "customer_value_key": "", "value_key": "CUSTOMER 001 SDN BHD",
        "action": "link", "target_id": customer.id, "new_title": None})
    assert linked.status_code == 200, linked.text
    bulk = client.put(f"{BASE}/runs/{run_id}/lines/bulk", json={
        "kind": "project",
        "keys": [["CUSTOMER 001 SDN BHD", "PROJECT 001 SAMPLE NAME"]],
        "action": "create", "target_id": None, "new_title": "ZZT HISTORY TOWER"})
    assert bulk.status_code == 200, bulk.text
    preview = client.post(f"{BASE}/runs/{run_id}/preview")
    assert preview.status_code == 200, preview.text
    from app.models.job import ImportJob

    run = w.db.get(ImportJob, run_id)
    service.apply(w.db, run, user_id=w.admin_id)
    service.revert(w.db, run, user_id=w.admin_id)
    w.db.commit()
    return w, client, run_id


def _history(client, run_id):
    response = client.get(HISTORY_URL, params={"entity_type": HISTORY_ENTITY_TYPE,
                                               "entity_id": run_id, "limit": 200})
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.parametrize("word", ["Uploaded", "Columns saved", "Value linked", "Previewed",
                                  "Imported", "Reverted"])
def test_history_every_action_on_the_run_has_one_entry(history_world, word):
    _w, client, run_id = history_world

    entries = _history(client, run_id)

    matching = [e for e in entries if _re.search(rf"\b{word}\b", _history_text(e), _re.I)]
    assert len(matching) == 1, (word, [_history_text(e) for e in entries])


def test_history_the_bulk_set_is_recorded(history_world):
    _w, client, run_id = history_world

    texts = [_history_text(e) for e in _history(client, run_id)]

    assert any(_re.search(r"\bvalues?\b.*\b(set|created|create|linked|skipped)\b", t, _re.I)
               and not _re.search(r"\bValue linked\b", t) for t in texts), texts


def test_history_names_the_acting_user_and_when(history_world):
    w, client, run_id = history_world

    entries = _history(client, run_id)

    assert len(entries) >= 7
    for e in entries:
        assert e["user_id"] == w.admin_id, e
        assert e["user_display_name"] == f"{MARKER} Importer", e
        assert e["changed_at"]
        assert e["entity_id"] == run_id


def test_history_action_text_carries_no_uuid_and_no_customer_name(history_world):
    _w, client, run_id = history_world

    entries = _history(client, run_id)
    assert len(entries) >= 7, "no history to check"
    for e in entries:
        text = _history_text(e)
        assert text, e
        assert not _UUID.search(text), text
        assert "CUSTOMER 001" not in text.upper(), text
        assert "ZZT-PIM DEALER" not in text.upper(), text


def test_history_reads_with_the_import_view_permission_only(history_world, api_client):
    w, _client, run_id = history_world
    w.extra["admin_reader"]["on"] = False  # the per-record path, not the audit admin
    reader = api_client(w.db, w.admin_id, w.company_id, {VIEW})

    response = reader.get(HISTORY_URL, params={"entity_type": HISTORY_ENTITY_TYPE,
                                               "entity_id": run_id})

    assert response.status_code == 200, response.text
    assert response.json()["data"]


# --------------------------------------------------------------------------- labels
#
# Shape (documented here, the coder matches it):
# - every report row (GET .../rows, and the `rows` of the preview / import report) carries
#   `labels`: [label_for(code) for code in codes], same order and length as `codes`;
# - the run detail (GET /runs/{id}) carries `code_labels`: {code: label_for(code)} for every
#   code in preview_codes and result_codes, so the frontend keeps no copy of the label table.


def test_labels_report_rows_carry_a_plain_label_per_code(world, api_client):
    from app.services import import_outcome_codes as oc
    from app.services.project_import import service

    w = world
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    run_id = _created_id(client, make_book({"JAN'26": [
        row("PS26-0001"),
        row("PS26-0002", project_name=None),
        row("PS26-0003", po_value="-"),
    ]}))
    client.put(f"{BASE}/runs/{run_id}/columns",
               json={"sheets": ["JAN'26"], "columns": HEADER_BY_FIELD})

    preview = client.post(f"{BASE}/runs/{run_id}/preview")
    assert preview.status_code == 200, preview.text
    rows = client.get(f"{BASE}/runs/{run_id}/rows", params={"limit": 50}).json()["data"]

    assert len(rows) == 3
    for r in rows:
        assert "labels" in r, r
        assert r["labels"] == [oc.label_for(c) for c in r["codes"]], r
    from app.models.job import ImportJob

    report = service.preview(w.db, w.db.get(ImportJob, run_id), user_id=w.admin_id)
    for r in report["rows"]:
        assert r["labels"] == [oc.label_for(c) for c in r["codes"]], r


def test_labels_run_detail_carries_code_labels_for_preview_and_result_codes(world, api_client):
    from app.services import import_outcome_codes as oc
    from app.services.project_import import service
    from app.models.job import ImportJob

    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    run_id = _created_id(client, _small_book())
    client.put(f"{BASE}/runs/{run_id}/columns",
               json={"sheets": ["JAN'26"], "columns": HEADER_BY_FIELD})
    client.put(f"{BASE}/runs/{run_id}/lines", json={
        "kind": "customer", "customer_value_key": "", "value_key": "CUSTOMER 001 SDN BHD",
        "action": "link", "target_id": customer.id, "new_title": None})
    client.put(f"{BASE}/runs/{run_id}/lines/bulk", json={
        "kind": "project", "keys": [["CUSTOMER 001 SDN BHD", "PROJECT 001 SAMPLE NAME"]],
        "action": "create", "target_id": None, "new_title": "ZZT LABEL TOWER"})
    client.post(f"{BASE}/runs/{run_id}/preview")
    service.apply(w.db, w.db.get(ImportJob, run_id), user_id=w.admin_id)
    w.db.commit()

    body = client.get(f"{BASE}/runs/{run_id}").json()

    codes = set(body.get("preview_codes") or {}) | set(body.get("result_codes") or {})
    assert codes, body
    assert "code_labels" in body, sorted(body)
    for c in codes:
        assert body["code_labels"].get(c) == oc.label_for(c), c
        assert "_" not in body["code_labels"][c], c
