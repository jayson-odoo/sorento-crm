# PLAN — Unified Conversation Composer + Smart 24h Send

**Status:** DONE — all 22 UAC met; tests green (BE 18 / FE 12); review findings fixed. Not yet committed (awaiting user verification). Working tree mixes this feature with unrelated ai-assistant-prompt-registry changes — isolate onto its own branch before PR.

### Live browser verification (2026-07-04, logged-in prod build on :3000)
- **UAC-6 ✅ live** — on a complaint whose 24h window is CLOSED, the composer textarea is **enabled** (not disabled); the old amber "24-hour window closed" blocking banner is **gone**.
- **UAC-7 ✅ live** — subtle hint renders: "Outside the 24h window — your message will be sent as a template."
- **UAC-9 ✅ live** — "Send template", "Attach view link", "Use technical response" all present.
- **UAC-11 ✅ live** — Settings → WhatsApp Templates shows both groups ("Status update templates", "Chat reply templates") and all 5 chat rows.
- **UAC-13 ✅ live (full FE→BE→route round-trip)** — typing + send on a closed-window complaint with no `complaint_chat` default returned backend `422 no_chat_template`; FE rendered the actionable notice + settings deep link `/integration-management/whatsapp-templates`. This exercised composer → `sendConversationMessage` → `POST …/conversation/send-message` → `send_chat_message_for` → window-closed (via chat_history fallback) → no valid default → typed 422 → FE notice.
- **Note (pre-existing, not a regression):** the conversation **list** endpoint 500s locally because Respond.io returns 401 (intentionally-wrong local creds); `get_window_state` degrades via its chat_history fallback so the send path is unaffected. Git confirms the list handler is untouched.
- Success template-send branch (UAC-2/14) is environmental locally (needs real Respond creds + an approved Meta template) → covered deterministically by pytest/vitest with mocked Respond.
**Owner:** Jayson
**Slug:** unified-conversation-composer-smart-send

---

## Problem

Every chat-window composer (complaint, stock inquiry, purchase request, sponsorship form) shows a scary amber **"24-hour window closed"** banner, disables the textarea, and forces the admin to manually click **"Send template"**. This confuses users. Conversation-SLA has no composer at all (view-only, punts to Respond).

The backend already has the smart switch (`send_text_or_template()` → within 24h plain text, outside 24h a WhatsApp template), but **only Purchase Request** uses it. Complaint + stock inquiry enqueue plain sends with no window check and silently drop when the window is closed.

**Goal:** the chat-window composer becomes *smart* — type + send always works. Within 24h it sends plain text; outside 24h it auto-wraps the typed text into a **separate, per-form chat template** (distinct from the existing status-update templates) that carries the **sender's name** so the contact knows who replied. Centralize into ONE shared composer + ONE backend choke point so all current and future composers inherit it.

---

## Decisions (from grill)

