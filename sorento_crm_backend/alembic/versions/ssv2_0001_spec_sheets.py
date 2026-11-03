"""Saved spec sheets (SPEC-SHEET-V2): table `projects.quotation_spec_sheets` + backfill.

Plan: documentation/plans/project-sales/PLAN-spec-sheet-v2-03nov.md.

Each quotation document that was already set up through the old tab (`quotation_documents.spec_sheet`
names a cover and a page template) gets `SS1` on its saved issue (else its newest issue), carrying
its rows, an items snapshot and the templates' current published versions. The old column stays.
The backfill is inline SQL on purpose: a migration must not import models later migrations change.

Revision ID: ssv2_0001_spec_sheets
Revises: pqr_0001_quote_rules_routing
Create Date: 2026-11-03
"""
import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ssv2_0001_spec_sheets"
down_revision = "pqr_0001_quote_rules_routing"
branch_labels = None
depends_on = None

_TABLE = "quotation_spec_sheets"


def upgrade() -> None:
    uuid_t = postgresql.UUID(as_uuid=False)
    op.create_table(
        _TABLE,
        sa.Column("id", uuid_t, primary_key=True),
        sa.Column("company_id", uuid_t, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column(
            "document_id",
            uuid_t,
            sa.ForeignKey("projects.quotation_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "issue_id",
            uuid_t,
            sa.ForeignKey("projects.quotation_issues.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("based_on_issue_no", sa.Integer(), nullable=True),
        sa.Column("sheet_no", sa.Integer(), nullable=False),
        sa.Column("cover_template_id", uuid_t, sa.ForeignKey("dealer_kit.tag_template.id", ondelete="SET NULL")),
        sa.Column("page_template_id", uuid_t, sa.ForeignKey("dealer_kit.tag_template.id", ondelete="SET NULL")),
        sa.Column(
            "single_page_template_id", uuid_t, sa.ForeignKey("dealer_kit.tag_template.id", ondelete="SET NULL")
        ),
        sa.Column(
            "cover_version_id", uuid_t, sa.ForeignKey("dealer_kit.tag_template_version.id", ondelete="SET NULL")
        ),
        sa.Column(
            "page_version_id", uuid_t, sa.ForeignKey("dealer_kit.tag_template_version.id", ondelete="SET NULL")
        ),
        sa.Column(
            "single_version_id", uuid_t, sa.ForeignKey("dealer_kit.tag_template_version.id", ondelete="SET NULL")
        ),
        sa.Column("items", postgresql.JSONB(), nullable=False),
        sa.Column("rows", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("page_edits", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("items_taken_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_exported_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(100), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", sa.String(100), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "sheet_no", name="uq_project_quotation_spec_sheets_no"),
        schema="projects",
    )
    op.create_index("ix_quotation_spec_sheets_company_id", _TABLE, ["company_id"], schema="projects")
    op.create_index("ix_project_quotation_spec_sheets_document", _TABLE, ["document_id"], schema="projects")
    backfill(op.get_bind())


def downgrade() -> None:
    op.drop_table(_TABLE, schema="projects")


# ----------------------------------------------------------------------------- backfill
#
# Minimal Table constructs, not text(): a schema-qualified text() statement is not rewritten by a
# schema_translate_map (the test fixture's scratch schemas), a Table is. Not the ORM models, which
# later migrations may change.

_META = sa.MetaData()


def _t(name, *columns, schema="projects"):
    return sa.Table(name, _META, *[sa.Column(c) for c in columns], schema=schema)


_DOCS = _t("quotation_documents", "id", "company_id", "spec_sheet")
_ISSUES = _t("quotation_issues", "id", "document_id", "issue_no")
_ISSUE_SCOPES = _t("quotation_issue_scopes", "issue_id", "version_id", "sort_order", "id")
_LINES = _t(
    "quotation_lines",
    "id",
    "version_id",
    "product_id",
    "product_set_id",
    "set_parts_snapshot",
    "product_code_snapshot",
    "description_snapshot",
    "brand_snapshot",
    "image_attachment_id",
    "drawing_attachment_id",
    "band_label",
    "unit_price",
    "sort_order",
    "created_at",
)
_SHEETS = _t(
    _TABLE,
    "id",
    "company_id",
    "document_id",
    "issue_id",
    "sheet_no",
    "cover_template_id",
    "page_template_id",
    "single_page_template_id",
    "cover_version_id",
    "page_version_id",
    "single_version_id",
    "items",
    "rows",
    "page_edits",
    "page_count",
)
_TEMPLATES = _t(
    "tag_template", "id", "published_version_id", "company_id", "family", schema="dealer_kit"
)
_PRODUCTS = _t("products", "id", "brand_id", schema=None)
_BRANDS = _t("brands", "id", "brand_name", schema=None)


def _jsonb(value):
    # A text parameter cast in SQL: a JSONB-typed bind would serialise the string a second time.
    return sa.cast(sa.literal(json.dumps(value, default=str), sa.Text), postgresql.JSONB)


def _items(connection, issue_id):
    """The issue's items in quotation order, one per product or set (first position wins)."""
    scopes = connection.execute(
        sa.select(_ISSUE_SCOPES.c.version_id)
        .where(_ISSUE_SCOPES.c.issue_id == issue_id)
        .order_by(_ISSUE_SCOPES.c.sort_order, _ISSUE_SCOPES.c.id)
    ).all()
    items = {}
    for (version_id,) in scopes:
        section = ""
        lines = connection.execute(
            sa.select(
                _LINES.c.id,
                _LINES.c.product_id,
                _LINES.c.product_set_id,
                _LINES.c.set_parts_snapshot,
                _LINES.c.product_code_snapshot,
                _LINES.c.description_snapshot,
                _LINES.c.brand_snapshot,
                _LINES.c.image_attachment_id,
                _LINES.c.drawing_attachment_id,
                _LINES.c.band_label,
                _LINES.c.unit_price,
                sa.select(_BRANDS.c.brand_name)
                .select_from(_PRODUCTS.join(_BRANDS, _BRANDS.c.id == _PRODUCTS.c.brand_id))
                .where(_PRODUCTS.c.id == _LINES.c.product_id)
                .scalar_subquery()
                .label("product_brand"),
            )
            .where(_LINES.c.version_id == version_id)
            .order_by(_LINES.c.sort_order, _LINES.c.created_at)
        ).mappings().all()
        for line in lines:
            heading = (line["band_label"] or "").strip()
            if heading:
                section = heading
            if line["product_set_id"]:
                key = f"set:{line['product_set_id']}"
            elif line["product_id"]:
                key = str(line["product_id"])
            else:
                code = (line["product_code_snapshot"] or "").strip().upper()
                key = f"code:{code}" if code else None
            if key is None or key in items:
                continue
            parts = line["set_parts_snapshot"] or []
            driver = None
            if line["product_set_id"] and parts:
                driver = next((p for p in parts if p.get("is_driver")), parts[0])
            price = float(line["unit_price"]) if line["unit_price"] is not None else None
            items[key] = {
                "key": key,
                "line_id": str(line["id"]),
                "product_id": (driver or {}).get("product_id")
                or (str(line["product_id"]) if line["product_id"] else None),
                "code": (driver or {}).get("product_code") or line["product_code_snapshot"] or "",
                "description": (driver or {}).get("description") or line["description_snapshot"] or "",
                "brand": line["brand_snapshot"] or line["product_brand"] or "",
                "image_attachment_id": str(line["image_attachment_id"]) if line["image_attachment_id"] else None,
                "drawing_attachment_id": str(line["drawing_attachment_id"])
                if line["drawing_attachment_id"]
                else None,
                "section": section,
                "unit_price": price,
                "set_parts": [
                    {
                        "product_id": p.get("product_id"),
                        "product_code": p.get("product_code"),
                        "description": p.get("description"),
                    }
                    for p in parts
                    if line["product_set_id"] and p is not driver
                ],
            }
    return list(items.values())


def _page_count(items, rows):
    """Cover plus the visible pages: picked accessories ride their host, hidden pages drop."""
    keys = {i["key"] for i in items}
    by_key = {r.get("key"): r for r in rows}
    absorbed = {
        a for r in by_key.values() if r.get("key") in keys for a in r.get("accessories") or [] if a in keys
    }
    visible = [k for k in keys if k not in absorbed and not (by_key.get(k) or {}).get("hidden")]
    return 1 + len(visible)


def backfill(connection) -> None:
    """Give every already set-up document its SS1. Idempotent: a document with a sheet is skipped."""
    has_sheet = sa.exists().where(_SHEETS.c.document_id == _DOCS.c.id)
    docs = connection.execute(
        sa.select(_DOCS.c.id, _DOCS.c.company_id, _DOCS.c.spec_sheet).where(
            _DOCS.c.spec_sheet.isnot(None), ~has_sheet
        )
    ).mappings().all()
    for doc in docs:
        settings = doc["spec_sheet"] or {}
        if not doc["company_id"]:
            continue
        cover, page = settings.get("cover_template_id"), settings.get("page_template_id")
        if not cover or not page:
            continue
        newest = (
            sa.select(_ISSUES.c.id)
            .where(_ISSUES.c.document_id == doc["id"])
            .order_by(_ISSUES.c.issue_no.desc())
            .limit(1)
        )
        issue_id = None
        if settings.get("issue_id"):
            issue_id = connection.execute(
                sa.select(_ISSUES.c.id).where(
                    _ISSUES.c.id == settings["issue_id"], _ISSUES.c.document_id == doc["id"]
                )
            ).scalar()
        if issue_id is None:
            issue_id = connection.execute(newest).scalar()
        if issue_id is None:
            continue
        single = settings.get("single_page_template_id") or None
        versions = {}
        for name, template_id, family in (
            ("cover", cover, "spec_cover"),
            ("page", page, "spec_page"),
            ("single", single, "spec_page"),
        ):
            # Same company as the document and the right family, else the template does not count.
            versions[name] = (
                connection.execute(
                    sa.select(_TEMPLATES.c.published_version_id).where(
                        _TEMPLATES.c.id == template_id,
                        _TEMPLATES.c.company_id == doc["company_id"],
                        _TEMPLATES.c.family == family,
                    )
                ).scalar()
                if template_id
                else None
            )
        if versions["single"] is None:
            # A single-item template that is gone, unpublished, of another family or company:
            # the sheet uses its page template instead.
            single = None
        if versions["cover"] is None or versions["page"] is None:
            continue
        items = _items(connection, issue_id)
        if not items:
            continue
        rows = [r for r in settings.get("rows") or [] if isinstance(r, dict)]
        connection.execute(
            sa.insert(_SHEETS).values(
                id=str(uuid.uuid4()),
                company_id=doc["company_id"],
                document_id=doc["id"],
                issue_id=issue_id,
                sheet_no=1,
                cover_template_id=cover,
                page_template_id=page,
                single_page_template_id=single,
                cover_version_id=versions["cover"],
                page_version_id=versions["page"],
                single_version_id=versions["single"],
                items=_jsonb(items),
                rows=_jsonb(rows),
                page_edits=_jsonb({}),
                page_count=_page_count(items, rows),
            )
        )
