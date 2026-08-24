"""Seed Annual Dinner Sponsorship workflow form (definition + published schema + demo submission).

Revision ID: 108_seed_annual_dinner_sponsorship_workflow
Revises: 107_workflow_forms_list_query
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "108_seed_annual_dinner_sponsorship_workflow"
down_revision = "107_workflow_forms_list_query"
branch_labels = None
depends_on = None

CODE = "annual_dinner_sponsorship"


def _repo_root() -> Path:
    # alembic/versions/*.py -> parents[3] = repo root (sorento_crm)
    return Path(__file__).resolve().parents[3]


def _load_seed() -> dict:
    path = _repo_root() / "docs" / "workflow-seeds" / "annual_dinner_sponsorship_form.json"
    if not path.is_file():
        raise RuntimeError(
            f"Seed file missing: {path}. Restore docs/workflow-seeds/annual_dinner_sponsorship_form.json"
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def upgrade() -> None:
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT id FROM workflow_form_definitions WHERE code = :c"),
        {"c": CODE},
    ).fetchone()
    if existing:
        return

    seed = _load_seed()
    schema = seed["draft_schema"]
    sample_header = seed.get("sample_header_data") or {}
    def_meta = seed.get("definition") or {}

    definition_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    submission_id = str(uuid.uuid4())

    schema_json = json.dumps(schema)
    header_json = json.dumps(sample_header)

    conn.execute(
        sa.text(
            """
            INSERT INTO workflow_form_definitions (
                id, code, name, description, is_active, draft_schema,
                published_version_id, created_by_user_id
            )
            VALUES (
                :id, :code, :name, :desc, true, CAST(:draft AS jsonb),
                NULL, NULL
            )
            """
        ),
        {
            "id": definition_id,
            "code": CODE,
            "name": def_meta.get("name", "Annual Dinner Sponsorship (Dealer)"),
            "desc": def_meta.get(
                "description",
                "Sponsorship request - customer detail, criteria/SKUs, contact, dealer dinner.",
            ),
            "draft": schema_json,
        },
    )

    conn.execute(
        sa.text(
            """
            INSERT INTO workflow_form_versions (
                id, definition_id, version_number, schema, created_by_user_id
            )
            VALUES (
                :vid, :did, 1, CAST(:sch AS jsonb), NULL
            )
            """
        ),
        {"vid": version_id, "did": definition_id, "sch": schema_json},
    )

    conn.execute(
        sa.text(
            """
            UPDATE workflow_form_definitions
            SET published_version_id = :vid, updated_at = NOW()
            WHERE id = :did
            """
        ),
        {"vid": version_id, "did": definition_id},
    )

    # Demo submission in initial state (draft) with sample header data
    conn.execute(
        sa.text(
            """
            INSERT INTO workflow_submissions (
                id, definition_id, version_id, current_state_code,
                header_data, created_by_user_id, updated_by_user_id
            )
            VALUES (
                :sid, :did, :vid, 'draft',
                CAST(:hdr AS jsonb), NULL, NULL
            )
            """
        ),
        {
            "sid": submission_id,
            "did": definition_id,
            "vid": version_id,
            "hdr": header_json,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT id FROM workflow_form_definitions WHERE code = :c"),
        {"c": CODE},
    ).fetchone()
    if not row:
        return
    did = row[0]
    conn.execute(sa.text("DELETE FROM workflow_form_definitions WHERE id = :id"), {"id": did})
