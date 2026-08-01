"""Customer PO document intake and handwriting review (P4, P5). Contract sections 2 and 3.

Routes live at the module root rather than under `/projects/{project_id}` because they
are addressed both ways: nested for listing, and directly by id for everything else.
See `documentation/plans/CONTRACT-project-lead-to-so.md`.
"""
from fastapi import APIRouter

router = APIRouter()
