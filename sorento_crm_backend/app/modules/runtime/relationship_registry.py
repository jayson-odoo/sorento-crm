"""Deferred inverse-relationship registry.

Modules whose models declare ``relationship("X", back_populates="...")`` against
a class owned by another module register the matching inverse here instead of
patching the upstream class directly. After every module's ``models.py`` has
imported, ``apply_pending()`` walks the queue, resolves each target class from
the live SQLAlchemy registry, and adds the property via ``mapper.add_property``.

Why deferred: at module import time, target classes may not be loaded yet.
Resolving lazily — and against the live registry rather than via direct imports
— avoids the silent ``except ImportError`` skip that produced the original
``Mapper has no property 'leads'`` failure (spec §1, §6).

Design contract:
- ``register_inverse`` is idempotent in effect: if the target class already
  declares the named property, the registered factory is skipped (lets legacy
  codebases that ship reciprocals natively keep working).
- A missing target class raises ``RuntimeError`` from ``apply_pending``. Loud,
  not silent.
- ``apply_pending`` drains the queue and may be called repeatedly. The upload
  pipeline calls it after importing a freshly-extracted module so newly-queued
  inverses attach before the post-upload ``configure_mappers()``.

See docs/superpowers/specs/2026-04-30-module-golden-standard-design.md §6.
"""
from __future__ import annotations

from typing import Any, Callable, List, Tuple

# (target_class_name, attr_name, factory) — factory returns a fresh
# RelationshipProperty when called.
_pending: List[Tuple[str, str, Callable[[], Any]]] = []


def register_inverse(
    target_class_name: str,
    attr_name: str,
    factory: Callable[[], Any],
) -> None:
    """Queue an inverse relationship to be added on the next ``apply_pending`` call.

    Parameters
    ----------
    target_class_name:
        Class name (string, not import) of the upstream class that should grow
        the inverse property. Resolved against ``base.registry.mappers`` at
        ``apply_pending`` time.
    attr_name:
        Attribute name to add on the target class (e.g. ``"commercial_leads"``).
    factory:
        Zero-arg callable returning a fresh ``relationship(...)`` property.
        Factory form (not a value) avoids constructing the relationship before
        the dependent module's models are registered.
    """
    _pending.append((target_class_name, attr_name, factory))


def apply_pending(base_registry: Any) -> None:
    """Apply every queued inverse to its target class.

    Drains the queue. Subsequent registrations require another call to
    ``apply_pending`` — the upload pipeline does this after importing a freshly
    extracted module so the new module's reciprocals attach before
    ``configure_mappers()`` runs.

    Parameters
    ----------
    base_registry:
        SQLAlchemy ``DeclarativeBase.registry``. Mappers are walked via
        ``base_registry.mappers`` so we don't depend on the private
        ``_class_registry`` map.
    """
    if not _pending:
        return
    by_name = {m.class_.__name__: m.class_ for m in base_registry.mappers}
    failures: list[str] = []
    queued = list(_pending)
    _pending.clear()
    for target_name, attr, factory in queued:
        cls = by_name.get(target_name)
        if cls is None:
            failures.append(
                f"target class '{target_name}' (for property '{attr}') not registered "
                "in SQLAlchemy declarative base"
            )
            continue
        # `_props` is a private SQLAlchemy attr but stable across 1.4 / 2.x and avoids
        # triggering mapper configuration mid-discovery (which `inspect(cls).attrs` would).
        if attr in cls.__mapper__._props:
            continue
        cls.__mapper__.add_property(attr, factory())
    if failures:
        raise RuntimeError("relationship_registry.apply_pending: " + "; ".join(failures))
