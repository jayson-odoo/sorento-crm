"""Showroom walkthroughs: dealer_kit.walkthrough and dealer_kit.walkthrough_stop.

PLAN-showroom-walkthrough-28oct.md. A walkthrough is company owned; a stop is
reached only through its walkthrough and dies with it.

Revision ID: wt_0001_showroom_walkthrough
Revises: stg_0001_project_ladder_edges
"""

from alembic import op

revision = "wt_0001_showroom_walkthrough"
down_revision = "stg_0001_project_ladder_edges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS dealer_kit")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dealer_kit.walkthrough (
            id          uuid PRIMARY KEY,
            name        varchar(200) NOT NULL,
            created_by  uuid,
            company_id  uuid REFERENCES companies (id),
            created_at  timestamp without time zone NOT NULL DEFAULT now(),
            updated_at  timestamp without time zone NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_dealer_kit_walkthrough_company_created
        ON dealer_kit.walkthrough (company_id, created_at)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dealer_kit.walkthrough_stop (
            id                uuid PRIMARY KEY,
            walkthrough_id    uuid NOT NULL
                REFERENCES dealer_kit.walkthrough (id) ON DELETE CASCADE,
            position          integer NOT NULL,
            title             varchar(200) NOT NULL,
            status            varchar(16) NOT NULL,
            error_message     text,
            storage_provider  varchar(16),
            panorama_key      varchar(512),
            h_fov_deg         numeric(6, 2),
            v_fov_deg         numeric(6, 2),
            job_id            varchar(64),
            created_at        timestamp without time zone NOT NULL DEFAULT now(),
            finished_at       timestamp without time zone,
            CONSTRAINT ck_dealer_kit_walkthrough_stop_status
                CHECK (status IN ('processing', 'done', 'failed'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_dealer_kit_walkthrough_stop_walkthrough
        ON dealer_kit.walkthrough_stop (walkthrough_id, position)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dealer_kit.walkthrough_stop")
    op.execute("DROP TABLE IF EXISTS dealer_kit.walkthrough")
