"""Defense-in-depth SQLAlchemy listener enforcing lookup bindings on every insert/update."""
from __future__ import annotations
from sqlalchemy import event
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
        _check(target, mapper)

    @event.listens_for(Mapper, "before_update")
    def _before_update(mapper, connection, target):
        _check(target, mapper)


def _check(target, mapper) -> None:
    table_name = mapper.local_table.name
    # Avoid recursive triggers when writing into the lookup tables themselves.
    if table_name.startswith("lookup_"):
        return
    sess = object_session(target)
    if sess is None:
        return
    for col in mapper.columns:
        value = getattr(target, col.key, None)
        validate_lookup_value(sess, table=table_name, column=col.key, value=value)
