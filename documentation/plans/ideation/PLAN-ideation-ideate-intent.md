# PLAN - Sorento `ideate` intent + Ideas iframe host

**Status:** Planning (UAC written first; grilled against the sorento AI brain + program spine; no code yet - 2026-07-18).
Multi-modal capture (voice/image/video/file) grilled + folded in 2026-07-20 → decisions DC-1..DC-10, UAC Group F
(AC-60..AC-70), Phase 2f. Blocked on spine §5.1 (`attachments[]` + `discard_draft_id`) + the n8n contract.
**UAC:** `ideation-ideate-intent-acceptance-criteria.md` (this plan fulfils it).
**Program spine (authority on contracts):** `foundryx-shared-service/documentation/plans/ideation/PLAN-ideation-to-delivery-program.md`
 - this plan keys back to **§5.1 (`create_idea`)**, **§5.2 (`session_vars.ideation`)**, **§5.3 (embed SSO + product-domain link)**, and **D6/D7/D8/D19**.
**Classification:** Additive CORE change to the existing CRM WhatsApp brain (D6) + one net-new external
endpoint + a FE iframe host. **Not** a new tenant module (it extends the current brain, not App-Store enablement).
**Sequencing:** choice **X** (D19) - build into the *current* sorento brain now; the small ideate logic is
absorbed when the assistant is later ported to shared-service (Phase 0, deferred).

> **Contract discipline.** Every JSON shape / field / status string below is copied from §5 and must
> stay byte-identical. If the shared-service team changes §5, change the spine first, then this plan.

---

## 1. What ships on the sorento side (and what does not)

| In scope (sorento) | Out of scope (other repos) |
|---|---|
| `ideate` intent in the parser schema + router (additive, guarded) | `create_idea` tool internals, dedup, templates, Idea entity → **shared-service** |
| New external **brain-path** endpoint that invokes `create_idea` + manages `session_vars.ideation` | n8n routing (`domain=ideate` → call the endpoint, relay `reply_text`) → **n8n plan** |
| Workspace↔Product binding (`ideation_product_id`) + config settings | Product/embed-connection provisioning → **shared-service** |
| Ideas sidebar + `/ideas` + `/ideas/{id}` iframe host + embed-session mint (SSO) | The ideation board/detail/grill UI rendered *inside* the iframe → **shared-service** |

The `create_idea` **intake logic lives in shared-service** (D7); sorento only *detects → calls → carries the
pointer → relays* (D8). n8n stays **thin** (§5.5): it classifies, calls this endpoint, and relays.

---

## 2. Grounding in the current codebase (real files)

- **Parser contract:** `app/schemas/ai_semantic_parser.py` - `Intent` literal + `PARSE_RESULT_JSON_SCHEMA`
  (OpenAI strict + Anthropic `input_schema`). `intent` is the router branch selector; `entities.domain`
  is a **data_query bucket** only. → We add `ideate` as an **intent**, not a `domain` value (see Decision D-1).
- **Parser call + router:** `app/services/ai_assistant_service.py` - `_parse_turn()` (single schema-forced
  LLM call, retry-then-`fallback_parse`), `_route()` (pure switch, `_LOW_CONFIDENCE_FLOOR = 0.4`),
  `respond()` (orchestration; capability/clarify/confirm short-circuits are the template for a new branch).
- **Parser prompt:** `app/services/ai_prompt_registry.py` - key `semantic_parser` (`_semantic_parser_fallback`).
  The intent menu in that prompt must gain an `ideate` line.
- **session_vars store:** `app/services/conversation_variables_service.py`
  (`get_for_contact` / `overwrite_for_contact`, keyed by `respond_io_id`; **whole-blob overwrite**) and
  `app/api/v1/external/conversation_variables.py` (API-key auth via `get_external_api_user`, writes an
  `integration_log`). The new endpoint reuses this service and mirrors its logging.
- **Workspace:** `app/models/respond_workspace.py` (one `is_default` workspace;
  `app/services/respond_workspace_service.py` resolves it). No product binding today → add one.
- **Shared-service call:** an `httpx` server-to-server POST to `{ideation_shared_service_url}/ideation/intake/create-idea`
  (workspace/integration-key auth) - **NOT** MCP (D-A5/§8-R3: shared-service has no MCP write server;
  `sorento_crm_mcp` is read-only). `MCPRuntimeClient` is unrelated to this path.
- **UUID arg coercion:** `_coerce_uuid_args` exists for **LLM-passed** names→UUIDs; the ideate endpoint builds
  args deterministically, so it does not depend on it (AC-18).
