"""Saved views (segments): personal by default, shared when published, one shared view
the default per listing key.

Generalised from `app/services/reports/views_service.py` (S4,
PLAN-scm-reorder-oi-feedback-1sep.md). Same shape, same rules:

- **Mine** = the views the caller OWNS, published ones included (the menu badges those).
  A view leaving its author's own list the moment they share it is how somebody loses the
  view they just made.
- **Shared** = OTHER people's published views.

Ownership is the write rule: publish and set-default are the owner's (or, for
set-default, anyone holding the publish grant acting on an already-shared view) - and a
view that is not the caller's answers 404 rather than 403, the same reasoning
`ReportViewsService` documents.

Delete is NOT here as a direct write: it runs through the deferred-action registry
(`app/services/record_actions.py`, key `saved_view.delete`, `permission=OWN_RECORD`) so
the frontend gets the standard countdown rather than a confirmation dialog. `delete()`
below is the one line that record action calls.

Unlike `ReportViewsService`, `delete`/`publish`/`set_default` take only the view's own id
- `listing_key` is a column on the row, not a caller-supplied scope, since the id alone
already identifies one row uniquely (a UUID primary key), and the record-action payload
that reaches `delete()` carries only `entity_id`.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.saved_view import SavedView as SavedViewRow
from app.schemas.saved_view import SavedView, SavedViewConfig, SavedViews
from app.services.error_handler import AppException, handle_not_found

PUBLISH_PERMISSION = "list_query.saved_views.publish"


class SavedViewsService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ reads

    def list_for(self, listing_key: str, user_id: str) -> SavedViews:
        rows = (
            self.db.query(SavedViewRow)
            .filter(SavedViewRow.listing_key == listing_key)
            .filter(
                (SavedViewRow.owner_user_id == str(user_id))
                | (SavedViewRow.is_shared.is_(True))
            )
            .order_by(SavedViewRow.name, SavedViewRow.id)
            .all()
        )
        names = self._owner_names([r.owner_user_id for r in rows])
        mine = [self._to_schema(r, names) for r in rows if r.owner_user_id == str(user_id)]
        shared = [self._to_schema(r, names) for r in rows if r.owner_user_id != str(user_id)]
        return SavedViews(mine=mine, shared=shared)

    def default_config(self, listing_key: str) -> Optional[SavedViewConfig]:
        """The shared default view's config for this listing key, if one has been set."""
        row = (
            self.db.query(SavedViewRow)
            .filter(
                SavedViewRow.listing_key == listing_key,
                SavedViewRow.is_default.is_(True),
            )
            .first()
        )
        if row is None:
            return None
        return SavedViewConfig.model_validate(row.view)

    # ----------------------------------------------------------------- writes

    def create(
        self, listing_key: str, user_id: str, name: str, config: SavedViewConfig
    ) -> SavedView:
        cleaned = (name or "").strip()
        if not cleaned:
            raise AppException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                message="A view needs a name",
                code="VALIDATION_ERROR",
            )
        row = SavedViewRow(
            listing_key=listing_key,
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

    def delete(self, view_id: str, user_id: str) -> None:
        row = self._owned(view_id, user_id)
        self.db.delete(row)
        self.db.commit()

    def publish(self, view_id: str, user_id: str, is_shared: bool) -> SavedView:
        row = self._owned(view_id, user_id)
        row.is_shared = bool(is_shared)
        if not row.is_shared:
            # A private view cannot be everyone's default.
            row.is_default = False
        self.db.commit()
        self.db.refresh(row)
        return self._to_schema(row, self._owner_names([row.owner_user_id]))

    def set_default(self, view_id: str, user_id: str) -> SavedView:
        """Make one SHARED view the listing's default for everyone.

        The owner may publish and default in one step. Anyone else has to work with a
        view its author already published - without that rule a holder of the publish
        grant could expose somebody else's PRIVATE view by knowing its id.
        """
        row = self._row(view_id)
        if row is None:
            raise handle_not_found("View", view_id)
        if not row.is_shared and row.owner_user_id != str(user_id):
            raise AppException(
                status_code=status.HTTP_409_CONFLICT,
                message="That view is not shared. Only a shared view can be the default.",
                code="CONFLICT",
            )
        listing_key = row.listing_key
        # Clear first: the partial unique index would otherwise reject the second
        # default. Under a lock on this listing key's rows, because clear-then-set is
        # two statements and two people pressing Set as default at the same moment both
        # cleared, then both set.
        self.db.query(SavedViewRow.id).filter(
            SavedViewRow.listing_key == listing_key
        ).with_for_update().all()
        self.db.query(SavedViewRow).filter(
            SavedViewRow.listing_key == listing_key,
            SavedViewRow.is_default.is_(True),
            SavedViewRow.id != row.id,
        ).update({"is_default": False}, synchronize_session=False)
        row.is_shared = True  # the listing default is shared by definition
        row.is_default = True
        try:
            self.db.commit()
        except IntegrityError:
            # The index is the arbiter, and the loser of a race is a conflict, not a crash.
            self.db.rollback()
            raise AppException(
                status_code=status.HTTP_409_CONFLICT,
                message="Another default was set at the same moment. Try again.",
                code="CONFLICT",
            )
        self.db.refresh(row)
        return self._to_schema(row, self._owner_names([row.owner_user_id]))

    # ---------------------------------------------------------------- helpers

    def listing_key_of(self, view_id: str) -> Optional[str]:
        """The listing key a view belongs to, for the route's own `_can_view_listing_key`
        check before publish/set-default - looked up before any ownership question."""
        row = self._row(view_id)
        return row.listing_key if row is not None else None

    def _row(self, view_id: str) -> Optional[SavedViewRow]:
        return self.db.query(SavedViewRow).filter(SavedViewRow.id == str(view_id)).first()

    def _owned(self, view_id: str, user_id: str) -> SavedViewRow:
        row = self._row(view_id)
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
    def _to_schema(row: SavedViewRow, names: dict) -> SavedView:
        return SavedView(
            id=str(row.id),
            name=row.name,
            is_shared=bool(row.is_shared),
            is_default=bool(row.is_default),
            owner_name=names.get(str(row.owner_user_id)),
            view=SavedViewConfig.model_validate(row.view),
        )
