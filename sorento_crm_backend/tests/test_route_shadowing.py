"""Literal-segment routes must be declared before the parameterised ones that
would swallow them.

FastAPI matches in declaration order, so ``GET /customers/{customer_id}`` mounted
ahead of ``GET /customers/select`` captures the literal word "select" as a customer
id. The symptom is a 404 that looks like missing data rather than a routing mistake,
which is why this is worth a guard instead of a code comment: the same class of bug
already hit ``/sla/integration/escalate``.

Asserted against the assembled app, so it covers every module at once and catches a
new offender the moment somebody mounts one.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import pytest

from app.main import app

# Literal segments that are known API verbs rather than identifiers. A route ending in
# one of these must not sit behind a same-prefix parameterised route.
LITERAL_LEAF_SEGMENTS = {
    "select",
    "metrics",
    "summary",
    "export",
    "search",
    "options",
    "my-tasks",
    "disqualify-reasons",
    "clash-preview",
}


def _routes() -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            out.append((method, path))
    return out


def _parent_and_leaf(path: str) -> Tuple[str, str]:
    parts = path.rstrip("/").split("/")
    return "/".join(parts[:-1]), parts[-1]


def test_no_literal_route_is_shadowed_by_a_parameterised_sibling():
    routes = _routes()

    # Declaration order per (method, parent prefix).
    order: Dict[Tuple[str, str], List[str]] = {}
    for index, (method, path) in enumerate(routes):
        parent, leaf = _parent_and_leaf(path)
        order.setdefault((method, parent), []).append(leaf)

    offenders = []
    for (method, parent), leaves in order.items():
        for position, leaf in enumerate(leaves):
            if leaf not in LITERAL_LEAF_SEGMENTS:
                continue
            earlier_param = next(
                (
                    candidate
                    for candidate in leaves[:position]
                    if candidate.startswith("{") and candidate.endswith("}")
                ),
                None,
            )
            if earlier_param:
                offenders.append(
                    f"{method} {parent}/{leaf} is shadowed by "
                    f"{method} {parent}/{earlier_param} declared before it"
                )

    assert not offenders, "Literal routes captured by a parameterised sibling:\n" + "\n".join(
        sorted(offenders)
    )
