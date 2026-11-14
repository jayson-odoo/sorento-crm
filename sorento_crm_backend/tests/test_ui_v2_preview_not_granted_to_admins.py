"""UI-V2 phase 0: `ui.v2.preview` is for the owner alone (UAC journey step 1).

The bootstrap seed `grant_all_permissions_to_admin_roles` gives admin and superadmin every
registered permission; this slug is the one exception, or every admin would see the switch.

Run:
    SORENTO_ENV_FILE=.env.ci-tests venv/bin/python -m pytest tests/test_ui_v2_preview_not_granted_to_admins.py -q
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text

from app.rbac.permission_registry import sync_permissions
from app.services import reference_seed
from tests._pg_fixture import blank_session

SLUG = "ui.v2.preview"


def test_admin_seed_grants_everything_but_the_v2_preview():
    with blank_session() as db:
        sync_permissions(db)
        reference_seed.seed_roles(db)
        # The migration inserts the slug; the registry sync does not know it.
        if db.execute(text("SELECT 1 FROM user_permissions WHERE slug = :s"), {"s": SLUG}).first() is None:
            db.execute(
                text(
                    "INSERT INTO user_permissions (id, slug, name, description, created_at) "
                    "VALUES (:i, :s, 'Preview UI v2', 'x', :n)"
                ),
                {"i": str(uuid.uuid4()), "s": SLUG, "n": datetime.utcnow()},
            )
        reference_seed.grant_all_permissions_to_admin_roles(db)
        db.flush()

        grants = db.execute(
            text(
                "SELECT count(*) FROM user_role_permissions rp "
                "JOIN user_permissions p ON p.id = rp.permission_id WHERE p.slug = :s"
            ),
            {"s": SLUG},
        ).scalar()
        others = db.execute(
            text(
                "SELECT count(*) FROM user_role_permissions rp "
                "JOIN user_permissions p ON p.id = rp.permission_id WHERE p.slug <> :s"
            ),
            {"s": SLUG},
        ).scalar()
    assert grants == 0
    assert others > 0  # the seed still grants everything else
