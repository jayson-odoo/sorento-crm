"""DB-driven ideation connection config on respond_workspaces.

Covers the migration off ``.env``/app.config and onto the workspace row, mirroring
the respond.io encrypted-key pattern:

- the two new columns exist and are nullable;
- the workspace service encrypts the intake key on create/update (round-trips via
  the field-encryption helper), masks it in the response, and never leaks plaintext;
- ``_resolve_ideation_config`` reads base URL / intake key / product binding from
  the DEFAULT workspace (DB is the source of truth), falls back to app.config
  per-field ONLY when the workspace field is blank, and reports fail-closed when
  a piece is missing.

All deterministic / offline (rolled-back Postgres + static file inspection); no
live data or LLM.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import app.services.ideation_turn_service as turn_svc
from app.models.respond_workspace import RespondWorkspace
from app.schemas.respond_workspace import (
    RespondWorkspaceCreate,
    RespondWorkspaceUpdate,
)
from app.services.respond_workspace_service import RespondWorkspaceService
from app.utils.field_encryption import decrypt_secret
from tests._pg_fixture import blank_session


_MIGRATIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


@pytest.fixture
def session():
    """A blank Postgres schema, rolled back after the test.

    Was in-memory sqlite. Matters here because respond_workspaces carries a
    PARTIAL unique index (``WHERE is_default IS TRUE``) that sqlite renders as
    a plain unique index -- so the default-workspace behaviour these tests lean
    on was being checked against the wrong constraint.
    """
    with blank_session() as s:
        yield s


# ===========================================================================
# Model — two new nullable columns
# ===========================================================================
def test_workspace_model_has_ideation_config_columns():
    cols = RespondWorkspace.__table__.columns
    for name in ("ideation_shared_service_url", "ideation_intake_api_key_ciphertext"):
        col = cols.get(name)
        assert col is not None, f"respond_workspaces must carry {name}"
        assert col.nullable is True, f"{name} must be nullable"


# ===========================================================================
# Migration — idempotent + chains onto the committed feature head (273)
# ===========================================================================
def _config_migration() -> Path:
    matches = list(_MIGRATIONS.glob("*ideation_workspace_config*.py"))
    assert matches, "a migration adding the ideation config columns must exist"
    assert len(matches) == 1, f"exactly one config migration expected, got {matches}"
    return matches[0]


def test_config_migration_chains_and_is_idempotent():
    text = _config_migration().read_text()
    assert 'down_revision = "273_ideation_product_binding"' in text, (
        "config migration must chain onto 273 (the product-binding head)"
    )
    for col in ("ideation_shared_service_url", "ideation_intake_api_key_ciphertext"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in text, f"upgrade must ADD {col} idempotently"
        assert f"DROP COLUMN IF EXISTS {col}" in text, f"downgrade must DROP {col} idempotently"


def test_alembic_has_single_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, f"expected a single alembic head, found {heads}"


# ===========================================================================
# Service — encrypt round-trip + masked output + decrypt helper
# ===========================================================================
def test_create_encrypts_and_masks_ideation_key(session):
    svc = RespondWorkspaceService(session)
    row = svc.create(
        RespondWorkspaceCreate(
            space_id="space-1",
            name="Default",
            api_key="respond-secret-key",
            is_default=True,
            ideation_shared_service_url="https://shared.example.com",
            ideation_product_id="prod-uuid-1",
            ideation_intake_api_key="intake-secret-123456",
        )
    )
    # stored ciphertext is NOT the plaintext but round-trips to it
    assert row.ideation_intake_api_key_ciphertext
    assert row.ideation_intake_api_key_ciphertext != "intake-secret-123456"
    assert decrypt_secret(row.ideation_intake_api_key_ciphertext) == "intake-secret-123456"

    out = svc.to_response_dict(row)
    assert out["ideation_shared_service_url"] == "https://shared.example.com"
    assert out["ideation_product_id"] == "prod-uuid-1"
    # masked, never plaintext
    assert out["ideation_intake_api_key_masked"] == "****3456"
    assert "intake-secret" not in (out["ideation_intake_api_key_masked"] or "")


def test_create_without_ideation_key_leaves_masked_none(session):
    svc = RespondWorkspaceService(session)
    row = svc.create(
        RespondWorkspaceCreate(space_id="space-2", api_key="k", is_default=True)
    )
    assert row.ideation_intake_api_key_ciphertext is None
    out = svc.to_response_dict(row)
    assert out["ideation_intake_api_key_masked"] is None


def test_update_replaces_key_only_when_provided(session):
    svc = RespondWorkspaceService(session)
    row = svc.create(
        RespondWorkspaceCreate(
            space_id="space-3",
            api_key="k",
            is_default=True,
            ideation_intake_api_key="first-key-000000",
        )
    )
    first_cipher = row.ideation_intake_api_key_ciphertext

    # url update, key omitted → key unchanged
    row = svc.update(
        row.id,
        RespondWorkspaceUpdate(ideation_shared_service_url="https://new.example.com"),
    )
    assert row.ideation_shared_service_url == "https://new.example.com"
    assert row.ideation_intake_api_key_ciphertext == first_cipher

    # key provided → replaced
    row = svc.update(row.id, RespondWorkspaceUpdate(ideation_intake_api_key="second-key-111111"))
    assert decrypt_secret(row.ideation_intake_api_key_ciphertext) == "second-key-111111"


def test_decrypt_ideation_api_key_helper(session):
    svc = RespondWorkspaceService(session)
    row = svc.create(
        RespondWorkspaceCreate(
            space_id="space-4",
            api_key="k",
            is_default=True,
            ideation_intake_api_key="helper-key-222222",
        )
    )
    assert RespondWorkspaceService.decrypt_ideation_api_key(row) == "helper-key-222222"

    bare = svc.create(RespondWorkspaceCreate(space_id="space-5", api_key="k"))
    assert RespondWorkspaceService.decrypt_ideation_api_key(bare) is None


# ===========================================================================
# Config resolution — DB over .env, per-field fallback, fail-closed
# ===========================================================================
def test_resolve_config_prefers_db_over_settings(session, monkeypatch):
    svc = RespondWorkspaceService(session)
    svc.create(
        RespondWorkspaceCreate(
            space_id="space-1",
            api_key="k",
            is_default=True,
            ideation_shared_service_url="https://db.example.com",
            ideation_product_id="db-prod",
            ideation_intake_api_key="db-key-333333",
        )
    )
    # settings hold different (legacy .env) values — DB must win
    monkeypatch.setattr(turn_svc.settings, "ideation_shared_service_url", "https://env.example.com")
    monkeypatch.setattr(turn_svc.settings, "ideation_intake_api_key", "env-key")

    cfg = turn_svc._resolve_ideation_config(session)
    assert cfg.base_url == "https://db.example.com"
    assert cfg.api_key == "db-key-333333"
    assert cfg.product_id == "db-prod"
    assert cfg.is_ready is True


def test_resolve_config_falls_back_to_settings_per_field(session, monkeypatch):
    svc = RespondWorkspaceService(session)
    # workspace has ONLY the product binding; url + key blank
    svc.create(
        RespondWorkspaceCreate(
            space_id="space-1",
            api_key="k",
            is_default=True,
            ideation_product_id="db-prod",
        )
    )
    monkeypatch.setattr(turn_svc.settings, "ideation_shared_service_url", "https://env.example.com")
    monkeypatch.setattr(turn_svc.settings, "ideation_intake_api_key", "env-key")

    cfg = turn_svc._resolve_ideation_config(session)
    assert cfg.base_url == "https://env.example.com"  # from .env fallback
    assert cfg.api_key == "env-key"                    # from .env fallback
    assert cfg.product_id == "db-prod"                 # from DB
    assert cfg.is_ready is True


def test_resolve_config_fail_closed_when_all_blank(session, monkeypatch):
    svc = RespondWorkspaceService(session)
    svc.create(RespondWorkspaceCreate(space_id="space-1", api_key="k", is_default=True))
    monkeypatch.setattr(turn_svc.settings, "ideation_shared_service_url", None)
    monkeypatch.setattr(turn_svc.settings, "ideation_intake_api_key", None)

    cfg = turn_svc._resolve_ideation_config(session)
    assert cfg.is_ready is False


def test_resolve_config_no_default_workspace_uses_settings(session, monkeypatch):
    # no rows at all → falls back entirely to settings (product_id stays None)
    monkeypatch.setattr(turn_svc.settings, "ideation_shared_service_url", "https://env.example.com")
    monkeypatch.setattr(turn_svc.settings, "ideation_intake_api_key", "env-key")

    cfg = turn_svc._resolve_ideation_config(session)
    assert cfg.base_url == "https://env.example.com"
    assert cfg.api_key == "env-key"
    assert cfg.product_id is None
    assert cfg.is_ready is False  # no product binding => fail-closed
