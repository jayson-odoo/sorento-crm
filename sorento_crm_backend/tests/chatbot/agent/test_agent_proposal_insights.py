"""AGENT-PROPOSAL-INSIGHTS red tests (UAC sections A to F; G is the existing suite, H is a live run).

A  `prepared_by` per document (tool) and per row (`serialize_quotations`): the document's creator, never the owner
B  per document facts: line_count, no_charge_lines, repeated_codes, rate_only_lines, empty
C  `comparison` (2+ documents): totals, only_in, shared, scopes_only_in, scope_totals, caps, built before `_fit`
D  vs_list "no charge"; the tool description no longer prescribes a format
E  the agent prompt fallback: COMPARING, Prepared By rule, analysis allowed; the bump migration
F  DEFAULT_EFFORT is "medium"

Postgres only (`blank_session`); every row is seeded here with fake prices. Expected values are worked out by hand
in the comments next to the seed.
"""
from __future__ import annotations

import ast
import json
import re
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.services.company_scope import register_company_scope_listeners
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent.test_agent_quote_compare import _doc, _lines

BACKEND = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    yield


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _uid() -> str:
    return str(uuid.uuid4())


def _f(value):
    return None if value is None else round(float(value), 2)


# ------------------------------------------------------------------ seeding


class Builder:
    """A project in company SRT, owned by `owner`, with helpers to add documents, scopes and lines."""

    def __init__(self, db, owner_name="ZZT Project Owner"):
        from sqlalchemy import text

        from app.models.base import company_scope
        from app.models.projects import Project
        from app.models.user import User
        from app.services import project_seed_service
        from app.services.project_service import register_project

        self.db = db
        self.company_id = str(db.execute(text("select id from companies where code = 'SRT'")).scalar())
        project_seed_service.run(db, company_id=self.company_id)
        self.owner = self.user(owner_name)
        with company_scope(db, frozenset({self.company_id})):
            project = register_project(
                db, company_id=self.company_id, actor_user_id=self.owner, developer_party_id=None,
                title=f"ZZT Insights {unique_code('p')}",
            )
            db.query(Project).filter(Project.id == project.id).update({"owner_user_id": self.owner})
            db.flush()
        self.project_id = str(project.id)
        self._doc_seq = 0
        self._scope_seq = 0
        self._line_seq = 0

    def scoped(self):
        from app.models.base import company_scope

        return company_scope(self.db, frozenset({self.company_id}))

    def user(self, name):
        from app.models.user import User

        uid = _uid()
        self.db.add(User(id=uid, email=f"{uid}@zzt.test", name=name))
        self.db.flush()
        return uid

    def doc(self, prefix, created_by):
        from app.models.projects import ProjectQuotationDocument

        self._doc_seq += 1
        no = unique_code(prefix)
        with self.scoped():
            row = ProjectQuotationDocument(
                company_id=self.company_id, project_id=self.project_id, document_no=no, created_by=created_by,
                created_at=datetime(2026, 1, 1, 9, 0, self._doc_seq),
            )
            self.db.add(row)
            self.db.flush()
            self.db.refresh(row)
            assert row.created_by == created_by, "a listener rewrote created_by: the seed is wrong, not the code"
        return row

    def scope(self, doc, label, lines, version_total=None):
        """`lines`: (code, qty, list_price, unit, total, uom, rate_only). Version 1, total = sum of line totals."""
        from app.models.projects import ProjectQuotation, ProjectQuotationLine, ProjectQuotationVersion

        self._scope_seq += 1
        total = version_total if version_total is not None else sum((Decimal(ln[4]) for ln in lines), Decimal("0"))
        with self.scoped():
            q = ProjectQuotation(
                company_id=self.company_id, project_id=self.project_id, document_id=doc.id, scope_label=label,
                sort_order=self._scope_seq,
            )
            self.db.add(q)
            self.db.flush()
            v = ProjectQuotationVersion(company_id=self.company_id, quotation_id=q.id, version_no=1,
                                        total_amount=Decimal(total))
            self.db.add(v)
            self.db.flush()
            for code, qty, listed, unit, line_total, uom, rate_only in lines:
                self._line_seq += 1
                self.db.add(ProjectQuotationLine(
                    company_id=self.company_id, version_id=v.id, product_code_snapshot=code,
                    description_snapshot=f"{code} item", quantity=Decimal(qty),
                    list_price_snapshot=None if listed is None else Decimal(listed), unit_price=Decimal(unit),
                    line_total=Decimal(line_total), uom=uom, sort_order=self._line_seq, is_rate_only=rate_only,
                ))
            self.db.flush()
        return q, v


