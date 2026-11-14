"""AC-PROJECT-REGISTER: register a CRM project in AutoCount.

Plan: `documentation/plans/autocount/PLAN-ac-project-register-13nov.md`; UAC R1-R18.

A project is created in AutoCount once, by a press (owner, 13 Nov; Q5: editing the project later
sends nothing). Everything about the write is the AC-QTSO-CRM create path, reused as is: the
write-ahead key on the record (`_create`), the plain words for every SS answer (`_interpret`), the
audit row with the person who pressed (`_log_unlanded`) and the capability read
(`read_capabilities`). Only a `done` answer stores the AutoCount number.

Identity (U19): the company code and the project code come from the CRM record, never from the
request.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from app.models.projects import OUTCOME_LOST, Project, ProjectSalesProfile
from app.services.error_handler import AppException
from app.services.project_activity_service import record_project_event
from app.services.project_autocount_write_service import (
    _KINDS,
    UNREACHABLE,
    WAITING,
    ProjectAutocountWriteService,
    _cap,
    _landed,
)
from app.services.project_service import is_approved

# STUB until the AutoCount endpoint (owner 13 Nov): the SS route the create goes to.
PROJECTS_PATH = "documents/projects"

NOT_ELIGIBLE = "Only an approved project that is not lost can be registered in AutoCount."
ACTIVITY_TEMPLATE = "autocount_registered"
DONE_ACTIVITY = "Registered in AutoCount as {number}"
NOT_DONE_ACTIVITY = "AutoCount registration not completed: {reason}"

_DESCRIPTION_MAX = 100


def is_eligible(project: Project) -> bool:
    """R5: approved (a staff project, or an approved portal registration) and not lost."""
    return is_approved(project) and project.outcome != OUTCOME_LOST


# STUB until the AutoCount endpoint (owner 13 Nov): the body shape is the plan's guess.
def build_project_body(project: Project, profile: Optional[ProjectSalesProfile], company_code: str) -> Dict[str, Any]:
    """R8: the project code, the title, and where the project is (location, else address)."""
    entry: Dict[str, Any] = {
        "projNo": project.project_code,
        "description": (project.title or "")[:_DESCRIPTION_MAX],
    }
    place = ((profile.location if profile else None) or "").strip() or (
        (profile.address if profile else None) or ""
    ).strip()
    if place:
        entry["desc2"] = place[:_DESCRIPTION_MAX]
    entry["isActive"] = True
    return {"companyCode": company_code, "project": entry}


class ProjectAutocountRegisterService(ProjectAutocountWriteService):
    # The SS capability kind name for a project is a guess.
    KINDS = {**_KINDS, "projects": "projects"}  # STUB until the AutoCount endpoint (owner 13 Nov)

    def _project(self, project_id: str) -> Project:
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if project is None:
            raise AppException(status_code=404, message="Project not found.", code="project_not_found")
        return project

    def _profile(self, project: Project) -> Optional[ProjectSalesProfile]:
        return self.db.query(ProjectSalesProfile).filter(ProjectSalesProfile.project_id == project.id).first()

    def _create_capability(self, project: Project):
        """(enabled, the plain reason when not, the book SS names)."""
        caps, book = self.read_capabilities(project.company_id)
        create = caps["projects"]["create_doc"]
        if not create["enabled"]:
            return False, create["reason"] or WAITING, book
        if not book:
            # Owner ruling R9: no AutoCount write of any kind without a book.
            return False, WAITING, book
        return True, None, book

    # ------------------------------------------------------------ status (GET)

    def status(self, project_id: str) -> Dict[str, Any]:
        project = self._project(project_id)
        registered = bool(project.autocount_doc_key)
        eligible = is_eligible(project)
        can_register = False
        reason: Optional[str] = None
        if eligible and not registered:
            can_register, reason, _book = self._create_capability(project)
        return {
            "registered": registered,
            "project_no": project.autocount_doc_no if registered else None,
            "registered_at": project.autocount_registered_at if registered else None,
            "eligible": eligible,
            "can_register": can_register,
            "reason": reason,
        }

    # ------------------------------------------------------------ register (POST)

    def _already(self, project: Project) -> Dict[str, Any]:
        number = project.autocount_doc_no or project.project_code
        return self._blank("done", f"{number} is already in AutoCount.", project.autocount_doc_no)

    def register(self, project_id: str, actor: Optional[dict] = None) -> Dict[str, Any]:
        self._actor = actor
        project = self._project(project_id)
        if project.autocount_doc_key:
            # R13: a second press after a success sends nothing.
            return self._already(project)
        if not is_eligible(project):
            raise AppException(status_code=409, message=NOT_ELIGIBLE, code="ac_not_eligible")

        enabled, reason, book = self._create_capability(project)
        if not enabled:
            return self._blank("unreachable" if reason == UNREACHABLE else "waiting", reason)

        body = build_project_body(project, self._profile(project), self.company_code(project.company_id))
        answer, sent, _meta = self._create(project, f"crm-proj-{project.id}-create", PROJECTS_PATH, body)
        if answer is None:  # another press linked it meanwhile
            self.db.refresh(project)
            return self._already(project)

        result = self._interpret(answer, verb="registered")
        if self._is_done(answer) or _landed(answer):
            # R10: the number AutoCount answered, else the document's ProjNo, else what was sent.
            document = answer.get("document") or {}
            number = _cap(
                answer.get("docNo") or document.get("ProjNo") or (sent.get("project") or {}).get("projNo"),
                80,
            )
            project.autocount_doc_no = number
            project.autocount_doc_key = self._key_of(answer) or number
            project.autocount_book = book
            project.autocount_registered_at = datetime.utcnow()
            self.db.flush()
            if self._is_done(answer):
                result = self._blank("done", f"{number} registered in AutoCount", number)

        # R14: one Activity row per press that reached the SS with a write.
        sentence = (
            DONE_ACTIVITY.format(number=result["doc_no"])
            if result["outcome"] == "done"
            else NOT_DONE_ACTIVITY.format(reason=result["message"])
        )
        record_project_event(
            self.db,
            project=project,
            template=ACTIVITY_TEMPLATE,
            payload={"outcome": result["outcome"]},
            actor_id=(actor or {}).get("id"),
            body_text=sentence,
        )
        return result
