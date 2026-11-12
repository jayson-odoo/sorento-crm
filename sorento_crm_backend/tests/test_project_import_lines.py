"""Project import: the Values step, lines and saved value maps (AC-PI-12..19).

RED tests, written before `app/services/project_import/service.py` and
`app/models/project_import.py` exist (PLAN-project-import-12nov.md, "Backend contract").
Postgres via `blank_session`; every customer, sales order, party, project and user is seeded
here.

Kill tests in this file: saved maps are per company (another company's map is never
offered), and NOTHING is matched by similarity (one letter, a prefix or a contains match is
still "To do").
"""
from __future__ import annotations

from datetime import datetime

import pytest

from ._project_import_support import (  # noqa: F401  fixtures
    MARKER,
    fold,
    make_book,
    memory_storage,
    new_run,
    row,
    seed_company,
    seed_core_so,
    seed_customer,
    seed_group,
    seed_party,
    seed_project,
    seed_user,
    world,
)


def _svc():
    from app.services.project_import import service

    return service


def _lines(w, run, kind, status=None):
    return _svc().list_lines(w.db, run, kind=kind, status=status)


def _line(lines, value_key, customer_value_key=""):
    match = [
        l for l in lines
        if l["value_key"] == value_key and (l.get("customer_value_key") or "") == customer_value_key
    ]
    assert len(match) == 1, (value_key, customer_value_key, [l["value_key"] for l in lines])
    return match[0]


def _map_rows(w, **filters):
    from app.models.project_import import ProjectImportValueMap

    q = w.db.query(ProjectImportValueMap)
    for k, v in filters.items():
        q = q.filter(getattr(ProjectImportValueMap, k) == v)
    return q.all()


BOOK_ROWS = [
    row("PS26-0001", customer="CUSTOMER 001 SDN BHD", project_name="PROJECT A",
        developer="DEVELOPER 001", salesperson="ALVIN", customer_service="KATE"),
    row("PS26-0002", customer=" customer 001  sdn bhd ", project_name="project  a ",
        developer="DEVELOPER 001 ", salesperson="ALVIN ", customer_service="KATE"),
    row("PS26-0003", customer="CUSTOMER 002 SDN BHD", project_name="PROJECT A",
        developer=None, salesperson="BELLA", customer_service="LUNA"),
    row("PS26-0004", customer="CUSTOMER 002 SDN BHD", project_name=None,
        developer=None, salesperson="BELLA", customer_service="LUNA"),
]


# --------------------------------------------------------------------------- AC-PI-12


def test_ac_pi_12_lines_are_listed_per_kind_with_row_counts(world):
    run = new_run(world, make_book({"JAN'26": BOOK_ROWS}))

    customers = _lines(world, run, "customer")
    assert {l["value_key"]: l["rows"] for l in customers} == {
        "CUSTOMER 001 SDN BHD": 2,
        "CUSTOMER 002 SDN BHD": 2,
    }
    for l in customers:
        assert l["kind"] == "customer"
        assert (l.get("customer_value_key") or "") == ""

    projects = _lines(world, run, "project")
    assert {(l["customer_value_key"], l["value_key"]): l["rows"] for l in projects} == {
        ("CUSTOMER 001 SDN BHD", "PROJECT A"): 2,
        ("CUSTOMER 002 SDN BHD", "PROJECT A"): 1,
    }
    pair = _line(projects, "PROJECT A", "CUSTOMER 001 SDN BHD")
    assert fold(pair["customer_text"]) == "CUSTOMER 001 SDN BHD"
    assert fold(pair["value_text"]) == "PROJECT A"

    developers = _lines(world, run, "developer")
    assert {l["value_key"]: l["rows"] for l in developers} == {"DEVELOPER 001": 2}

    people = _lines(world, run, "person")
    assert {l["value_key"]: l["rows"] for l in people} == {
        "ALVIN": 2, "BELLA": 2, "KATE": 2, "LUNA": 2,
    }
    for l in customers + projects + developers + people:
        assert l["status"] == "todo"
        assert l["action"] in (None, "")
        assert l["source"] is None


