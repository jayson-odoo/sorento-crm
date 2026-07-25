import uuid

import pytest

from app.models.lookup import LookupSet, LookupOption, LookupOptionKeyword, LookupBinding
from tests._pg_fixture import blank_session


@pytest.fixture
def db_session():
    """Empty Postgres session over the full real schema.

    Previously an in-memory SQLite database carrying only the four lookup
    tables, because the wider registry uses PostgreSQL-only types. The blank
    schema removes that constraint -- every table is present, with the real
    DDL -- so the relationships here are exercised against production types
    and real foreign keys rather than SQLite's approximations.
    """
    with blank_session() as session:
        yield session


def test_models_construct(db_session):
    s = LookupSet(id=str(uuid.uuid4()), set_key="region", name="Region")
    db_session.add(s)
    db_session.flush()
    o = LookupOption(id=str(uuid.uuid4()), set_id=s.id, value="north", label="North")
    db_session.add(o)
    db_session.flush()
    k = LookupOptionKeyword(id=str(uuid.uuid4()), option_id=o.id, keyword="up north")
    b = LookupBinding(id=str(uuid.uuid4()), set_id=s.id, table_name="customers", column_name="region")
    db_session.add_all([k, b])
    db_session.flush()
    assert o.set is s
    assert k.option is o
    assert b.set is s