def L(code, qty, listed, unit, total, uom="UNIT", rate_only=False):  # noqa: N802
    return (code, qty, listed, unit, total, uom, rate_only)


def _owner_case(db):
    """The owner's case shape (plan section C.1), fake prices.

    D1 (Quoter One)  UNIT: SRTWC8518-SH 1 x 240.90 (list 945.35); CB310-CR-PJ 1 x 10.95 (no list)
                     total 251.85, 2 lines
    D2 (Quoter One)  UNIT (10 lines, total 2267.45):
                       SRTWHBWP 6 x 65.70 = 394.20, twice
                       SRTWT907SS 6 x 0 (list 27.74) = 0          no charge
                       SRTWT907SS 5 x 0.73 = 3.65
                       SRTWC8518-SH 6 x 240.90 = 1445.40
                       ZZT-NC-A 2 x 0 (list 50) = 0                no charge
                       ZZT-NC-B 1 x 0 (list 12) = 0                no charge
                       ZZT-ZERO-QTY 0 x 0 (list 30) = 0            qty 0: NOT no charge
                       ZZT-RATE 1 x 0 (list 20) rate only = 0      rate only: NOT no charge
                       SRT73-CR 2 SET x 15.00 = 30.00 (no list)
                     LEVEL 9: ZZT-L9 1 x 100.00 ; Guard House: ZZT-L9 1 x 50.00  (repeated across scopes)
                     total 2417.45, 12 lines
    D3 (Quoter Two)  UNIT: SRTWC8518-SH 1 x 219.00; CB310-CR-PJ 2 x 10.95 = 21.90; SRTWT907SS 11 x 0.50 = 5.50
                     total 246.40, 3 lines
    D4 (Quoter One)  no scopes
    """
    b = Builder(db)
    one, two = b.user("ZZT Quoter One"), b.user("ZZT Quoter Two")
    d1 = b.doc("PRJQ-D1", one)
    d2 = b.doc("PRJQ-D2", one)
    d3 = b.doc("PRJQ-D3", two)
    d4 = b.doc("PRJQ-D4", one)
    _q1, v1 = b.scope(d1, "UNIT", [
        L("SRTWC8518-SH", "1", "945.35", "240.90", "240.90"),
        L("CB310-CR-PJ", "1", None, "10.95", "10.95"),
    ])
    b.scope(d2, "UNIT", [
        L("SRTWHBWP", "6", "80.00", "65.70", "394.20"),
        L("SRTWHBWP", "6", "80.00", "65.70", "394.20"),
        L("SRTWT907SS", "6", "27.74", "0", "0"),
        L("SRTWT907SS", "5", "27.74", "0.73", "3.65"),
        L("SRTWC8518-SH", "6", "945.35", "240.90", "1445.40"),
        L("ZZT-NC-A", "2", "50.00", "0", "0"),
        L("ZZT-NC-B", "1", "12.00", "0", "0"),
        L("ZZT-ZERO-QTY", "0", "30.00", "0", "0"),
        L("ZZT-RATE", "1", "20.00", "0", "0", rate_only=True),
        L("SRT73-CR", "2", None, "15.00", "30.00", uom="SET"),
    ])
    b.scope(d2, "LEVEL 9", [L("ZZT-L9", "1", None, "100.00", "100.00")])
    b.scope(d2, "Guard House", [L("ZZT-L9", "1", None, "50.00", "50.00")])
    b.scope(d3, "UNIT", [
        L("SRTWC8518-SH", "1", "945.35", "219.00", "219.00"),
        L("CB310-CR-PJ", "2", None, "10.95", "21.90"),
        L("SRTWT907SS", "11", "27.74", "0.50", "5.50"),
    ])
    return SimpleNamespace(
        b=b, company_id=b.company_id, project_id=b.project_id, owner=b.owner, one=one, two=two,
        d1=d1.document_no, d2=d2.document_no, d3=d3.document_no, d4=d4.document_no,
        d1_row=d1, d2_row=d2, d4_row=d4, v1=v1,
    )


