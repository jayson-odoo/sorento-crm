# Lookup Sets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a generic dropdown master-data system: `lookup_sets`/`lookup_options`/`lookup_option_keywords`/`lookup_bindings` tables, code-declared eligibility registry, FE list+detail with binding picker driven by friendly labels, public `/lookup/resolve` for n8n LLM keyword mapping, strict 422 enforcement on writes.

**Architecture:** Bindings stored in DB so admins can attach a set to an eligible (table, column) without typing schema names. Eligibility (which columns are bindable + their friendly labels) is code-declared. SQLAlchemy `before_insert/before_update` listener enforces value ∈ active options. Resolver attempts exact-value → exact-label → exact-keyword → normalized.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + Pydantic v2 (backend); Next.js 15 + TanStack Query + Tailwind + ReUI shell (frontend); pytest + vitest. Spec: `documentation/superpowers/specs/2026-04-30-lookup-sets-design.md`.

---

## File map

**Backend (`sorento_crm_backend/`):**
- Create `alembic/versions/157_lookup_sets.py`
- Create `app/models/lookup.py`
- Create `app/schemas/lookup.py`
- Create `app/services/lookup_eligibility.py`
- Create `app/services/lookup_eligibility_registrations.py`
- Create `app/services/lookup_set_service.py`
- Create `app/services/lookup_option_service.py`
- Create `app/services/lookup_binding_service.py`
- Create `app/services/lookup_resolver.py`
- Create `app/services/lookup_validator.py`
- Create `app/services/lookup_write_listener.py`
- Create `app/api/v1/master_data/lookup_sets.py`
- Create `app/api/v1/master_data/lookup_eligibility.py`
- Create `app/api/v1/lookup.py`
- Modify `app/api/v1/master_data/__init__.py` (mount routers)
- Modify `app/api/v1/__init__.py` (mount `/lookup` cross-cutting router)
- Modify `app/main.py` (import registrations + register listener)
- Modify `app/rbac/permission_registry.py` (add lookup_sets permissions)
- Tests: `tests/test_lookup_eligibility.py`, `tests/test_lookup_resolver.py`, `tests/test_lookup_validator.py`, `tests/test_lookup_sets_api.py`, `tests/test_lookup_bindings_api.py`, `tests/test_lookup_write_enforcement.py`

**Frontend (`sorento_crm_frontend/app/(protected)/master-data-management/lookup-sets/`):**
- Create `page.tsx`
- Create `[id]/page.tsx`
- Create `types/lookup.types.ts`
- Create `services/lookupSetService.ts`
- Create `hooks/useLookupSets.ts`
- Create `components/LookupSetsList.tsx`
- Create `components/LookupSetTable.tsx`
- Create `components/LookupSetFormDialog.tsx`
- Create `components/LookupSetDeleteDialog.tsx`
- Create `components/SetInfoCard.tsx`
- Create `components/OptionsSection.tsx`
- Create `components/OptionFormDialog.tsx`
- Create `components/KeywordChipInput.tsx`
- Create `components/BindingsSection.tsx`
- Create `components/BindingAddDialog.tsx`
- Create `components/TestResolveCard.tsx`
- Test: `__tests__/KeywordChipInput.test.tsx`

**MCP (`sorento_crm_mcp/sorento_crm_mcp/`):**
- Modify `catalog.py` (add 2 tools)
- Test: `tests/test_lookup_tools.py`

---

## Phase 1 - Backend foundations

### Task 1: Permission registry entries

**Files:**
- Modify: `sorento_crm_backend/app/rbac/permission_registry.py`
- Test: `sorento_crm_backend/tests/test_lookup_permissions.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_lookup_permissions.py
from app.rbac.permission_registry import PERMISSION_REGISTRY

def test_lookup_sets_permissions_present():
    slugs = {p["slug"] for p in PERMISSION_REGISTRY}
    assert "master_data.lookup_sets.view" in slugs
    assert "master_data.lookup_sets.add" in slugs
    assert "master_data.lookup_sets.edit" in slugs
    assert "master_data.lookup_sets.delete" in slugs
```

- [ ] **Step 2: Run failing**

```bash
cd sorento_crm_backend && pytest tests/test_lookup_permissions.py -q
```

Expected: 4 missing slug assertions fail.

- [ ] **Step 3: Add permissions**

In `app/rbac/permission_registry.py`, add (after the existing `master_data` block):

```python
PERMISSION_REGISTRY.extend(_crud("master_data", "lookup_sets", "Lookup Sets"))
```

(Find the `master_data.brands` extend line and place this near it.)

- [ ] **Step 4: Run pass**

```bash
pytest tests/test_lookup_permissions.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/rbac/permission_registry.py tests/test_lookup_permissions.py
git commit -m "rbac: register master_data.lookup_sets permissions"
```

---

### Task 2: Alembic migration - tables + indexes + permission sync

**Files:**
- Create: `sorento_crm_backend/alembic/versions/157_lookup_sets.py`

- [ ] **Step 1: Create migration file**

```python
"""Lookup sets, options, option keywords, bindings.

Revision ID: 157_lookup_sets
Revises: 156_respond_contacts_session_vars
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from app.rbac.permission_registry import sync_permissions


revision = "157_lookup_sets"
down_revision = "156_respond_contacts_session_vars"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lookup_sets",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("set_key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
        sa.UniqueConstraint("tenant_id", "set_key", name="uq_lookup_sets_tenant_setkey"),
    )
    op.create_index("ix_lookup_sets_is_active", "lookup_sets", ["is_active"])

    op.create_table(
        "lookup_options",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("set_id", sa.dialects.postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("lookup_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.String(150), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index(
        "uq_lookup_options_set_value_lower",
        "lookup_options",
        ["set_id", sa.text("lower(value)")],
        unique=True,
    )
    op.create_index("ix_lookup_options_set_sort", "lookup_options", ["set_id", "sort_order"])

    op.create_table(
        "lookup_option_keywords",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("option_id", sa.dialects.postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("lookup_options.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword", sa.String(150), nullable=False),
        sa.Column("locale", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("option_id", "keyword", "locale", name="uq_lookup_keywords_unique"),
    )
    op.create_index("ix_lookup_keywords_lower", "lookup_option_keywords", [sa.text("lower(keyword)")])

    op.create_table(
        "lookup_bindings",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("set_id", sa.dialects.postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("lookup_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("column_name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
        sa.UniqueConstraint("tenant_id", "table_name", "column_name", name="uq_lookup_bindings_tenant_col"),
    )
    op.create_index("ix_lookup_bindings_set", "lookup_bindings", ["set_id"])

    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        sync_permissions(session, created_by_user_id=None)
    finally:
        session.close()


def downgrade() -> None:
    op.drop_index("ix_lookup_bindings_set", table_name="lookup_bindings")
    op.drop_table("lookup_bindings")
    op.drop_index("ix_lookup_keywords_lower", table_name="lookup_option_keywords")
    op.drop_table("lookup_option_keywords")
    op.drop_index("ix_lookup_options_set_sort", table_name="lookup_options")
    op.drop_index("uq_lookup_options_set_value_lower", table_name="lookup_options")
    op.drop_table("lookup_options")
    op.drop_index("ix_lookup_sets_is_active", table_name="lookup_sets")
    op.drop_table("lookup_sets")
```

- [ ] **Step 2: Run upgrade**

```bash
cd sorento_crm_backend && alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade 156_... -> 157_lookup_sets`.

- [ ] **Step 3: Verify tables exist**

```bash
psql "$DATABASE_URL" -c "\d lookup_sets" -c "\d lookup_options" -c "\d lookup_option_keywords" -c "\d lookup_bindings"
```

Expected: 4 tables w/ listed columns + indexes.

- [ ] **Step 4: Round-trip downgrade then upgrade**

```bash
alembic downgrade -1 && alembic upgrade head
```

Expected: clean down + up, no errors.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/157_lookup_sets.py
git commit -m "alembic: add lookup_sets/options/keywords/bindings tables"
```

---

### Task 3: SQLAlchemy models

**Files:**
- Create: `sorento_crm_backend/app/models/lookup.py`
- Test: `sorento_crm_backend/tests/test_lookup_models.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_lookup_models.py
import uuid
from app.models.lookup import LookupSet, LookupOption, LookupOptionKeyword, LookupBinding

def test_models_construct(db_session):
    s = LookupSet(id=str(uuid.uuid4()), set_key="region", name="Region")
    db_session.add(s); db_session.flush()
    o = LookupOption(id=str(uuid.uuid4()), set_id=s.id, value="north", label="North")
    db_session.add(o); db_session.flush()
    k = LookupOptionKeyword(id=str(uuid.uuid4()), option_id=o.id, keyword="up north")
    b = LookupBinding(id=str(uuid.uuid4()), set_id=s.id, table_name="customers", column_name="region")
    db_session.add_all([k, b]); db_session.flush()
    assert o.set is s
    assert k.option is o
    assert b.set is s
```

(Use existing pytest `db_session` fixture from `tests/conftest.py`.)

- [ ] **Step 2: Run failing**

```bash
pytest tests/test_lookup_models.py -q
```

Expected: ImportError for `app.models.lookup`.

- [ ] **Step 3: Implement models**

```python
# app/models/lookup.py
"""Generic dropdown master-data models. See documentation/superpowers/specs/2026-04-30-lookup-sets-design.md."""
import uuid
from sqlalchemy import (
    Column, String, Boolean, Integer, Text, ForeignKey, DateTime, Index, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class LookupSet(Base):
    __tablename__ = "lookup_sets"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(UUID(as_uuid=False), nullable=True)
    set_key = Column(String(80), nullable=False)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    options = relationship("LookupOption", back_populates="set", cascade="all, delete-orphan", passive_deletes=True)
    bindings = relationship("LookupBinding", back_populates="set", cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "set_key", name="uq_lookup_sets_tenant_setkey"),
        Index("ix_lookup_sets_is_active", "is_active"),
    )


class LookupOption(Base):
    __tablename__ = "lookup_options"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    set_id = Column(UUID(as_uuid=False), ForeignKey("lookup_sets.id", ondelete="CASCADE"), nullable=False)
    value = Column(String(150), nullable=False)
    label = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    set = relationship("LookupSet", back_populates="options")
    keywords = relationship("LookupOptionKeyword", back_populates="option", cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        Index("uq_lookup_options_set_value_lower", "set_id", text("lower(value)"), unique=True),
        Index("ix_lookup_options_set_sort", "set_id", "sort_order"),
    )


class LookupOptionKeyword(Base):
    __tablename__ = "lookup_option_keywords"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    option_id = Column(UUID(as_uuid=False), ForeignKey("lookup_options.id", ondelete="CASCADE"), nullable=False)
    keyword = Column(String(150), nullable=False)
    locale = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    option = relationship("LookupOption", back_populates="keywords")

    __table_args__ = (
        UniqueConstraint("option_id", "keyword", "locale", name="uq_lookup_keywords_unique"),
        Index("ix_lookup_keywords_lower", text("lower(keyword)")),
    )


class LookupBinding(Base):
    __tablename__ = "lookup_bindings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(UUID(as_uuid=False), nullable=True)
    set_id = Column(UUID(as_uuid=False), ForeignKey("lookup_sets.id", ondelete="CASCADE"), nullable=False)
    table_name = Column(String(100), nullable=False)
    column_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    set = relationship("LookupSet", back_populates="bindings")

    __table_args__ = (
        UniqueConstraint("tenant_id", "table_name", "column_name", name="uq_lookup_bindings_tenant_col"),
        Index("ix_lookup_bindings_set", "set_id"),
    )
```

Add `from app.models.lookup import *` to `app/models/__init__.py` if that file aggregates models (check; if not, do nothing).

- [ ] **Step 4: Run pass**

```bash
pytest tests/test_lookup_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models/lookup.py tests/test_lookup_models.py
git commit -m "models: lookup sets/options/keywords/bindings"
```

---

### Task 4: Pydantic schemas

**Files:**
- Create: `sorento_crm_backend/app/schemas/lookup.py`
- Test: `sorento_crm_backend/tests/test_lookup_schemas.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_lookup_schemas.py
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
```

- [ ] **Step 2: Run failing**

```bash
pytest tests/test_lookup_schemas.py -q
```

Expected: ImportError.

- [ ] **Step 3: Implement schemas**

```python
# app/schemas/lookup.py
from __future__ import annotations
import re
from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


class LookupKeywordIn(BaseModel):
    keyword: str = Field(min_length=1, max_length=150)
    locale: Optional[str] = Field(default=None, max_length=10)


class LookupKeywordOut(LookupKeywordIn):
    id: str
    model_config = ConfigDict(from_attributes=True)


class LookupOptionCreate(BaseModel):
    value: str = Field(min_length=1, max_length=150)
    label: str = Field(min_length=1, max_length=255)
    sort_order: int = 0
    is_active: bool = True
    description: Optional[str] = None
    keywords: List[LookupKeywordIn] = Field(default_factory=list)


class LookupOptionUpdate(BaseModel):
    value: Optional[str] = Field(default=None, min_length=1, max_length=150)
    label: Optional[str] = Field(default=None, min_length=1, max_length=255)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None
    keywords: Optional[List[LookupKeywordIn]] = None  # None = leave unchanged; [] = clear


