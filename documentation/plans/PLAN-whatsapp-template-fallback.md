# PLAN: WhatsApp Template Sync + 24h-Window-Aware Sending

**Status:** Phase 1 + Phase 2 complete (2026-06-08). Backend merged (migration 226, sync service, window-aware send refactor, 4 send sites + manual chat template send), FE off mocks against the live workspace, all three test suites green (pytest 19, vitest 11, playwright e2e 1 - env-gated). Phase 3 (code review) pending. Spike confirmed Respond.io shapes: channels `GET /v2/space/channel`, templates `GET /v2/space/channel/{id}/template`, template send `POST /v2/contact/{id}/message` with `channelId` + `message.type=whatsapp_template` + full body text + positional `parameters`.
**Owner:** Claude + Jayson
**Created:** 2026-06-07

## Problem

Respond.io accepts outbound WhatsApp messages with a success response even when the
contact's 24-hour messaging window is closed - the message is then silently never
delivered. This hits every CRM auto-response (complaint decisions, stock inquiry
replies/rejections, purchase request + sponsorship form status updates) and the
admin Chat Records manual send. Outside the 24h window WhatsApp only delivers
pre-approved **message templates**, which the CRM cannot send today.

## Solution summary

1. Sync WhatsApp message templates (and channels) from the Respond.io workspace
   into the CRM.
