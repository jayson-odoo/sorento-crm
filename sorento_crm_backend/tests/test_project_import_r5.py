"""Project import, fix round 5: the security review and code review findings (RED).

Sources: crew/state/files/project-migration/security-1.md (SEC-*) and review-1.md (REV-*),
line numbers at 59f5eded. Postgres via `blank_session`; everything seeded here.

Shapes this file pins (the coder matches them):
- revert keeps a record that has ANY child row the run did not create, and lists it under
  `kept` with reason `revert_kept_edited` (SEC-B1);
- revert restores only the lines the run itself rewrote (create -> link); any other line
  whose target the revert removed is deleted, so it reads To do (REV-RB1);
- an upload whose uncompressed size / compression ratio is over the cap, or whose sheet
  declares a huge `<dimension>`, is refused with 422 and a plain message, quickly (SEC-S1);
- a person target is an ACTIVE user with a grant in the run's company (SEC-S2/REV-M6);
- the route commits before it enqueues; a redelivered job on an imported run changes
  nothing; a failure resets the phase only from `importing`, and the run detail then
  carries `error` (a plain message) with phase `previewed` (SEC-S3, REV-minor1/2);
- a parked revert re-checks `projects.import.run` of the parking user at commit (SEC-N1);
- a column choice must name a heading present in the run's file, or `ignore` (SEC-N2);
- a bulk "create" on project lines with no common title gives each line its own title
  (REV-M5);
- a folded value longer than 255 characters never gives a 500 (REV-minor6);
- column N "SO498152 refer PS26-0022" links the SO and keeps the text as an SO note; an
  unreadable text PO date imports with no date and flag `po_date_unreadable` (REV-minor7);
- report rows carry `blocking_kind`; the run detail carries `field_labels` (REV-minor8);
- rows sort by `reason` (REV-minor4); notes dates go through `fmt_date` (REV-M7).
"""
from __future__ import annotations

import io
import re
import time
import zipfile
from datetime import date, datetime

import pytest

from tests.fixtures.project_import.build_so_summary import FIELDS, HEADER_BY_FIELD

from ._project_import_support import (  # noqa: F401  fixtures
    MARKER,
    api_client,
    grant,
    make_book,
    memory_storage,
    new_run,
    row,
    seed_company,
    seed_core_so,
    seed_customer,
    seed_party,
    seed_project,
    seed_user,
    snapshot,
    world,
)
from .test_project_import_run import C1, P1, _by_ps, _map, _pos, _projects, _simple_world

BASE = "/api/v1/projects/import"
VIEW = "projects.import.view"
RUN = "projects.import.run"
BOTH = {VIEW, RUN}
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _svc():
    from app.services.project_import import service

    return service


def _maps(w, **filters):
    from app.models.project_import import ProjectImportValueMap

    q = w.db.query(ProjectImportValueMap)
    for k, v in filters.items():
        q = q.filter(getattr(ProjectImportValueMap, k) == v)
    return q.all()


# --------------------------------------------------------------------------- SEC-B1


def _imported_with_so(w):
    from app.models.project_so import ProjectSalesOrder

    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    core = seed_core_so(w.db, w.company_id, "SO490001", customer)
    w.db.commit()
    run, _ = _simple_world(w, [row("PS26-0001", so_number="SO490001")], customer=customer)
    _svc().apply(w.db, run, user_id=w.admin_id)
    w.db.commit()
    project = _projects(w)[0]
    po = _pos(w, "PS26-0001")[0]
    pso = w.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.so_id == core.id).one()
    return run, project, po, pso


def _add_child(w, kind, project, po, pso):
    from app.models.project_so import OrderInquiry, ProjectPOVersion
    from app.models.projects import ProjectTask

    if kind == "task":
        child = ProjectTask(company_id=w.company_id, project_id=project.id, name="ZZT follow up")
    elif kind == "po_version":
        child = ProjectPOVersion(company_id=w.company_id, purchase_order_id=po.id, version_no=1)
    else:
        child = OrderInquiry(company_id=w.company_id, inquiry_no="ZZTOI0001",
                             project_sales_order_id=pso.id)
    w.db.add(child)
    w.db.commit()
    return type(child), child.id