# --------------------------------------------------------------------------- AC-PI-13


def test_ac_pi_13_rows_without_a_project_name_are_skipped_and_never_project_lines(world):
    run = new_run(world, make_book({"JAN'26": BOOK_ROWS}))

    projects = _lines(world, run, "project")
    assert all(l["value_key"] for l in projects)
    assert ("CUSTOMER 002 SDN BHD", "") not in {
        (l["customer_value_key"], l["value_key"]) for l in projects
    }

    report = _svc().preview(world.db, run, user_id=world.admin_id)
    by_ps = {r["ps_number"]: r for r in report["rows"]}
    assert by_ps["PS26-0004"]["outcome"] == "skipped"
    assert "no_project_name" in by_ps["PS26-0004"]["codes"]
    assert report["codes"].get("no_project_name") == 1


# --------------------------------------------------------------------------- AC-PI-14 / 40


def test_ac_pi_14_a_saved_map_of_the_same_company_prefills_the_next_run(world):
    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} CUSTOMER ONE")
    w.db.commit()
    first = new_run(w, make_book({"JAN'26": BOOK_ROWS}))
    _svc().set_line(w.db, first, kind="customer", value_key="CUSTOMER 001 SDN BHD",
                    action="link", target_id=customer.id, user_id=w.admin_id)
    w.db.commit()

    second = new_run(w, make_book({"FEB'26": [
        row("PS26-0171", customer="Customer 001 Sdn Bhd", po_date=datetime(2026, 2, 3)),
        row("PS26-0172", customer="CUSTOMER 002 SDN BHD", po_date=datetime(2026, 2, 3)),
    ]}))
    lines = _lines(w, second, "customer")

    saved = _line(lines, "CUSTOMER 001 SDN BHD")
    assert saved["status"] == "set"
    assert saved["action"] == "link"
    assert saved["target_id"] == customer.id
    assert saved["source"] == "saved"
    assert saved["set_by_name"] == f"{MARKER} Importer"
    assert saved["set_at"]
    assert saved["target_label"]  # a name, never the id
    assert customer.id not in str(saved["target_label"])

    never_saved = _line(lines, "CUSTOMER 002 SDN BHD")
    assert never_saved["status"] == "todo"
    assert never_saved["source"] is None


def test_ac_pi_14_and_40_a_map_saved_only_by_another_company_is_never_offered(world):
    from app.models.base import company_scope
    from app.models.project_import import ProjectImportValueMap

    w = world
    other = seed_company(w.db, "Other")
    with company_scope(w.db, frozenset({other})):
        foreign_customer = seed_customer(w.db, other, f"{MARKER} FOREIGN")
        w.db.add(ProjectImportValueMap(
            company_id=other, kind="customer", customer_value_key="",
            value_key="CUSTOMER 001 SDN BHD", value_text="CUSTOMER 001 SDN BHD",
            action="link", target_id=foreign_customer.id, set_by_user_id=w.admin_id,
            set_at=datetime(2026, 11, 1),
        ))
        w.db.add(ProjectImportValueMap(
            company_id=other, kind="project", customer_value_key="CUSTOMER 001 SDN BHD",
            value_key="PROJECT A", value_text="PROJECT A", action="skip",
            set_by_user_id=w.admin_id, set_at=datetime(2026, 11, 1),
        ))
        w.db.flush()
    w.db.commit()

    run = new_run(w, make_book({"JAN'26": BOOK_ROWS}))

    customer = _line(_lines(w, run, "customer"), "CUSTOMER 001 SDN BHD")
    assert customer["status"] == "todo"
    assert customer["target_id"] is None
    assert customer["source"] is None
    project = _line(_lines(w, run, "project"), "PROJECT A", "CUSTOMER 001 SDN BHD")
    assert project["status"] == "todo"
    assert project["action"] in (None, "")


# --------------------------------------------------------------------------- AC-PI-15