| # | Decision |
|---|----------|
| Q1 | Outside 24h, the typed text is delivered **inside a template body param** (`{{message}}`), not a fixed nudge. Template is admin-configurable to include a text variable. |
| Q2 | Chat templates are **per-form** (`complaint_chat`, `stock_inquiry_chat`, `purchase_request_chat`, `sponsorship_form_chat`) + one form-less `conversation_chat`. |
| Q3 | `sender_name` = the **logged-in admin's `users.name`**, auto from JWT. No static config, no per-send field. |
| Q4 | Composer **always enabled**. No blocking amber banner. A **subtle inline hint** shows only when outside 24h ("Outside 24h — will send as a template message"). |
| Q5 | Keep the manual **"Send template"** button as a secondary/advanced affordance. Keep "Attach view link" for entity composers. |
| Q6/Q13/Q14 | **Chat-window send is decoupled from `update-and-reply`.** It is a **pure message send** (no entity mutation — no status change, no `technical_team_response` write). It still *references* the entity (to resolve contact, chat use-case, view-link) and logs into that entity's chat history. `update-and-reply` stays untouched (already smart). Send-decision is **backend-authoritative** — no FE race, no retry. |
| Q7 | On the template path only, **sanitize** the typed text (collapse newlines→space, strip tabs, collapse space runs, truncate ~900 chars) to satisfy Meta's body-param rules, and **warn** when the text was actually altered. In-window plain sends keep full formatting. |
| Q8 | Chat use-case variable set: `message` (**mandatory**), `sender_name`, `contact_name`, view-link (`portal_url`). Saving a `*_chat` default is **rejected if no slot maps to `message`**; warn if `sender_name` unmapped. |
| Q9 | Window closed + no chat template configured for that form → **block send with an actionable message** ("No chat template configured for [form] — set one in Settings → WhatsApp Templates") + deep link. Manual "Send template" stays as escape hatch. Never silently reuse the update template. |
| Q10/Q11/Q12 | Scope: complaint, stock inquiry, purchase request, sponsorship form (rides PR panel + `PurchaseRequestHeader`), **and conversation SLA** (net-new composer, form-less). Conversation SLA uses `conversation_chat`, keys on the tracking row's `respond_contact_id`, **no view-link / no prefill buttons**. |
| Q15 | Add a new route to the **shared `build_chat_template_router`**: `POST /{entity_id}/conversation/send-message`. Every entity that mounts the router inherits pure smart-send. Each entity supplies a resolver returning `{contact_identifier, chat_use_case, view_link_builder}`. Conversation SLA gets a new resolver + must mount the router. |
| Q16 | The outgoing chat bubble shows the **rendered template body** (params filled) when `sent_as === "template"`, plus a small "sent as template" badge — so the admin sees exactly what the contact received. In-window shows the raw typed text. |
| Q17 | Pure send is **synchronous** (like PR) — returns `{sent_as, rendered_text, window_state}` so FE can render truthfully. Still writes chat-history + integration_log outbox (even on 401/fail). |
| Q18 | Settings `TemplateDefaultsSection` splits into two groups: **"Status update templates"** (existing 4) + **"Chat reply templates"** (new 5). Reuse `SetDefaultTemplateDialog` with the new variable set + `message` enforcement. `sender_name` is runtime-filled; config only picks the slot. |
| L1 | Conversation-SLA composer enabled only when tracking has a linked contact + user has conversation-SLA permission; else view-only "Open in Respond". |
| L2 | `sender_name` fallback for API-key/system principal = constant `"Customer Service"`. |
| L3 | Kill blocking UI centrally in `<SharedConversationComposer>`: remove textarea/button `disabled={windowClosed}`, drop the "send a template instead" placeholder, replace `WindowStateNotice` amber banner with the subtle hint + flatten warning. |

---

## User Acceptance Criteria (UAC)

Each line is a testable pass/fail. Verified end-to-end (FE + BE) before handoff.

### Chat-window send behaviour

- **UAC-1** In-window (contact replied < 24h ago): admin types a message in the chat composer, hits send → contact receives the **plain typed text**; the outgoing bubble shows the exact typed text; `sent_as === "text"`.
- **UAC-2** Out-of-window (> 24h): admin types a message → contact receives the form's **`*_chat` template** with `{{sender_name}}` = the logged-in admin's name and `{{message}}` = the typed text; `sent_as === "template"`.
- **UAC-3** The chat-window send **never mutates the entity** — no status change, no `technical_team_response`/`purchasing_response`/`reply_message` write. Verified by asserting the entity row is unchanged after a chat send.
- **UAC-4** The chat send **still references the entity**: message is logged into that entity's chat history and (entity mode) the `*_chat` template's view-link points to that entity's portal page.
- **UAC-5** `update-and-reply` (status-change action) behaviour is **unchanged** by this work.

### Composer UX

