"""Bare 柜号 / 封条 shared aliases (design A2, owner ruling 4, 24 Sep 2026,
PLAN-pi-header-fields-convert-fixes-24sep.md).

DAFUYUAN's own header cell states three facts in one run - `提单号 ：OOLU2339207730
柜号 ：FSCU9304169  封条号：OOLLGZ7182` - and NEW YANGGANG's combined-file header states the
same three with a BARE `封条` (not `封条号`): `提单号：  柜号：FSCU8706420  封条：OOLLJN6147`.
`提单号` already resolves to `bl_no` (375) and `封条号` to `seal_no` (506) for both doc
types; `柜号` and bare `封条` resolve to NOTHING today - `货柜号`/`箱号` are container_no
aliases (311/483) but the bare two-character `柜号` on its own is not, and `封签号`/`封条号`
are seal_no aliases (483/506) but bare `封条` is not. A1's cell-splitter (design A1) can
only ever split at a label the resolver already knows, so without these two rows the
DAFUYUAN/NEW YANGGANG header cells never split past their first pair.

Seeded shared (`supplier_id IS NULL`) for BOTH doc types, same convention 483/506 use -
`import_field_alias`'s own unique partial index is the idempotency guard.
"""
import sqlalchemy as sa
from alembic import op

revision = "ifa_bare_container_seal"
down_revision = "sdbt_0001_download_counts"
branch_labels = None
depends_on = None

#: (doc_type, field, alias, locale)
_ALIASES = [
    ("proforma_invoice", "container_no", "柜号", "zh"),
    ("packing_list", "container_no", "柜号", "zh"),
    ("proforma_invoice", "seal_no", "封条", "zh"),
    ("packing_list", "seal_no", "封条", "zh"),
]


def seed(bind) -> None:
    """Exposed for the tests, which build their schema from the migrations by hand."""
    for doc_type, field, alias, locale in _ALIASES:
        bind.execute(
            sa.text(
                "INSERT INTO import_field_alias (doc_type, field, alias, locale) "
                "VALUES (:d, :f, :a, :l) "
                "ON CONFLICT (doc_type, field, alias) WHERE supplier_id IS NULL DO NOTHING"
            ),
            {"d": doc_type, "f": field, "a": alias, "l": locale},
        )


def upgrade() -> None:
    seed(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    for doc_type, field, alias, _locale in _ALIASES:
        bind.execute(
            sa.text(
                "DELETE FROM import_field_alias "
                "WHERE doc_type = :d AND field = :f AND alias = :a AND supplier_id IS NULL"
            ),
            {"d": doc_type, "f": field, "a": alias},
        )