@pytest.mark.parametrize("kind", ["task", "po_version", "order_inquiry"])
def test_r5_sec_b1_revert_keeps_a_record_with_a_child_the_run_did_not_create(world, kind):
    from app.models.project_so import ProjectSalesOrder
    from app.models.projects import Project, ProjectPurchaseOrder

    w = world
    run, project, po, pso = _imported_with_so(w)
    model, child_id = _add_child(w, kind, project, po, pso)
    parent = {"task": (Project, project.id), "po_version": (ProjectPurchaseOrder, po.id),
              "order_inquiry": (ProjectSalesOrder, pso.id)}[kind]

    result = _svc().revert(w.db, run, user_id=w.admin_id)
    w.db.commit()

    assert w.db.get(model, child_id) is not None, "revert deleted a record it did not create"
    assert w.db.get(*parent) is not None, "the parent of a foreign child must be kept"
    assert result["kept"], result
    assert {k["reason"] for k in result["kept"]} == {"revert_kept_edited"}
    w.db.refresh(run)
    assert run.job_metadata["phase"] == "reverted"


def test_r5_sec_b1_a_run_with_no_later_children_still_removes_everything(world):
    w = world
    before = snapshot(w.db)
    run, _project, _po, _pso = _imported_with_so(w)
    seeded = snapshot(w.db)

    result = _svc().revert(w.db, run, user_id=w.admin_id)
    w.db.commit()

    after = snapshot(w.db)
    for table in ("projects", "sales_profiles", "purchase_orders", "project_sales_orders"):
        assert after[table] == before[table], (table, before[table], seeded[table], after[table])
    assert result["kept"] == []


# --------------------------------------------------------------------------- REV-RB1


def test_r5_rev_rb1_revert_restores_only_the_lines_the_run_rewrote(world):
    w = world
    s = _svc()
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    other = seed_customer(w.db, w.company_id, f"{MARKER} DEALER TWO")
    w.db.commit()
    run1 = new_run(w, make_book({"JAN'26": [row("PS26-0001", developer="ZZT DEV R1")]}))
    _map(w, run1, customers={C1: customer.id}, projects={(C1, P1): ("create", "ZZT R1 TOWER")},
         developers={"ZZT DEV R1": ("create",)})
    s.apply(w.db, run1, user_id=w.admin_id)
    w.db.commit()
    project = _projects(w)[0]
    party = project.developer_party_id

    # A later file: a person links a different pair and developer to what run 1 created.
    run2 = new_run(w, make_book({"FEB'26": [
        row("PS26-0171", customer="CUSTOMER 002 SDN BHD", project_name="PROJECT 2",
            developer="ZZT DEV OTHER", po_date=datetime(2026, 2, 3)),
    ]}))
    s.set_line(w.db, run2, kind="customer", value_key="CUSTOMER 002 SDN BHD", action="link",
               target_id=other.id, user_id=w.admin_id)
    s.set_line(w.db, run2, kind="project", customer_value_key="CUSTOMER 002 SDN BHD",
               value_key="PROJECT 2", action="link", target_id=project.id, user_id=w.admin_id)
    s.set_line(w.db, run2, kind="developer", value_key="ZZT DEV OTHER", action="link",
               target_id=party, user_id=w.admin_id)
    w.db.commit()

    s.revert(w.db, run1, user_id=w.admin_id)
    w.db.commit()

    # Run 1's own rewritten lines go back to create (with their title).
    own = _maps(w, kind="project", value_key=P1)[0]
    assert (own.action, own.target_id, own.new_title) == ("create", None, "ZZT R1 TOWER")
    own_dev = _maps(w, kind="developer", value_key="ZZT DEV R1")[0]
    assert (own_dev.action, own_dev.target_id) == ("create", None)
    # The lines a person linked are deleted: To do, never create.
    assert _maps(w, kind="project", value_key="PROJECT 2") == []
    assert _maps(w, kind="developer", value_key="ZZT DEV OTHER") == []
    lines = {l["value_key"]: l for l in s.list_lines(w.db, run2, kind="project")}
    assert lines["PROJECT 2"]["status"] == "todo"
    assert lines["PROJECT 2"]["action"] in (None, "")
    dev = {l["value_key"]: l for l in s.list_lines(w.db, run2, kind="developer")}
    assert dev["ZZT DEV OTHER"]["status"] == "todo"
    assert dev["ZZT DEV OTHER"]["action"] != "create"


