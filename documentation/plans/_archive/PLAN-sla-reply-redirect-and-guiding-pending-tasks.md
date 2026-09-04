# PLAN - SLA reply → Respond redirect, Resolve-closes-Respond, guiding pending tasks

Status: **Code complete + tests green** (Parts 1 - 4 done; browser verification pending local login)

## Context / why

Three user-driven refinements to the conversation-SLA + pending-task experience:

1. The CRM cannot yet send **files** over Respond.io. So in-system text reply on a
   conversation-SLA row is misleading - staff start a reply here, then can't attach the
   file the customer needs. Decision: stop offering in-system reply for conversation SLA;
   **redirect to the Respond inbox** (where files work) and keep a **Resolve** action.
2. **Form SLA stays on the existing in-system form-view flow** (complaint / stock_inquiry /
   purchase_request / sponsorship) - those are actioned on their record pages, unchanged.
3. The "My pending tasks" widget lists entity + tier + due but does **not tell the user what
   to do next**. Make every row **guiding**: an explicit next-action line + a CTA button,
   differentiated by SLA type.

Decisions locked with user:
- **Resolve = also closes the conversation in Respond.io** (not just a local flag flip).
- Pending-task rows get **action line + CTA button** (the most guiding option).

## Distinctions that drive the code

- **Conversation SLA** rows: `source_entity_type` NULL (or `conversation`), `respond_contact_id`
  set. Next action = reply in Respond + Resolve. CTA → Respond inbox + Resolve button.
- **Form SLA** rows: `source_entity_type` in `{complaint, stock_inquiry, purchase_request,
  sponsorship_form}`, `source_entity_id` set. Next action = open record & respond on its page.
  CTA → entity record page (existing link), no change to that flow.

## Respond.io API - close conversation

`POST {respond_base_url}/v2/contact/{identifier}/conversation/close`
- identifier format: `id:{respond_io_id}` (mirror `RespondClient._contact_api_identifier`).
- Optional body: `{ "category": "...", "summary": "..." }` - workspace may require category.
- Auth: `Authorization: Bearer {respond_api_key}` (existing `_headers()`).
Refs: developers.respond.io "Open/close conversation".

## Part 1 - Template config: `sla_daily_summary` use case (DONE)

- BE `respond_template_service.py`: added `sla_daily_summary` use case + params
  `outstanding`, `escalated_last_24h`, `resolved_last_24h`.
- BE `respond_template.py`: added `sla_daily_summary` to allowed use cases.
- FE `whatsappTemplateService.ts`: added use-case + 3 param-variable entries with labels/desc.
- Verified via defaults API: use case + params present. tsc clean.

## Part 2 - Conversation-SLA reply panel → Respond redirect

File: `SlaTrackingConversationPanel.tsx`
- Replace the in-system reply Textarea + Send (lines ~154-177) with a **redirect CTA**:
 - When `respondInboxUrl` present: a note "Replies (including files) are sent from Respond"
    + a primary "Open in Respond" button (`window.open(respondInboxUrl)`).
 - Keep the message history (read-only) + refresh + existing ExternalLink.
- Drop `useSlaTrackingConversationReply` usage from the panel (keep history hook).
- Leaves the BE reply endpoint in place (still used by form-SLA chat windows / other surfaces);
  only the conversation-SLA panel stops exposing it. Confirm no other caller breaks.

## Part 3 - Resolve closes Respond conversation

- BE `RespondClient.close_conversation(identifier, category=None, summary=None)` in
  `integration_service.py` - mirror `send_message` (httpx POST, `_headers`, `_contact_api_identifier`).
- BE: a first-class **resolve** path for conversation SLA (not the admin test-override):
  on resolve, flip `is_resolved` (existing logic) **and** best-effort
  `close_conversation` for the contact's `respond_io_id`. Post-commit side effect →
  catch + warn, never raise (per the post-commit best-effort rule). Log to integration_log.
- FE: a Resolve action available to the **assignee** (not gated on test_override), wired to
  the new resolve endpoint, with `AlertDialog` confirm ("Mark as resolved" / cannot be undone).

## Part 4 - Guiding pending-task widget

Files: `MyPendingSLAWidget.tsx`, `list_my_pending` (sla_service.py), `MyPendingSLAItem` type.
- BE `list_my_pending`: add `respond_io_id` (from joined contact) to each item so FE can build
  the Respond inbox URL for conversation rows. (Form rows already route by entity.)
- FE row, per type:
 - Form SLA: status sub-line ("Awaiting your response") + action line
    ("Open <entity>, review & reply to customer") + **[ Open record ]** button → entity page.
 - Conversation SLA: action line ("Reply in Respond - files unsupported in-app") +
    **[ Open in Respond ]** (inbox URL) + **[ Resolve ]** (confirm dialog → resolve endpoint).
- Keep pagination. Keep empty/loading/error states.

## Tests (Phase 2)

- pytest: `close_conversation` builds correct URL/headers/body; resolve endpoint flips flag +
  calls close best-effort (close failure does not fail resolve); `list_my_pending` includes
  `respond_io_id`.
- vitest: `MyPendingSLAWidget` renders form-row CTA vs conversation-row CTA + Resolve; panel
  shows redirect CTA (no textarea) when inbox URL present.
- Playwright MCP: pending widget guiding rows; resolve flow; panel redirect.

## Verification

Browser verification blocked on local login (shared remote DB - won't reset real users).
Need user's local credentials to exercise in browser.
