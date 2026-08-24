# UAC - Sorento `ideate` intent + Ideas iframe host

**Feature slug:** `ideation-ideate-intent`
**Program spine:** `foundryx-shared-service/documentation/plans/ideation/PLAN-ideation-to-delivery-program.md`
(this UAC keys back to the **Cross-Repo Contracts** §5.1 / §5.2 / §5.3, and decisions D6, D7, D8, D19).
**Classification:** CORE change to the sorento AI brain (additive) + a new external brain-path endpoint +
a FE iframe host. NOT a new tenant module - it extends the existing CRM WhatsApp brain (D6).
**Sequencing:** choice **X** (D19) - the `ideate` intent is built into the **current** sorento brain now.

> Contract note. This UAC is written so that every field name, status value, and JSON shape is
> **byte-identical to §5** of the program spine. If a shape here disagrees with §5, §5 wins and this
> file is wrong - fix here, never fork the contract.

Legend: `[BE]` FastAPI/backend · `[FE]` Next.js · `[E2E]` Playwright round-trip · `[T]` unit/service test.
Given/When/Then, one id per row. A slice is done only when its ids pass the DoD gate in `PRINCIPLES.md`.

---

## Group A - Parser recognises `ideate` (additive, guarded) - D6, §5.5

**AC-01 [BE][T]** - *Given* the semantic parser contract (`app/schemas/ai_semantic_parser.py`),
*When* the schema is extended, *Then* a new closed intent value `ideate` exists in the `Intent`
literal, in `PARSE_RESULT_JSON_SCHEMA.properties.intent.enum`, and in the intent description - and
the JSON schema still validates under OpenAI strict mode (every property required,
`additionalProperties:false`, nullables as `["type","null"]`).