- **UAC-6** The composer textarea + send button are **never disabled** due to the 24h window (only disabled when `!canReply` or send in-flight). The old amber "24-hour window closed" blocking banner and "send a template instead" placeholder are **gone**.
- **UAC-7** When out-of-window, a **subtle inline hint** ("Outside 24h — will send as a template message") is shown; when in-window, no hint.
- **UAC-8** Out-of-window, if the typed text was altered to fit the template param (newlines/tabs/space-runs collapsed or truncated), a **flatten warning** is shown and `flattened === true`.
- **UAC-9** The manual **"Send template"** button still exists (secondary) on all entity composers; "Attach view link" still exists on entity composers.

### Sender name

- **UAC-10** `{{sender_name}}` resolves to the logged-in user's `users.name`. For API-key/system principal it falls back to the constant `"Customer Service"`.

### Config / templates

- **UAC-11** Settings → WhatsApp Templates shows two groups: "Status update templates" (existing 4) and "Chat reply templates" (`complaint_chat`, `stock_inquiry_chat`, `purchase_request_chat`, `sponsorship_form_chat`, `conversation_chat`).
- **UAC-12** Saving a `*_chat` / `conversation_chat` default with **no slot mapped to `message`** is **rejected** with a clear error; a warning shows if `sender_name` is unmapped.
- **UAC-13** Out-of-window send when the form has **no chat template configured** → send is blocked with an actionable `no_chat_template` message + deep link to the settings page; "Send template" remains available.

### Bubble display

- **UAC-14** After an out-of-window send, the outgoing bubble shows the **rendered template body** (params filled) with a "sent as template" badge — matching what the contact received.

### Coverage / centralization

- **UAC-15** All 4 form composers (complaint, stock inquiry, purchase request, sponsorship form) render the **single** `<SharedConversationComposer>` — no duplicated composer JSX remains.
- **UAC-16** Conversation-SLA gains a working composer (`mode="conversation"`, form-less: no view-link, no prefill buttons) using `conversation_chat`, keyed on the tracking's `respond_contact_id`; enabled only when a contact is linked + user has permission, else view-only "Open in Respond".
- **UAC-17** The pure-send route is one shared route on `build_chat_template_router`; adding a future composer requires only mounting the router + a resolver.

### Reliability

- **UAC-18** Every send writes an `integration_log` outbox row on **success AND failure** (incl. 401 with wrong creds); the send is synchronous and returns `{sent_as, rendered_text, flattened, window_state}`.
- **UAC-19** Chat-history + outbox writes are best-effort post-send — a failure there does not 500 a send that actually delivered.

### Tests (Phase 2)

- **UAC-20** pytest: route happy path, auth denial, validation error, window-open vs window-closed branch, `no_chat_template` 422, sanitize, outbox-written-on-fail.
- **UAC-21** vitest: composer renders in-window / out-window / flatten-warning / no-template-error / conversation-mode states.
- **UAC-22** playwright: FE→BE→DB round-trip for a chat send with network assertion on `POST …/conversation/send-message`.

---

## Post-review UX iteration — inline template-fill composer

User feedback after first cut: instead of a plain textbox + an after-the-fact "contact received" preview, render the template **in the composer** with a fill-in field. Implemented:

- **Out-of-window + template configured:** composer renders the `*_chat` template body inline — non-message params (sender name, contact, links) resolved read-only, the `message` slot as an editable field. Header names the template + warns line breaks are removed. Send posts only the message text (backend still authoritative).
- **Live flatten warning:** fires the instant the message field contains a real newline/tab/space-run (not after send). Literal `\n` text is not a control char → correctly no warning.
- **Out-of-window + no template:** the actionable "configure a chat reply template" notice, shown **upfront** (not on send).
- **In-window:** unchanged plain textbox (raw send). Dropped the post-send "sent as template" box.
- **New BE endpoint** `GET /{entity}/conversation/chat-template` on the shared router (4 mounts) — DB-only (no Respond.io call): returns `{configured, template_name, body_text, slots{index → {variable, value, editable}}}` with `sender_name`/`context_builder` resolved server-side.
- **Delivery-status catch-up:** after send the panel refetches at 0s + 6s + 15s so the outgoing clock → delivered/read ticks update (was 0 + 1.6s).
- Verified live (complaint 9f0cfa98): template-mode renders with the inline field, live flatten warning fires on a real newline. Tests: BE 21, FE composer 11, dialog 5 — all green.

