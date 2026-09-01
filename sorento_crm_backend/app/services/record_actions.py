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
from typing import Optional

from sqlalchemy.orm import Session

from app.services.form_action_grace import WINDOW_DESTRUCTIVE, WINDOW_REVERSIBLE
from app.services.form_action_registry import FormAction, register

logger = logging.getLogger(__name__)

#: A record action authorised by OWNERSHIP rather than by a role grant.
#:
#: `permission` is what tells `/pending-actions` this is a record action at all, and for
#: every other one it is the slug the immediate route enforces. A notification has no
#: such slug: the bell is in the topbar for every signed-in user, the route checks
#: nothing, and the handler is scoped to the requester, so the only row it can reach is
#: the reader's own. Inventing a permission for it would mean a grant sweep across every
#: role for a rule the query already enforces.
OWN_RECORD = "@own"


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


def _actor(db: Session, payload: dict) -> dict:
    """The click's actor, in the shape a service expects `current_user` to be.

    The row is read back rather than passed through, because a service may re-check a
    grant against the id AND write the email into provenance ("cleared by ...").
    A dict with only an id would leave that reading "a person" ten seconds after
    somebody with a name pressed the button.
    """
    uid = payload.get("requested_by_id")
    if not uid:
        return {"id": None}
    from app.models.user import User

    row = db.query(User).filter(User.id == str(uid)).first()
    return {
        "id": str(uid),
        "email": getattr(row, "email", None),
        "name": getattr(row, "name", None),
    }


# ----- Resources (attachments/folders) --------------------------------------------------
#
# `Set company…` (PLAN-shared-brand-attachments.md R4/R22). Reversible - the twin links
# it maintains are just as reversible as the company itself, so it takes the short window
# like `order.set_status`. `permission=OWN_RECORD` mirrors the route it defers to
# (`POST .../bulk-company`), which is guarded the same as `PUT /attachments/{id}` - no
# permission slug of its own, just a signed-in caller (R13); `AttachmentCompanyService`
# still checks the target company against the actor's own grants (AC-B6).


def _set_attachment_company(db: Session, payload: dict):
    from app.services.attachment_company_service import AttachmentCompanyService

    return AttachmentCompanyService(db).apply(
        attachment_ids=[_entity_id(payload)],
        company_id=payload.get("company_id"),
        actor_id=payload.get("requested_by_id"),
    )


def _set_directory_company(db: Session, payload: dict):
    from app.services.attachment_company_service import AttachmentCompanyService

    return AttachmentCompanyService(db).apply(
        directory_ids=[_entity_id(payload)],
        company_id=payload.get("company_id"),
        actor_id=payload.get("requested_by_id"),
    )


register(
    FormAction(
        key="attachment.set_company",
        entity_types=("attachment",),
        execute=_set_attachment_company,
        window=WINDOW_REVERSIBLE,
        permission=OWN_RECORD,
        label="Set company",
    )
)

register(
    FormAction(
        key="attachment_directory.set_company",
        entity_types=("attachment_directory",),
        execute=_set_directory_company,
        window=WINDOW_REVERSIBLE,
        permission=OWN_RECORD,
        label="Set company",
    )
)


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

    return delete_ticket(db, ticket_id=_entity_id(payload), current_user=_actor(db, payload))


