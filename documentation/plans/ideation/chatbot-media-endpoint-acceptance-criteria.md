# Chatbot media endpoint - User Acceptance Criteria

**Status:** draft, Phase 1 not started
**Plan:** `documentation/plans/ideation/PLAN-chatbot-media-endpoint.md`
**Domain:** ideation (chatbot) + user-management (operator surfaces)
**Classification:** CORE, `public` schema (see plan header for the rationale)

This file is the contract. The plan is the design that fulfils it. An issue that contradicts
this file loses.

Source decisions, verbatim and settled, are in the captain's decision log
(`multimodal-implementation-plan/decisions.md`, `decisions-part2.md`). They are not reopened
here. Where this file records a recommendation rather than a decision, it says so.

---

## Journey

Two actors. The design is derived backwards from both.

### Actor A - the dealer on WhatsApp

The dealer is standing in their shop or warehouse with a phone. They already have the
information in their hand: a carton, a delivery order, an RMA form, or a question they would
rather say than type. Today they send a photo and the bot silently ignores the picture, or
they send a voice note and are told voice is not supported.

1. **They send a photo with a caption**, for example "check stock for these" over a photo of
   two cartons. They arrive from an ordinary WhatsApp thread. They make **no decisions** - they
   send what they were already going to send.
2. **The system already knows** who they are (the contact is resolved from the phone number
   before this feature is reached), whether photo reading is turned on for them, how much of
   their monthly allowance is left, and what period it resets in. None of that is asked.
3. **They get one confirmation message** naming what was read from the photo, before the
   answer. If something is unreadable or disagrees with itself, the confirmation says so and
   asks - it never quietly picks a value.
4. **They get the answer** to the question they asked, produced by the same machinery a typed
   question uses. They cannot tell the entities came from a photo.
5. **At the end they hold** a stock figure, a delivery date, or whatever they asked for - plus,
   when relevant, one appended line telling them how much allowance is left, or that accuracy
   has dropped and typing is exact.

The single decision the dealer makes on the whole journey is "is that what I meant?", and only
when the system is genuinely unsure. Everything else is derived from the photo, the caption and
what the CRM already holds.

**The captionless variant.** A photo with no caption, or a caption whose intent is unclear, ends
at step 3: the system says what it read and **asks what they want**. It does not guess. Guessing
intent on top of imperfect extraction stacks two silent failure modes.

**The voice variant.** Identical shape. They send a voice note, they get "here is what I heard",
then the answer. A clip over the maximum length is refused with a plain instruction to send a
shorter one.

**The not-enabled variant.** Nothing is on for anybody at the start. A dealer whose access has
not been turned on is told so in one sentence, with the escape hatch ("type the codes instead"),
and no money is spent.

### Actor B - the CRM operator

The operator is whoever administers contacts today. They arrive from a support question:
"why did the bot stop reading my photos", or "turn this on for this dealer".

1. **They open the contact they already have open** - `user-management/contacts/{id}`. No new
   screen to learn, no new role to be granted.
2. **The first thing they see** on the Media Access card is the answer to the support question:
   whether each modality is on, how much has been used this month out of what limit, and
   whether the limit is the inherited default or an override.
3. **The single decision** is a toggle, and optionally a number. Nothing else is asked - the
   period, the reset date, the usage count and the default are all derived.
4. **At the end they hold** a contact that can send photos, and a visible record of it having
   been changed.

Separately, an operator who needs to change the numbers **for everyone** goes to
`user-management/settings/chatbot-media` and edits them there. No deploy. That surface exists
because the captain required the starting numbers to be configurable by an operator, not
constants in code.

### What every other stakeholder is told automatically

- The ledger records every accepted item and every refusal, so "the gate denied everyone" is
  observable rather than invisible.
- Token spend is written to `AIAssistantUsageLog` with `contact_id` in the same call that spends
  it, so the existing AI usage dashboard picks it up with no new plumbing.

---

## Phase and slice map

| slice | what it delivers | phase order |
|---|---|---|
| S1 | Settings defaults + per-contact limit/gate rows + both operator surfaces | FE mock, then BE |
| S2 | The synchronous fast path: gate, burst, quota, ledger, idempotency | BE |
| S3 | The queued extraction job, the callback, and the polling fallback | BE |
| S4 | Image extraction: prompt, schema, conflict detection, corpus harness | BE |
| S5 | Voice transcription with a configurable language strategy | BE |
| S6 | Customer-facing wording rendered from the decision | BE |

---

## S1 - Access, limits and the operator surfaces

### S1-01 [FE] The contact Media Access card renders with every section present

**Given** an operator on `user-management/contacts/{id}`
**When** the page loads
**Then** a Media Access section renders for **both** modalities (image and voice), each showing
enabled state, used-of-limit for the current period, the reset date in human-readable form
("1 September"), and whether the limit is inherited or an override
**And** it renders with an explicit empty state when the contact has no rows and no usage, never
a hidden section.

