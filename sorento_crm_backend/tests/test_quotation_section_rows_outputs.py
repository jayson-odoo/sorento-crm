"""PROPOSAL-FORM-COLLAPSE: every reader of quotation lines treats a heading row (`is_section`)
as the band only. It never takes an item number, never counts as a line, is never flagged, and
never joins a set's companions on the sales order draft."""
from __future__ import annotations

import uuid
from decimal import Decimal

from ._pg_fixture import blank_session
from .test_project_quotation_pdf import MARKER, PRICED_RATE, _issue, _product, _setup


def _document_with_heading(db, env):
    """One scope: line, heading "PAGE 1", line, line. Returns (document, scope, version)."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    owner = env["owner"]
    product = _product(db, env["category"].id, env["uom"], description=f"{MARKER} WC suite")
    document = qdocs.create_document(db, project=env["project"], actor_user_id=owner)
    scope = qdocs.add_scope(
        db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
    )
    version = quotes.current_version(db, scope.id)

    def line(desc: str) -> dict:
        return {
            "product_id": product.id,
            "unit_price": PRICED_RATE,
            "quantity": 1,
            "description_snapshot": f"{MARKER} {desc}",
        }

    quotes.replace_lines(
        db,
        version=version,
        actor_user_id=owner,
        lines=[
            line("basin"),
            {"is_section": True, "band_label": f"{MARKER} PAGE 1"},
            line("tap"),
            line("mirror"),
        ],
    )
    return document, scope, version


def test_the_pdf_prints_a_heading_row_as_its_band_and_numbers_only_the_lines():
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        env = _setup(db)
        document, _scope, _version = _document_with_heading(db, env)
        html = qpdf.build_issue_html(db, _issue(db, document, env["owner"]))

        heading = f"{MARKER} PAGE 1"
        assert html.count(heading) == 1
        assert html.index(f"{MARKER} basin") < html.index(heading) < html.index(f"{MARKER} tap")
        for number in ("1", "2", "3"):
            assert f'<td class="item">{number}</td>' in html
        assert '<td class="item">4</td>' not in html


def test_the_workbook_numbers_only_the_lines():
    from app.services import project_quotation_excel_service as qxls

    with blank_session() as db:
        env = _setup(db)
        document, _scope, _version = _document_with_heading(db, env)
        workbook = qxls.build_issue_workbook(db, _issue(db, document, env["owner"]))
        values = [
            cell
            for sheet in workbook.worksheets
            for row in sheet.iter_rows(values_only=True)
            for cell in row
            if cell is not None
        ]
        assert f"{MARKER} PAGE 1" in values
        assert "4" not in values and 4 not in values
        assert "3" in values or 3 in values


def test_the_sign_page_draws_the_heading_row_and_numbers_only_the_lines():
    from .test_quote_cover_design_issue import sign_body

    with blank_session() as db:
        env = _setup(db)
        document, _scope, _version = _document_with_heading(db, env)
        body = sign_body(db, _issue(db, document, env["owner"]))
        (scope,) = body["scopes"]
        rows = scope["lines"]
        assert [row.get("is_section", False) for row in rows] == [False, True, False, False]
        assert rows[1]["band_label"] == f"{MARKER} PAGE 1"
        assert rows[1]["item_label"] is None
        assert [rows[i]["item_label"] for i in (0, 2, 3)] == ["1", "2", "3"]


def test_counts_and_flags_leave_heading_rows_out():
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        env = _setup(db)
        document, scope, version = _document_with_heading(db, env)

        listed = quotes.serialize_quotations(db, [scope])
        assert listed[0]["line_count"] == 3
        summary = qdocs._scope_summary(db, scope)
        assert summary["line_count"] == 3

        report = quotes.recompute_version(db, version=version)
        assert report["line_count"] == 3
        heading = next(row for row in quotes.list_lines(db, version.id) if row.is_section)
        assert heading.is_non_standard is False and heading.is_below_floor is False
        assert heading.line_total == Decimal("0.00")


def test_a_heading_row_after_a_priced_line_never_becomes_its_companion_on_the_so_draft():
    """A heading row is priced at 0, like a set's companion; it must end the run instead."""
    from app.models.projects import ProjectQuotationLine
    from app.services.project_so_draft_service import ProjectSODraftService

    from . import test_project_so_draft as so

    with blank_session() as db:
        company_id = so._sorento(db)
        so.project_seed_service.run(db, company_id=company_id)
        owner = so._user(db, f"{so.MARKER} CONTACT AH")
        project = so._project(db, company_id, owner)
        parent = so._product(db, "SRTWC8613-RL")
        version = so._quotation(db, project, lines=[(parent, "10", "392.85")], total="3928.50")
        db.add(
            ProjectQuotationLine(
                id=str(uuid.uuid4()),
                company_id=project.company_id,
                version_id=version.id,
                is_section=True,
                band_label=f"{so.MARKER} PAGE 2",
                unit_price=Decimal("0"),
                quantity=Decimal("0"),
                line_total=Decimal("0"),
                sort_order=1,
            )
        )
        db.flush()
        party = so._party(db, company_id)
        po = so._po(db, project, party=party, quotation_version=version)
        po_version = so._po_version(
            db,
            po,
            lines=[(1, parent, "SRTWC8613-RL", "10", "SETS", "392.85", "3928.50", False)],
            extracted_total="3928.50",
        )
        schedule = so._schedule(db, project, po, po_version=po_version)
        phase = so._phase(
            db, project, area_group="TOWER", sequence=1, label="L2",
            delivery_date=so.date(2026, 7, 1), version=schedule,
        )
        so._cell(db, schedule, phase, parent, "10")

        result = ProjectSODraftService(db).build(po.id, schedule.id)
        lines = so._lines(db, result["data"][0]["id"])
        assert [line.product_id for line in lines] == [parent.id]
