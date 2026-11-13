"""Who may use the warranty configuration API (after-sales P2). One place, so an owner ruling is a one-line change.

Reads: a warranty viewer or anyone who can see service jobs. Writes: `after_sales.warranty.manage`.
"""
from app.dependencies import require_any_permission_with_api_key, require_permission

WARRANTY_VIEW = "after_sales.warranty.view"
WARRANTY_MANAGE = "after_sales.warranty.manage"
JOBS_VIEW = "after_sales.service_jobs.view"

can_read = require_any_permission_with_api_key([WARRANTY_VIEW, JOBS_VIEW])
can_write = require_permission(WARRANTY_MANAGE)
