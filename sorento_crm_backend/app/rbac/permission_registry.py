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

# Order Management
PERMISSION_REGISTRY.extend(_crud("order_management", "orders", "Orders"))
PERMISSION_REGISTRY.append({"slug": "order_management.orders.import", "name": "Import Orders", "description": "Permission to bulk import orders."})
PERMISSION_REGISTRY.append({"slug": "order_management.orders.bulk_delete", "name": "Bulk Delete Orders", "description": "Permission to bulk delete orders."})
PERMISSION_REGISTRY.extend(_crud("order_management", "order_statuses", "Order Statuses"))
PERMISSION_REGISTRY.extend(_crud("order_management", "customers", "Customers"))

# Complaint Management
PERMISSION_REGISTRY.extend(_crud("complaint_management", "complaints", "Complaints"))

# SLA Management
PERMISSION_REGISTRY.extend(_crud("sla_management", "sla_policies", "SLA Policies"))
PERMISSION_REGISTRY.extend(_crud("sla_management", "conversation_sla_tracking", "Conversation SLA Tracking"))
PERMISSION_REGISTRY.extend(_crud("sla_management", "escalation_logs", "SLA Event Logs"))

# Master Data (Products)
PERMISSION_REGISTRY.extend(_crud("master_data", "products", "Products"))
PERMISSION_REGISTRY.append({"slug": "master_data.products.import", "name": "Import Products", "description": "Permission to bulk import products."})
PERMISSION_REGISTRY.append({"slug": "master_data.products.bulk_delete", "name": "Bulk Delete Products", "description": "Permission to bulk delete products."})
PERMISSION_REGISTRY.extend(_crud("master_data", "product_attachments", "Product Attachments"))
PERMISSION_REGISTRY.extend(_crud("master_data", "product_categories", "Product Categories"))
PERMISSION_REGISTRY.extend(_crud("master_data", "brands", "Brands"))
PERMISSION_REGISTRY.extend(_crud("master_data", "units_of_measure", "Units of Measure"))

# Procurement
PERMISSION_REGISTRY.extend(_crud("procurement", "suppliers", "Suppliers"))
PERMISSION_REGISTRY.extend(_crud("procurement", "product_suppliers", "Product-Suppliers"))
PERMISSION_REGISTRY.extend(_crud("procurement", "packing_lists", "Packing Lists"))
PERMISSION_REGISTRY.extend(_crud("procurement", "spo_allocations", "SPO Allocations"))
PERMISSION_REGISTRY.append({"slug": "procurement.spo_allocations.import", "name": "Import SPO Allocations", "description": "Permission to import SPO allocations."})
PERMISSION_REGISTRY.extend(_crud("procurement", "grn", "GRN"))
PERMISSION_REGISTRY.append({"slug": "procurement.grn.import", "name": "Import GRN", "description": "Permission to import GRN."})
PERMISSION_REGISTRY.extend(_crud("procurement", "picking_lines", "Picking Lines"))
PERMISSION_REGISTRY.extend(_crud("procurement", "stock_inquiries", "Stock Inquiries"))
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
PERMISSION_REGISTRY.extend(_crud("forms", "kol_video_request", "KOL Video Request"))

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
