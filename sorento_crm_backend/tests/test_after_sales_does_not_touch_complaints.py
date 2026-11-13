"""GUARD (owner ruling, 12 Nov 2026): After-sales adds NOTHING to the live Complaints module.

"The after sales shouldn't affect how our current complaints work because our current complaint is
for project." What this pins is the After-sales footprint, not main's complaint surface: no
after-sales route on the complaints router, no after-sales field on the complaint or resolution
schemas, no after-sales column on their tables, and no complaints code importing after-sales.
Other lanes may still change complaints (crew premerge, 13 Nov: pinning main's exact route and
column sets broke as soon as #2383 added a route and #2361 a column).
"""
from __future__ import annotations

import ast
from pathlib import Path

from fastapi.routing import APIRoute

BACKEND = Path(__file__).resolve().parents[1]

# The names the After-sales slices use. "within_warranty" is a live complaint field and is NOT one.
_ROUTE_MARKERS = ("service-job", "service_job", "technician", "after-sales", "after_sales", "dispatch")
_FIELD_MARKERS = ("service_job", "technician", "after_sales", "requires_service_job")
_SITE_PREFIX = "site_"


def _after_sales_names(names):
    return sorted(
        n for n in names
        if n.startswith(_SITE_PREFIX) or any(m in n for m in _FIELD_MARKERS)
    )


def test_complaints_router_has_no_after_sales_route():
    import app.main  # noqa: F401  register everything
    from app.api.v1.complaints import router

    leaked = sorted(
        (m, r.path)
        for r in router.routes
        if isinstance(r, APIRoute)
        for m in r.methods - {"HEAD", "OPTIONS"}
        if any(marker in r.path for marker in _ROUTE_MARKERS)
    )
    assert leaked == []


def test_complaint_and_resolution_schemas_carry_no_after_sales_field():
    from app.schemas import complaint_master_data as sm
    from app.schemas import complaints as sc

    for model in (
        sc.ComplaintCreate, sc.ComplaintUpdate, sc.ComplaintResponse,
        sm.ComplaintResolutionCreate, sm.ComplaintResolutionUpdate, sm.ComplaintResolutionResponse,
    ):
        assert _after_sales_names(model.model_fields) == [], model.__name__


def test_complaint_and_resolution_tables_carry_no_after_sales_column():
    from app.models.complaint_master_data import ComplaintResolution
    from app.models.complaints import Complaint

    for table in (Complaint.__table__, ComplaintResolution.__table__):
        assert _after_sales_names(c.name for c in table.columns) == [], table.name


def test_the_complaints_module_never_imports_after_sales():
    files = [
        *sorted((BACKEND / "app" / "api" / "v1" / "complaints").glob("*.py")),
        BACKEND / "app" / "services" / "complaints_service.py",
        BACKEND / "app" / "services" / "complaint_master_data_service.py",
        BACKEND / "app" / "models" / "complaints.py",
        BACKEND / "app" / "models" / "complaint_master_data.py",
        BACKEND / "app" / "schemas" / "complaints.py",
        BACKEND / "app" / "schemas" / "complaint_master_data.py",
    ]
    offenders = []
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [a.name for a in node.names]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            if any("after_sales" in n or "service_job" in n or "technician" in n for n in names):
                offenders.append(f"{path.name}: {names}")
    assert not offenders, offenders
