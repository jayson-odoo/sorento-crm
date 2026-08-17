"""Defense-in-depth SQLAlchemy listener enforcing lookup bindings on every insert/update."""
from __future__ import annotations
from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import Mapper, object_session

from app.services.lookup_validator import validate_lookup_value


_INSTALLED = False


def register_lookup_write_listeners() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    @event.listens_for(Mapper, "before_insert")
    def _before_insert(mapper, connection, target):
        _check(target, mapper, only_changed=False)

    @event.listens_for(Mapper, "before_update")
    def _before_update(mapper, connection, target):
        # On UPDATE, only validate columns that actually changed in this flush.
        # Re-validating unchanged columns would reject a row whose legacy value
        # predates its lookup binding (e.g. an old complaint's defects_discovered)
        # on any unrelated update — blocking status changes etc. We only enforce
        # the binding on the value being written.
        _check(target, mapper, only_changed=True)


def _check(target, mapper, *, only_changed: bool) -> None:
    # SCHEMA-QUALIFIED, matching how a binding is stored and how eligibility is keyed
    # (``app/services/lookup_eligibility.py``). On the bare name a binding made for core
    # `purchase_orders.status` would also police writes to `projects.purchase_orders`,
    # rejecting values that are valid there - and neither table's own binding would be
    # reliably found. For a default-schema table the key IS the bare name.
    table_name = mapper.local_table.key
    # Avoid recursive triggers when writing into the lookup tables themselves.
    if mapper.local_table.name.startswith("lookup_"):
        return
    sess = object_session(target)
    if sess is None:
        return
    state = sa_inspect(target) if only_changed else None
    for col in mapper.columns:
        if only_changed:
            try:
                if not state.attrs[col.key].history.has_changes():
                    continue
            except KeyError:
                # No mapped attribute for this column key (rare); fall through and validate.
                pass
        value = getattr(target, col.key, None)
        validate_lookup_value(sess, table=table_name, column=col.key, value=value)
