"""The chatbot module's lane vocabulary, published for the settings screen (AC-809).

The Settings > Chatbot screen has to render one checkbox per branch kind the build can
complete, and `PUT /settings/general` has to refuse one it cannot. Both live in
`app/api/v1/user_management/settings.py`, which is CORE, and core never imports
`app/services/chatbot/` (AC-002, and `tests/chatbot/test_import_boundary.py` fails naming
the importer). So the module publishes what core needs HERE, on its own surface, and the
package import stays on the module's side of the line - which is what `app/modules/chatbot/`
is for.

`contracts` is imported inside the functions and read as a module attribute, not bound at
import time, so it stays the single source: a slice that adds a lane changes `contracts`
and this answers differently on the next call, with nothing to keep in step.
"""
from __future__ import annotations


def completed_lane_kinds() -> frozenset[str]:
    """Every `branch_kind` this build can finish inside the CRM."""
    from app.services.chatbot import contracts

    return frozenset(contracts.CRM_COMPLETED_BRANCH_KINDS)


def lane_options(*, business_lane_enabled: bool) -> list[tuple[str, bool]]:
    """`(kind, built)` for every lane, sorted, with the one flag the screen needs.

    `built` is False for the three business arms while `chatbot_business_lane_enabled` is
    off: the arm ships, but nothing runs it, so checking it would do nothing at all. Every
    other kind has no second switch and is built unconditionally.
    """
    from app.services.chatbot.contracts import BUSINESS_BRANCH_KINDS

    return [
        (kind, business_lane_enabled if kind in BUSINESS_BRANCH_KINDS else True)
        for kind in sorted(completed_lane_kinds())
    ]
