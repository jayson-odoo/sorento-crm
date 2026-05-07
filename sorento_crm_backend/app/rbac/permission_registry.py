"""
Central permission registry: module.resource.action slugs and descriptions.
Used to seed user_permissions and to enforce RBAC. When adding a new menu or module,
add corresponding CRUD (view, add, edit, delete) and optionally import, export, upload, bulk_*.
"""
from typing import Optional
from sqlalchemy.orm import Session
from app.models.user import UserPermission


def _crud(module: str, resource: str, name_prefix: str) -> list[dict]:
    """Generate view, add, edit, delete for a resource."""
    return [
        {"slug": f"{module}.{resource}.view", "name": f"View {name_prefix}", "description": f"Permission to view {name_prefix}."},
        {"slug": f"{module}.{resource}.add", "name": f"Add {name_prefix}", "description": f"Permission to add {name_prefix}."},
        {"slug": f"{module}.{resource}.edit", "name": f"Edit {name_prefix}", "description": f"Permission to edit {name_prefix}."},
        {"slug": f"{module}.{resource}.delete", "name": f"Delete {name_prefix}", "description": f"Permission to delete {name_prefix}."},
    ]


def _with_import_export(module: str, resource: str, name_prefix: str) -> list[dict]:
    """CRUD + import + export."""
    out = _crud(module, resource, name_prefix)
    out.append({"slug": f"{module}.{resource}.import", "name": f"Import {name_prefix}", "description": f"Permission to import {name_prefix}."})
    out.append({"slug": f"{module}.{resource}.export", "name": f"Export {name_prefix}", "description": f"Permission to export {name_prefix}."})
    return out


# Flat list of {slug, name, description}. Order preserved for seeding.
PERMISSION_REGISTRY: list[dict] = []

# User Management
PERMISSION_REGISTRY.extend(_crud("user_management", "users", "Users"))
PERMISSION_REGISTRY.extend(_crud("user_management", "roles", "Roles"))
PERMISSION_REGISTRY.extend(_crud("user_management", "permissions", "Permissions"))
PERMISSION_REGISTRY.extend(_crud("user_management", "access_agents", "Access Agents"))
PERMISSION_REGISTRY.extend(_crud("user_management", "teams", "Teams"))
PERMISSION_REGISTRY.extend([
    {"slug": "user_management.settings.view", "name": "View Settings", "description": "Permission to view system settings."},
    {"slug": "user_management.settings.edit", "name": "Edit Settings", "description": "Permission to edit system settings."},
    {"slug": "user_management.logs.view", "name": "View Logs", "description": "Permission to view system logs."},
    {"slug": "user_management.account.view", "name": "View Account", "description": "Permission to view own account."},
])
PERMISSION_REGISTRY.append({
    "slug": "user_management.contacts.portal_link",
    "name": "Get contact portal link",
    "description": "Generate or send a user-submission portal link for a respond contact.",
})

# Delivery Order Management
PERMISSION_REGISTRY.extend(_crud("order_management", "orders", "Delivery Orders"))
PERMISSION_REGISTRY.append({"slug": "order_management.orders.import", "name": "Import Delivery Orders", "description": "Permission to bulk import delivery orders."})
PERMISSION_REGISTRY.append({"slug": "order_management.orders.export", "name": "Export Delivery Orders", "description": "Permission to export delivery orders with dynamic fields."})
PERMISSION_REGISTRY.append({"slug": "order_management.orders.bulk_delete", "name": "Bulk Delete Delivery Orders", "description": "Permission to bulk delete delivery orders."})
PERMISSION_REGISTRY.extend(_crud("order_management", "order_statuses", "Delivery Order Statuses"))
PERMISSION_REGISTRY.extend(_crud("order_management", "customers", "Customers"))

# Complaint Management
PERMISSION_REGISTRY.extend(_crud("complaint_management", "complaints", "Complaints"))
PERMISSION_REGISTRY.append({
    "slug": "complaint_management.complaints.approve",
    "name": "Approve Complaints",
    "description": "Permission to approve a complaint after technical team response and notify the contact via Respond.io.",
})
PERMISSION_REGISTRY.append({
    "slug": "complaint_management.complaints.reject",
    "name": "Reject Complaints",
    "description": "Permission to reject a complaint after technical team response and notify the contact via Respond.io.",
})

# SLA Management
PERMISSION_REGISTRY.extend(_crud("sla_management", "sla_policies", "SLA Policies"))
PERMISSION_REGISTRY.extend(_crud("sla_management", "conversation_sla_tracking", "Conversation SLA Tracking"))
PERMISSION_REGISTRY.append(
    {
        "slug": "sla_management.conversation_sla_tracking.test_override",
        "name": "Conversation SLA test overrides",
        "description": "Override assignee and SLA timestamps on a tracking record for testing (non-production use).",
    }
)
PERMISSION_REGISTRY.extend(_crud("sla_management", "escalation_logs", "SLA Event Logs"))