**AC-02 [BE][T]** - *Given* a WhatsApp-style raw idea turn ("I wish the app could remind me before a
PO expires", "can we add a feature that…", "idea: bulk-tag complaints"), *When* `_parse_turn` runs,
*Then* it returns `intent="ideate"` with `confidence ≥ _LOW_CONFIDENCE_FLOOR` (0.4). Tested against a
**paraphrase table**, not a keyword allowlist (per the "no overfit LLM NLP" rule).

**AC-03 [BE][T]** - *Given* the existing CRM intent corpus (data_query / record_question /
record_action / form_submit / how_to / capability / smalltalk / definition), *When* the parser runs
after the `ideate` addition, *Then* **zero** of those turns are reclassified as `ideate`
(no-regression golden set). This is the live-flow safety gate (Risk: live-flow surgery).

**AC-04 [BE][T]** - *Given* a low-confidence `ideate` guess (`confidence < 0.4`), *When* the router
`_route` runs, *Then* it demotes to the agent loop (`kind="agent"`), mirroring the existing
low-confidence floor - a shaky `ideate` guess never hijacks a CRM turn.

**AC-05 [BE][T]** - *Given* `intent="ideate"` at/above the floor, *When* `_route` runs, *Then* it
returns a dedicated decision that does **not** fall through to record_answer/capability, and the
in-app web brain path handles it per AC-06 (the WhatsApp path is the endpoint in Group B).

**AC-06 [BE][T]** - *Given* the **in-app web** assistant (`AIAssistantChatService.respond`, no
`respond_contacts` row / no `session_vars`) classifies a turn as `ideate`, *When* it responds, *Then*
it does **not** call `create_idea` (no contact context) and instead returns a friendly redirect to the
Ideas board (`/ideas`) - guarded, no exception, no CRM regression. (Intake proper is WhatsApp-first.)

---

## Group B - `ideate` brain-path endpoint calls `create_idea` - D7, D8, §5.1, §5.2

**AC-10 [BE]** - *Given* a new external endpoint `POST /api/v1/external/ideation/turn`
(API-key principal via `get_external_api_user`, mirroring the other `app/api/v1/external/*` routers),
*When* n8n posts `{ respond_io_id, message_text, media_selection?, is_new_idea? }` for an `ideate`-classified
turn, *Then* the endpoint executes one `create_idea` call and returns
`{ status, reply_text, link?, session_vars }` where `session_vars` is the full, updated blob.
(`media_selection` = the parser-extracted reference-positions when `pending_media` is set - Group F/DC-7;
`is_new_idea` = the semantic restart flag - DC-10. The legacy singular `audio_attachment_ref` is retired in
favour of the unified `attachments[]` the endpoint builds sorento-side - Group F/DC-9.)

**AC-11 [BE]** - *Given* the endpoint resolves `product_id` from the **workspace↔Product binding**
(never from the human - D6/§5.1), *When* it builds the `create_idea` input, *Then* it sends exactly
`{ product_id, submitter (phone E.164), message_text, attachments?, draft_id?, discard_draft_id? }` - the
input shape of §5.1 (revised per D21 + DC-9/DC-10): `submitter` = the contact **phone in E.164**, which
shared-service **matches** against its own cron-synced respond.io contact copy (sorento does NOT pass a
contact-row id); `product_id` from the bound sorento workspace; `attachments[]` = the unified media array
(Group F/DC-9); `discard_draft_id` = an abandoned draft to drop on restart (DC-10).

**AC-11b [BE][T]** - *Given* an `ideate` turn (D-CONFIRM), *When* the endpoint prepares the `create_idea`
call, *Then* the sorento **brain extracts** `{ fields, remove, confirm }` from `message_text` in the context
of the current draft (its schema + `session_vars.ideation.status`): `fields` = answer key→value updates,
`remove` = keys the user asked to clear, `confirm` = `true` **only** on an explicit confirmation of a
`review` summary. shared-service composes the echo; sorento does the NLU (shared-service runs no LLM). These
are passed structured - never a free-text "change X to Y" left for shared-service to parse.

**AC-12 [BE][T]** - *Given* the **first** `ideate` turn for a contact (no `session_vars.ideation`),
*When* the endpoint calls `create_idea`, *Then* it omits `draft_id`, receives
`{ draft_id, status, captured, missing, reply_text }`, and persists
`session_vars.ideation = { draft_id, status, missing, updated_at }` (§5.2 shape, ISO `updated_at`).

**AC-12b [BE][T]** - *Given* `create_idea` returns `status="review"` (all required captured, not yet confirmed - 
D-CONFIRM), *When* the endpoint finishes, *Then* it relays the echo `reply_text` (captured summary + confirm/
revise ask), **keeps** `session_vars.ideation = { draft_id, status:"review", missing:[], updated_at }` (does NOT
clear it), and makes **no** completion - the draft stays open awaiting explicit confirmation. This holds even
when the first turn was fully complete (one-shot complete still routes through `review`).

**AC-13 [BE][T]** - *Given* a **continuation** `ideate` turn (`session_vars.ideation.draft_id` set),
*When* the endpoint calls `create_idea`, *Then* it passes that `draft_id` through, and repeated calls
with the same `draft_id` are idempotent (enrich, never a duplicate draft - §5.1 idempotency).

**AC-13b [BE][T]** - *Given* a draft in `review` and a **revision** turn ("change module to X", "remove who",
"also it should…" - D-CONFIRM), *When* the endpoint runs, *Then* the brain-extracted `fields`/`remove` are
passed to `create_idea`, which merges them and re-returns `review` (or `collecting` if a required key was
removed); the endpoint relays the updated echo and keeps `session_vars.ideation` current. The revise loop
must survive **≥3 turns** (incomplete → collecting; complete → review; revise → review; …) until confirm.

**AC-13c [BE][T]** - *Given* a draft in `review`, *When* the user **explicitly confirms**, *Then* the brain
sets `confirm=true`, `create_idea` returns `status="complete"` with `link`, and only now is
`session_vars.ideation` **cleared** (AC-14). A non-confirmation reply while in `review` never completes.

**AC-14 [BE][T]** - *Given* `create_idea` returns `status="complete"`, *When* the endpoint finishes,
*Then* it **clears** `session_vars.ideation` (removes the key), relays `reply_text`, and includes the
returned `link` (the **product-domain** deep link, §5.3) in the response for n8n to send.

**AC-15 [BE][T]** - *Given* `create_idea` returns `status="duplicate"` with `duplicate_of`, *When* the
endpoint finishes, *Then* it **clears** `session_vars.ideation` and relays the "similar to … upvoted"
`reply_text` (the tool authors that copy; sorento does not compose it).

**AC-16 [BE][T]** - *Given* `session_vars` already carries CRM keys (e.g.
`referenced_result_set`, other namespaced blobs), *When* the endpoint writes/clears `ideation`, *Then*
it performs a **read-modify-write** that touches only the `ideation` key and preserves every other key
byte-for-byte (`overwrite_for_contact` replaces the whole blob, so the merge happens before the write).

**AC-17 [BE][T]** - *Given* a CRM question arrives **mid-collection** (interrupt), *When* that CRM turn
is handled by the existing consume path (not this endpoint), *Then* it never touches
`session_vars.ideation`; and *When* the next `ideate` turn arrives, *Then* the endpoint resumes by
`draft_id` - the open draft is neither corrupted nor cleared (D8, Risk: interrupt correctness).

**AC-18 [BE]** - *Given* `create_idea` args are constructed **deterministically** by the endpoint
(product_id/draft_id derived, not LLM-synthesised), *Then* the existing LLM UUID-arg coercion
(`_coerce_uuid_args`) is **not** relied upon on this path - args are already real ids.

**AC-19 [BE]** - *Given* shared-service `create_idea` is an **HTTP endpoint** (D-A5/§8-R3: shared-service
has no MCP write server; `sorento_crm_mcp` is read-only), *When* the endpoint calls `create_idea`, *Then*
it issues a server-to-server `httpx` POST to `{ideation_shared_service_url}/ideation/intake/create-idea`
authed with `ideation_intake_api_key`; a shared-service outage/timeout returns a graceful error
`reply_text` (never a 500 that would break the n8n send sub-flow - mirrors the "always log outbox"
resilience posture).

**AC-20 [BE]** - *Given* every call to this endpoint, *Then* an `integration_log` row is written
(inbound, `business_table="respond_contacts.session_vars"` or an `ideation` channel) on both success
and failure, matching the existing conversation-variables endpoint's logging.

---

## Group C - Workspace↔Product binding + config - D3, §5.1

**AC-30 [BE][T]** - *Given* the sorento deployment maps to exactly one shared-service **Product**
(`kind=software`), *When* the binding is modelled, *Then* `respond_workspaces` carries a nullable
`ideation_product_id` (shared-service Product UUID, server-side only, never rendered in the FE), added
by an idempotent Alembic migration chained onto the committed main head.

**AC-31 [BE][T]** - *Given* an `ideate` turn on a workspace with **no** `ideation_product_id`, *When*
the endpoint runs, *Then* it returns a graceful "ideation not configured for this workspace"
`reply_text` and makes **no** `create_idea` call (fail-closed, no partial state).

**AC-32 [BE]** - *Given* new settings `ideation_shared_service_url`, `ideation_intake_api_key`,
`ideation_embed_signing_secret`, `ideation_embed_connection_id` (all in `app/config.py`, `.env`-driven,
secrets masked in any echo; **no** `ideation_mcp_url` - create_idea is HTTP), *Then* absent/blank values
keep the feature dormant without affecting existing routes.

---

## Group D - Ideas iframe host + embed SSO - D17, §5.3

**AC-40 [FE]** - *Given* the sorento sidebar (`config/menu.config.tsx`), *When* a permitted user opens
it, *Then* an **"Ideas"** entry renders (own icon) and is reachable by **clicking through the sidebar**
(not deep-URL) to `/ideas`. Verified via Playwright sidebar navigation (per the "via sidebar" rule).

**AC-41 [FE]** - *Given* route `/ideas`, *When* it loads, *Then* it renders an `<iframe>` of the
shared-service ideation **board** UI; and *Given* `/ideas/{id}`, *Then* it iframes the ideation
**detail** UI for that idea. The `{id}` route param is opaque plumbing - **no UUID is shown as visible
UI text** (cursor rule); the human-readable content lives inside the iframe.

**AC-42 [BE]** - *Given* a logged-in sorento user opening `/ideas` or `/ideas/{id}`, *When* the FE
requests an embed session from a sorento BE endpoint (e.g.
`POST /api/v1/integrations/ideation/embed-session`), *Then* the BE **mints a signed assertion** for
that user (`ideation_embed_signing_secret`), `POST`s it to
`{ideation_shared_service_url}/embed/session`, and returns the embed token (`typ="embed"`) + the iframe
URL `{ideation_shared_service_url}/embed/ideas[/{id}]` (§5.3).

**AC-43 [FE][E2E]** - *Given* the returned embed token, *When* the iframe loads, *Then* it authenticates
seamlessly (no second login) because the shared-service embed connection's `allowedOrigins` includes the
sorento origin and its `frame-policy` permits the frame (§5.3, generalised from omnichannel plan 11H).
The token is passed to the iframe per the embed framework (query param or `postMessage`), never logged.

**AC-44 [FE]** - *Given* the embed session mint fails (shared-service down, misconfig), *When* `/ideas`
loads, *Then* the page shows an explicit error state with a retry CTA - it never renders a blank iframe
or leaks internal URLs/secrets (CRUD UX empty/error-state standard).

**AC-45 [FE]** - *Given* the product-domain link returned by `create_idea` on completion
(`{product_domain_base}/ideas/{idea_id}`, §5.3) is delivered to the user over WhatsApp, *When* they open
it in the sorento app, *Then* `/ideas/{id}` renders the same detail iframe (link round-trips).

---

## Group E - Cross-cutting / non-regression

**AC-50 [E2E]** - *Given* the live consume flow, *When* a normal CRM WhatsApp turn is processed after
this feature ships, *Then* behaviour is unchanged (data_query / form_submit / how_to answers identical)
 - proven by the Group A no-regression set plus one end-to-end CRM smoke.

**AC-51 [BE][T]** - *Given* the `ideate` end-to-end (parse → endpoint → `create_idea` → session_vars),
*When* driven with a **stubbed shared-service `create_idea`** returning each of
`collecting`/`complete`/`duplicate`, *Then* session_vars transitions match AC-12/14/15 exactly.

**AC-52 [E2E]** - *Given* a real multi-turn WhatsApp-style ideation (turn 1 collecting → CRM interrupt
→ turn 2 resume → turn 3 complete), driven against the running stack with a stubbed/real shared-service,
*Then* the draft survives the interrupt and completes, with `session_vars.ideation` created, preserved,
and cleared at the right steps (D8 exercised).

---

## Group F - Multi-modal capture (voice / image / video / file) - DC-1..DC-10

> **Scope.** Capture idea content + supporting media across WhatsApp's *stream of separate messages*.
> The hard problem is **binding** - media (photo/video/file/voice) carries no intent of its own; it
> inherits the intent of the text it belongs with. Solved by a **backward lookback + human confirm-gate**
> contained entirely to the `ideate` branch (DC-1), never an aggregation window over the live consume path.
> **Contract dependency:** §5.1 must gain `attachments[]` + `discard_draft_id` (change the spine FIRST - see
> the PLAN open questions). n8n owns STT + reference-position extraction; sorento owns lookback, snapshot,
> vision, and attachment assembly.

**AC-60 [BE][T]** - *Given* the unified media contract (DC-9), *When* the endpoint builds the
`create_idea` input, *Then* it sends `attachments: [{ source_msg_id, url, type:
"image"|"video"|"file"|"audio", filename?, caption? }]` (replacing the retired singular
`audio_attachment_ref`); `source_msg_id` (the Respond message id) is the **idempotency key** so a re-run
never double-attaches; and each `caption` is also **folded into `message_text`** (`(attached <type>:
<caption>)`) so `create_idea`'s semantic collection/dedup sees the media content.

**AC-61 [BE][T]** - *Given* the **first** `ideate` turn that opens a draft (DC-1/2/3/8), *When* the
endpoint runs, *Then* it calls **Respond List Messages** for the contact (existing `RespondClient`),
filters to **inbound, media-type, within the last 10 inbound messages**, dedupes against media already on
the draft, and - if any candidates exist - **appends a numbered menu to the first reply**
("I saw N recent files: 1. 📷 photo (2m ago) … reply `1,3` / `all` / `none`"); an **empty candidate set →
no menu, no friction**. No park endpoint / buffer table / consumed-tracking is introduced (DC-3).

**AC-62 [BE][T]** - *Given* the menu is shown, *When* the endpoint persists state, *Then* it writes
`session_vars.ideation.pending_media = [{ source_msg_id, type, filename, received_at }, …]`
(read-modify-write, preserving all other keys per AC-16); the state is preserved across the turn boundary
and **cleared** when a selection resolves (AC-63) or the draft closes (complete/duplicate/restart). No
time-based TTL on this state (DC-7/DC-10).

**AC-63 [BE][T]** - *Given* `pending_media` is set and n8n passes the **parser-extracted
`media_selection`** (reference-positions - numbers / "all" / "none"; DC-7), *When* the endpoint runs,
*Then* it maps positions → candidates, **snapshots the picked media** (AC-64), attaches them via
`attachments[]` (AC-60), and clears `pending_media`; `none` → attaches nothing + clears; an
**unrecognised** selection → the endpoint re-prompts once, then defaults to `none` and continues. A turn
with **no reference-position** is **not** a selection - n8n lets it fall through to normal classify, so a
mid-selection CRM interrupt is never swallowed (DC-7).

**AC-64 [BE][T]** - *Given* a picked (or current-message) media ref (DC-4), *When* the endpoint attaches
it, *Then* it fetches the bytes from the Respond CDN and stores them **durably via `storage_router`
(R2/S3)**, passing the resulting durable URL in `attachments[]` - only the *picked* media is snapshotted
(not all 10), at attach-time - so the idea's link never rots when the Respond CDN URL expires.

**AC-65 [BE][T]** - *Given* an attached **image** (DC-6), *When* the endpoint snapshots it, *Then* it runs
a **vision caption** using the assistant's existing provider (`settings.openai_api_key`, reusing the
already-downloaded bytes), stores the caption on the attachment **and** folds it into `message_text`
(AC-60); a missing key / vision failure **degrades gracefully to attach-without-caption** (never a 500,
mirrors D-5).

