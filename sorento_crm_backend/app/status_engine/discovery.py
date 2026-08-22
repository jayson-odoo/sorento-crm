"""Finds the module-supplied status entities.

ADR-0001 says core ships an empty registry and every entity arrives from a module.
That leaves a gap: something has to import the modules, and if that something is a
hardcoded list inside core then core knows its modules after all.

So core knows a CONVENTION instead of a list. A module joins the status engine by
adding ``app/modules/<key>/status_entities.py`` exposing ``register() -> None``, and
gets picked up with no edit to core. The same shape as the permission registry: a
declaration in the module, discovered generically.

Import failures are logged and skipped rather than raised. One malformed module must
not take down every status graph in the system, and the symptom (its entity missing
from the admin screen) points straight at the cause.
"""
from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

MODULES_PACKAGE = "app.modules"
ENTITY_MODULE = "status_entities"


def _modules_root() -> Path:
    # app/status_engine/discovery.py -> app/ -> app/modules/
    return Path(__file__).resolve().parent.parent / "modules"


def module_keys_with_status_entities() -> List[str]:
    root = _modules_root()
    if not root.is_dir():
        return []
    return sorted(
        child.name
        for child in root.iterdir()
        if child.is_dir()
        and not child.name.startswith("_")
        and child.name != "runtime"
        and (child / f"{ENTITY_MODULE}.py").exists()
    )


def register_module_entities() -> None:
    """Call ``register()`` on every discovered module."""
    for key in module_keys_with_status_entities():
        dotted = f"{MODULES_PACKAGE}.{key}.{ENTITY_MODULE}"
        try:
            module = importlib.import_module(dotted)
            module.register()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Status entity registration failed for %s: %s", dotted, exc)
