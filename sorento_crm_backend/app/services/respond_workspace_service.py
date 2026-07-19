"""CRUD for Respond workspace configuration."""
from __future__ import annotations

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.respond_workspace import RespondWorkspace
from app.schemas.respond_workspace import RespondWorkspaceCreate, RespondWorkspaceUpdate
from app.utils.field_encryption import decrypt_secret, encrypt_secret


def _mask_key(_cipher: str) -> str:
    try:
        plain = decrypt_secret(_cipher)
    except ValueError:
        return "****"
    if len(plain) <= 8:
        return "****"
    return f"****{plain[-4:]}"


def _mask_optional_key(_cipher: Optional[str]) -> Optional[str]:
    """Like ``_mask_key`` but returns None for an unset (nullable) ciphertext,
    so the FE can tell "no key configured" apart from "key hidden"."""
    if not _cipher:
        return None
    return _mask_key(_cipher)


class RespondWorkspaceService:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> List[RespondWorkspace]:
        return self.db.query(RespondWorkspace).order_by(RespondWorkspace.created_at.asc()).all()

    def list_active_select(self) -> List[RespondWorkspace]:
        return (
            self.db.query(RespondWorkspace)
            .filter(RespondWorkspace.is_active.is_(True))
            .order_by(RespondWorkspace.space_id.asc())
            .all()
        )

    def get(self, workspace_id: str) -> Optional[RespondWorkspace]:
        return self.db.query(RespondWorkspace).filter(RespondWorkspace.id == workspace_id).first()

    def get_default(self) -> Optional[RespondWorkspace]:
        return (
            self.db.query(RespondWorkspace)
            .filter(RespondWorkspace.is_default.is_(True))
            .first()
        )

    def _clear_default_others(self, keep_id: Optional[str]) -> None:
        q = self.db.query(RespondWorkspace).filter(RespondWorkspace.is_default.is_(True))
        if keep_id:
            q = q.filter(RespondWorkspace.id != keep_id)
        for other in q.all():
            other.is_default = False

    def create(self, data: RespondWorkspaceCreate) -> RespondWorkspace:
        exists = (
            self.db.query(RespondWorkspace.id)
            .filter(RespondWorkspace.space_id == data.space_id.strip())
            .first()
        )
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="space_id already exists")
        ideation_key = (data.ideation_intake_api_key or "").strip()
        embed_secret = (data.ideation_embed_signing_secret or "").strip()
        row = RespondWorkspace(
            space_id=data.space_id.strip(),
            name=(data.name or "").strip() or None,
            base_url=(data.base_url or "").strip() or None,
            whatsapp_number=(data.whatsapp_number or "").strip() or None,
            is_active=data.is_active,
            is_default=data.is_default,
            api_key_ciphertext=encrypt_secret(data.api_key.strip()),
            ideation_shared_service_url=(data.ideation_shared_service_url or "").strip() or None,
            ideation_product_id=(data.ideation_product_id or "").strip() or None,
            ideation_intake_api_key_ciphertext=(
                encrypt_secret(ideation_key) if ideation_key else None
            ),
            ideation_embed_connection_id=(
                data.ideation_embed_connection_id or ""
            ).strip() or None,
            ideation_embed_fe_base_url=(
                data.ideation_embed_fe_base_url or ""
            ).strip() or None,
            ideation_embed_signing_secret_ciphertext=(
                encrypt_secret(embed_secret) if embed_secret else None
            ),
        )
        if data.is_default:
            self._clear_default_others(keep_id=None)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update(self, workspace_id: str, data: RespondWorkspaceUpdate) -> RespondWorkspace:
        row = self.get(workspace_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Respond workspace not found")
        if data.space_id is not None:
            sid = data.space_id.strip()
            clash = (
                self.db.query(RespondWorkspace.id)
                .filter(RespondWorkspace.space_id == sid, RespondWorkspace.id != workspace_id)
                .first()
            )
            if clash:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="space_id already exists")
            row.space_id = sid
        if data.name is not None:
            row.name = data.name.strip() or None
        if data.base_url is not None:
            row.base_url = data.base_url.strip() or None
        if data.whatsapp_number is not None:
            row.whatsapp_number = data.whatsapp_number.strip() or None
        if data.is_active is not None:
            row.is_active = data.is_active
        if data.is_default is not None:
            if data.is_default:
                self._clear_default_others(keep_id=workspace_id)
                row.is_default = True
            else:
                row.is_default = False
        if data.api_key is not None and data.api_key.strip():
            row.api_key_ciphertext = encrypt_secret(data.api_key.strip())
        if data.ideation_shared_service_url is not None:
            row.ideation_shared_service_url = data.ideation_shared_service_url.strip() or None
        if data.ideation_product_id is not None:
            row.ideation_product_id = data.ideation_product_id.strip() or None
        if data.ideation_intake_api_key is not None and data.ideation_intake_api_key.strip():
            row.ideation_intake_api_key_ciphertext = encrypt_secret(
                data.ideation_intake_api_key.strip()
            )
        if data.ideation_embed_connection_id is not None:
            row.ideation_embed_connection_id = (
                data.ideation_embed_connection_id.strip() or None
            )
        if data.ideation_embed_fe_base_url is not None:
            row.ideation_embed_fe_base_url = data.ideation_embed_fe_base_url.strip() or None
        if data.ideation_embed_signing_secret is not None and data.ideation_embed_signing_secret.strip():
            row.ideation_embed_signing_secret_ciphertext = encrypt_secret(
                data.ideation_embed_signing_secret.strip()
            )
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, workspace_id: str) -> None:
        row = self.get(workspace_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Respond workspace not found")
        self.db.delete(row)
        self.db.commit()

    def set_default(self, workspace_id: str) -> RespondWorkspace:
        row = self.get(workspace_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Respond workspace not found")
        self._clear_default_others(keep_id=workspace_id)
        row.is_default = True
        self.db.commit()
        self.db.refresh(row)
        return row

    def to_response_dict(self, row: RespondWorkspace) -> dict:
        return {
            "id": str(row.id),
            "space_id": row.space_id,
            "name": row.name,
            "base_url": row.base_url,
            "whatsapp_number": row.whatsapp_number,
            "is_active": row.is_active,
            "is_default": bool(row.is_default),
            "api_key_masked": _mask_key(row.api_key_ciphertext),
            "ideation_shared_service_url": row.ideation_shared_service_url,
            "ideation_product_id": row.ideation_product_id,
            "ideation_intake_api_key_masked": _mask_optional_key(
                row.ideation_intake_api_key_ciphertext
            ),
            "ideation_embed_connection_id": row.ideation_embed_connection_id,
            "ideation_embed_fe_base_url": row.ideation_embed_fe_base_url,
            "ideation_embed_signing_secret_masked": _mask_optional_key(
                row.ideation_embed_signing_secret_ciphertext
            ),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    def decrypt_ideation_api_key(row: RespondWorkspace) -> Optional[str]:
        """Plaintext ideation intake API key for server-side use (create_idea
        Bearer token), or None when unset/undecryptable."""
        cipher = getattr(row, "ideation_intake_api_key_ciphertext", None)
        if not cipher:
            return None
        try:
            return decrypt_secret(cipher) or None
        except ValueError:
            return None

    @staticmethod
    def decrypt_ideation_embed_secret(row: RespondWorkspace) -> Optional[str]:
        """Plaintext ideation embed signing secret for server-side use (minting the
        SSO assertion), or None when unset/undecryptable."""
        cipher = getattr(row, "ideation_embed_signing_secret_ciphertext", None)
        if not cipher:
            return None
        try:
            return decrypt_secret(cipher) or None
        except ValueError:
            return None

    def to_select_dict(self, row: RespondWorkspace) -> dict:
        return {
            "id": str(row.id),
            "space_id": row.space_id,
            "name": row.name,
            "is_default": bool(row.is_default),
        }
