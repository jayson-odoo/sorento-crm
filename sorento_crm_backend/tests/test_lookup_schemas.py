import pytest
from pydantic import ValidationError
from app.schemas.lookup import LookupSetCreate, LookupOptionCreate, LookupBindingCreate

def test_set_key_slug_validated():
    LookupSetCreate(set_key="order_priority", name="Order Priority")
    with pytest.raises(ValidationError):
        LookupSetCreate(set_key="Order Priority!", name="x")

def test_option_keywords_default_empty():
    o = LookupOptionCreate(value="north", label="North")
    assert o.keywords == []

def test_binding_requires_table_column():
    with pytest.raises(ValidationError):
        LookupBindingCreate(table_name="", column_name="region")
