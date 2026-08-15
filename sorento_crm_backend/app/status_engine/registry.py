"""Status-entity registry — which tables ride the engine.

Code-side, like the permissions CSV: a table joins the engine by registering here
with a flat ``entity_type`` and a ``status_id`` column. Core registers nothing;
each module appends from its bootstrap. This is what lets the engine offer
"block delete if referenced" and "migrate records" without knowing a single
domain table.

Divergence from ``foundryx-shared-service`` (ADR-0001):

- **``scope_resolver`` replaces ``scope_attr``.** The source names a column on the
  record (``form_id``). That cannot express a project task, whose graph is owned by
  its *project's* template, one hop away. A callable covers both the direct case
  (``lambda p: p.template_id``) and the indirect one, so there is one mechanism
  instead of a column name plus an escape hatch.
- **No ``platform_owned``.** That flag exists for the source's tenant-lifecycle
  entity; sorento registers no tenant entity.
- **No ``scoped`` boolean.** Every entity here is "default graph, optionally
  forked per scope". An entity with no ``scope_resolver`` simply always resolves
  the default.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.lazy_registry import lazy_once


@dataclass(frozen=True)
class StatusEntity:
    """One engine-managed entity.

    ``count_records(db, status_id)`` and ``migrate_records(db, from_id, to_id)``
    back the block-delete-if-referenced and migrate-records flows. Both are
    required: an entity that cannot report its own usage would let an admin delete
    a status out from under live records.
    """

    entity_type: str
    label: str
    module: str
    count_records: Callable[[Session, str], int]
    migrate_records: Callable[[Session, str, str], int]

    # The SQLAlchemy model backing this entity. Required to load a record for
    # transition checks and to expose ``record:<type>`` rule facts.
    model: Optional[Any] = None
    # Attribute holding the status FK on the record.
    status_attr: str = "status_id"
    # Attribute used as the record's display noun in notifications and errors.
    record_label_attr: str = "name"

    # ``scope_resolver(record) -> scope_id | None``. None (or no resolver) means
    # this record resolves the entity's DEFAULT graph.
    scope_resolver: Optional[Callable[[Any], Optional[str]]] = None
    # Display noun for the scope owner ("Template") -- used in admin copy.
    scope_label: str = ""

    # Semantic hints the graph admin surfaces when configuring.
    required_flags: List[str] = field(default_factory=list)

    # ---- rule-engine bridge ----
    # Whitelisted columns exposed as ``record:<type>`` facts. NEVER auto-expose
    # the whole schema. Empty = no record facts registered.
    fact_attrs: Sequence[str] = field(default_factory=tuple)
    # Declarative aggregate whitelist; each entry expands to count + column x op
    # facts plus a child -> owner derived trigger.
    aggregatable_relations: Sequence[Any] = field(default_factory=tuple)

    def scope_for(self, record: Any) -> Optional[str]:
        if self.scope_resolver is None or record is None:
            return None
        return self.scope_resolver(record)

    def load_record(self, db: Session, record_id: str) -> Optional[Any]:
        if self.model is None or record_id is None:
            return None
        return db.query(self.model).filter(self.model.id == record_id).first()


_REGISTRY: Dict[str, StatusEntity] = {}


def register_status_entity(entity: StatusEntity) -> None:
    """Idempotent - modules re-register on every bootstrap.

    When the entity declares ``fact_attrs`` or ``aggregatable_relations``, also
    register a ``record:<type>`` rule fact source so auto-edge conditions can
    reference the record's own fields and child aggregates. A pre-existing source
    wins, so a hand-written richer source is never clobbered.
    """
    _REGISTRY[entity.entity_type] = entity

    if not (entity.fact_attrs or entity.aggregatable_relations):
        return

    from app.rule_engine.registry import get_facts, infer_facts, register_fact_source

    source = f"record:{entity.entity_type}"

    # Relations expand to facts plus a child -> owner trigger. Triggers are always
    # (re)registered because register_derived_trigger is idempotent -- so a
    # re-bootstrap that skips the source rebuild still wires the trigger.
    relation_facts: list = []
    if entity.aggregatable_relations:
        from app.rule_engine.aggregates import expand_relation
        from app.status_engine.derived import register_derived_trigger

        if entity.model is None:
            raise ValueError(
                f"Status entity '{entity.entity_type}' declares "
                "aggregatable_relations but no model."
            )
        for relation in entity.aggregatable_relations:
            facts_r, trigger = expand_relation(entity.entity_type, entity.model, relation)
            relation_facts.extend(facts_r)
            register_derived_trigger(trigger)

    if get_facts([source]):
        return

    facts = (
        list(infer_facts(entity.model, list(entity.fact_attrs), prefix="record"))
        if entity.model is not None and entity.fact_attrs
        else []
    )
    facts.extend(relation_facts)
    register_fact_source(source, f"{entity.label} record", facts)


def get_status_entity(entity_type: str) -> Optional[StatusEntity]:
    _ensure_core()
    return _REGISTRY.get(entity_type)


def list_status_entities() -> List[StatusEntity]:
    _ensure_core()
    return sorted(_REGISTRY.values(), key=lambda e: e.label)


# Module bootstraps that register status entities. Imported for their side
# effect the first time anything reads the registry.
#
# Loaded HERE rather than from each module's router package, which is where the
# Dealer Kit bootstrap was first hooked. A router-mount side effect registers the
# entity in the API process and nowhere else: the RQ worker, a management script
# and a test that touches the registry without building the app would every one
# of them see an unregistered entity, and the symptom is a status graph that
# reports no records using it - which is the answer that makes a status DELETABLE
# out from under live rows.
_MODULE_BOOTSTRAPS = ("app.modules.dealer_kit.bootstrap",)


def _register_core() -> None:
    """Core registers no entities; modules append from their bootstraps.

    The engine is infrastructure: it ships with an empty registry and every
    entity arrives from a module bootstrap. Existing hardcoded status vocabularies
    (complaints, PR/SF, stock inquiries, orders) are deliberately NOT migrated
    here -- they move entity by entity, later (ADR-0001).

    An import failure is swallowed with a warning rather than raised. This runs
    on the first read of the registry, which can be deep inside an unrelated
    request, and one module failing to import must not take down every status
    surface in the system.
    """
    import importlib
    import logging

    for module in _MODULE_BOOTSTRAPS:
        try:
            importlib.import_module(module)
        except Exception:  # pragma: no cover - defensive
            # error, not warning. The consequence is spelled out above: an
            # unregistered entity reports ZERO records in a status, which is the
            # answer that makes the status deletable out from under live rows,
            # and /migrate-records answers {"migrated": 0} while records exist.
            # A warning is the wrong volume for a lie to an admin.
            logging.getLogger(__name__).error(
                "Status entity bootstrap %s failed to import; its entity is now "
                "UNREGISTERED for this process and its status graph will report "
                "no records using any status",
                module,
                exc_info=True,
            )


_ensure_core = lazy_once(_register_core)
