"""Slice B - workspace<->product binding + ideation config (ideation pipeline).

Keys back to ``documentation/plans/ideation/ideation-ideate-intent-acceptance-criteria.md``:

- **AC-30 [T]** - ``respond_workspaces`` carries a nullable ``ideation_product_id``
  (shared-service Product UUID, server-side only), added by an idempotent Alembic
  migration chained onto the committed main head - a single linear head, no fork.
- **AC-31 [T]** - a workspace with NO ``ideation_product_id`` is detectable so the
  brain-path endpoint can fail-closed (no ``create_idea`` call).
- **AC-32 [T]** - the four ideation settings (``ideation_shared_service_url``,
  ``ideation_intake_api_key``, ``ideation_embed_signing_secret``,
  ``ideation_embed_connection_id``) exist, default blank (feature dormant), and
  there is NO ``ideation_mcp_url`` (create_idea is HTTP, not MCP).

All deterministic (a rolled-back Postgres session + static file inspection); no
LLM. The database work runs on a blank copy of the real schema, so the column
types and constraints under test are the production ones.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect

from app.models.respond_workspace import RespondWorkspace
from tests._pg_fixture import blank_session


_MIGRATIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


# ===========================================================================
# AC-30 / AC-31 - nullable ideation_product_id on respond_workspaces
# ===========================================================================
def test_workspace_model_has_nullable_ideation_product_id():
    col = RespondWorkspace.__table__.columns.get("ideation_product_id")
    assert col is not None, "respond_workspaces must carry ideation_product_id"
    assert col.nullable is True, "ideation_product_id must be nullable"


def test_workspace_without_binding_is_detectable_fail_closed():
    """AC-31: a workspace with no binding reads back None so the endpoint can
    fail-closed without a create_idea call."""
    with blank_session() as session:
        ws = RespondWorkspace(
            space_id="space-1",
            name="Default",
            api_key_ciphertext="cipher",
            is_default=True,
        )
        session.add(ws)
        session.commit()

        got = inspect(ws)
        assert ws.ideation_product_id is None, "unbound workspace must read None"
        assert got is not None


# ===========================================================================
# AC-30 - migration is chained + idempotent + single head
# ===========================================================================
def _binding_migration() -> Path:
    matches = list(_MIGRATIONS.glob("*ideation_product*.py"))
    assert matches, "a migration adding ideation_product_id must exist"
    assert len(matches) == 1, f"exactly one binding migration expected, got {matches}"
    return matches[0]


def test_binding_migration_chains_on_committed_head():
    """AC-30: the migration chains onto the ideate-parser head (272) so the head
    stays a single linear chain - no dual head after merge."""
    text = _binding_migration().read_text()
    assert 'down_revision = "272_ideate_intent_parser_prompt"' in text, (
        "the binding migration must chain onto 272 (the ideate parser head) to "
        "keep a single linear head"
    )


def test_binding_migration_is_idempotent():
    """AC-30: idempotent add/drop so a re-run is a no-op (IF NOT EXISTS / IF EXISTS)."""
    text = _binding_migration().read_text()
    assert "ideation_product_id" in text
    assert "ADD COLUMN IF NOT EXISTS ideation_product_id" in text, (
        "upgrade must use ADD COLUMN IF NOT EXISTS for idempotency"
    )
    assert "DROP COLUMN IF EXISTS ideation_product_id" in text, (
        "downgrade must use DROP COLUMN IF EXISTS for idempotency"
    )


def test_alembic_has_single_head():
    """AC-30: the migration graph resolves to exactly one head (no fork)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(Path(__file__).resolve().parent.parent / "alembic")
    )
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"expected a single alembic head, found {heads}"


# ===========================================================================
# AC-32 - ideation settings exist, default blank/dormant, no ideation_mcp_url
# ===========================================================================
def test_ideation_settings_default_blank_and_dormant():
    from app.config import Settings

    fields = Settings.model_fields
    for name in (
        "ideation_shared_service_url",
        "ideation_intake_api_key",
        "ideation_embed_signing_secret",
        "ideation_embed_connection_id",
    ):
        assert name in fields, f"{name} must be a config setting"
        assert fields[name].default in (None, ""), (
            f"{name} must default to blank (feature dormant when unset)"
        )


def test_no_ideation_mcp_url_setting():
    """create_idea is an HTTP call, not MCP - the mcp url setting must not exist."""
    from app.config import Settings

    assert "ideation_mcp_url" not in Settings.model_fields, (
        "ideation_mcp_url is retired; create_idea is HTTP (ideation_shared_service_url)"
    )
