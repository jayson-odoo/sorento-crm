"""GUARD (owner ruling, 12 Nov 2026): After-sales changes NOTHING in the live Complaints module.

"The after sales shouldn't affect how our current complaints work because our current complaint is
for project." These sets are pinned from origin/main when the After-sales module was built, so the
test passes on main and on the After-sales branch: any added, removed or renamed complaint route,
schema field or table column fails here and needs the owner's say-so.
"""
from __future__ import annotations

import ast
from pathlib import Path

from fastapi.routing import APIRoute

BACKEND = Path(__file__).resolve().parents[1]

COMPLAINT_ROUTES = [('DELETE', '/complaint-resolutions/{resolution_id}'), ('DELETE', '/complaint-root-causes/{root_cause_id}'), ('DELETE', '/complaints/attachments/{link_id}'), ('DELETE', '/complaints/bulk'), ('DELETE', '/complaints/response-attachments/{link_id}'), ('DELETE', '/complaints/{complaint_id}'), ('GET', '/complaint-resolutions/'), ('GET', '/complaint-resolutions/select'), ('GET', '/complaint-resolutions/{resolution_id}'), ('GET', '/complaint-root-causes/'), ('GET', '/complaint-root-causes/select'), ('GET', '/complaint-root-causes/{root_cause_id}'), ('GET', '/complaints/'), ('GET', '/complaints/analytics'), ('GET', '/complaints/{complaint_id}'), ('GET', '/complaints/{complaint_id}/conversation'), ('GET', '/complaints/{complaint_id}/fulfilment-orders'), ('GET', '/complaints/{complaint_id}/revisions'), ('GET', '/complaints/{entity_id}/conversation/chat-template'), ('GET', '/complaints/{entity_id}/conversation/window-state'), ('POST', '/complaint-resolutions/'), ('POST', '/complaint-root-causes/'), ('POST', '/complaints/'), ('POST', '/complaints/integration'), ('POST', '/complaints/{complaint_id}/approve'), ('POST', '/complaints/{complaint_id}/attachments'), ('POST', '/complaints/{complaint_id}/close'), ('POST', '/complaints/{complaint_id}/export/pdf'), ('POST', '/complaints/{complaint_id}/notify-resolution'), ('POST', '/complaints/{complaint_id}/notify-root-cause'), ('POST', '/complaints/{complaint_id}/process'), ('POST', '/complaints/{complaint_id}/reject'), ('POST', '/complaints/{complaint_id}/response-attachments'), ('POST', '/complaints/{complaint_id}/sync-assignee'), ('POST', '/complaints/{complaint_id}/update-and-reply'), ('POST', '/complaints/{complaint_id}/view-link'), ('POST', '/complaints/{complaint_id}/void'), ('POST', '/complaints/{entity_id}/conversation/send-message'), ('POST', '/complaints/{entity_id}/conversation/template-message'), ('PUT', '/complaint-resolutions/{resolution_id}'), ('PUT', '/complaint-root-causes/{root_cause_id}'), ('PUT', '/complaints/{complaint_id}')]
COMPLAINT_CREATE_FIELDS = ['assigned_to', 'assigned_to_name', 'attachments', 'complaint_date', 'complaint_number', 'complaint_type', 'contact_id', 'contact_number', 'contact_person', 'created_at', 'customer_address', 'customer_name', 'customer_type', 'customer_type_others', 'defect_description', 'defects_discovered', 'delivery_order_number', 'last_responded_at', 'last_responded_by', 'product_code', 'product_lines', 'product_type', 'project_id', 'project_title', 'quantity', 'required_on_site_support', 'resolution_id', 'root_cause_id', 'salesperson', 'space_id', 'status', 'technical_team_response', 'within_warranty']
COMPLAINT_UPDATE_FIELDS = ['complaint_date', 'complaint_number', 'complaint_type', 'contact_id', 'contact_number', 'contact_person', 'customer_address', 'customer_name', 'customer_type', 'customer_type_others', 'defect_description', 'defects_discovered', 'delivery_order_number', 'last_responded_at', 'last_responded_by', 'product_code', 'product_lines', 'product_type', 'project_id', 'project_title', 'quantity', 'required_on_site_support', 'resolution_id', 'root_cause_id', 'salesperson', 'space_id', 'status', 'technical_team_response', 'within_warranty']
COMPLAINT_RESPONSE_FIELDS = ['assigned_to', 'assigned_to_name', 'attachments', 'complaint_date', 'complaint_number', 'complaint_type', 'contact_id', 'contact_number', 'contact_person', 'created_at', 'customer_address', 'customer_name', 'customer_type', 'customer_type_others', 'defect_description', 'defects_discovered', 'delivery_order_number', 'form_type', 'handled_by_name', 'handled_by_wa_phone', 'id', 'last_responded_at', 'last_responded_by', 'last_responded_by_name', 'last_revised_at', 'print_count', 'product_code', 'product_lines', 'product_type', 'project_code', 'project_id', 'project_name', 'project_title', 'quantity', 'rejected_at', 'rejected_by', 'rejected_by_name', 'rejected_by_wa_phone', 'rejection_reason', 'required_on_site_support', 'resolution_id', 'resolution_name', 'resolution_notified_at', 'resolved_at', 'resolved_by', 'respond_inbox_url', 'response_write_allowed', 'revision_no', 'root_cause_id', 'root_cause_name', 'root_cause_notified_at', 'salesperson', 'space_id', 'status', 'system_id', 'technical_team_response', 'view_url', 'void_reason', 'voided_at', 'voided_by_name', 'voided_by_wa_phone', 'within_warranty']
RESOLUTION_CREATE_FIELDS = ['description', 'is_active', 'name']
RESOLUTION_UPDATE_FIELDS = ['description', 'is_active', 'name']
RESOLUTION_RESPONSE_FIELDS = ['complaint_count', 'created_at', 'description', 'id', 'is_active', 'name', 'updated_at']
COMPLAINT_COLUMNS = ['assigned_to', 'complaint_date', 'complaint_number', 'complaint_type', 'contact_id', 'contact_number', 'contact_person', 'created_at', 'customer_address', 'customer_name', 'customer_type', 'customer_type_others', 'defect_description', 'defects_discovered', 'delivery_order_number', 'id', 'last_responded_at', 'last_responded_by', 'last_revised_at', 'portal_draft_at', 'product_code', 'product_type', 'project_id', 'project_title', 'quantity', 'rejected_at', 'rejected_by', 'rejection_reason', 'required_on_site_support', 'resolution_id', 'resolution_notified_at', 'resolved_at', 'resolved_by', 'respond_inbox_url', 'revision_no', 'root_cause_id', 'root_cause_notified_at', 'salesperson', 'space_id', 'status', 'technical_team_response', 'void_reason', 'voided_at', 'voided_by', 'within_warranty']
RESOLUTION_COLUMNS = ['created_at', 'created_by', 'description', 'id', 'is_active', 'name', 'updated_at']


