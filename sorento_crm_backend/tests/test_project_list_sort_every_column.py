"""Every Projects grid column sorts on the SERVER (owner, PROJECTS-BOARD-VIEW-PREF fix round).

Owner rule 27 Oct: every grid column sorts server-side. The derived columns sort on what
the row displays: Developer and Owner by name, Stage by its place in the status graph
(not alphabetically), Estimated by amount, Next action by the earliest open task's due
date with "Nothing open" last, Flags by Critical. Blanks sort last in both directions.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.projects import Project, ProjectParty, ProjectSalesProfile, ProjectTask
from app.models.status import Status
from app.models.user import User
from app.services import project_service

from ._pg_fixture import blank_session


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def seeded():
    with blank_session() as db:
        company = db.execute(text("select id from companies where code = 'SRT'")).scalar()
        # Stage labels chosen so alphabetical order != graph order.
        stages = {}
        for order, (key, label) in enumerate(
            [("zz_identified", "Zebra start"), ("zz_quoted", "Middle"), ("zz_won", "Alpha end")]
        ):
            st = Status(id=_uid(), entity_type="project", key=key, label=label, sort_order=order)
            db.add(st)
            stages[key] = st.id
        open_task = Status(
            id=_uid(), entity_type="project_task", key="zz_open", label="Open", sort_order=0
        )
        db.add(open_task)
        users = {}
        for name in ["charlie", "Alice", "bob"]:
            uid = _uid()
            db.add(User(id=uid, email=f"{uid}@zzt.test", name=name))
            users[name] = uid
        devs = {}
        for name in ["Beta Dev", "alpha dev", "Gamma Dev"]:
            party = ProjectParty(id=_uid(), company_id=company, party_type="developer", name=name)
            db.add(party)
            devs[name] = party.id
        db.flush()

        def project(title, **kw):
            p = Project(
                id=_uid(), company_id=company, title=title, normalised_title=title.lower(), **kw
            )
            db.add(p)
            db.flush()
            return p

        a = project("A", developer_party_id=devs["Beta Dev"], owner_user_id=users["charlie"],
                    status_id=stages["zz_won"], is_critical=True)
        b = project("B", developer_party_id=devs["alpha dev"], owner_user_id=users["Alice"],
                    status_id=stages["zz_identified"])
        c = project("C", developer_party_id=devs["Gamma Dev"], owner_user_id=users["bob"],
                    status_id=stages["zz_quoted"])
        d = project("D")  # blanks everywhere, nothing open
        for p, amount in [(a, "300"), (b, "1000"), (c, "20")]:
            db.add(ProjectSalesProfile(project_id=p.id, estimated_sales_value=Decimal(amount)))
        # Next action: B due earliest, A later, C open but undated, D nothing open.
        db.add(ProjectTask(project_id=b.id, name="t", status_id=open_task.id, due_date=date(2026, 1, 5)))
        db.add(ProjectTask(project_id=b.id, name="t2", status_id=open_task.id, due_date=date(2026, 3, 1)))
        db.add(ProjectTask(project_id=a.id, name="t", status_id=open_task.id, due_date=date(2026, 2, 1)))
        db.add(ProjectTask(project_id=c.id, name="t", status_id=open_task.id))
        db.flush()
        yield db, company, [a.id, b.id, c.id, d.id]


def _titles(db, company, ids, sort, direction):
    rows, total = project_service.list_projects(
        db, company_id=company, project_ids=ids, sort=sort, direction=direction, limit=50
    )
    assert total == len(ids)  # the sort join never duplicates or drops a project
    return [r.title for r in rows]


@pytest.mark.parametrize(
    "sort, asc, desc",
    [
        # Name, case-insensitive; blank last both ways.
        ("developer_name", ["B", "A", "C", "D"], ["C", "A", "B", "D"]),
        ("owner_name", ["B", "C", "A", "D"], ["A", "C", "B", "D"]),
        # Graph order (Zebra start < Middle < Alpha end), not alphabetical.
        ("status_label", ["B", "C", "A", "D"], ["A", "C", "B", "D"]),
        # Amount, numerically (1000 > 300 > 20, not string order).
        ("estimated_sales_value", ["C", "A", "B", "D"], ["B", "A", "C", "D"]),
        # Dated by earliest due date, then open-undated, then nothing open, both ways.
        ("next_action", ["B", "A", "C", "D"], ["A", "B", "C", "D"]),
    ],
)
def test_derived_column_sorts_server_side(seeded, sort, asc, desc):
    db, company, ids = seeded
    assert _titles(db, company, ids, sort, "asc") == asc
    assert _titles(db, company, ids, sort, "desc") == desc


def test_flags_sort_puts_critical_first_descending(seeded):
    db, company, ids = seeded
    assert _titles(db, company, ids, "flags", "desc")[0] == "A"
    assert _titles(db, company, ids, "flags", "asc")[-1] == "A"


def test_sorted_pages_do_not_overlap(seeded):
    db, company, ids = seeded
    seen = []
    for page in (1, 2):
        rows, _ = project_service.list_projects(
            db, company_id=company, project_ids=ids, sort="flags", direction="asc",
            page=page, limit=2,
        )
        seen += [r.id for r in rows]
    assert sorted(seen) == sorted(ids)
