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


# --------------------------------------------------------------------------------------
# S6b - the sweep of what still confirmed in a dialog.
#
# Same two rules as above: `execute` is one line onto the service method the immediate
# route already calls, and `permission` is the slug that route (or the screen the action
# lives on) enforces. A key ending `.delete` takes the destructive window; a detach that
# can be made again by re-adding the row takes the reversible one.
# --------------------------------------------------------------------------------------


def _unlink_product_supplier(db: Session, payload: dict):
    from app.services.procurement_service import ProductSupplierService

    return ProductSupplierService(db).delete_product_supplier(_entity_id(payload))


register(
    FormAction(
        key="product_supplier.unlink",
        entity_types=("product_supplier",),
        execute=_unlink_product_supplier,
        # Reversible: the supplier is still there, and re-adding the row restores the
        # link. The terms typed on it are not restored, which is why it is deferred at
        # all rather than applied on the click.
        window=WINDOW_REVERSIBLE,
        # The section is part of a product's edit form, and that is the grant it is
        # rendered behind.
        permission="master_data.products.edit",
        label="Remove supplier",
    )
)


def _actor(payload: dict) -> dict:
    """The click's actor, in the shape a service that re-checks a grant expects."""
    return {"id": payload.get("requested_by_id")}


# ----- Master data ---------------------------------------------------------------------


def _delete_uom(db: Session, payload: dict):
    from app.services.product_service import UnitOfMeasureService

    return UnitOfMeasureService(db).delete_uom(_entity_id(payload))


def _delete_brand(db: Session, payload: dict):
    from app.services.product_service import BrandService

    return BrandService(db).delete_brand(_entity_id(payload))


def _delete_product_category(db: Session, payload: dict):
    from app.services.product_service import ProductCategoryService

    return ProductCategoryService(db).delete_category(_entity_id(payload))


def _delete_product_set(db: Session, payload: dict):
    from app.services.product_set_service import ProductSetService

    return ProductSetService(db).delete(_entity_id(payload))


def _delete_certificate(db: Session, payload: dict):
    from app.services.certificate_service import CertificateService

    return CertificateService(db).delete_certificate(_entity_id(payload))


def _delete_lookup_option(db: Session, payload: dict):
    from app.services.lookup_option_service import LookupOptionService

    return LookupOptionService(db).delete(_entity_id(payload))


def _unlink_lookup_binding(db: Session, payload: dict):
    from app.services.lookup_binding_service import LookupBindingService

    return LookupBindingService(db).delete(_entity_id(payload))


register(
    FormAction(
        key="uom.delete",
        entity_types=("uom",),
        execute=_delete_uom,
        window=WINDOW_DESTRUCTIVE,
        permission="master_data.units_of_measure.delete",
        label="Delete unit of measure",
    )
)

register(
    FormAction(
        key="brand.delete",
        entity_types=("brand",),
        execute=_delete_brand,
        window=WINDOW_DESTRUCTIVE,
        permission="master_data.brands.delete",
        label="Delete brand",
    )
)

register(
    FormAction(
        key="product_category.delete",
        entity_types=("product_category",),
        execute=_delete_product_category,
        window=WINDOW_DESTRUCTIVE,
        permission="master_data.product_categories.delete",
        label="Delete category",
    )
)

register(
    FormAction(
        key="product_set.delete",
        entity_types=("product_set",),
        execute=_delete_product_set,
        window=WINDOW_DESTRUCTIVE,
        permission="master_data.product_sets.delete",
        label="Delete product set",
    )
)

register(
    FormAction(
        key="certificate.delete",
        entity_types=("certificate",),
        execute=_delete_certificate,
        window=WINDOW_DESTRUCTIVE,
        permission="master_data.certificates.delete",
        label="Delete certificate",
    )
)

register(
    FormAction(
        key="lookup_option.delete",
        entity_types=("lookup_option",),
        execute=_delete_lookup_option,
        window=WINDOW_DESTRUCTIVE,
        permission="master_data.lookup_sets.edit",
        label="Delete option",
    )
)

register(
    FormAction(
        key="lookup_binding.unlink",
        entity_types=("lookup_binding",),
        execute=_unlink_lookup_binding,
        # Reversible: the column keeps its data and the binding can be made again.
        window=WINDOW_REVERSIBLE,
        permission="master_data.lookup_sets.edit",
        label="Remove binding",
    )
)


# ----- Marketing -----------------------------------------------------------------------


def _delete_campaign(db: Session, payload: dict):
    from app.services.marketing_service import MarketingCampaignService

    return MarketingCampaignService(db).delete_campaign(_entity_id(payload))


def _delete_promotion_type(db: Session, payload: dict):
    from app.services.marketing_service import PromotionTypeService

    return PromotionTypeService(db).delete_promotion_type(_entity_id(payload))