def _call(db, w, refs=None):
    args = {"project_id": w.project_id}
    if refs is not None:
        args["refs"] = refs
    out = _lines(db, w, args)
    assert out.status == "ok", (out.status, out.message)
    return out


def _direct(db, w, refs, cap):
    from app.services.chatbot.agent.quotation_lines import project_quotation_lines

    with w.b.scoped():
        return project_quotation_lines(db, w.project_id, refs, cap)


# ================================================================== A. prepared_by


def test_AC_A1_A2_every_document_carries_its_creators_name_never_the_project_owners(db):
    w = _owner_case(db)
    out = _call(db, w)
    docs = out.data["documents"]
    assert [d["ref"] for d in docs] == [w.d1, w.d2, w.d3, w.d4]
    for d in docs:
        assert "prepared_by" in d, d.keys()
    assert _doc(out, w.d1)["prepared_by"] == "ZZT Quoter One"
    assert _doc(out, w.d2)["prepared_by"] == "ZZT Quoter One"
    assert _doc(out, w.d3)["prepared_by"] == "ZZT Quoter Two"
    assert _doc(out, w.d4)["prepared_by"] == "ZZT Quoter One"
    assert all(d["prepared_by"] != "ZZT Project Owner" for d in docs)


def test_AC_A1_an_issued_revision_carries_its_documents_creator(db):
    from app.models.projects import ProjectQuotation, ProjectQuotationIssue, ProjectQuotationIssueScope

    w = _owner_case(db)
    with w.b.scoped():
        q = db.query(ProjectQuotation).filter(ProjectQuotation.document_id == w.d1_row.id).one()
        issue = ProjectQuotationIssue(
            company_id=w.company_id, document_id=w.d1_row.id, issue_no=1, revision_label="A", issued_by=w.owner,
            grand_total=Decimal("251.85"),
        )
        db.add(issue)
        db.flush()
        db.add(ProjectQuotationIssueScope(company_id=w.company_id, issue_id=issue.id, quotation_id=q.id,
                                          version_id=w.v1.id, scope_total=Decimal("251.85"), sort_order=0))
        db.flush()
    ref = f"{w.d1}-A"
    out = _call(db, w, [ref])
    assert [d["ref"] for d in out.data["documents"]] == [ref]
    assert _doc(out, ref).get("prepared_by") == "ZZT Quoter One", _doc(out, ref)


@pytest.mark.parametrize("creator", [None, "unknown"])
def test_AC_A3_no_or_an_unknown_creator_gives_prepared_by_null_with_the_key_present(db, creator):
    from app.models.projects import ProjectQuotationDocument

    w = _owner_case(db)
    with w.b.scoped():
        db.query(ProjectQuotationDocument).filter(ProjectQuotationDocument.id == w.d4_row.id).update(
            {"created_by": None if creator is None else _uid()}
        )
        db.flush()
    out = _call(db, w)
    d4 = _doc(out, w.d4)
    assert "prepared_by" in d4, d4.keys()
    assert d4["prepared_by"] is None


