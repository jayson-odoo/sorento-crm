"""Order status select endpoint."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_optional
from app.models.order import OrderStatus

logger = logging.getLogger(__name__)

router = APIRouter()


def _safe_select_response():
    """Return a valid empty response so the UI does not break."""
    return {
        "data": [],
        "pagination": {"total": 0, "page": 1, "limit": 0},
        "empty": True,
    }


@router.get("/select")
def get_order_statuses_select(
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Get order statuses for select dropdowns. Returns empty data on any error to avoid 500."""
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        statuses = db.query(OrderStatus).order_by(OrderStatus.id).all()
        if statuses is None:
            return _safe_select_response()

        data = []
        for s in statuses:
            try:
                data.append({
                    "id": str(s.id),
                    "status_code": str(s.status_code) if s.status_code is not None else "",
                    "status_name": str(s.status_name) if s.status_name is not None else "",
                })
            except Exception as e:
                logger.warning("order-statuses/select: skip row %s: %s", getattr(s, "id", None), e)
                continue

        return {
            "data": data,
            "pagination": {"total": len(data), "page": 1, "limit": len(data)},
            "empty": len(data) == 0,
        }
    except Exception as e:
        logger.exception("order-statuses/select failed: %s", e)
        return _safe_select_response()
