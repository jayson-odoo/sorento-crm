"""Seed integration records, their principals and their roles.

Called by the Group A seed migration. Lives here rather than inside the
migration so it can be tested directly and re-run safely -- it executes against
a live database, and a migration that half-applied then re-ran must not leave
duplicate principals or a second legacy key behind. Every step is guarded.

**The cutover this implements.** ``EXTERNAL_API_KEY`` is currently shared by n8n
and the MCP server. Seeding a ``legacy-shared-key`` integration that carries the
*hash of that same value*, acting as the *same* principal, means both callers
keep working with zero changes -- while nothing reads the env var at runtime.
That is what dissolves the AC-AC-01 / AC-AC-09 conflict instead of trading one
against the other.

Afterwards: issue per-caller keys, migrate n8n and the MCP server onto them, and
revoke the legacy row once its ``last_used_at`` goes quiet.

**Privilege level, stated plainly.** The seeded roles copy Admin's permission
set, matching what the shared key grants today, so nothing regresses at cutover.
That is parity, not least privilege: n8n and the MCP server remain
Admin-equivalent. Narrowing them is tracked follow-up work and is deliberately
not delivered here.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.integration import Integration, IntegrationApiKey
from app.models.user import (
    User,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from app.services.integration_key_crypto import hash_api_key, key_prefix

logger = logging.getLogger(__name__)

LEGACY_INTEGRATION_NAME = "legacy-shared-key"

# name -> (type, human label). One integration per real caller, so revoking one
# cannot affect another -- the defect the single shared key has today.
SEEDED_INTEGRATIONS = {
    "n8n": ("automation", "n8n"),
    "sorento-mcp": ("mcp", "Sorento MCP"),
    "foundryx-esb": ("autocount_esb", "FoundryX ESB"),
}

_ADMIN_ROLE_SLUG = "admin"


def _admin_permission_ids(db: Session) -> list[str]:
    admin = db.query(UserRole).filter(UserRole.slug == _ADMIN_ROLE_SLUG).first()
    if admin is None:
        logger.warning("integration_seed: no admin role found; roles will be created empty")
        return []
    return [p.permission_id for p in db.query(UserRolePermission).filter_by(role_id=admin.id).all()]


def _ensure_principal(db: Session, name: str, label: str) -> User:
    email = f"{name}@integrations.local"
    user = db.query(User).filter(User.email == email).first()
    if user is not None:
        return user

    user = User(
        email=email,
        name=f"Integration: {label}",
        # No password: interactive login rejects a null-password user outright,
        # which is what actually enforces "machine principals cannot log in".
        password=None,
        status="ACTIVE",
        is_integration=True,
        # Deliberately NOT is_protected -- that flag selects notification
        # recipients, and these principals must not receive automation email.
        is_protected=False,
    )
    db.add(user)
    db.flush()
    return user


def _ensure_role(db: Session, name: str, label: str, permission_ids: list[str]) -> UserRole:
    slug = f"integration_{name.replace('-', '_')}"
    role = db.query(UserRole).filter(UserRole.slug == slug).first()
    if role is None:
        role = UserRole(
            slug=slug,
            name=f"Integration: {label}",
            description=(
                f"Machine role for the {label} integration. Seeded at parity with Admin "
                "so the cutover from the shared EXTERNAL_API_KEY regresses nothing; "
                "narrow it once the caller's real endpoint usage is confirmed."
            ),
        )
        db.add(role)
        db.flush()

    existing = {p.permission_id for p in db.query(UserRolePermission).filter_by(role_id=role.id).all()}
    for permission_id in permission_ids:
        if permission_id not in existing:
            db.add(UserRolePermission(role_id=role.id, permission_id=permission_id))
    db.flush()
    return role


def _ensure_assignment(db: Session, user: User, role: UserRole) -> None:
    exists = (
        db.query(UserRoleAssignment).filter_by(user_id=user.id, role_id=role.id).first() is not None
    )
    if not exists:
        db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
        db.flush()


def _ensure_integration(
    db: Session, name: str, type_: str, act_as_user_id: Optional[str]
) -> Integration:
    row = db.query(Integration).filter(Integration.name == name).first()
    if row is None:
        row = Integration(
            name=name,
            type=type_,
            act_as_user_id=act_as_user_id,
            # UNVERIFIED until a real call succeeds. Nothing has been proven yet.
            status="UNVERIFIED",
            is_active=True,
        )
        db.add(row)
        db.flush()
    elif row.act_as_user_id is None and act_as_user_id:
        row.act_as_user_id = act_as_user_id
        db.flush()
    return row


def seed_integrations(
    db: Session,
    external_api_key: Optional[str],
    legacy_act_as_user_id: Optional[str],
) -> None:
    """Create integration principals, roles, integration rows and the legacy key.

    Safe to run repeatedly. ``external_api_key`` absent or blank seeds no legacy
    key at all -- never an empty hash, which would be an authentication bypass
    rather than a missing feature.
    """
    permission_ids = _admin_permission_ids(db)

    for name, (type_, label) in SEEDED_INTEGRATIONS.items():
        user = _ensure_principal(db, name, label)
        role = _ensure_role(db, name, label, permission_ids)
        _ensure_assignment(db, user, role)
        # No key is issued here: the plaintext is shown exactly once and a
        # migration has nobody to show it to. An admin issues it deliberately.
        _ensure_integration(db, name, type_, user.id)

    _seed_legacy_key(db, external_api_key, legacy_act_as_user_id)
    logger.info("integration_seed: complete")


def _seed_legacy_key(
    db: Session, external_api_key: Optional[str], legacy_act_as_user_id: Optional[str]
) -> None:
    if not external_api_key or not external_api_key.strip():
        # Loud, because the operator needs to know current callers were not
        # carried over -- but not fatal, since a fresh install has no legacy key.
        logger.warning(
            "integration_seed: EXTERNAL_API_KEY absent; no legacy key seeded. "
            "Existing callers using the shared key will stop authenticating once "
            "the env fallback is removed."
        )
        return

    key = external_api_key.strip()
    legacy = _ensure_integration(db, LEGACY_INTEGRATION_NAME, "legacy", legacy_act_as_user_id)

    key_hash = hash_api_key(key)
    already = db.query(IntegrationApiKey).filter_by(key_hash=key_hash).first()
    if already is not None:
        return

    db.add(
        IntegrationApiKey(
            integration_id=legacy.id,
            key_hash=key_hash,
            key_prefix=key_prefix(key),
        )
    )
    db.flush()
    logger.info(
        "integration_seed: legacy shared key carried over as integration '%s'",
        LEGACY_INTEGRATION_NAME,
    )