def _users_selects(db, fn):
    from sqlalchemy import event

    engine = db.get_bind()
    seen: list[str] = []

    def listen(conn, cursor, statement, params, context, executemany):
        if re.search(r"\bFROM\s+(\w+\.)?users\b", statement, re.IGNORECASE):
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", listen)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", listen)
    return result, seen


def test_AC_A4_the_quotations_list_rows_carry_their_documents_creator(db):
    from app.models.projects import ProjectQuotation
    from app.services.project_quotation_service import serialize_quotations

    w = _owner_case(db)
    with w.b.scoped():
        scopes = db.query(ProjectQuotation).filter(ProjectQuotation.project_id == w.project_id).all()
        rows = serialize_quotations(db, scopes)
    by_doc = {r["document_no"]: r for r in rows}
    assert len(rows) == 5  # D1 UNIT, D2 UNIT + LEVEL 9 + Guard House, D3 UNIT
    for row in rows:
        assert "prepared_by" in row, row.keys()
    assert {r["prepared_by"] for r in rows if r["document_no"] == w.d2} == {"ZZT Quoter One"}
    assert by_doc[w.d1]["prepared_by"] == "ZZT Quoter One"
    assert by_doc[w.d3]["prepared_by"] == "ZZT Quoter Two"
    assert all(r["prepared_by"] != "ZZT Project Owner" for r in rows)


def test_AC_A4_a_row_whose_document_has_no_creator_has_prepared_by_null(db):
    from app.models.projects import ProjectQuotation, ProjectQuotationDocument
    from app.services.project_quotation_service import serialize_quotations

    w = _owner_case(db)
    with w.b.scoped():
        db.query(ProjectQuotationDocument).filter(ProjectQuotationDocument.id == w.d1_row.id).update(
            {"created_by": None}
        )
        db.flush()
        scopes = db.query(ProjectQuotation).filter(ProjectQuotation.document_id == w.d1_row.id).all()
        rows = serialize_quotations(db, scopes)
    assert len(rows) == 1 and "prepared_by" in rows[0], rows
    assert rows[0]["prepared_by"] is None


def test_AC_A4_user_names_are_read_in_one_query_per_call(db):
    from app.models.projects import ProjectQuotation
    from app.services.project_quotation_service import serialize_quotations

    w = _owner_case(db)
    with w.b.scoped():
        scopes = (
            db.query(ProjectQuotation)
            .filter(ProjectQuotation.document_id.in_([w.d1_row.id, w.d2_row.id]))
            .all()
        )
        assert len(scopes) == 4  # 4 rows from 2 documents (D1, D2), 1 creator
        rows, selects = _users_selects(db, lambda: serialize_quotations(db, scopes))
    assert all("prepared_by" in r for r in rows), [r.keys() for r in rows]
    assert len(selects) == 1, selects


# ================================================================== B. per document facts


def test_AC_B1_to_B5_per_document_facts(db):
    w = _owner_case(db)
    out = _call(db, w)
    expected = {
        w.d1: dict(line_count=2, no_charge_lines=[], repeated_codes=[], rate_only_lines=0, empty=False),
        w.d2: dict(
            line_count=12,
            no_charge_lines=["SRTWT907SS", "ZZT-NC-A", "ZZT-NC-B"],
            repeated_codes=[{"code": "SRTWHBWP", "times": 2}, {"code": "SRTWT907SS", "times": 2},
                            {"code": "ZZT-L9", "times": 2}],
            rate_only_lines=1, empty=False,
        ),
        w.d3: dict(line_count=3, no_charge_lines=[], repeated_codes=[], rate_only_lines=0, empty=False),
        w.d4: dict(line_count=0, no_charge_lines=[], repeated_codes=[], rate_only_lines=0, empty=True),
    }
    for ref, facts in expected.items():
        doc = _doc(out, ref)
        got = {k: doc.get(k, "<missing>") for k in facts}
        assert got == facts, (ref, got)


