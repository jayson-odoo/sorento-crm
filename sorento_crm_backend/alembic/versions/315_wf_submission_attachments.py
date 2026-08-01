"""Files on a workflow submission and on its lines (F2c).

**This migration creates no table, and that is the point.** AC-F2c-1 was tagged `[MIG]`,
which is what invites someone to add the `workflow_submission_attachments` table the same
AC forbids. `entity_attachment_links` already carries `entity_type` VARCHAR(50) and
`entity_id` VARCHAR(100), both wide enough for `workflow_submission` and
`workflow_submission_line`, so the header and the line ride the existing polymorphic
table under two entity types declared once in
`app/services/workflow_submission_attachments.py`. A bespoke table would be this repo's
THIRD linkage pattern (per-entity tables, the generic table, and one more) on the one
feature whose premise is that a new form is configuration rather than code: every future
form type would then need its own migration before it could hold a photo. The AC is
retagged `[BE][SEED]`.

So the whole content is one `attachment_types` row, and it matters because that row IS
the configuration: `max_count_per_entity` is the cap (blank meaning unlimited),
`allowed_extensions` is what a customer may send and `max_file_size_mb` is how much.
Hardcoding any of them in the upload path would make "how many photos may a claim hold"
a deploy.

Seeded through the same function the application and the tests call, not restated as SQL
(ADR-0013 rule 10): the code string is the FIRST segment of every storage key this type
ever writes, so a migration spelling it differently would scatter objects under two
prefixes with nothing to relate them. The seeder converges - a re-run repairs a drifted
extension list or cap IN PLACE, keeping the row's id, so every attachment already
pointing at it follows the repair.

**Found by writing the tests, and fixed in the service rather than here:**
`entity_attachment_links` has NO foreign key on `entity_id`, so a line id belonging to
another customer's claim inserts happily and the file appears under their item. A
database constraint cannot express it (the column is polymorphic), so the parent/child
check lives in the service, where every caller inherits it - a guard on the action routes
is not a guard (ADR-0013 rule 7).

**What stays broken, deliberately, and is pre-existing:** `max_count_per_entity = 0`
means "never attachable" rather than "unlimited", so a form posting `0` instead of
omitting the field silently bricks a whole attachment type; and `attachments.uploaded_by`
is a `uuid` column while `users.id` is `String(64)`, so a non-uuid principal (the API-key
principal is literally `system`) would 500 the upload. The upload path drops a non-uuid
id and keeps the file, the way every neighbouring call site does, so the row degrades to
"a staff member we cannot name" rather than to a failed upload. Both are wider than F2c
and belong with whoever fixes them for all six upload paths at once.

Revision ID: 315_wf_submission_attachments
Revises: 314_wf_submission_portal
Create Date: 2026-08-01

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "315_wf_submission_attachments"
down_revision = "314_wf_submission_portal"
branch_labels = None
depends_on = None

_TABLE = "attachment_types"


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    """Seed (or correct) the `workflow_submission_file` attachment type.

    Defensive like 311-314: the shared development database is stamped on another
    worktree's chain and cannot be brought forward, so it may be missing the table this
    seed writes to. A guard is cheaper than a failed deploy on a schema that has simply
    not caught up yet.
    """
    bind = op.get_bind()
    if _TABLE not in set(_inspector().get_table_names()):
        return

    from app.services.workflow_submission_attachments import (
        seed_workflow_submission_attachment_type,
    )

    session = Session(bind=bind)
    try:
        seed_workflow_submission_attachment_type(session)  # flushes only
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    """Leaves the seeded row.

    Deleting the type would set `attachments.attachment_type_id` to NULL on every file
    already uploaded against it (the FK is ON DELETE SET NULL), which loses the cap, the
    extension list and the only thing tying those rows to this feature - while the
    objects themselves stay in the bucket under a prefix nothing can now explain. An
    inert configuration row is the cheaper end state, and a re-run of `upgrade` converges
    it.
    """