# Master Data (Products)
PERMISSION_REGISTRY.extend(_crud("master_data", "products", "Products"))
PERMISSION_REGISTRY.append({"slug": "master_data.products.import", "name": "Import Products", "description": "Permission to bulk import products."})
PERMISSION_REGISTRY.append({"slug": "master_data.products.export", "name": "Export Products", "description": "Permission to export products with dynamic fields."})
PERMISSION_REGISTRY.append({"slug": "master_data.products.bulk_delete", "name": "Bulk Delete Products", "description": "Permission to bulk delete products."})
PERMISSION_REGISTRY.extend(_crud("master_data", "product_attachments", "Product Attachments"))
PERMISSION_REGISTRY.extend(_crud("master_data", "product_categories", "Product Categories"))
PERMISSION_REGISTRY.extend(_crud("master_data", "brands", "Brands"))
PERMISSION_REGISTRY.extend(_crud("master_data", "lookup_sets", "Lookup Sets"))
PERMISSION_REGISTRY.extend(_crud("master_data", "units_of_measure", "Units of Measure"))

# Procurement
PERMISSION_REGISTRY.extend(_crud("procurement", "suppliers", "Suppliers"))
PERMISSION_REGISTRY.append({"slug": "procurement.suppliers.export", "name": "Export Suppliers", "description": "Permission to export suppliers with dynamic fields."})
PERMISSION_REGISTRY.extend(_crud("procurement", "product_suppliers", "Product-Suppliers"))
PERMISSION_REGISTRY.extend(_crud("procurement", "packing_lists", "Packing Lists"))
PERMISSION_REGISTRY.extend(_crud("procurement", "spo_allocations", "SPO Allocations"))
PERMISSION_REGISTRY.append({"slug": "procurement.spo_allocations.import", "name": "Import SPO Allocations", "description": "Permission to import SPO allocations."})
PERMISSION_REGISTRY.extend(_crud("procurement", "grn", "GRN"))
PERMISSION_REGISTRY.append({"slug": "procurement.grn.import", "name": "Import GRN", "description": "Permission to import GRN."})
PERMISSION_REGISTRY.extend(_crud("procurement", "picking_lines", "Picking Lines"))
PERMISSION_REGISTRY.extend(_crud("procurement", "stock_inquiries", "Stock Inquiries"))
PERMISSION_REGISTRY.extend([
    {"slug": "procurement.stock_inquiries.submit_for_project_sales", "name": "Submit stock inquiry for project sales", "description": "Move stock inquiry to pending project sales review."},
    {"slug": "procurement.stock_inquiries.project_sales_approve", "name": "Project sales approve stock inquiry", "description": "Approve stock inquiry and send to purchasing."},
    {"slug": "procurement.stock_inquiries.project_sales_reject", "name": "Project sales reject stock inquiry", "description": "Reject stock inquiry (project sales)."},
    {"slug": "procurement.stock_inquiries.purchasing_approve", "name": "Purchasing respond to stock inquiry", "description": "Update & Reply is used to respond; this permission gates access to that action."},
    {"slug": "procurement.stock_inquiries.purchasing_reject", "name": "Purchasing reject stock inquiry", "description": "Reject stock inquiry (purchasing)."},
    {"slug": "procurement.stock_inquiries.reopen", "name": "Reopen rejected stock inquiry", "description": "Reopen a rejected stock inquiry back to its previous state (pending project sales or pending purchasing)."},
])
PERMISSION_REGISTRY.extend(_crud("procurement", "purchase_requests", "Purchase Requests"))
PERMISSION_REGISTRY.extend(_crud("procurement", "sponsorship_forms", "Sponsorship Forms"))

# Inventory
PERMISSION_REGISTRY.extend(_crud("inventory", "warehouses", "Warehouses"))
PERMISSION_REGISTRY.extend(_crud("inventory", "storage_zones", "Storage Zones"))
PERMISSION_REGISTRY.extend(_with_import_export("inventory", "stock", "Stock"))
PERMISSION_REGISTRY.extend(_crud("inventory", "stock_batches", "Stock Batches"))
PERMISSION_REGISTRY.extend(_crud("inventory", "stock_ledger", "Stock Ledger"))