def test_r5_rev_rb1_preview_after_the_revert_answers_200(world, api_client):
    w = world
    s = _svc()
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    run1 = new_run(w, make_book({"JAN'26": [row("PS26-0001")]}))
    _map(w, run1, customers={C1: customer.id}, projects={(C1, P1): ("create", "ZZT R1 TOWER")})
    s.apply(w.db, run1, user_id=w.admin_id)
    w.db.commit()
    project = _projects(w)[0]
    run2 = new_run(w, make_book({"FEB'26": [
        row("PS26-0171", project_name="PROJECT 2", po_date=datetime(2026, 2, 3)),
    ]}))
    s.set_line(w.db, run2, kind="project", customer_value_key=C1, value_key="PROJECT 2",
               action="link", target_id=project.id, user_id=w.admin_id)
    w.db.commit()
    s.revert(w.db, run1, user_id=w.admin_id)
    w.db.commit()
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)

    response = client.post(f"{BASE}/runs/{run2.id}/preview")

    assert response.status_code == 200, response.text
    row2 = response.json()["rows"][0] if "rows" in response.json() else None
    lines = client.get(f"{BASE}/runs/{run2.id}/lines",
                       params={"kind": "project", "status": "todo"}).json()["items"]
    assert [l["value_key"] for l in lines] == ["PROJECT 2"]
    if row2:
        assert row2["outcome"] == "needs_review"


# --------------------------------------------------------------------------- SEC-S1


def _rezip(content: bytes, *, replace=None, extra=None) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(content))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if replace and info.filename in replace:
                data = replace[info.filename](data)
            dst.writestr(info.filename, data)
        if extra:
            name, size = extra
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED  # a bare ZipInfo would be STORED
            with dst.open(info, "w", force_zip64=True) as fh:
                chunk = b"\0" * (1024 * 1024)
                for _ in range(size // len(chunk)):
                    fh.write(chunk)
    return out.getvalue()


def _assert_refused_quickly(w, content, name="bomb.xlsx"):
    from app.services.error_handler import AppException

    started = time.monotonic()
    with pytest.raises(AppException) as excinfo:
        _svc().create_run(w.db, company_id=w.company_id, user_id=w.admin_id, filename=name,
                          content=content)
    elapsed = time.monotonic() - started
    assert excinfo.value.status_code == 422
    message = str(getattr(excinfo.value, "message", excinfo.value))
    assert message.strip() and "Traceback" not in message
    assert elapsed < 20, f"took {elapsed:.1f}s"


def test_r5_sec_s1_an_upload_over_the_uncompressed_cap_is_refused(world):
    content = _rezip(make_book({"JAN'26": [row("PS26-0001")]}),
                     extra=("xl/media/padding.bin", 400 * 1024 * 1024))
    assert len(content) < 10 * 1024 * 1024  # under the compressed limit: only a ratio cap catches it
    _assert_refused_quickly(world, content)


def test_r5_sec_s1_a_sheet_declaring_a_huge_dimension_is_refused(world):
    def widen(xml: bytes) -> bytes:
        text = xml.decode("utf-8")
        text, n = re.subn(r'<dimension ref="[^"]*"\s*/>', '<dimension ref="A1:XFD1048576"/>', text)
        if not n:
            text = text.replace("<sheetData", '<dimension ref="A1:XFD1048576"/><sheetData', 1)
        return text.encode("utf-8")

    content = _rezip(make_book({"JAN'26": [row("PS26-0001")]}),
                     replace={"xl/worksheets/sheet1.xml": widen})
    _assert_refused_quickly(world, content)


# --------------------------------------------------------------------------- SEC-S2 / REV-M6


@pytest.mark.parametrize("case", ["inactive", "no_grant", "other_company"])
def test_r5_sec_s2_a_person_target_must_be_an_active_user_granted_in_the_run_company(world, case):
    from app.services.error_handler import AppException

    w = world
    if case == "inactive":
        target = seed_user(w.db, f"{MARKER} SECRETPERSON", w.company_id, active=False)
    elif case == "no_grant":
        target = seed_user(w.db, f"{MARKER} SECRETPERSON")
    else:
        other = seed_company(w.db, "Other")
        target = seed_user(w.db, f"{MARKER} SECRETPERSON", other)
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [row("PS26-0001")]}))

    with pytest.raises(AppException) as excinfo:
        _svc().set_line(w.db, run, kind="person", value_key="ALVIN", action="link",
                        target_id=target, user_id=w.admin_id)
    assert excinfo.value.status_code == 422
    assert "SECRETPERSON" not in str(getattr(excinfo.value, "message", excinfo.value)).upper()
    assert _maps(w, kind="person") == []


