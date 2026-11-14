"""Warranty term routes. Mounted under /after-sales/warranty/terms."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.after_sales.warranty.access import can_read, can_write
from app.database import get_db
from app.schemas.warranty_config import TermCreate, TermUpdate
from app.services import warranty_config_service as svc
from app.services.service_job_service import stamp_actor

router = APIRouter()


@router.get("")
def list_terms(policy_id: str = Query(...), current_user: dict = Depends(can_read), db: Session = Depends(get_db)):
    return svc.list_terms(db, policy_id)


@router.post("", status_code=201)
def create_term(payload: TermCreate, current_user: dict = Depends(can_write), db: Session = Depends(get_db)):
    stamp_actor(db, current_user)
    return svc.create_term(db, payload)


@router.patch("/{term_id}")
def update_term(term_id: str, payload: TermUpdate, current_user: dict = Depends(can_write), db: Session = Depends(get_db)):
    stamp_actor(db, current_user)
    return svc.update_term(db, term_id, payload)


@router.delete("/{term_id}")
def delete_term(term_id: str, current_user: dict = Depends(can_write), db: Session = Depends(get_db)):
    stamp_actor(db, current_user)
    return svc.delete_term(db, term_id)
