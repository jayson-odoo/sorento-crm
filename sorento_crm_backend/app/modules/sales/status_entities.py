"""Status-engine entity owned by the Sales module (plan 3.4; slice S2).

Discovered by ``app/status_engine/discovery.py``; core never names this file.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.sales import SalesOpportunity
from app.modules.sales.bootstrap import MODULE_KEY
from app.status_engine.registry import StatusEntity, register_status_entity

SALES_OPPORTUNITY_ENTITY_TYPE = "sales_opportunity"


def register() -> None:
    _register_sales_opportunity()


def _count_opportunities(db: Session, status_id: str) -> int:
    return db.query(SalesOpportunity).filter(SalesOpportunity.status_id == status_id).count()


def _migrate_opportunities(db: Session, from_status_id: str, to_status_id: str) -> int:
    return (
        db.query(SalesOpportunity)
        .filter(SalesOpportunity.status_id == from_status_id)
        .update({SalesOpportunity.status_id: to_status_id}, synchronize_session=False)
    )


def _register_sales_opportunity() -> None:
    """No ``scope_resolver`` (plan 3.4): one opportunity funnel per install, the same
    reasoning ``_register_project_lead`` gives - there is no template to fork on."""
    register_status_entity(
        StatusEntity(
            entity_type=SALES_OPPORTUNITY_ENTITY_TYPE,
            label="Sales Opportunity",
            module=MODULE_KEY,
            count_records=_count_opportunities,
            migrate_records=_migrate_opportunities,
            model=SalesOpportunity,
            status_attr="status_id",
            record_label_attr="title",
            required_flags=["is_initial", "is_terminal"],
        )
    )