def _cancel_ticket_draft(db: Session, payload: dict):
    from app.services.tickets_service import cancel_ticket_draft

    return cancel_ticket_draft(
        db, ticket_id=_entity_id(payload), current_user=_actor(db, payload)
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


def _clear_product_spec_value(db: Session, payload: dict):
    from app.models.product import Product
    from app.services.error_handler import handle_not_found, handle_validation_error
    from app.services.product_spec_write import apply_spec_values

    # The record is one product's value for one key, so the entity id has to name BOTH
    # (`<product id>:<spec key>`). Parked against the bare spec key it was a globally
    # shared id: two people clearing `width` on two different products collided on the
    # one-pending-action-per-record index, one of them got a 409 for a record nobody
    # else had touched, and each then read the other's outcome as their own.
    product_id, _, spec_key = _entity_id(payload).partition(":")
    if not product_id or not spec_key:
        raise handle_validation_error(
            "A specification value is addressed as '<product id>:<spec key>'."
        )
    # `spec.values` may only be written through this one service (hard-fail rule), so
    # the handler goes through it exactly as the route does.
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise handle_not_found("Product", product_id)
    mode = "absent" if payload.get("mode") == "absent" else "revert"
    return apply_spec_values(
        db,
        product.product_code,
        [{"spec_key": spec_key, "op": mode}],
        actor=_actor(db, payload),
    )


def _remove_stock_visibility_policy(db: Session, payload: dict):
    from app.services.stock_visibility import delete_policy

    # The scope is the entity: a contact override or an access-type policy. The kind
    # travels in the payload because the two are different columns, not different ids.
    scope_kind = str(payload.get("scope_kind") or "")
    if scope_kind == "contact":
        return delete_policy(db, contact_id=_entity_id(payload))
    return delete_policy(db, access_type_code=_entity_id(payload))


def _remove_signin_background(db: Session, payload: dict):
    from app.services.signin_background import clear_signin_background

    return clear_signin_background(db)


def _delete_market_segment(db: Session, payload: dict):
    from app.services.market_segment_service import MarketSegmentService

    # Keyed by CODE, not a uuid - that is what the table's primary key is and what
    # `DELETE /market-segments/{code}` takes.
    return MarketSegmentService(db).delete_segment(_entity_id(payload))


def _delete_onboarding_request(db: Session, payload: dict):
    from app.services import onboarding_service

    # No service method to call: `DELETE /onboarding-requests/{id}` is these three
    # lines and no rule of its own (`get_request` already carries the 404 and the
    # company-scope filter), so there is nothing here that could drift from it.
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
        key="product_spec_value.clear",
        # The record is the VALUE on one product, so the entity id names both halves of
        # it: `<product id>:<spec key>`. The spec key alone is shared by every product
        # that holds it, and the engine's one-pending-action-per-record index would then
        # treat two products as one record.
        entity_types=("product_spec_value",),
        execute=_clear_product_spec_value,
        # `revert` hands the key back to derivation and `absent` writes a tombstone.
        # The tombstone is the irreversible one, so both take the long window rather
        # than the screen having to pick a different countdown per menu item.
        window=WINDOW_DESTRUCTIVE,
        permission="master_data.products.edit",
        label="Clear specification",
    )
)

register(
    FormAction(
        key="stock_visibility_policy.remove",
        entity_types=("stock_visibility_policy",),
        execute=_remove_stock_visibility_policy,
        # Reversible: the tier falls back to the policy above it and the card can
        # write the override again from what is still on screen.
        window=WINDOW_REVERSIBLE,
        permission="inventory.stock.edit",
        label="Remove stock visibility",
    )
)

register(
    FormAction(
        key="signin_background.remove",
        # A singleton setting, not a row: the frontend parks it against the constant
        # `signin-background`, because there is one of it and the reader never sees an id.
        entity_types=("signin_background",),
        execute=_remove_signin_background,
        # Reversible: the sign-in page falls back to its designed default and the admin
        # still holds the file they uploaded, so putting it back is one drop away.
        window=WINDOW_REVERSIBLE,
        permission="user_management.settings.edit",
        label="Remove sign-in background",
    )
)