- **FE menu:** `sorento_crm_frontend/config/menu.config.tsx` (`{ title, icon, path, children }` items).
- **No embed/SSO exists in sorento today** - the iframe host + assertion→embed-session is net-new here.

---

## 3. Decision log

- **D-1 - `ideate` is an `intent`, not a `domain`.** §5.5 phrases classification as "`domain=ideate`", but the
  sorento parser reserves `entities.domain` for the **data_query** bucket (stock/orders/…), only consulted on
  `intent="data_query"`. Adding `ideate` there would be a semantic no-op. D6 itself says "a new **ideate
  intent**". So sorento realises the concept as `intent="ideate"` - a new router branch. The **contract shapes
  in §5.1/§5.2 are unchanged**; only the parser's internal representation adapts. Documented so the n8n plan and
  shared-service parser prompt agree on the label.
- **D-2 - Brain path = a new external endpoint, not `respond()`.** `AIAssistantChatService.respond()` is the
  **in-app web** brain (keyed by `user_id` + `AIAssistantConversation`); it has no `respond_contacts` row and no
  `session_vars`. Intake is WhatsApp (D6), whose state is `respond_contacts.session_vars`. So the ideate brain
  path is a **new external endpoint** `POST /api/v1/external/ideation/turn` that n8n calls. `respond()` still
  recognises `ideate` but only to redirect web users to `/ideas` (AC-06) - never to call `create_idea`.
- **D-3 - Sorento derives `product_id` from the workspace binding and passes it.** §5.1 lists `product_id` as
  an input and says it is "derived … from the workspace↔Product binding (never from the human)". Sorento owns
  that binding (`respond_workspaces.ideation_product_id`) and passes the id. `product_domain_base` is a
  shared-service Product attribute; sorento never composes the link - it relays the `link` §5.1 returns (§5.3).
- **D-4 - `session_vars.ideation` is namespaced + merge-written.** The store overwrites the whole blob, so the
  endpoint does read-modify-write: set/clear only the `ideation` key, preserve all CRM keys (AC-16). Cleared on
  `complete`/`duplicate` (§5.2). Pointer-only (`draft_id`, `missing`, `updated_at`); the durable draft lives in
  shared-service (D8).
- **D-5 - Fail-closed + resilient.** No `ideation_product_id` → no `create_idea` call, friendly reply (AC-31).
  Shared-service MCP outage → graceful `reply_text`, never a 500 that breaks n8n's send sub-flow (AC-19). Always
  write an `integration_log` (AC-20), mirroring the "always log outbox" rule.
- **D-6 - Live-flow safety is the gating risk.** The only edit to the production consume path is the parser
  enum + router branch. Guard: `ideate` must clear the `0.4` floor or it demotes to the agent loop (AC-04); a
  no-regression golden set proves no CRM intent flips to `ideate` (AC-03). Everything else is net-new surface.
- **D-7 - Embed SSO is net-new; generalise from omnichannel 11H.** Sorento BE mints a signed assertion →
  `POST {shared_service}/embed/session` → embed token; FE iframes `{shared_service}/embed/ideas[/{id}]`
  (§5.3). Token passed to the iframe per the embed framework (query param / `postMessage`), never logged.
- **D-8 - No UUIDs in FE UI.** `/ideas/{id}` uses the idea id only as an opaque route param (the canonical
  product-domain link shape, §5.3); no UUID is rendered as visible text. Human-readable content is the iframe's.

### Multi-modal capture decisions (voice / image / video / file) - grilled 2026-07-20, UAC Group F

The capture problem is **binding**, not media handling: WhatsApp delivers a *stream of separate messages*
with no submission boundary, and media carries no intent of its own - it inherits the intent of the text it
belongs with (image-then-"idea" vs image-then-"complaint" are the same shape, opposite binding).

- **DC-1 - Lookback + confirm-gate, NOT an aggregation window.** Solve the "media arrived before the idea
  text" case by a **backward lookback on the first `ideate` turn**, contained to the `ideate` branch only - 
  zero change to the complaint/order/stock consume paths (respects D-6 live-flow safety). An aggregation
  window would wrap the entire production classifier in a timer; rejected.
- **DC-2 - Numbered menu, last 10 inbound, backward-only; subsequent auto-attach.** Menu lists type icon +
  filename + relative time (no thumbnails - WA text). Media arriving *after* the draft is open auto-attaches
  (context unambiguous); the user removes a wrong one in the iframe.