def test_ac_pi_15_nothing_is_linked_by_similarity(world):
    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} CUSTOMER ONE")
    w.db.commit()
    first = new_run(w, make_book({"JAN'26": [row("PS26-0001")]}))
    _svc().set_line(w.db, first, kind="customer", value_key="CUSTOMER 001 SDN BHD",
                    action="link", target_id=customer.id, user_id=w.admin_id)
    _svc().set_line(w.db, first, kind="project", customer_value_key="CUSTOMER 001 SDN BHD",
                    value_key="PROJECT 001 SAMPLE NAME", action="skip", user_id=w.admin_id)
    w.db.commit()

    near = make_book({"JAN'26": [
        row("PS26-0002", customer="CUSTOMER 001 SDN BHE"),  # one letter
        row("PS26-0003", customer="CUSTOMER 001"),  # prefix
        row("PS26-0004", customer="CUSTOMER 001 SDN BHD (KL)"),  # contains
        row("PS26-0005", customer="CUSTOMER 001 SDN. BHD."),  # punctuation
        # Same project text under a DIFFERENT customer is a different pair.
        row("PS26-0006", customer="CUSTOMER 009 SDN BHD", project_name="PROJECT 001 SAMPLE NAME"),
        # One letter off on the project under the SAME customer.
        row("PS26-0007", project_name="PROJECT 001 SAMPLE NAMES",
            customer="CUSTOMER 001 SDN BHE"),
    ]})
    run = new_run(w, near)

    customers = {l["value_key"]: l for l in _lines(w, run, "customer")}
    for key in ("CUSTOMER 001 SDN BHE", "CUSTOMER 001", "CUSTOMER 001 SDN BHD (KL)",
                "CUSTOMER 001 SDN. BHD.", "CUSTOMER 009 SDN BHD"):
        assert customers[key]["status"] == "todo", key
        assert customers[key]["target_id"] is None, key
    assert "CUSTOMER 001 SDN BHD" not in customers
    for l in _lines(w, run, "project"):
        assert l["status"] == "todo", (l["customer_value_key"], l["value_key"])


# --------------------------------------------------------------------------- AC-PI-16


def test_ac_pi_16_setting_a_line_stores_or_replaces_one_map_row(world):
    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} CUSTOMER ONE")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": BOOK_ROWS}))

    out = _svc().set_line(w.db, run, kind="customer", value_key="CUSTOMER 001 SDN BHD",
                          action="link", target_id=customer.id, user_id=w.admin_id)
    assert out["status"] == "set"
    rows = _map_rows(w, kind="customer", value_key="CUSTOMER 001 SDN BHD")
    assert len(rows) == 1
    assert str(rows[0].company_id) == w.company_id
    assert rows[0].customer_value_key == ""
    assert rows[0].set_by_user_id == w.admin_id
    assert rows[0].set_at is not None

    _svc().set_line(w.db, run, kind="customer", value_key="CUSTOMER 001 SDN BHD",
                    action="skip", user_id=w.admin_id)
    rows = _map_rows(w, kind="customer", value_key="CUSTOMER 001 SDN BHD")
    assert len(rows) == 1
    assert rows[0].action == "skip"
    assert rows[0].target_id is None


@pytest.mark.parametrize(
    "kind,value_key,customer_value_key,action",
    [
        ("customer", "CUSTOMER 001 SDN BHD", "", "create"),
        ("customer", "CUSTOMER 001 SDN BHD", "", "none"),
        ("project", "PROJECT A", "CUSTOMER 001 SDN BHD", "none"),
        ("developer", "DEVELOPER 001", "", "skip"),
        ("person", "ALVIN", "", "create"),
        ("person", "ALVIN", "", "skip"),
        ("customer", "CUSTOMER 001 SDN BHD", "", "explode"),
    ],
)
def test_ac_pi_16_actions_outside_the_table_are_refused(
    world, kind, value_key, customer_value_key, action
):
    from app.services.error_handler import AppException

    run = new_run(world, make_book({"JAN'26": BOOK_ROWS}))
    with pytest.raises(AppException) as excinfo:
        _svc().set_line(world.db, run, kind=kind, value_key=value_key,
                        customer_value_key=customer_value_key, action=action,
                        new_title="X" if action == "create" else None,
                        user_id=world.admin_id)
    assert excinfo.value.status_code == 422
    assert _map_rows(world, kind=kind, value_key=value_key) == []