### S1-02 [FE] Access defaults to off and is switchable in place

**Given** a contact with no media limit rows
**Then** both modalities read "Not enabled"
**And** an operator can turn either on without leaving the page.

### S1-03 [FE] Turning access off asks for confirmation

**Given** a contact with image access on
**When** the operator turns it off
**Then** a confirmation dialog appears using `AlertDialog` / `ConfirmDeleteDialog`, never
`confirm()`.

### S1-04 [FE] The settings page edits every configurable number

**Given** an operator on `user-management/settings/chatbot-media`
**Then** they can edit, without a deploy: image monthly limit, voice monthly limit, voice
maximum clip seconds, burst count, burst window seconds, the warning threshold percent, the
standard and degraded model for image, the transcription model, and the language strategy
(mode plus pinned language plus hint list)
**And** every optional select on that page is clearable.

### S1-05 [BE] Access is denied by default for every existing contact

**Given** a contact with no `contact_media_limit` row for a modality
**When** the media endpoint is called for that modality
**Then** the decision is `denied_gate`
**And** no extraction job is created and no provider call is made.

### S1-06 [BE] Anyone who can edit a contact can change media access

**Given** a user whose role grants the existing contact-edit permission
**When** they PUT the media access for a contact
**Then** it succeeds
**And** a user without that permission gets 403. No new admin-only role is introduced.

### S1-07 [BE] Per-contact overrides sit on top of configurable defaults

**Given** the system default image limit is 50 and a contact has an override of 200
**Then** that contact's effective limit is 200 and every other contact's is 50
**And** clearing the override returns the contact to 50 without a deploy.

### S1-08 [BE] New settings columns reach the frontend

**Given** a new media settings column
**Then** it is present in **both** manual dict builders - the `GET /settings` response dict and
`SystemSettingUpdate` - and a round trip through the settings page preserves the saved value.

### S1-09 [T] Settings and limit resolution are unit-tested

Effective limit resolution is tested for: no row, row with NULL limit (inherit), row with an
override, and a changed system default taking effect without a restart.

---

## S2 - The synchronous fast path

### S2-01 [BE] One call decides, meters and records before any spend

**Given** an enabled contact within quota
**When** n8n POSTs the media endpoint
**Then** the response returns within the fast-path budget and carries the decision, the quota
numbers, the tier and any notices
**And** a ledger row exists **before** the response is returned
**And** no provider call has yet been made.

### S2-02 [BE] Strict idempotency on message_id

**Given** an accepted call for `(respond_io_id, message_id, modality)`
**When** the identical call is repeated, as n8n's `retryOnFail` will do
**Then** the response carries the **same** decision, the same `job_id` and `idempotent_replay:
true`
**And** exactly one ledger row exists
**And** no second extraction job is created and no extraction tokens are spent a second time.

### S2-03 [BE] The gate fails closed

**Given** a contact whose modality is not enabled
**Then** the decision is `denied_gate`, a ledger row with outcome `refused_gate` is written, and
no job is created.

### S2-04 [BE] Refusals are recorded, so a dead gate is observable

**Given** any refusal - gate, burst, quota-hard, or duration
**Then** a ledger row is written with the matching `refused_*` outcome
**And** a query over the ledger can distinguish "everybody was refused" from "nobody used the
feature". This AC exists because the respond.io gate failed silently for three weeks and nothing
recorded it.

### S2-05 [BE] Burst limiting is per contact and is not the quota

**Given** the burst setting is 5 per 60 seconds
**When** a contact's sixth item arrives inside the window
**Then** the decision is `denied_burst` with a pacing message, not a quota message
**And** the quota count is unaffected.

### S2-06 [BE] At the quota limit the contact is degraded, not turned away

**Given** a contact who has used their whole monthly allowance
**When** they send another item
**Then** the decision is `accepted` with `tier: degraded`
**And** the configured degraded model is used for the extraction
**And** the response carries a degradation notice stating accuracy has dropped and that typing is
exact.

### S2-07 [BE] The 80 percent warning fires once per contact per period per modality

**Given** a contact crossing the warning threshold
**Then** the first crossing returns a `warn_80` notice and stamps the period on the limit row
**And** every later call in the same period for the same modality returns no `warn_80` notice.

### S2-08 [BE] The degradation notice is its own message and also fires once per period

Distinct from S2-07: a separate notice kind, stamped on its own column, sent when degradation
first happens in a period.

### S2-09 [BE] A voice clip over the configured maximum is refused before spend

**Given** the maximum clip length is 120 seconds and a 150 second clip arrives
**Then** the decision is `denied_duration` with the "send a shorter one" message and no
transcription is attempted.

