"""After-sales service module manifest."""
from __future__ import annotations

MODULE_KEY = "after_sales"
DISPLAY_NAME = "After-sales service"
DESCRIPTION = "Service jobs, the dispatch board and technicians."
DEPENDENCIES = ("base", "complaints")
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("after-sales",)
GUARD_KEY = "after_sales"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/service_jobs.py",
    "app/schemas/service_jobs.py",
    "app/api/v1/after_sales/",
    "app/services/service_job_service.py",
    "app/services/technician_service.py",
)
EXPORT_FILES_FRONTEND = ("app/(protected)/after-sales/",)