def test_r5_sec_s2_an_active_granted_user_is_accepted(world):
    w = world
    person = seed_user(w.db, f"{MARKER} Alvin", w.company_id)
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [row("PS26-0001")]}))

    out = _svc().set_line(w.db, run, kind="person", value_key="ALVIN", action="link",
                          target_id=person, user_id=w.admin_id)
    assert out["status"] == "set"


def test_r5_sec_s2_target_label_never_shows_another_companys_user(world):
    from app.models.project_import import ProjectImportValueMap

    w = world
    other = seed_company(w.db, "Other")
    foreign = seed_user(w.db, f"{MARKER} SECRETPERSON", other)
    w.db.add(ProjectImportValueMap(
        company_id=w.company_id, kind="person", customer_value_key="", value_key="ALVIN",
        value_text="ALVIN", action="link", target_id=foreign, set_by_user_id=w.admin_id,
        set_at=datetime(2026, 11, 1)))
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [row("PS26-0001")]}))

    line = {l["value_key"]: l for l in _svc().list_lines(w.db, run, kind="person")}["ALVIN"]
    assert "SECRETPERSON" not in str(line.get("target_label") or "").upper()
    assert "@zzt.test" not in str(line.get("target_label") or "")


# --------------------------------------------------------------------------- SEC-S3 / REV-minor1/2


def _task_on(w, monkeypatch):
    from app.tasks import import_tasks

    monkeypatch.setattr(w.db, "close", lambda: None, raising=False)
    monkeypatch.setattr(import_tasks, "SessionLocal", lambda: w.db)
    return import_tasks.process_project_import


def test_r5_sec_s3_the_route_commits_before_it_enqueues(world, api_client, monkeypatch):
    from app.models.job import ImportJob

    w = world
    run, _ = _simple_world(w, [row("PS26-0001")])
    w.db.commit()
    events = []
    real_commit = w.db.commit

    def commit():
        events.append("commit")
        return real_commit()

    def fake_enqueue(func, *args, queue_name="imports", **kwargs):
        meta = dict(w.db.get(ImportJob, run.id).job_metadata or {})
        events.append(("enqueue", meta.get("phase"), meta.get("started_by"), bool(w.db.dirty)))
        return type("J", (), {"id": "rq-r5"})()

    monkeypatch.setattr(w.db, "commit", commit)
    monkeypatch.setattr(_svc(), "enqueue_job", fake_enqueue, raising=False)
    from app.services import queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", fake_enqueue)
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)

    response = client.post(f"{BASE}/runs/{run.id}/import")

    assert response.status_code == 202, response.text
    enq = [i for i, e in enumerate(events) if isinstance(e, tuple)]
    assert len(enq) == 1, events
    assert "commit" in events[: enq[0]], f"enqueue ran before any commit: {events}"
    _, phase, started_by, dirty = events[enq[0]]
    assert phase == "importing"
    assert started_by == w.admin_id
    assert dirty is False


def test_r5_sec_s3_a_redelivered_job_on_an_imported_run_changes_nothing(world, monkeypatch):
    from app.models.job import ImportJobRow

    w = world
    run, _ = _simple_world(w, [row("PS26-0001")])
    _svc().apply(w.db, run, user_id=w.admin_id)
    w.db.commit()
    ledger = (w.db.query(ImportJobRow)
              .filter(ImportJobRow.import_job_id == run.id, ImportJobRow.entity_id.isnot(None))
              .count())
    before = snapshot(w.db)
    task = _task_on(w, monkeypatch)

    task(str(run.id))

    w.db.refresh(run)
    assert run.job_metadata["phase"] == "imported"
    assert (w.db.query(ImportJobRow)
            .filter(ImportJobRow.import_job_id == run.id, ImportJobRow.entity_id.isnot(None))
            .count()) == ledger > 0
    assert snapshot(w.db)["projects"] == before["projects"]
    result = _svc().revert(w.db, run, user_id=w.admin_id)
    assert sum(result["removed"].values()) >= 3
    assert _projects(w) == []