def test_AC_B2_a_qty_0_line_at_0_and_a_rate_only_line_at_0_are_not_no_charge(db):
    w = _owner_case(db)
    d2 = _doc(_call(db, w), w.d2)
    assert "no_charge_lines" in d2, d2.keys()
    assert "ZZT-ZERO-QTY" not in d2["no_charge_lines"]
    assert "ZZT-RATE" not in d2["no_charge_lines"]


def test_AC_B5_a_document_with_no_scopes_is_returned_empty(db):
    w = _owner_case(db)
    d4 = _doc(_call(db, w), w.d4)
    assert d4["scopes"] == []
    assert d4.get("line_count") == 0 and d4.get("empty") is True, d4


def test_AC_C9_total_lines_is_the_sum_of_every_documents_line_count(db):
    w = _owner_case(db)
    out = _call(db, w)
    assert out.data.get("total_lines") == 17, out.data.keys()  # 2 + 12 + 3 + 0


def test_AC_C9_a_single_document_call_has_total_lines_and_no_comparison(db):
    w = _owner_case(db)
    out = _call(db, w, [w.d1])
    assert [d["ref"] for d in out.data["documents"]] == [w.d1]
    assert "comparison" not in out.data
    assert out.data.get("total_lines") == 2, out.data.keys()


# ================================================================== C. comparison


def _cmp(out):
    assert "comparison" in out.data, sorted(out.data)
    return out.data["comparison"]


def _totals(cmp):
    return [(t["ref"], _f(t["total"]), _f(t["gap_to_lowest"])) for t in cmp["totals"]]


def test_AC_C1_totals_ranked_with_gap_to_lowest_across_all_four_documents(db):
    w = _owner_case(db)
    cmp = _cmp(_call(db, w))
    assert _totals(cmp) == [
        (w.d4, 0.0, 0.0), (w.d3, 246.40, 246.40), (w.d1, 251.85, 251.85), (w.d2, 2417.45, 2417.45),
    ]
    assert cmp["lowest"] == w.d4 and cmp["highest"] == w.d2


def test_AC_C1_totals_for_three_referenced_documents(db):
    w = _owner_case(db)
    cmp = _cmp(_call(db, w, [w.d1, w.d2, w.d3]))
    assert _totals(cmp) == [(w.d3, 246.40, 0.0), (w.d1, 251.85, 5.45), (w.d2, 2417.45, 2171.05)]
    assert cmp["lowest"] == w.d3 and cmp["highest"] == w.d2


def test_AC_C2_only_in_lists_codes_not_in_every_document_in_first_seen_order(db):
    w = _owner_case(db)
    cmp = _cmp(_call(db, w, [w.d1, w.d2, w.d3]))
    assert cmp["only_in"] == [
        {"code": "CB310-CR-PJ", "refs": [w.d1, w.d3]},
        {"code": "SRTWHBWP", "refs": [w.d2]},
        {"code": "SRTWT907SS", "refs": [w.d2, w.d3]},
        {"code": "ZZT-NC-A", "refs": [w.d2]},
        {"code": "ZZT-NC-B", "refs": [w.d2]},
        {"code": "ZZT-ZERO-QTY", "refs": [w.d2]},
        {"code": "ZZT-RATE", "refs": [w.d2]},  # C8: a rate-only line counts like any other
        {"code": "SRT73-CR", "refs": [w.d2]},
        {"code": "ZZT-L9", "refs": [w.d2]},
    ]


def _shared(cmp):
    out = []
    for s in cmp["shared"]:
        out.append({
            "code": s["code"],
            "docs": [(d["ref"], _f(d["qty"]), [_f(p) for p in d["unit_prices"]], _f(d["line_total"]))
                     for d in s["docs"]],
            "cheapest": s["cheapest"],
            "unit_price_gap": _f(s["unit_price_gap"]),
            "line_total_gap": _f(s["line_total_gap"]),
            "same_uom": s["same_uom"],
        })
    return out