register(
    FormAction(
        key="market_segment.delete",
        entity_types=("market_segment",),
        execute=_delete_market_segment,
        window=WINDOW_DESTRUCTIVE,
        # `.manage`, not `.view`: a read grant authorising a hard delete was wrong
        # in principle, even though the immediate route it replaced had no slug
        # at all (issue #402).
        permission="user_management.reference_data.manage",
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


# ----- Dealer kit -----------------------------------------------------------------------
#
# One slug for all five, `dealer_kit.page.edit`, because that is the single grant every
# one of these DELETE routes is behind today.


def _delete_dk_bundle(db: Session, payload: dict):
    from app.services.dealer_kit import bundle_service

    return bundle_service.delete_bundle(db, _entity_id(payload))


def _delete_dk_collection(db: Session, payload: dict):
    from app.services.dealer_kit import collection_service

    return collection_service.delete_collection(db, _entity_id(payload))


def _delete_dk_page(db: Session, payload: dict):
    from app.services.dealer_kit import page_service

    return page_service.delete_page(db, _entity_id(payload))


def _delete_dk_flyer_reading(db: Session, payload: dict):
    from app.services.dealer_kit import flyer_reading_service

    return flyer_reading_service.delete_reading(db, _entity_id(payload))


def _delete_dk_tile_template(db: Session, payload: dict):
    from app.services.dealer_kit import tile_template_service

    return tile_template_service.delete_template(db, _entity_id(payload))


for _key, _entity, _fn, _label in (
    ("dk_bundle.delete", "dk_bundle", _delete_dk_bundle, "Delete bundle"),
    ("dk_collection.delete", "dk_collection", _delete_dk_collection, "Delete collection"),
    ("dk_page.delete", "dk_page", _delete_dk_page, "Delete page"),
    (
        "dk_flyer_reading.delete",
        "dk_flyer_reading",
        _delete_dk_flyer_reading,
        "Delete flyer reading",
    ),
    (
        "dk_tile_design.delete",
        "dk_tile_design",
        _delete_dk_tile_template,
        "Delete tile design",
    ),
):
    register(
        FormAction(
            key=_key,
            entity_types=(_entity,),
            execute=_fn,
            window=WINDOW_DESTRUCTIVE,
            permission="dealer_kit.page.edit",
            label=_label,
        )
    )


def _undo_flyer_code_adopt(db: Session, payload: dict):
    """"This printed code is NOT that product" - undoing an adoption (D7, S1).

    There is no row of its own to key a pending action on: the thing being
    detached is one entry inside a reading's `code_overrides` JSONB map, not a
    record with an id. So the entity id names BOTH (`<reading id>:<printed
    code>`), the same shape `_clear_product_spec_value` above uses for a
    product's spec value - and like that one, this reads BOTH out of the id
    rather than trusting separate payload fields, which is what
    `test_every_handler_resolves_its_service_import` drives every handler
    with (no `reading_id`/`printed_code` keys, only a bare `entity_id`).

    A reading id is a fixed 36-char UUID, so this SLICES at that width rather
    than splitting on the first ':' - a printed code never contains one, but
    slicing also never raises on an entity id that has no colon at all (the
    harness's bare-uuid stand-in), where a `str.split(":", 1)` unpack would
    raise `ValueError` before ever reaching `db` and fail that test for the
    wrong reason.

    Same service call the DELETE route makes (`flyer_reading_service.
    unadopt_code`) - the deferred path changes WHEN this runs, never what it
    does.
    """
    from app.services.dealer_kit import flyer_reading_service

    entity_id = _entity_id(payload)
    reading_id, printed_code = entity_id[:36], entity_id[37:]
    record = flyer_reading_service.get_reading(db, reading_id)
    return flyer_reading_service.unadopt_code(db, record, printed_code=printed_code)


register(
    FormAction(
        key="flyer_code_adoption.undo",
        entity_types=("flyer_code_adoption",),
        execute=_undo_flyer_code_adopt,
        # Reversible, not destructive: re-adopting the same code afterwards
        # writes the same key back (AC-A.4), and nothing already applied to
        # the product is touched either way the window resolves (R2).
        window=WINDOW_REVERSIBLE,
        # `master_data.products.edit` only - the direct DELETE route also
        # requires `dealer_kit.page.view`, and this generic route checks ONE
        # slug. Narrowing that pair to its write half is a deliberate,
        # reviewed call for this action: `products.edit` is the permission
        # that actually authorises the write (which product a code means),
        # `page.view` scopes which readings a caller may look at, and this
        # path is reached from the button on a reading the caller is already
        # looking at, gated by the page's own view permission before the
        # button ever renders.
        permission="master_data.products.edit",
        label="Undo code adoption",
    )
)


# ----- SCM ------------------------------------------------------------------------------


def _scm_actor(db: Session, payload: dict) -> Optional[str]:
    """The caller's human NAME, which is what SCM writes into provenance."""
    who = _actor(db, payload)
    return who.get("name") or who.get("email") or None


def _delete_loading_plan(db: Session, payload: dict):
    from app.services.scm import loading_plan_service

    return loading_plan_service.delete_record(db, _entity_id(payload))


def _delete_market_topic(db: Session, payload: dict):
    from app.services.scm import market_research_service

    return market_research_service.delete_topic(db, _entity_id(payload))


def _delete_container_size(db: Session, payload: dict):
    from app.models.scm import ContainerSize
    from app.services.error_handler import handle_not_found

    # No service method to call: `DELETE /container-sizes/{id}` is these three lines and
    # no rule of its own, so there is nothing here that could drift from it.
    row = db.query(ContainerSize).filter(ContainerSize.id == _entity_id(payload)).first()
    if row is None:
        raise handle_not_found("Container size", _entity_id(payload))
    db.delete(row)
    db.commit()


def _delete_currency_rate(db: Session, payload: dict):
    from app.services.scm import currency_rate_service

    # Keyed by CURRENCY, not a uuid - that is what the route takes too.
    return currency_rate_service.delete_rate(db, _entity_id(payload))


def _delete_reorder_policy(db: Session, payload: dict):
    from app.services.scm import policy_service

    return policy_service.delete_policy(db, _entity_id(payload))


def _delete_scm_sales_order(db: Session, payload: dict):
    from app.services.scm.sales_order_service import SalesOrderService

    return SalesOrderService(db).delete(_entity_id(payload))


def _delete_proforma_invoice(db: Session, payload: dict):
    from app.services.scm import proforma_invoice_service

    proforma_invoice_service.delete(db, _entity_id(payload))
    db.commit()


def _forget_supplier_code_alias(db: Session, payload: dict):
    from app.services.scm import supplier_code_alias_service

    out = supplier_code_alias_service.delete(
        db, _entity_id(payload), actor=_scm_actor(db, payload)
    )
    db.commit()
    return out


register(
    FormAction(
        key="loading_plan.delete",
        entity_types=("loading_plan",),
        execute=_delete_loading_plan,
        window=WINDOW_DESTRUCTIVE,
        permission="scm.reorder.run",
        label="Delete loading plan",
    )
)

register(
    FormAction(
        key="market_topic.delete",
        entity_types=("market_topic",),
        execute=_delete_market_topic,
        window=WINDOW_DESTRUCTIVE,
        permission="scm.policy.manage",
        label="Delete research topic",
    )
)

register(
    FormAction(
        key="container_size.delete",
        entity_types=("container_size",),
        execute=_delete_container_size,
        window=WINDOW_DESTRUCTIVE,
        permission="scm.reorder.run",
        label="Delete container size",
    )
)

register(
    FormAction(
        key="currency_rate.delete",
        entity_types=("currency_rate",),
        execute=_delete_currency_rate,
        window=WINDOW_DESTRUCTIVE,
        permission="scm.config.manage",
        label="Remove exchange rate",
    )
)

register(
    FormAction(
        key="reorder_policy.delete",
        entity_types=("reorder_policy",),
        execute=_delete_reorder_policy,
        window=WINDOW_DESTRUCTIVE,
        permission="scm.policy.manage",
        label="Delete policy",
    )
)

register(
    FormAction(
        key="scm_sales_order.delete",
        entity_types=("scm_sales_order",),
        execute=_delete_scm_sales_order,
        window=WINDOW_DESTRUCTIVE,
        permission="scm.reorder.run",
        label="Delete sales order",
    )
)

register(
    FormAction(
        key="proforma_invoice.delete",
        entity_types=("proforma_invoice",),
        execute=_delete_proforma_invoice,
        window=WINDOW_DESTRUCTIVE,
        permission="scm.proforma_invoice.upload",
        label="Delete proforma invoice",
    )
)

register(
    FormAction(
        key="supplier_code_alias.forget",
        entity_types=("supplier_code_alias",),
        execute=_forget_supplier_code_alias,
        # Reversible: the rows go back to whatever the ladder says now, and the ruling
        # can be made again from the same screen.
        window=WINDOW_REVERSIBLE,
        permission="scm.reorder.run",
        label="Forget supplier-code match",
    )
)


def _delete_notification(db: Session, payload: dict):
    from app.services.error_handler import handle_not_found
    from app.services.notification_service import NotificationService

    # Scoped to the requester, exactly as DELETE /notifications/{id} is: the row this
    # can reach is the reader's own, which is what stands in for a permission slug.
    notification_id = _entity_id(payload)
    requested_by_id = payload.get("requested_by_id")
    if not requested_by_id:
        raise handle_not_found("Notification", notification_id)
    if not NotificationService(db).delete(notification_id, str(requested_by_id)):
        raise handle_not_found("Notification", notification_id)
    return {"message": "Deleted"}


register(
    FormAction(
        key="notification.delete",
        entity_types=("notification",),
        execute=_delete_notification,
        # Reversible: the notification is a copy of something that happened elsewhere,
        # and the reader can Clear the whole list beside this button anyway. Five
        # seconds is the window this needs - enough that no click is final on its own.
        window=WINDOW_REVERSIBLE,
        permission=OWN_RECORD,
        label="Delete notification",
    )
)
