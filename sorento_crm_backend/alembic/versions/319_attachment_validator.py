"""After-sales S2a: a photo can be judged before anybody depends on it.

Three columns on the per-type upload policy table and seven on the link row. **No new
table** (AC-M20): `attachment_types` already IS the per-type upload policy table, beside
`allowed_extensions`, `max_file_size_mb`, `max_count_per_entity` and
`supports_field_linkage`. The `service_job_photo_types` master this supersedes would have
been a second policy row an admin edits in a second dialog, and the two drift the first
time somebody changes one of them.

**This migration touches a table every module in the repo already uploads through**, so
the whole design is "a type that does not opt in behaves exactly as it did the day
before". `validate_on_upload` is NOT NULL with a server default of false, which is the
only shape that leaves the 8 live types alone: nullable would put a third state on a
two-state switch and every read site would then need its own opinion about what a NULL
means, and they would not agree.

**What the tests forced out into the open.** Two columns here are not in AC-M22, and they
exist because the red suite refused the five that were. With only `ai_score` /
`ai_suggestion` / `override_reason` / `latitude` / `longitude`, `ai_score IS NULL` has to
mean three separate things at once - the type does not validate, the model timed out, and
the row predates this migration - so any UI reading NULL as failure REFUSES A GOOD PHOTO
BECAUSE THE NETWORK WAS SLOW, which is precisely the outcome the slice's own risk
mitigation exists to prevent. `ai_validation_state` answers "may I trust ai_score" and
`ai_validation_reason` answers "why not", and the second is the only thing that separates
"my timeout is too short" from "my provider key is wrong". Same ruling, and the same
reason, as S2's explicit `unknown` verdict.

`ai_score` and `min_score` are both `integer`, on one declared 0-100 scale. Nothing in
Group M stated a scale, so the two were not comparable as written; `min_score` is admin
data entry sitting in the same dialog as `max_file_size_mb`, and an admin who types 70
meaning 70% into a 0-1 column sets a threshold nothing can ever clear, silently and
permanently. Both stay NULLable: NULL on `ai_score` is "no claim made", NULL on
`min_score` is "advisory only", and neither is expressible with a default of 0.

`latitude` / `longitude` are `numeric(10,7)`, deliberately identical to
`complaints.latitude` / `longitude`. Two coordinate pairs now exist answering different
questions - where the Site is, and where THIS photo was taken - and they will be read side
by side on one screen, so a capture pin rounded coarser than the Site pin would make "was
this photo taken at the site" unanswerable at the precision the question is asked. They
sit on the LINK and NOT on `attachments`: the argument that a geotag is an immutable
property of the FILE is a good one and is recorded in the AC, but two homes for one fact
is strictly worse than one arguable home.

Everything to do with the verdict is on the LINK for a harder reason than convenience.
The same receipt scored as intake evidence and as collection proof gets two different
numbers, because the guidance differs, and a column on `attachments` can hold only one of
them - it would silently report the last upload's verdict for both.

**What stays broken after this migration.** Nothing meters the cost: every opted-in
upload is now an LLM call and no equivalent of `ai_extract`'s `AIAssistantUsageLog` row is
written, so there is no way to answer "what did photo validation cost last month" or to
rate-limit it. That needs a decision before this reaches a public page, where the callers
are unauthenticated. The seeded 8 attachment types all keep `validate_on_upload = false`,
so NOTHING is validated until an admin opts a type in; the guidance strings AC-M26
describes are written in a later slice. Only IMAGES are judged - a PDF receipt, a .docx
and a .heic all degrade to `unvalidated` / `unsupported_media`, which keeps the upload but
means a document-shaped evidence type cannot be validated until PDF page rendering is
wired in (`ai_extract` already has it, behind a service that needs a db handle).

Every idempotency guard here is load-bearing: the shared dev database is stamped on
another worktree's chain, so this DDL gets applied by hand there and a plain `add_column`
would abort the whole upgrade.

Revision ID: 319_attachment_validator
Revises: 318_consumer_ledger
Create Date: 2026-08-03

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "319_attachment_validator"
down_revision = "318_consumer_ledger"
branch_labels = None
depends_on = None

_TYPES = "attachment_types"
_LINKS = "entity_attachment_links"

# (table, column, type, kwargs) - the whole slice's DDL, declared once so upgrade and
# downgrade cannot disagree about what was added.
_COLUMNS = (
    # AC-M20: the per-type upload policy, joining the caps already on this row.
    (_TYPES, "validation_guidance", sa.Text(), {"nullable": True}),
    (_TYPES, "min_score", sa.Integer(), {"nullable": True}),
    (
        _TYPES,
        "validate_on_upload",
        sa.Boolean(),
        {"nullable": False, "server_default": sa.text("false")},
    ),
    # AC-M22 plus the two the red suite added.
    (_LINKS, "ai_validation_state", sa.String(length=20), {"nullable": True}),
    (_LINKS, "ai_validation_reason", sa.String(length=32), {"nullable": True}),
    (_LINKS, "ai_score", sa.Integer(), {"nullable": True}),
    (_LINKS, "ai_suggestion", sa.Text(), {"nullable": True}),
    (_LINKS, "override_reason", sa.Text(), {"nullable": True}),
    (_LINKS, "latitude", sa.Numeric(10, 7), {"nullable": True}),
    (_LINKS, "longitude", sa.Numeric(10, 7), {"nullable": True}),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set:
    return {c["name"] for c in _inspector().get_columns(table)}


def upgrade() -> None:
    tables = set(_inspector().get_table_names())
    present: dict = {}
    for table, name, type_, kwargs in _COLUMNS:
        if table not in tables:
            continue
        if table not in present:
            present[table] = _columns(table)
        if name in present[table]:
            continue
        op.add_column(table, sa.Column(name, type_, **kwargs))

    if _LINKS in tables:
        # The reviewer's question is "which uploads are being overridden", and the
        # answer is a handful of rows in a table with hundreds of thousands. Partial,
        # because indexing the NULLs would be indexing every row that has nothing to
        # say.
        indexes = {ix["name"] for ix in _inspector().get_indexes(_LINKS)}
        if "ix_entity_attachment_links_ai_validation_state" not in indexes:
            op.create_index(
                "ix_entity_attachment_links_ai_validation_state",
                _LINKS,
                ["ai_validation_state"],
                postgresql_where=sa.text("ai_validation_state IS NOT NULL"),
            )

    # The prompt itself is registry data (AC-M25), so a new photo type is admin data
    # entry rather than a deployment. Idempotent and shared: it inserts a v1 from the
    # hardcoded fallback for any key that has none and moves no existing label, so a
    # re-run cannot duplicate a version or silently republish another node's prompt.
    from app.services.ai_prompt_seed import seed_prompt_registry

    seed_prompt_registry(op.get_bind())


def downgrade() -> None:
    tables = set(_inspector().get_table_names())
    if _LINKS in tables:
        indexes = {ix["name"] for ix in _inspector().get_indexes(_LINKS)}
        if "ix_entity_attachment_links_ai_validation_state" in indexes:
            op.drop_index("ix_entity_attachment_links_ai_validation_state", table_name=_LINKS)
    for table, name, _type, _kwargs in reversed(_COLUMNS):
        if table not in tables:
            continue
        if name in _columns(table):
            op.drop_column(table, name)
    # The seeded prompt version is left in place: it is data an admin may already have
    # edited or labelled, and a downgrade that deletes it would take an edit with it.