def test_AC_C3_shared_codes_with_cheapest_and_gaps_ordered_by_line_total_gap(db):
    w = _owner_case(db)
    cmp = _cmp(_call(db, w))
    assert _shared(cmp) == [
        {   # 1445.40 - 219.00 = 1226.40; per unit 240.90 - 219.00 = 21.90
            "code": "SRTWC8518-SH",
            "docs": [(w.d1, 1.0, [240.90], 240.90), (w.d2, 6.0, [240.90], 1445.40), (w.d3, 1.0, [219.00], 219.00)],
            "cheapest": w.d3, "unit_price_gap": 21.90, "line_total_gap": 1226.40, "same_uom": True,
        },
        {   # same unit price everywhere: no cheapest; 21.90 - 10.95 = 10.95
            "code": "CB310-CR-PJ",
            "docs": [(w.d1, 1.0, [10.95], 10.95), (w.d3, 2.0, [10.95], 21.90)],
            "cheapest": None, "unit_price_gap": 0.0, "line_total_gap": 10.95, "same_uom": True,
        },
        {   # D2 sums its two lines: qty 11, prices [0, 0.73], total 3.65; min 0 < 0.50; 5.50 - 3.65 = 1.85
            "code": "SRTWT907SS",
            "docs": [(w.d2, 11.0, [0.0, 0.73], 3.65), (w.d3, 11.0, [0.50], 5.50)],
            "cheapest": w.d2, "unit_price_gap": 0.50, "line_total_gap": 1.85, "same_uom": True,
        },
    ]


def test_AC_C4_C5_scopes_only_in_and_scope_totals(db):
    w = _owner_case(db)
    cmp = _cmp(_call(db, w, [w.d1, w.d2, w.d3]))
    assert cmp["scopes_only_in"] == [
        {"scope": "LEVEL 9", "refs": [w.d2]},
        {"scope": "Guard House", "refs": [w.d2]},
    ]
    totals = [(s["scope"], [(t["ref"], _f(t["total"])) for t in s["totals"]]) for s in cmp["scope_totals"]]
    assert totals == [("UNIT", [(w.d1, 251.85), (w.d2, 2267.45), (w.d3, 246.40)])]


def test_AC_C4_a_document_with_no_scopes_makes_every_scope_only_in_some(db):
    w = _owner_case(db)
    cmp = _cmp(_call(db, w))
    assert cmp["scopes_only_in"] == [
        {"scope": "UNIT", "refs": [w.d1, w.d2, w.d3]},
        {"scope": "LEVEL 9", "refs": [w.d2]},
        {"scope": "Guard House", "refs": [w.d2]},
    ]


def _uom_world(db):
    """P and Q tie at 100.00; ZZT-UOM is 2 pcs x 50.00 in P and 1 set x 100.00 in Q."""
    b = Builder(db)
    q1 = b.user("ZZT Quoter One")
    p = b.doc("PRJQ-P", q1)
    q = b.doc("PRJQ-Q", q1)
    b.scope(p, "UNIT", [L("ZZT-UOM", "2", None, "50.00", "100.00", uom="pcs")])
    b.scope(q, "UNIT", [L("ZZT-UOM", "1", None, "100.00", "100.00", uom="set")])
    return SimpleNamespace(b=b, company_id=b.company_id, project_id=b.project_id, p=p.document_no, q=q.document_no)


def test_AC_C3_a_shared_code_in_different_units_has_no_cheapest_and_no_unit_gap(db):
    w = _uom_world(db)
    cmp = _cmp(_call(db, w))
    assert _shared(cmp) == [{
        "code": "ZZT-UOM",
        "docs": [(w.p, 2.0, [50.0], 100.0), (w.q, 1.0, [100.0], 100.0)],
        "cheapest": None, "unit_price_gap": None, "line_total_gap": 0.0, "same_uom": False,
    }]


