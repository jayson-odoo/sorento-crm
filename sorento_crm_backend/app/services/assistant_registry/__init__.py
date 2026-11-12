"""The assistant registry: every `<module>.py` in this package adds its `EntityDef`s to `ENTITIES`.

Core code: it must not import `app.services.chatbot` (`tests/chatbot/test_import_boundary.py`).
"""
from __future__ import annotations

import importlib
import pkgutil

from app.services.assistant_registry.types import EntityDef, FieldDef

ENTITIES: dict[str, EntityDef] = {}

_NOT_MODULES = {"types", "query", "computed"}


def register(*entities: EntityDef) -> None:
    for entity in entities:
        if entity.key in ENTITIES:
            raise ValueError(f"assistant registry: entity {entity.key!r} is registered twice")
        ENTITIES[entity.key] = entity


def _load() -> None:
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if info.name not in _NOT_MODULES and not info.name.startswith("_"):
            importlib.import_module(f"{__name__}.{info.name}")


_load()

__all__ = ["ENTITIES", "EntityDef", "FieldDef", "register"]
