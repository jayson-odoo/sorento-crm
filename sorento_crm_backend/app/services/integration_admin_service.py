"""Management operations for integration records and their keys (AC-AC-08).

Serialisation lives here rather than in the route so there is exactly one place
that decides what leaves the server. These records exist to hold secrets, and a
leak is cheapest to prevent where the shape is defined once -- a careless field
on a list endpoint would publish credentials to every client that can read it.

``serialise`` never emits ``credentials_json`` or ``key_hash``. It reports
``has_credentials`` instead, because an operator needs to know a credential
exists without the API ever transmitting it.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.integration import Integration, IntegrationApiKey
from app.models.user import User
from app.services.error_handler import AppException
from app.services.integration_key_service import DEFAULT_GRACE_DAYS, IntegrationKeyService
from app.utils.field_encryption import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)


class IntegrationAdminService:
    def __init__(self, db: Session):
        self.db = db
        self.keys = IntegrationKeyService(db)

    # ----------------------------------------------------------------- read

    def list(self) -> list[Integration]:
        return self.db.query(Integration).order_by(Integration.name).all()

    def get(self, integration_id: str) -> Integration:
        row = self.db.query(Integration).filter(Integration.id == integration_id).first()
        if row is None:
            raise AppException("Integration not found", status_code=404)
        return row

    def serialise(self, integration: Integration) -> dict[str, Any]:
        """Public shape. Carries no secret material of any kind."""
        principal_name = None
        if integration.act_as_user_id:
            user = (
                self.db.query(User).filter(User.id == integration.act_as_user_id).first()
            )
            principal_name = user.name if user else None

        keys = (
            self.db.query(IntegrationApiKey)
            .filter(IntegrationApiKey.integration_id == integration.id)
            .order_by(IntegrationApiKey.created_at.desc())
            .all()
        )

        now = datetime.utcnow()
        return {
            "id": integration.id,
            "name": integration.name,
            "type": integration.type,
            "status": integration.status,
            "act_as_user_id": integration.act_as_user_id,
            "act_as_user_name": principal_name,
            "config_json": integration.config_json,
            # Whether a credential is set, never what it is.
            "has_credentials": bool(integration.credentials_json),
            "is_active": integration.is_active,
            "last_used_at": integration.last_used_at,
            "last_error": integration.last_error,
            "created_at": integration.created_at,
            "updated_at": integration.updated_at,
            "keys": [
                {
                    "id": k.id,
                    "key_prefix": k.key_prefix,
                    "expires_at": k.expires_at,
                    "revoked_at": k.revoked_at,
                    "rotated_from_id": k.rotated_from_id,
                    "last_used_at": k.last_used_at,
                    "created_at": k.created_at,
                    # Computed here so the UI cannot drift from what the
                    # authentication path actually enforces.
                    "is_active": (
                        k.revoked_at is None
                        and (k.expires_at is None or k.expires_at > now)
                    ),
                }
                for k in keys
            ],
        }

    # ---------------------------------------------------------------- write

    def create(
        self,
        *,
        name: str,
        type_: str,
        act_as_user_id: Optional[str] = None,
        config_json: Optional[dict] = None,
        credentials_json: Optional[dict] = None,
        is_active: bool = True,
    ) -> Integration:
        if self.db.query(Integration).filter(Integration.name == name).first():
            raise AppException(f"An integration named '{name}' already exists", status_code=409)

        row = Integration(
            name=name,
            type=type_,
            act_as_user_id=act_as_user_id,
            config_json=config_json,
            credentials_json=self._encrypt(credentials_json),
            is_active=is_active,
            status="UNVERIFIED",
        )
        self.db.add(row)
        self.db.flush()
        logger.info("integration.created name=%s type=%s", name, type_)
        return row

    def update(
        self,
        integration: Integration,
        *,
        name: Optional[str] = None,
        type_: Optional[str] = None,
        act_as_user_id: Optional[str] = None,
        config_json: Optional[dict] = None,
        credentials_json: Optional[dict] = None,
        is_active: Optional[bool] = None,
    ) -> Integration:
        if name is not None:
            clash = (
                self.db.query(Integration)
                .filter(Integration.name == name, Integration.id != integration.id)
                .first()
            )
            if clash:
                raise AppException(f"An integration named '{name}' already exists", status_code=409)
            integration.name = name
        if type_ is not None:
            integration.type = type_
        if act_as_user_id is not None:
            integration.act_as_user_id = act_as_user_id
        if config_json is not None:
            integration.config_json = config_json
        if is_active is not None:
            integration.is_active = is_active
        # None means "keep existing" (AC-AC-07). Clearing a credential requires
        # an explicit empty dict, so a form posting a blank field cannot silently
        # break authentication in a way that looks like an outage.
        if credentials_json is not None:
            integration.credentials_json = self._encrypt(credentials_json)

        self.db.flush()
        return integration

    def delete(self, integration: Integration) -> None:
        """Hard delete, per the CRUD standard.

        Keys are removed explicitly rather than left to the FK's ON DELETE
        CASCADE. The cascade is real on Postgres, but the ORM session does not
        reflect it and sqlite does not enforce foreign keys unless asked -- so
        relying on it would make "are this integration's keys dead?" depend on
        which database you are running. For credential revocation that answer
        must be the same everywhere.
        """
        self.db.query(IntegrationApiKey).filter(
            IntegrationApiKey.integration_id == integration.id
        ).delete(synchronize_session=False)
        self.db.delete(integration)
        self.db.flush()
        logger.info("integration.deleted name=%s", integration.name)

    # ------------------------------------------------------------- key ops

    def issue_key(self, integration: Integration) -> dict[str, str]:
        plaintext = self.keys.issue_key(integration)
        return self._issued(integration, plaintext)

    def rotate_key(
        self, integration: Integration, grace_days: int = DEFAULT_GRACE_DAYS
    ) -> dict[str, str]:
        plaintext = self.keys.rotate_key(integration, grace_days=grace_days)
        return self._issued(integration, plaintext)

    def revoke_key(self, integration: Integration, key_id: str) -> None:
        key = (
            self.db.query(IntegrationApiKey)
            .filter(
                IntegrationApiKey.id == key_id,
                # Scoped to the integration: otherwise an operator acting on one
                # integration could disable another's credentials.
                IntegrationApiKey.integration_id == integration.id,
            )
            .first()
        )
        if key is None:
            raise AppException("Key not found for this integration", status_code=404)
        self.keys.revoke_key(key)

    # ------------------------------------------------------------ internals

    def _issued(self, integration: Integration, plaintext: str) -> dict[str, str]:
        return {
            "key": plaintext,
            "key_prefix": plaintext[:11],
            "integration_id": integration.id,
            "warning": "Copy this key now. It cannot be retrieved again.",
        }

    def _encrypt(self, credentials: Optional[dict]) -> Optional[str]:
        if credentials is None:
            return None
        return encrypt_secret(json.dumps(credentials))

    def decrypt_credentials(self, integration: Integration) -> Optional[dict]:
        """Read credentials for *server-side* use only. Never for a response.

        Returns None on an undecryptable value rather than raising, so a rotated
        encryption key degrades the integration instead of breaking every list
        request that happens to include it.
        """
        if not integration.credentials_json:
            return None
        try:
            return json.loads(decrypt_secret(integration.credentials_json))
        except Exception:
            logger.warning(
                "integration.credentials_undecryptable name=%s", integration.name
            )
            return None
