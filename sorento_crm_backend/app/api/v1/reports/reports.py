"""One set of routes for EVERY report. The report key is a parameter, never a code path.

The catalog is permission-filtered, each report is gated on its own slug, and publishing a
view (or making one the default for everyone) additionally needs `reports.views.publish`.
Report #2 adds a dataset and a definition and appears here with no route work at all.

Mounted under the procurement module guard for now: the only report is the sponsorship one,
and a "reports" module key would be a module nobody can install anything into. It moves when
a second module owns a report (PLAN-reporting-foundation, Architecture).
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas.report import (
    ReportCatalogColumn,
    ReportCatalogEntry,
    ReportCatalogResponse,
    ReportDateBasisParam,
    ReportExportResult,
    ReportMeta,
    ReportParamMeta,
    ReportPeriodParam,
    ReportResult,
    ReportRunRequest,
    ReportSelectOption,
    ReportSelectParamMeta,
    ReportView,
    ReportViewCreate,
    ReportViewPublish,
    ReportViews,
)
from app.services.error_handler import AppException, handle_not_found
from app.services.reports import engine, registry as reg
from app.services.reports.views_service import PUBLISH_PERMISSION, ReportViewsService
from app.services.user_service import UserPermissionService
from app.services.uuid_path_param import validate_uuid_path

logger = logging.getLogger(__name__)

router = APIRouter()


def _holds(db: Session, user: dict, slug: str) -> bool:
    return bool(UserPermissionService(db).check_user_has_permission(user["id"], slug))


def _definition(key: str) -> reg.ReportDefinition:
    definition = reg.get(key)
    if definition is None:
        raise handle_not_found("Report", key)
    return definition


def _authorised(db: Session, user: dict, key: str) -> reg.ReportDefinition:
    """The report, or 403/404. 404 first: an unknown key is not a permission question."""
    definition = _definition(key)
    if not _holds(db, user, definition.permission):
        raise AppException(
            status_code=status.HTTP_403_FORBIDDEN,
            message=f"Permission required: {definition.permission}",
            code="FORBIDDEN",
        )
    return definition


def _require_publish(db: Session, user: dict) -> None:
    if not _holds(db, user, PUBLISH_PERMISSION):
        raise AppException(
            status_code=status.HTTP_403_FORBIDDEN,
            message=f"Permission required: {PUBLISH_PERMISSION}",
            code="FORBIDDEN",
        )


def _years(db: Session, definition: reg.ReportDefinition) -> List[int]:
    """The years the filter bar offers. The dataset knows; otherwise, a sane window."""
    from datetime import date

    if definition.dataset.years is not None:
        return list(definition.dataset.years(db))
    this_year = date.today().year
    return [this_year - offset for offset in range(0, 5)]


def _params_meta(db: Session, definition: reg.ReportDefinition) -> List[ReportParamMeta]:
    metas: List[ReportParamMeta] = []
    for param in definition.params:
        if isinstance(param, reg.DateBasisParam):
            metas.append(
                ReportDateBasisParam(
                    key=param.key,
                    label=param.label,
                    default=param.default,
                    options=[
                        ReportSelectOption(value=b.key, label=b.label)
                        for b in definition.dataset.date_bases
                    ],
                )
            )
        elif isinstance(param, reg.PeriodParam):
            metas.append(
                ReportPeriodParam(
                    key=param.key,
                    label=param.label,
                    default=param.resolved_default(),
                    years=_years(db, definition),
                )
            )
        elif isinstance(param, reg.SelectParam):
            metas.append(
                ReportSelectParamMeta(
                    key=param.key,
                    label=param.label,
                    multi=param.multi,
                    clearable=param.clearable,
                    default=list(param.default),
                    options=[
                        ReportSelectOption(value=value, label=label)
                        for value, label in param.options(db)
                    ],
                )
            )
    return metas


@router.get("", response_model=ReportCatalogResponse)
def list_reports(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportCatalogResponse:
    """Every report the caller may see. A report they may not is absent, not disabled."""
    return ReportCatalogResponse(
        reports=[
            ReportCatalogEntry(key=d.key, title=d.title, permission=d.permission)
            for d in reg.all_definitions()
            if _holds(db, current_user, d.permission)
        ]
    )


@router.get("/{key}", response_model=ReportMeta)
def get_report_meta(
    key: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportMeta:
    definition = _authorised(db, current_user, key)
    default_view = ReportViewsService(db).default_config(key) or engine.view_config(definition)
    return ReportMeta(
        key=definition.key,
        title=definition.title,
        permission=definition.permission,
        params=_params_meta(db, definition),
        catalog=[
            ReportCatalogColumn(
                key=c.key, label=c.label, type=c.type, tag=c.tag, size=c.size
            )
            for c in definition.dataset.columns
        ],
        default_view=default_view,
        can_publish=_holds(db, current_user, PUBLISH_PERMISSION),
    )


def _params_of(body: ReportRunRequest) -> dict:
    """One source for the params of a run.

    Top-level params are what the FILTER BAR is showing, so they win. A body that carries
    only a view (which is how a saved view is applied) runs on the params that view was
    saved with, rather than silently on the report's own defaults.
    """
    if body.params:
        return dict(body.params)
    return dict(body.view.params) if body.view else {}


@router.post("/{key}/run", response_model=ReportResult)
def run_report(
    key: str,
    body: ReportRunRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportResult:
    """Both layouts over one row set, capped (the export path is not)."""
    definition = _authorised(db, current_user, key)
    return engine.run(db, definition, _params_of(body), body.view)


#: Anything a filesystem or a Content-Disposition header reads as structure. The period
#: label carries slashes on a custom range ("15/01/2026 TO 10/03/2026").
_FILENAME_UNSAFE = str.maketrans({c: "-" for c in '/\\:*?"<>|'})


def _export_filename(definition: reg.ReportDefinition, period: engine.Period) -> str:
    """The file names the period it covers, the way the report's own labels do.

    The year alone put January, February and the whole of 2026 in My Downloads under one
    name, with only a timestamp to tell three different workbooks apart. A whole year is
    still written as the year: "JAN-DEC'26" is the label a total row wants, not a filename.
    """
    if period.kind == "year":
        suffix = str(period.start.year)
    else:
        suffix = period.compact_label or str(period.start.year)
    suffix = suffix.translate(_FILENAME_UNSAFE)
    return f"{definition.title}-{suffix}.xlsx"


@router.post("/{key}/export", response_model=ReportExportResult)
def export_report(
    key: str,
    body: ReportRunRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportExportResult:
    """Queue the workbook. It surfaces through the existing My Downloads drawer (AC-A8)."""
    from app.config import settings
    from app.services import queue_service
    from app.services.download_service import DownloadService
    from app.tasks.report_export_tasks import generate_report_xlsx

    definition = _authorised(db, current_user, key)
    # Validate the params here rather than on the worker: a 422 the user can act on beats a
    # download row that fails a minute later in a drawer.
    params = _params_of(body)
    ctx = engine.resolve(db, definition, params)
    filename = _export_filename(definition, ctx.period)

    view = body.view or engine.view_config(definition)
    engine.validate_view(definition, view)
    download = DownloadService(db).create(
        user_id=str(current_user["id"]),
        kind="report_xlsx",
        filename=filename,
    )
    try:
        queue_service.enqueue_job(
            generate_report_xlsx,
            str(download.id),
            definition.key,
            params,
            view.model_dump(mode="json"),
            str(current_user["id"]),
            queue_name=settings.report_export_queue,
            job_timeout=600,
        )
    except Exception as e:  # noqa: BLE001 - Redis down must not leave a row spinning
        DownloadService(db).mark_failed(str(download.id), f"Could not queue the export: {e}")
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Could not queue the export. Please try again.",
            code="EXPORT_QUEUE_FAILED",
        )
    return ReportExportResult(download_id=str(download.id), filename=filename)


# ------------------------------------------------------------------------- views


@router.get("/{key}/views", response_model=ReportViews)
def list_report_views(
    key: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportViews:
    _authorised(db, current_user, key)
    return ReportViewsService(db).list_for(key, str(current_user["id"]))


def _validate_stored(
    db: Session,
    definition: reg.ReportDefinition,
    view_id: str,
    user_id: str,
    *,
    owner_only: bool,
) -> None:
    """A stored view, checked before it is handed to anybody else.

    Save validates what the screen sent, but a view saved last year can name a column the
    catalog has since lost. Publishing or defaulting one hands every user a report that
    answers 422 on open, so the fault belongs to the person doing the publishing. A view
    the caller may not act on - or one that does not exist - is left to the service, which
    answers the 404 or the 409 it always did.
    """
    stored = ReportViewsService(db).actionable_config(
        definition.key, view_id, user_id, owner_only=owner_only
    )
    if stored is not None:
        engine.validate_view(definition, stored)


@router.post("/{key}/views", response_model=ReportView)
def create_report_view(
    key: str,
    body: ReportViewCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportView:
    definition = _authorised(db, current_user, key)
    # A view is persisted for later, so it is validated now: an unrunnable one could
    # otherwise be saved, published, made everyone's default, and 422 every run after that.
    engine.validate_view(definition, body.view)
    return ReportViewsService(db).create(key, str(current_user["id"]), body.name, body.view)


@router.delete("/{key}/views/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report_view(
    key: str,
    view_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    _authorised(db, current_user, key)
    validate_uuid_path(view_id, resource="View")
    ReportViewsService(db).delete(key, view_id, str(current_user["id"]))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{key}/views/{view_id}/publish", response_model=ReportView)
def publish_report_view(
    key: str,
    view_id: str,
    body: ReportViewPublish,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportView:
    definition = _authorised(db, current_user, key)
    _require_publish(db, current_user)
    validate_uuid_path(view_id, resource="View")
    if body.is_shared:
        _validate_stored(db, definition, view_id, str(current_user["id"]), owner_only=True)
    return ReportViewsService(db).publish(key, view_id, str(current_user["id"]), body.is_shared)


@router.post("/{key}/views/{view_id}/set-default", response_model=ReportView)
def set_default_report_view(
    key: str,
    view_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportView:
    """Make one shared view the report default for everyone. At most one per report."""
    definition = _authorised(db, current_user, key)
    _require_publish(db, current_user)
    validate_uuid_path(view_id, resource="View")
    _validate_stored(db, definition, view_id, str(current_user["id"]), owner_only=False)
    return ReportViewsService(db).set_default(key, view_id, str(current_user["id"]))