def test_ac_pi_16_allowed_actions_per_kind_are_accepted(world):
    w = world
    customer = seed_customer(w.db, w.company_id, f"{MARKER} CUSTOMER ONE")
    party = seed_party(w.db, w.company_id, f"{MARKER} DEV PARTY")
    project = seed_project(w.db, w.company_id, w.admin_id, f"{MARKER} EXISTING TOWER")
    person = seed_user(w.db, f"{MARKER} Alvin")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": BOOK_ROWS}))
    s = _svc()

    s.set_line(w.db, run, kind="customer", value_key="CUSTOMER 001 SDN BHD", action="link",
               target_id=customer.id, user_id=w.admin_id)
    s.set_line(w.db, run, kind="customer", value_key="CUSTOMER 002 SDN BHD", action="skip",
               user_id=w.admin_id)
    s.set_line(w.db, run, kind="project", customer_value_key="CUSTOMER 001 SDN BHD",
               value_key="PROJECT A", action="link", target_id=project.id, user_id=w.admin_id)
    s.set_line(w.db, run, kind="project", customer_value_key="CUSTOMER 002 SDN BHD",
               value_key="PROJECT A", action="create", new_title="PROJECT A TOWER",
               user_id=w.admin_id)
    s.set_line(w.db, run, kind="developer", value_key="DEVELOPER 001", action="link",
               target_id=party.id, user_id=w.admin_id)
    s.set_line(w.db, run, kind="person", value_key="ALVIN", action="link", target_id=person,
               user_id=w.admin_id)
    s.set_line(w.db, run, kind="person", value_key="KATE", action="none", user_id=w.admin_id)
    w.db.commit()

    assert len(_map_rows(w)) == 7
    pair = _line(_lines(w, run, "project"), "PROJECT A", "CUSTOMER 002 SDN BHD")
    assert pair["action"] == "create"
    assert pair["new_title"] == "PROJECT A TOWER"
    dev = _line(_lines(w, run, "developer"), "DEVELOPER 001")
    assert dev["target_id"] == party.id
    assert dev["target_label"] == f"{MARKER} DEV PARTY"


def test_ac_pi_16_project_create_needs_a_new_title(world):
    from app.services.error_handler import AppException

    run = new_run(world, make_book({"JAN'26": BOOK_ROWS}))
    with pytest.raises(AppException) as excinfo:
        _svc().set_line(world.db, run, kind="project", customer_value_key="CUSTOMER 001 SDN BHD",
                        value_key="PROJECT A", action="create", new_title="   ",
                        user_id=world.admin_id)
    assert excinfo.value.status_code == 422


@pytest.mark.parametrize("kind", ["customer", "project", "developer"])
def test_ac_pi_16_a_link_to_another_companys_record_is_refused(world, kind):
    from app.models.base import company_scope
    from app.services import project_seed_service
    from app.services.error_handler import AppException

    w = world
    other = seed_company(w.db, "Other")
    with company_scope(w.db, frozenset({other})):
        project_seed_service.run(w.db, company_id=other)
        target = {
            "customer": lambda: seed_customer(w.db, other, f"{MARKER} SECRET CUSTOMER").id,
            "project": lambda: seed_project(w.db, other, w.admin_id, f"{MARKER} SECRET TOWER").id,
            "developer": lambda: seed_party(w.db, other, f"{MARKER} SECRET DEV").id,
        }[kind]()
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": BOOK_ROWS}))
    keys = {
        "customer": ("", "CUSTOMER 001 SDN BHD"),
        "project": ("CUSTOMER 001 SDN BHD", "PROJECT A"),
        "developer": ("", "DEVELOPER 001"),
    }[kind]

    with pytest.raises(AppException) as excinfo:
        _svc().set_line(w.db, run, kind=kind, customer_value_key=keys[0], value_key=keys[1],
                        action="link", target_id=target, user_id=w.admin_id)
    assert excinfo.value.status_code == 422
    # AC-PI-41: the refusal does not name the other company's record.
    assert "SECRET" not in str(getattr(excinfo.value, "message", excinfo.value))
    assert _map_rows(w, kind=kind) == []