**AC-66 [BE][T]** - *Given* a **current-message** voice note classified `ideate` (DC-5), *When* n8n has
already transcribed it (Whisper) into `message_text`, *Then* the endpoint treats the transcript as the
idea content **and auto-attaches** the voice file as `attachments[type=audio]` (no menu - it *is* the
current idea, not lookback). A current-message image+caption (S1) likewise auto-attaches with its caption.

**AC-67 [BE][T]** - *Given* media arrives **while a draft is already open** (not the first turn; DC-2),
*When* the endpoint processes it, *Then* it **auto-attaches** to the open draft with no menu - the
confirm-gate is **backward-only**; the user removes a wrong attachment inside the iframe.

**AC-68 [BE][T]** - *Given* an `ideate` turn arrives with an **open draft** and n8n's parser (with the
open-draft topic as context) extracts **`is_new_idea = true`** (semantic, not keyword - the "no, different
idea" signal; DC-10), *When* the endpoint runs, *Then* it **clears `session_vars.ideation`**, calls
`create_idea` **without `draft_id`** (fresh draft) and passes **`discard_draft_id` = the abandoned draft**
so shared-service drops the phantom; default (`is_new_idea` absent/false) **resumes** by `draft_id`.

**AC-69 [BE][T]** - *Given* an **abandoned** open draft (user never confirmed), *When* the same contact
returns later on the **same topic**, *Then* the endpoint **resumes** it by `draft_id` with **no
time-based expiry** - topic, not time, is the discriminator; the only reset is the explicit `is_new_idea`
restart (AC-68). Neither `pending_media` nor the draft pointer time-expires (DC-7/DC-10).

**AC-70 [E2E]** - *Given* the full multi-modal capture flow, *When* driven end-to-end (photo with no
caption → "I have an idea about X" → menu appended to first reply → user replies `1` → snapshot + vision
caption + attach → field collection → review → confirm → complete), *Then* the completed idea carries the
attachment with a **durable URL + caption**, `session_vars.ideation` (incl. `pending_media`) transitions
and clears at the right steps, and no CRM turn in the corpus is affected (ties to AC-50).
