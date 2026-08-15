"""Shared SQLAlchemy scope filters for ``conversation_sla_tracking``.

Its own module so every consumer - services, routers, dashboards - can import the
predicate without dragging in ``sla_service`` (which imports half the app) and
without an import cycle.

``not_voided()`` is the one that matters here. A tracker whose stage was voided
(today only by a contact revising the submission underneath it) is NOT resolved:
it was cancelled before anyone could finish it, and overloading ``is_resolved``
would count it as a completed stage in every duration and KPI aggregate. So it
stays ``is_resolved = false`` and carries ``voided_at`` instead, which means every
query that reads "unresolved" as "still open" has to say so explicitly.

See UAC ``portal-submission-revisions`` F4/F4a.
"""
from __future__ import annotations

from app.models.sla import ConversationSLATracking


def not_voided():
    """Rows whose stage has not been voided."""
    return ConversationSLATracking.voided_at.is_(None)


def open_tracker_scope():
    """Rows that are genuinely still open: unresolved AND not voided.

    Use this wherever "unresolved" was standing in for "open" - overdue scans,
    active-tracker lookups, open-work and breach aggregates.
    """
    return (
        ConversationSLATracking.is_resolved.is_(False),
        ConversationSLATracking.voided_at.is_(None),
    )
