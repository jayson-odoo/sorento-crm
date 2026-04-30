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
