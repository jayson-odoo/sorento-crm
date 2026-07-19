"""DB-driven ideation EMBED (iframe SSO) config on respond_workspaces.

Keys back to ``documentation/plans/ideation/ideation-embed-sso-acceptance-criteria.md``:

- **AC-E-1** — the three embed fields live on the ``RespondWorkspace`` row: connection
  id + FE base URL (plain) and the signing secret (Fernet-encrypted ``..._ciphertext``,
  masked on read, never plaintext).
- **AC-E-2** — ``_resolve_embed_config`` reads DB-first from the DEFAULT workspace
  (decrypting the secret); ``.env`` is a per-field fallback only.
- **AC-E-3** — backend base (``ideation_shared_service_url``) and FE base
  (``ideation_embed_fe_base_url``) resolve to distinct values.
- **AC-E-4** — any blank required field => not ready (dormant).
- **AC-E-12** — the signing secret is never returned plaintext (masked only).

All deterministic / offline (sqlite + static file inspection); no live DB or LLM.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.ideation_embed_service as embed_svc
from app.database import Base
from app.models.respond_workspace import RespondWorkspace
from app.schemas.respond_workspace import (
    RespondWorkspaceCreate,
    RespondWorkspaceUpdate,
)
from app.services.respond_workspace_service import RespondWorkspaceService
from app.utils.field_encryption import decrypt_secret


_MIGRATIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[RespondWorkspace.__table__])
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


# ===========================================================================
# Model — three new nullable columns (AC-E-1)
# ===========================================================================
def test_workspace_model_has_embed_config_columns():
    cols = RespondWorkspace.__table__.columns
    for name in (
        "ideation_embed_connection_id",
        "ideation_embed_signing_secret_ciphertext",
        "ideation_embed_fe_base_url",
    ):
        col = cols.get(name)
        assert col is not None, f"respond_workspaces must carry {name}"
        assert col.nullable is True, f"{name} must be nullable"


# ===========================================================================
# Migration — idempotent + chains onto the committed head (287) + single head
# ===========================================================================
def _embed_migration() -> Path:
    matches = list(_MIGRATIONS.glob("*ideation_embed_config*.py"))
    assert matches, "a migration adding the embed config columns must exist"
    assert len(matches) == 1, f"exactly one embed migration expected, got {matches}"
    return matches[0]


def test_embed_migration_chains_and_is_idempotent():
    text = _embed_migration().read_text()
    assert 'down_revision = "287_form_void"' in text, (
        "embed migration must chain onto 287 (the current single head)"
    )
    for col in (
        "ideation_embed_connection_id",
        "ideation_embed_signing_secret_ciphertext",
        "ideation_embed_fe_base_url",
    ):
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
# Service — encrypt round-trip + masked output + decrypt helper (AC-E-1/E-12)
# ===========================================================================
def test_create_encrypts_and_masks_embed_secret(session):
    svc = RespondWorkspaceService(session)
    row = svc.create(
        RespondWorkspaceCreate(
            space_id="space-1",
            name="Default",
            api_key="respond-secret-key",
            is_default=True,
            ideation_embed_connection_id="conn-abc",
            ideation_embed_fe_base_url="https://fe.example.com",
            ideation_embed_signing_secret="embed-secret-123456",
        )
    )
    # stored ciphertext is NOT the plaintext but round-trips to it
    assert row.ideation_embed_signing_secret_ciphertext
    assert row.ideation_embed_signing_secret_ciphertext != "embed-secret-123456"
    assert decrypt_secret(row.ideation_embed_signing_secret_ciphertext) == "embed-secret-123456"

    out = svc.to_response_dict(row)
    assert out["ideation_embed_connection_id"] == "conn-abc"
    assert out["ideation_embed_fe_base_url"] == "https://fe.example.com"
    # masked, never plaintext (AC-E-12)
    assert out["ideation_embed_signing_secret_masked"] == "****3456"
    assert "embed-secret" not in (out["ideation_embed_signing_secret_masked"] or "")


def test_create_without_embed_secret_leaves_masked_none(session):
    svc = RespondWorkspaceService(session)
    row = svc.create(RespondWorkspaceCreate(space_id="space-2", api_key="k", is_default=True))
    assert row.ideation_embed_signing_secret_ciphertext is None
    out = svc.to_response_dict(row)
    assert out["ideation_embed_signing_secret_masked"] is None
    assert out["ideation_embed_connection_id"] is None
    assert out["ideation_embed_fe_base_url"] is None


def test_update_replaces_embed_secret_only_when_provided(session):
    svc = RespondWorkspaceService(session)
    row = svc.create(
        RespondWorkspaceCreate(
            space_id="space-3",
            api_key="k",
            is_default=True,
            ideation_embed_signing_secret="first-secret-000000",
        )
    )
    first_cipher = row.ideation_embed_signing_secret_ciphertext

    # connection id update, secret omitted → secret unchanged
    row = svc.update(row.id, RespondWorkspaceUpdate(ideation_embed_connection_id="conn-xyz"))
    assert row.ideation_embed_connection_id == "conn-xyz"
    assert row.ideation_embed_signing_secret_ciphertext == first_cipher

    # secret provided → replaced
    row = svc.update(row.id, RespondWorkspaceUpdate(ideation_embed_signing_secret="second-secret-111111"))
    assert decrypt_secret(row.ideation_embed_signing_secret_ciphertext) == "second-secret-111111"


def test_decrypt_embed_secret_helper(session):
    svc = RespondWorkspaceService(session)
    row = svc.create(
        RespondWorkspaceCreate(
            space_id="space-4",
            api_key="k",
            is_default=True,
            ideation_embed_signing_secret="helper-secret-222222",
        )
    )
    assert RespondWorkspaceService.decrypt_ideation_embed_secret(row) == "helper-secret-222222"

    bare = svc.create(RespondWorkspaceCreate(space_id="space-5", api_key="k"))
    assert RespondWorkspaceService.decrypt_ideation_embed_secret(bare) is None


# ===========================================================================
# Config resolution — DB over .env, per-field fallback, dormant (AC-E-2/E-3/E-4)
# ===========================================================================
def test_resolve_embed_config_prefers_db_over_settings(session, monkeypatch):
    svc = RespondWorkspaceService(session)
    svc.create(
        RespondWorkspaceCreate(
            space_id="space-1",
            api_key="k",
            is_default=True,
            ideation_shared_service_url="https://db.example.com/be",
            ideation_embed_fe_base_url="https://db.example.com",
            ideation_embed_connection_id="db-conn",
            ideation_embed_signing_secret="db-secret-333333",
        )
    )
    # settings hold different (legacy .env) values — DB must win
    monkeypatch.setattr(embed_svc.settings, "ideation_shared_service_url", "https://env.example.com/be")
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_fe_base_url", "https://env.example.com")
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_connection_id", "env-conn")
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_signing_secret", "env-secret")

    cfg = embed_svc._resolve_embed_config(session)
    assert cfg.base_url == "https://db.example.com/be"
    assert cfg.fe_base_url == "https://db.example.com"
    assert cfg.connection_id == "db-conn"
    assert cfg.secret == "db-secret-333333"
    assert cfg.is_ready is True
    # AC-E-3: backend base and FE base are distinct
    assert cfg.base_url != cfg.fe_base_url


def test_resolve_embed_config_falls_back_to_settings_per_field(session, monkeypatch):
    svc = RespondWorkspaceService(session)
    # workspace has ONLY the connection id; url + fe_base + secret blank
    svc.create(
        RespondWorkspaceCreate(
            space_id="space-1",
            api_key="k",
            is_default=True,
            ideation_embed_connection_id="db-conn",
        )
    )
    monkeypatch.setattr(embed_svc.settings, "ideation_shared_service_url", "https://env.example.com/be")
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_fe_base_url", "https://env.example.com")
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_connection_id", "env-conn")
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_signing_secret", "env-secret")

    cfg = embed_svc._resolve_embed_config(session)
    assert cfg.base_url == "https://env.example.com/be"   # from .env fallback
    assert cfg.fe_base_url == "https://env.example.com"   # from .env fallback
    assert cfg.connection_id == "db-conn"                 # from DB
    assert cfg.secret == "env-secret"                     # from .env fallback
    assert cfg.is_ready is True


def test_resolve_embed_config_dormant_when_all_blank(session, monkeypatch):
    svc = RespondWorkspaceService(session)
    svc.create(RespondWorkspaceCreate(space_id="space-1", api_key="k", is_default=True))
    monkeypatch.setattr(embed_svc.settings, "ideation_shared_service_url", None)
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_fe_base_url", None)
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_connection_id", None)
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_signing_secret", None)

    cfg = embed_svc._resolve_embed_config(session)
    assert cfg.is_ready is False


def test_resolve_embed_config_dormant_when_fe_base_missing(session, monkeypatch):
    svc = RespondWorkspaceService(session)
    svc.create(
        RespondWorkspaceCreate(
            space_id="space-1",
            api_key="k",
            is_default=True,
            ideation_shared_service_url="https://db.example.com/be",
            ideation_embed_connection_id="db-conn",
            ideation_embed_signing_secret="db-secret-333333",
        )
    )
    monkeypatch.setattr(embed_svc.settings, "ideation_shared_service_url", None)
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_fe_base_url", None)
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_connection_id", None)
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_signing_secret", None)

    cfg = embed_svc._resolve_embed_config(session)
    assert cfg.fe_base_url is None
    assert cfg.is_ready is False  # FE base missing => dormant (AC-E-4)


def test_create_embed_session_uses_db_secret_and_fe_base(session, monkeypatch):
    """AC-E-2/E-3 end-to-end (POST stubbed): the assertion is signed with the DB
    secret and verifiable with it; iframe_url is built from the DB FE base."""
    from jose import jwt

    from app.config import settings as app_settings

    svc = RespondWorkspaceService(session)
    svc.create(
        RespondWorkspaceCreate(
            space_id="space-1",
            api_key="k",
            is_default=True,
            ideation_shared_service_url="https://db.example.com/be",
            ideation_embed_fe_base_url="https://db.example.com",
            ideation_embed_connection_id="db-conn",
            ideation_embed_signing_secret="db-secret-abcdef",
        )
    )
    # blank .env so only the DB path can satisfy config
    monkeypatch.setattr(embed_svc.settings, "ideation_shared_service_url", None)
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_fe_base_url", None)
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_connection_id", None)
    monkeypatch.setattr(embed_svc.settings, "ideation_embed_signing_secret", None)

    captured: dict = {}

    def _fake_post(base_url, payload):  # noqa: ANN001
        captured["base_url"] = base_url
        captured["payload"] = payload
        return {"token": "tok", "expires_at": "2026-07-20T00:00:00+00:00"}

    monkeypatch.setattr(embed_svc, "post_embed_session", _fake_post)

    result = embed_svc.create_embed_session(
        session, {"id": "u1", "email": "a@b.c", "name": "A"}, idea_id=None
    )

    # POST went to the backend base; iframe to the distinct FE base (AC-E-3)
    assert captured["base_url"] == "https://db.example.com/be"
    assert result["iframe_url"] == "https://db.example.com/embed/ideas"
    # the assertion verifies against the DB secret (AC-E-2)
    decoded = jwt.decode(
        captured["payload"]["assertion"],
        "db-secret-abcdef",
        algorithms=[app_settings.jwt_algorithm],
        audience="ideation-embed",
    )
    assert decoded["connection_id"] == "db-conn"