## Code review — findings & resolution (Phase 3)

- **BLOCKER (fixed):** in-window chat sends routed through `send_text_or_template`, whose in-window branch renders the template *body* (a "uniformity" behaviour meant for status-update templates) and delivers that as plain text — so a configured no-button `*_chat` template caused the contact to receive the wrapped, newline-flattened text in-window, violating UAC-1/UAC-8. Fix: `send_chat_message_for` no longer calls `send_text_or_template`; it sends the **raw typed text** via `RespondClient().send_message` in-window and only builds a template on the closed-window path. A non-mocked regression test asserts raw-text delivery in-window even when a chat template is configured.
- **SHOULD-FIX (fixed):** `flattened` was returned unconditionally → false "line breaks removed" warning in-window. Now `flattened` is only ever `True` on the template path.
- **SHOULD-FIX (fixed):** `context_builder` was pre-called eagerly + unguarded in the route (a builder error would 500 an otherwise-valid send, and it wrote a view-token on every send incl. in-window). Now the callable is passed through and invoked **lazily + guarded** inside `send_chat_message_for`, **only** on the out-of-window path.
- **NIT (resolved by the rewrite):** double window evaluation — now a single `get_window_state` call drives the branch, so the `no_chat_template` 422 can't be downgraded to a generic 502 on a boundary flip.
- **NITs (accepted, no change):** coarse authz on the send route matches the pre-existing window-state/template routes (conscious, consistent); the `id:` endpoint string mirrors `send_manual_template_for`.
- **Verified correct by review:** `respond_contact_id ≠ respond_io_id` (identifiers built from `respond_io_id`); outbox best-effort; FE error extraction from `{message, detail, code}`; UAC-5 (update-and-reply untouched); UAC-3 decouple (composer calls `sendConversationMessage`, not any update-and-reply mutation); routing/mount + no route-shadowing.

## Design

### Backend

**Choke point:** `app/services/respond_messaging_service.py :: send_text_or_template(db, identifier, text, use_case, context_vars)`.

- Already: window open → plain text; closed → `send_template_for_use_case(use_case)`.
- Extend so the closed path, for `*_chat` / `conversation_chat` use-cases, renders params from the template's `param_mapping` against `context_vars = {message (sanitized), sender_name, contact_name, view_link?}`.
- Sanitize `message` for the template path only; surface whether it was altered so the route can echo a `flattened: true` flag.

**Shared router:** `app/api/v1/_respond_chat_template_routes.py :: build_chat_template_router`.

- New route `POST /{entity_id}/conversation/send-message`, body `{ text: str }`.
- Resolver contract per entity: `{ contact_identifier, chat_use_case, view_link_builder | None, contact_name }`.
- Route flow: resolve → `sender_name = current_user.name or "Customer Service"` → `send_text_or_template(...)` → write chat-history + integration_log outbox → return `{ sent_as, rendered_text, window_state, flattened }`.
- If closed + no chat template default configured → 422 with a typed `no_chat_template` error carrying the settings deep link.
- Extend existing resolvers (complaint / stock_inquiry / purchase_request / sponsorship_form) with `chat_use_case`. Add a **new conversation-SLA resolver** (tracking_id → `respond_contact_id`, `conversation_chat`, no view-link) and mount the router under the SLA conversation-tracking prefix.

**Template defaults:** `respond_template_defaults` gains 5 new use-case rows. Endpoint `PUT /integrations/respond/template-defaults/{use_case}` enforces `message` mapping for `*_chat` / `conversation_chat`.

### Frontend

**New shared component** `components/common/conversation/SharedConversationComposer.tsx`:

- Props: `entityType`, `entityId`, `canReply`, `mode: "entity" | "conversation"`, `technicalTeamResponse?`, `onGetViewLink?`, `contactName?`, `contactPhone?`.
- Owns: textarea + send button (always enabled when `canReply`), the `useConversationWindowState(entityType, entityId)` hook (hint only), the subtle out-of-window hint + flatten warning, the "Send template" secondary button, and (entity mode only) "Attach view link" + "Use … response" prefill.
- Send → `POST /{prefix}/{entityId}/conversation/send-message` → on success append the returned `rendered_text` bubble (with "template" badge if `sent_as==="template"`) + refetch.
- `no_chat_template` 422 → inline actionable message + deep link; keep "Send template" available.

**Refactor** the 3 existing `*ConversationPanel.tsx` to render `<SharedConversationComposer>` (delete duplicated composer JSX/handleSend/window-state query). **Add** a composer to `SlaTrackingConversationPanel.tsx` in `mode="conversation"`.

**Settings:** `TemplateDefaultsSection.tsx` → two groups; `SetDefaultTemplateDialog.tsx` → new variable set + `message`-required validation.

---

## Contract

```
POST /api/v1/<entity-prefix>/{entityId}/conversation/send-message
Request:  { "text": string }
Response: {
  "sent_as": "text" | "template",
  "rendered_text": string,        // what the contact actually received
  "flattened": boolean,           // typed text altered to fit template param
  "window_state": { "open": boolean, "last_incoming_at": string | null }
}
Errors:
  422 no_chat_template  -> { "code": "no_chat_template", "settings_url": "/integration-management/whatsapp-templates" }
```

---

## Critical files

- BE: `app/services/respond_messaging_service.py`, `app/api/v1/_respond_chat_template_routes.py`, entity resolvers (complaints, procurement stock_inquiries + purchase_requests, sla conversation-tracking), `app/models/respond_template.py`, `app/api/v1/integrations/respond_templates.py`, new Alembic migration (5 use-case rows are data, not schema; enforce in service).
- FE: new `components/common/conversation/SharedConversationComposer.tsx` + `useConversationWindowState` hook; refactor `ComplaintConversationPanel.tsx`, `StockInquiryConversationPanel.tsx`, `PurchaseRequestConversationPanel.tsx`; add composer to `SlaTrackingConversationPanel.tsx`; `whatsapp-templates` settings `TemplateDefaultsSection.tsx` + `SetDefaultTemplateDialog.tsx`; `services/whatsappTemplateService.ts`.

---

## Three-phase breakdown

**Phase 1 — FE prototype (mocks).** Build `<SharedConversationComposer>` against a stubbed send hook returning `sent_as: text|template`, `flattened`, `no_chat_template`. Wire all 4 form panels + the conversation-SLA panel to it. Verify every state via Playwright MCP through the sidebar: in-window plain, out-window template (rendered bubble + badge), flatten warning, no-template-configured actionable error, conversation-SLA form-less mode. Screenshot golden + edge paths. Document the contract at the top of `whatsappTemplateService.ts`.

**Phase 2 — BE wiring + tests.** Add the `send-message` route to the shared router + resolvers (incl. conversation SLA) + `send_text_or_template` chat-param rendering + sanitize + template-default `message` enforcement + 5 use-case rows. Wire FE off mocks. Tests: pytest (route happy/auth-deny/validation, window open vs closed, no-template 422, sanitize, outbox written on fail); vitest (composer states); playwright (FE→BE→DB round-trip, network assertion on `send-message`).

**Phase 3 — Code review.** `/code-review`, address, open PR with Phase 1 screenshots + Phase 2 tests + this contract.

---

## Risks / watch-items

- **Meta body-param limits** (no `\n`/`\t`/4+ spaces, length cap) — sanitize handles it; flatten warning keeps admins honest. Watch Respond.io rejection codes and log them to the outbox.
- **`respond_contact_id ≠ respond_io_id`** (CLAUDE.md) — resolvers must resolve via `RespondContact` before building identifiers.
- **`create_event_log` naive-datetime MYT shift** — N/A here (no event log on pure chat send), but reuse `_to_aware_utc()` if any timestamp is passed downstream.
- **Post-commit side effects best-effort** — chat-history + outbox writes after the send must catch+warn, never 500 a successful send.