# Marketing
PERMISSION_REGISTRY.extend(_crud("marketing", "promotions", "Promotions"))
PERMISSION_REGISTRY.extend(_crud("marketing", "promotion_attachments", "Promotion Attachments"))
PERMISSION_REGISTRY.extend(_crud("marketing", "promotion_products", "Promotion Products"))
PERMISSION_REGISTRY.extend(_crud("marketing", "campaigns", "Campaigns"))

# Forms
PERMISSION_REGISTRY.extend(_crud("forms", "forms", "Forms"))

# Workflow forms (standalone module: builder + submissions / approvals)
PERMISSION_REGISTRY.extend(_crud("workflow_forms", "definitions", "Workflow form definitions"))
PERMISSION_REGISTRY.append(
    {
        "slug": "workflow_forms.definitions.export",
        "name": "Export workflow form definitions",
        "description": "Permission to export workflow form definitions (dynamic list export).",
    }
)
PERMISSION_REGISTRY.extend(_crud("workflow_forms", "submissions", "Workflow form submissions"))
PERMISSION_REGISTRY.append(
    {
        "slug": "workflow_forms.submissions.export",
        "name": "Export workflow form submissions",
        "description": "Permission to export workflow form submissions (dynamic list export).",
    }
)
PERMISSION_REGISTRY.append(
    {
        "slug": "workflow_forms.submissions.transition",
        "name": "Transition workflow submissions",
        "description": "Move a workflow submission to another state (approve, reject, submit, etc.).",
    }
)

# Resource Management (Attachments)
PERMISSION_REGISTRY.extend(_crud("resource", "attachments", "Attachments"))
PERMISSION_REGISTRY.append({"slug": "resource.attachments.upload", "name": "Upload Attachments", "description": "Permission to upload attachments."})
PERMISSION_REGISTRY.append({"slug": "resource.attachments.bulk_import", "name": "Bulk Import Attachments", "description": "Permission to bulk import attachments."})
PERMISSION_REGISTRY.append({"slug": "resource.attachments.bulk_delete", "name": "Bulk Delete Attachments", "description": "Permission to bulk delete attachments."})
PERMISSION_REGISTRY.extend(_crud("resource", "attachment_directories", "Attachment Directories"))
PERMISSION_REGISTRY.extend(_crud("resource", "attachment_types", "Attachment Types"))

# Integration
PERMISSION_REGISTRY.extend(_crud("integration", "integration_logs", "Integration Logs"))

# System
PERMISSION_REGISTRY.extend(_crud("system", "import_jobs", "Import Jobs"))
PERMISSION_REGISTRY.extend(_crud("system", "import_logs", "Import Logs"))
PERMISSION_REGISTRY.extend(_crud("system", "work_calendar", "Work Calendar"))
PERMISSION_REGISTRY.append({
    "slug": "system.outgoing_mails.view",
    "name": "View Outgoing Mails",
    "description": "Permission to view outgoing email log and delivery status.",
})
PERMISSION_REGISTRY.extend([
    {"slug": "system.numbering_rules.view", "name": "View Running Numbers", "description": "Permission to view document numbering rules."},
    {"slug": "system.numbering_rules.edit", "name": "Edit Running Numbers", "description": "Permission to edit document numbering rules."},
])
PERMISSION_REGISTRY.append({
    "slug": "system.modules.manage",
    "name": "Manage App Store Modules",
    "description": "Install, enable, and disable application modules for the tenant.",
})
PERMISSION_REGISTRY.extend(_crud("system", "respond_workspaces", "Respond.io Workspaces"))
PERMISSION_REGISTRY.append({
    "slug": "system.respond_workspaces.set_default",
    "name": "Set Default Respond.io Workspace",
    "description": "Mark a Respond.io workspace as the tenant default for new contact syncs.",
})
PERMISSION_REGISTRY.extend(
    [
        {
            "slug": "system.ai_assistant_chat.use",
            "name": "Use AI Assistant Chat",
            "description": "Permission to use AI assistant chat in the application.",
        },
        {
            "slug": "system.ai_assistant_settings.view",
            "name": "View AI Assistant Settings",
            "description": "Permission to view AI assistant settings.",
        },
        {
            "slug": "system.ai_assistant_settings.edit",
            "name": "Edit AI Assistant Settings",
            "description": "Permission to edit AI assistant settings.",
        },
    ]
)

# Menu / Quick Access
PERMISSION_REGISTRY.append({
    "slug": "menu.quick_access.pin",
    "name": "Pin Quick Access",
    "description": "Permission to pin menu items or folders to Quick Access.",
})
PERMISSION_REGISTRY.append({
    "slug": "menu.quick_access.unpin",
    "name": "Unpin Quick Access",
    "description": "Permission to remove items from Quick Access.",
})

