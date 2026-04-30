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
