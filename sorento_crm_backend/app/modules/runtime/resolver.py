"""Topological install plan and reverse dependency lookup (graph from DB catalog)."""
from __future__ import annotations

from typing import Dict, List, Mapping, MutableMapping, Set


def resolve_install_plan(
    dep_graph: Mapping[str, Set[str]],
    requested_keys: List[str],
) -> List[str]:
    """
    Return module keys in install order (dependencies first), deduplicated.
    Raises ValueError on unknown keys or cycles.
    """
    for k in requested_keys:
        if k not in dep_graph:
            raise ValueError(f"Unknown module: {k}")

    seen: Set[str] = set()
    order: List[str] = []

    def visit(key: str, stack: Set[str]) -> None:
        if key in seen:
            return
        if key in stack:
            raise ValueError(f"Circular module dependency involving {key}")
        stack.add(key)
        for dep in sorted(dep_graph.get(key, ())):
            visit(dep, stack)
        stack.remove(key)
        seen.add(key)
        order.append(key)

    for req in requested_keys:
        visit(req, set())

    return order


def get_reverse_dependents(
    dep_graph: Mapping[str, Set[str]],
    module_key: str,
) -> List[str]:
    """Modules that directly depend on module_key (for disable safety / UX)."""
    if module_key not in dep_graph:
        raise ValueError(f"Unknown module: {module_key}")
    out: List[str] = []
    for k, deps in dep_graph.items():
        if module_key in deps:
            out.append(k)
    return sorted(out)


def transitive_dependencies(
    dep_graph: Mapping[str, Set[str]],
    module_key: str,
) -> Set[str]:
    """All modules required by module_key (recursive)."""
    if module_key not in dep_graph:
        raise ValueError(f"Unknown module: {module_key}")
    result: Set[str] = set()
    stack = list(dep_graph[module_key])
    while stack:
        d = stack.pop()
        if d in result:
            continue
        result.add(d)
        stack.extend(dep_graph.get(d, ()))
    return result


def enabled_modules_blocking_disable(
    dep_graph: Mapping[str, Set[str]],
    module_key: str,
    enabled_module_keys: Set[str],
) -> List[str]:
    """
    If disabling module_key, return other enabled modules that still transitively depend on it.
    """
    conflicts: List[str] = []
    for e in sorted(enabled_module_keys):
        if e == module_key:
            continue
        if module_key in transitive_dependencies(dep_graph, e):
            conflicts.append(e)
    return conflicts


def installed_modules_blocking_uninstall(
    dep_graph: Mapping[str, Set[str]],
    module_key: str,
    installed_module_keys: Set[str],
) -> List[str]:
    """
    If removing module_key from the tenant, return other still-installed modules that depend on it.
    Stricter than disable (considers disabled-but-installed dependents).
    """
    conflicts: List[str] = []
    for e in sorted(installed_module_keys):
        if e == module_key:
            continue
        if module_key in transitive_dependencies(dep_graph, e):
            conflicts.append(e)
    return conflicts