def test_AC_C1_tied_totals_keep_document_order(db):
    w = _uom_world(db)
    cmp = _cmp(_call(db, w))
    assert _totals(cmp) == [(w.p, 100.0, 0.0), (w.q, 100.0, 0.0)]
    assert cmp["lowest"] == w.p and cmp["highest"] == w.q


def test_AC_C6_each_list_holds_at_most_20_and_counts_the_rest(db):
    """A: scopes S01..S22 + X01..X21; S01 has ONLY-01..25 and SH-01..22. B: scopes S01..S22; S01 has SH-01..22."""
    b = Builder(db)
    q1 = b.user("ZZT Quoter One")
    a = b.doc("PRJQ-A", q1)
    bb = b.doc("PRJQ-B", q1)
    only = [L(f"ONLY-{i:02d}", "1", None, "1.00", "1.00") for i in range(1, 26)]
    shared_a = [L(f"SH-{i:02d}", "1", None, "2.00", "2.00") for i in range(1, 23)]
    shared_b = [L(f"SH-{i:02d}", "1", None, "3.00", "3.00") for i in range(1, 23)]
    b.scope(a, "S01", only + shared_a)
    b.scope(bb, "S01", shared_b)
    for i in range(2, 23):
        b.scope(a, f"S{i:02d}", [])
        b.scope(bb, f"S{i:02d}", [])
    for i in range(1, 22):
        b.scope(a, f"X{i:02d}", [])
    w = SimpleNamespace(company_id=b.company_id, project_id=b.project_id)
    cmp = _cmp(_call(db, w))
    assert len(cmp["only_in"]) == 20 and cmp.get("only_in_not_shown") == 5, cmp.get("only_in_not_shown")
    assert [e["code"] for e in cmp["only_in"]] == [f"ONLY-{i:02d}" for i in range(1, 21)]
    assert len(cmp["shared"]) == 20 and cmp.get("shared_not_shown") == 2, cmp.get("shared_not_shown")
    assert len(cmp["scopes_only_in"]) == 20 and cmp.get("scopes_only_in_not_shown") == 1
    assert len(cmp["scope_totals"]) == 20 and cmp.get("scope_totals_not_shown") == 2


def test_AC_C7_the_comparison_and_document_facts_are_built_before_the_size_cut(db):
    w = _owner_case(db)
    whole, whole_cut = _direct(db, w, [], 10**9)
    assert whole_cut == 0
    assert "comparison" in whole, sorted(whole)
    cap = len(json.dumps(whole, default=str)) - 300
    cut, more = _direct(db, w, [], cap)
    assert more > 0, "the cap did not cut any line; lower it"
    assert any(s.get("lines_not_shown") for d in cut["documents"] for s in d["scopes"]), "no scope was cut"
    assert cut["comparison"] == whole["comparison"]
    assert cut.get("total_lines") == whole.get("total_lines") == 17
    facts = ("line_count", "no_charge_lines", "repeated_codes", "rate_only_lines", "empty", "prepared_by")
    for d_cut in cut["documents"]:
        d_whole = next(d for d in whole["documents"] if d["ref"] == d_cut["ref"])
        assert {k: d_cut.get(k) for k in facts} == {k: d_whole.get(k) for k in facts}, d_cut["ref"]


# ================================================================== D. below-list text


def test_AC_D2_vs_list_at_unit_price_0_is_no_charge():
    from app.services.chatbot.agent.quotation_lines import vs_list

    assert vs_list(Decimal("945.35"), Decimal("0")) == "no charge"
    assert vs_list(None, Decimal("0")) is None
    assert vs_list(None, Decimal("10.95")) is None


