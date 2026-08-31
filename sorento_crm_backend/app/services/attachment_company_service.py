"""`Set company…` on attachments and folders - the twin linker (PLAN-shared-brand-
attachments.md S2, S3; UAC groups B, C).

One service, two entry points (R4): `POST /resource-management/attachments/
bulk-company` (the popup single-row Edit fallback, tests, n8n-style callers) and
the deferred actions `attachment.set_company` / `attachment_directory.set_company`
(`app/services/record_actions.py`), which the UI actually drives through the
grace-window engine (R22). Both call `AttachmentCompanyService.apply`.

Resolution order inside one call, all in ONE transaction (R6, R21):

1. Expand every selected folder DOWNWARD to its full subtree (folders + files,
   `is_deleted = false`, R18) - the recursion.
2. When sharing (`company_id is None`), pull every ANCESTOR folder of every
   selected folder and of every selected file's folder up to shared too (R19).
   Folders only; a sibling file is untouched (AC-C2). Owning (`company_id` is a
   real company) never does this - it only pushes down (R19).
3. Stamp `company_id` on every collected folder and file.
4. The TWIN LINKER: over the whole collected file set, one `INSERT … SELECT`
   and one `DELETE`, never a per-file loop (R26 / AC-B13) - so a folder with
   thousands of files still commits inside one execute.
5. Certificate follow (S6) is NOT wired here yet - it lands in a later slice;
   `certificates_updated` is always 0 in this slice.

Folder/file lookups that must see ACROSS companies (the descendant walk, the
ancestor pull, the twin linker's target-company products) run with the session
scope set to `None` (all companies) in a `try/finally`, restoring the caller's
scope on exit - ORM only, never `text()`, so the audit/scope machinery still
sees every statement (R6 note in the plan).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.models.company import Company
from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment, AttachmentDirectory
from app.services.attachment_field_link_service import AttachmentFieldLinkService
from app.services.error_handler import AppException, handle_not_found, handle_validation_error


class AttachmentCompanyService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def apply(
        self,
        *,
        attachment_ids: Optional[list[str]] = None,
        directory_ids: Optional[list[str]] = None,
        company_id: Optional[str],
        actor_id: Optional[str] = None,
    ) -> dict:
        attachment_ids = [str(a) for a in (attachment_ids or []) if a]
        directory_ids = [str(d) for d in (directory_ids or []) if d]
        if not attachment_ids and not directory_ids:
            raise handle_validation_error(
                "At least one attachment or directory ID is required."
            )

        self._assert_company_granted(company_id, actor_id)

        # 404 under the CALLER's ambient scope, before anything else runs - a
        # foreign id is a 404 for the WHOLE call, and nothing partially applies.
        selected_attachments = self._require_all(Attachment, attachment_ids, "Attachment")
        selected_directories = self._require_all(
            AttachmentDirectory, directory_ids, "Attachment directory"
        )

        with company_scope(self.db, None):
            folders = self._expand_folders_downward(selected_directories)
            files = {str(a.id): a for a in selected_attachments}
            files.update(self._descendant_files(folders))

            if company_id is None:
                self._pull_ancestors_to_shared(selected_directories, selected_attachments, folders)

            for folder in folders.values():
                folder.company_id = company_id
            for attachment in files.values():
                attachment.company_id = company_id

            links_added, links_removed = self._sync_product_links(
                list(files.keys()), company_id, actor_id
            )

            self.db.commit()

        return {
            "updated_directories": len(folders),
            "updated_attachments": len(files),
            "company_id": company_id,
            "links_added": links_added,
            "links_removed": links_removed,
            # Certificate follow (S6) is wired in a later slice.
            "certificates_updated": 0,
        }

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------
    def _assert_company_granted(
        self, company_id: Optional[str], actor_id: Optional[str]
    ) -> None:
        """`company_id`, when it names a real company, must be one the actor is
        granted - Shared (None) needs no grant (R13, AC-B6)."""
        if company_id is None or not actor_id:
            return
        from app.services.user_service import UserPermissionService

        perm = UserPermissionService(self.db)
        role_slugs = perm.get_user_role_slugs(actor_id)
        if role_slugs & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
            return
        from app.services.company_scope_resolver import _user_grant_ids

        if str(company_id) not in _user_grant_ids(self.db, actor_id):
            raise AppException(
                status_code=403,
                message="You are not granted that company.",
                code="FORBIDDEN",
            )

    def _require_all(self, model, ids: list[str], label: str) -> list:
        """Every id must resolve under the caller's CURRENT scope, or the whole
        call is a 404 (AC-B5) - checked before the scope is ever widened."""
        if not ids:
            return []
        rows = self.db.query(model).filter(model.id.in_(ids)).all()
        found = {str(r.id) for r in rows}
        missing = next((i for i in ids if i not in found), None)
        if missing is not None:
            raise handle_not_found(label, missing)
        return rows

    # ------------------------------------------------------------------
    # 1. Folder recursion (R18)
    # ------------------------------------------------------------------
    def _expand_folders_downward(self, selected_directories: list) -> dict[str, AttachmentDirectory]:
        """Every selected folder plus its full subtree, live rows only (AC-C6)."""
        from app.services.resources_service import AttachmentDirectoryService

        if not selected_directories:
            return {}
        dir_service = AttachmentDirectoryService(self.db)
        all_ids: set[str] = set()
        for folder in selected_directories:
            all_ids.update(
                dir_service.get_descendant_directory_ids_portable(
                    str(folder.id), include_deleted=False
                )
            )
        if not all_ids:
            return {}
        rows = (
            self.db.query(AttachmentDirectory)
            .filter(AttachmentDirectory.id.in_(all_ids))
            .all()
        )
        return {str(r.id): r for r in rows}

    def _descendant_files(self, folders: dict[str, AttachmentDirectory]) -> dict[str, Attachment]:
        """Live files directly inside any collected folder (the subtree's files)."""
        if not folders:
            return {}
        rows = (
            self.db.query(Attachment)
            .filter(
                Attachment.directory_id.in_(list(folders.keys())),
                Attachment.is_deleted == False,  # noqa: E712
            )
            .all()
        )
        return {str(r.id): r for r in rows}

    # ------------------------------------------------------------------
    # 2. Ancestor pull (R19) - folders only, sharing only.
    # ------------------------------------------------------------------
    def _pull_ancestors_to_shared(
        self,
        selected_directories: list,
        selected_attachments: list,
        folders: dict[str, AttachmentDirectory],
    ) -> None:
        for folder in selected_directories:
            _collect_owned_ancestors(self.db, folder.parent_id, folders)
        for attachment in selected_attachments:
            _collect_owned_ancestors(self.db, attachment.directory_id, folders)

    # ------------------------------------------------------------------
    # 4. Twin linker (R26) - set-based, one INSERT + one DELETE for the whole batch.
    # ------------------------------------------------------------------
    def _sync_product_links(
        self, file_ids: list[str], company_id: Optional[str], actor_id: Optional[str]
    ) -> tuple[int, int]:
        if not file_ids:
            return 0, 0

        if company_id is None:
            targets = [r[0] for r in self.db.query(Company.id).all()]
        else:
            targets = [company_id]
        if not targets:
            return 0, 0

        added = self._insert_twin_links(file_ids, targets, actor_id)
        removed = self._delete_out_of_scope_links(file_ids, targets)
        return added, removed

    def _insert_twin_links(
        self, file_ids: list[str], targets: list[str], actor_id: Optional[str]
    ) -> int:
        from sqlalchemy.orm import aliased

        source_product = aliased(Product)
        target_product = aliased(Product)
        existing = aliased(ProductAttachment)

        select_stmt = (
            select(
                func.gen_random_uuid().label("id"),
                target_product.id.label("product_id"),
                ProductAttachment.attachment_id.label("attachment_id"),
                ProductAttachment.is_primary.label("is_primary"),
                ProductAttachment.sort_order.label("sort_order"),
                ProductAttachment.access_levels.label("access_levels"),
                ProductAttachment.linked_via_set_id.label("linked_via_set_id"),
                target_product.company_id.label("company_id"),
                func.now().label("created_at"),
            )
            # DISTINCT ON (target product, attachment): several source rows
            # (one per already-linked company) can name the same twin when 3+
            # companies exist - one link, not one per source row.
            .distinct(target_product.id, ProductAttachment.attachment_id)
            .select_from(ProductAttachment)
            .join(source_product, source_product.id == ProductAttachment.product_id)
            .join(
                target_product,
                (target_product.product_code == source_product.product_code)
                & (target_product.id != source_product.id)
                & (target_product.company_id.in_(targets)),
            )
            .where(ProductAttachment.attachment_id.in_(file_ids))
            .where(
                ~select(existing.id)
                .where(
                    existing.product_id == target_product.id,
                    existing.attachment_id == ProductAttachment.attachment_id,
                )
                .exists()
            )
            .order_by(target_product.id, ProductAttachment.attachment_id, ProductAttachment.created_at)
        )

        insert_stmt = (
            insert(ProductAttachment)
            .from_select(
                [
                    "id",
                    "product_id",
                    "attachment_id",
                    "is_primary",
                    "sort_order",
                    "access_levels",
                    "linked_via_set_id",
                    "company_id",
                    "created_at",
                ],
                select_stmt,
            )
            .returning(
                ProductAttachment.id,
                ProductAttachment.product_id,
                ProductAttachment.attachment_id,
            )
        )
        inserted = self.db.execute(insert_stmt).fetchall()
        if not inserted:
            return 0

        field_link_service = AttachmentFieldLinkService(self.db)
        for row in inserted:
            try:
                field_link_service.apply_template_to_row(
                    str(row.attachment_id),
                    "product",
                    str(row.product_id),
                    created_by=actor_id,
                )
            except Exception:
                # Best-effort, exactly like the n8n path (external/product_attachments.py):
                # a template mismatch must not turn a successful share into a 500.
                pass
        return len(inserted)

    def _delete_out_of_scope_links(self, file_ids: list[str], targets: list[str]) -> int:
        delete_stmt = (
            delete(ProductAttachment)
            .where(
                ProductAttachment.attachment_id.in_(file_ids),
                ProductAttachment.product_id.in_(
                    select(Product.id).where(Product.company_id.not_in(targets))
                ),
            )
            .returning(ProductAttachment.id)
        )
        removed = self.db.execute(delete_stmt).fetchall()
        return len(removed)


# --------------------------------------------------------------------------------------
# Ancestor pull (R19) - shared with the CREATE and MOVE paths (resources_service.py,
# S3), which each have exactly one starting folder rather than a batch, so they use
# these module-level helpers directly instead of going through `apply()`.
# --------------------------------------------------------------------------------------


def _collect_owned_ancestors(
    db: Session,
    start_directory_id: Optional[str],
    into: dict[str, AttachmentDirectory],
) -> dict[str, AttachmentDirectory]:
    """Walk upward from `start_directory_id` (inclusive), adding every OWNED
    ancestor to `into`. Stops at the first already-shared folder without adding
    it - by the R19 invariant, everything above a shared folder is shared
    already, so there is nothing left to change up there. Does not write
    anything; the caller stamps the collected folders."""
    current_id = str(start_directory_id) if start_directory_id else None
    seen: set[str] = set()
    while current_id and current_id not in seen:
        seen.add(current_id)
        folder = into.get(current_id) or (
            db.query(AttachmentDirectory).filter(AttachmentDirectory.id == current_id).first()
        )
        if folder is None or folder.company_id is None:
            return into
        into[current_id] = folder
        current_id = str(folder.parent_id) if folder.parent_id else None
    return into


def share_ancestor_chain(db: Session, start_directory_id: Optional[str]) -> int:
    """Set every OWNED ancestor of `start_directory_id` (inclusive) to shared
    (`company_id = NULL`) immediately, and return how many changed (R19).

    Used by the create/move paths (`resources_service.py`), which each have one
    starting folder to pull rather than a batch to count and commit together.
    Runs unscoped, like the batch version - the chain may cross company
    boundaries the caller's own scope cannot otherwise see.
    """
    if not start_directory_id:
        return 0
    with company_scope(db, None):
        folders = _collect_owned_ancestors(db, start_directory_id, {})
        for folder in folders.values():
            folder.company_id = None
        return len(folders)