def test_r5_sec_s3_a_failure_does_not_reset_an_imported_run(world, monkeypatch):
    w = world
    run, _ = _simple_world(w, [row("PS26-0001")])
    _svc().apply(w.db, run, user_id=w.admin_id)
    w.db.commit()
    task = _task_on(w, monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("worker died")

    monkeypatch.setattr(_svc(), "apply", boom)
    task(str(run.id))

    w.db.refresh(run)
    assert run.job_metadata["phase"] == "imported"


def test_r5_rev_minor1_a_failed_import_shows_its_error_and_goes_back_to_preview(
    world, api_client, monkeypatch
):
    w = world
    run, _ = _simple_world(w, [row("PS26-0001")])
    _svc().preview(w.db, run, user_id=w.admin_id)
    w.db.commit()
    monkeypatch.setattr(_svc(), "enqueue_job",
                        lambda *a, **k: type("J", (), {"id": "rq-r5"})(), raising=False)
    from app.services import queue_service

    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: type("J", (), {"id": "rq-r5"})())
    _svc().start_import(w.db, run, user_id=w.admin_id)
    w.db.commit()
    task = _task_on(w, monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("CUSTOMER 001 SDN BHD exploded")

    monkeypatch.setattr(_svc(), "apply", boom)
    task(str(run.id))
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)

    body = client.get(f"{BASE}/runs/{run.id}").json()

    assert body["status"] == "previewed"
    assert body.get("error"), sorted(body)
    assert "RuntimeError" not in body["error"] and "Traceback" not in body["error"]
    assert "CUSTOMER 001" not in body["error"]


# --------------------------------------------------------------------------- SEC-N1


def test_r5_sec_n1_a_parked_revert_rechecks_the_permission_at_commit(world, monkeypatch):
    from datetime import timedelta

    from app.models.sla import FORM_ACTION_CHANNEL_UI, FORM_ACTION_FAILED, SlaFormAction
    from app.services.form_action_service import FormActionService

    w = world
    run, _ = _simple_world(w, [row("PS26-0001")])
    _svc().apply(w.db, run, user_id=w.admin_id)
    w.db.commit()
    grant(monkeypatch, BOTH)
    FormActionService(w.db).dispatch(
        action_key="project_import_run.revert", entity_type="project_import_run",
        entity_id=str(run.id), payload={"entity_id": str(run.id)}, actor_id=w.admin_id,
        channel=FORM_ACTION_CHANNEL_UI, grace_seconds=10,
    )
    parked = (w.db.query(SlaFormAction)
              .filter(SlaFormAction.action_key == "project_import_run.revert").one())
    parked.commit_at = datetime.utcnow() - timedelta(minutes=1)
    w.db.commit()

    grant(monkeypatch, {VIEW})  # the parking user lost projects.import.run
    FormActionService(w.db).commit_due()

    w.db.refresh(run)
    w.db.refresh(parked)
    assert run.job_metadata["phase"] == "imported"
    assert len(_projects(w)) == 1
    assert parked.status == FORM_ACTION_FAILED


# --------------------------------------------------------------------------- SEC-N2


