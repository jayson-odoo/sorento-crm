"""Project Sales API routes."""
from fastapi import APIRouter

from app.api.v1.projects import parties, projects, types

router = APIRouter()

# Config first: /config/types and /config/templates would otherwise be captured by
# the /{project_id} path in the projects router.
router.include_router(types.router, prefix="/config", tags=["project-config"])
router.include_router(parties.router, prefix="/parties", tags=["project-parties"])
router.include_router(projects.router, prefix="/projects", tags=["projects"])