# Dashboard (optional)
PERMISSION_REGISTRY.append({
    "slug": "dashboard.view",
    "name": "View Dashboard",
    "description": "Permission to access and view the dashboard.",
})

# Commercial core
for _slug, _name in [
    ("commercial_core.leads.view", "View commercial leads"),
    ("commercial_core.leads.add", "Add commercial leads"),
    ("commercial_core.leads.edit", "Edit commercial leads"),
    ("commercial_core.leads.delete", "Delete commercial leads"),
    ("commercial_core.projects.view", "View commercial projects"),
    ("commercial_core.projects.add", "Add commercial projects"),
    ("commercial_core.projects.edit", "Edit commercial projects"),
    ("commercial_core.projects.delete", "Delete commercial projects"),
    ("commercial_core.tenders.view", "View commercial tenders"),
    ("commercial_core.tenders.add", "Add commercial tenders"),
    ("commercial_core.tenders.edit", "Edit commercial tenders"),
    ("commercial_core.tenders.delete", "Delete commercial tenders"),
    ("commercial_core.quotations.view", "View commercial quotations"),
    ("commercial_core.quotations.add", "Add commercial quotations"),
    ("commercial_core.quotations.edit", "Edit commercial quotations"),
    ("commercial_core.quotations.delete", "Delete commercial quotations"),
    ("commercial_core.pipeline.view", "View commercial pipeline"),
    ("commercial_core.process_config.view", "View commercial process config"),
    ("commercial_core.process_config.edit", "Edit commercial process config"),
    ("commercial_core.email_templates.view", "View quotation email templates"),
    ("commercial_core.email_templates.edit", "Edit quotation email templates"),
]:
    PERMISSION_REGISTRY.append({"slug": _slug, "name": _name, "description": _name})

# Commercial activity
for _slug, _name in [
    ("commercial_activity.plans.view", "View activity plans"),
    ("commercial_activity.plans.add", "Add activity plans"),
    ("commercial_activity.plans.edit", "Edit activity plans"),
    ("commercial_activity.plans.delete", "Delete activity plans"),
    ("commercial_activity.tasks.view", "View activity tasks"),
    ("commercial_activity.tasks.edit", "Edit activity tasks"),
    ("commercial_activity.templates.view", "View activity templates"),
    ("commercial_activity.templates.edit", "Edit activity templates"),
]:
    PERMISSION_REGISTRY.append({"slug": _slug, "name": _name, "description": _name})

# Tickets — Jira-style internal ticketing.
# Activities/notes for a ticket reuse `tickets.tickets.view` (anyone who can see
# the ticket can read/post activities). `view_all` unlocks the full pool;
# `assign` gates the assignee picker; `export` gates list-query CSV export.
PERMISSION_REGISTRY.extend(_crud("tickets", "tickets", "Tickets"))
PERMISSION_REGISTRY.append({
    "slug": "tickets.tickets.view_all",
    "name": "View all tickets",
    "description": "Without this, tickets are scoped to raised_by / assigned_to / watcher.",
})
PERMISSION_REGISTRY.append({
    "slug": "tickets.tickets.assign",
    "name": "Assign tickets",
    "description": "Set or change the assignee on a ticket.",
})
PERMISSION_REGISTRY.append({
    "slug": "tickets.tickets.export",
    "name": "Export tickets",
    "description": "Permission to export tickets with dynamic fields.",
})


# Email Templates — designable HTML emails with Jinja2 placeholders.
PERMISSION_REGISTRY.extend(_crud("email_templates", "templates", "Email Templates"))
PERMISSION_REGISTRY.append({
    "slug": "email_templates.templates.preview",
    "name": "Preview Email Templates",
    "description": "Render a template against sample context to verify the layout.",
})


# Automation — rule-driven scheduled email sends.
PERMISSION_REGISTRY.extend(_crud("automation", "automations", "Automations"))
PERMISSION_REGISTRY.append({
    "slug": "automation.automations.run",
    "name": "Run Automation",
    "description": "Trigger an automation manually outside its schedule.",
})


def sync_permissions(db: Session, created_by_user_id: Optional[str] = None) -> int:
    """
    Idempotent sync: ensure every slug in PERMISSION_REGISTRY exists in user_permissions.
    Creates missing ones; does not change existing. Returns count of newly created.
    """
    existing = {row.slug for row in db.query(UserPermission.slug).all()}
    created = 0
    for entry in PERMISSION_REGISTRY:
        slug = entry["slug"]
        if slug in existing:
            continue
        perm = UserPermission(
            slug=slug,
            name=entry["name"],
            description=entry.get("description"),
            created_by_user_id=created_by_user_id,
        )
        db.add(perm)
        created += 1
        existing.add(slug)
    if created:
        db.commit()
    return created