class LookupOptionResponse(BaseModel):
    id: str
    set_id: str
    value: str
    label: str
    sort_order: int
    is_active: bool
    description: Optional[str]
    keywords: List[LookupKeywordOut]
    created_at: datetime
    updated_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)


class LookupSetCreate(BaseModel):
    set_key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=150)
    description: Optional[str] = None
    is_active: bool = True
    initial_binding: Optional["LookupBindingCreate"] = None  # used by FE create flow

    @field_validator("set_key")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("set_key must match ^[a-z][a-z0-9_]{0,79}$")
        return v


class LookupSetUpdate(BaseModel):
    set_key: Optional[str] = Field(default=None, min_length=1, max_length=80)
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    description: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("set_key")
    @classmethod
    def _slug(cls, v):
        if v is not None and not _SLUG_RE.match(v):
            raise ValueError("set_key must match ^[a-z][a-z0-9_]{0,79}$")
        return v


class LookupSetResponse(BaseModel):
    id: str
    tenant_id: Optional[str]
    set_key: str
    name: str
    description: Optional[str]
    is_active: bool
    option_count: int = 0
    binding_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)


class LookupBindingCreate(BaseModel):
    table_name: str = Field(min_length=1, max_length=100)
    column_name: str = Field(min_length=1, max_length=100)


class LookupBindingResponse(BaseModel):
    id: str
    tenant_id: Optional[str]
    set_id: str
    table_name: str
    column_name: str
    table_label: Optional[str] = None
    column_label: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LookupEligibilityResponse(BaseModel):
    table_name: str
    column_name: str
    table_label: str
    column_label: str
    data_type: Literal["string", "int"]
    nullable: bool
    is_bound: bool = False  # set when ?available filter applied


class LookupResolveRequest(BaseModel):
    set_key: str
    raw: str = Field(min_length=1)
    locale: Optional[str] = None


class LookupResolveResponse(BaseModel):
    value: str
    label: str
    matched_keyword: Optional[str]
    match_type: Literal["exact_value", "exact_label", "exact_keyword", "normalized"]
    score: float


LookupSetCreate.model_rebuild()
```

- [ ] **Step 4: Run pass**

```bash
pytest tests/test_lookup_schemas.py -q
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/schemas/lookup.py tests/test_lookup_schemas.py
git commit -m "schemas: lookup sets/options/keywords/bindings/resolve"
```

---

### Task 5: Eligibility registry module

**Files:**
- Create: `sorento_crm_backend/app/services/lookup_eligibility.py`
- Test: `sorento_crm_backend/tests/test_lookup_eligibility.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_lookup_eligibility.py
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
```

- [ ] **Step 2: Run failing**

```bash
pytest tests/test_lookup_eligibility.py -q
```

Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# app/services/lookup_eligibility.py
"""Code-only registry of bindable (table, column) pairs with friendly labels."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Type, Literal

DataType = Literal["string", "int"]


@dataclass(frozen=True)
class LookupEligibility:
    table_name: str
    column_name: str
    table_label: str
    column_label: str
    data_type: DataType
    nullable: bool


_REGISTRY: dict[tuple[str, str], LookupEligibility] = {}


def register_lookup_eligible(
    *,
    model: Type,
    column: str,
    table_label: str,
    column_label: str,
    data_type: DataType = "string",
    nullable: bool = True,
) -> None:
    table_name = getattr(model, "__tablename__", None)
    if not table_name:
        raise RuntimeError("model must have __tablename__")
    key = (table_name, column)
    if key in _REGISTRY:
        raise RuntimeError(f"Duplicate lookup eligibility for {key}")
    _REGISTRY[key] = LookupEligibility(
        table_name=table_name, column_name=column,
        table_label=table_label, column_label=column_label,
        data_type=data_type, nullable=nullable,
    )


def get_eligibility(table: str, column: str) -> LookupEligibility | None:
    return _REGISTRY.get((table, column))


def all_eligibility() -> list[LookupEligibility]:
    return list(_REGISTRY.values())
```

- [ ] **Step 4: Run pass**

```bash
pytest tests/test_lookup_eligibility.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/lookup_eligibility.py tests/test_lookup_eligibility.py
git commit -m "services: code-only lookup eligibility registry"
```

---

### Task 6: Eligibility registrations file (initially empty + sample)

**Files:**
- Create: `sorento_crm_backend/app/services/lookup_eligibility_registrations.py`
- Modify: `sorento_crm_backend/app/main.py` (import the module so registrations load at startup)

- [ ] **Step 1: Create file**

```python
# app/services/lookup_eligibility_registrations.py
"""Declare bindable (model, column) pairs here. Each must have a friendly label.

Add new entries by importing the model and calling register_lookup_eligible.
Admins cannot edit eligibility; ask a developer.
"""
from app.services.lookup_eligibility import register_lookup_eligible

# Example (kept commented until a real model adopts it):
# from app.models.order import Order
# register_lookup_eligible(
#     model=Order, column="priority",
#     table_label="Order", column_label="Priority",
# )
```

- [ ] **Step 2: Import in app/main.py at startup**

Find the existing block that registers audit listeners (search for `register_audit_listeners`) and add nearby:

```python
# Triggers eligibility registrations side-effects.
import app.services.lookup_eligibility_registrations  # noqa: F401
```

- [ ] **Step 3: Verify app boots**

```bash
uvicorn app.main:app --port 18000 &
sleep 2 && curl -s http://localhost:18000/health && kill %1
```

Expected: 200 health.

- [ ] **Step 4: Commit**

```bash
git add app/services/lookup_eligibility_registrations.py app/main.py
git commit -m "services: load lookup eligibility registrations at startup"
```

---

### Task 7: Lookup set service (CRUD)

**Files:**
- Create: `sorento_crm_backend/app/services/lookup_set_service.py`
- Test: `sorento_crm_backend/tests/test_lookup_set_service.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_lookup_set_service.py
import pytest
from app.schemas.lookup import LookupSetCreate, LookupSetUpdate
from app.services.lookup_set_service import LookupSetService
from app.services.error_handler import AppException

def test_create_and_get(db_session):
    svc = LookupSetService(db_session)
    s = svc.create(LookupSetCreate(set_key="region", name="Region"))
    assert s.set_key == "region"
    got = svc.get(s.id)
    assert got.id == s.id

def test_duplicate_set_key_conflict(db_session):
    svc = LookupSetService(db_session)
    svc.create(LookupSetCreate(set_key="region", name="Region"))
    with pytest.raises(AppException) as e:
        svc.create(LookupSetCreate(set_key="region", name="Region 2"))
    assert e.value.status_code == 409

def test_list_paginated(db_session):
    svc = LookupSetService(db_session)
    for i in range(3):
        svc.create(LookupSetCreate(set_key=f"k{i}", name=f"K{i}"))
    res = svc.list(page=1, limit=2, query=None)
    assert res["pagination"]["total"] == 3
    assert len(res["data"]) == 2

def test_update_and_delete(db_session):
    svc = LookupSetService(db_session)
    s = svc.create(LookupSetCreate(set_key="region", name="Region"))
    svc.update(s.id, LookupSetUpdate(name="Regions"))
    assert svc.get(s.id).name == "Regions"
    svc.delete(s.id)
    with pytest.raises(AppException):
        svc.get(s.id)
```

- [ ] **Step 2: Run failing**

```bash
pytest tests/test_lookup_set_service.py -q
```

Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# app/services/lookup_set_service.py
from __future__ import annotations
import uuid
from typing import Optional
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from app.models.lookup import LookupSet, LookupOption, LookupBinding
from app.schemas.lookup import LookupSetCreate, LookupSetUpdate
from app.services.error_handler import handle_not_found, handle_conflict
from app.modules.runtime.installer import DEFAULT_TENANT_ID


class LookupSetService:
    def __init__(self, db: Session):
        self.db = db

    def _tenant(self) -> Optional[str]:
        # Stubbed; matches existing pattern.
        return None  # store NULL until real tenant resolution lands

    def list(self, *, page: int = 1, limit: int = 50, query: Optional[str] = None):
        q = self.db.query(LookupSet)
        if query:
            q = q.filter(or_(
                LookupSet.set_key.ilike(f"%{query}%"),
                LookupSet.name.ilike(f"%{query}%"),
            ))
        q = q.order_by(LookupSet.name.asc())
        total = q.count()
        offset = (page - 1) * limit
        rows = q.offset(offset).limit(limit).all()
        if not rows:
            return {"data": [], "pagination": {"total": 0, "page": page, "limit": limit}, "empty": True}
        ids = [r.id for r in rows]
        opt_counts = dict(
            self.db.query(LookupOption.set_id, func.count(LookupOption.id))
            .filter(LookupOption.set_id.in_(ids)).group_by(LookupOption.set_id).all()
        )
        bind_counts = dict(
            self.db.query(LookupBinding.set_id, func.count(LookupBinding.id))
            .filter(LookupBinding.set_id.in_(ids)).group_by(LookupBinding.set_id).all()
        )
        data = []
        for r in rows:
            data.append({
                "id": r.id,
                "tenant_id": r.tenant_id,
                "set_key": r.set_key,
                "name": r.name,
                "description": r.description,
                "is_active": r.is_active,
                "option_count": opt_counts.get(r.id, 0),
                "binding_count": bind_counts.get(r.id, 0),
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            })
        return {"data": data, "pagination": {"total": total, "page": page, "limit": limit}, "empty": total == 0}

    def get(self, set_id: str) -> LookupSet:
        s = self.db.query(LookupSet).filter(LookupSet.id == set_id).first()
        if not s:
            raise handle_not_found("LookupSet", set_id)
        return s

    def get_by_key(self, set_key: str) -> LookupSet:
        s = self.db.query(LookupSet).filter(
            LookupSet.set_key == set_key,
            LookupSet.tenant_id.is_(self._tenant()),
        ).first()
        if not s:
            raise handle_not_found("LookupSet", set_key)
        return s

    def create(self, data: LookupSetCreate) -> LookupSet:
        existing = self.db.query(LookupSet).filter(
            LookupSet.set_key == data.set_key,
            LookupSet.tenant_id.is_(self._tenant()),
        ).first()
        if existing:
            raise handle_conflict("Lookup set key already exists.")
        s = LookupSet(
            id=str(uuid.uuid4()),
            tenant_id=self._tenant(),
            set_key=data.set_key,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
        )
        self.db.add(s)
        self.db.flush()  # commit happens in caller after optional binding create
        return s

    def update(self, set_id: str, data: LookupSetUpdate) -> LookupSet:
        s = self.get(set_id)
        update = data.model_dump(exclude_unset=True)
        if "set_key" in update and update["set_key"] != s.set_key:
            clash = self.db.query(LookupSet).filter(
                LookupSet.set_key == update["set_key"],
                LookupSet.tenant_id.is_(self._tenant()),
                LookupSet.id != set_id,
            ).first()
            if clash:
                raise handle_conflict("Lookup set key already exists.")
        for k, v in update.items():
            setattr(s, k, v)
        self.db.commit()
        self.db.refresh(s)
        return s

    def delete(self, set_id: str) -> dict:
        s = self.get(set_id)
        self.db.delete(s)
        self.db.commit()
        return {"message": "Lookup set deleted"}
```

- [ ] **Step 4: Run pass**

```bash
pytest tests/test_lookup_set_service.py -q
```

Expected: PASS (4 tests). If `create` test fails because of missing commit, add `self.db.commit()` at the end of `create` (the LookupSetCreate w/o initial_binding path doesn't need outer transaction).

- [ ] **Step 5: Adjust create + add commit**

Replace `self.db.flush()` with:

```python
        self.db.add(s)
        self.db.commit()
        self.db.refresh(s)
        return s
```

Re-run tests, then commit.

```bash
git add app/services/lookup_set_service.py tests/test_lookup_set_service.py
git commit -m "services: lookup set CRUD service"
```

---

### Task 8: Lookup option service

**Files:**
- Create: `sorento_crm_backend/app/services/lookup_option_service.py`
- Test: `sorento_crm_backend/tests/test_lookup_option_service.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_lookup_option_service.py
import pytest
from app.schemas.lookup import LookupSetCreate, LookupOptionCreate, LookupOptionUpdate, LookupKeywordIn
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
from app.services.error_handler import AppException

def _set(db_session, key="region"):
    return LookupSetService(db_session).create(LookupSetCreate(set_key=key, name="x"))

def test_create_with_keywords(db_session):
    s = _set(db_session)
    svc = LookupOptionService(db_session)
    o = svc.create(s.id, LookupOptionCreate(value="north", label="North",
        keywords=[LookupKeywordIn(keyword="up north"), LookupKeywordIn(keyword="northern")]))
    assert len(o.keywords) == 2

def test_duplicate_value_case_insensitive(db_session):
    s = _set(db_session)
    svc = LookupOptionService(db_session)
    svc.create(s.id, LookupOptionCreate(value="North", label="North"))
    with pytest.raises(AppException) as e:
        svc.create(s.id, LookupOptionCreate(value="north", label="x"))
    assert e.value.status_code == 409