- **DC-3 - Pull from Respond List Messages; no buffer.** On `ideate`-open, the endpoint calls Respond's
  List Messages via the existing `RespondClient` and filters recent inbound media. **Because the human picks
  via the menu, there is no park endpoint, no `ideation_media_buffer` table, and no `consumed_by` tracking** - 
  a complaint's photo may appear in the menu; the user simply doesn't select it. n8n stays thin (unchanged).
- **DC-4 - Snapshot picked media to durable storage.** Respond CDN URLs expire, but the idea links them
  long-term. On confirm, the endpoint fetches the *picked* bytes and stores them via `storage_router`
  (R2/S3, existing attachment infra) → passes the **durable URL** to `create_idea`. Only picked media, at
  attach-time.
- **DC-5 - STT at n8n (Whisper).** A voice note carries the idea words but has no text to classify, so it is
  transcribed **before** classification: n8n Whisper → transcript = `message_text` → normal classify →
  `/turn`. Current-message voice auto-attaches as content (`attachments[type=audio]`); a lookback voice goes
  through the menu.
- **DC-6 - Vision caption at backend (OpenAI, reused).** The assistant already runs on `openai_api_key`
  (`config.provider=="openai"`). Images are vision-captioned backend-side at snapshot-time (reusing the
  already-downloaded bytes); caption is stored on the attachment **and** folded into `message_text` so
  `create_idea`'s semantic collection/dedup sees the visual content. Failure/no-key → attach-without-caption
  (graceful, D-5).
- **DC-7 - Routing via `pending_media` + parser position-extraction, no LLM classification of the reply.**
  When the menu is shown, `session_vars.ideation.pending_media` holds the candidates. On the next turn n8n's
  parser **extracts reference-positions** (numbers / "all" / "none") - a narrow, reliable NLP task, *not*
  full classification - gated by `pending_media` being set. Positions present ⇒ deterministic selection route
  to `/turn`; **no position ⇒ not a selection**, the turn falls through to normal classify (a mid-selection
  CRM interrupt is never swallowed). No TTL on `pending_media`.
- **DC-8 - Media menu appended to the first reply (front), then field collection.** Recency is the signal - 
  ask while the files are fresh; one clean selection turn, then `create_idea`'s field questions.
- **DC-9 - Unified `attachments[]`, retire `audio_attachment_ref`.** §5.1 input gains
  `attachments: [{ source_msg_id, url, type, filename?, caption? }]`; `source_msg_id` is the idempotency key
  (dedupe on re-run). One array covers audio/image/video/file. **Spine change - do §5.1 first.**
- **DC-10 - No draft-resume TTL; semantic `is_new_idea` restart.** Time is the wrong discriminator (a user
  may genuinely return to the same idea later). Default = **always resume** the open draft. The only reset is
  an explicit, *semantic* `is_new_idea` flag (parser-extracted with the open-draft topic as context, not
  keyword-matched): true → clear the pointer, `create_idea` **without `draft_id`** + `discard_draft_id` =
  the abandoned draft so shared-service drops the phantom.

---

## 4. Contract snapshots (copied from §5 - do not drift)

**`create_idea` HTTP endpoint (§5.1, revised - DC-9/DC-10)** - sorento calls this on shared-service (server-to-server, no MCP) each ideate turn:
```
Input:  { product_id, submitter (phone E.164), message_text,
          attachments?: [{ source_msg_id, url, type:"image"|"video"|"file"|"audio", filename?, caption? }],
          draft_id?, discard_draft_id? }
Output: { draft_id, status: "collecting"|"complete"|"duplicate",
          captured: {...}, missing: ["field", ...], reply_text, link?, duplicate_of? }
```
- `attachments[]` replaces the retired singular `audio_attachment_ref`; `source_msg_id` (Respond message id)
  is the **idempotency key** - repeated attach of the same media never duplicates (DC-9).
- `discard_draft_id` drops an abandoned draft on an `is_new_idea` restart (DC-10).
- **Spine dependency:** these two fields are a §5.1 change - update `PLAN-ideation-to-delivery-program.md` §5.1
  FIRST, then this plan (contract discipline).
- No `draft_id` on turn 1 → tool creates a draft Idea (status `draft`) and starts collection.
- `status="complete"` → `link` = product-domain deep link (§5.3); caller clears `session_vars.ideation`.
- `status="duplicate"` → `duplicate_of`; caller relays "similar to … upvoted".
- Idempotent on repeated `draft_id` (enrich, never duplicate).

