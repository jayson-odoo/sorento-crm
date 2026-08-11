"""Every `dispatch_or_defer` call in the domain routers names a real, matching action.

The route glue is a string contract: `action_key` must exist in the registry, and the
route's `entity_type` must be one the action declares. Nothing checks that at import
time - a typo'd key or a complaint route dispatching a stock-inquiry action would only
surface as a 409 in production, ten seconds after a user clicked.

Static source scan, no app boot, no database - so it runs everywhere and fails the
moment a new route wires an action the registry does not back.
"""
from __future__ import annotations

import re
from pathlib import Path

import app.services.form_actions  # noqa: F401  (registers the actions)
from app.services.form_action_registry import REGISTRY, get_action

ROUTE_FILES = [
    "app/api/v1/procurement/purchase_requests.py",
    "app/api/v1/procurement/stock_inquiries.py",
    "app/api/v1/complaints/complaints.py",
    "app/api/v1/tickets/tickets.py",
]

_BACKEND_ROOT = Path(__file__).resolve().parents[1]

# One dispatch call site: action_key first, entity_type somewhere after it within the
# same call. PR/SF routes resolve entity_type at runtime (request_type), so the
# entity_type group is optional there.
_CALL_RX = re.compile(
    r"action_key=\"(?P<key>[a-z_]+\.[a-z_]+)\""
    r"(?:.{0,200}?entity_type=\"(?P<etype>[a-z_]+)\")?",
    re.DOTALL,
)


def _call_sites():
    for rel in ROUTE_FILES:
        source = (_BACKEND_ROOT / rel).read_text()
        for match in _CALL_RX.finditer(source):
            yield rel, match.group("key"), match.group("etype")


def test_routes_dispatch_at_least_the_wired_surface():
    """If this shrinks, a route stopped dispatching - deferral silently died there."""
    keys = {key for _, key, _ in _call_sites()}
    assert {
        "pr.approval_decision",
        "pr.send_for_approval",
        "pr.reject_submitted",
        "pr.finalize",
        "si.purchasing_respond",
        "si.project_sales_approve",
        "si.project_sales_reject",
        "si.purchasing_decide",
        "cx.decide",
        "cx.finalize",
        "tk.resolve",
    } <= keys


def test_every_wired_action_key_exists_in_the_registry():
    for rel, key, _ in _call_sites():
        assert get_action(key) is not None, f"{rel} dispatches unknown action {key!r}"


def test_every_wired_entity_type_matches_the_action_declaration():
    for rel, key, etype in _call_sites():
        if etype is None:
            continue  # PR/SF resolve entity_type at runtime from request_type
        action = get_action(key)
        assert action is not None, f"{rel}: {key!r} not registered"
        assert etype in action.entity_types, (
            f"{rel} dispatches {key!r} for {etype!r}, but the action only covers "
            f"{action.entity_types}"
        )


def test_registry_covers_every_form_type_the_routes_dispatch_for():
    """All four form families stay deferrable - a registry refactor that drops one
    form type must fail here, not in a user's browser."""
    covered = {t for action in REGISTRY.values() for t in action.entity_types}
    assert {
        "purchase_request",
        "sponsorship_form",
        "stock_inquiry",
        "complaint",
        "ticket",
    } <= covered