def test_update_replaces_keywords(db_session):
    s = _set(db_session)
    svc = LookupOptionService(db_session)
    o = svc.create(s.id, LookupOptionCreate(value="n", label="N",
        keywords=[LookupKeywordIn(keyword="a")]))
    svc.update(o.id, LookupOptionUpdate(keywords=[LookupKeywordIn(keyword="b")]))
    db_session.refresh(o)
    assert {k.keyword for k in o.keywords} == {"b"}

def test_delete_cascades_keywords(db_session):
    from app.models.lookup import LookupOptionKeyword
    s = _set(db_session)
    svc = LookupOptionService(db_session)
    o = svc.create(s.id, LookupOptionCreate(value="n", label="N",
        keywords=[LookupKeywordIn(keyword="a")]))
    svc.delete(o.id)
    assert db_session.query(LookupOptionKeyword).filter_by(option_id=o.id).count() == 0
```

- [ ] **Step 2: Run failing**

```bash
pytest tests/test_lookup_option_service.py -q
```

Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# app/services/lookup_option_service.py
from __future__ import annotations
import uuid
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.lookup import LookupOption, LookupOptionKeyword
from app.schemas.lookup import LookupOptionCreate, LookupOptionUpdate, LookupKeywordIn
from app.services.error_handler import handle_not_found, handle_conflict


class LookupOptionService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, set_id: str, *, page: int = 1, limit: int = 100):
        q = self.db.query(LookupOption).filter(LookupOption.set_id == set_id).order_by(
            LookupOption.sort_order.asc(), LookupOption.label.asc())
        total = q.count()
        offset = (page - 1) * limit
        rows = q.offset(offset).limit(limit).all()
        return {"data": rows, "pagination": {"total": total, "page": page, "limit": limit},
                "empty": total == 0}

    def get(self, option_id: str) -> LookupOption:
        o = self.db.query(LookupOption).filter(LookupOption.id == option_id).first()
        if not o:
            raise handle_not_found("LookupOption", option_id)
        return o

    def _check_value_unique(self, set_id: str, value: str, exclude_id: Optional[str] = None):
        from sqlalchemy import func
        q = self.db.query(LookupOption).filter(
            LookupOption.set_id == set_id,
            func.lower(LookupOption.value) == value.lower(),
        )
        if exclude_id:
            q = q.filter(LookupOption.id != exclude_id)
        if q.first():
            raise handle_conflict(f"Option value '{value}' already exists in this set")

    def _replace_keywords(self, option: LookupOption, items: List[LookupKeywordIn]):
        self.db.query(LookupOptionKeyword).filter(
            LookupOptionKeyword.option_id == option.id).delete(synchronize_session=False)
        seen = set()
        for kw in items:
            norm = (kw.keyword or "").strip().lower()
            if not norm:
                continue
            key = (norm, kw.locale)
            if key in seen:
                continue
            seen.add(key)
            self.db.add(LookupOptionKeyword(
                id=str(uuid.uuid4()), option_id=option.id,
                keyword=norm, locale=kw.locale,
            ))

    def create(self, set_id: str, data: LookupOptionCreate) -> LookupOption:
        self._check_value_unique(set_id, data.value)
        o = LookupOption(
            id=str(uuid.uuid4()), set_id=set_id,
            value=data.value, label=data.label,
            sort_order=data.sort_order, is_active=data.is_active,
            description=data.description,
        )
        self.db.add(o)
        self.db.flush()
        self._replace_keywords(o, data.keywords)
        self.db.commit()
        self.db.refresh(o)
        return o

    def update(self, option_id: str, data: LookupOptionUpdate) -> LookupOption:
        o = self.get(option_id)
        update = data.model_dump(exclude_unset=True)
        if "value" in update and update["value"].lower() != (o.value or "").lower():
            self._check_value_unique(o.set_id, update["value"], exclude_id=o.id)
        new_keywords = update.pop("keywords", None)
        for k, v in update.items():
            setattr(o, k, v)
        if new_keywords is not None:
            self._replace_keywords(o, [LookupKeywordIn(**k) if isinstance(k, dict) else k for k in new_keywords])
        self.db.commit()
        self.db.refresh(o)
        return o

    def delete(self, option_id: str) -> dict:
        o = self.get(option_id)
        self.db.delete(o)
        self.db.commit()
        return {"message": "Option deleted"}
```

- [ ] **Step 4: Run pass**

```bash
pytest tests/test_lookup_option_service.py -q
```

Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/lookup_option_service.py tests/test_lookup_option_service.py
git commit -m "services: lookup option service with keyword replacement"
```

---

### Task 9: Lookup binding service (eligibility check + existing-data check)

**Files:**
- Create: `sorento_crm_backend/app/services/lookup_binding_service.py`
- Test: `sorento_crm_backend/tests/test_lookup_binding_service.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_lookup_binding_service.py
import pytest
from app.schemas.lookup import LookupSetCreate, LookupOptionCreate, LookupBindingCreate
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
from app.services.lookup_binding_service import LookupBindingService
from app.services.lookup_eligibility import _REGISTRY, register_lookup_eligible
from app.services.error_handler import AppException

class _M:
    __tablename__ = "fake_orders"

def setup_function(_):
    _REGISTRY.clear()
    register_lookup_eligible(model=_M, column="priority",
                             table_label="Order", column_label="Priority")

def test_create_binding(db_session):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="op", name="Order Priority"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(value="high", label="High"))
    svc = LookupBindingService(db_session)
    b = svc.create(s.id, LookupBindingCreate(table_name="fake_orders", column_name="priority"))
    assert b.table_name == "fake_orders"

def test_reject_unknown_eligibility(db_session):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="op", name="x"))
    svc = LookupBindingService(db_session)
    with pytest.raises(AppException) as e:
        svc.create(s.id, LookupBindingCreate(table_name="fake_orders", column_name="ghost"))
    assert e.value.status_code == 422

def test_reject_duplicate_binding(db_session):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="op", name="x"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(value="h", label="H"))
    svc = LookupBindingService(db_session)
    svc.create(s.id, LookupBindingCreate(table_name="fake_orders", column_name="priority"))
    with pytest.raises(AppException) as e:
        svc.create(s.id, LookupBindingCreate(table_name="fake_orders", column_name="priority"))
    assert e.value.status_code == 409
```

- [ ] **Step 2: Run failing**

```bash
pytest tests/test_lookup_binding_service.py -q
```

Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# app/services/lookup_binding_service.py
from __future__ import annotations
import uuid
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.models.lookup import LookupBinding, LookupOption, LookupSet
from app.schemas.lookup import LookupBindingCreate
from app.services.error_handler import handle_not_found, handle_conflict, handle_validation_error
from app.services.lookup_eligibility import get_eligibility


class LookupBindingService:
    def __init__(self, db: Session):
        self.db = db

    def list_for_set(self, set_id: str) -> list[LookupBinding]:
        return self.db.query(LookupBinding).filter(LookupBinding.set_id == set_id).all()

    def create(self, set_id: str, data: LookupBindingCreate) -> LookupBinding:
        s = self.db.query(LookupSet).filter(LookupSet.id == set_id).first()
        if not s:
            raise handle_not_found("LookupSet", set_id)
        elig = get_eligibility(data.table_name, data.column_name)
        if not elig:
            raise handle_validation_error(
                f"({data.table_name}.{data.column_name}) is not registered as a lookup-eligible column."
            )
        existing = self.db.query(LookupBinding).filter(
            LookupBinding.tenant_id.is_(s.tenant_id),
            LookupBinding.table_name == data.table_name,
            LookupBinding.column_name == data.column_name,
        ).first()
        if existing:
            raise handle_conflict(
                f"({data.table_name}.{data.column_name}) is already bound to another set."
            )
        # Verify existing rows in target column only contain values present in this set's options.
        opt_values = {v for (v,) in self.db.query(LookupOption.value).filter(
            LookupOption.set_id == set_id).all()}
        try:
            existing_vals = {row[0] for row in self.db.execute(
                text(f"SELECT DISTINCT {data.column_name} FROM {data.table_name} "
                     f"WHERE {data.column_name} IS NOT NULL")
            ).fetchall()}
        except Exception:
            existing_vals = set()
        unknown = existing_vals - opt_values
        if unknown:
            raise handle_validation_error(
                f"Cannot bind: existing rows have values not in this set's options: "
                f"{sorted(list(unknown))[:10]}"
            )
        b = LookupBinding(
            id=str(uuid.uuid4()), tenant_id=s.tenant_id, set_id=set_id,
            table_name=data.table_name, column_name=data.column_name,
        )
        self.db.add(b)
        self.db.commit()
        self.db.refresh(b)
        return b

    def delete(self, binding_id: str) -> dict:
        b = self.db.query(LookupBinding).filter(LookupBinding.id == binding_id).first()
        if not b:
            raise handle_not_found("LookupBinding", binding_id)
        self.db.delete(b)
        self.db.commit()
        return {"message": "Binding removed"}

    def list_for_table_column(self, tenant_id: Optional[str], table: str, column: str) -> Optional[LookupBinding]:
        return self.db.query(LookupBinding).filter(
            LookupBinding.tenant_id.is_(tenant_id),
            LookupBinding.table_name == table,
            LookupBinding.column_name == column,
        ).first()
```

- [ ] **Step 4: Run pass**

```bash
pytest tests/test_lookup_binding_service.py -q
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/lookup_binding_service.py tests/test_lookup_binding_service.py
git commit -m "services: lookup binding service with eligibility + data-check"
```

---

### Task 10: Resolver service

**Files:**
- Create: `sorento_crm_backend/app/services/lookup_resolver.py`
- Test: `sorento_crm_backend/tests/test_lookup_resolver.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_lookup_resolver.py
import pytest
from app.schemas.lookup import LookupSetCreate, LookupOptionCreate, LookupKeywordIn
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
from app.services.lookup_resolver import LookupResolverService

@pytest.fixture
def seeded(db_session):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="region", name="Region"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(
        value="north", label="North",
        keywords=[LookupKeywordIn(keyword="up north"), LookupKeywordIn(keyword="northern")]
    ))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(
        value="south", label="South"))
    return s

def test_exact_value_match(db_session, seeded):
    r = LookupResolverService(db_session).resolve("region", "north")
    assert r.value == "north" and r.match_type == "exact_value"

def test_exact_label_case_insensitive(db_session, seeded):
    r = LookupResolverService(db_session).resolve("region", "SOUTH")
    assert r.value == "south" and r.match_type == "exact_label"

def test_keyword_match(db_session, seeded):
    r = LookupResolverService(db_session).resolve("region", "Up North")
    assert r.value == "north" and r.match_type == "exact_keyword"

def test_normalized_match(db_session, seeded):
    r = LookupResolverService(db_session).resolve("region", "  northern!  ")
    assert r.value == "north"
    assert r.match_type in ("exact_keyword", "normalized")

def test_unresolved_raises_404(db_session, seeded):
    from app.services.error_handler import AppException
    with pytest.raises(AppException) as e:
        LookupResolverService(db_session).resolve("region", "moon")
    assert e.value.status_code == 404
```

- [ ] **Step 2: Run failing**

```bash
pytest tests/test_lookup_resolver.py -q
```

Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# app/services/lookup_resolver.py
from __future__ import annotations
import re
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.lookup import LookupOption, LookupOptionKeyword, LookupSet
from app.schemas.lookup import LookupResolveResponse
from app.services.error_handler import AppException, handle_not_found
from fastapi import status

_NORM_RE = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    return _NORM_RE.sub(" ", (s or "").lower()).strip()


class LookupResolverService:
    def __init__(self, db: Session):
        self.db = db

    def _set(self, set_key: str) -> LookupSet:
        s = self.db.query(LookupSet).filter(LookupSet.set_key == set_key).first()
        if not s:
            raise handle_not_found("LookupSet", set_key)
        return s

    def resolve(self, set_key: str, raw: str, locale: Optional[str] = None) -> LookupResolveResponse:
        s = self._set(set_key)
        raw_lower = (raw or "").strip().lower()
        if not raw_lower:
            raise AppException(status_code=status.HTTP_404_NOT_FOUND,
                               message=f"Could not resolve '{raw}' in {set_key}",
                               code="lookup_unresolved")

        # 1. exact value (case-insensitive)
        opt = self.db.query(LookupOption).filter(
            LookupOption.set_id == s.id, LookupOption.is_active.is_(True),
            func.lower(LookupOption.value) == raw_lower,
        ).first()
        if opt:
            return LookupResolveResponse(value=opt.value, label=opt.label,
                                         matched_keyword=None, match_type="exact_value", score=1.0)

        # 2. exact label
        opt = self.db.query(LookupOption).filter(
            LookupOption.set_id == s.id, LookupOption.is_active.is_(True),
            func.lower(LookupOption.label) == raw_lower,
        ).first()
        if opt:
            return LookupResolveResponse(value=opt.value, label=opt.label,
                                         matched_keyword=None, match_type="exact_label", score=0.95)

        # 3. exact keyword
        kq = self.db.query(LookupOptionKeyword, LookupOption).join(
            LookupOption, LookupOption.id == LookupOptionKeyword.option_id
        ).filter(
            LookupOption.set_id == s.id, LookupOption.is_active.is_(True),
            func.lower(LookupOptionKeyword.keyword) == raw_lower,
        )
        if locale:
            kq = kq.filter((LookupOptionKeyword.locale == locale) | (LookupOptionKeyword.locale.is_(None)))
        row = kq.first()
        if row:
            kw, opt = row
            return LookupResolveResponse(value=opt.value, label=opt.label,
                                         matched_keyword=kw.keyword, match_type="exact_keyword", score=0.9)

        # 4. normalized
        norm = _norm(raw)
        if norm:
            options = self.db.query(LookupOption).filter(
                LookupOption.set_id == s.id, LookupOption.is_active.is_(True),
            ).all()
            for o in options:
                if _norm(o.value) == norm or _norm(o.label) == norm:
                    return LookupResolveResponse(value=o.value, label=o.label,
                                                 matched_keyword=None, match_type="normalized", score=0.8)
            kws = self.db.query(LookupOptionKeyword, LookupOption).join(
                LookupOption, LookupOption.id == LookupOptionKeyword.option_id
            ).filter(LookupOption.set_id == s.id, LookupOption.is_active.is_(True)).all()
            for k, o in kws:
                if _norm(k.keyword) == norm:
                    return LookupResolveResponse(value=o.value, label=o.label,
                                                 matched_keyword=k.keyword, match_type="normalized", score=0.8)

        raise AppException(status_code=status.HTTP_404_NOT_FOUND,
                           message=f"Could not resolve '{raw}' in {set_key}",
                           code="lookup_unresolved")
