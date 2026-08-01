"""Sales order drafts, findings, publish, and the revision delta (P7, P11). Contract sections 5 and 6.

Routes live at the module root rather than under `/projects/{project_id}` because they
are addressed both ways: nested for listing, and directly by id for everything else.
See `documentation/plans/CONTRACT-project-lead-to-so.md`.
"""
from fastapi import APIRouter

router = APIRouter()