**`session_vars.ideation` (§5.2)** - sorento owns the blob; shape is the contract:
```json
{ "ideation": { "draft_id": "<uuid>", "missing": ["module","who"], "updated_at": "<iso>" } }
```
Written after each `create_idea`; **cleared** on `complete`/`duplicate`. Pointer only (D8). Persisted via the
existing conversation-variables path (namespaced `ideation`, must not clobber CRM keys).

**Product-domain link + embed SSO (§5.3):**
- Link = `{product_domain_base}/ideas/{idea_id}` (e.g. `https://fe-sorento.foundryx.my/ideas/123`) - never a
  shared-service URL. Sorento `/ideas/{id}` renders `<iframe src="{shared_service}/embed/ideas/{id}">`.
- Sorento BE mints a signed assertion for the logged-in user → `POST {shared_service}/embed/session` → embed
  token (`typ="embed"`). Connection `allowedOrigins` includes the sorento origin; `frame-policy` permits the frame.

---

## 5. Three-phase breakdown

### Phase 1 - FE prototype (mocks first)  → AC-40..AC-45 (FE), AC-06

Build the Ideas iframe host against a **stubbed embed session** before the BE mint endpoint exists.

- Add an **"Ideas"** item to `config/menu.config.tsx` (`{ title, icon, path:'/ideas' }`), reachable by
  clicking through the sidebar (AC-40).
- `app/(protected)/ideas/page.tsx` (board) and `app/(protected)/ideas/[id]/page.tsx` (detail): render an
  `<iframe>` whose `src` + token come from a stubbed `useIdeationEmbedSession()` hook returning a synthetic
  `{ iframe_url, token }`. Cover loading / error / retry states (AC-44). No UUID shown as text (AC-08/D-8).
- Document the **expected BE contract** at the top of `services/ideationService.ts`:
  `POST /api/v1/integrations/ideation/embed-session {idea_id?} → { iframe_url, token, expires_at }`.
- Verify with Playwright MCP: sidebar → Ideas → board iframe; simulate `/ideas/{id}`; screenshot golden +
  error state. No backend code this phase.

### Phase 2 - Backend wiring, TDD (test-first)  → AC-01..AC-05, AC-10..AC-20, AC-30..AC-32, AC-42/43, AC-50..AC-52

Red → green → refactor. Write failing tests first, especially the parser golden sets and session_vars transitions.

**2a. Parser (Group A).**
- `app/schemas/ai_semantic_parser.py`: add `"ideate"` to `Intent`, to the enum + description in
  `PARSE_RESULT_JSON_SCHEMA`. Keep strict-mode validity (AC-01).
- `app/services/ai_prompt_registry.py`: add an `ideate` line to the `semantic_parser` intent menu
  (new immutable version, movable label).
- `_route()` in `ai_assistant_service.py`: add an `ideate` branch (`intent=="ideate"` & `confidence≥0.4`);
  low-confidence demotes to agent (AC-04). In `respond()`, on `ideate` for the web brain, return the redirect
  to `/ideas` (AC-06).
- Tests (`[T]`): paraphrase table for AC-02, no-regression corpus for AC-03, floor demotion AC-04.

**2b. Workspace↔Product binding + config (Group C).**
- Alembic migration (idempotent, chained on the committed main head - see the dual-head/down_revision lessons):
  add nullable `respond_workspaces.ideation_product_id` (UUID text, server-side only).
- `app/config.py`: `ideation_shared_service_url`, `ideation_intake_api_key`,
  `ideation_embed_signing_secret`, `ideation_embed_connection_id` (all `.env`-driven, dormant when blank).
  (No `ideation_mcp_url` - the create_idea call is HTTP, not MCP.)

**2c. Brain-path endpoint (Group B).**
- `app/services/ideation_turn_service.py`: `handle_turn(db, respond_io_id, message_text, audio_ref?)`:
  1. resolve the default workspace + `ideation_product_id` (fail-closed if unset → AC-31);
  2. `get_for_contact` → read `session_vars.ideation.draft_id`;
  3. build the §5.1 input deterministically, call shared-service `create_idea` over **HTTP** (server-to-server,
     `httpx` to `{ideation_shared_service_url}/ideation/intake/create-idea`, workspace/integration-key auth) - 
     **NOT** MCP (D-A5/§8-R3: shared-service has no MCP write server; `sorento_crm_mcp` is read-only). The
     `ideation_mcp_url` setting is retired in favour of `ideation_shared_service_url` + `ideation_intake_api_key`;
  4. on `collecting` → merge `session_vars.ideation = {draft_id, missing, updated_at}`; on
     `complete`/`duplicate` → delete the key; **read-modify-write** preserving all other keys (AC-16);
     `overwrite_for_contact` writes the merged blob;
  5. return `{ status, reply_text, link?, session_vars }`.