```

- [ ] **Step 4: Run pass**

```bash
pytest tests/test_lookup_resolver.py -q
```

Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/lookup_resolver.py tests/test_lookup_resolver.py
git commit -m "services: lookup resolver with 4-stage match algorithm"
```

---

### Task 11: Validator helper + cache

**Files:**
- Create: `sorento_crm_backend/app/services/lookup_validator.py`
- Test: `sorento_crm_backend/tests/test_lookup_validator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_lookup_validator.py
import pytest
from app.schemas.lookup import LookupSetCreate, LookupOptionCreate, LookupBindingCreate
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
from app.services.lookup_binding_service import LookupBindingService
from app.services.lookup_eligibility import _REGISTRY, register_lookup_eligible
from app.services.lookup_validator import validate_lookup_value, _cache_clear
from app.services.error_handler import AppException

class _M:
    __tablename__ = "fake_t"

def setup_function(_):
    _REGISTRY.clear()
    register_lookup_eligible(model=_M, column="status", table_label="F", column_label="S")
    _cache_clear()

def test_value_in_active_options_passes(db_session):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="fs", name="x"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(value="open", label="Open"))
    LookupBindingService(db_session).create(s.id, LookupBindingCreate(table_name="fake_t", column_name="status"))
    validate_lookup_value(db_session, table="fake_t", column="status", value="open")

def test_unknown_value_raises_422(db_session):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="fs", name="x"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(value="open", label="Open"))
    LookupBindingService(db_session).create(s.id, LookupBindingCreate(table_name="fake_t", column_name="status"))
    with pytest.raises(AppException) as e:
        validate_lookup_value(db_session, table="fake_t", column="status", value="closed")
    assert e.value.status_code == 422

def test_unbound_column_skipped(db_session):
    validate_lookup_value(db_session, table="fake_t", column="status", value="anything")
```

- [ ] **Step 2: Run failing**

```bash
pytest tests/test_lookup_validator.py -q
```

Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# app/services/lookup_validator.py
from __future__ import annotations
import time
from typing import Optional
from sqlalchemy.orm import Session
from app.models.lookup import LookupBinding, LookupOption, LookupSet
from app.services.error_handler import AppException
from fastapi import status

_TTL = 60.0  # seconds
_cache: dict[tuple[Optional[str], str, str], tuple[float, Optional[tuple[str, set[str]]]]] = {}


def _cache_clear() -> None:
    _cache.clear()


def _lookup_binding(db: Session, tenant_id: Optional[str], table: str, column: str):
    key = (tenant_id, table, column)
    now = time.time()
    if key in _cache:
        ts, payload = _cache[key]
        if now - ts < _TTL:
            return payload
    b = db.query(LookupBinding).filter(
        LookupBinding.tenant_id.is_(tenant_id),
        LookupBinding.table_name == table,
        LookupBinding.column_name == column,
    ).first()
    if not b:
        _cache[key] = (now, None)
        return None
    set_obj = db.query(LookupSet).filter(LookupSet.id == b.set_id).first()
    values = {v for (v,) in db.query(LookupOption.value).filter(
        LookupOption.set_id == b.set_id, LookupOption.is_active.is_(True)).all()}
    payload = (set_obj.set_key if set_obj else "", values)
    _cache[key] = (now, payload)
    return payload


def validate_lookup_value(db: Session, *, table: str, column: str, value, tenant_id: Optional[str] = None) -> None:
    if value is None:
        return  # NULL handled by nullability of underlying column
    payload = _lookup_binding(db, tenant_id, table, column)
    if payload is None:
        return  # not bound
    set_key, allowed = payload
    if str(value) not in allowed:
        raise AppException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message=f"'{value}' is not a valid value for {set_key}",
            detail={"set_key": set_key, "field": column,
                    "hint": "Call POST /api/v1/lookup/resolve to map a raw keyword."},
            code="invalid_lookup_value",
        )
```

- [ ] **Step 4: Run pass**

```bash
pytest tests/test_lookup_validator.py -q
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/lookup_validator.py tests/test_lookup_validator.py
git commit -m "services: validate_lookup_value helper with 60s in-process cache"
```

---

### Task 12: SQLAlchemy write-listener (defense-in-depth)

**Files:**
- Create: `sorento_crm_backend/app/services/lookup_write_listener.py`
- Modify: `sorento_crm_backend/app/main.py` (register listener at startup)
- Test: `sorento_crm_backend/tests/test_lookup_write_enforcement.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_lookup_write_enforcement.py
import pytest
import uuid
from sqlalchemy import Column, String
from app.database import Base
from app.schemas.lookup import LookupSetCreate, LookupOptionCreate, LookupBindingCreate
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
from app.services.lookup_binding_service import LookupBindingService
from app.services.lookup_eligibility import _REGISTRY, register_lookup_eligible
from app.services.lookup_write_listener import register_lookup_write_listeners
from app.services.lookup_validator import _cache_clear
from app.services.error_handler import AppException


class FakeLookupTarget(Base):
    __tablename__ = "fake_lookup_target"
    id = Column(String, primary_key=True)
    status = Column(String, nullable=True)


@pytest.fixture(autouse=True)
def _reg():
    _REGISTRY.clear()
    register_lookup_eligible(model=FakeLookupTarget, column="status",
                             table_label="Fake", column_label="Status")
    _cache_clear()
    register_lookup_write_listeners()
    yield


def test_listener_rejects_unknown(db_session, _reg):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="fs", name="F"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(value="open", label="Open"))
    LookupBindingService(db_session).create(s.id, LookupBindingCreate(
        table_name="fake_lookup_target", column_name="status"))
    bad = FakeLookupTarget(id=str(uuid.uuid4()), status="closed")
    db_session.add(bad)
    with pytest.raises(AppException) as e:
        db_session.flush()
    assert e.value.status_code == 422
```

(Need migration for `fake_lookup_target` table - for the test, use the SQLAlchemy `create_all` hook in `tests/conftest.py`. If conftest doesn't auto-create per-test tables, register the test model and call `Base.metadata.create_all(bind=engine, tables=[FakeLookupTarget.__table__])` in the fixture.)

- [ ] **Step 2: Run failing**

```bash
pytest tests/test_lookup_write_enforcement.py -q
```

Expected: ImportError on `register_lookup_write_listeners`.

- [ ] **Step 3: Implement**

```python
# app/services/lookup_write_listener.py
"""Defense-in-depth SQLAlchemy listener enforcing lookup bindings on every insert/update."""
from __future__ import annotations
from sqlalchemy import event, inspect
from sqlalchemy.orm import Mapper

from app.database import Base
from app.services.lookup_validator import validate_lookup_value


_INSTALLED = False


def register_lookup_write_listeners() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    @event.listens_for(Mapper, "before_insert")
    def _before_insert(mapper, connection, target):
        _check(connection, target, mapper)

    @event.listens_for(Mapper, "before_update")
    def _before_update(mapper, connection, target):
        _check(connection, target, mapper)


def _check(connection, target, mapper):
    table_name = mapper.local_table.name
    # Avoid recursive triggers when writing into the lookup tables themselves.
    if table_name.startswith("lookup_"):
        return
    from sqlalchemy.orm import Session
    sess = Session(bind=connection)
    try:
        for col in mapper.columns:
            value = getattr(target, col.key, None)
            validate_lookup_value(sess, table=table_name, column=col.key, value=value)
    finally:
        sess.close()
```

- [ ] **Step 4: Register at startup**

In `app/main.py`, after the audit-listener registration:

```python
from app.services.lookup_write_listener import register_lookup_write_listeners
register_lookup_write_listeners()
```

- [ ] **Step 5: Run pass**

```bash
pytest tests/test_lookup_write_enforcement.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/lookup_write_listener.py app/main.py tests/test_lookup_write_enforcement.py
git commit -m "services: SQLAlchemy lookup write enforcement listener"
```

---

### Task 13: Admin CRUD - sets

**Files:**
- Create: `sorento_crm_backend/app/api/v1/master_data/lookup_sets.py`
- Test: `sorento_crm_backend/tests/test_lookup_sets_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_lookup_sets_api.py
def test_create_list_get_update_delete(client_admin):
    r = client_admin.post("/api/v1/master-data/lookup-sets",
                          json={"set_key": "region", "name": "Region"})
    assert r.status_code == 201, r.text
    set_id = r.json()["id"]

    r = client_admin.get("/api/v1/master-data/lookup-sets")
    assert r.status_code == 200
    assert any(d["id"] == set_id for d in r.json()["data"])

    r = client_admin.get(f"/api/v1/master-data/lookup-sets/{set_id}")
    assert r.status_code == 200

    r = client_admin.patch(f"/api/v1/master-data/lookup-sets/{set_id}",
                           json={"name": "Regions"})
    assert r.status_code == 200 and r.json()["name"] == "Regions"

    r = client_admin.delete(f"/api/v1/master-data/lookup-sets/{set_id}")
    assert r.status_code == 200
```

(`client_admin` fixture from `tests/conftest.py`; if not present, use existing admin auth pattern from another `*_api.py` test.)

- [ ] **Step 2: Run failing**

```bash
pytest tests/test_lookup_sets_api.py -q
```

Expected: 404 on every endpoint.

- [ ] **Step 3: Implement**

```python
# app/api/v1/master_data/lookup_sets.py
"""Lookup sets admin API + nested options/bindings + eligibility list."""
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse
from app.schemas.lookup import (
    LookupSetCreate, LookupSetUpdate, LookupSetResponse,
    LookupOptionCreate, LookupOptionUpdate, LookupOptionResponse,
    LookupBindingCreate, LookupBindingResponse,
    LookupEligibilityResponse,
)
from app.services.error_handler import handle_internal_error
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
from app.services.lookup_binding_service import LookupBindingService
from app.services.lookup_eligibility import all_eligibility

router = APIRouter()


# ----- Sets -----

@router.get("/", response_model=ListResponse[LookupSetResponse])
async def list_sets(page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=100),
                    query: Optional[str] = Query(None),
                    current_user=Depends(require_permission_with_api_key("master_data.lookup_sets.view")),
                    db: Session = Depends(get_db)):
    return LookupSetService(db).list(page=page, limit=limit, query=query)


@router.post("/", response_model=LookupSetResponse, status_code=status.HTTP_201_CREATED)
async def create_set(data: LookupSetCreate,
                     current_user=Depends(require_permission("master_data.lookup_sets.add")),
                     db: Session = Depends(get_db)):
    set_obj = LookupSetService(db).create(data)
    if data.initial_binding:
        LookupBindingService(db).create(set_obj.id, data.initial_binding)
    return _set_to_response(db, set_obj)


@router.get("/{set_id}", response_model=LookupSetResponse)
async def get_set(set_id: str,
                  current_user=Depends(require_permission_with_api_key("master_data.lookup_sets.view")),
                  db: Session = Depends(get_db)):
    return _set_to_response(db, LookupSetService(db).get(set_id))


@router.patch("/{set_id}", response_model=LookupSetResponse)
async def update_set(set_id: str, data: LookupSetUpdate,
                     current_user=Depends(require_permission("master_data.lookup_sets.edit")),
                     db: Session = Depends(get_db)):
    return _set_to_response(db, LookupSetService(db).update(set_id, data))


@router.delete("/{set_id}")
async def delete_set(set_id: str,
                     current_user=Depends(require_permission("master_data.lookup_sets.delete")),
                     db: Session = Depends(get_db)):
    return LookupSetService(db).delete(set_id)


def _set_to_response(db: Session, s) -> dict:
    from app.models.lookup import LookupOption, LookupBinding
    opt_count = db.query(LookupOption).filter(LookupOption.set_id == s.id).count()
    bind_count = db.query(LookupBinding).filter(LookupBinding.set_id == s.id).count()
    return {
        "id": s.id, "tenant_id": s.tenant_id, "set_key": s.set_key,
        "name": s.name, "description": s.description, "is_active": s.is_active,
        "option_count": opt_count, "binding_count": bind_count,
        "created_at": s.created_at, "updated_at": s.updated_at,
    }


