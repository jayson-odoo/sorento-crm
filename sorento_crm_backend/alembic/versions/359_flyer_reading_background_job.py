"""The flyer reading row becomes the record of a background read.

The read moved out of the request (`PLAN-flyer-read-background-job.md`): the
POST now returns 202 and an RQ job does the extraction. That only works if the
row exists from the first second, in the SAME id it will carry when the report
is ready - which is what makes "it appears in my uploads at once" and "Done
links to the report exactly as today" one thing rather than two.

So the row gains a lifecycle.

* `status` is `processing` / `done` / `failed`, and its server default is
  **`done`**. That default IS the backfill (gate 2 of PRINCIPLES): every row
  already in this table was read synchronously and successfully by the old
  route, so `done` is not a guess about them, it is what happened. A CHECK
  pins the three values, because a fourth spelling would render as an unknown
  pill on the Flyers list and nothing would say why.
* `error_message` carries the refusal in the words the request used to say
  ("not a PDF", "password protected", "over the 50 MB limit"). Without it a
  failed read is a row that says nothing, and the designer re-uploads the same
  broken file.
* `finished_at` is when the job wrote done or failed. `created_at` is when it
  was asked for; the two differ by the whole read, which is the number anybody
  tuning this will want.
* `source_attachment_id` is the library file a read came from, NULL for an
  upload. Deliberately **no foreign key**: a reading is derived working
  material and must never block or cascade an attachment delete. The bytes are
  not kept either, so a reading whose source file was deleted is still a
  perfectly good reading.
* `job_id` is the RQ job, for an operator asking "where did that read go".

`sha256` becomes NULLABLE, and that is the one change here that is not additive.
The library path has no bytes at enqueue time - the whole point is that nothing
is fetched in the request - so it cannot fingerprint anything until the job
runs. The column is filled by the job. `byte_size` stays NOT NULL: at enqueue it
is the real length for an upload and the attachment's recorded size (or 0) for
the library path, and the job overwrites it with what actually arrived.

Two partial indexes serve the idempotent re-click: while a read for the same
source is in flight, a second POST returns the row already running rather than
starting a duplicate 20 to 60 second extraction. Partial on
`status = 'processing'`, because that is the only state the lookup ever asks
about and the table is overwhelmingly `done`.

They are **UNIQUE**, and that is the whole guarantee rather than a lookup
optimisation. The service reads (`_reading_in_flight`) and then inserts, and
between those two statements sits a window: a double-click, a retried request
or two tabs both find nothing in flight, both insert, and the loser's job reads
the same document a second time and stores a second set of banners into the
asset library. No application-side check can close that window, so the index
does: the second insert is refused, and the service turns the refusal into the
row that won.

Two NULL notes, because they decide what the indexes actually forbid.
`sha256` is NULL on every library read until its job fills it in, and
`source_attachment_id` is NULL on every upload; Postgres treats NULLs as
distinct in a unique index, so neither index constrains rows that have nothing
to be constrained on. That is exactly right - two different attachments read at
once are two reads - and it is why the pair has to be two indexes rather than
one over both columns. A row whose `company_id` is NULL (nothing in the request
path produces one) is likewise unconstrained, falling back to today's
read-then-insert behaviour rather than to something worse.

Every statement is idempotent (IF NOT EXISTS / a pg_constraint probe), matching
316's reasoning: several worktrees share one local database and this may already
have been applied by hand.

It chains onto `359_scm_plan_feedback_r2`, not onto `358`, because that revision
landed on main while this branch was in flight. Two revisions off the same
parent are a dual head, and `alembic upgrade head` / CI's `bootstrap_env` stamp
both fail outright with "Multiple heads are present". The sibling file is
vendored into this branch verbatim (357's reasoning) so the graph resolves on a
branch-only checkout too; it is byte-identical to main's, so the git merge is a
no-op on it.

Revision ID: 359_flyer_read_background_job
Revises: 359_scm_plan_feedback_r2
"""

from alembic import op

revision = "359_flyer_read_background_job"
down_revision = "359_scm_plan_feedback_r2"
branch_labels = None
depends_on = None

STATUS_CHECK = "ck_dealer_kit_flyer_reading_status"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE dealer_kit.flyer_reading
        ADD COLUMN IF NOT EXISTS status varchar(16) NOT NULL DEFAULT 'done',
        ADD COLUMN IF NOT EXISTS error_message text,
        ADD COLUMN IF NOT EXISTS finished_at timestamp without time zone,
        ADD COLUMN IF NOT EXISTS source_attachment_id uuid,
        ADD COLUMN IF NOT EXISTS job_id varchar(64)
        """
    )

    # Postgres has no ADD CONSTRAINT IF NOT EXISTS, so probe the catalog.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{STATUS_CHECK}'
            ) THEN
                ALTER TABLE dealer_kit.flyer_reading
                ADD CONSTRAINT {STATUS_CHECK}
                CHECK (status IN ('processing', 'done', 'failed'));
            END IF;
        END
        $$
        """
    )

    op.execute("ALTER TABLE dealer_kit.flyer_reading ALTER COLUMN sha256 DROP NOT NULL")

    # The idempotency guard, one index per source. Partial because a finished
    # reading never blocks a new read of the same file, UNIQUE because the
    # read-then-insert above it cannot be made atomic in application code.
    #
    # Dropped first: an earlier cut of this same (unmerged) revision created
    # these NON-unique, and `CREATE INDEX IF NOT EXISTS` would find that name
    # taken and leave the weaker index in place without a word. The drop makes
    # the statement say what the database ends up with.
    op.execute(
        "DROP INDEX IF EXISTS dealer_kit.ix_dealer_kit_flyer_reading_pending_attachment"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_dealer_kit_flyer_reading_pending_attachment
        ON dealer_kit.flyer_reading (company_id, source_attachment_id)
        WHERE status = 'processing'
        """
    )
    op.execute(
        "DROP INDEX IF EXISTS dealer_kit.ix_dealer_kit_flyer_reading_pending_sha256"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_dealer_kit_flyer_reading_pending_sha256
        ON dealer_kit.flyer_reading (company_id, sha256)
        WHERE status = 'processing'
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS dealer_kit.ix_dealer_kit_flyer_reading_pending_sha256"
    )
    op.execute(
        "DROP INDEX IF EXISTS dealer_kit.ix_dealer_kit_flyer_reading_pending_attachment"
    )
    # A row the job never finished has no fingerprint, and NOT NULL would refuse
    # to come back over it. Nothing can read a half-written reading anyway, so
    # they are removed rather than invented.
    op.execute(
        "DELETE FROM dealer_kit.flyer_reading WHERE sha256 IS NULL"
    )
    op.execute("ALTER TABLE dealer_kit.flyer_reading ALTER COLUMN sha256 SET NOT NULL")
    op.execute(
        f"ALTER TABLE dealer_kit.flyer_reading DROP CONSTRAINT IF EXISTS {STATUS_CHECK}"
    )
    op.execute(
        """
        ALTER TABLE dealer_kit.flyer_reading
        DROP COLUMN IF EXISTS job_id,
        DROP COLUMN IF EXISTS source_attachment_id,
        DROP COLUMN IF EXISTS finished_at,
        DROP COLUMN IF EXISTS error_message,
        DROP COLUMN IF EXISTS status
        """
    )