### S2-10 [BE] The period is computed in Asia/Kuala_Lumpur by the CRM

**Given** a call at a UTC instant that falls in a different calendar month in MYT
**Then** the `period_key` and the reset date are derived from MYT, and n8n performs no date
arithmetic - the endpoint returns a rendered human-readable reset label.

### S2-11 [BE] Auth and validation

The endpoint requires `X-API-Key` resolving through the external-integration principal with its
own permission slug; a missing or unusable key returns 401, a key without the slug returns 403,
and a malformed body returns 422.

### S2-12 [T] Every branch above has a pytest case on Postgres

Each test seeds its own chain (workspace, contact, limit row, settings) with a marker prefix and
borrows no existing row.

---

## S3 - The queued extraction and the callback

### S3-01 [BE] Only extraction is queued; nothing slow is inside the request

**Given** an accepted decision
**Then** the HTTP handler returns without having downloaded media or called a provider
**And** the extraction runs on the worker.

### S3-02 [BE] The job holds n8n's callback target opaquely

**Given** a request carrying `callback_url` and optional `callback_headers`
**Then** they are stored against the job and used verbatim when the result is delivered
**And** the CRM makes no assumption about what mechanism the far end uses to consume it. This AC
exists because mid-flow resume was **not** confirmed to exist in the spine (see the plan's
"Resume" section) and the CRM half must not depend on it.

### S3-03 [BE] The turn context survives the pause

**Given** a request carrying turn context (`turn_id`, `respond_io_id`, `message_id`, caption and
any opaque `context` blob)
**Then** the callback payload carries all of it back unchanged, so the far end can rebuild the
turn without re-reading anything.

### S3-04 [BE] A polling fallback exists

**Given** a `job_id`
**When** `GET` is called on the job
**Then** it returns the job state and, once complete, the same result body the callback carried
**And** it is idempotent and safe to poll.

### S3-05 [BE] The callback always fires, on success and on failure

**Given** a job that fails or times out
**Then** a callback is still delivered, with `status: failed` and a reason
**And** the ledger row's outcome is updated to `failed`
**And** the failure never leaves the far end waiting indefinitely.

### S3-06 [BE] The extraction is bounded by a configurable timeout

**Given** the configured extraction timeout
**When** a job exceeds it
**Then** the job is abandoned, marked failed, and the callback fires
**And** the ceiling is well inside the dispatcher's 120 second lock TTL so the pause cannot
outlive it even if the far end does hold the lock.

### S3-07 [BE] Callback delivery is best-effort and never poisons the job

**Given** the callback POST fails
**Then** it is retried a bounded number of times, the failure is logged, and the job result
remains readable through the polling endpoint. A post-commit side effect never raises.

### S3-08 [BE] The event loop is not blocked

The extraction path does not call a synchronous multi-second function from an `async def`
request handler. The known existing defect on the portal route
(`app/api/v1/public/ai_extract.py`) is out of scope and is not to be reproduced here.

### S3-09 [T] Job lifecycle is tested end to end on Postgres

Queued, running, completed, failed, timed out, callback-failed, and replay-after-complete.

---

## S4 - Image extraction

### S4-01 [BE] Extraction emits entities in the reformulator's own shape

**Given** a successful image extraction
**Then** each entity is `{raw, hint, current_message, confident}` with `hint` drawn only from
the 14-value enum in `docs/flows/sub-query-reformulator.md` section 2
**And** `raw` is the literal string as it appears, with no product-code matching or snapping
performed - `resolve-entity` adjudicates.

### S4-02 [BE] Values with no hint in the enum are carried as unhinted context

**Given** a carton label yielding a batch number, a barcode, a box dimension or a product size
**Then** those are returned in a separate `attributes` array with their own kind, **not** forced
into `entities` with a wrong hint
**And** they are available to the confirmation message.
*Decided by the captain 2026-08-14: unhinted `attributes[]`, and the 14-value enum is not
extended. See the plan's section 9.*

### S4-03 [BE] Conflict detection is a first-class output

**Given** an image where a handwritten or stamped value disagrees with a printed one
**Then** the result carries a `conflicts` entry naming the field and **both** values with their
sources
**And** the affected entity is marked `confident: false`
**And** the system does not silently prefer either value. This AC exists because the measured
baseline silently preferred ink over print on a real RMA photo.

### S4-04 [BE] An ambiguous date is flagged, not resolved

**Given** a date whose day and month are both 12 or less, such as `11/08/2026`
**Then** the raw printed string is preserved and the ambiguity is flagged rather than a month
being chosen silently. The measured baseline read August as November.

### S4-05 [BE] Punctuation in names is transcribed as printed

**Given** a customer name containing an ampersand or punctuation, such as `J&Y WORLD HARDWARE`
**Then** it is not normalised to a phonetic or simplified form. The measured baseline returned
`JAY WORLD HARDWARE`.