# ----- Options nested -----

@router.get("/{set_id}/options", response_model=ListResponse[LookupOptionResponse])
async def list_options(set_id: str, page: int = Query(1, ge=1), limit: int = Query(100, ge=1, le=200),
                       current_user=Depends(require_permission_with_api_key("master_data.lookup_sets.view")),
                       db: Session = Depends(get_db)):
    return LookupOptionService(db).list(set_id, page=page, limit=limit)


@router.post("/{set_id}/options", response_model=LookupOptionResponse, status_code=status.HTTP_201_CREATED)
async def create_option(set_id: str, data: LookupOptionCreate,
                        current_user=Depends(require_permission("master_data.lookup_sets.edit")),
                        db: Session = Depends(get_db)):
    return LookupOptionService(db).create(set_id, data)


@router.patch("/{set_id}/options/{option_id}", response_model=LookupOptionResponse)
async def update_option(set_id: str, option_id: str, data: LookupOptionUpdate,
                        current_user=Depends(require_permission("master_data.lookup_sets.edit")),
                        db: Session = Depends(get_db)):
    return LookupOptionService(db).update(option_id, data)


@router.delete("/{set_id}/options/{option_id}")
async def delete_option(set_id: str, option_id: str,
                        current_user=Depends(require_permission("master_data.lookup_sets.edit")),
                        db: Session = Depends(get_db)):
    return LookupOptionService(db).delete(option_id)


# ----- Bindings nested -----

@router.get("/{set_id}/bindings", response_model=list[LookupBindingResponse])
async def list_bindings(set_id: str,
                        current_user=Depends(require_permission_with_api_key("master_data.lookup_sets.view")),
                        db: Session = Depends(get_db)):
    rows = LookupBindingService(db).list_for_set(set_id)
    return [_binding_with_labels(b) for b in rows]


@router.post("/{set_id}/bindings", response_model=LookupBindingResponse, status_code=status.HTTP_201_CREATED)
async def add_binding(set_id: str, data: LookupBindingCreate,
                      current_user=Depends(require_permission("master_data.lookup_sets.edit")),
                      db: Session = Depends(get_db)):
    b = LookupBindingService(db).create(set_id, data)
    return _binding_with_labels(b)


@router.delete("/{set_id}/bindings/{binding_id}")
async def remove_binding(set_id: str, binding_id: str,
                         current_user=Depends(require_permission("master_data.lookup_sets.edit")),
                         db: Session = Depends(get_db)):
    return LookupBindingService(db).delete(binding_id)


def _binding_with_labels(b) -> dict:
    from app.services.lookup_eligibility import get_eligibility
    elig = get_eligibility(b.table_name, b.column_name)
    return {
        "id": b.id, "tenant_id": b.tenant_id, "set_id": b.set_id,
        "table_name": b.table_name, "column_name": b.column_name,
        "table_label": elig.table_label if elig else None,
        "column_label": elig.column_label if elig else None,
        "created_at": b.created_at,
    }
```

- [ ] **Step 4: Mount router**

In `app/api/v1/master_data/__init__.py`:

```python
from app.api.v1.master_data import lookup_sets

# ... existing includes ...
router.include_router(lookup_sets.router, prefix="/lookup-sets", tags=["lookup-sets"])
```

- [ ] **Step 5: Run pass**

```bash
pytest tests/test_lookup_sets_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/v1/master_data/lookup_sets.py app/api/v1/master_data/__init__.py tests/test_lookup_sets_api.py
git commit -m "api: lookup sets admin CRUD + nested options/bindings"
```

---

### Task 14: Eligibility listing endpoint

**Files:**
- Create: `sorento_crm_backend/app/api/v1/master_data/lookup_eligibility.py`
- Modify: `sorento_crm_backend/app/api/v1/master_data/__init__.py`
- Test: `sorento_crm_backend/tests/test_lookup_eligibility_api.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_lookup_eligibility_api.py
from app.services.lookup_eligibility import _REGISTRY, register_lookup_eligible

class _M:
    __tablename__ = "fake_t"

def test_eligibility_endpoint(client_admin):
    _REGISTRY.clear()
    register_lookup_eligible(model=_M, column="status",
                             table_label="Fake", column_label="Status")
    r = client_admin.get("/api/v1/master-data/lookup-eligibility")
    assert r.status_code == 200
    body = r.json()
    assert any(e["table_name"] == "fake_t" and e["column_name"] == "status" for e in body)
```

- [ ] **Step 2: Run failing**

```bash
pytest tests/test_lookup_eligibility_api.py -q
```

Expected: 404.

- [ ] **Step 3: Implement**

```python
# app/api/v1/master_data/lookup_eligibility.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.lookup import LookupEligibilityResponse
from app.services.lookup_eligibility import all_eligibility
from app.services.lookup_binding_service import LookupBindingService

router = APIRouter()


@router.get("/", response_model=list[LookupEligibilityResponse])
async def list_eligibility(available: bool = Query(False),
                           current_user=Depends(require_permission_with_api_key("master_data.lookup_sets.view")),
                           db: Session = Depends(get_db)):
    rows = all_eligibility()
    bound: set[tuple[str, str]] = set()
    if available:
        from app.models.lookup import LookupBinding
        for b in db.query(LookupBinding).all():
            bound.add((b.table_name, b.column_name))
    out = []
    for e in rows:
        is_bound = (e.table_name, e.column_name) in bound
        if available and is_bound:
            continue
        out.append({
            "table_name": e.table_name, "column_name": e.column_name,
            "table_label": e.table_label, "column_label": e.column_label,
            "data_type": e.data_type, "nullable": e.nullable,
            "is_bound": is_bound,
        })
    return out
```

- [ ] **Step 4: Mount router**

In `app/api/v1/master_data/__init__.py`:

```python
from app.api.v1.master_data import lookup_sets, lookup_eligibility

router.include_router(lookup_eligibility.router, prefix="/lookup-eligibility", tags=["lookup-eligibility"])
```

- [ ] **Step 5: Run pass**

```bash
pytest tests/test_lookup_eligibility_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/v1/master_data/lookup_eligibility.py app/api/v1/master_data/__init__.py tests/test_lookup_eligibility_api.py
git commit -m "api: GET /master-data/lookup-eligibility for FE binding picker"
```

---

### Task 15: Public lookup endpoints (`/options`, `/resolve`)

**Files:**
- Create: `sorento_crm_backend/app/api/v1/lookup.py`
- Modify: `sorento_crm_backend/app/api/v1/__init__.py`
- Test: `sorento_crm_backend/tests/test_lookup_public_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_lookup_public_api.py
def test_options_then_resolve(client_admin, client_public):
    # seed
    r = client_admin.post("/api/v1/master-data/lookup-sets",
                          json={"set_key": "region", "name": "Region"})
    set_id = r.json()["id"]
    client_admin.post(f"/api/v1/master-data/lookup-sets/{set_id}/options",
                      json={"value": "north", "label": "North",
                            "keywords": [{"keyword": "up north"}]})

    r = client_public.get("/api/v1/lookup/region/options")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["value"] == "north"
    assert "up north" in body[0]["keywords"]

    r = client_public.post("/api/v1/lookup/resolve",
                           json={"set_key": "region", "raw": "Up North"})
    assert r.status_code == 200
    assert r.json()["value"] == "north"

    r = client_public.post("/api/v1/lookup/resolve",
                           json={"set_key": "region", "raw": "moon"})
    assert r.status_code == 404