- `app/api/v1/external/ideation.py`: `POST /turn` (register in `app/api/v1/external/__init__.py`),
  `get_external_api_user` auth, wraps the service, writes an `integration_log` on success+failure (AC-20),
  graceful error `reply_text` on shared-service HTTP outage/timeout (AC-19).
- Tests (`[T]`): stub `create_idea` for each status (AC-12/13/14/15/51), key-preservation (AC-16),
  interrupt-resume (AC-17), no-config fail-closed (AC-31), idempotent draft_id (AC-13).

**2d. Embed-session mint (Group D BE).**
- `app/api/v1/integrations/ideation_embed.py`: `POST /ideation/embed-session {idea_id?}` - mint a signed
  assertion for the logged-in user (`ideation_embed_signing_secret` + `ideation_embed_connection_id`),
  `POST {ideation_shared_service_url}/embed/session`, return `{ iframe_url, token, expires_at }` (AC-42).
- FE: replace the stubbed hook with the real `ideationService` call; iframe uses the returned token per the
  embed framework; error/retry state stays (AC-43/44).
- Playwright round-trip (AC-43/45/52) against the running stack with a stubbed or real shared-service.

**2f. Multi-modal capture (Group F) - DC-1..DC-10, AC-60..AC-70.** Layers onto 2c; build **after** the
text ideate path is green (capture is additive to the same endpoint/service). Test-first:
- `ideation_turn_service`: on draft-open, **lookback** via `RespondClient.list_messages(contact)` →
  filter inbound media in last 10 → build the numbered menu, append to the first reply (AC-61);
  persist/clear `session_vars.ideation.pending_media` (AC-62).
- **Selection resolve** (AC-63): map parser `media_selection` positions → candidates; unrecognised →
  re-prompt-once-then-`none`; no-position turns are handled by n8n falling through (DC-7, n8n plan).
- **Snapshot + vision** (AC-64/65): fetch Respond CDN bytes → `storage_router.store(...)` → durable URL;
  OpenAI vision caption (reuse `openai_api_key`) → attachment `caption` + folded into `message_text`;
  graceful degrade on vision failure.
- **`attachments[]` assembly** (AC-60) + current-message auto-attach (AC-66) + subsequent auto-attach
  (AC-67) + `is_new_idea` restart with `discard_draft_id` (AC-68) + no-TTL resume (AC-69).
- Tests (`[T]`): stub `RespondClient.list_messages` + `storage_router` + vision; assert menu build,
  pending_media transitions, snapshot durability, caption fold, idempotent `source_msg_id`, restart/discard.
- E2E (AC-70): photo-no-caption → idea text → menu → pick → snapshot+caption+attach → review → complete,
  against a stubbed/real shared-service + a Respond List Messages fixture.
- **Blocked on** spine §5.1 gaining `attachments[]` + `discard_draft_id` (open Q5) and the n8n contract (open Q6).

> **BUILT 2026-07-20 (feat/ideation-capture-parity + shared feat/ideation-capture-embed-parity), tested,
> local, unpushed.** Shared-service: `IdeaAttachment` model + migration 0007 + intake persistence
> (idempotent `source_msg_id`) + `discard_draft_id` (draft→rejected) + read wiring; 6 new tests green,
> full ideation suite green. Sorento: `ideation_media_service.py` (lookback/menu/selection/snapshot+vision,
> injected seams) + `handle_turn` capture state machine (`pending_media`/`seen_media_ids`/`is_new_idea`) +
> external schema `media_selection`/`is_new_idea`; 12 media-service + 27 turn tests green. n8n contract
> written (`PLAN-ideation-capture-n8n.md`, in the capture-parity worktree).
>
> **Implementation deviation (honest note vs DC-2/DC-6):** the shipped sorento flow makes **all** recent
> unconfirmed media menu-gated - one lookback runs on first *and* continuation turns (excluding
> `seen_media_ids`), rather than current-message media auto-attaching (DC-6) with only backward media
> menu-gated (DC-2). This unifies the UX (every attach is human-confirmed) and prevents re-nagging via
> `seen_media_ids`, at the cost of one extra confirm turn for an image sent *with* the idea. Revisit if the
> extra turn annoys in real use; the auto-attach path can be added by keying off the current message's
> `source_msg_id`.

