"""The business lane. S6a owns resolve + gate; fetch (S6b) and answer (S6c) follow.

`run_until_exit` is the ONE call site the engine makes into this package. It exists so
S6a can ship without restructuring `engine.py`: the head still routes, and three of its
arms now come here first and hand n8n a resolve+gate result instead of nothing.

**Which arms, and why those three.** `sorento-consume-main`'s `route` Switch wires
`check_promotion` (arm 8) to `tag-entry-access-check` and both `stock_denied` (arm 11, via
`Edit Fields2`) and `business_query` (the fallback) to `tag-entry-resolve`; both tags then
call `sub-main-processing`, which calls `sub-resolve-and-gate`. So the three arms are the
sub's three real call sites, `entry` is the tag they carried, and `not_allowed_check_stock`
is `Edit Fields2`' one field.

After S6a the CRM returns `delegate = "business_query"` with `delegate_payload` = the
sub's own output item. n8n's `sub-main-processing` enters at `resolve-arm`; its stand-in
chain (`resolve-gate` / `aggregate-gate` / `annotate-incoming-gate` plus the five
name-preserving Code nodes) re-emits the six contract fields, so every by-name reader
downstream is unchanged and the old wiring is one edge away from being restored.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot.lanes.business import resolve_gate
from app.services.chatbot.lanes.business.services import ResolveGateServices

# `branch_kind` -> the `entry` its `tag-entry-*` node stamps. The three arms that reach
# `sub-resolve-and-gate`, and nothing else: an arm absent from this map never enters the
# lane, which is what keeps `run_until_exit` a no-op for the other ten.
ENTRY_BY_BRANCH_KIND: dict[str, str] = {
    "check_promotion": "access_check",
    "stock_denied": "resolve",
    "business_query": "resolve",
}

# The n8n lane the caller must still run after S6a. One name for all three arms because
# they converge on ONE node (`resolve-arm`), and the arm they take there is `_exit_kind`.
DELEGATE = "business_query"


def handles(branch_kind: str | None) -> bool:
    """Does the business lane own this arm?"""
    return branch_kind in ENTRY_BY_BRANCH_KIND


def run_until_exit(
    ctx: dict[str, Any],
    item: dict[str, Any],
    *,
    branch_kind: str,
    services: ResolveGateServices,
    space_id: str | None = None,
    probe_default_start: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run resolve + gate for one turn and return the `{delegate, payload}` fragment.

    `item` is the router's own item, forwarded UNCHANGED.

    An earlier version stamped `not_allowed_check_stock: true` here for the `stock_denied`
    arm, mirroring the spine's `Edit Fields2`. It was dead and is gone: inside the sub the
    item reaches only `tier-gate`'s `$('item')` read, which is on the `access_check` path
    that `stock_denied` never takes, and the node that actually consumes the field -
    `sub-main-processing`'s `validator` - reads it off `$('Edit Fields2')` BY NAME, not off
    the flowing item. That Set node stays in n8n and keeps owning the value; a CRM copy
    would have been a second writer of something it cannot be read from.
    """
    entry = ENTRY_BY_BRANCH_KIND[branch_kind]
    payload = resolve_gate.run(
        ctx,
        entry,
        item,
        services=services,
        space_id=space_id,
        probe_default_start=probe_default_start,
        dry_run=dry_run,
    )
    return {"delegate": DELEGATE, "payload": payload}


__all__ = ["DELEGATE", "ENTRY_BY_BRANCH_KIND", "handles", "run_until_exit"]