### S4-06 [BE] Carton and warehouse photos have their own extraction guidance

**Given** an angled phone photo of a carton label
**Then** model code, quantity, product size, box dimension, batch and barcode are each attempted
**And** product size and box dimension are kept distinct from one another. The measured baseline
found the model code and stopped.

### S4-07 [BE] Document-shaped inputs keep the rules that already pass

**Given** a clean delivery-order screenshot listing several product codes where only one is the
subject
**Then** only the subject code is emitted as a product entity, compatibility codes and a
wrongly-received part are not
**And** spreadsheet artifacts such as an `#N/A` row do not become line items.

### S4-08 [BE] A captionless or unclear-intent image asks rather than assumes

**Given** an image with no caption, or a caption whose intent cannot be determined
**Then** the result sets a clarification flag and carries a question naming what was read
**And** no query sentence is rendered for the parser.

### S4-09 [BE] Nothing extracted degrades to today's behaviour

**Given** an image from which nothing legible is extracted
**Then** the rendered text is the caption alone, which is exactly what the turn does today
**And** the confirmation says plainly that nothing was read and names the escape hatch.

### S4-10 [BE] Extraction is capped and truncation is stated

**Given** an image containing more entities than the configured cap
**Then** the result is truncated to the cap and says so, rather than truncating silently.

### S4-11 [T] The extraction runs against the real corpus and the results are recorded

**Given** the three real Sorento images in the supplied test corpus
**When** the extraction is run against each
**Then** a results file records, per image and per field, exact match / plausible-but-wrong /
refused, measured against the written ground truth
**And** plausible-but-wrong outcomes are reported explicitly, including any that remain.
An extraction path that has never been run against a real photo does not satisfy this AC.

### S4-12 [T] Prompt behaviour is unit-tested without a provider call

Parsing, conflict propagation into `confident: false`, the entity/attribute split, the cap and
the captionless branch are tested against recorded provider responses, so the suite does not
require a paid call.

---

## S5 - Voice transcription

### S5-01 [BE] The language strategy is configurable without a deploy

**Given** the settings surface
**Then** an operator can switch between a pinned single language, a list of language hints, and
auto-detect
**And** the transcription request body changes accordingly with no code change.

### S5-02 [BE] The current pin stays until it is changed

**Given** a fresh install or an untouched settings row
**Then** the effective strategy is pinned, language `en`, matching today's behaviour exactly.

### S5-03 [BE] Detected languages are reported when the model supplies them

**Given** a transcription response carrying detected languages
**Then** they are recorded on the job and returned in the callback
**And** an empty detected-language list is treated as a valid "unsure" signal, not as an error
and not as silence.

### S5-04 [BE] The transcription model is a setting, not a constant

Changing it requires no deploy.

### S5-05 [BE] A transcript is returned in the callback for confirmation

The callback carries the transcript so the far end can send the existing "here is what I heard"
confirmation.

### S5-06 [T] Transcription is tested against recorded responses

Pinned, hints and auto modes each produce the expected request shape; the unsure signal is
handled; a provider failure produces a failed callback.

---

## S6 - Customer-facing wording

### S6-01 [BE] Every notice is rendered by the CRM, not assembled in n8n

**Given** any decision carrying notices
**Then** each notice arrives as ready-to-send text, so the far end sends a string and performs no
formatting.

### S6-02 [BE] Notices append, never replace

**Given** an accepted call that also carries a warning or degradation notice
**Then** the notice is returned alongside the answer path, marked for appending, and never
substitutes for it.

### S6-03 [BE] Dates in customer text are human-readable

"1 September", never "2026-09-01".

### S6-04 [BE] Counts are stated as X of Y left, never as a percentage

### S6-05 [BE] The burst message does not imply the contact has run out

It is a pacing message, and it is suppressed for the remainder of the burst window so fifty
images produce one of it, not forty-five.

### S6-06 [BE] The not-enabled wording matches the live voice sentence in shape

So that image and voice read as one feature, and every failure message names an action that
definitely works.

### S6-07 [T] Wording is unit-tested by rendered string

Each notice kind is asserted on its full rendered text, not on a fragment, so a partially wrong
message cannot pass.

---

## Definition of Done for this feature

On top of the repo's standing DoD gate:

1. The three corpus images have been run through the shipped extraction and the results recorded
   honestly, including what it still gets wrong (S4-11).
2. The fast-path latency has been measured and the `lock:{contact}` recommendation stated with
   that evidence.
3. Whether the spine can resume mid-flow has been stated as a finding, not assumed.
4. The entity-hint question is either answered by the captain or carried in the PR description as
   an open point with a recommendation.
5. The new permission slug has a grant migration for already-provisioned roles.
6. New settings columns are present in both manual dict builders.
