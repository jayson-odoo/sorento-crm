"""Project import: preview and import, the same function (AC-PI-20..36).

RED tests, written before `app/services/project_import/service.py`,
`app/services/project_so_link.py` and the new outcome codes exist
(PLAN-project-import-12nov.md, "Backend contract"). Postgres via `blank_session`; every
customer, synced sales order, party, project and user is seeded here.

Kill tests in this file: preview writes nothing (projects, POs, parties, project sales
orders, audit rows all counted before and after), create-only (an existing PO with the PS
number is never updated, a blank never clears), and an import writes no notification,
email, outbound message or project task and leaves the shared invoiced sales total as it was.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from ._project_import_support import (  # noqa: F401  fixtures
    MARKER,
    invoiced_total,
    make_book,
    memory_storage,
    new_run,
    row,
    seed_core_so,
    seed_customer,
    seed_party,
    seed_project,
    seed_user,
    snapshot,
    world,
)

C1 = "CUSTOMER 001 SDN BHD"
P1 = "PROJECT 001 SAMPLE NAME"


def _svc():
    from app.services.project_import import service

    return service


def _map(w, run, *, customers=None, projects=None, developers=None, persons=None):
    """Set lines. projects: {(customer_key, project_key): ("link", id) | ("create", title) |
    ("skip",)}; developers: {key: ("link", id) | ("create",) | ("none",)}; persons:
    {key: user_id | None}. Every person line not named is set to none."""
    s = _svc()
    for key, target in (customers or {}).items():
        if target == "skip":
            s.set_line(w.db, run, kind="customer", value_key=key, action="skip",
                       user_id=w.admin_id)
        else:
            s.set_line(w.db, run, kind="customer", value_key=key, action="link",
                       target_id=target, user_id=w.admin_id)
    for (ck, vk), spec in (projects or {}).items():
        action = spec[0]
        s.set_line(w.db, run, kind="project", customer_value_key=ck, value_key=vk,
                   action=action,
                   target_id=spec[1] if action == "link" else None,
                   new_title=spec[1] if action == "create" else None,
                   user_id=w.admin_id)
    for key, spec in (developers or {}).items():
        s.set_line(w.db, run, kind="developer", value_key=key, action=spec[0],
                   target_id=spec[1] if spec[0] == "link" else None, user_id=w.admin_id)
    persons = dict(persons or {})
    for line in s.list_lines(w.db, run, kind="person"):
        key = line["value_key"]
        target = persons.get(key)
        if target:
            s.set_line(w.db, run, kind="person", value_key=key, action="link",
                       target_id=target, user_id=w.admin_id)
        else:
            s.set_line(w.db, run, kind="person", value_key=key, action="none",
                       user_id=w.admin_id)
    w.db.commit()


def _by_ps(report):
    return {r["ps_number"]: r for r in report["rows"]}


def _pos(w, admin_ref=None):
    from app.models.projects import ProjectPurchaseOrder

    q = w.db.query(ProjectPurchaseOrder)
    if admin_ref:
        q = q.filter(ProjectPurchaseOrder.admin_ref == admin_ref)
    return q.all()


def _projects(w):
    from app.models.projects import Project

    return w.db.query(Project).all()


def _simple_world(w, rows, *, sheet="JAN'26", title="ZZT IMPORTED TOWER", developers=None,
                  persons=None, customer=None):
    customer = customer or seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    run = new_run(w, make_book({sheet: rows}))
    pairs = {(l["customer_value_key"], l["value_key"])
             for l in _svc().list_lines(w.db, run, kind="project")}
    _map(w, run, customers={C1: customer.id},
         projects={pair: ("create", title) for pair in pairs},
         developers=developers, persons=persons)
    return run, customer


# --------------------------------------------------------------------------- AC-PI-20


def test_ac_pi_20_preview_runs_the_import_and_writes_nothing(world):
    from app.models.job import ImportJobRow

    w = world
    dev_rows = [row("PS26-0001", developer="DEVELOPER 001", so_number="SO430001"),
                row("PS26-0002", developer="DEVELOPER 001")]
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    seed_core_so(w.db, w.company_id, "SO430001", customer)
    w.db.commit()
    run, _ = _simple_world(w, dev_rows, developers={"DEVELOPER 001": ("create",)},
                           customer=customer)
    before = snapshot(w.db)

    report = _svc().preview(w.db, run, user_id=w.admin_id)

    assert report["counts"].get("created", 0) == 2  # the create path really ran
    assert _by_ps(report)["PS26-0001"]["codes"][0] == "project_and_po_created"
    after = snapshot(w.db)
    assert after == before
    # Only the run's report rows are kept.
    kept = w.db.query(ImportJobRow).filter(ImportJobRow.import_job_id == run.id).count()
    assert kept >= len(report["rows"]) == 2
    w.db.refresh(run)
    assert run.job_metadata["phase"] == "previewed"
    assert run.job_metadata["preview_counts"]["created"] == 2


# --------------------------------------------------------------------------- AC-PI-21


def test_ac_pi_21_import_creates_project_po_and_so_links(world):
    from app.models.project_so import ProjectSalesOrder

    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    core = seed_core_so(w.db, w.company_id, "SO430011", customer)
    w.db.commit()
    run, _ = _simple_world(w, [
        row("PS26-0001", so_number="SO430011"),
        row("PS26-0002", po_number="PO-SECOND"),
    ], customer=customer)

    report = _svc().apply(w.db, run, user_id=w.admin_id)

    rows = _by_ps(report)
    assert rows["PS26-0001"]["outcome"] == "created"
    assert "project_and_po_created" in rows["PS26-0001"]["codes"]
    assert rows["PS26-0002"]["outcome"] == "created"
    assert "po_added" in rows["PS26-0002"]["codes"]
    projects = _projects(w)
    assert len(projects) == 1
    pos = {p.admin_ref: p for p in _pos(w)}
    assert set(pos) == {"PS26-0001", "PS26-0002"}
    assert {p.project_id for p in pos.values()} == {projects[0].id}
    pso = w.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.so_id == core.id).one()
    assert pso.project_id == projects[0].id
    assert pso.purchase_order_id == pos["PS26-0001"].id
    w.db.refresh(run)
    assert run.job_metadata["phase"] == "imported"
    assert run.job_metadata.get("imported_at")


def test_ac_pi_21_po_added_to_an_existing_linked_project(world):
    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    existing = seed_project(w.db, w.company_id, w.admin_id, f"{MARKER} EXISTING TOWER")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [row("PS26-0001")]}))
    _map(w, run, customers={C1: customer.id}, projects={(C1, P1): ("link", existing.id)})

    report = _svc().apply(w.db, run, user_id=w.admin_id)

    r = _by_ps(report)["PS26-0001"]
    assert r["outcome"] == "created"
    assert "po_added" in r["codes"]
    assert len(_projects(w)) == 1
    assert _pos(w, "PS26-0001")[0].project_id == existing.id


# --------------------------------------------------------------------------- AC-PI-22


def test_ac_pi_22_lines_created_with_the_same_title_become_one_project(world):
    from app.models.project_import import ProjectImportValueMap
    from app.models.projects import ProjectSalesProfile

    w = world
    alvin = seed_user(w.db, f"{MARKER} Alvin")
    bella = seed_user(w.db, f"{MARKER} Bella")
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [
        row("PS26-0009", project_name="TOWER ONE", salesperson="BELLA", developer="DEV TEXT A"),
        row("PS26-0004", project_name="TOWER 1", salesperson="ALVIN", developer="DEV TEXT A"),
    ]}))
    _map(w, run, customers={C1: customer.id},
         projects={(C1, "TOWER ONE"): ("create", "ZZT Tower One"),
                   (C1, "TOWER 1"): ("create", "  zzt   TOWER one ")},
         developers={"DEV TEXT A": ("none",)},
         persons={"ALVIN": alvin, "BELLA": bella})

    report = _svc().apply(w.db, run, user_id=w.admin_id)

    projects = _projects(w)
    assert len(projects) == 1
    project = projects[0]
    assert project.admin_ref == "PS26-0004"  # the lowest PS number of its rows
    assert project.owner_user_id == alvin  # salesperson of the lowest PS row
    assert project.template_id is None
    assert project.approval_state is None
    profile = w.db.get(ProjectSalesProfile, project.id)
    assert profile.customer_id == customer.id
    assert profile.developer_name == "DEV TEXT A"
    assert profile.lead_source is None
    rows = _by_ps(report)
    assert "clash_check_skipped" in rows["PS26-0004"]["codes"]
    assert "project_and_po_created" in rows["PS26-0004"]["codes"]
    assert "po_added" in rows["PS26-0009"]["codes"]
    # Each create line is rewritten to link to what it made.
    maps = w.db.query(ProjectImportValueMap).filter(ProjectImportValueMap.kind == "project").all()
    assert len(maps) == 2
    assert {(m.action, m.target_id) for m in maps} == {("link", project.id)}


def test_ac_pi_22_an_unmapped_salesperson_defaults_the_owner_to_the_importer(world):
    w = world
    run, _ = _simple_world(w, [row("PS26-0001")])

    report = _svc().apply(w.db, run, user_id=w.admin_id)

    assert _projects(w)[0].owner_user_id == w.admin_id
    assert "owner_defaulted" in _by_ps(report)["PS26-0001"]["codes"]


def test_ac_pi_22_a_later_file_adds_to_the_project_the_first_one_created(world):
    w = world
    run, customer = _simple_world(w, [row("PS26-0001")])
    _svc().apply(w.db, run, user_id=w.admin_id)
    w.db.commit()
    project_id = _projects(w)[0].id

    later = new_run(w, make_book({"FEB'26": [
        row("PS26-0171", po_number="PO-FEB", po_date=datetime(2026, 2, 3)),
    ]}))
    line = [l for l in _svc().list_lines(w.db, later, kind="project")][0]
    assert line["source"] == "saved"
    assert line["action"] == "link"
    assert line["target_id"] == project_id

    report = _svc().apply(w.db, later, user_id=w.admin_id)
    assert "po_added" in _by_ps(report)["PS26-0171"]["codes"]
    assert len(_projects(w)) == 1


# --------------------------------------------------------------------------- AC-PI-23


def test_ac_pi_23_developer_link_create_and_none(world):
    from app.models.project_import import ProjectImportValueMap
    from app.models.projects import ProjectParty

    w = world
    linked = seed_party(w.db, w.company_id, f"{MARKER} LINKED DEV")
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [
        row("PS26-0001", project_name="TOWER L", developer="DEV LINKED"),
        row("PS26-0002", project_name="TOWER C", developer="ZZT DEV NEW ONE"),
        row("PS26-0003", project_name="TOWER C2", developer="ZZT DEV NEW ONE"),
        row("PS26-0004", project_name="TOWER N", developer="END USER"),
    ]}))
    _map(w, run, customers={C1: customer.id},
         projects={(C1, "TOWER L"): ("create", "ZZT TOWER L"),
                   (C1, "TOWER C"): ("create", "ZZT TOWER C"),
                   (C1, "TOWER C2"): ("create", "ZZT TOWER C2"),
                   (C1, "TOWER N"): ("create", "ZZT TOWER N")},
         developers={"DEV LINKED": ("link", linked.id), "ZZT DEV NEW ONE": ("create",),
                     "END USER": ("none",)})
    parties_before = w.db.query(ProjectParty).count()

    _svc().apply(w.db, run, user_id=w.admin_id)

    by_title = {p.title: p for p in _projects(w)}
    assert by_title["ZZT TOWER L"].developer_party_id == linked.id
    assert by_title["ZZT TOWER N"].developer_party_id is None
    made = w.db.query(ProjectParty).filter(ProjectParty.name == "ZZT DEV NEW ONE").all()
    assert len(made) == 1  # exactly one party for the line, shared by both of its rows
    assert w.db.query(ProjectParty).count() == parties_before + 1
    assert by_title["ZZT TOWER C"].developer_party_id == made[0].id
    assert by_title["ZZT TOWER C2"].developer_party_id == made[0].id
    line = (w.db.query(ProjectImportValueMap)
            .filter(ProjectImportValueMap.kind == "developer",
                    ProjectImportValueMap.value_key == "ZZT DEV NEW ONE").one())
    assert (line.action, line.target_id) == ("link", made[0].id)


def test_ac_pi_23_one_new_project_with_differing_developers_needs_review(world):
    w = world
    a = seed_party(w.db, w.company_id, f"{MARKER} DEV A")
    b = seed_party(w.db, w.company_id, f"{MARKER} DEV B")
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [
        row("PS26-0001", project_name="TOWER X", developer="DEV A TEXT"),
        row("PS26-0002", project_name="TOWER X PHASE 2", developer="DEV B TEXT"),
    ]}))
    _map(w, run, customers={C1: customer.id},
         projects={(C1, "TOWER X"): ("create", "ZZT TOWER X"),
                   (C1, "TOWER X PHASE 2"): ("create", "ZZT TOWER X")},
         developers={"DEV A TEXT": ("link", a.id), "DEV B TEXT": ("link", b.id)})

    report = _svc().apply(w.db, run, user_id=w.admin_id)

    for ps in ("PS26-0001", "PS26-0002"):
        assert _by_ps(report)[ps]["outcome"] == "needs_review"
        assert "developer_conflict" in _by_ps(report)[ps]["codes"]
    assert _projects(w) == []


# --------------------------------------------------------------------------- AC-PI-24


def test_ac_pi_24_the_registration_lock_is_never_bypassed(world):
    w = world
    party = seed_party(w.db, w.company_id, f"{MARKER} LOCK DEV")
    existing = seed_project(w.db, w.company_id, w.admin_id, "ZZT LOCK TOWER",
                            developer_party_id=party.id)
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [row("PS26-0001", developer="LOCK DEV TEXT")]}))
    _map(w, run, customers={C1: customer.id},
         projects={(C1, P1): ("create", "zzt  lock tower")},
         developers={"LOCK DEV TEXT": ("link", party.id)})

    report = _svc().apply(w.db, run, user_id=w.admin_id)

    r = _by_ps(report)["PS26-0001"]
    assert r["outcome"] == "needs_review"
    assert "registration_lock" in r["codes"]
    assert existing.project_code and existing.project_code in r["message"]
    assert [p.id for p in _projects(w)] == [existing.id]
    assert _pos(w) == []


# --------------------------------------------------------------------------- AC-PI-25


def test_ac_pi_25_the_po_fields(world):
    from app.models.projects import ProjectParty

    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    issuer = seed_party(w.db, w.company_id, f"{MARKER} DEALER PARTY", party_type="trading_house",
                        customer_id=customer.id)
    w.db.commit()
    parties_before = w.db.query(ProjectParty).count()
    run, _ = _simple_world(w, [
        row("PS26-0001", salesperson="ALVIN ", po_number=12119, po_value=49.68,
            po_date=datetime(2026, 1, 5)),
    ], customer=customer)

    _svc().apply(w.db, run, user_id=w.admin_id)

    po = _pos(w, "PS26-0001")[0]
    assert po.po_number == "12119"
    assert po.po_date == date(2026, 1, 5)
    assert po.po_amount == Decimal("49.68")
    assert po.admin_ref == "PS26-0001"
    assert po.sales_person == "ALVIN"
    assert po.po_source == "contractor_direct"
    assert po.issuing_party_id == issuer.id
    assert po.status == "draft"
    assert w.db.query(ProjectParty).count() == parties_before  # none made from a customer


def test_ac_pi_25_no_issuer_unless_exactly_one_party_carries_the_customer(world):
    from app.models.projects import ProjectParty

    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    seed_party(w.db, w.company_id, f"{MARKER} PARTY 1", party_type="trading_house",
               customer_id=customer.id)
    seed_party(w.db, w.company_id, f"{MARKER} PARTY 2", party_type="trading_house",
               customer_id=customer.id)
    other = seed_customer(w.db, w.company_id, f"{MARKER} DEALER TWO")
    w.db.commit()
    parties_before = w.db.query(ProjectParty).count()
    run = new_run(w, make_book({"JAN'26": [
        row("PS26-0001"),
        row("PS26-0002", customer="CUSTOMER 002 SDN BHD", project_name="PROJECT 2"),
    ]}))
    _map(w, run, customers={C1: customer.id, "CUSTOMER 002 SDN BHD": other.id},
         projects={(C1, P1): ("create", "ZZT T1"),
                   ("CUSTOMER 002 SDN BHD", "PROJECT 2"): ("create", "ZZT T2")})

    _svc().apply(w.db, run, user_id=w.admin_id)

    assert _pos(w, "PS26-0001")[0].issuing_party_id is None  # two candidates
    assert _pos(w, "PS26-0002")[0].issuing_party_id is None  # none
    assert w.db.query(ProjectParty).count() == parties_before


# --------------------------------------------------------------------------- AC-PI-26


def test_ac_pi_26_po_notes_one_line_each_in_order_only_when_present(world):
    w = world
    run, _ = _simple_world(w, [
        row("PS26-0001", customer_service="KATE", amended_date="amend 9/4/2026",
            schedule="O/C", delivery=datetime(2026, 2, 3), outstanding="on hold 23/4/2026",
            remarks="WAIVE TRASNPORT CHARGE", so_number="refer PS26-0022"),
        row("PS26-0002", customer_service="LUNA", amended_date=datetime(2026, 4, 9),
            schedule="CBD", delivery="IMMEDIATE", remarks="HOLD"),
        row("PS26-0003", customer_service="MIKE", schedule=None, remarks="WAIVE TRANPORT CHARGES"),
        row("PS26-0004", customer_service="NORA", schedule="YES", remarks="waive trasport charge"),
    ])

    _svc().apply(w.db, run, user_id=w.admin_id)

    notes = {p.admin_ref: (p.notes or "").splitlines() for p in _pos(w)}
    assert notes["PS26-0001"] == [
        "CS: KATE",
        "Amended: amend 9/4/2026",
        "Schedule: O/C",
        "Delivery: 03/02/2026",
        "Outstanding: on hold 23/4/2026",
        "Waive transport charge",
        "SO note: refer PS26-0022",
    ]
    assert notes["PS26-0002"] == [
        "CS: LUNA",
        "Amended: 09/04/2026",
        "Schedule: CBD",
        "Delivery: IMMEDIATE",
        "Remarks: HOLD",
    ]
    assert notes["PS26-0003"] == ["CS: MIKE", "Waive transport charge"]
    assert notes["PS26-0004"] == ["CS: NORA", "Schedule: YES", "Waive transport charge"]


# --------------------------------------------------------------------------- AC-PI-27


def test_ac_pi_27_cancelled_rows_are_skipped_and_listed(world):
    w = world
    run, _ = _simple_world(w, [
        row("PS26-0001", po_value="-"),
        row("PS26-0002", outstanding="CANCELLED 12/6/2026"),
        row("PS26-0003", so_number="cancelled 11/5/2026"),
        row("PS26-0004", remarks="Cancel PS no"),
        row("PS26-0005", remarks="CANCELLED BY CASH"),
        row("PS26-0006", remarks="HOLD"),  # not cancelled
    ])

    report = _svc().apply(w.db, run, user_id=w.admin_id)

    rows = _by_ps(report)
    for n in range(1, 6):
        ps = f"PS26-{n:04d}"
        assert rows[ps]["outcome"] == "skipped", ps
        assert rows[ps]["codes"] == ["cancelled"], ps
    assert rows["PS26-0006"]["outcome"] == "created"
    assert report["codes"].get("cancelled") == 5
    assert [p.admin_ref for p in _pos(w)] == ["PS26-0006"]


# --------------------------------------------------------------------------- AC-PI-28


def test_ac_pi_28_date_flags_and_rows_imported_as_written(world):
    w = world
    run, _ = _simple_world(w, [
        row("PS26-0001", po_date=datetime(2025, 1, 2)),  # year typo, same month
        row("PS26-0002", po_date=datetime(2026, 2, 3)),  # other month
        row("PS26-0003", po_date=datetime(2026, 1, 20)),  # clean
    ])

    report = _svc().apply(w.db, run, user_id=w.admin_id)

    rows = _by_ps(report)
    assert "date_other_year" in rows["PS26-0001"]["codes"]
    assert "date_other_month" not in rows["PS26-0001"]["codes"]
    assert "date_other_month" in rows["PS26-0002"]["codes"]
    assert "date_other_year" not in rows["PS26-0002"]["codes"]
    assert not {"date_other_year", "date_other_month"} & set(rows["PS26-0003"]["codes"])
    assert _pos(w, "PS26-0001")[0].po_date == date(2025, 1, 2)
    assert _pos(w, "PS26-0002")[0].po_date == date(2026, 2, 3)
    for ps in ("PS26-0001", "PS26-0002"):
        assert rows[ps]["outcome"] == "created"


def test_ac_pi_28_the_malay_march_sheet_is_month_three(world):
    w = world
    run, _ = _simple_world(w, [row("PS26-0299", po_date=datetime(2026, 3, 4))], sheet="MAC'26 ")

    report = _svc().preview(w.db, run, user_id=w.admin_id)

    assert "date_other_month" not in _by_ps(report)["PS26-0299"]["codes"]


# --------------------------------------------------------------------------- AC-PI-29


def test_ac_pi_29_unsynced_so_is_flagged_and_linked_on_a_later_run(world):
    from app.models.project_so import ProjectSalesOrder

    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    content_rows = [row("PS26-0001", so_number="SO440001, SO440002")]
    run, _ = _simple_world(w, content_rows, customer=customer)
    seed_core_so(w.db, w.company_id, "SO440001", customer)
    w.db.commit()

    first = _svc().apply(w.db, run, user_id=w.admin_id)
    r = _by_ps(first)["PS26-0001"]
    assert r["outcome"] == "created"
    assert "so_not_synced" in r["codes"]
    assert len(_pos(w, "PS26-0001")) == 1
    assert w.db.query(ProjectSalesOrder).count() == 1
    w.db.commit()

    late = seed_core_so(w.db, w.company_id, "SO440002", customer)
    w.db.commit()
    second_run = new_run(w, make_book({"JAN'26": content_rows}))
    second = _svc().apply(w.db, second_run, user_id=w.admin_id)

    r2 = _by_ps(second)["PS26-0001"]
    assert r2["outcome"] == "updated"
    assert "so_linked" in r2["codes"]
    pso = w.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.so_id == late.id).one()
    po = _pos(w, "PS26-0001")[0]
    assert (pso.project_id, pso.purchase_order_id) == (po.project_id, po.id)


def test_ac_pi_29_an_so_on_another_project_needs_review_and_is_not_moved(world):
    from app.models.project_so import ProjectSalesOrder
    from app.services.project_so_adoption_service import ProjectSOAdoptionService

    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    core = seed_core_so(w.db, w.company_id, "SO450001", customer)
    elsewhere = seed_project(w.db, w.company_id, w.admin_id, f"{MARKER} ELSEWHERE")
    ProjectSOAdoptionService(w.db).adopt_for_migration(core.id, actor_user_id=w.admin_id)
    pso = w.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.so_id == core.id).one()
    pso.project_id = elsewhere.id
    w.db.commit()
    run, _ = _simple_world(w, [row("PS26-0001", so_number="SO450001")], customer=customer)

    report = _svc().apply(w.db, run, user_id=w.admin_id)

    r = _by_ps(report)["PS26-0001"]
    assert r["outcome"] == "needs_review"
    assert "so_on_other_project" in r["codes"]
    w.db.refresh(pso)
    assert pso.project_id == elsewhere.id


def test_ac_pi_29_link_sales_order_to_project_refuses_an_order_on_another_project(world):
    from app.models.project_so import ProjectSalesOrder
    from app.services.error_handler import AppException
    from app.services.project_so_adoption_service import ProjectSOAdoptionService
    from app.services.project_so_link import link_sales_order_to_project

    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    core = seed_core_so(w.db, w.company_id, "SO460001", customer)
    a = seed_project(w.db, w.company_id, w.admin_id, f"{MARKER} PROJECT A")
    b = seed_project(w.db, w.company_id, w.admin_id, f"{MARKER} PROJECT B")
    ProjectSOAdoptionService(w.db).adopt_for_migration(core.id, actor_user_id=w.admin_id)
    pso = w.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.so_id == core.id).one()

    link_sales_order_to_project(w.db, project_sales_order=pso, project=a, purchase_order=None)
    assert pso.project_id == a.id
    with pytest.raises(AppException) as excinfo:
        link_sales_order_to_project(w.db, project_sales_order=pso, project=b,
                                    purchase_order=None)
    assert excinfo.value.status_code == 409
    assert pso.project_id == a.id


# --------------------------------------------------------------------------- AC-PI-30 / 31


def test_ac_pi_30_and_31_existing_ps_number_is_unchanged_and_never_written(world):
    w = world
    run, customer = _simple_world(w, [row("PS26-0001", po_value=1000,
                                          po_date=datetime(2026, 1, 5))])
    _svc().apply(w.db, run, user_id=w.admin_id)
    w.db.commit()
    po = _pos(w, "PS26-0001")[0]
    stamp = (po.po_amount, po.po_date, po.po_number, po.notes, po.updated_at)

    # Same PS number, a different amount and a blank date in the new file.
    changed = new_run(w, make_book({"JAN'26": [
        row("PS26-0001", po_value=2500, po_date=None),
    ]}))
    report = _svc().apply(w.db, changed, user_id=w.admin_id)

    r = _by_ps(report)["PS26-0001"]
    assert r["outcome"] == "unchanged"
    assert "changed_in_file" in r["codes"]
    assert "amount" in r["message"].lower() or "po_amount" in r["message"].lower()
    w.db.refresh(po)
    assert (po.po_amount, po.po_date, po.po_number, po.notes, po.updated_at) == stamp
    assert len(_pos(w, "PS26-0001")) == 1


def test_ac_pi_30_duplicates_in_the_file_and_in_the_crm(world):
    from app.services import project_po_service

    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    host = seed_project(w.db, w.company_id, w.admin_id, f"{MARKER} HOST")
    for number in ("PO-DUP-1", "PO-DUP-2"):
        po = project_po_service.create_po(
            w.db, project=host, actor_user_id=w.admin_id,
            payload={"po_source": "contractor_direct", "po_number": number},
        )
        po.admin_ref = "PS26-0050"
    taken = project_po_service.create_po(
        w.db, project=host, actor_user_id=w.admin_id,
        payload={"po_source": "contractor_direct", "po_number": "PO-TAKEN"},
    )
    taken.admin_ref = "PS26-0060"
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [
        row("PS26-0001", po_number="PO-A"),
        row("PS26-0001", po_number="PO-B"),
        row("PS26-0050", po_number="PO-C"),
        row("PS26-0070", po_number="PO-TAKEN"),
    ]}))
    _map(w, run, customers={C1: customer.id}, projects={(C1, P1): ("link", host.id)})
    pos_before = len(_pos(w))

    report = _svc().apply(w.db, run, user_id=w.admin_id)

    rows = report["rows"]
    dup = [r for r in rows if r["ps_number"] == "PS26-0001"]
    assert len(dup) == 2
    assert all(r["outcome"] == "error" and "ps_duplicate_in_file" in r["codes"] for r in dup)
    crm = _by_ps(report)["PS26-0050"]
    assert crm["outcome"] == "error"
    assert "ps_duplicate_in_crm" in crm["codes"]
    clash = _by_ps(report)["PS26-0070"]
    assert clash["outcome"] == "needs_review"
    assert "po_number_taken" in clash["codes"]
    assert len(_pos(w)) == pos_before


def test_ac_pi_31_a_linked_existing_project_is_never_edited(world):
    from app.models.projects import ProjectSalesProfile

    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    existing = seed_project(w.db, w.company_id, w.admin_id, f"{MARKER} KEEP AS IS")
    w.db.commit()
    before = (existing.title, existing.owner_user_id, existing.admin_ref,
              existing.developer_party_id, existing.updated_at)
    profile = w.db.get(ProjectSalesProfile, existing.id)
    profile_before = (profile.customer_id, profile.developer_name) if profile else None
    run = new_run(w, make_book({"JAN'26": [row("PS26-0001", developer="SOME DEV")]}))
    _map(w, run, customers={C1: customer.id}, projects={(C1, P1): ("link", existing.id)},
         developers={"SOME DEV": ("none",)})

    _svc().apply(w.db, run, user_id=w.admin_id)

    w.db.refresh(existing)
    assert existing.title == before[0]
    assert existing.owner_user_id == before[1]
    assert existing.admin_ref == before[2]
    assert existing.developer_party_id == before[3]
    profile = w.db.get(ProjectSalesProfile, existing.id)
    assert ((profile.customer_id, profile.developer_name) if profile else None) == profile_before


# --------------------------------------------------------------------------- AC-PI-32


def test_ac_pi_32_importing_the_same_file_twice_changes_nothing(world):
    w = world
    rows = [row("PS26-0001"), row("PS26-0002", po_number="PO-2"),
            row("PS26-0003", project_name=None), row("PS26-0004", po_value="-")]
    run, _ = _simple_world(w, rows)
    _svc().apply(w.db, run, user_id=w.admin_id)
    w.db.commit()
    before = snapshot(w.db)

    again = new_run(w, make_book({"JAN'26": rows}))
    report = _svc().apply(w.db, again, user_id=w.admin_id)

    assert report["counts"].get("created", 0) == 0
    assert report["counts"].get("updated", 0) == 0
    by = _by_ps(report)
    assert by["PS26-0001"]["outcome"] == "unchanged"
    assert by["PS26-0002"]["outcome"] == "unchanged"
    after = snapshot(w.db)
    assert after["projects"] == before["projects"]
    assert after["purchase_orders"] == before["purchase_orders"]


# --------------------------------------------------------------------------- AC-PI-33


def test_ac_pi_33_one_bad_row_never_fails_the_batch(world):
    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [
        row("PS26-0001"),
        row("PS26-0002", po_number="X" * 150),  # longer than purchase_orders.po_number
        row("PS26-0003", po_number="PO-3"),
        row("PS26-0004", customer="CUSTOMER 404 SDN BHD", project_name="UNMAPPED"),
    ]}))
    _map(w, run, customers={C1: customer.id}, projects={(C1, P1): ("create", "ZZT BATCH")})

    report = _svc().apply(w.db, run, user_id=w.admin_id)

    by = _by_ps(report)
    assert by["PS26-0002"]["outcome"] == "error"
    assert by["PS26-0001"]["outcome"] == "created"
    assert by["PS26-0003"]["outcome"] == "created"
    assert by["PS26-0004"]["outcome"] == "needs_review"
    assert sorted(p.admin_ref for p in _pos(w)) == ["PS26-0001", "PS26-0003"]
    w.db.refresh(run)
    result = run.job_metadata["result_counts"]
    assert result["needs_review"] == 1
    assert result["error"] == 1
    assert result["created"] == 2


# --------------------------------------------------------------------------- AC-PI-34


def _posted_invoice(w, customer):
    from app.models.finance import BillingDocument

    w.db.add(BillingDocument(
        document_type="invoice", doc_no=f"{MARKER}-IV-1", doc_date=date(2026, 1, 9),
        customer_id=customer.id, local_net_total=Decimal("1234.50"), status="posted",
        company_id=w.company_id,
    ))
    w.db.flush()


def test_ac_pi_34_no_notification_or_outbound_and_the_invoiced_total_is_unchanged(world):
    w = world
    alvin = seed_user(w.db, f"{MARKER} Alvin")
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    core = seed_core_so(w.db, w.company_id, "SO470001", customer)
    _posted_invoice(w, customer)
    w.db.commit()
    total_before = invoiced_total(w.db, w.company_id)
    assert total_before == Decimal("1234.50")
    run, _ = _simple_world(w, [row("PS26-0001", so_number="SO470001"), row("PS26-0002")],
                           persons={"ALVIN": alvin}, customer=customer)
    before = snapshot(w.db)

    _svc().apply(w.db, run, user_id=w.admin_id)
    w.db.commit()

    after = snapshot(w.db)
    assert after["projects"] == before["projects"] + 1  # the import did run
    for table in ("notifications", "notification_deliveries", "email_outbox",
                  "integration_outbound", "project_tasks"):
        assert after[table] == before[table], table
    assert invoiced_total(w.db, w.company_id) == total_before
    assert core.id  # the SO stays a synced order


# --------------------------------------------------------------------------- AC-PI-35


def test_ac_pi_35_every_created_record_has_a_ledger_row(world):
    from app.models.job import ImportJobRow
    from app.models.project_so import ProjectSalesOrder
    from app.models.projects import ProjectParty

    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    core = seed_core_so(w.db, w.company_id, "SO480001", customer)
    w.db.commit()
    run, _ = _simple_world(w, [row("PS26-0001", developer="ZZT NEW DEV", so_number="SO480001")],
                           developers={"ZZT NEW DEV": ("create",)}, customer=customer)

    report = _svc().apply(w.db, run, user_id=w.admin_id)

    project = _projects(w)[0]
    po = _pos(w, "PS26-0001")[0]
    party = w.db.query(ProjectParty).filter(ProjectParty.name == "ZZT NEW DEV").one()
    pso = w.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.so_id == core.id).one()
    ledger = (w.db.query(ImportJobRow)
              .filter(ImportJobRow.import_job_id == run.id, ImportJobRow.entity_id.isnot(None))
              .all())
    ids = {r.entity_id for r in ledger}
    for record_id in (project.id, po.id, party.id, pso.id):
        assert record_id in ids, record_id
    # The sales profile is keyed by its project id; it has its own typed row.
    types = {(r.entity_type, r.entity_id) for r in ledger}
    assert sum(1 for t, i in types if i == project.id) >= 2  # project + sales profile
    assert all(r.entity_type for r in ledger)
    w.db.refresh(run)
    result = run.job_metadata["result_counts"]
    assert all(result.get(k, 0) == v for k, v in report["counts"].items())
    assert sum(report["counts"].values()) == len(report["rows"])


def test_ac_pi_35_the_run_is_the_audit_actor(world):
    from app.models.audit import AuditLog

    w = world
    run, _ = _simple_world(w, [row("PS26-0001")])

    _svc().apply(w.db, run, user_id=w.admin_id)
    w.db.flush()

    project = _projects(w)[0]
    audit = (w.db.query(AuditLog)
             .filter(AuditLog.entity_id == str(project.id)).all())
    assert audit, "creating a project writes an audit row"
    assert any(a.user_id == w.admin_id for a in audit)
    # stamp_actor(AuditActor(actor_type="user", user_id=..., job_id=run id)).
    assert any(a.job_id == str(run.id) for a in audit)


# --------------------------------------------------------------------------- AC-PI-36


def test_ac_pi_36_import_is_queued_on_the_imports_queue(world, monkeypatch):
    from app.services import queue_service

    w = world
    run, _ = _simple_world(w, [row("PS26-0001")])
    captured = []

    class _Job:
        id = "rq-job-1"

    def fake_enqueue(func, *args, queue_name="imports", **kwargs):
        captured.append((getattr(func, "__name__", str(func)), queue_name, args, kwargs))
        return _Job()

    monkeypatch.setattr(queue_service, "enqueue_job", fake_enqueue)
    s = _svc()
    monkeypatch.setattr(s, "enqueue_job", fake_enqueue, raising=False)

    job_id = s.start_import(w.db, run, user_id=w.admin_id)

    assert job_id
    assert len(captured) == 1
    name, queue, args, kwargs = captured[0]
    assert name == "process_project_import"
    assert queue == "imports"
    assert _pos(w) == []  # nothing ran in-process


def test_ac_pi_36_the_task_exists():
    from app.tasks import import_tasks

    assert callable(import_tasks.process_project_import)


# --------------------------------------------------------------------------- codes


def test_the_new_outcome_codes_have_plain_labels():
    from app.services import import_outcome_codes as codes

    new = [
        "project_and_po_created", "po_added", "no_project_name", "placeholder", "other_year",
        "cancelled", "mapped_skip", "project_unmapped", "customer_unmapped",
        "developer_unmapped", "customer_conflict", "customer_same_shop_so_used",
        "developer_conflict", "registration_lock", "po_number_taken", "so_on_other_project",
        "ps_duplicate_in_file", "ps_duplicate_in_crm", "changed_in_file", "so_linked",
        "so_not_synced", "po_number_numeric", "date_other_year", "date_other_month",
        "owner_defaulted", "clash_check_skipped", "missing_header", "revert_kept_edited",
    ]
    for code in new:
        assert code in codes.LABELS, code
        label = codes.label_for(code)
        assert label and "_" not in label, (code, label)