def test_r5_sec_n2_a_column_choice_must_name_a_heading_in_the_file(world, api_client):
    from app.models.import_alias import ImportFieldAlias

    w = world
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    created = client.post(f"{BASE}/runs", files={"file": (
        "small.xlsx", make_book({"JAN'26": [row("PS26-0001")]}),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]

    response = client.put(f"{BASE}/runs/{run_id}/columns", json={
        "sheets": ["JAN'26"], "columns": {"customer": "ZZT NOT A HEADING IN THIS FILE"}})

    assert response.status_code == 422, response.text
    assert (w.db.query(ImportFieldAlias)
            .filter(ImportFieldAlias.alias.ilike("%NOT A HEADING%")).count()) == 0
    ok = client.put(f"{BASE}/runs/{run_id}/columns",
                    json={"sheets": ["JAN'26"], "columns": {"remarks": "ignore"}})
    assert ok.status_code in (200, 204), ok.text


# --------------------------------------------------------------------------- REV-M5


def test_r5_rev_m5_bulk_create_without_a_common_title_makes_one_project_per_line(world):
    w = world
    s = _svc()
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    names = ["TOWER ALPHA", "TOWER BETA", "TOWER GAMMA"]
    run = new_run(w, make_book({"JAN'26": [
        row(f"PS26-{i + 1:04d}", project_name=n) for i, n in enumerate(names)]}))
    _map(w, run, customers={C1: customer.id})

    s.bulk_set(w.db, run, kind="project", keys=[(C1, n) for n in names], action="create",
               new_title=None, user_id=w.admin_id)
    w.db.commit()
    s.apply(w.db, run, user_id=w.admin_id)

    assert sorted(p.title for p in _projects(w)) == names


def test_r5_rev_m5_an_explicit_common_title_still_makes_one_project(world):
    w = world
    s = _svc()
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [
        row("PS26-0001", project_name="TOWER ALPHA"), row("PS26-0002", project_name="TOWER A")]}))
    _map(w, run, customers={C1: customer.id})

    s.bulk_set(w.db, run, kind="project", keys=[(C1, "TOWER ALPHA"), (C1, "TOWER A")],
               action="create", new_title="ZZT ONE TOWER", user_id=w.admin_id)
    w.db.commit()
    s.apply(w.db, run, user_id=w.admin_id)

    assert [p.title for p in _projects(w)] == ["ZZT ONE TOWER"]


# --------------------------------------------------------------------------- REV-minor6


def test_r5_rev_minor6_a_value_longer_than_255_never_gives_a_500(world, api_client):
    w = world
    long_name = "CUSTOMER " + "X" * 300 + " SDN BHD"
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    created = client.post(f"{BASE}/runs", files={"file": (
        "long.xlsx", make_book({"JAN'26": [row("PS26-0001", customer=long_name)]}),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]
    client.put(f"{BASE}/runs/{run_id}/columns",
               json={"sheets": ["JAN'26"], "columns": HEADER_BY_FIELD})

    lines = client.get(f"{BASE}/runs/{run_id}/lines", params={"kind": "customer"})
    assert lines.status_code == 200, lines.text
    response = client.put(f"{BASE}/runs/{run_id}/lines", json={
        "kind": "customer", "customer_value_key": "", "value_key": long_name.upper(),
        "action": "skip", "target_id": None, "new_title": None})

    assert response.status_code in (200, 422), response.text
    if response.status_code == 422:
        assert "Traceback" not in response.text and "psycopg" not in response.text.lower()


# --------------------------------------------------------------------------- REV-minor7


def test_r5_rev_minor7_an_so_cell_with_text_links_the_so_and_keeps_the_text(world):
    from app.models.project_so import ProjectSalesOrder

    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    core = seed_core_so(w.db, w.company_id, "SO498152", customer)
    w.db.commit()
    run, _ = _simple_world(w, [row("PS26-0001", so_number="SO498152 refer PS26-0022")],
                           customer=customer)

    _svc().apply(w.db, run, user_id=w.admin_id)

    pso = w.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.so_id == core.id).one()
    po = _pos(w, "PS26-0001")[0]
    assert pso.purchase_order_id == po.id
    notes = (po.notes or "").splitlines()
    assert any(l.startswith("SO note:") and "refer PS26-0022" in l for l in notes), notes


def test_r5_rev_minor7_an_unreadable_text_po_date_is_flagged(world):
    from app.services import import_outcome_codes as oc

    w = world
    run, _ = _simple_world(w, [row("PS26-0001", po_date="31/02/2026 TBC")])

    report = _svc().apply(w.db, run, user_id=w.admin_id)

    r = _by_ps(report)["PS26-0001"]
    assert r["outcome"] == "created"
    assert "po_date_unreadable" in r["codes"]
    assert _pos(w, "PS26-0001")[0].po_date is None
    assert "po_date_unreadable" in oc.LABELS
    assert "_" not in oc.label_for("po_date_unreadable")


# --------------------------------------------------------------------------- REV-minor8


def test_r5_rev_minor8_report_rows_carry_the_blocking_kind(world, api_client):
    w = world
    a = seed_party(w.db, w.company_id, f"{MARKER} DEV A")
    b = seed_party(w.db, w.company_id, f"{MARKER} DEV B")
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [
        row("PS26-0001", customer="CUSTOMER 404 SDN BHD"),  # customer + project unmapped
        row("PS26-0002", project_name="UNMAPPED PROJECT"),  # project unmapped
        row("PS26-0003", project_name="TOWER X", developer="DEV A TEXT"),
        row("PS26-0004", project_name="TOWER X2", developer="DEV B TEXT"),  # developer conflict
        row("PS26-0005", project_name=None),  # skipped, nothing blocks
    ]}))
    _map(w, run, customers={C1: customer.id},
         projects={(C1, "TOWER X"): ("create", "ZZT X"), (C1, "TOWER X2"): ("create", "ZZT X")},
         developers={"DEV A TEXT": ("link", a.id), "DEV B TEXT": ("link", b.id)})
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    client.post(f"{BASE}/runs/{run.id}/preview")

    rows = {r["ps_number"]: r for r in client.get(f"{BASE}/runs/{run.id}/rows",
                                                  params={"limit": 50}).json()["data"]}

    assert rows["PS26-0001"]["blocking_kind"] == "customer"
    assert rows["PS26-0002"]["blocking_kind"] == "project"
    assert rows["PS26-0003"]["blocking_kind"] == "developer"
    assert rows["PS26-0004"]["blocking_kind"] == "developer"
    assert rows["PS26-0005"]["blocking_kind"] is None


