"""Project task management (S2b, UAC Group N).

Revision ID: 311_project_tasks
Revises: 310_project_clash_thresholds

Two tables. ``project_template_tasks`` is the checklist a template hands to every
project created from it; ``project_tasks`` is the instantiated work.

The two axes on a task are deliberately separate columns and not one field:
``task_phase`` (pursuit | delivery) is where in the project's life the work sits,
``category`` is which work-stream it belongs to. Collapsing them was the design error
the ecohub reference pass caught.
"""
from alembic import op

revision = "311_project_tasks"
down_revision = "310_project_clash_thresholds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_template_tasks (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            template_id UUID NOT NULL
                REFERENCES project_templates(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            task_phase VARCHAR(16) NOT NULL DEFAULT 'pursuit',
            category VARCHAR(120),
            sort_order INTEGER NOT NULL DEFAULT 0,
            default_offset_days INTEGER,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_project_template_tasks_template
            ON project_template_tasks (template_id, sort_order);

        CREATE TABLE IF NOT EXISTS project_tasks (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            task_phase VARCHAR(16) NOT NULL DEFAULT 'pursuit',
            category VARCHAR(120),
            status_id UUID REFERENCES statuses(id) ON DELETE SET NULL,
            assignee_user_id VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
            escalated_to_user_id VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
            stuck_reason TEXT,
            start_date DATE,
            due_date DATE,
            completed_at TIMESTAMP,
            sort_order INTEGER NOT NULL DEFAULT 0,
            source_template_task_id UUID
                REFERENCES project_template_tasks(id) ON DELETE SET NULL,
            linked_entity_type VARCHAR(32),
            linked_entity_id UUID,
            created_by VARCHAR(100),
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_project_tasks_project_phase
            ON project_tasks (project_id, task_phase);
        CREATE INDEX IF NOT EXISTS ix_project_tasks_status
            ON project_tasks (status_id);
        CREATE INDEX IF NOT EXISTS ix_project_tasks_assignee
            ON project_tasks (assignee_user_id);
        -- "My Tasks" reads one user's open tasks across every project, due date first.
        CREATE INDEX IF NOT EXISTS ix_project_tasks_assignee_due
            ON project_tasks (assignee_user_id, due_date);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS project_tasks;
        DROP TABLE IF EXISTS project_template_tasks;
        """
    )