def test_AC_D1_D2_lines_keep_list_unit_and_vs_list_and_a_0_line_reads_no_charge(db):
    w = _owner_case(db)
    d2 = _doc(_call(db, w, [w.d2]), w.d2)
    lines = [ln for s in d2["scopes"] for ln in s["lines"]]
    for ln in lines:
        assert {"list_price", "unit_price", "vs_list"} <= set(ln), ln
    nc_a = next(ln for ln in lines if ln["code"] == "ZZT-NC-A")
    assert nc_a["vs_list"] == "no charge", nc_a
    assert all("100% below list" != ln["vs_list"] for ln in lines), lines


def _desc():
    from app.services.chatbot.agent.tools import QUOTATION_LINES_SCHEMA

    return QUOTATION_LINES_SCHEMA["function"]["description"]


def test_AC_D3_the_description_no_longer_prescribes_a_table_or_one_sentence():
    text = _desc()
    assert "compact markdown table" not in text
    assert "(vs_list as given)" not in text
    assert "one sentence" not in text


def test_AC_D3_the_description_says_vs_list_is_for_when_the_user_asks_about_list_price():
    text = _desc()
    assert "vs_list" in text and "list price" in text and "ask" in text.lower(), text


def test_AC_D4_the_description_names_the_computed_comparison_and_prepared_by():
    text = _desc()
    assert "comparison" in text and "cheapest" in text, text
    assert "prepared_by" in text, text


# ================================================================== E. agent prompt


def _prompt():
    from app.services.ai_prompt_registry import _chatbot_agent_fallback

    return _chatbot_agent_fallback()


def test_AC_E1_the_prompt_has_a_comparing_section_with_findings_then_the_table_rule():
    text = _prompt()
    low = text.lower()
    assert "COMPARING" in text
    assert "findings" in low
    assert 'Reply "table" for the full table.' in text
    assert "30" in text
    assert "HTML" in text  # never HTML such as <br>
    assert "list price" in low
    assert "repeated" in low
    assert "no charge" in low or "no_charge" in low
    assert "rate only" in low or "rate_only" in low
    assert "empty" in low


def test_AC_E2_the_prompt_has_the_prepared_by_rule():
    text = _prompt()
    assert "prepared_by" in text
    assert "project owner" in text
    assert "cannot see" in text


def test_AC_E3_the_prompt_allows_analysis_and_keeps_the_no_arithmetic_rules():
    text = _prompt()
    assert "never do arithmetic on results" in text
    assert "Every number in your answer must come from a tool result" in text
    concise = [s for s in re.split(r"(?<=[.!?])\s+", text) if "concise" in s.lower()]
    assert concise, "the concise rule for simple lookups is gone"
    assert all("lookup" in s.lower() for s in concise), concise


def test_AC_E4_the_prompt_has_no_em_or_en_dash():
    text = _prompt()
    assert "\u2014" not in text and "\u2013" not in text


def _bump_migrations():
    found = []
    for path in sorted((BACKEND / "alembic" / "versions").glob("*.py")):
        src = path.read_text(encoding="utf-8")
        if "bump_prompt_to_fallback" in src and re.search(r"""["']chatbot_agent["']""", src):
            found.append((path, src))
    return found


def test_AC_E5_a_migration_bumps_the_chatbot_agent_prompt_with_a_short_revision_and_a_no_op_downgrade():
    found = _bump_migrations()
    assert found, "no migration calls bump_prompt_to_fallback for chatbot_agent"
    for path, src in found:
        rev = re.search(r"""^revision\s*(?::\s*str)?\s*=\s*["']([^"']+)["']""", src, re.MULTILINE)
        assert rev and len(rev.group(1)) <= 32, (path.name, rev and rev.group(1))
        tree = ast.parse(src)
        down = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "downgrade")
        assert all(
            isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
            for s in down.body
        ), f"{path.name}: downgrade is not a no-op"


# ================================================================== F. effort


def test_AC_F1_the_default_effort_is_medium():
    from app.services.chatbot.agent import loop

    assert loop.DEFAULT_EFFORT == "medium"