# --------------------------------------------------------------------------- AC-PI-17


def test_ac_pi_17_bulk_calls_set_line_once_per_line(world, monkeypatch):
    w = world
    s = _svc()
    run = new_run(w, make_book({"JAN'26": BOOK_ROWS}))
    calls = []
    real = s.set_line

    def counting(*args, **kwargs):
        calls.append(kwargs.get("value_key"))
        return real(*args, **kwargs)

    monkeypatch.setattr(s, "set_line", counting)
    out = s.bulk_set(w.db, run, kind="customer",
                     keys=[("", "CUSTOMER 001 SDN BHD"), ("", "CUSTOMER 002 SDN BHD")],
                     action="skip", user_id=w.admin_id)

    assert sorted(calls) == ["CUSTOMER 001 SDN BHD", "CUSTOMER 002 SDN BHD"]
    assert len(out) == 2
    assert {r.action for r in _map_rows(w, kind="customer")} == {"skip"}


def test_ac_pi_17_bulk_is_all_or_nothing_and_names_the_bad_line(world):
    from app.services.error_handler import AppException

    w = world
    project = seed_project(w.db, w.company_id, w.admin_id, f"{MARKER} BULK TOWER")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": BOOK_ROWS}))

    with pytest.raises(AppException) as excinfo:
        _svc().bulk_set(
            w.db, run, kind="project",
            keys=[
                ("CUSTOMER 001 SDN BHD", "PROJECT A"),
                ("CUSTOMER 002 SDN BHD", "PROJECT A"),
                ("CUSTOMER 777 SDN BHD", "NOT IN THIS FILE"),
            ],
            action="link", target_id=project.id, user_id=w.admin_id,
        )
    assert excinfo.value.status_code == 422
    assert "NOT IN THIS FILE" in str(getattr(excinfo.value, "message", excinfo.value)).upper()
    assert _map_rows(w, kind="project") == []
    assert all(l["status"] == "todo" for l in _lines(w, run, "project"))


# --------------------------------------------------------------------------- AC-PI-18


def test_ac_pi_18_the_to_do_count_equals_the_to_do_filter(world):
    w = world
    run = new_run(w, make_book({"JAN'26": BOOK_ROWS}))
    s = _svc()

    for kind in ("customer", "project", "developer", "person"):
        every = _lines(w, run, kind)
        todo = _lines(w, run, kind, status="todo")
        assert len(todo) == sum(1 for l in every if l["status"] == "todo"), kind
        assert all(l["status"] == "todo" for l in todo)

    s.set_line(w.db, run, kind="person", value_key="KATE", action="none", user_id=w.admin_id)
    todo = _lines(w, run, "person", status="todo")
    done = _lines(w, run, "person", status="set")
    assert len(todo) == 3
    assert [l["value_key"] for l in done] == ["KATE"]


# --------------------------------------------------------------------------- AC-PI-19


def _so_book():
    return make_book({"JAN'26": [
        row("PS26-0001", customer="CUSTOMER 010 SDN BHD", so_number="SO410001"),
        row("PS26-0002", customer="CUSTOMER 010 SDN BHD", so_number="SO410002, SO410003"),
        row("PS26-0003", customer="CUSTOMER 011 SDN BHD", so_number="SO410004"),
        row("PS26-0004", customer="CUSTOMER 011 SDN BHD", so_number="SO499999"),  # not synced
    ]})


def test_ac_pi_19_a_customer_whose_sos_resolve_to_one_customer_reads_from_so(world):
    w = world
    x = seed_customer(w.db, w.company_id, f"{MARKER} SO CUSTOMER")
    y = seed_customer(w.db, w.company_id, f"{MARKER} OTHER SO CUSTOMER")
    for so in ("SO410001", "SO410002", "SO410003"):
        seed_core_so(w.db, w.company_id, so, x)
    seed_core_so(w.db, w.company_id, "SO410004", y)
    w.db.commit()

    run = new_run(w, _so_book())
    lines = _lines(w, run, "customer")

    from_so = _line(lines, "CUSTOMER 010 SDN BHD")
    assert from_so["source"] == "so"
    assert from_so["status"] == "set"
    assert from_so["target_id"] == x.id
    # One of CUSTOMER 011's SOs is not synced: not every SO resolves, so a human decides.
    partial = _line(lines, "CUSTOMER 011 SDN BHD")
    assert partial["source"] is None
    assert partial["status"] == "todo"
    assert partial in _lines(w, run, "customer", status="todo")