def test_r5_rev_minor8_the_run_carries_field_labels(world, api_client):
    w = world
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    run = new_run(w, make_book({"JAN'26": [row("PS26-0001")]}))

    body = client.get(f"{BASE}/runs/{run.id}").json()

    labels = body.get("field_labels")
    assert isinstance(labels, dict), sorted(body)
    assert set(labels) == set(FIELDS)
    assert labels["ps_number"].upper().startswith("PS")
    assert labels["customer"] == "Customer"
    for key, label in labels.items():
        assert label and "_" not in label, (key, label)


# --------------------------------------------------------------------------- REV-minor4


def test_r5_rev_minor4_rows_sort_by_reason(world, api_client):
    w = world
    run = new_run(w, make_book({"JAN'26": [
        row("PS26-0001"), row("PS26-0002", project_name=None), row("PS26-0003", po_value="-"),
        {"ps_number": "PS26-0004"}, row("PS26-0005", developer="SOME DEV"),
    ]}))
    client = api_client(w.db, w.admin_id, w.company_id, BOTH)
    client.post(f"{BASE}/runs/{run.id}/preview")
    url = f"{BASE}/runs/{run.id}/rows"

    def reasons(direction):
        r = client.get(url, params={"sort": "reason", "dir": direction, "limit": 50})
        assert r.status_code == 200, r.text
        return [(x.get("message") or "; ".join(x.get("labels") or [])).lower()
                for x in r.json()["data"]]

    asc, desc = reasons("asc"), reasons("desc")
    assert asc == sorted(asc), asc
    assert desc == sorted(desc, reverse=True), desc
    assert asc != desc


# --------------------------------------------------------------------------- REV-M7


def test_r5_rev_m7_notes_dates_use_the_shared_fmt_date(world, monkeypatch):
    from app.utils import date_format

    w = world
    run, _ = _simple_world(w, [row("PS26-0001", delivery=datetime(2026, 2, 3),
                                   amended_date=datetime(2026, 4, 9))])
    real = date_format.fmt_date
    expected = real(date(2026, 2, 3))
    assert expected == "03/02/2026"

    def marked(value, *args, **kwargs):
        return "FMT[" + real(value, *args, **kwargs) + "]"

    monkeypatch.setattr(date_format, "fmt_date", marked)
    monkeypatch.setattr(_svc(), "fmt_date", marked, raising=False)

    _svc().apply(w.db, run, user_id=w.admin_id)

    notes = (_pos(w, "PS26-0001")[0].notes or "").splitlines()
    assert "Delivery: FMT[03/02/2026]" in notes, notes
    assert "Amended: FMT[09/04/2026]" in notes, notes
