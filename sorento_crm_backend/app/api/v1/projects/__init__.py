"""Project Sales API routes."""
from fastapi import APIRouter

from app.api.v1.projects import leads, parties, projects, tasks, types

router = APIRouter()

# Config first: /config/types and /config/templates would otherwise be captured by
# the /{project_id} path in the projects router.
router.include_router(types.router, prefix="/config", tags=["project-config"])
# Tasks mount at the module root because they span three shapes: nested under a
# project, the cross-project /my-tasks worklist, and template checklist admin. Before
# the projects router, so /projects/{id}/tasks is not captured by /projects/{id}.
router.include_router(tasks.router, tags=["project-tasks"])
router.include_router(parties.router, prefix="/parties", tags=["project-parties"])
# Leads before projects for the same reason config is: /leads/{id}/qualify returns a
# PROJECT, but the route itself lives under the leads prefix.
router.include_router(leads.router, prefix="/leads", tags=["project-leads"])
router.include_router(projects.router, prefix="/projects", tags=["projects"])
