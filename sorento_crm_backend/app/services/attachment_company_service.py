"""`Set company…` on attachments and folders - the twin linker (PLAN-shared-brand-
attachments.md S2, S3, S6; UAC groups B, C, H).

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
5. Certificate follow (S6, R5): every collected file that is a certificate's
   CURRENT filed revision moves that certificate's `company_id`, rewrites its
   coverage with the same expand/shrink rule, and re-projects
   `product_attachments` (`_apply_certificate_follow`). One JOIN finds every
   touched certificate, same reasoning as the twin linker (R26 / AC-B13).

Folder/file lookups that must see ACROSS companies (the descendant walk, the
ancestor pull, the twin linker's target-company products, the certificate
follow hook) run with the session scope set to `None` (all companies) via
`company_scope(db, None)`, restoring the caller's scope on exit - ORM only,
never `text()`, so the audit/scope machinery still sees every statement (R6
note in the plan).
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.models.company import Company
from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment, AttachmentDirectory
from app.services.attachment_field_link_service import AttachmentFieldLinkService
from app.services.error_handler import (
    AppException,
    handle_conflict,
    handle_not_found,
    handle_validation_error,
)

logger = logging.getLogger(__name__)


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
                files, company_id, actor_id
            )
            certificates_updated = self._apply_certificate_follow(
                list(files.keys()), company_id, actor_id
            )

            self.db.commit()

        return {
            "updated_directories": len(folders),
            "updated_attachments": len(files),
            "company_id": company_id,
            "links_added": links_added,
            "links_removed": links_removed,
            "certificates_updated": certificates_updated,
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
        call is a 404 (AC-B5) - checked before the scope is ever widened. A
        trashed row is a 404 too: it is on its way out, not a target for a
        company decision."""
        if not ids:
            return []
        rows = (
            self.db.query(model)
            .filter(model.id.in_(ids), model.is_deleted == False)  # noqa: E712
            .all()
        )
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
        self, files: dict[str, Attachment], company_id: Optional[str], actor_id: Optional[str]
    ) -> tuple[int, int]:
        file_ids = list(files.keys())
        if not file_ids:
            return 0, 0

        if company_id is None:
            targets = [
                r[0]
                for r in self.db.query(Company.id).filter(Company.is_active == True).all()  # noqa: E712
            ]
        else:
            targets = [company_id]
        if not targets:
            return 0, 0

        added = self._insert_twin_links(files, targets, actor_id)
        removed = self._delete_out_of_scope_links(file_ids, targets)
        return added, removed

    def _insert_twin_links(
        self, files: dict[str, Attachment], targets: list[str], actor_id: Optional[str]
    ) -> int:
        from sqlalchemy.orm import aliased

        file_ids = list(files.keys())
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
                ProductAttachment.created_by.label("created_by"),
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
                    "created_by",
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
            attachment = files.get(str(row.attachment_id))
            # No template to fan out - skip the call outright rather than
            # asking the service to no-op it, so a batch with no field-linked
            # files pays no per-row statement at all (AC-B13).
            if attachment is None or not attachment.target_field_keys:
                continue
            try:
                # A SAVEPOINT per row: one bad template must not abort the
                # whole twin-link transaction, the way the n8n path's own
                # per-row `db.commit()` (external/product_attachments.py)
                # keeps a template mismatch from losing every other link.
                with self.db.begin_nested():
                    field_link_service.apply_template_to_row(
                        attachment,
                        "product",
                        str(row.product_id),
                        created_by=actor_id,
                    )
            except Exception:
                logger.warning(
                    "Field-link fan-out failed for the twin link (attachment=%s, product=%s)",
                    row.attachment_id,
                    row.product_id,
                    exc_info=True,
                )
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

    # ------------------------------------------------------------------
    # 5. Certificate follow (S6, R5) - a filed certificate's revision
    # attachment carries the company decision with it.
    # ------------------------------------------------------------------
    def _apply_certificate_follow(
        self, file_ids: list[str], company_id: Optional[str], actor_id: Optional[str]
    ) -> int:
        """Every collected file that is the CURRENT filed revision of a
        certificate takes that certificate with it: ``certificate.company_id``
        moves to the same target, coverage is rewritten with the SAME
        expand/shrink/move rule the twin linker uses (over product codes), and
        ``reconcile_certificate`` re-projects ``product_attachments`` so it
        never drifts from coverage. A superseded revision's certificate is
        left alone - only the live document decides.

        Runs inside the caller's ``company_scope(db, None)`` (set by
        ``apply()``), so every company's rows are visible while this executes.

        ONE query finds every touched certificate - a per-file
        ``find_by_revision_attachment`` loop would be an N+1 exactly like the
        twin linker was built to avoid (R26 / AC-B13); the same
        current-revision rule that method uses (``current_revision_id`` when
        set, else the ``is_current`` flag) is expressed directly in the JOIN.
        The ``current_revision_id IS NULL`` branch is the SAME dangling-
        pointer fallback ``get_current_revision`` falls back to: the FK is
        ``ondelete="SET NULL"``, so a certificate whose pointed-to revision
        row was deleted out from under it reads ``current_revision_id`` as
        NULL even though a revision with ``is_current = true`` still exists.
        """
        if not file_ids:
            return 0
        from sqlalchemy import and_, or_

        from app.models.certificate import Certificate, CertificateRevision
        from app.services.certificate_service import CertificateService

        cert_service = CertificateService(self.db)
        targets = (
            [r[0] for r in self.db.query(Company.id).all()]
            if company_id is None
            else [company_id]
        )

        rows = (
            self.db.query(Certificate)
            .join(CertificateRevision, CertificateRevision.certificate_id == Certificate.id)
            .filter(
                CertificateRevision.attachment_id.in_(file_ids),
                or_(
                    Certificate.current_revision_id == CertificateRevision.id,
                    and_(
                        Certificate.current_revision_id.is_(None),
                        CertificateRevision.is_current.is_(True),
                    ),
                ),
            )
            .all()
        )
        touched = {str(c.id): c for c in rows}
        self._assert_no_identity_collision(touched.values(), company_id)

        for certificate in touched.values():
            certificate.company_id = company_id
            self._rewrite_certificate_coverage(cert_service, certificate, targets, actor_id)

        return len(touched)

    def _assert_no_identity_collision(self, certificates, company_id) -> None:
        """Two DIFFERENT certificates landing on the same target `company_id`
        must not collide on identity (`uq_certificates_company_scheme_number`)
        - a raw `IntegrityError` surfacing at commit is a 500 with no
        explanation; this catches it early and names which identity clashed.

        Two shapes, both checked:
        1. Both certificates are touched by THIS action (loop below).
        2. One is touched here; the OTHER already sits at the target company
           from an EARLIER action - e.g. Sorento's copy of identity X was
           shared yesterday (company_id NULL), and today's action shares
           Mocha's copy of the SAME identity X. `touched` alone never sees
           yesterday's row, so this needs its own probe against `certificates`
           for the same identities, excluding whatever THIS action already
           touched.
        """
        from app.models.certificate import Certificate
        from app.services.certificate_service import CertificateService, normalize_identity

        certificates = list(certificates)
        touched_ids = {str(c.id) for c in certificates}
        seen: dict[str, object] = {}
        for certificate in certificates:
            key = normalize_identity(certificate.scheme, certificate.certificate_number)
            if not key:
                continue
            other = seen.get(key)
            if other is not None and str(other.id) != str(certificate.id):
                label = f"{certificate.scheme} {certificate.certificate_number}".strip()
                raise handle_conflict(
                    f"{label} names the same certificate identity as another "
                    "certificate in this action - they cannot both move to the "
                    "same company."
                )
            seen[key] = certificate

        if not seen:
            return

        identity_expr = CertificateService._identity_expression()
        company_filter = (
            Certificate.company_id.is_(None)
            if company_id is None
            else Certificate.company_id == company_id
        )
        existing = (
            self.db.query(Certificate.id, Certificate.scheme, Certificate.certificate_number)
            .filter(company_filter)
            .filter(identity_expr.in_(list(seen.keys())))
            .filter(Certificate.id.notin_(touched_ids))
            .all()
        )
        if existing:
            row = existing[0]
            label = f"{row.scheme} {row.certificate_number}".strip()
            raise handle_conflict(
                f"{label} already exists at the target company - an earlier "
                "action already moved a different certificate onto the same "
                "identity."
            )

    def _rewrite_certificate_coverage(
        self, cert_service, certificate, targets: list[str], actor_id: Optional[str]
    ) -> None:
        """Coverage follows the same expand/shrink/move rule as the twin
        linker, over product CODES rather than a caller-supplied set: every
        currently-covered product's code is looked up, then coverage is
        replaced with every product (in ``targets``) sharing one of those
        codes. Sharing (``targets`` = every company) adds the twin; moving to
        one company (``targets`` = ``[company_id]``) drops the others.

        Written directly against ``certificate_products`` rather than through
        ``CertificateService.set_coverage`` (which takes ONE ``source`` for
        the whole call): a twin row copies ``source`` AND ``created_by`` from
        the EXISTING row for the same product code, never defaulting to
        manual - an AI-extracted certificate's twin coverage must not read as
        human-confirmed just because it arrived via a company share.
        """
        import uuid

        from app.models.certificate import CERTIFICATE_SOURCE_MANUAL, CertificateProduct

        existing_rows = (
            self.db.query(CertificateProduct)
            .filter(CertificateProduct.certificate_id == certificate.id)
            # Deterministic per-code representative below (setdefault keeps
            # the FIRST row seen) needs a stable row order - oldest first,
            # ties broken by id, never physical/scan order.
            .order_by(CertificateProduct.created_at, CertificateProduct.id)
            .all()
        )
        if not existing_rows:
            return

        existing_by_product = {str(r.product_id): r for r in existing_rows}
        products = {
            str(p.id): p
            for p in self.db.query(Product)
            .filter(Product.id.in_(existing_by_product.keys()))
            .all()
        }
        # One representative existing row per product code - the source every
        # twin row for that code inherits from. Deterministic: the oldest row
        # (lowest created_at, then id) for that code, per the ORDER BY above.
        representative_by_code: dict[str, CertificateProduct] = {}
        codes: set[str] = set()
        for pid, row in existing_by_product.items():
            product = products.get(pid)
            code = product.product_code if product is not None else None
            if not code:
                continue
            codes.add(code)
            representative_by_code.setdefault(code, row)

        target_products = (
            self.db.query(Product)
            .filter(Product.product_code.in_(codes), Product.company_id.in_(targets))
            .all()
            if codes
            else []
        )
        wanted_ids = {str(p.id) for p in target_products}

        for pid, row in existing_by_product.items():
            if pid not in wanted_ids:
                self.db.delete(row)

        for product in target_products:
            pid = str(product.id)
            if pid in existing_by_product:
                continue
            representative = representative_by_code.get(product.product_code)
            self.db.add(
                CertificateProduct(
                    id=str(uuid.uuid4()),
                    certificate_id=certificate.id,
                    product_id=pid,
                    source=(
                        representative.source
                        if representative is not None
                        else CERTIFICATE_SOURCE_MANUAL
                    ),
                    created_by=(
                        representative.created_by
                        if representative is not None
                        else actor_id
                    ),
                )
            )

        self.db.flush()
        cert_service.reconcile_certificate(certificate)
        cert_service.refresh_review_state(certificate)


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
