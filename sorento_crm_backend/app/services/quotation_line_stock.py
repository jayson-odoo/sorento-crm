"""The locations a quotation line's stock figure covers: the signed-in user's contact's Stock
visibility, within the active fulfilment-planning warehouses (QUOTE-STOCK-AGENT-LOC).

Sales agents and roles play no part: a user with no linked contact, or whose contact may see no
location, gets None (nothing shown).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.user import User
from app.services import stock_visibility


def allowed_warehouse_ids(db: Session, user_id: str) -> Optional[List[str]]:
    contact_id = db.query(User.respond_contact_id).filter(User.id == user_id).scalar()
    if not contact_id:
        return None
    policy = stock_visibility.resolve_policy(db, contact_id)
    if policy is None:
        return None
    allowed = stock_visibility.scope_warehouse_ids(db, policy)
    query = db.query(Warehouse.id).filter(
        Warehouse.is_active.is_(True), Warehouse.fulfilment_planning.is_(True)
    )
    if allowed is not None:
        query = query.filter(Warehouse.id.in_(list(allowed)))
    ids = [str(row[0]) for row in query.all()]
    return ids or None


def quotation_line_stock(
    db: Session, user: Dict[str, Any], product_id: str, *, reveal_eta_delay: bool
) -> Optional[Dict[str, Any]]:
    from app.services.project_fulfilment_board_service import FulfilmentBoardService

    ids = allowed_warehouse_ids(db, str(user["id"]))
    if not ids:
        return None
    detail = FulfilmentBoardService(db, reveal_eta_delay=reveal_eta_delay).stock_detail(
        product_id, None, line_ids=[], warehouse_ids=ids
    )
    # Locations, totals and incoming SPOs only: who owes what, and who supplies it, is not for
    # a quotation line, whoever asks.
    detail["sales_orders"] = []
    detail["holds"] = []
    detail["incoming"] = [{**row, "supplier_name": None} for row in detail.get("incoming", [])]
    return detail
