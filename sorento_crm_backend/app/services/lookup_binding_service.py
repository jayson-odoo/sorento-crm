from __future__ import annotations
import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
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
        existing_vals = self._distinct_column_values(data.table_name, data.column_name)
        unknown = existing_vals - opt_values
        if unknown:
            raise handle_validation_error(
                f"Cannot bind: existing rows have values not in this set's options: "
                f"{sorted(list(unknown))[:10]}"
            )
        default_value = getattr(data, "default_value", None)
        if default_value is not None and default_value not in opt_values:
            raise handle_validation_error(
                f"default_value {default_value!r} is not an option of this set."
            )
        b = LookupBinding(
            id=str(uuid.uuid4()), tenant_id=s.tenant_id, set_id=set_id,
            table_name=data.table_name, column_name=data.column_name,
            default_value=default_value,
        )
        self.db.add(b)
        self.db.commit()
        self.db.refresh(b)
        return b

    def set_default_value(self, binding_id: str, default_value: Optional[str]) -> LookupBinding:
        """Set/clear a binding's default option (DV-2). Validates value ∈ set options."""
        b = self.db.query(LookupBinding).filter(LookupBinding.id == binding_id).first()
        if not b:
            raise handle_not_found("LookupBinding", binding_id)
        if default_value is not None:
            opt_values = {
                v for (v,) in self.db.query(LookupOption.value).filter(
                    LookupOption.set_id == b.set_id).all()
            }
            if default_value not in opt_values:
                raise handle_validation_error(
                    f"default_value {default_value!r} is not an option of this set."
                )
        b.default_value = default_value
        self.db.commit()
        self.db.refresh(b)
        return b

    def _distinct_column_values(self, table_name: str, column_name: str) -> set:
        """Distinct non-null values of an eligible ``(table, column)``.

        Built from the RESOLVED SQLAlchemy metadata ``Column`` rather than an
        interpolated string. Eligibility has already validated the pair against
        ``Base.metadata`` (``lookup_eligibility._eligibility_from_metadata``), so
        the identifiers are emitted/quoted by SQLAlchemy Core and never
        concatenated into SQL — no injection surface, even as defense-in-depth.

        Synthetic ``(table, column)`` pairs registered only via ``_REGISTRY``
        (used by tests) are absent from ``Base.metadata``; for those we return an
        empty set so the existing-rows guard is a no-op, matching the prior
        ``try/except`` behaviour exactly.
        """
        from app.database import Base  # local import to avoid cycle on startup
        tbl = Base.metadata.tables.get(table_name)
        if tbl is None:
            return set()
        col = tbl.columns.get(column_name)
        if col is None:
            return set()
        stmt = select(col).where(col.isnot(None)).distinct()
        try:
            rows = self.db.execute(stmt).fetchall()
        except SQLAlchemyError:
            # Physical table not present (e.g. a metadata-only mapping in a test
            # DB). Narrowed from the prior bare ``except Exception`` so genuine
            # programming errors surface; missing-table is treated as no rows.
            return set()
        return {row[0] for row in rows}

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