2. Before every outbound send, check whether the contact's 24h window is open
   (last **incoming** message < 23h ago, via Respond API).
   - Open → send the composed plain-text message (today's behaviour).
   - Closed → send the configured **default template** for that use case, with
     params filled from a per-template mapping. No reactive fallback - the branch
     is decided up front.
3. In Chat Records, gate the plain-text input on window state and add a manual
   "send template" flow mimicking Respond.io (pick template → fill params →
   preview → send).

## Decision record (from grilling session 2026-06-07)

| # | Decision |
|---|----------|
| D1 | Send paths in scope: complaint decision (RQ task), stock inquiry reply/reject (RQ task), purchase request status update ×2 sync sites in `procurement_service` (covers sponsorship forms - shared table), Chat Records manual send. |
| D2 | **Pre-check, not fallback.** Respond returns success even for undeliverable sends, so reactive fallback is impossible. Deterministic branch on window state before sending. |
| D3 | Window source of truth = Respond API `RespondClient.list_messages` (newest first), scan first page for latest `traffic: incoming`. Margin: treat window as **23h**, not 24h. No incoming message in page → treat closed. `chat_history` is NOT authoritative (n8n skips ingest when `is_human_intervened`); it is only the degraded fallback when the Respond API call errors. API error → check `chat_history` latest incoming → still nothing → treat closed (send template). |
| D4 | New `respond_channels` table synced from Respond list-channels API per active `respond_workspaces` row. Prod today: 1 workspace, 1 WhatsApp channel; design stays multi-ready. Template send payload requires `channelId`. |
| D5 | New `respond_message_templates` table. Sync = upsert by (channel, respond template id); hard-delete rows gone from API. All statuses stored (`approved`/`pending`/`rejected`) for admin visibility; only `approved` selectable as default or manually sendable. Sync triggers: settings-page "Sync templates" button + daily job on the existing background scheduler. If the configured default template disappears or loses approval: UI warning flag on the settings page; auto-sends in closed-window state skip sending entirely + write a `failed` `integration_log` row (plain text into a closed window is a silent drop; an unapproved template is an API error - neither is better). |
| D6 | Per-use-case defaults, **4 keys**: `complaint`, `stock_inquiry`, `purchase_request`, `sponsorship_form` (sponsorship shares the `purchase_requests` table but gets its own key - cheap now, painful to split later). Param mapping configured per default: each `{{n}}` slot maps to a variable from a fixed catalog - `contact_name`, `entity_number`, `status`, `reason`, `portal_url`, `message`. `message` = the full composed update text so the original content survives inside a param. |
| D7 | Param sanitization (WhatsApp rejects newlines/tabs/4+ spaces in params): newlines → `" | "`, collapse whitespace runs, truncate ~900 chars with `…`, keep `*bold*`/`_italic_` markers. |
| D8 | Chat Records UX mimics Respond.io: window state fetched per contact (cached ~60s); closed → plain input disabled with hint "24h window closed - send a template". Template button always available: dialog → select approved template (search + body preview) → one free-text input per `{{n}}` (required) → live rendered preview → send. **No param prefill** in manual flow - defaults/mapping are auto-send machinery only. |
| D9 | Chat panel lists messages live from Respond API (`activities_service.list_messages`), so template sends appear automatically. `_respond_item_to_message` must learn the `whatsapp_template` message type and render the filled body text. |
| D10 | Settings page at `/integration-management/whatsapp-templates` (Integration Management sidebar group). Admin-only RBAC slugs at launch. Param-mapping UI lives inside the set-default flow (select template → mapping form appears). |
| D11 | One choke point: `respond_messaging_service.send_text_or_template(db, contact, text, use_case, context_vars)` - window check → plain send OR resolve default → fill params → template send → `integration_log` either way (template sends marked distinctly in the payload). All 4 auto-send sites refactor onto it. Chat manual send uses the window check for UI gating only - no auto-template substitution. |
| D12 | Defaults stored in dedicated `respond_template_defaults` table (`use_case` unique enum, FK → `respond_message_templates.id`, `param_mapping` JSONB, timestamps). FK integrity lets sync flag dangling/rejected defaults cheaply. |
| D13 | **Remove** the stock inquiry `verify_delivery` post-send polling (`get_message` ×3) entirely. With the window pre-check its main purpose is gone; both RQ tasks become uniform fire-and-log. |

## Expected API contract (Phase 1 output, locked for Phase 2)

> To be finalized in `sorento_crm_frontend/services/whatsappTemplateService.ts` during
> Phase 1. Initial sketch:

```
GET    /api/v1/integrations/respond/templates                 → DataGrid list (buildDataGridParams)
POST   /api/v1/integrations/respond/templates/sync            → { synced: n, deleted: n, channels: n }
GET    /api/v1/integrations/respond/template-defaults         → [{ use_case, template_id, template_name, param_mapping, is_valid }]
PUT    /api/v1/integrations/respond/template-defaults/{use_case} → { template_id, param_mapping }
DELETE /api/v1/integrations/respond/template-defaults/{use_case}

GET    /api/v1/activities/{entity_type}/{entity_id}/window-state?contact_id= → { open: bool, last_incoming_at, checked_at }
POST   /api/v1/activities/{entity_type}/{entity_id}/template-messages        → { contact_id, template_id, params: { "1": "...", ... } }
```

## Open verification items (Phase 2 spike, before coding)

- Exact Respond.io API shapes (docs are JS-rendered; verify against live workspace):
  - List channels endpoint + response.
  - `GET /v2/space/channel/{channelId}/message_templates` (list message templates)  - 
    pagination, component JSON shape, status values.
  - Template send payload on `POST /v2/contact/{identifier}/message`  - 
    `whatsapp_template` message type, channelId placement, param format.
- How template messages appear in `list_messages` items (for renderer support, D9).
- WhatsApp param length limits (truncation threshold in D7).

## Phase 1 - Frontend prototype (mocks only, no backend changes)

- [ ] `/integration-management/whatsapp-templates` page:
  - Workspace/channel info card.
  - "Sync templates" button (mock: spinner → toast).
  - Templates DataGrid (house standards: fixed layout, resizable, explicit sizes,
    truncate+title): name, language, category, status badge, body preview, synced_at.
  - Default-template config section: 4 use-case rows; set-default flow opens
    template picker → param-mapping form (`{{n}}` → variable dropdown) → save.
  - Mock states: populated list, pending/rejected rows, "default no longer
    approved" warning, empty/never-synced.
- [ ] Chat Records (ActivitiesNotesPanel chat):
  - Window-closed banner + disabled plain input + hint.
  - Template-send dialog: searchable picker with body preview → required param
    inputs → live preview → send. States: sending, success, error.
- [ ] Document the API contract at the top of `services/whatsappTemplateService.ts`.
- [ ] Playwright MCP verification via sidebar navigation; screenshots of golden
  path + edge states.
- [ ] No backend code. No tests yet.

## Phase 2 - Backend + wiring + tests

Backend:
- [ ] Spike: verify Respond.io API shapes (see open items) against the live workspace.
- [ ] Migrations: `respond_channels`, `respond_message_templates`,
  `respond_template_defaults`.
- [ ] `RespondClient`: `list_channels()`, `list_message_templates(channel_id)`,
  `send_template_message(identifier, channel_id, template, params)`.
- [ ] Template sync service + `POST .../templates/sync` endpoint + daily job on the
  existing background scheduler. Dangling-default flagging.
- [ ] Window-check helper (D3): Respond `list_messages` scan → 23h compare (UTC) →
  `chat_history` degraded fallback → default closed.
- [ ] `respond_messaging_service.send_text_or_template(...)` (D11) with param
  resolution per use-case context + sanitization (D7) + distinct integration_log
  marking.
- [ ] Refactor 4 auto-send sites onto it; **delete** `verify_delivery` polling (D13).
- [ ] Chat endpoints: window-state GET, template-message POST;
  `_respond_item_to_message` template-type rendering (D9).
- [ ] RBAC slugs (admin-only), menu entry, module guard wiring.

Frontend:
- [ ] Replace mocks with real hooks/services/api-client; delete unused fixtures.

Tests (land here, not deferred):
- [ ] pytest: sync upsert/delete, window-check branches (open/closed/API-error/
  no-history), send_text_or_template branching + skip-on-invalid-default,
  endpoints happy/auth-denial/validation.
- [ ] vitest: settings page states, param-mapping form, template dialog states,
  chat input gating.
- [ ] Playwright e2e: sync → set default with mapping → manual template send from
  an entity chat panel.
- [ ] Playwright MCP re-verification against the live stack.

## Phase 3 - Code review

- [ ] `/code-review` (or `ultra` if diff is big) on the merged branch; fix findings.
- [ ] PR with Phase 1 screenshots, contract-vs-shipped check, PR-CHECKLIST.md pass.
