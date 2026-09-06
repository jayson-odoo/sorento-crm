"""attachment_types.default_directory_id - the folder an upload of this type files into.

R4 (purchasing consolidation batch, 6 Sep 2026). One preference, one column: the Upload
packing list CTA (section 2) needs somewhere to file the document it just read, and the
generic Create Attachment dialog pre-selects the same folder once a type carrying one is
picked. Nullable, SET NULL on the folder's delete - a type with no default behaves exactly
as it does today (AC-B4).

No seed here. Which type gets which folder is admin data, set by the captain after deploy
(the plan's own ruling), not code.

Revision ID: 482_attachment_type_default_dir
Revises: 481_chatbot_turns_is_test
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "482_attachment_type_default_dir"
down_revision = "481_chatbot_turns_is_test"
branch_labels = None
depends_on = None

_TABLE = "attachment_types"
_COLUMN = "default_directory_id"
_FK = "fk_attachment_types_default_directory"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_column(table: str, column: str) -> bool:
    return column in {col["name"] for col in _inspector().get_columns(table)}


def _has_fk(table: str, name: str) -> bool:
    return name in {fk["name"] for fk in _inspector().get_foreign_keys(table)}


def upgrade() -> None:
    if not _has_column(_TABLE, _COLUMN):
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, UUID(as_uuid=False), nullable=True),
        )
    if not _has_fk(_TABLE, _FK):
        op.create_foreign_key(
            _FK,
            source_table=_TABLE,
            referent_table="attachment_directories",
            local_cols=[_COLUMN],
            remote_cols=["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if _has_fk(_TABLE, _FK):
        op.drop_constraint(_FK, _TABLE, type_="foreignkey")
    if _has_column(_TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