def test_complaints_router_paths_and_methods_are_unchanged():
    import app.main  # noqa: F401  register everything
    from app.api.v1.complaints import router

    got = sorted({(m, r.path) for r in router.routes if isinstance(r, APIRoute) for m in r.methods - {"HEAD", "OPTIONS"}})
    assert got == COMPLAINT_ROUTES


def test_complaint_and_resolution_schemas_are_unchanged():
    from app.schemas import complaint_master_data as sm
    from app.schemas import complaints as sc

    assert sorted(sc.ComplaintCreate.model_fields) == COMPLAINT_CREATE_FIELDS
    assert sorted(sc.ComplaintUpdate.model_fields) == COMPLAINT_UPDATE_FIELDS
    assert sorted(sc.ComplaintResponse.model_fields) == COMPLAINT_RESPONSE_FIELDS
    assert sorted(sm.ComplaintResolutionCreate.model_fields) == RESOLUTION_CREATE_FIELDS
    assert sorted(sm.ComplaintResolutionUpdate.model_fields) == RESOLUTION_UPDATE_FIELDS
    assert sorted(sm.ComplaintResolutionResponse.model_fields) == RESOLUTION_RESPONSE_FIELDS


def test_complaint_and_resolution_tables_are_unchanged():
    from app.models.complaint_master_data import ComplaintResolution
    from app.models.complaints import Complaint

    assert sorted(c.name for c in Complaint.__table__.columns) == COMPLAINT_COLUMNS
    assert sorted(c.name for c in ComplaintResolution.__table__.columns) == RESOLUTION_COLUMNS


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