def _delete_promotion_group(db: Session, payload: dict):
    from app.services.marketing_service import PromotionService

    return PromotionService(db).delete_promotion_group(
        str(payload["promotion_id"]), _entity_id(payload)
    )


def _unlink_promotion_product(db: Session, payload: dict):
    from app.services.marketing_service import PromotionProductService

    return PromotionProductService(db).delete_promotion_product(
        str(payload["promotion_id"]), _entity_id(payload)
    )


register(
    FormAction(
        key="campaign.delete",
        entity_types=("campaign",),
        execute=_delete_campaign,
        window=WINDOW_DESTRUCTIVE,
        permission="marketing.campaigns.delete",
        label="Delete campaign",
    )
)

register(
    FormAction(
        key="promotion_type.delete",
        entity_types=("promotion_type",),
        execute=_delete_promotion_type,
        window=WINDOW_DESTRUCTIVE,
        permission="marketing.promotion_types.delete",
        label="Delete promotion type",
    )
)

register(
    FormAction(
        key="promotion_group.delete",
        entity_types=("promotion_group",),
        execute=_delete_promotion_group,
        window=WINDOW_DESTRUCTIVE,
        permission="marketing.promotions.edit",
        label="Delete group",
    )
)

register(
    FormAction(
        key="promotion_product.unlink",
        entity_types=("promotion_product",),
        execute=_unlink_promotion_product,
        window=WINDOW_REVERSIBLE,
        permission="marketing.promotion_products.delete",
        label="Remove product line",
    )
)


# ----- Inventory, integrations, tickets, workflow forms ---------------------------------


def _delete_warehouse(db: Session, payload: dict):
    from app.services.inventory_service import WarehouseService

    return WarehouseService(db).delete_warehouse(_entity_id(payload))


def _delete_integration(db: Session, payload: dict):
    from app.services.integration_admin_service import IntegrationAdminService

    service = IntegrationAdminService(db)
    service.delete(service.get(_entity_id(payload)))
    db.commit()


def _revoke_integration_key(db: Session, payload: dict):
    from app.services.integration_admin_service import IntegrationAdminService

    service = IntegrationAdminService(db)
    service.revoke_key(
        service.get(str(payload["integration_id"])), _entity_id(payload)
    )
    db.commit()


def _delete_ticket(db: Session, payload: dict):
    from app.services.tickets_service import delete_ticket

    return delete_ticket(db, ticket_id=_entity_id(payload), current_user=_actor(payload))


def _cancel_ticket_draft(db: Session, payload: dict):
    from app.services.tickets_service import cancel_ticket_draft

    return cancel_ticket_draft(
        db, ticket_id=_entity_id(payload), current_user=_actor(payload)
    )


def _delete_workflow_definition(db: Session, payload: dict):
    from app.services.workflow_forms_service import WorkflowFormsService

    return WorkflowFormsService(db).delete_definition(_entity_id(payload))


def _delete_workflow_submission(db: Session, payload: dict):
    from app.services.workflow_forms_service import WorkflowFormsService

    return WorkflowFormsService(db).delete_submission(_entity_id(payload))


register(
    FormAction(
        key="warehouse.delete",
        entity_types=("warehouse",),
        execute=_delete_warehouse,
        window=WINDOW_DESTRUCTIVE,
        permission="inventory.warehouses.delete",
        label="Delete warehouse",
    )
)

register(
    FormAction(
        key="integration.delete",
        entity_types=("integration",),
        execute=_delete_integration,
        window=WINDOW_DESTRUCTIVE,
        permission="integration.integrations.delete",
        label="Delete integration",
    )
)

register(
    FormAction(
        key="integration_key.revoke",
        entity_types=("integration_key",),
        execute=_revoke_integration_key,
        # A revoked key can never be un-revoked - the plaintext is gone - so this
        # takes the long window even though its verb is not `delete`.
        window=WINDOW_DESTRUCTIVE,
        permission="integration.integrations.manage_keys",
        label="Revoke API key",
    )
)

register(
    FormAction(
        key="ticket.delete",
        entity_types=("ticket",),
        execute=_delete_ticket,
        window=WINDOW_DESTRUCTIVE,
        permission="tickets.tickets.delete",
        label="Delete ticket",
    )
)

register(
    FormAction(
        key="ticket.cancel_draft",
        entity_types=("ticket",),
        execute=_cancel_ticket_draft,
        # Discarding a draft hard-deletes it, so it takes the long window even
        # though the button on screen says Cancel rather than Delete.
        window=WINDOW_DESTRUCTIVE,
        permission="tickets.tickets.edit",
        label="Discard draft",
    )
)