**2e. Non-regression (Group E).** CRM smoke (AC-50) + full ideate lifecycle E2E (AC-52).

### Phase 3 - Code review

`/code-review` on the merged Phase 1+2 branch. Confirm: parser change is additive + guarded (no CRM regression
set green), session_vars merge preserves CRM keys, secrets never logged/echoed, no UUID rendered in FE, iframe
error states present, migration idempotent + single head. Then open the PR with Phase-1 screenshots + the
test report keyed to the UAC ids.

---

## 6. Risks (sorento-specific, from the spine §6)

- **Live-flow surgery (highest).** The parser enum + router branch touch the production consume classifier.
  Mitigation: confidence floor demotion (AC-04) + no-regression golden set (AC-03) + CRM smoke (AC-50).
- **Interrupt correctness.** A CRM turn mid-collection must not clear/corrupt the open draft. Mitigation:
  CRM path never touches `session_vars.ideation`; resume-by-`draft_id` test (AC-17/52).
- **session_vars clobber.** Whole-blob overwrite could drop CRM keys. Mitigation: read-modify-write + AC-16 test.
- **Shared-service dependency (new).** `create_idea` MCP + `/embed/session` are cross-repo and may be down or
  mid-change. Mitigation: fail-closed / graceful reply (AC-19/31), settings dormant when blank (AC-32),
  contract snapshots pinned to §5.
- **Embed SSO is net-new** in sorento (no prior iframe-auth surface) - assertion signing + `allowedOrigins`/
  `frame-policy` must match the shared-service connection exactly (§5.3); mis-set → blank iframe (AC-44 guards UX).
- **Media binding (capture).** The image-then-idea vs image-then-complaint ambiguity (same shape, opposite
  binding) is the core capture risk. Mitigation: DC-1 lookback is **ideate-branch-contained** (no aggregation
  window over the live classifier) + DC-3 **human confirm-gate** (the user filters, so no cross-intent
  mis-attach and no `consumed_by` bookkeeping). Backward-only; subsequent media auto-attaches (DC-2).
- **Respond CDN expiry (capture).** Chat-CDN URLs are time-boxed; a raw Respond URL on an idea would rot.
  Mitigation: DC-4 snapshot picked bytes to R2/S3 at attach-time, pass a durable URL.
- **`pending_media` wedge (capture).** A stuck selection-state could swallow every later reply. Mitigation:
  DC-7 - n8n only treats a reply as a selection when the parser extracts a reference-position; non-positional
  turns fall through to normal classify, so no wedge and no TTL needed.
- **Contract drift - RESOLVED (master §8/D21).** `product_id` is derived **sorento-side** from `respond_workspaces.ideation_product_id` and passed (shared-service validates, no double-derivation). `submitter` = **phone E.164**; shared-service matches it to its own cron-synced contact copy (sorento passes no contact-row id).

---

## 7. Open questions to confirm with shared-service before Phase 2c

1. ~~`submitter_contact_id`~~ - **RESOLVED (D21):** pass **phone E.164**; shared-service matches to its own synced copy.
2. ~~`product_id` derivation~~ - **RESOLVED (§8-R2):** sorento derives + passes; shared-service validates. No double-derivation.
3. ~~`audio_attachment_ref` format~~ - **RESOLVED (DC-9):** retired in favour of unified `attachments[]` (durable
   sorento URLs). n8n transcribes voice (Whisper) into `message_text`; the audio *file* rides in `attachments[]`.
4. `/embed/session` request/response shape + assertion signing algorithm (reuse omnichannel 11H exactly).
5. **`attachments[]` + `discard_draft_id` on §5.1 (DC-9/DC-10)** - confirm the array shape, that shared-service
   stores attachments on the Idea + echoes them in `captured`, that it dedupes on `source_msg_id`, and that
   `discard_draft_id` marks the old draft `discarded`. **Change the spine §5.1 before Phase 2 of capture.**
6. **n8n contract (separate n8n plan)** - n8n must: (a) run Whisper STT on inbound voice → `message_text`
   (DC-5); (b) extract `media_selection` reference-positions when `pending_media` is set (DC-7); (c) extract
   the semantic `is_new_idea` flag with open-draft context (DC-10). Sorento owns lookback / snapshot / vision /
   attachment assembly; n8n owns STT + the two extractions + relay.