```

(`client_public` is the same as `client_admin` if anonymous public access not allowed; reuse view permission.)

- [ ] **Step 2: Run failing**

```bash
pytest tests/test_lookup_public_api.py -q
```

Expected: 404 on `/api/v1/lookup/...`.

- [ ] **Step 3: Implement**

```python
# app/api/v1/lookup.py
"""Public lookup endpoints - used by FE dropdowns and n8n MCP tools."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.lookup import LookupResolveRequest, LookupResolveResponse
from app.services.lookup_resolver import LookupResolverService
from app.services.lookup_set_service import LookupSetService
from app.models.lookup import LookupOption, LookupOptionKeyword

router = APIRouter()


@router.get("/{set_key}/options")
async def list_options_public(
    set_key: str,
    include_inactive: bool = Query(False),
    current_user=Depends(require_permission_with_api_key("master_data.lookup_sets.view")),
    db: Session = Depends(get_db),
):
    s = LookupSetService(db).get_by_key(set_key)
    q = db.query(LookupOption).filter(LookupOption.set_id == s.id)
    if not include_inactive:
        q = q.filter(LookupOption.is_active.is_(True))
    rows = q.order_by(LookupOption.sort_order.asc(), LookupOption.label.asc()).all()
    out = []
    for o in rows:
        kws = db.query(LookupOptionKeyword).filter(LookupOptionKeyword.option_id == o.id).all()
        out.append({
            "value": o.value, "label": o.label,
            "keywords": [k.keyword for k in kws],
            "is_active": o.is_active,
        })
    return out


@router.post("/resolve", response_model=LookupResolveResponse)
async def resolve(
    body: LookupResolveRequest,
    current_user=Depends(require_permission_with_api_key("master_data.lookup_sets.view")),
    db: Session = Depends(get_db),
):
    return LookupResolverService(db).resolve(body.set_key, body.raw, body.locale)
```

- [ ] **Step 4: Mount in v1 root**

In `app/api/v1/__init__.py`, add after master_data inclusion:

```python
from app.api.v1 import lookup as lookup_router
api_router.include_router(lookup_router.router, prefix="/lookup", tags=["lookup"])
```

(Match the actual router name used in that file - adjust if it's `router` instead of `api_router`.)

- [ ] **Step 5: Run pass**

```bash
pytest tests/test_lookup_public_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/v1/lookup.py app/api/v1/__init__.py tests/test_lookup_public_api.py
git commit -m "api: public /lookup/{set_key}/options and /lookup/resolve"
```

---

## Phase 2 - Frontend

### Task 16: TypeScript types

**Files:**
- Create: `sorento_crm_frontend/app/(protected)/master-data-management/lookup-sets/types/lookup.types.ts`

- [ ] **Step 1: Create file**

```ts
// types/lookup.types.ts
export type MatchType = 'exact_value' | 'exact_label' | 'exact_keyword' | 'normalized';

export interface LookupKeyword {
  id?: string;
  keyword: string;
  locale?: string | null;
}

export interface LookupOption {
  id: string;
  set_id: string;
  value: string;
  label: string;
  sort_order: number;
  is_active: boolean;
  description: string | null;
  keywords: LookupKeyword[];
  created_at: string;
  updated_at: string | null;
}

export interface LookupOptionFormData {
  value: string;
  label: string;
  sort_order: number;
  is_active: boolean;
  description?: string;
  keywords: LookupKeyword[];
}

export interface LookupSet {
  id: string;
  tenant_id: string | null;
  set_key: string;
  name: string;
  description: string | null;
  is_active: boolean;
  option_count: number;
  binding_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface LookupSetFormData {
  set_key: string;
  name: string;
  description?: string;
  is_active: boolean;
  initial_binding?: { table_name: string; column_name: string };
}

export interface LookupBinding {
  id: string;
  tenant_id: string | null;
  set_id: string;
  table_name: string;
  column_name: string;
  table_label: string | null;
  column_label: string | null;
  created_at: string;
}

export interface LookupEligibility {
  table_name: string;
  column_name: string;
  table_label: string;
  column_label: string;
  data_type: 'string' | 'int';
  nullable: boolean;
  is_bound: boolean;
}

export interface LookupResolveResponse {
  value: string;
  label: string;
  matched_keyword: string | null;
  match_type: MatchType;
  score: number;
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd sorento_crm_frontend && npx tsc --noEmit -p tsconfig.json | grep -i "lookup-sets" || echo "ok"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add app/\(protected\)/master-data-management/lookup-sets/types/lookup.types.ts
git commit -m "fe: lookup sets types"
```

---

### Task 17: Service module

**Files:**
- Create: `sorento_crm_frontend/app/(protected)/master-data-management/lookup-sets/services/lookupSetService.ts`

- [ ] **Step 1: Create file**

```ts
// services/lookupSetService.ts
import { apiFetch } from '@/lib/api';
import { extractApiError, buildDataGridParams } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  LookupSet, LookupSetFormData,
  LookupOption, LookupOptionFormData,
  LookupBinding, LookupEligibility, LookupResolveResponse,
} from '../types/lookup.types';

const BASE = '/api/v1/master-data/lookup-sets';

export async function listLookupSets(p: DataGridApiFetchParams): Promise<DataGridApiResponse<LookupSet>> {
  const qs = buildDataGridParams(p);
  const r = await apiFetch(`${BASE}?${qs}`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load lookup sets'));
  return r.json();
}

export async function getLookupSet(id: string): Promise<LookupSet> {
  const r = await apiFetch(`${BASE}/${id}`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load lookup set'));
  return r.json();
}

export async function createLookupSet(data: LookupSetFormData): Promise<LookupSet> {
  const r = await apiFetch(BASE, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to create lookup set'));
  return r.json();
}

export async function updateLookupSet(id: string, data: Partial<LookupSetFormData>): Promise<LookupSet> {
  const r = await apiFetch(`${BASE}/${id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to update lookup set'));
  return r.json();
}

export async function deleteLookupSet(id: string): Promise<void> {
  const r = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to delete lookup set'));
}

// Options
export async function listOptions(setId: string): Promise<LookupOption[]> {
  const r = await apiFetch(`${BASE}/${setId}/options?page=1&limit=200`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load options'));
  return (await r.json()).data;
}
export async function createOption(setId: string, data: LookupOptionFormData) {
  const r = await apiFetch(`${BASE}/${setId}/options`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to create option'));
  return r.json();
}
export async function updateOption(setId: string, optionId: string, data: Partial<LookupOptionFormData>) {
  const r = await apiFetch(`${BASE}/${setId}/options/${optionId}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to update option'));
  return r.json();
}
export async function deleteOption(setId: string, optionId: string) {
  const r = await apiFetch(`${BASE}/${setId}/options/${optionId}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to delete option'));
}

// Bindings
export async function listBindings(setId: string): Promise<LookupBinding[]> {
  const r = await apiFetch(`${BASE}/${setId}/bindings`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load bindings'));
  return r.json();
}
export async function addBinding(setId: string, table_name: string, column_name: string): Promise<LookupBinding> {
  const r = await apiFetch(`${BASE}/${setId}/bindings`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ table_name, column_name }),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to add binding'));
  return r.json();
}
export async function removeBinding(setId: string, bindingId: string) {
  const r = await apiFetch(`${BASE}/${setId}/bindings/${bindingId}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to remove binding'));
}

// Eligibility
export async function listEligibility(available = false): Promise<LookupEligibility[]> {
  const r = await apiFetch(`/api/v1/master-data/lookup-eligibility${available ? '?available=true' : ''}`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load eligibility'));
  return r.json();
}

// Resolve
export async function resolveLookup(set_key: string, raw: string, locale?: string): Promise<LookupResolveResponse> {
  const r = await apiFetch('/api/v1/lookup/resolve', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ set_key, raw, locale }),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to resolve'));
  return r.json();
}
```

- [ ] **Step 2: Compile check**

```bash
npx tsc --noEmit -p tsconfig.json | grep "lookup-sets/services" || echo ok
```

- [ ] **Step 3: Commit**

```bash
git add app/\(protected\)/master-data-management/lookup-sets/services/lookupSetService.ts
git commit -m "fe: lookup sets service module"
```

---

### Task 18: Hooks

**Files:**
- Create: `sorento_crm_frontend/app/(protected)/master-data-management/lookup-sets/hooks/useLookupSets.ts`

- [ ] **Step 1: Create file**

```ts
// hooks/useLookupSets.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  listLookupSets, getLookupSet, createLookupSet, updateLookupSet, deleteLookupSet,
  listOptions, createOption, updateOption, deleteOption,
  listBindings, addBinding, removeBinding,
  listEligibility, resolveLookup,
} from '../services/lookupSetService';
import type { LookupSetFormData, LookupOptionFormData } from '../types/lookup.types';

const KEY = 'lookup-sets';

export function useLookupSets(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: [KEY, params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => listLookupSets(params),
    staleTime: 30_000,
  });
}

export function useLookupSet(id: string | null) {
  return useQuery({
    queryKey: [KEY, id],
    queryFn: () => getLookupSet(id!),
    enabled: !!id,
  });
}

export function useCreateLookupSet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: LookupSetFormData) => createLookupSet(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: [KEY] }); toast.success('Lookup set created'); },
    onError: (e: Error) => toast.error(e.message),
  });
}
export function useUpdateLookupSet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<LookupSetFormData> }) => updateLookupSet(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: [KEY] }); toast.success('Updated'); },
    onError: (e: Error) => toast.error(e.message),
  });
}
export function useDeleteLookupSet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteLookupSet(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: [KEY] }); toast.success('Deleted'); },
    onError: (e: Error) => toast.error(e.message),
  });
}

// Options
export function useOptions(setId: string | null) {
  return useQuery({
    queryKey: [KEY, setId, 'options'],
    queryFn: () => listOptions(setId!),
    enabled: !!setId,
  });
}
export function useCreateOption(setId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: LookupOptionFormData) => createOption(setId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: [KEY, setId, 'options'] }); toast.success('Option added'); },
    onError: (e: Error) => toast.error(e.message),
  });
}
export function useUpdateOption(setId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<LookupOptionFormData> }) => updateOption(setId, id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: [KEY, setId, 'options'] }); toast.success('Option updated'); },
    onError: (e: Error) => toast.error(e.message),
  });
}
export function useDeleteOption(setId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteOption(setId, id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: [KEY, setId, 'options'] }); toast.success('Option deleted'); },
    onError: (e: Error) => toast.error(e.message),
  });
}

// Bindings
export function useBindings(setId: string | null) {
  return useQuery({
    queryKey: [KEY, setId, 'bindings'],
    queryFn: () => listBindings(setId!),
    enabled: !!setId,
  });
}
export function useAddBinding(setId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ table_name, column_name }: { table_name: string; column_name: string }) =>
      addBinding(setId, table_name, column_name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [KEY, setId, 'bindings'] });
      qc.invalidateQueries({ queryKey: ['lookup-eligibility'] });
      toast.success('Binding added');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
export function useRemoveBinding(setId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (bindingId: string) => removeBinding(setId, bindingId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [KEY, setId, 'bindings'] });
      qc.invalidateQueries({ queryKey: ['lookup-eligibility'] });
      toast.success('Binding removed');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// Eligibility
export function useEligibility(available = false) {
  return useQuery({
    queryKey: ['lookup-eligibility', available],
    queryFn: () => listEligibility(available),
  });
}

// Resolve
export function useResolve() {
  return useMutation({
    mutationFn: ({ set_key, raw, locale }: { set_key: string; raw: string; locale?: string }) =>
      resolveLookup(set_key, raw, locale),
  });
}
```

- [ ] **Step 2: Compile check**

```bash
npx tsc --noEmit -p tsconfig.json | grep lookup-sets || echo ok
```

- [ ] **Step 3: Commit**

```bash
git add app/\(protected\)/master-data-management/lookup-sets/hooks/useLookupSets.ts
git commit -m "fe: lookup sets hooks"
```

---

### Task 19: List page + table + delete dialog

**Files:**
- Create: `page.tsx`, `components/LookupSetsList.tsx`, `components/LookupSetTable.tsx`, `components/LookupSetDeleteDialog.tsx`

- [ ] **Step 1: Create page.tsx (mirrors brands)**

```tsx
// app/(protected)/master-data-management/lookup-sets/page.tsx
import { Metadata } from 'next';
import {
  Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import LookupSetsList from './components/LookupSetsList';

export const metadata: Metadata = {
  title: 'Lookup Sets',
  description: 'Configure dropdown master data, options, and keyword mappings.',
};

export default function LookupSetsPage() {
  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Lookup Sets</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem><BreadcrumbLink href="/">Home</BreadcrumbLink></BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem><BreadcrumbPage>Master Data</BreadcrumbPage></BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
        </Toolbar>
      </Container>
      <Container><LookupSetsList /></Container>
    </>
  );
}
```

- [ ] **Step 2: Create LookupSetsList.tsx**

```tsx
// components/LookupSetsList.tsx
'use client';
import { useState } from 'react';
import { Plus, Search } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { useLookupSets } from '../hooks/useLookupSets';
import LookupSetTable from './LookupSetTable';
import LookupSetFormDialog from './LookupSetFormDialog';
import LookupSetDeleteDialog from './LookupSetDeleteDialog';
import type { LookupSet } from '../types/lookup.types';

export default function LookupSetsList() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | undefined>();
  const [deleting, setDeleting] = useState<LookupSet | null>(null);

  const { data, isLoading } = useLookupSets({
    pageIndex: 0, pageSize: 100,
    sorting: [{ id: 'name', desc: false }], searchQuery,
  });

  return (
    <>
      <Card>
        <CardHeader className="flex-row items-center justify-between flex-wrap gap-2.5">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input placeholder="Search lookup sets..." value={searchQuery}
                   onChange={(e) => setSearchQuery(e.target.value)} className="ps-9 w-64" />
          </div>
          <Button onClick={() => { setEditingId(undefined); setFormOpen(true); }}>
            <Plus className="size-4" /> Add lookup set
          </Button>
        </CardHeader>
        <CardTable>
          {isLoading ? <div className="py-12 text-center text-muted-foreground">Loading…</div> :
            <ScrollArea>
              <LookupSetTable
                rows={data?.data ?? []}
                onView={(s) => router.push(`/master-data-management/lookup-sets/${s.id}`)}
                onEdit={(s) => { setEditingId(s.id); setFormOpen(true); }}
                onDelete={(s) => setDeleting(s)}
              />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>}
        </CardTable>
      </Card>
      <LookupSetFormDialog open={formOpen} onOpenChange={setFormOpen} setId={editingId} />
      {deleting && (
        <LookupSetDeleteDialog
          open={!!deleting} closeDialog={() => setDeleting(null)} set={deleting}
        />
      )}
    </>
  );
}
```

- [ ] **Step 3: Create LookupSetTable.tsx**

```tsx
// components/LookupSetTable.tsx
'use client';
import { Eye, Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { LookupSet } from '../types/lookup.types';

export default function LookupSetTable({
  rows, onView, onEdit, onDelete,
}: {
  rows: LookupSet[];
  onView: (s: LookupSet) => void;
  onEdit: (s: LookupSet) => void;
  onDelete: (s: LookupSet) => void;
}) {
  if (!rows.length) {
    return <div className="py-12 text-center text-muted-foreground">
      No lookup sets yet. Click "Add lookup set" to create one.
    </div>;
  }
  return (
    <table className="table-fixed w-full">
      <thead>
        <tr className="text-left text-sm border-b">
          <th className="px-4 py-3 w-48">Set key</th>
          <th className="px-4 py-3">Name</th>
          <th className="px-4 py-3 w-24">Options</th>
          <th className="px-4 py-3 w-24">Bindings</th>
          <th className="px-4 py-3 w-20">Active</th>
          <th className="px-4 py-3 w-32 text-right">Actions</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((s) => (
          <tr key={s.id} className="border-b hover:bg-muted/40">
            <td className="px-4 py-2 font-mono text-sm">{s.set_key}</td>
            <td className="px-4 py-2">{s.name}</td>
            <td className="px-4 py-2">{s.option_count}</td>
            <td className="px-4 py-2">{s.binding_count}</td>
            <td className="px-4 py-2">{s.is_active ? 'Yes' : 'No'}</td>
            <td className="px-4 py-2 text-right">
              <Button size="icon" variant="ghost" onClick={() => onView(s)}><Eye className="size-4" /></Button>
              <Button size="icon" variant="ghost" onClick={() => onEdit(s)}><Pencil className="size-4" /></Button>
              <Button size="icon" variant="ghost" onClick={() => onDelete(s)}><Trash2 className="size-4" /></Button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 4: Create LookupSetDeleteDialog.tsx**

```tsx
// components/LookupSetDeleteDialog.tsx
'use client';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useDeleteLookupSet } from '../hooks/useLookupSets';
import type { LookupSet } from '../types/lookup.types';

export default function LookupSetDeleteDialog({
  open, closeDialog, set,
}: { open: boolean; closeDialog: () => void; set: LookupSet }) {
  const m = useDeleteLookupSet();
  return (
    <ConfirmDeleteDialog
      open={open}
      onOpenChange={(o) => { if (!o) closeDialog(); }}
      title="Delete lookup set?"
      description={`This will permanently delete "${set.name}" along with its options, keywords, and bindings. This action cannot be undone.`}
      onConfirm={async () => { await m.mutateAsync(set.id); closeDialog(); }}
    />
  );
}
```

- [ ] **Step 5: Verify dev server renders**

```bash
npm run dev
# Open http://localhost:3000/master-data-management/lookup-sets - empty list with "Add lookup set" button.
```

- [ ] **Step 6: Commit**

```bash
git add app/\(protected\)/master-data-management/lookup-sets/page.tsx \
        app/\(protected\)/master-data-management/lookup-sets/components/LookupSetsList.tsx \
        app/\(protected\)/master-data-management/lookup-sets/components/LookupSetTable.tsx \
        app/\(protected\)/master-data-management/lookup-sets/components/LookupSetDeleteDialog.tsx
git commit -m "fe: lookup sets list page + table + delete dialog"
```

---

### Task 20: Set form dialog (binding-driven create flow)

**Files:**
- Create: `components/LookupSetFormDialog.tsx`

- [ ] **Step 1: Create file**

```tsx
// components/LookupSetFormDialog.tsx
'use client';
import { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useCreateLookupSet, useUpdateLookupSet, useLookupSet, useEligibility } from '../hooks/useLookupSets';

const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '');

export default function LookupSetFormDialog({
  open, onOpenChange, setId,
}: { open: boolean; onOpenChange: (o: boolean) => void; setId?: string }) {
  const isEdit = !!setId;
  const { data: existing } = useLookupSet(setId ?? null);
  const create = useCreateLookupSet();
  const update = useUpdateLookupSet();
  const { data: eligibility } = useEligibility(true);

  const [setKey, setSetKey] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [skipBinding, setSkipBinding] = useState(false);
  const [tableName, setTableName] = useState('');
  const [columnName, setColumnName] = useState('');

  useEffect(() => {
    if (existing && isEdit) {
      setSetKey(existing.set_key); setName(existing.name);
      setDescription(existing.description ?? ''); setIsActive(existing.is_active);
    } else if (!isEdit) {
      setSetKey(''); setName(''); setDescription(''); setIsActive(true);
      setSkipBinding(false); setTableName(''); setColumnName('');
    }
  }, [existing, isEdit, open]);

  const tables = useMemo(() => {
    const seen = new Map<string, string>();
    (eligibility ?? []).forEach((e) => seen.set(e.table_name, e.table_label));
    return Array.from(seen.entries()).map(([table_name, table_label]) => ({ table_name, table_label }));
  }, [eligibility]);
  const columns = useMemo(
    () => (eligibility ?? []).filter((e) => e.table_name === tableName && !e.is_bound),
    [eligibility, tableName],
  );

  // Auto-suggest set_key + name from selected (table, column)
  useEffect(() => {
    if (isEdit) return;
    if (!tableName || !columnName) return;
    const elig = (eligibility ?? []).find((e) => e.table_name === tableName && e.column_name === columnName);
    if (!elig) return;
    if (!setKey) setSetKey(slugify(`${tableName}_${columnName}`));
    if (!name) setName(`${elig.table_label} - ${elig.column_label}`);
  }, [tableName, columnName, eligibility, isEdit, setKey, name]);

  async function submit() {
    if (isEdit) {
      await update.mutateAsync({ id: setId!, data: { set_key: setKey, name, description, is_active: isActive } });
    } else {
      const payload: any = { set_key: setKey, name, description, is_active: isActive };
      if (!skipBinding && tableName && columnName) {
        payload.initial_binding = { table_name: tableName, column_name: columnName };
      }
      await create.mutateAsync(payload);
    }
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit lookup set' : 'Add lookup set'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {!isEdit && (
            <>
              <div className="text-sm font-medium">Where will this dropdown appear?</div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Table</Label>
                  <Select value={tableName} onValueChange={(v) => { setTableName(v); setColumnName(''); }}
                          disabled={skipBinding}>
                    <SelectTrigger><SelectValue placeholder="Select table" /></SelectTrigger>
                    <SelectContent>
                      {tables.map((t) => (
                        <SelectItem key={t.table_name} value={t.table_name}>{t.table_label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Column</Label>
                  <Select value={columnName} onValueChange={setColumnName} disabled={skipBinding || !tableName}>
                    <SelectTrigger><SelectValue placeholder="Select column" /></SelectTrigger>
                    <SelectContent>
                      {columns.map((c) => (
                        <SelectItem key={c.column_name} value={c.column_name}>{c.column_label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={skipBinding} onCheckedChange={setSkipBinding} />
                <Label>Skip - create unbound set</Label>
              </div>
            </>
          )}
          <div>
            <Label>Set key</Label>
            <Input value={setKey} onChange={(e) => setSetKey(e.target.value)}
                   placeholder="lowercase_with_underscores" />
          </div>
          <div>
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <Label>Description</Label>
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="flex items-center gap-2">
            <Switch checked={isActive} onCheckedChange={setIsActive} />
            <Label>Active</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={!setKey || !name}>
            {isEdit ? 'Save' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Smoke test in browser**

```bash
npm run dev
# Click "Add lookup set" → confirm Table/Column dropdowns populate, set_key auto-fills, save creates row.
```

- [ ] **Step 3: Commit**

```bash
git add app/\(protected\)/master-data-management/lookup-sets/components/LookupSetFormDialog.tsx
git commit -m "fe: lookup set form dialog with binding-driven create flow"
```

---

### Task 21: Detail page shell + Set info card

**Files:**
- Create: `[id]/page.tsx`, `components/SetInfoCard.tsx`

- [ ] **Step 1: Create [id]/page.tsx**

```tsx
// app/(protected)/master-data-management/lookup-sets/[id]/page.tsx
'use client';
import { use } from 'react';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import { useLookupSet } from '../hooks/useLookupSets';
import SetInfoCard from '../components/SetInfoCard';
import OptionsSection from '../components/OptionsSection';
import BindingsSection from '../components/BindingsSection';
import TestResolveCard from '../components/TestResolveCard';

export default function LookupSetDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: set, isLoading } = useLookupSet(id);
  if (isLoading) return <Container>Loading…</Container>;
  if (!set) return <Container>Not found.</Container>;
  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>{set.name}</ToolbarTitle>
          </ToolbarHeading>
        </Toolbar>
      </Container>
      <Container className="space-y-6">
        <SetInfoCard set={set} />
        <OptionsSection setId={id} />
        <BindingsSection setId={id} />
        <TestResolveCard setKey={set.set_key} />
      </Container>
    </>
  );
}
```

- [ ] **Step 2: Create SetInfoCard.tsx**

```tsx
// components/SetInfoCard.tsx
'use client';
import { useState } from 'react';
import { Pencil } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import LookupSetFormDialog from './LookupSetFormDialog';
import type { LookupSet } from '../types/lookup.types';

export default function SetInfoCard({ set }: { set: LookupSet }) {
  const [editing, setEditing] = useState(false);
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Set info</CardTitle>
        <Button variant="outline" size="sm" onClick={() => setEditing(true)}><Pencil className="size-4" /> Edit</Button>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        <div><span className="text-muted-foreground">Key:</span> <span className="font-mono">{set.set_key}</span></div>
        <div><span className="text-muted-foreground">Active:</span> {set.is_active ? 'Yes' : 'No'}</div>
        {set.description && <div className="text-muted-foreground">{set.description}</div>}
      </CardContent>
      <LookupSetFormDialog open={editing} onOpenChange={setEditing} setId={set.id} />
    </Card>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add app/\(protected\)/master-data-management/lookup-sets/\[id\]/page.tsx \
        app/\(protected\)/master-data-management/lookup-sets/components/SetInfoCard.tsx
git commit -m "fe: lookup set detail page shell + info card"
```

(OptionsSection / BindingsSection / TestResolveCard live in next tasks; the detail page imports them now and will compile after those are written.)

---

### Task 22: Keyword chip input + vitest

**Files:**
- Create: `components/KeywordChipInput.tsx`, `__tests__/KeywordChipInput.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// __tests__/KeywordChipInput.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import KeywordChipInput from '../components/KeywordChipInput';

describe('KeywordChipInput', () => {
  it('adds chip on Enter', () => {
    const onChange = vi.fn();
    render(<KeywordChipInput value={[]} onChange={onChange} />);
    const input = screen.getByPlaceholderText('Add keyword and press Enter');
    fireEvent.change(input, { target: { value: 'urgent' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith([{ keyword: 'urgent', locale: null }]);
  });

  it('removes chip on click', () => {
    const onChange = vi.fn();
    render(<KeywordChipInput value={[{ keyword: 'a', locale: null }]} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText('Remove a'));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});
```

- [ ] **Step 2: Run failing**

```bash
npx vitest run app/\(protected\)/master-data-management/lookup-sets/__tests__/KeywordChipInput.test.tsx
```

Expected: Cannot find module.

- [ ] **Step 3: Implement**

```tsx
// components/KeywordChipInput.tsx
'use client';
import { useState } from 'react';
import { X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import type { LookupKeyword } from '../types/lookup.types';

export default function KeywordChipInput({
  value, onChange,
}: { value: LookupKeyword[]; onChange: (v: LookupKeyword[]) => void }) {
  const [draft, setDraft] = useState('');
  return (
    <div className="border rounded-md px-2 py-1.5 flex flex-wrap gap-1.5">
      {value.map((k, i) => (
        <span key={`${k.keyword}-${i}`} className="inline-flex items-center gap-1 bg-muted text-sm rounded-full px-2 py-0.5">
          {k.keyword}
          <button
            aria-label={`Remove ${k.keyword}`}
            type="button"
            onClick={() => onChange(value.filter((_, j) => j !== i))}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <Input
        className="border-0 shadow-none flex-1 min-w-32"
        placeholder="Add keyword and press Enter"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && draft.trim()) {
            e.preventDefault();
            onChange([...value, { keyword: draft.trim(), locale: null }]);
            setDraft('');
          }
        }}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run pass**

```bash
npx vitest run app/\(protected\)/master-data-management/lookup-sets/__tests__/KeywordChipInput.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/\(protected\)/master-data-management/lookup-sets/components/KeywordChipInput.tsx \
        app/\(protected\)/master-data-management/lookup-sets/__tests__/KeywordChipInput.test.tsx
git commit -m "fe: keyword chip input component + tests"
```

---

### Task 23: Options section + option form dialog

**Files:**
- Create: `components/OptionsSection.tsx`, `components/OptionFormDialog.tsx`

- [ ] **Step 1: Create OptionFormDialog.tsx**

```tsx
// components/OptionFormDialog.tsx
'use client';
import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import KeywordChipInput from './KeywordChipInput';
import { useCreateOption, useUpdateOption } from '../hooks/useLookupSets';
import type { LookupOption } from '../types/lookup.types';

export default function OptionFormDialog({
  open, onOpenChange, setId, editing,
}: {
  open: boolean; onOpenChange: (o: boolean) => void;
  setId: string; editing?: LookupOption | null;
}) {
  const create = useCreateOption(setId);
  const update = useUpdateOption(setId);
  const [value, setValue] = useState('');
  const [label, setLabel] = useState('');
  const [sortOrder, setSortOrder] = useState(0);
  const [isActive, setIsActive] = useState(true);
  const [description, setDescription] = useState('');
  const [keywords, setKeywords] = useState<{ keyword: string; locale: string | null }[]>([]);

  useEffect(() => {
    if (editing) {
      setValue(editing.value); setLabel(editing.label);
      setSortOrder(editing.sort_order); setIsActive(editing.is_active);
      setDescription(editing.description ?? '');
      setKeywords(editing.keywords.map((k) => ({ keyword: k.keyword, locale: k.locale ?? null })));
    } else {
      setValue(''); setLabel(''); setSortOrder(0); setIsActive(true);
      setDescription(''); setKeywords([]);
    }
  }, [editing, open]);

  async function submit() {
    const payload = { value, label, sort_order: sortOrder, is_active: isActive, description, keywords };
    if (editing) await update.mutateAsync({ id: editing.id, data: payload });
    else await create.mutateAsync(payload);
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? 'Edit option' : 'Add option'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div><Label>Value (canonical)</Label><Input value={value} onChange={(e) => setValue(e.target.value)} /></div>
          <div><Label>Label (display)</Label><Input value={label} onChange={(e) => setLabel(e.target.value)} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Sort order</Label>
              <Input type="number" value={sortOrder} onChange={(e) => setSortOrder(Number(e.target.value))} /></div>
            <div className="flex items-end gap-2">
              <Switch checked={isActive} onCheckedChange={setIsActive} />
              <Label>Active</Label>
            </div>
          </div>
          <div><Label>Description</Label><Textarea value={description} onChange={(e) => setDescription(e.target.value)} /></div>
          <div><Label>Keywords (synonyms for n8n / resolve)</Label>
            <KeywordChipInput value={keywords} onChange={setKeywords} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={!value || !label}>{editing ? 'Save' : 'Add'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Create OptionsSection.tsx**

```tsx
// components/OptionsSection.tsx
'use client';
import { useState } from 'react';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useOptions, useDeleteOption } from '../hooks/useLookupSets';
import OptionFormDialog from './OptionFormDialog';
import type { LookupOption } from '../types/lookup.types';

export default function OptionsSection({ setId }: { setId: string }) {
  const { data: options, isLoading } = useOptions(setId);
  const del = useDeleteOption(setId);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<LookupOption | null>(null);
  const [deleting, setDeleting] = useState<LookupOption | null>(null);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Options</CardTitle>
        <Button onClick={() => { setEditing(null); setFormOpen(true); }}>
          <Plus className="size-4" /> Add option
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading ? <div>Loading…</div> :
          (options ?? []).length === 0 ? (
            <div className="py-6 text-muted-foreground text-sm">
              No options yet. Click "Add option" to populate this dropdown.
            </div>
          ) : (
            <table className="table-fixed w-full text-sm">
              <thead>
                <tr className="text-left border-b">
                  <th className="px-3 py-2 w-48">Value</th>
                  <th className="px-3 py-2">Label</th>
                  <th className="px-3 py-2 w-20">Sort</th>
                  <th className="px-3 py-2 w-20">Active</th>
                  <th className="px-3 py-2 w-24">Keywords</th>
                  <th className="px-3 py-2 w-28 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {options!.map((o) => (
                  <tr key={o.id} className="border-b">
                    <td className="px-3 py-2 font-mono">{o.value}</td>
                    <td className="px-3 py-2">{o.label}</td>
                    <td className="px-3 py-2">{o.sort_order}</td>
                    <td className="px-3 py-2">{o.is_active ? 'Yes' : 'No'}</td>
                    <td className="px-3 py-2">{o.keywords.length}</td>
                    <td className="px-3 py-2 text-right">
                      <Button size="icon" variant="ghost"
                              onClick={() => { setEditing(o); setFormOpen(true); }}>
                        <Pencil className="size-4" />
                      </Button>
                      <Button size="icon" variant="ghost" onClick={() => setDeleting(o)}>
                        <Trash2 className="size-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </CardContent>
      <OptionFormDialog open={formOpen} onOpenChange={setFormOpen} setId={setId} editing={editing} />
      {deleting && (
        <ConfirmDeleteDialog
          open={!!deleting}
          onOpenChange={(o) => { if (!o) setDeleting(null); }}
          title="Delete option?"
          description={`This will permanently delete "${deleting.label}". This action cannot be undone.`}
          onConfirm={async () => { await del.mutateAsync(deleting.id); setDeleting(null); }}
        />
      )}
    </Card>
  );
}
```

- [ ] **Step 3: Smoke test**

```bash
npm run dev
# Visit /master-data-management/lookup-sets/{id} → add option, add keywords, edit, delete.
```

- [ ] **Step 4: Commit**

```bash
git add app/\(protected\)/master-data-management/lookup-sets/components/OptionFormDialog.tsx \
        app/\(protected\)/master-data-management/lookup-sets/components/OptionsSection.tsx
git commit -m "fe: lookup options section + form dialog with keyword chips"
```

---

### Task 24: Bindings section + add dialog

**Files:**
- Create: `components/BindingsSection.tsx`, `components/BindingAddDialog.tsx`

- [ ] **Step 1: Create BindingAddDialog.tsx**

```tsx
// components/BindingAddDialog.tsx
'use client';
import { useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useEligibility, useAddBinding } from '../hooks/useLookupSets';

export default function BindingAddDialog({
  open, onOpenChange, setId,
}: { open: boolean; onOpenChange: (o: boolean) => void; setId: string }) {
  const { data: eligibility } = useEligibility(true);
  const add = useAddBinding(setId);
  const [tableName, setTableName] = useState('');
  const [columnName, setColumnName] = useState('');
  const tables = useMemo(() => {
    const m = new Map<string, string>();
    (eligibility ?? []).forEach((e) => m.set(e.table_name, e.table_label));
    return Array.from(m.entries()).map(([table_name, table_label]) => ({ table_name, table_label }));
  }, [eligibility]);
  const columns = (eligibility ?? []).filter((e) => e.table_name === tableName && !e.is_bound);

  async function submit() {
    await add.mutateAsync({ table_name: tableName, column_name: columnName });
    onOpenChange(false);
    setTableName(''); setColumnName('');
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Add binding</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Table</Label>
            <Select value={tableName} onValueChange={(v) => { setTableName(v); setColumnName(''); }}>
              <SelectTrigger><SelectValue placeholder="Select table" /></SelectTrigger>
              <SelectContent>
                {tables.map((t) => <SelectItem key={t.table_name} value={t.table_name}>{t.table_label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div><Label>Column</Label>
            <Select value={columnName} onValueChange={setColumnName} disabled={!tableName}>
              <SelectTrigger><SelectValue placeholder="Select column" /></SelectTrigger>
              <SelectContent>
                {columns.map((c) => <SelectItem key={c.column_name} value={c.column_name}>{c.column_label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={!tableName || !columnName}>Bind</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Create BindingsSection.tsx**

```tsx
// components/BindingsSection.tsx
'use client';
import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useBindings, useRemoveBinding } from '../hooks/useLookupSets';
import BindingAddDialog from './BindingAddDialog';
import type { LookupBinding } from '../types/lookup.types';

export default function BindingsSection({ setId }: { setId: string }) {
  const { data: bindings, isLoading } = useBindings(setId);
  const remove = useRemoveBinding(setId);
  const [addOpen, setAddOpen] = useState(false);
  const [deleting, setDeleting] = useState<LookupBinding | null>(null);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Bindings</CardTitle>
        <Button onClick={() => setAddOpen(true)}><Plus className="size-4" /> Add binding</Button>
      </CardHeader>
      <CardContent>
        {isLoading ? <div>Loading…</div> :
          (bindings ?? []).length === 0 ? (
            <div className="py-6 text-muted-foreground text-sm">
              Not yet bound to any field. Click "Add binding" to choose where this dropdown appears.
            </div>
          ) : (
            <table className="table-fixed w-full text-sm">
              <thead>
                <tr className="text-left border-b">
                  <th className="px-3 py-2">Table</th>
                  <th className="px-3 py-2">Column</th>
                  <th className="px-3 py-2 w-24 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {bindings!.map((b) => (
                  <tr key={b.id} className="border-b">
                    <td className="px-3 py-2">{b.table_label ?? b.table_name}</td>
                    <td className="px-3 py-2">{b.column_label ?? b.column_name}</td>
                    <td className="px-3 py-2 text-right">
                      <Button size="icon" variant="ghost" onClick={() => setDeleting(b)}>
                        <Trash2 className="size-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </CardContent>
      <BindingAddDialog open={addOpen} onOpenChange={setAddOpen} setId={setId} />
      {deleting && (
        <ConfirmDeleteDialog
          open={!!deleting}
          onOpenChange={(o) => { if (!o) setDeleting(null); }}
          title="Remove binding?"
          description={`This will unbind ${deleting.table_label ?? deleting.table_name} → ${deleting.column_label ?? deleting.column_name}. Existing data is unaffected.`}
          onConfirm={async () => { await remove.mutateAsync(deleting.id); setDeleting(null); }}
        />
      )}
    </Card>
  );
}
```

- [ ] **Step 3: Smoke test**

```bash
npm run dev
# Detail page → "Add binding" → confirm dropdowns + bind succeeds.
```

- [ ] **Step 4: Commit**

```bash
git add app/\(protected\)/master-data-management/lookup-sets/components/BindingAddDialog.tsx \
        app/\(protected\)/master-data-management/lookup-sets/components/BindingsSection.tsx
git commit -m "fe: bindings section + add binding dialog"
```

---

### Task 25: Test resolve card

**Files:**
- Create: `components/TestResolveCard.tsx`

- [ ] **Step 1: Create file**

```tsx
// components/TestResolveCard.tsx
'use client';
import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useResolve } from '../hooks/useLookupSets';
import type { LookupResolveResponse } from '../types/lookup.types';

export default function TestResolveCard({ setKey }: { setKey: string }) {
  const [raw, setRaw] = useState('');
  const [result, setResult] = useState<LookupResolveResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const m = useResolve();

  async function go() {
    setErr(null); setResult(null);
    try {
      const r = await m.mutateAsync({ set_key: setKey, raw });
      setResult(r);
    } catch (e: any) { setErr(e.message || 'Unresolved'); }
  }

  return (
    <Card>
      <CardHeader><CardTitle>Test resolve</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div className="text-sm text-muted-foreground">
          Try a raw keyword and see how the backend resolves it for n8n.
        </div>
        <div className="flex gap-2">
          <Input value={raw} onChange={(e) => setRaw(e.target.value)} placeholder="e.g. urgent now" />
          <Button onClick={go} disabled={!raw}>Resolve</Button>
        </div>
        {result && (
          <div className="text-sm font-mono bg-muted rounded-md p-2">
            value=<b>{result.value}</b> · label={result.label} ·
            match_type={result.match_type} · score={result.score.toFixed(2)}
            {result.matched_keyword ? <> · keyword=<i>{result.matched_keyword}</i></> : null}
          </div>
        )}
        {err && <div className="text-sm text-destructive">{err}</div>}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Smoke test**

```bash
npm run dev
# Detail page → enter "Up North" → confirm result shows value=north match_type=exact_keyword.
```

- [ ] **Step 3: Commit**

```bash
git add app/\(protected\)/master-data-management/lookup-sets/components/TestResolveCard.tsx
git commit -m "fe: test-resolve card on lookup set detail page"
```

---

## Phase 3 - MCP

### Task 26: Add MCP catalog entries for lookup tools

**Files:**
- Modify: `sorento_crm_mcp/sorento_crm_mcp/catalog.py`
- Test: `sorento_crm_mcp/tests/test_lookup_tools.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_lookup_tools.py
from sorento_crm_mcp.catalog import CATALOG

def test_catalog_includes_lookup_tools():
    names = {t.name for t in CATALOG}
    assert "crm_lookup_options" in names
    assert "crm_lookup_resolve" in names
```

- [ ] **Step 2: Run failing**

```bash
cd sorento_crm_mcp && pytest tests/test_lookup_tools.py -q
```

Expected: AssertionError.

- [ ] **Step 3: Add tool specs in catalog.py**

Insert into `CATALOG` tuple, after the master-data block:

```python
    ToolSpec(
        "crm_lookup_options",
        "List active options + keywords for a dropdown configured in CRM. "
        "Use this to learn the canonical values and synonyms before sending a write. "
        "Returns [{value,label,keywords:[..],is_active}].",
        "/api/v1/lookup/{set_key}/options",
        path_params=("set_key",),
        query_params=("include_inactive",),
        module="master_data",
    ),
    ToolSpec(
        "crm_lookup_resolve",
        "Resolve a raw user keyword into the canonical option value for a set. "
        "Body: {set_key, raw, locale?}. Returns {value,label,matched_keyword,match_type,score} or 404. "
        "Use this whenever a user gives a free-text value for a CRM dropdown field - translate first, "
        "then send the canonical value to the matching write API.",
        "/api/v1/lookup/resolve",
        method="POST",
        body_params=("set_key", "raw", "locale"),
        module="master_data",
    ),
```

- [ ] **Step 4: Run pass**

```bash
pytest tests/test_lookup_tools.py -q
pytest tests/test_catalog_compile.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sorento_crm_mcp/sorento_crm_mcp/catalog.py sorento_crm_mcp/tests/test_lookup_tools.py
git commit -m "mcp: expose lookup options + resolve tools to n8n"
```

---

## Phase 4 - Integration smoke

### Task 27: End-to-end happy path

**Files:** none (manual run)

- [ ] **Step 1: Backend up + migration applied**

```bash
cd sorento_crm_backend && alembic upgrade head && uvicorn app.main:app --port 8000 &
```

- [ ] **Step 2: Register an eligibility entry for an existing model**

Edit `app/services/lookup_eligibility_registrations.py` to add a real binding (pick any existing string column). Example:

```python
from app.models.complaints import Complaint
register_lookup_eligible(
    model=Complaint, column="priority",
    table_label="Complaint", column_label="Priority",
)
```

Restart server.

- [ ] **Step 3: FE create flow**

Open `/master-data-management/lookup-sets`, click Add lookup set. Confirm:
- Table dropdown shows "Complaint".
- Column dropdown shows "Priority".
- set_key auto-fills `complaints_priority`.
- Save creates row + binding. Detail page opens.

- [ ] **Step 4: Add options + keywords**

Add 3 options (high/medium/low) with keywords (`urgent`, `asap` for high; `whenever` for low). Save.

- [ ] **Step 5: Test resolve**

In detail page Test resolve card, enter `URGENT` → confirm `value=high, match_type=exact_keyword`.

- [ ] **Step 6: Negative write test**

```bash
curl -X POST http://localhost:8000/api/v1/complaints \
  -H "Content-Type: application/json" -H "Authorization: Bearer <token>" \
  -d '{"...all required fields...","priority":"urgent"}'
```

Expected: 422 with `code=invalid_lookup_value`.

- [ ] **Step 7: Resolve then write**

```bash
curl -X POST http://localhost:8000/api/v1/lookup/resolve \
  -H "Content-Type: application/json" -H "Authorization: Bearer <token>" \
  -d '{"set_key":"complaints_priority","raw":"urgent"}'
# returns {"value":"high",...}
# now use "high" in the write - succeeds.
```

- [ ] **Step 8: Roll back the smoke registration if not desired**

Remove the `register_lookup_eligible(...)` line you added in Step 2 (or keep if it's a real adoption).

- [ ] **Step 9: Commit any kept registrations**

```bash
git add app/services/lookup_eligibility_registrations.py
git commit -m "registrations: complaint priority adopts lookup set"
```

(Skip this commit if Step 8 reverted everything.)

---

## Self-Review checklist (run after writing this plan)

- All four DB tables created in Task 2 → ✅ models referenced in Task 3, services in 7-12.
- Eligibility code-only + bindings DB-stored decision → enforced in Task 9 (eligibility check inside binding service) and Task 14 (eligibility GET endpoint).
- Strict 422 enforcement → Task 11 validator + Task 12 listener; both invoked from real write path because listener registers globally on `Mapper.before_insert/before_update`.
- Tenant scope → `tenant_id` columns present (Task 2/3); service stub returns `None` and queries use `tenant_id.is_(None)` consistently (Task 7/9/11). When real tenant lookup lands, only `LookupSetService._tenant()` and the validator's `tenant_id` arg need updating.
- FE binding-driven create → Task 20 reads eligibility, auto-fills set_key/name; Task 24 mirrors the picker for adding bindings later.
- n8n integration → Task 15 public endpoints; Task 26 MCP catalog entries.
- Permission slugs match between Task 1 (`add/edit/delete/view`) and Task 13 endpoints.
- All "TODO/TBD" placeholders absent - code is concrete.
