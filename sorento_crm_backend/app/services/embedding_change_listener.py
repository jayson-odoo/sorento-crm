"""Model change listeners to enqueue embedding events for key entities."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import event

from app.models.embeddings import EmbeddingQueue
from app.models.marketing import Promotion, PromotionProduct, PromotionAttachment
from app.models.procurement import InboundShipment, InboundShipmentLine, SPOAllocation, PickingHeader, PickingLine
from app.models.product import ProductAttachment
from app.models.order import Order, OrderStatus, OrderLine


_REGISTERED = False


def _queue_from_mapper(connection, source_type: str, source_id: str, event_type: str) -> None:
    connection.execute(
        EmbeddingQueue.__table__.insert().values(
            id=str(uuid.uuid4()),
            source_type=source_type,
            source_id=str(source_id),
            event_type=event_type,
            event_version=1,
            payload={
                "event_id": str(uuid.uuid4()),
                "event_type": event_type,
                "event_version": 1,
                "occurred_at": datetime.utcnow().isoformat(),
                "source_type": source_type,
                "source_id": str(source_id),
                "changed_fields": ["model_change_listener"],
                "triggered_by": "system",
            },
            status="pending",
            retry_count=0,
            available_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
    )


def _attach_listeners(model, source_type: str) -> None:
    @event.listens_for(model, "after_insert")
    def _after_insert(_mapper, connection, target):
        _queue_from_mapper(connection, source_type, target.id, f"{source_type}.created")

    @event.listens_for(model, "after_update")
    def _after_update(_mapper, connection, target):
        _queue_from_mapper(connection, source_type, target.id, f"{source_type}.updated")

    @event.listens_for(model, "after_delete")
    def _after_delete(_mapper, connection, target):
        _queue_from_mapper(connection, source_type, target.id, f"{source_type}.deleted")


def register_embedding_change_listeners() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    _attach_listeners(Promotion, "promotion")
    _attach_listeners(PromotionProduct, "promotion_product")
    _attach_listeners(InboundShipment, "inbound_shipment")
    _attach_listeners(InboundShipmentLine, "inbound_shipment_line")
    _attach_listeners(SPOAllocation, "spo_allocation")
    _attach_listeners(PickingHeader, "picking_header")
    _attach_listeners(PickingLine, "picking_line")
    _attach_listeners(ProductAttachment, "product_attachment")
    _attach_listeners(PromotionAttachment, "promotion_attachment")
    _attach_listeners(Order, "order")
    _attach_listeners(OrderStatus, "order_status")
    _attach_listeners(OrderLine, "order_line")
    _REGISTERED = True
