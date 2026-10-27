# PLAN: contact delete fails on foreign keys (CONTACT-DELETE-FK)

Status: in review. Small fix track: bug, diff well under 300 lines, no migration, no auth/RBAC change.

## Report

Contacts > select one > Delete contacts fails. The toast shows raw psycopg text:
`ForeignKeyViolation ... price_tag_requests_contact_id_fkey ... [SQL: DELETE FROM respond_contacts ...]`.

## FK inventory (every FK on `respond_contacts.id`)

Read from the models and the creating migrations (they agree), and confirmed from `pg_constraint` on a
freshly bootstrapped DB. 35 constraints.

NO ACTION (the crash): `price_tag_requests.contact_id`, NOT NULL (`app/models/price_tag.py:92-96`,
`alembic/versions/ptag_0001_price_tag_request_foundation.py:176-180`). The only FK without an ON DELETE.

CASCADE (rows go with the contact): link / config rows `respond_contact_companies`,
`respond_contact_access_types`, `respond_contact_tags`, `respond_contact_market_segments`,
`respond_contact_customers`, `contact_agent_access` (also deleted explicitly), `contact_attachment_types`,
`agent_field_access`, `contact_field_reveals`, `stock_visibility_policies`, `spec_visibility_policies`,
`contact_media_limit`, `contact_portal_form_overrides`, `respond_contact_cs_routing`, `dealer_kit.selection`;
and one history table, `conversation_ticket_comments.respond_contact_id` (`app/models/ticket_comment.py:54-56`,
`alembic/versions/328_conversation_ticket_comments.py:47`), the only copy of those notes.

SET NULL (record kept, link nulled): `attachments.uploaded_by_contact_id`, `price_tag_requests.collected_by_contact_id`,
`price_tag_review_comments.author_contact_id`, `users`, `sales_agents`, `stock_inquiries.salesperson_contact_id`,
`portal_form_revisions`, `contact_media_usage`, `conversation_sla_tracking`, `entity_conversation_messages`,
`stock_asks` (both), `ai_assistant_usage_logs`, `new_product_applications`, `sales.opportunities`,
`purchase_requests`, `projects.sales_profile`, `projects.sample_requests`.

## Decision

- Link rows: removed with the contact (unchanged).
- SET NULL history: kept, unchanged (the repo's own precedent for request history).
- Price tag requests (NOT NULL, cannot be nulled) and ticket comments (would be destroyed): the delete is refused
  with a message naming what is linked, the same shape as `project_schedule_service.py:2493`
  ("This schedule cannot be deleted: ..."). No migration.
- Bulk delete: deletes the deletable, returns `blocked: [{id, name, reason}]`; the dialog names each one.
- B: `handle_internal_error` (`app/services/error_handler.py`) replaces any message carrying DB driver /
  SQLAlchemy text with the generic one and logs it. Covers the ~580 `handle_internal_error(str(e))` routes.
  The global `Exception` handler (`app/main.py:162`) already hid detail; the leak was the route-level wrap.