def test_ac_pi_19_sos_of_another_company_do_not_resolve(world):
    from app.models.base import company_scope

    w = world
    other = seed_company(w.db, "Other")
    with company_scope(w.db, frozenset({other})):
        foreign = seed_customer(w.db, other, f"{MARKER} FOREIGN")
        for so in ("SO410001", "SO410002", "SO410003"):
            seed_core_so(w.db, other, so, foreign)
    w.db.commit()

    run = new_run(w, _so_book())
    line = _line(_lines(w, run, "customer"), "CUSTOMER 010 SDN BHD")
    assert line["source"] is None
    assert line["status"] == "todo"


def _so_conflict_world(w, *, same_shop: str):
    """X = the SO customer; mapped = what a person picked for the line."""
    if same_shop == "group":
        group = seed_group(w.db, w.company_id, f"{MARKER} SHOP GROUP")
        x = seed_customer(w.db, w.company_id, f"{MARKER} NORTH ACCOUNT", group_id=group)
        mapped = seed_customer(w.db, w.company_id, f"{MARKER} SOUTH ACCOUNT", group_id=group)
    elif same_shop == "family":
        x = seed_customer(w.db, w.company_id, "ZZT ALPHA BUILDERS SDN BHD")
        mapped = seed_customer(w.db, w.company_id, "ZZT ALPHA BUILDERS (M) SDN BHD")
    else:
        x = seed_customer(w.db, w.company_id, "ZZT ALPHA BUILDERS SDN BHD")
        mapped = seed_customer(w.db, w.company_id, "ZZT OMEGA HARDWARE SDN BHD")
    seed_core_so(w.db, w.company_id, "SO420001", x)
    project = seed_project(w.db, w.company_id, w.admin_id, f"{MARKER} CONFLICT TOWER")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": [
        row("PS26-0001", customer="CUSTOMER 020 SDN BHD", project_name="PROJECT C",
            so_number="SO420001"),
    ]}))
    s = _svc()
    s.set_line(w.db, run, kind="customer", value_key="CUSTOMER 020 SDN BHD", action="link",
               target_id=mapped.id, user_id=w.admin_id)
    s.set_line(w.db, run, kind="project", customer_value_key="CUSTOMER 020 SDN BHD",
               value_key="PROJECT C", action="link", target_id=project.id, user_id=w.admin_id)
    s.set_line(w.db, run, kind="person", value_key="ALVIN", action="none", user_id=w.admin_id)
    s.set_line(w.db, run, kind="person", value_key="KATE", action="none", user_id=w.admin_id)
    w.db.commit()
    return run, x, mapped


@pytest.mark.parametrize("same_shop", ["group", "family"])
def test_ac_pi_19_same_shop_uses_the_so_customer(world, same_shop):
    run, x, _mapped = _so_conflict_world(world, same_shop=same_shop)

    report = _svc().preview(world.db, run, user_id=world.admin_id)

    r = report["rows"][0]
    assert r["outcome"] != "needs_review", r
    assert "customer_same_shop_so_used" in r["codes"]
    assert "customer_conflict" not in r["codes"]
    assert report["codes"].get("customer_same_shop_so_used") == 1


def test_ac_pi_19_a_different_shop_is_a_customer_conflict(world):
    run, _x, _mapped = _so_conflict_world(world, same_shop="no")

    report = _svc().preview(world.db, run, user_id=world.admin_id)

    r = report["rows"][0]
    assert r["outcome"] == "needs_review"
    assert "customer_conflict" in r["codes"]
    assert report["counts"].get("created", 0) == 0
    assert report["counts"].get("updated", 0) == 0
