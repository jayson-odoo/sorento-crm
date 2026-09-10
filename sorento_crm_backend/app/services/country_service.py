"""Countries master service (S1, `PLAN-local-supplier-oi-routing.md`)."""
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.models.country import Country
from app.models.procurement import Supplier
from app.schemas.country import CountryCreate, CountryUpdate
from app.services.error_handler import handle_conflict, handle_not_found


class CountryService:
    """Copy of `UnitOfMeasureService`'s CRUD shape (S1's own precedent)."""

    def __init__(self, db: Session):
        self.db = db

    def list_countries(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        sort: Optional[str] = None,
        sort_dir: Optional[str] = None,
    ):
        q = self.db.query(Country)
        if query:
            q = q.filter(
                or_(
                    Country.code.ilike(f"%{query}%"),
                    Country.name.ilike(f"%{query}%"),
                )
            )
        sort_map = {"code": Country.code, "name": Country.name}
        sort_column = sort_map.get(sort, Country.name)
        q = q.order_by(sort_column.desc() if sort_dir == "desc" else sort_column.asc())

        total = q.count()
        offset = (page - 1) * limit
        rows = q.offset(offset).limit(limit).all()
        return {
            "data": rows,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }

    def get_country(self, country_id: str) -> Country:
        country = self.db.query(Country).filter(Country.id == country_id).first()
        if not country:
            raise handle_not_found("Country", country_id)
        return country

    def _duplicate_code(self, code: str, *, exclude_id: Optional[str] = None) -> bool:
        q = self.db.query(Country.id).filter(func.lower(Country.code) == code.strip().lower())
        if exclude_id:
            q = q.filter(Country.id != exclude_id)
        return q.first() is not None

    def create_country(self, data: CountryCreate) -> Country:
        if self._duplicate_code(data.code):
            raise handle_conflict("A country with this code already exists.")
        country = Country(**data.model_dump())
        self.db.add(country)
        self.db.commit()
        self.db.refresh(country)
        return country

    def update_country(self, country_id: str, data: CountryUpdate) -> Country:
        country = self.get_country(country_id)
        update_data = data.model_dump(exclude_unset=True)
        if "code" in update_data and self._duplicate_code(update_data["code"], exclude_id=country_id):
            raise handle_conflict("A country with this code already exists.")
        for key, value in update_data.items():
            setattr(country, key, value)
        self.db.commit()
        self.db.refresh(country)
        return country

    def delete_country(self, country_id: str) -> None:
        country = self.get_country(country_id)
        # Countries is company-SHARED (`__company_shared__`), so a row here can be
        # referenced by a supplier belonging to ANY company - counted here across all of
        # them, or the ambient (single-company) scope would undercount and let the delete
        # through, to fail loudly on the DB's own `ON DELETE RESTRICT` instead of the
        # clean 409 this guard exists to give.
        with company_scope(self.db, None):
            count = self.db.query(Supplier).filter(Supplier.country_id == country_id).count()
        if count:
            raise handle_conflict(
                f"Cannot delete this country: {count} supplier{'s' if count != 1 else ''} "
                "still reference it."
            )
        self.db.delete(country)
        self.db.commit()
