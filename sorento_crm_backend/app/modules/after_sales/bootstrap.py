"""After-sales service module bootstrap (PLAN-service-jobs-p1-12nov.md).

`MODULE_KEY` is what `require_module_enabled_with_api_key` gates `/api/v1/after-sales/*` on.
Standalone by owner ruling (12 Nov 2026): it owns its tables (`service_jobs`, `technicians`) and
changes nothing in the live Complaints module; a job may name a complaint as a plain reference.
"""

MODULE_KEY = "after_sales"
