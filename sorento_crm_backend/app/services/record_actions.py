"""The record actions a reader can take back while the window is open (D7, S6).

Deleting a product, deleting or re-statusing a delivery order, trashing a user: each
one used to open a confirmation dialog, and now parks itself on the server for a few
seconds instead. `/api/v1/pending-actions` is the only route that reaches these, and
it looks the action up here.

Two rules, both load-bearing:

* **`execute` calls the EXISTING service method, unchanged.** The same code the
  immediate route called still does the work; the pending action changed WHEN it runs,
  never what it does. Inlining logic here would let a deferred delete drift from the
  one the API still exposes, and the drift would be invisible until the two disagreed
  in production.
* **`permission` names the slug the route enforces before parking anything.** The check
  happens at the CLICK, not at the commit, because a refusal ten seconds later has no
  button left to report itself on.

`entity_type` is the frontend's word for the record (`product`, `order`, `user`), and
the payload carries `entity_id` plus whatever the method needs beyond it - the route
puts both there, so `execute` never has to reach for the action row.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.services.form_action_grace import WINDOW_DESTRUCTIVE, WINDOW_REVERSIBLE
from app.services.form_action_registry import FormAction, register

logger = logging.getLogger(__name__)


def _entity_id(payload: dict) -> str:
    return str(payload["entity_id"])


# --------------------------------------------------------------------------------------
# Handlers - one line each, straight onto the service method the route already calls.
# --------------------------------------------------------------------------------------


def _delete_product(db: Session, payload: dict):
    from app.services.product_service import ProductService

    return ProductService(db).delete_product(_entity_id(payload))


def _delete_order(db: Session, payload: dict):
    from app.services.order_service import OrderService

    return OrderService(db).delete_order(_entity_id(payload))


def _set_order_status(db: Session, payload: dict):
    from app.schemas.order import OrderUpdate
    from app.services.order_service import OrderService

    return OrderService(db).update_order(
        _entity_id(payload),
        OrderUpdate(order_status_id=str(payload["order_status_id"])),
        payload.get("requested_by_id"),
    )


def _delete_user(db: Session, payload: dict):
    from app.services.user_service import UserService

    # The trash the Users list restores from, which is what DELETE /users/{id} has
    # always done. The deferred path does not get to redefine the verb.
    return UserService(db).delete_user(_entity_id(payload))


# --------------------------------------------------------------------------------------
# Registrations. `<entity>.<verb>`, the same keys the frontend's action sets name.
# --------------------------------------------------------------------------------------

register(
    FormAction(
        key="product.delete",
        entity_types=("product",),
        execute=_delete_product,
        window=WINDOW_DESTRUCTIVE,
        permission="master_data.products.delete",
        label="Delete product",
    )
)

register(
    FormAction(
        key="order.delete",
        entity_types=("order",),
        execute=_delete_order,
        window=WINDOW_DESTRUCTIVE,
        permission="order_management.orders.delete",
        label="Delete delivery order",
    )
)

register(
    FormAction(
        key="order.set_status",
        entity_types=("order",),
        execute=_set_order_status,
        window=WINDOW_REVERSIBLE,
        permission="order_management.orders.edit",
        label="Change status",
    )
)

register(
    FormAction(
        key="user.delete",
        entity_types=("user",),
        execute=_delete_user,
        window=WINDOW_DESTRUCTIVE,
        permission="user_management.users.delete",
        label="Trash user",
    )
)
