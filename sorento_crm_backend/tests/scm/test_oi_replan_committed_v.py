"""AC-RL-15 (`PLAN-oi-replan-received-links.md` S3): `committed_v`'s confirmed leg must
not net a redirected row's quantity - the goods it names shipped to other orders a year
ago, and reading them as this line's own cover would silently understate what purchasing
still has to buy.

Reuses `tests/test_order_inquiry_handshake.py`'s harness (`world` / `api`,
`_raise_one_row`, `_settle`, `_project_committed`) and `tests/test_order_inquiry_draft_
links.py`'s `_redirected_fixture` (the settle-seam fixture builder), for the reason both
those files already state: one seeding chain, and the real database because `scm.
committed_v` lives in the migrated schema, not the blank scratch one.

TEST-FIRST: `demand.py`'s confirmed leg has no `redirected_to_pool` exclusion yet, so the
red state is `committed_v` netting the redirected row's own qty ON TOP OF the fresh row's,
never an import error.
"""
from __future__ import annotations

from decimal import Decimal

from tests.test_order_inquiry_draft_links import _redirected_fixture
from tests.test_order_inquiry_handshake import _project_committed, api, world

__all__ = ["api", "world"]  # re-exported fixtures; keeps linters from calling them unused


def test_committed_v_ignores_redirected_row(api):
    """The redirected row contributes nothing - neither its own qty nor its links - and
    the fresh row contributes its full replanned need."""
    _client, world = api

    _redirected_fixture(api)

    assert _project_committed(world, planned=False) == Decimal("220")
