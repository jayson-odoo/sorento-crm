"""SALES-SPLIT-TALLY: the read-only SQL the owner runs on prod says what it claims.

`documentation/plans/sales/evidence/sales-split-tally-owner-sql-28oct.md` R9 (class-data dry run
and its held apply) and R10 (every gap against AutoCount, DATA or GENUINE) are run here as
written, on seeded fictional documents, with the placeholder codes filled the way crew fills
them. The SQL names its schemas (`public.`, `finance.`, `sales.`), so this runs on the real
schemas inside a transaction that is rolled back (`pg_session`), never a scratch schema.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.main import app  # noqa: F401  (import order)
from app.models.finance import BillingDocument
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import pg_session, unique_code
from tests._sales_unified_seed import agent, cust, doc, line, so

SQL_DOC = (
    Path(__file__).resolve().parents[2]
    / "documentation/plans/sales/evidence/sales-split-tally-owner-sql-28oct.md"
)
JAN15 = date(2026, 1, 15)
D = Decimal


def _blocks(heading: str) -> list[str]:
    """The ```sql blocks under the markdown heading that starts with `heading`."""
    body = SQL_DOC.read_text()
    start = body.index(f"\n## {heading}") if f"\n## {heading}" in body else body.index(f"\n### {heading}")
    nxt = re.search(r"\n#{1,3} ", body[start + 1:])
    section = body[start: start + 1 + nxt.start()] if nxt else body[start:]
    return re.findall(r"```sql\n(.*?)```", section, re.S)


def _statements(block: str, fills: dict[str, str]) -> list[str]:
    """The block's statements, placeholders filled, without the transaction lines (the test's
    own transaction is the one rolled back). Split on `;` outside quotes, `$$` bodies and
    comments."""
    for placeholder, value in fills.items():
        block = block.replace(placeholder, value)
    out, current, quoted, dollar, i = [], [], False, False, 0
    while i < len(block):
        ch = block[i]
        if not quoted and block.startswith("$$", i):
            dollar = not dollar
            current.append("$$")
            i += 2
            continue
        if not quoted and not dollar and block.startswith("--", i):
            i = block.find("\n", i) if "\n" in block[i:] else len(block)
            continue
        if ch == "'" and not dollar:
            quoted = not quoted
        if ch == ";" and not quoted and not dollar:
            out.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        i += 1
    out.append("".join(current).strip())
    skip = re.compile(r"^(BEGIN( READ ONLY)?|ROLLBACK|COMMIT)$", re.I)
    return [s for s in out if s and not skip.match(s)]


@pytest.fixture
def db():
    with pg_session() as s:
        if s.execute(text("SELECT count(*) FROM finance.billing_documents bd JOIN companies c "
                          "ON c.id = bd.company_id WHERE c.code = 'SRT' AND bd.doc_date "
                          ">= '2026-01-01' AND bd.doc_date < '2026-02-01'")).scalar():
            pytest.skip("this database holds real January 2026 SRT documents")
        yield s


@pytest.fixture
def seeded(db):
    dealer = agent(db, unique_code("AG") + " IV", demand_class="retail")
    project = agent(db, unique_code("AG"), demand_class="project")
    left_out = agent(db, unique_code("AG"), demand_class="retail")  # AutoCount: left out
    set_apart = cust(db, code=unique_code("DEB")[:40])
    fills = {f"<OTHER {i}>": left_out.sales_agent.upper() for i in range(1, 6)}
    fills.update({f"<DEBTOR {i}>": set_apart.customer_code.upper() for i in range(1, 5)})

    def order(cls, who, order_type=None):
        header, (so_line,) = so(db, demand_class=cls)
        header.sales_agent_id, header.order_date, header.order_type = who.id, JAN15, order_type
        db.flush()
        return so_line

    def invoice(net, who, so_line=None, customer=None):
        row = doc(db, "invoice", net, JAN15, agent_row=who, customer=customer,
                  lines=[line(so_line=so_line)] if so_line else None)
        if customer is not None:
            row.debtor_code = customer.customer_code
            db.flush()
        return row

    invoice("100.00", dealer, order("retail", dealer))                    # 1 match
    invoice("50.00", dealer)                                              # 3 no SO
    invoice("30.00", left_out, order("retail", left_out))                 # 7 agent class
    invoice("20.00", dealer, order("project", dealer, "Project"))         # 4 stated type
    invoice("10.00", project, order("retail", dealer))                    # 5 other agent
    invoice("5.00", project, order("retail", project))                    # 6 stale SO class
    invoice("7.00", dealer, order("retail", dealer), customer=set_apart)  # 2 set apart
    return fills, dealer, project, left_out


def _r10(db, fills):
    (block,) = _blocks("R10.")
    *setup, query = _statements(block, fills)
    for statement in setup:
        db.execute(text(statement))
    return {
        row.reason: (row.ac_block, row.crm_block, row.docs, row.rm)
        for row in db.execute(text(query))
    }


def test_r10_names_the_first_reason_for_every_gap(db, seeded):
    fills, *_ = seeded
    assert _r10(db, fills) == {
        "1 match": ("dealer", "dealer", 1, D("100.00")),
        "2 set-apart debtor not entered": ("set_apart", "dealer", 1, D("7.00")),
        "3 no sales order traced": ("dealer", "no_sales_order", 1, D("50.00")),
        "4 SO states an order type of the other kind": ("dealer", "project", 1, D("20.00")),
        "5 SO sold by another agent than the invoice": ("project", "dealer", 1, D("10.00")),
        "6 SO class stale": ("project", "dealer", 1, D("5.00")),
        "7 SO agent's class is not AutoCount's list": ("left_out", "dealer", 1, D("30.00")),
    }


def test_r9_dry_run_proposes_autocounts_lists_and_sums_them(db, seeded):
    fills, dealer, project, left_out = seeded
    per_agent, per_class = _blocks("R9.")[0], None
    statements = _statements(per_agent, fills)
    rows = {r.sales_agent: (r.proposed, r.action) for r in db.execute(text(statements[0]))}
    assert rows[dealer.sales_agent] == ("retail", "change")  # no dated row yet
    assert rows[project.sales_agent] == ("project", "change")
    assert rows[left_out.sales_agent] == ("other", "change")
    per_class = {r.proposed: r.rm for r in db.execute(text(statements[1]))}
    assert per_class == {"retail": D("177.00"), "project": D("15.00"), "other": D("30.00")}


def test_r9_apply_writes_one_open_row_and_the_mirror_then_the_dry_run_reads_no_change(db, seeded):
    fills, dealer, project, left_out = seeded
    (apply_block,) = _blocks("R9 apply")
    for statement in _statements(apply_block, fills):
        db.execute(text(statement))
    statements = _statements(_blocks("R9.")[0], fills)
    rows = {r.sales_agent: (r.proposed, r.action) for r in db.execute(text(statements[0]))}
    for who, cls in ((dealer, "retail"), (project, "project"), (left_out, "other")):
        assert rows[who.sales_agent] == (cls, "no change")
        assert db.execute(text("SELECT demand_class FROM sales_agents WHERE id = :i"), {"i": who.id}).scalar() == cls
    assert db.query(BillingDocument).filter(BillingDocument.company_id == DEFAULT_COMPANY_ID).count() == 7


# ------------------------------------------------- incident 29 Oct: R9 apply run unfilled


@pytest.fixture
def five_left_out(db):
    """Five left-out agents (two with no class row, three `retail` with one row, as prod had
    them), one more agent the lists put on `project`, each with a January document."""
    from app.models.sales import SalesAgentClass

    agents = []
    for n in range(5):
        row = agent(db, unique_code("AG"), demand_class=None if n < 2 else "retail")
        if n >= 2:
            db.add(SalesAgentClass(sales_agent_id=row.id, demand_class="retail"))
        agents.append(row)
    to_project = agent(db, unique_code("AG"), demand_class="retail")
    db.add(SalesAgentClass(sales_agent_id=to_project.id, demand_class="retail"))
    db.flush()
    for row in agents + [to_project]:
        doc(db, "invoice", "10.00", JAN15, agent_row=row)
    fills = {f"<OTHER {n + 1}>": row.sales_agent.upper() for n, row in enumerate(agents)}
    fills.update({"<PROJECT 1>": to_project.sales_agent.upper(), "<NONE 1>": "ZZT-NONE"})
    return fills, agents, to_project


def _classes(db, rows):
    """Each agent's mirror and class rows, straight from the tables."""
    return {
        row.sales_agent: (
            db.execute(text("SELECT demand_class FROM sales_agents WHERE id = :i"), {"i": row.id}).scalar(),
            [tuple(x) for x in db.execute(text(
                "SELECT demand_class, from_month, to_month FROM sales.agent_classes "
                "WHERE sales_agent_id = :i"), {"i": row.id})],
        )
        for row in rows
    }


def test_incident_the_apply_with_unfilled_placeholders_is_refused_and_writes_nothing(db, five_left_out):
    _fills, agents, to_project = five_left_out
    before = _classes(db, agents + [to_project])
    (apply_block,) = _blocks("R9 apply")
    guard, *_rest = _statements(apply_block, {})
    savepoint = db.begin_nested()
    with pytest.raises(Exception, match="fill every <OTHER n>"):
        db.execute(text(guard))
    savepoint.rollback()
    assert _classes(db, agents + [to_project]) == before


def test_incident_r11_sees_the_unfilled_apply_and_the_correction_moves_the_five_to_other(db, five_left_out):
    fills, agents, to_project = five_left_out
    # The incident: the apply as it stood before the guard, placeholders unfilled.
    _guard, *unfilled_apply = _statements(_blocks("R9 apply")[0], {})
    for statement in unfilled_apply:
        db.execute(text(statement))

    d1, *_rest = _statements(_blocks("R11.")[0], fills)
    landed = {r.sales_agent: (r.mirror_now, r.class_rows, r.rows_now.split(" created")[0])
              for r in db.execute(text(d1))}
    for row in agents + [to_project]:
        assert landed[row.sales_agent] == ("project", 1, "project start..open")

    for statement in _statements(_blocks("R11 correction")[0], fills)[:-1]:
        db.execute(text(statement))
    after = _classes(db, agents + [to_project])
    for row in agents:
        assert after[row.sales_agent] == ("other", [("other", None, None)])
    assert after[to_project.sales_agent] == ("project", [("project", None, None)])


def test_incident_the_correction_writes_nothing_unless_all_five_codes_name_an_agent(db, five_left_out):
    fills, agents, _to_project = five_left_out
    fills["<OTHER 5>"] = "ZZT-NO-SUCH-AGENT"
    before = _classes(db, agents)
    guard = _statements(_blocks("R11 correction")[0], fills)[0]
    savepoint = db.begin_nested()
    with pytest.raises(Exception, match="expected 5 agents, found 4"):
        db.execute(text(guard))
    savepoint.rollback()
    assert _classes(db, agents) == before
