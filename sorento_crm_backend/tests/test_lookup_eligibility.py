import pytest
from app.services.lookup_eligibility import (
    register_lookup_eligible, get_eligibility, all_eligibility, _REGISTRY,
)

class _M:
    __tablename__ = "fake_table"

def setup_function(fn):
    _REGISTRY.clear()

def test_register_and_get():
    register_lookup_eligible(model=_M, column="status",
                             table_label="Fake", column_label="Status")
    e = get_eligibility("fake_table", "status")
    assert e is not None
    assert e.table_label == "Fake" and e.column_label == "Status"
    assert e.data_type == "string" and e.nullable is True

def test_duplicate_raises():
    register_lookup_eligible(model=_M, column="status",
                             table_label="Fake", column_label="Status")
    with pytest.raises(RuntimeError):
        register_lookup_eligible(model=_M, column="status",
                                 table_label="Fake", column_label="Status")

def test_all_eligibility_returns_list():
    register_lookup_eligible(model=_M, column="a",
                             table_label="Fake", column_label="A")
    register_lookup_eligible(model=_M, column="b",
                             table_label="Fake", column_label="B")
    assert len(all_eligibility()) == 2
