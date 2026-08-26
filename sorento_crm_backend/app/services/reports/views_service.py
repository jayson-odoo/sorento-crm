"""Saved views: personal by default, shared when published, one shared view the default.

Mine vs Shared, settled while building S2:

- **Mine** = the views the caller OWNS, published ones included (the menu badges those).
  A view leaving its author's own list the moment they share it is how somebody loses the
  view they just made.
- **Shared** = OTHER people's published views.

Ownership is the write rule: delete and publish are the owner's, and a view that is
not the caller's answers 404 rather than 403 - a view id in someone else's hand is not a
licence to learn that it exists. Setting the report default additionally needs
`reports.views.publish` (enforced at the route) and works on any SHARED view, or on one
the caller owns (owner publishes and defaults in one step).
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.report_view import ReportView as ReportViewRow
from app.schemas.report import ReportView, ReportViewConfig, ReportViews
from app.services.error_handler import AppException, handle_not_found

PUBLISH_PERMISSION = "reports.views.publish"


class ReportViewsService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ reads

    def list_for(self, report_key: str, user_id: str) -> ReportViews:
        rows = (
            self.db.query(ReportViewRow)
            .filter(ReportViewRow.report_key == report_key)
            .filter(
                (ReportViewRow.owner_user_id == str(user_id))
                | (ReportViewRow.is_shared.is_(True))
            )
            .order_by(ReportViewRow.name, ReportViewRow.id)
            .all()
        )
        names = self._owner_names([r.owner_user_id for r in rows])
        mine = [self._to_schema(r, names) for r in rows if r.owner_user_id == str(user_id)]
        shared = [self._to_schema(r, names) for r in rows if r.owner_user_id != str(user_id)]
        return ReportViews(mine=mine, shared=shared)

    def default_config(self, report_key: str) -> Optional[ReportViewConfig]:
        """The shared default view's config, when a holder of the publish grant set one."""
        row = (
            self.db.query(ReportViewRow)
            .filter(
                ReportViewRow.report_key == report_key,
                ReportViewRow.is_default.is_(True),
            )
            .first()
        )
        return ReportViewConfig.model_validate(row.view) if row else None

    # ----------------------------------------------------------------- writes

    def create(
        self, report_key: str, user_id: str, name: str, config: ReportViewConfig
    ) -> ReportView:
        cleaned = (name or "").strip()
        if not cleaned:
            raise AppException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                message="A view needs a name",
                code="VALIDATION_ERROR",
            )
        row = ReportViewRow(
            report_key=report_key,
            owner_user_id=str(user_id),
            name=cleaned,
            view=config.model_dump(mode="json"),
        )
        self.db.add(row)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            raise AppException(
                status_code=status.HTTP_409_CONFLICT,
                message=f'You already have a view called "{cleaned}"',
                code="CONFLICT",
            )
        self.db.commit()
        self.db.refresh(row)
        return self._to_schema(row, self._owner_names([row.owner_user_id]))

    def delete(self, report_key: str, view_id: str, user_id: str) -> None:
        row = self._owned(report_key, view_id, user_id)
        self.db.delete(row)
        self.db.commit()

    def publish(self, report_key: str, view_id: str, user_id: str, is_shared: bool) -> ReportView:
        row = self._owned(report_key, view_id, user_id)
        row.is_shared = bool(is_shared)
        if not row.is_shared:
            # A private view cannot be everyone's default.
            row.is_default = False
        self.db.commit()
        self.db.refresh(row)
        return self._to_schema(row, self._owner_names([row.owner_user_id]))

    def set_default(self, report_key: str, view_id: str, user_id: str) -> ReportView:
        """Make one SHARED view the report default for everyone.

        The owner may publish and default in one step, which is the screen's own flow. Anyone
        else has to work with a view its author already published: without that rule a holder
        of the publish grant could expose somebody else's PRIVATE view to the whole company
        by knowing its id.
        """
        row = self._row(report_key, view_id)
        if row is None:
            raise handle_not_found("View", view_id)
        if not row.is_shared and row.owner_user_id != str(user_id):
            raise AppException(
                status_code=status.HTTP_409_CONFLICT,
                message="That view is not shared. Only a shared view can be the report default.",
                code="CONFLICT",
            )
        # Clear first: the partial unique index would otherwise reject the second default.
        self.db.query(ReportViewRow).filter(
            ReportViewRow.report_key == report_key,
            ReportViewRow.is_default.is_(True),
            ReportViewRow.id != row.id,
        ).update({"is_default": False}, synchronize_session=False)
        row.is_shared = True  # the report default is shared by definition
        row.is_default = True
        self.db.commit()
        self.db.refresh(row)
        return self._to_schema(row, self._owner_names([row.owner_user_id]))

    # ---------------------------------------------------------------- helpers

    def _row(self, report_key: str, view_id: str) -> Optional[ReportViewRow]:
        return (
            self.db.query(ReportViewRow)
            .filter(ReportViewRow.report_key == report_key, ReportViewRow.id == str(view_id))
            .first()
        )

    def _owned(self, report_key: str, view_id: str, user_id: str) -> ReportViewRow:
        row = self._row(report_key, view_id)
        if row is None or row.owner_user_id != str(user_id):
            raise handle_not_found("View", view_id)
        return row

    def _owner_names(self, user_ids: List[str]) -> dict:
        """Display names, through the one bulk lookup the route serialisers share."""
        from app.services.project_service import resolve_user_names

        return {
            str(k): v for k, v in resolve_user_names(self.db, [i for i in user_ids if i]).items()
        }

    @staticmethod
    def _to_schema(row: ReportViewRow, names: dict) -> ReportView:
        return ReportView(
            id=str(row.id),
            name=row.name,
            is_shared=bool(row.is_shared),
            is_default=bool(row.is_default),
            owner_name=names.get(str(row.owner_user_id)),
            view=ReportViewConfig.model_validate(row.view),
        )
