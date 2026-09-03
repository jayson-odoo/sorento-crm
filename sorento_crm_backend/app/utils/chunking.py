"""Split a sequence into fixed-size pieces, for callers building a chunked `IN (...)` query.

One definition rather than the same six-line generator re-typed per importer: `order_service`
and `outstanding_import_service` both had their own copy, and a copy that merely agrees today
is exactly how the three ever drift - one gets a tighter bound-parameter ceiling than the
others and nobody notices until a file large enough to matter proves it.
"""
from __future__ import annotations

from typing import Iterable, Iterator, TypeVar

T = TypeVar("T")

#: The default a caller gets by leaving `size` unset - comfortably under Postgres' own
#: bound-parameter ceiling even when every element expands to several columns worth of
#: placeholders, and small enough that no single statement approaches the 1,000-parameter
#: mark a prod trace once shipped for want of any chunking at all.
DEFAULT_CHUNK_SIZE = 500


def chunked(items: Iterable[T], size: int = DEFAULT_CHUNK_SIZE) -> Iterator[list[T]]:
    """Yield `items` in pieces of at most `size`, preserving order.

    `items` is materialised to a list first, so a generator or a set can be passed directly -
    a caller building a chunked `.in_(...)` clause almost always has one of those, not
    already a list.
    """
    values = list(items)
    for i in range(0, len(values), size):
        yield values[i:i + size]
