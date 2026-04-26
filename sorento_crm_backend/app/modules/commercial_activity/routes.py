"""Commercial activity plan: statuses, templates, tasks on master quotations."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_permission, require_permission_with_api_key
from sqlalchemy.orm import joinedload

from app.modules.commercial_core.models import CommercialMasterQuotation
from app.modules.commercial_activity.models import CommercialActivityPlanApplication, CommercialQuotationActivityTask
from app.modules.commercial_activity.schemas import (
    ActivityPlanApplicationOut,
    ApplyActivityTemplateBody,
    CommercialActivityTaskStatusCreate,
    CommercialActivityTaskStatusOut,
    CommercialActivityTaskStatusUpdate,
    CommercialActivityTemplateCreate,
    CommercialActivityTemplateNodeCreate,
    CommercialActivityTemplateNodeOut,
    CommercialActivityTemplateNodeUpdate,
    CommercialActivityTemplateOut,
    CommercialActivityTemplateUpdate,
    commercial_activity_template_out_without_nodes,
    CommercialProjectTaskCategoryCreate,
    CommercialProjectTaskCategoryOut,
    CommercialProjectTaskCategoryUpdate,
    CommercialQuotationActivityTaskCreate,
    CommercialQuotationActivityTaskOut,
    CommercialQuotationActivityTaskUpdate,
    ReorderActivityTasksBody,
)
from app.schemas.common import ListResponse, PaginationResponse
from app.modules.commercial_activity.services.plan_service import CommercialActivityPlanError, CommercialActivityPlanService

router = APIRouter()


def _svc(db: Session) -> CommercialActivityPlanService:
    return CommercialActivityPlanService(db)


def _handle(err: CommercialActivityPlanError) -> None:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err.message)


# --- statuses ---


@router.get("/statuses", response_model=List[CommercialActivityTaskStatusOut])
def list_statuses(
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("commercial_core.activity_task_statuses.view")),
):
    return _svc(db).list_statuses(active_only=active_only)


@router.post("/statuses", response_model=CommercialActivityTaskStatusOut)
def create_status(
    body: CommercialActivityTaskStatusCreate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_task_statuses.add")),
):
    try:
        row = _svc(db).create_status(
            code=body.code,
            label=body.label,
            sort_order=body.sort_order,
            is_default=body.is_default,
            is_terminal=body.is_terminal,
            is_active=body.is_active,
        )
        return row
    except CommercialActivityPlanError as e:
        _handle(e)


@router.patch("/statuses/{status_id}", response_model=CommercialActivityTaskStatusOut)
def update_status(
    status_id: str,
    body: CommercialActivityTaskStatusUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_task_statuses.edit")),
):
    try:
        fields = body.model_dump(exclude_unset=True)
        return _svc(db).update_status(status_id, **fields)
    except CommercialActivityPlanError as e:
        _handle(e)


@router.delete("/statuses/{status_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_status(
    status_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_task_statuses.delete")),
):
    try:
        _svc(db).delete_status(status_id)
    except CommercialActivityPlanError as e:
        _handle(e)


# --- project task categories ---


@router.get("/task-categories", response_model=List[CommercialProjectTaskCategoryOut])
def list_task_categories(
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("commercial_core.activity_templates.view")),
):
    rows = _svc(db).list_task_categories(active_only=active_only)
    return [CommercialProjectTaskCategoryOut.model_validate(r) for r in rows]


@router.post("/task-categories", response_model=CommercialProjectTaskCategoryOut)
def create_task_category(
    body: CommercialProjectTaskCategoryCreate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_templates.edit")),
):
    try:
        row = _svc(db).create_task_category(code=body.code, label=body.label, sort_order=body.sort_order)
        return CommercialProjectTaskCategoryOut.model_validate(row)
    except CommercialActivityPlanError as e:
        _handle(e)


@router.patch("/task-categories/{category_code}", response_model=CommercialProjectTaskCategoryOut)
def update_task_category(
    category_code: str,
    body: CommercialProjectTaskCategoryUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_templates.edit")),
):
    try:
        row = _svc(db).update_task_category(
            category_code,
            label=body.label,
            sort_order=body.sort_order,
            is_active=body.is_active,
        )
        return CommercialProjectTaskCategoryOut.model_validate(row)
    except CommercialActivityPlanError as e:
        _handle(e)


@router.delete("/task-categories/{category_code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_category(
    category_code: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_templates.edit")),
):
    try:
        _svc(db).delete_task_category(category_code)
    except CommercialActivityPlanError as e:
        _handle(e)


# --- templates ---


@router.get("/templates", response_model=List[CommercialActivityTemplateOut])
def list_templates(
    active_only: bool = Query(False),
    template_scope: Optional[str] = Query(
        None,
        description="Filter by template_scope: project | quotation",
    ),
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("commercial_core.activity_templates.view")),
):
    rows = _svc(db).list_templates(active_only=active_only, template_scope=template_scope)
    return [commercial_activity_template_out_without_nodes(r) for r in rows]


@router.get("/templates/{template_id}", response_model=CommercialActivityTemplateOut)
def get_template(
    template_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("commercial_core.activity_templates.view")),
):
    row = _svc(db).get_template(template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found.")
    tree = _svc(db).build_template_node_tree(template_id)
    out = commercial_activity_template_out_without_nodes(row).model_dump()
    out["nodes"] = tree
    return out


@router.post("/templates", response_model=CommercialActivityTemplateOut)
def create_template(
    body: CommercialActivityTemplateCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.activity_templates.add")),
):
    row = _svc(db).create_template(
        name=body.name,
        description=body.description,
        is_active=body.is_active,
        template_scope=body.template_scope,
        created_by_user_id=str(current_user.get("id") or "") or None,
    )
    return commercial_activity_template_out_without_nodes(row)


@router.patch("/templates/{template_id}", response_model=CommercialActivityTemplateOut)
def update_template(
    template_id: str,
    body: CommercialActivityTemplateUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_templates.edit")),
):
    try:
        row = _svc(db).update_template(
            template_id,
            name=body.name,
            description=body.description,
            is_active=body.is_active,
            template_scope=body.template_scope,
        )
        return commercial_activity_template_out_without_nodes(row)
    except CommercialActivityPlanError as e:
        _handle(e)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_templates.delete")),
):
    try:
        _svc(db).delete_template(template_id)
    except CommercialActivityPlanError as e:
        _handle(e)


@router.post("/templates/{template_id}/nodes", response_model=CommercialActivityTemplateNodeOut)
def create_template_node(
    template_id: str,
    body: CommercialActivityTemplateNodeCreate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_templates.edit")),
):
    try:
        row = _svc(db).create_template_node(
            template_id,
            {
                "parent_id": body.parent_id,
                "sort_order": body.sort_order,
                "title": body.title,
                "category_code": body.category_code,
                "is_service_task": body.is_service_task,
                "description": body.description,
                "default_status_id": body.default_status_id,
                "default_offset_days": body.default_offset_days,
                "lead_time_days": body.lead_time_days,
                "dependency_node_ids": body.dependency_node_ids,
            },
        )
        return CommercialActivityTemplateNodeOut.model_validate(row)
    except CommercialActivityPlanError as e:
        _handle(e)


@router.patch("/templates/{template_id}/nodes/{node_id}", response_model=CommercialActivityTemplateNodeOut)
def update_template_node(
    template_id: str,
    node_id: str,
    body: CommercialActivityTemplateNodeUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_templates.edit")),
):
    try:
        row = _svc(db).get_template(template_id)
        if not row:
            raise HTTPException(status_code=404, detail="Template not found.")
        n = _svc(db).update_template_node(node_id, body.model_dump(exclude_unset=True))
        if str(n.template_id) != template_id:
            raise HTTPException(status_code=404, detail="Node not found.")
        return CommercialActivityTemplateNodeOut.model_validate(n)
    except CommercialActivityPlanError as e:
        _handle(e)


@router.delete("/templates/{template_id}/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template_node(
    template_id: str,
    node_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_templates.edit")),
):
    from app.modules.commercial_activity.models import CommercialActivityTemplateNode

    row = _svc(db).get_template(template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found.")
    n = db.query(CommercialActivityTemplateNode).filter(CommercialActivityTemplateNode.id == node_id).first()
    if not n or str(n.template_id) != template_id:
        raise HTTPException(status_code=404, detail="Node not found.")
    try:
        _svc(db).delete_template_node(node_id)
    except CommercialActivityPlanError as e:
        _handle(e)


# --- tasks per master quotation ---


from pydantic import BaseModel as _PydBaseModel


class _ActivityTasksKanbanRequest(_PydBaseModel):
    quick_search: Optional[str] = None
    master_quotation_id: Optional[str] = None
    assignee_user_id: Optional[str] = None


class _ActivityTaskStatusUpdate(_PydBaseModel):
    status_code: str


@router.post("/activity-tasks/kanban")
def activity_tasks_kanban(
    body: _ActivityTasksKanbanRequest,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_tasks.view")),
):
    return _svc(db).list_tasks_kanban(
        quick_search=body.quick_search,
        master_quotation_id=(body.master_quotation_id or "").strip() or None,
        assignee_user_id=(body.assignee_user_id or "").strip() or None,
    )


@router.post("/activity-tasks/{task_id}/status")
def update_activity_task_status(
    task_id: str,
    body: _ActivityTaskStatusUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_tasks.edit")),
):
    svc = _svc(db)
    st = (
        db.query(svc.list_statuses.__self__.__class__.__bases__[0])
        if False
        else None
    )
    try:
        row = svc.update_task(task_id, {"status_id": _resolve_status_id(svc, body.status_code)})
        return {"id": str(row.id), "status_id": str(row.status_id)}
    except CommercialActivityPlanError as exc:
        _handle(exc)


def _resolve_status_id(svc: CommercialActivityPlanService, status_code: str) -> str:
    code = (status_code or "").strip()
    if not code:
        raise CommercialActivityPlanError("Status code required.")
    rows = svc.list_statuses(active_only=True)
    for r in rows:
        if r.code == code:
            return str(r.id)
    raise CommercialActivityPlanError("Invalid status.")


@router.get("/master-quotations/{master_quotation_id}/activity-tasks/tree")
def list_activity_tasks_tree(
    master_quotation_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("commercial_core.activity_tasks.view")),
):
    try:
        return _svc(db).build_task_tree(master_quotation_id)
    except CommercialActivityPlanError as e:
        _handle(e)


@router.get(
    "/master-quotations/{master_quotation_id}/activity-tasks",
    response_model=ListResponse[CommercialQuotationActivityTaskOut],
)
def list_activity_tasks_flat(
    master_quotation_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("commercial_core.activity_tasks.view")),
):
    try:
        rows = _svc(db).list_tasks_flat(master_quotation_id)
        out: List[CommercialQuotationActivityTaskOut] = []
        for t in rows:
            mq = t.master_quotation
            tender = mq.tender if mq else None
            st = t.status
            out.append(
                CommercialQuotationActivityTaskOut(
                    id=str(t.id),
                    master_quotation_id=str(t.master_quotation_id),
                    parent_id=str(t.parent_id) if t.parent_id else None,
                    source_template_node_id=str(t.source_template_node_id) if t.source_template_node_id else None,
                    sort_order=t.sort_order,
                    title=t.title,
                    status_id=str(t.status_id),
                    assignee_user_id=t.assignee_user_id,
                    due_at=t.due_at,
                    remind_at=t.remind_at,
                    last_reminder_sent_at=t.last_reminder_sent_at,
                    is_tender_level=bool(t.is_tender_level),
                    deleted_at=t.deleted_at,
                    created_at=t.created_at,
                    updated_at=t.updated_at,
                    quotation_code=mq.quotation_code if mq else None,
                    tender_code=tender.tender_code if tender else None,
                    status_code=st.code if st else None,
                    status_label=st.label if st else None,
                    children=[],
                )
            )
        return ListResponse(
            data=out,
            pagination=PaginationResponse(total=len(out), page=1, limit=max(len(out), 1)),
            empty=len(out) == 0,
        )
    except CommercialActivityPlanError as e:
        _handle(e)


@router.post("/master-quotations/{master_quotation_id}/activity-tasks", response_model=CommercialQuotationActivityTaskOut)
def create_activity_task(
    master_quotation_id: str,
    body: CommercialQuotationActivityTaskCreate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_tasks.add")),
):
    try:
        t = _svc(db).create_task(master_quotation_id, body.model_dump(exclude_unset=True))
        return _task_to_out(db, str(t.id))
    except CommercialActivityPlanError as e:
        _handle(e)


@router.patch("/master-quotations/{master_quotation_id}/activity-tasks/{task_id}", response_model=CommercialQuotationActivityTaskOut)
def update_activity_task(
    master_quotation_id: str,
    task_id: str,
    body: CommercialQuotationActivityTaskUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_tasks.edit")),
):
    t0 = db.query(CommercialQuotationActivityTask).filter(CommercialQuotationActivityTask.id == task_id).first()
    if not t0 or str(t0.master_quotation_id) != master_quotation_id:
        raise HTTPException(status_code=404, detail="Task not found.")
    try:
        _svc(db).update_task(task_id, body.model_dump(exclude_unset=True))
        return _task_to_out(db, task_id)
    except CommercialActivityPlanError as e:
        _handle(e)


@router.delete("/master-quotations/{master_quotation_id}/activity-tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity_task(
    master_quotation_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_tasks.delete")),
):
    t0 = db.query(CommercialQuotationActivityTask).filter(CommercialQuotationActivityTask.id == task_id).first()
    if not t0 or str(t0.master_quotation_id) != master_quotation_id:
        raise HTTPException(status_code=404, detail="Task not found.")
    try:
        _svc(db).soft_delete_task(task_id, cascade_children=True)
    except CommercialActivityPlanError as e:
        _handle(e)


@router.post("/master-quotations/{master_quotation_id}/activity-tasks/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_activity_tasks(
    master_quotation_id: str,
    body: ReorderActivityTasksBody,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("commercial_core.activity_tasks.edit")),
):
    try:
        _svc(db).reorder_tasks(master_quotation_id, body.parent_id, [(i.id, i.sort_order) for i in body.items])
    except CommercialActivityPlanError as e:
        _handle(e)


@router.post("/master-quotations/{master_quotation_id}/activity-plan/apply-template")
def apply_activity_template(
    master_quotation_id: str,
    body: ApplyActivityTemplateBody,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.activity_tasks.add")),
):
    try:
        return _svc(db).apply_template(
            master_quotation_id,
            body.template_id,
            anchor_at=body.anchor_at,
            applied_by_user_id=str(current_user.get("id") or "") or None,
        )
    except CommercialActivityPlanError as e:
        _handle(e)


@router.get("/master-quotations/{master_quotation_id}/activity-plan/applications", response_model=List[ActivityPlanApplicationOut])
def list_plan_applications(
    master_quotation_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("commercial_core.activity_tasks.view")),
):
    try:
        _svc(db)._get_master_or_raise(master_quotation_id)
    except CommercialActivityPlanError as e:
        _handle(e)
    rows = (
        db.query(CommercialActivityPlanApplication)
        .filter(CommercialActivityPlanApplication.master_quotation_id == master_quotation_id)
        .order_by(CommercialActivityPlanApplication.applied_at.desc())
        .all()
    )
    return [ActivityPlanApplicationOut.model_validate(r) for r in rows]


def _task_to_out(db: Session, task_id: str) -> CommercialQuotationActivityTaskOut:
    t = (
        db.query(CommercialQuotationActivityTask)
        .options(
            joinedload(CommercialQuotationActivityTask.master_quotation).joinedload(CommercialMasterQuotation.tender),
            joinedload(CommercialQuotationActivityTask.status),
        )
        .filter(CommercialQuotationActivityTask.id == task_id)
        .first()
    )
    if not t:
        raise HTTPException(status_code=404, detail="Task not found.")
    mq = t.master_quotation
    tender = mq.tender if mq else None
    st = t.status
    return CommercialQuotationActivityTaskOut(
        id=str(t.id),
        master_quotation_id=str(t.master_quotation_id),
        parent_id=str(t.parent_id) if t.parent_id else None,
        source_template_node_id=str(t.source_template_node_id) if t.source_template_node_id else None,
        sort_order=t.sort_order,
        title=t.title,
        status_id=str(t.status_id),
        assignee_user_id=t.assignee_user_id,
        due_at=t.due_at,
        remind_at=t.remind_at,
        last_reminder_sent_at=t.last_reminder_sent_at,
        is_tender_level=bool(t.is_tender_level),
        deleted_at=t.deleted_at,
        created_at=t.created_at,
        updated_at=t.updated_at,
        quotation_code=mq.quotation_code if mq else None,
        tender_code=tender.tender_code if tender else None,
        status_code=st.code if st else None,
        status_label=st.label if st else None,
        children=[],
    )