register(
    FormAction(
        key="workflow_definition.delete",
        entity_types=("workflow_definition",),
        execute=_delete_workflow_definition,
        window=WINDOW_DESTRUCTIVE,
        permission="workflow_forms.definitions.delete",
        label="Delete workflow form",
    )
)

register(
    FormAction(
        key="workflow_submission.delete",
        entity_types=("workflow_submission",),
        execute=_delete_workflow_submission,
        window=WINDOW_DESTRUCTIVE,
        permission="workflow_forms.submissions.delete",
        label="Delete submission",
    )
)


# ----- SLA, system, user management -----------------------------------------------------


def _delete_sla_tracking(db: Session, payload: dict):
    from app.services.sla_service import ConversationSLATrackingService

    return ConversationSLATrackingService(db).delete_tracking(_entity_id(payload))


def _delete_message_snippet(db: Session, payload: dict):
    from app.services.message_snippet_service import MessageSnippetService

    return MessageSnippetService(db).delete_snippet(_entity_id(payload))


def _delete_automation(db: Session, payload: dict):
    from app.services.automation_service import AutomationService

    return AutomationService(db).delete(_entity_id(payload))


def _delete_email_template(db: Session, payload: dict):
    from app.services.email_template_service import EmailTemplateService

    return EmailTemplateService(db).delete(_entity_id(payload))


def _delete_role(db: Session, payload: dict):
    from app.services.user_service import UserRoleService

    return UserRoleService(db).delete_role(_entity_id(payload))


def _delete_team(db: Session, payload: dict):
    from app.services.user_service import TeamService

    return TeamService(db).delete_team(_entity_id(payload))


def _delete_access_agent(db: Session, payload: dict):
    from app.services.user_service import AccessAgentService

    return AccessAgentService(db).delete_agent(_entity_id(payload))


def _delete_market_segment(db: Session, payload: dict):
    from app.services.market_segment_service import MarketSegmentService

    # Keyed by CODE, not a uuid - that is what the table's primary key is and what
    # `DELETE /market-segments/{code}` takes.
    return MarketSegmentService(db).delete_segment(_entity_id(payload))


def _delete_onboarding_request(db: Session, payload: dict):
    from app.services import onboarding_service

    request = onboarding_service.get_request(db, _entity_id(payload))
    db.delete(request)
    db.commit()


register(
    FormAction(
        key="sla_tracking.delete",
        entity_types=("sla_tracking",),
        execute=_delete_sla_tracking,
        window=WINDOW_DESTRUCTIVE,
        permission="sla_management.conversation_sla_tracking.delete",
        label="Delete tracking record",
    )
)

register(
    FormAction(
        key="message_snippet.delete",
        entity_types=("message_snippet",),
        execute=_delete_message_snippet,
        window=WINDOW_DESTRUCTIVE,
        permission="sla_management.message_snippets.delete",
        label="Delete snippet",
    )
)

register(
    FormAction(
        key="automation.delete",
        entity_types=("automation",),
        execute=_delete_automation,
        window=WINDOW_DESTRUCTIVE,
        permission="automation.automations.delete",
        label="Delete automation",
    )
)

register(
    FormAction(
        key="email_template.delete",
        entity_types=("email_template",),
        execute=_delete_email_template,
        window=WINDOW_DESTRUCTIVE,
        permission="email_templates.templates.delete",
        label="Delete email template",
    )
)

register(
    FormAction(
        key="role.delete",
        entity_types=("role",),
        execute=_delete_role,
        window=WINDOW_DESTRUCTIVE,
        permission="user_management.roles.delete",
        label="Delete role",
    )
)

register(
    FormAction(
        key="team.delete",
        entity_types=("team",),
        execute=_delete_team,
        window=WINDOW_DESTRUCTIVE,
        permission="user_management.teams.delete",
        label="Delete team",
    )
)

register(
    FormAction(
        key="access_agent.delete",
        entity_types=("access_agent",),
        execute=_delete_access_agent,
        window=WINDOW_DESTRUCTIVE,
        permission="user_management.access_agents.delete",
        label="Delete access agent",
    )
)

register(
    FormAction(
        key="market_segment.delete",
        entity_types=("market_segment",),
        execute=_delete_market_segment,
        window=WINDOW_DESTRUCTIVE,
        # The route itself has no slug, so this names the grant the SCREEN is
        # gated on in `menu.config`. Anyone who can reach the button already
        # holds it; nobody who could delete a segment before loses the ability.
        permission="user_management.reference_data.view",
        label="Delete market segment",
    )
)

register(
    FormAction(
        key="onboarding_request.delete",
        entity_types=("onboarding_request",),
        execute=_delete_onboarding_request,
        window=WINDOW_DESTRUCTIVE,
        permission="user_management.onboarding.delete",
        label="Delete onboarding request",
    )
)
