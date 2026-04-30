"""Schema-driven (table, column) eligibility for lookup bindings.

Source of truth: SQLAlchemy ``Base.metadata`` introspection. Any string/integer
column on a non-system table is bindable. The legacy ``register_lookup_eligible``
hook is preserved as an in-memory override (also used by tests): when ``_REGISTRY``
is non-empty it short-circuits the metadata path.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Type, Literal, Optional

DataType = Literal["string", "int"]


@dataclass(frozen=True)
class LookupEligibility:
    table_name: str
    column_name: str
    table_label: str
    column_label: str
    data_type: DataType
    nullable: bool


# Override / test layer. When non-empty, all_eligibility / get_eligibility return
# values from this dict only; metadata introspection is bypassed.
_REGISTRY: dict[tuple[str, str], LookupEligibility] = {}


# ---------------------------------------------------------------------------
# Metadata-driven eligibility
# ---------------------------------------------------------------------------

# Tables whose columns must never appear as user-bindable lookup targets.
_BLACKLIST_TABLE_PREFIXES: tuple[str, ...] = (
    "lookup_",
    "alembic_",
    "audit_",
    "embedding",
    "scheduled_",
    "import_",
    "integration_",
    "password_",
    "email_verification",
    "ai_assistant_",
    "app_modules",
    "sessions",
    "accounts",
    "verification_token",
    "verificationtokens",
    "jobs",
    "user_role",
    "user_permission",
    "user_team",
    "permission_",
    "role_",
    "chat_",
    "entity_conversation",
    "notification",
    "respond_",
    "running_number",
    "numbering_",
    "calendar",
    "workflow_stage",
    "tenant_",
    "list_query_",
)

_BLACKLIST_TABLE_NAMES: frozenset[str] = frozenset({
    "users",
    "tenants",
    "session",
    "account",
    "verification_request",
})

_BLACKLIST_COLUMN_NAMES: frozenset[str] = frozenset({
    "id", "tenant_id", "created_at", "updated_at", "deleted_at",
    "created_by", "updated_by", "password", "password_hash",
    "hashed_password", "token", "refresh_token", "access_token",
    "session_token", "secret", "salt", "api_key", "external_id",
    "email", "phone", "phone_number", "mobile", "mobile_number",
    "url", "website", "logo_url", "image_url", "file_url",
    "set_key", "slug", "uuid",
})

_BLACKLIST_COLUMN_SUFFIXES: tuple[str, ...] = (
    "_id", "_at", "_url", "_path", "_hash", "_token", "_secret", "_uuid",
)


def _humanize(name: str) -> str:
    return " ".join(p.capitalize() for p in name.split("_") if p)


def _is_blacklisted_table(name: str) -> bool:
    if name in _BLACKLIST_TABLE_NAMES:
        return True
    return any(name.startswith(p) for p in _BLACKLIST_TABLE_PREFIXES)


def _classify_column(col) -> Optional[DataType]:
    """Map a SQLAlchemy column to ``string`` / ``int`` / None (not eligible)."""
    try:
        t = type(col.type).__name__.lower()
    except Exception:
        return None
    if t in {"string", "text", "varchar", "unicode", "unicodetext", "char", "nvarchar", "ntext"}:
        return "string"
    if t in {"integer", "biginteger", "smallinteger", "int", "bigint", "smallint"}:
        return "int"
    return None


def _from_metadata() -> list[LookupEligibility]:
    from app.database import Base  # local import to avoid cycle on startup
    out: list[LookupEligibility] = []
    seen: set[tuple[str, str]] = set()
    for tbl in Base.metadata.tables.values():
        if _is_blacklisted_table(tbl.name):
            continue
        for col in tbl.columns:
            if col.primary_key:
                continue
            if col.foreign_keys:
                continue
            cname = col.name
            if cname in _BLACKLIST_COLUMN_NAMES:
                continue
            if any(cname.endswith(s) for s in _BLACKLIST_COLUMN_SUFFIXES):
                continue
            data_type = _classify_column(col)
            if data_type is None:
                continue
            key = (tbl.name, cname)
            if key in seen:
                continue
            seen.add(key)
            out.append(LookupEligibility(
                table_name=tbl.name,
                column_name=cname,
                table_label=_humanize(tbl.name),
                column_label=_humanize(cname),
                data_type=data_type,
                nullable=bool(col.nullable),
            ))
    out.sort(key=lambda e: (e.table_label, e.column_label))
    return out


def _eligibility_from_metadata(table: str, column: str) -> Optional[LookupEligibility]:
    from app.database import Base
    tbl = Base.metadata.tables.get(table)
    if tbl is None or _is_blacklisted_table(tbl.name):
        return None
    col = tbl.columns.get(column)
    if col is None:
        return None
    if col.primary_key or col.foreign_keys:
        return None
    if column in _BLACKLIST_COLUMN_NAMES:
        return None
    if any(column.endswith(s) for s in _BLACKLIST_COLUMN_SUFFIXES):
        return None
    data_type = _classify_column(col)
    if data_type is None:
        return None
    return LookupEligibility(
        table_name=table,
        column_name=column,
        table_label=_humanize(table),
        column_label=_humanize(column),
        data_type=data_type,
        nullable=bool(col.nullable),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_lookup_eligible(
    *,
    model: Type,
    column: str,
    table_label: str,
    column_label: str,
    data_type: DataType = "string",
    nullable: bool = True,
) -> None:
    """Add an explicit override to the in-memory registry.

    Production code does not use this; eligibility is derived from
    SQLAlchemy metadata. Kept for tests that need synthetic (table, column)
    pairs without polluting ``Base.metadata``.
    """
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


def get_eligibility(table: str, column: str) -> Optional[LookupEligibility]:
    if _REGISTRY:
        return _REGISTRY.get((table, column))
    return _eligibility_from_metadata(table, column)


def all_eligibility() -> list[LookupEligibility]:
    if _REGISTRY:
        return list(_REGISTRY.values())
    return _from_metadata()
