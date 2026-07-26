"""Grant every external-ingest permission slug to the integration roles.

The `/external` guard (`require_external_permission`) checks EXPLICIT grants with
no admin bypass, so a new ingest endpoint's permission slug must be granted to
the integration roles (FoundryX ESB, n8n) or every ingest from them 403s. The
integration roles are Admin-equivalent by design (see integration_seed.py), so
mirroring the ingest slugs onto them is parity, not a privilege escalation.

This runs at startup AFTER `sync_permissions` (which creates the permission
rows). It is the automated replacement for the manual SQL grants done during
development: idempotent, so re-running only fills gaps. The set of slugs is
derived from the SAME sources the guards read -- EXTERNAL_ENDPOINT_PERMISSIONS
(document/parent+lines routers) plus the flat-master INGEST/READ maps -- so a
future ingest endpoint is granted automatically the moment it is mounted, with
no second place to update.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Integration principals that hit the /external/* ingest surface.
_INTEGRATION_ROLE_SLUGS = ("integration_foundryx_esb", "integration_n8n")


def _ingest_slugs() -> set[str]:
    """Every permission slug an /external ingest or read endpoint is gated on."""
    from app.api.v1.external.permissions import EXTERNAL_ENDPOINT_PERMISSIONS
    from app.api.v1.external.ingest import INGEST_PERMISSIONS, READ_PERMISSIONS

    slugs: set[str] = set(EXTERNAL_ENDPOINT_PERMISSIONS.values())
    slugs.update(INGEST_PERMISSIONS.values())
    slugs.update(READ_PERMISSIONS.values())
    return slugs


def grant_ingest_permissions(db: Session) -> int:
    """Grant all ingest slugs to the integration roles. Returns rows added."""
    slugs = _ingest_slugs()
    if not slugs:
        return 0

    # Resolve slug -> permission id and role slug -> role id up front.
    perm_ids = {
        row[0]: row[1]
        for row in db.execute(
            text("SELECT slug, id FROM user_permissions WHERE slug = ANY(:slugs)"),
            {"slugs": list(slugs)},
        ).fetchall()
    }
    missing = slugs - set(perm_ids)
    if missing:
        # Not fatal: sync_permissions runs first, so a miss means a slug mapped
        # by a guard was never registered in PERMISSION_REGISTRY -- log it loudly.
        logger.warning("integration ingest grants: unregistered slugs skipped: %s", sorted(missing))

    role_ids = {
        row[0]: row[1]
        for row in db.execute(
            text("SELECT slug, id FROM user_roles WHERE slug = ANY(:slugs)"),
            {"slugs": list(_INTEGRATION_ROLE_SLUGS)},
        ).fetchall()
    }

    added = 0
    for role_slug, role_id in role_ids.items():
        existing = {
            row[0]
            for row in db.execute(
                text("SELECT permission_id FROM user_role_permissions WHERE role_id = :r"),
                {"r": role_id},
            ).fetchall()
        }
        for slug, pid in perm_ids.items():
            if pid in existing:
                continue
            db.execute(
                text(
                    "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
                    "VALUES (:id, :r, :p, now())"
                ),
                {"id": str(uuid.uuid4()), "r": role_id, "p": pid},
            )
            added += 1
    if added:
        db.commit()
    return added
