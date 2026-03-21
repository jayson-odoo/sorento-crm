"""Load list query field metadata from DB."""
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.list_query_metadata import ListQueryField, ListQueryResource


class ListQueryMetadataService:
    def __init__(self, db: Session):
        self.db = db

    def list_resources(self) -> List[ListQueryResource]:
        return (
            self.db.query(ListQueryResource)
            .filter(ListQueryResource.is_active.is_(True))
            .order_by(ListQueryResource.display_name.asc())
            .all()
        )

    def get_resource(self, resource_key: str) -> Optional[ListQueryResource]:
        return (
            self.db.query(ListQueryResource)
            .filter(
                ListQueryResource.resource_key == resource_key,
                ListQueryResource.is_active.is_(True),
            )
            .first()
        )

    def list_fields(self, resource_key: str) -> List[ListQueryField]:
        r = self.get_resource(resource_key)
        if not r:
            return []
        return (
            self.db.query(ListQueryField)
            .filter(ListQueryField.resource_id == r.id)
            .order_by(ListQueryField.sort_order.asc(), ListQueryField.field_key.asc())
            .all()
        )

    def fields_by_key(self, resource_key: str) -> Dict[str, ListQueryField]:
        return {f.field_key: f for f in self.list_fields(resource_key)}
