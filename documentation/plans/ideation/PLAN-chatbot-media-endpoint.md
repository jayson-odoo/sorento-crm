# PLAN - Chatbot media endpoint (voice transcription + image recognition)

**Status:** Phase 1 (frontend mock) in progress
**UAC (the contract):** `documentation/plans/ideation/chatbot-media-endpoint-acceptance-criteria.md`
**Classification:** **CORE**, `public` schema, normal FKs.
Rationale: this extends the core chatbot/contact domain and references `respond_contacts` and
`system_settings` directly. It is not something a second tenant would install separately, and the
usage ledger is a durable business record that must survive anything being turned off.

**Scope:** the CRM half only. The n8n workflow changes are a separate follow-up that depends on
this. No file outside this repo is touched.

---

## 0. What this builds, in one paragraph

One endpoint that n8n calls once per inbound media message, **and waits for**. It checks whether
the contact is allowed the modality, checks burst and monthly quota, and writes a ledger row -
all of that instantly and **before any money is spent** - then hands extraction to the worker and
awaits the worker's result, returning decision and extraction in one response. The extraction
emits entities in the chatbot's own entity shape so nothing downstream has to know a photo was
involved.

**The wire is synchronous; the execution is not.** This distinction is the whole design. n8n makes
one call and blocks on it, which is what the captain approved and what the spine can actually do
today. But the CRM never performs the multi-second work inside the request handler: the handler
enqueues, then awaits the job without holding the event loop. That is deliberately the opposite of
the live portal defect at `app/api/v1/public/ai_extract.py:116`, where a synchronous multi-second
`extract` call inside an `async def` route freezes the whole backend for 5.8-9.8 seconds per
request. That defect is out of scope to fix and is not to be reproduced here.

The transport-agnostic callback and the polling endpoint are built anyway, and the synchronous
wait falls back to them on timeout. True async is therefore a configuration switch, not a rebuild.

---

## 1. The two flagged questions, settled with evidence

The captain flagged two things to settle deliberately rather than assume. Both are settled here.

### 1.1 Does the spine hold `lock:{contact}` across the wait?

**Chosen: HOLD. This reverses the recommendation made against the earlier async design, and the
reversal is the direct consequence of the captain approving the synchronous wire.**

The reversal is stated plainly rather than quietly amended, because the reasoning matters more
than the conclusion.

**Under the synchronous wire, hold-versus-release is no longer a choice.** A spine node that makes
a blocking HTTP request holds the dispatcher's lock for the duration by construction:
`call-spine` is `waitForSubWorkflow: true` (`sorento-dispatcher/workflow.json:379`), so the
dispatcher execution is blocked on the spine, and the spine is blocked on the CRM. There is no
pause to release across. The earlier release recommendation was answering a different question -
whether to hold across an **open-ended** suspension in an async/resume design - and that question
no longer exists.

**So the real question becomes: is holding safe?** It is a budget argument, and the budget now
closes, where before it did not.

| term | value | source |
|---|---|---|
| lock TTL | 120s | `sorento-dispatcher/workflow.json:330` |
| existing spine turn | 5.0 - 18.4s | `concurrency-plan.md:82,84,143`, `dym-probe-before-offer-plan.md:463` |
| fast path added by this endpoint | milliseconds | measured in this work, section 8 |
| extraction, typical | 5.8 - 9.8s | measured, three corpus images |
| extraction, hard ceiling | `media_sync_wait_seconds`, default 30s | enforced by this endpoint |
| **worst-case turn** | **~48s** | 18.4 + 30, against a 120s TTL |

That leaves better than 60 percent margin at the worst case and roughly 75 percent at the typical
one. Crucially the ceiling is **enforced by a CRM setting rather than hoped for**: past
`media_sync_wait_seconds` the endpoint stops waiting and returns `status: pending` with the
`job_id`, so the wait cannot run long no matter how badly the provider behaves. That is a strict
improvement on the status quo, in which nothing bounded a turn at all.

**What does not change, and must still be said in the PR:** spine p99 remains **unmeasured**
(`concurrency-plan.md:148`), it is already risk #1 in that plan (`:193`, `:222`), and this feature
makes measuring it more urgent rather than less. The mitigation shipped here is that
`media_sync_wait_seconds` is an operator setting, so if the lock does prove tight the wait can be
shortened - and the flow degrades to the callback rather than breaking - without a deploy.

The original evidence, which still stands and is what sized the budget above:

- The dispatcher calls the spine with `waitForSubWorkflow: true`
  (`sorento-dispatcher/workflow.json:379`), so the dispatcher execution is blocked for the whole
  spine turn and `lock:{contact}` is held for that whole time.
- The lock TTL is **120 seconds** (`sorento-dispatcher/workflow.json:330`, mirrored in
  `plans/dispatcher.sdk.js:59`).
- Spine p99 is **explicitly unmeasured** and accepted as a monitored residual risk
  (`plans/concurrency-plan.md:148`), with the re-measure listed as an outstanding preflight
  (`:193`) and a live regression risk (`:222`).
- The only recorded durations are single runs, not a distribution: 4.8s and 9.0s
  (`concurrency-plan.md:82`, `:84`), 6.25s and 6.79s at the live cutover (`:143`), and a range of
  5.8-18.4s (`plans/dym-probe-before-offer-plan.md:463`).
- Measured extraction cost on the same class of work: 5.8s, 9.8s and 5.8s wall time for the three
  corpus images (prior experiment, `image-extract-experiment/report.md`). Add media download and
  queue wait on top.
- The consequence of overrun is specific and bad. When the TTL fires, the dispatcher's 1 second
  schedule tick sees a free lock and starts a **second concurrent spine for the same contact** -
  which is exactly the `save-session-vars` read-modify-write clobber the dispatcher was built to
  eliminate (`concurrency-plan.md:5`).

Holding is also what the repo's own precedent does for the equivalent work: voice today runs
`fetch-audio` then `whisper-transcribe` **inline and synchronously** inside the spine
(`live-spine-sorento-consume-main/workflow.json:5057`, `:5083`), under the same lock, for the same
class of multi-second provider call. This endpoint is that pattern with a bounded ceiling added,
not a new risk class.

**What is measured in this work:** the fast-path latency and the worst-case end-to-end call, since
both now sit inside the lock. Method and targets are in section 8.

### 1.2 The n8n node timeout

The captain asked for this to be settled with evidence, and it interacts with idempotency in a way
that is easy to get wrong.

**Recommendation: set the n8n HTTP node timeout to 60 seconds**, with `retryOnFail: true` and
`onError: stopWorkflow`.

- 60s is double `media_sync_wait_seconds` (30s) and comfortably above the worst case of roughly
  40s for the call itself, so a normal slow turn never trips it.
- It still leaves half the 120s lock budget unspent even if the node runs to its own timeout.
- **`retryOnFail` is safe precisely because of the idempotency constraint.** If the node times out
  while the CRM job actually completed, the retry hits the idempotent replay path (section 3.3
  step 2) and returns the **same** `job_id` and the **completed result**, with no second ledger
  row and no second extraction spend. Without strict idempotency this configuration would double
  charge a contact and pay twice for one photo, which is why the constraint is mandatory rather
  than defensive.
- **Never configure it as `continueErrorOutput` with the error output unwired.** That combination
  routes the item to an unconnected output, the branch dead-ends, and the execution still reports
  `success` - a documented incident class in that repo where a swallowed error produced a
  confidently wrong customer reply.

### 1.3 Can the spine actually resume mid-flow?

**Finding: not today, and not without new construction. This was checked, not assumed.**

Under the synchronous wire this is no longer on the critical path - it is what the fallback would
need if async is ever switched on. It is recorded in full because that switch is meant to be a
configuration change, and this is the fact that decides how much work the switch actually costs.

- Exactly one `n8n-nodes-base.wait` node exists in the whole n8n repo, in `sub-sendmsg`
  (`export/sub-sendmsg/workflow.json:357-367`). It carries no `resume` property, so it is in the
  default `timeInterval` mode, **not** `resume: webhook`. Its `webhookId` is auto-minted by the
  editor for every Wait node and is not evidence of webhook mode.
- That node is **orphaned** - zero inbound edges (`export/sub-sendmsg/TOPOLOGY.md:39-40`, and the
  n8n repo's own `CLAUDE.md:57`).
- `resumeUrl`, `$execution.resumeUrl` and `webhookSuffix` have **zero occurrences** repo-wide.
- The spine itself contains no Wait node at all.
- The live instance's n8n version and execution mode are recorded nowhere in that repo; the
  `docker-compose.yml` pin is explicitly disclaimed as the dead local stack (`CLAUDE.md:43`).

**Consequence for this plan: the CRM must not depend on resume existing** - and under the
synchronous wire it does not, because the primary path returns the result on the same call. The
callback stays transport-agnostic for the fallback and the future switch: n8n may supply an opaque
`callback_url` plus optional `callback_headers`, and the CRM POSTs the result there and cares
about nothing else. That target can be a Wait-node resume URL if the n8n half ever builds one, or
a plain webhook that re-enqueues the turn - which is cheaper and matches the repo's own precedent.
A `GET` polling endpoint covers the case where neither is wanted, and it is also what n8n should
call after a `status: pending` response.

One structural fact the n8n follow-up must respect, recorded here so it is not rediscovered: the
extracted text has to land in the queue item **upstream of `tf-message`**
(`live-spine-sorento-consume-main/workflow.json:2706`), because roughly fifteen downstream nodes
read `$('tf-message')` by name (`TOPOLOGY.md:202`). That is the same trick `patch-transcript`
(`:5100`) already uses for voice.

---

## 2. Data model

Three pieces. Two new tables, plus columns on the existing settings singleton.

### 2.1 `contact_media_usage` - the ledger

Append-mostly, one row per media item, including refusals. This is the metered fact.

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `respond_io_id` | Text, not null | what n8n knows; enforcement reads this |
| `contact_id` | Text FK `respond_contacts.id` ON DELETE SET NULL | internal id; reporting joins this, mirroring `AIAssistantUsageLog.contact_id` |
| `modality` | Text, not null | `image` or `voice` |
| `message_id` | Text, not null | respond.io messageId - the idempotency key |
| `period_key` | Text, not null | `YYYY-MM`, computed in Asia/Kuala_Lumpur by the CRM |
| `outcome` | Text, not null | `accepted`, `failed`, `refused_gate`, `refused_burst`, `refused_quota`, `refused_duration` |
| `tier` | Text, nullable | `standard` or `degraded` |
| `turn_id` | Text, nullable | n8n `$execution.id` |
| `bytes` | Integer, nullable | |
| `duration_ms` | Integer, nullable | voice |
| `model`, `provider` | Text, nullable | stamped after extraction |
| `prompt_tokens`, `completion_tokens` | Integer, nullable | |
| `created_at` | TIMESTAMPTZ default now() | |

- `UNIQUE (respond_io_id, message_id, modality)` - the idempotency constraint.
- `INDEX (respond_io_id, modality, period_key)` - the hot enforcement query.
- `INDEX (contact_id, created_at)` - reporting.

Quota counting uses `outcome IN ('accepted','failed')`. Refusals are recorded but do not consume.

**On the idempotency key's shape.** The plan's open item E7 asked whether a multi-image WhatsApp
message yields one `messageId` or several. This cannot be answered from the CRM repo, and getting
it wrong changes the migration. The key here is therefore
`(respond_io_id, message_id, modality)` **plus a nullable `media_ordinal` defaulting to 0**, and
the unique constraint includes it. If one id turns out to carry several images, n8n sends an
ordinal and nothing needs a migration. If it does not, the column stays 0 and the key behaves
exactly as specified. This costs one integer column and removes a schema risk.

### 2.2 `contact_media_limit` - the gate and the overrides

| column | type | notes |
|---|---|---|
| `contact_id` | Text FK `respond_contacts.id` ON DELETE CASCADE | |
| `modality` | Text | PK is `(contact_id, modality)` |
| `is_allowed` | Boolean, not null, **default false** | the gate |
| `monthly_limit` | Integer, nullable | NULL inherits the system default |
| `max_clip_seconds` | Integer, nullable | NULL inherits; voice only |
| `languages` | Text[], nullable | NULL inherits; voice only |
| `warned_period` | Text, nullable | last period the 80 percent warning was sent |
| `degraded_notified_period` | Text, nullable | last period the degradation notice was sent |
| `updated_by`, `updated_at` | | |

**Absence of a row means denied.** That is how "default OFF for every existing contact" is
satisfied without a backfill that writes a row per contact, and it is fail-closed by construction
rather than by a default value someone can flip globally. There is deliberately **no** system-wide
"allow everyone" switch - that would be the footgun that produced the three-week silent outage in
reverse.

DoD gate item 2 (backfill existing rows) is therefore satisfied by argument rather than by a data
migration, and the migration docstring must say so explicitly.

The override semantics follow `AgentFieldAccess` (`app/models/access.py:338-341`), which already
articulates the inherit-unless-overridden pattern.

### 2.3 `media_extraction_job` - the queued work

Separate from the ledger deliberately: the ledger is the metered fact and must not churn, the job
is mutable work state with attempts and results.

| column | type | notes |
|---|---|---|
| `id` | UUID PK | returned to n8n as `job_id` |
| `usage_id` | UUID FK `contact_media_usage.id` ON DELETE CASCADE, unique | 1:1 with an accepted unit |
| `status` | Text | `queued`, `running`, `completed`, `failed` |
| `modality`, `tier` | Text | |
| `media_url` | Text, nullable | |
| `mime_type`, `caption` | Text, nullable | |
| `callback_url` | Text, nullable | opaque, supplied by n8n |
| `callback_headers` | JSONB, nullable | opaque |
| `callback_status` | Text, nullable | `pending`, `delivered`, `failed` |
| `callback_attempts` | Integer default 0 | |
| `context` | JSONB, nullable | opaque turn context echoed back verbatim |
| `result` | JSONB, nullable | the extraction result body |
| `error` | Text, nullable | |
| `rq_job_id` | Text, nullable | mirrors the `ImportJob.job_id` convention |
| `created_at`, `started_at`, `completed_at` | | |

Pattern to follow for the enqueue: `app/api/v1/resources/attachments.py:1357-1370` - write the DB
row first, then `enqueue_job(..., job_id=str(job.id))` so the RQ id is pre-assigned, then store it.

### 2.4 Settings columns on `system_settings`

Added to `app/models/user.py` (the `SystemSetting` model, around the existing AI block at
`:341-347`), and - non-negotiably - to **both** manual dict builders:
`SystemSettingUpdate` (`app/api/v1/user_management/settings.py:17-98`) and the hand-written
response dict in `get_settings` (`:130-212`). A column missing from either is invisible to the
frontend; this is a documented repeat failure in this repo.

| column | default | what it controls |
|---|---|---|
| `media_image_monthly_limit` | 50 | |
| `media_voice_monthly_limit` | 100 | |
| `media_voice_max_seconds` | 120 | |
| `media_burst_limit` | 5 | |
| `media_burst_window_seconds` | 60 | |
| `media_warn_threshold_percent` | 80 | |
| `media_image_provider` / `media_image_model` | NULL / NULL | NULL falls back to the `AIAssistantConfig` row, matching `_resolve_provider` |
| `media_image_degraded_model` | `gpt-4o-mini` | the degraded tier; see 2.5 for the branch when it is absent or equal to the standard model |
| `media_transcribe_model` | `whisper-1` | |
| `media_language_mode` | `pinned` | `pinned`, `hints`, `auto` |
| `media_language_pinned` | `en` | |
| `media_language_hints` | `en,ms,zh` | CSV, only used in `hints` mode |
| `media_sync_wait_seconds` | 30 | how long the endpoint awaits the worker before returning `pending`; this is the value that bounds the lock |
| `media_extraction_timeout_seconds` | 45 | the worker's own hard ceiling; must be >= the sync wait so a job that outlives the wait still finishes and is retrievable |
| `media_max_entities` | 10 | the extraction cap |

`media_transcribe_model` defaulting to `whisper-1` with `media_language_mode` defaulting to
`pinned`/`en` reproduces today's behaviour exactly. The captain's instruction is that the pin
stays until he says otherwise; the mechanism to change it without a deploy is what ships.

The captain also asked to prefer a transcription model that accepts a **list** of language hints
and reports which it detected. That capability is provided by the `hints` mode and by parsing a
`languages` array off the response, so switching the model setting is all that is needed once he
has tested. No model is silently changed on his behalf.

---

## 3. The endpoint

### 3.1 Placement and auth

`app/api/v1/external/media.py`, mounted in `app/api/v1/external/__init__.py` with
`dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["/media"]))]`,
and a matching key added to `EXTERNAL_ENDPOINT_PERMISSIONS` in
`app/api/v1/external/permissions.py`. A completeness test asserts every mounted prefix has an
entry, so omitting it fails the suite rather than shipping unguarded.

New permission slug: `integration.chatbot_media.process`. It needs a **grant migration** for
`admin` and the existing `integration_*` roles, or the feature 403s the moment it is deployed.
This is DoD gate item 3 and it is the single most common way a feature like this ships broken.

Auth is `X-API-Key` through `get_external_api_user` (`app/dependencies.py:491-521`), the same
principal every other n8n route uses.

### 3.2 `POST /api/v1/external/media/process` - one call, awaited

Request:

```jsonc
{
  "respond_io_id": "437264483",
  "message_id": "1783918786000000",
  "media_ordinal": 0,                 // optional, default 0
  "modality": "image",                // or "voice"
  "media_url": "https://...",         // respond.io CDN url
  "mime_type": "image/jpeg",
  "caption": "check stock for these", // may be null
  "duration_ms": 18400,               // voice only, used for the clip cap
  "bytes": 284119,                    // optional
  "turn_id": "9240705",
  "callback_url": "https://automate-sorento.foundryx.my/webhook/...",  // optional
  "callback_headers": {"X-Whatever": "..."},   // optional, opaque
  "context": { }                      // optional, opaque, echoed back verbatim
}
```

Response, always 200 for a well-formed request - the decision is in the body, not the status,
because n8n branches on it:

```jsonc
{
  "job_id": "…",                      // null when the decision is a refusal
  "decision": "accepted",             // accepted | denied_gate | denied_burst | denied_quota | denied_duration
  "status": "completed",              // completed | pending | failed  (accepted decisions only)
  "idempotent_replay": false,
  "tier": "standard",                 // standard | degraded
  "quota": {
    "used": 41, "limit": 50, "remaining": 9,
    "period_key": "2026-08",
    "resets_on": "1 September"        // already rendered; n8n does no date arithmetic
  },
  "notices": [
    {"kind": "warn_80", "text": "…", "append": true}
  ],
  "language_strategy": {"mode": "pinned", "language": "en"},  // voice only
  "result": { }                       // the extraction body, section 3.5; null unless status == completed
}
```

**`status` is what n8n branches on for the slow half:**

- `completed` - the normal case. `result` is populated and the turn continues immediately.
- `pending` - the wait hit `media_sync_wait_seconds` before the worker finished. The job is still
  running; n8n either polls `GET /media/jobs/{job_id}` or waits for the callback if it supplied
  one. This is the graceful edge, not an error, and it is what makes async a switch rather than a
  rebuild.
- `failed` - extraction failed. `result` is null and `error` carries the reason. The turn should
  degrade to caption-only, which is today's behaviour.

A refusal (`denied_*`) returns immediately with no job, no `status` and no `result`.

`denied_quota` is only ever returned when degradation is impossible (no degraded model
configured). The captain's decision is degrade, not refuse, so the normal at-limit path is
`accepted` with `tier: degraded` plus a `degraded` notice.

### 3.3 The order of operations inside the fast path

Inside one transaction, in this order:

1. Resolve the contact from `respond_io_id`. Unknown contact is a `denied_gate`.
2. **Idempotency probe.** `SELECT` the ledger row on the unique key. If present, return the
   stored decision with `idempotent_replay: true` and the existing `job_id`. Nothing else runs.
   This is what makes n8n's `retryOnFail` cheap rather than a second spend.
3. **Gate.** No `contact_media_limit` row, or `is_allowed = false`, gives `denied_gate`.
4. **Duration cap** for voice, against the effective `max_clip_seconds`.
5. **Burst**, via the existing `rate_limit.hit` primitive (`app/services/rate_limit.py:41`) on a
   namespaced bucket. Redis is correct here and only here: the burst window is genuinely
   ephemeral and a reset is harmless. It fails open, which is the right direction for a pacing
   control.
6. **Quota.** `COUNT` over the period index. Over the limit gives `tier: degraded` when a degraded
   model is configured, otherwise `denied_quota`.
7. **Record.** `INSERT ... ON CONFLICT DO NOTHING` on the ledger, then re-select. Recording
   precedes spending, so "crashed after spending, before recording" cannot happen.
8. **Notices.** Stamp `warned_period` / `degraded_notified_period` in the same transaction so each
   notice can only fire once per period per modality.
9. Create the job row and enqueue it.

Everything above is milliseconds of ordinary SQLAlchemy work and runs inline, exactly like every
other route in this repo. The transaction commits here, **before** any waiting begins, so the
ledger row and the decision are durable even if the wait or the worker later dies.

### 3.3b Awaiting the worker without blocking the event loop

The route is `async def`. After the commit it awaits the job:

```
await asyncio.wait_for(_await_job(job_id), timeout=media_sync_wait_seconds)
```

where `_await_job` loops on `await asyncio.sleep(0.25)` and reads the job row through
`await asyncio.to_thread(...)`, using its **own short-lived session** rather than the request's.
Two properties matter and both are the point of the exercise:

- **No synchronous multi-second call ever runs in the handler.** The provider call happens in the
  RQ work-horse process, not in the API process. This is the specific mistake the live portal
  route makes (`app/api/v1/public/ai_extract.py:116` calling the synchronous
  `extract_service.py:238`), which freezes the backend for 5.8-9.8 seconds per request. That
  defect is filed separately and rated low priority; it is not fixed here and it is not copied.
- **Each poll is a short read moved off the loop.** `asyncio.to_thread` keeps even the millisecond
  DB read from occupying the loop, so a hundred concurrent media turns cost sleeping coroutines,
  not blocked workers.

On `TimeoutError` the endpoint returns `status: pending` with the `job_id`. The job keeps running
and the result stays retrievable through the polling endpoint and the callback. Nothing is lost
and nothing is double charged, because the ledger row was written in step 7.

The gate fails **closed** and the quota fails **open**. This is a deliberate departure from the
house style of the existing limiters, which are fail-open by design because they are abuse
ceilings rather than entitlements. The PR description must say so.

### 3.4 `GET /api/v1/external/media/jobs/{job_id}` - the polling fallback

Returns the job status and, once complete, the identical result body the callback carries. Safe
to poll, no side effects. This exists because mid-flow resume was not confirmed (section 1.2).

### 3.5 The result body, and the callback

The `result` object below is the single shape returned three ways - inline on the synchronous
response, from the polling endpoint, and in the callback body. One shape, three transports, so
switching transport changes nothing downstream.

The callback fires only when `callback_url` was supplied. Under the synchronous wire it is
optional and most turns will not need it; it is what makes the async switch free. The worker POSTs
to `callback_url` with `callback_headers` applied verbatim:

```jsonc
{
  "job_id": "…", "status": "completed",       // or "failed"
  "respond_io_id": "…", "message_id": "…", "modality": "image",
  "turn_id": "…", "context": { },             // echoed back unchanged
  "tier": "standard",
  "result": {
    "entities": [
      {"raw": "SRTKS6647", "hint": "product", "current_message": true, "confident": true}
    ],
    "attributes": [
      {"kind": "batch_number", "raw": "YG2539", "confident": true}
    ],
    "conflicts": [
      {"field": "quantity", "entity_raw": "SRTBF31610",
       "values": [{"value": "6", "source": "printed"}, {"value": "4", "source": "handwritten"}],
       "note": "handwritten amendment over the printed quantity"}
    ],
    "image_kind": "document",
    "needs_clarification": false,
    "truncated": false,
    "rendered_text": "please check stock for these products: SRTKS6647",
    "confirmation_message": "…",              // ready to send
    "clarification_message": null,
    "transcript": null,                       // voice
    "languages_detected": null                // voice
  },
  "notices": [ ],
  "error": null
}
```

Delivery is best-effort with bounded retries; a failed callback logs and leaves the result
readable through the polling endpoint. A post-commit side effect never raises - the caller must
not get a 500 for work that succeeded.

---

## 4. Extraction

### 4.1 What is reused, and what is not

Reused, because it genuinely transfers: `ExtractFile` and `_render_files`
(`app/services/ai_extract/extract_service.py:129-135`, `:405-439`) for turning bytes into
provider image parts including PDF and video handling; provider resolution off `AIAssistantConfig`
(`:354-387`); and `_log_usage` (`:968-1001`), which already writes `AIAssistantUsageLog` with
`contact_id`, so token accounting for this feature is free and lands on the existing dashboard.

**Not reused: the prompt and the schema.** This is the premise that was disproved. Measured
against three real Sorento images, the existing `portal.complaint` prompt was flawless on a clean
screenshot, produced **three confident wrong answers** on a photographed RMA form, and found only
the model code on an angled carton photo. It is a good **document** prompt and a bad warehouse
prompt, and no registered schema covers carton model plus batch plus barcode plus box dimension.

Also not reused: `_canonical_product_code` (`:921-933`). Product-code matching is not rebuilt here.
The extraction emits raw strings plus `confident` and lets `resolve-entity` adjudicate, which
already runs a far better ladder with typo tolerance this extraction cannot have.

### 4.2 The new extraction service

`app/services/media_extract/` - a sibling package, not an edit to `ai_extract`, so the live portal
route is untouched.

- `prompts.py` holds the system prompt as a module constant, diffable and unit-testable.
- `schema.py` holds the strict output contract and its Pydantic parse.
- `service.py` holds `MediaExtractService`, which composes `_render_files` for the image parts and
  the provider adapter for the call.

One provider call per image, not two. The prompt classifies and extracts in the same pass, because
a second call doubles both cost and the latency that sits inside n8n's lock budget.

### 4.3 The prompt, and what each rule is for

The prompt has a shared preamble and two lanes selected by the model's own classification of the
image. Every rule below exists because a measured failure demanded it.

**Shared rules:**

1. Transcribe strings **exactly as printed**, including ampersands, punctuation, hyphens and
   spacing. Do not normalise, expand or phoneticise. *(`J&Y WORLD HARDWARE` was returned as
   `JAY WORLD HARDWARE`.)*
2. If a handwritten, stamped or otherwise overlaid value disagrees with a printed one, **report
   both in `conflicts` and do not choose**. Mark the affected entity `confident: false`.
   *(A handwritten 4 was silently preferred over a printed 6, with no flag.)*
3. Dates on these documents are day-first. When day and month are both 12 or less the date is
   ambiguous: return the raw string as printed and flag it rather than emitting a resolved date.
   *(`11/08/2026` was read as November.)*
4. Never invent. Omit rather than guess. A refusal costs one message; a confident wrong code costs
   a wrong business decision.
5. Emit at most `media_max_entities` entities and set `truncated` when you stop.

**Document lane** - delivery orders, RMA forms, invoices, spreadsheet screenshots. This lane keeps
the rules that measurably passed, carried over from `form_schema_registry.py:41-64`:

6. Only the **subject** of the line is a product entity. Compatibility codes named in a
   description, and a wrongly-received part named in a remark, are context and are not subjects.
   *(This trap passed unprompted on the clean screenshot and the rule is worth keeping explicit.)*
7. The customer is the **buyer** being billed, not the seller on the letterhead, not the
   salesperson, not the project name.
8. Formula errors and empty rows are not line items. *(An `#N/A` row.)*

**Label lane** - carton and shelf photos taken at an angle in warehouse light. This lane is new
and is budgeted, not inherited:

9. Attempt each of: model code, quantity, product size, box dimension, batch number, barcode.
10. **Product size and box dimension are different fields on the same label.** Never merge them
    and never report one as the other. When only one dimension is legible, say which it is or set
    `confident: false`. *(The baseline extracted neither.)*
11. A barcode read from digits printed under the bars is `confident: true`; one inferred any other
    way is not.

### 4.4 The output contract

`entities[]` uses the chatbot's own shape verbatim, so downstream cannot tell a photo was
involved: `{raw, hint, current_message, confident}`, with `hint` drawn only from the 14 values in
`docs/flows/sub-query-reformulator.md:33-44` - `product`, `promotion`, `customer`, `transporter`,
`inbound_shipment`, `warehouse`, `attachment`, `form`, `order`, `category`, `brand`,
`attachment_type`, `goods_receive`, `spo`. `current_message` is always `true` for an extraction.

`attributes[]` carries values that have **no hint in that enum** - batch number, barcode, box
dimension, product size, quantity - as `{kind, raw, confident}`. This is the captain's decision of
2026-08-14; section 9 records it and the reasoning. An attribute must never be emitted as an
entity with an approximate hint.

`conflicts[]` is a first-class output, not an afterthought, per the captain's instruction.

### 4.5 Rendering for the parser

`rendered_text` is what the far end patches into the queue item. It must read like something a
customer typed, because that is what the parser is tuned on.

| situation | `rendered_text` |
|---|---|
| caption plus confident entities | the caption with the raw strings appended |
| no caption, confident entities | **null**, with `needs_clarification: true` |
| unclear caption intent | **null**, with `needs_clarification: true` |
| low confidence or conflicts | the caption alone, with the raws appended verbatim |
| nothing extracted | the caption alone - identical to today's behaviour |

The captionless rows are the captain's override of the plan's assume-and-state recommendation.
Guessing intent on top of imperfect extraction stacks two silent failure modes, so the system
asks. `clarification_message` carries the question, naming what was read.

---

## 5. Voice

No transcription code exists anywhere in this repo - verified, zero hits for
`whisper|transcrib|speech_to_text` across `app/`. This is net new, and it is the one place the
"reuse what transfers" instruction has nothing to transfer.

`app/services/media_extract/transcribe.py` posts multipart to the configured transcription
endpoint. The language strategy is built from settings at call time:

- `pinned` sends `language: <media_language_pinned>`. **This is the default and it reproduces
  today's behaviour exactly.**
- `hints` sends `languages: [...]` from the CSV setting, for a model that accepts a list.
- `auto` sends neither.

A `languages` array on the response is recorded on the job and returned in the callback. An
**empty** array is a valid "the model could not make a reliable prediction" signal and is
propagated as such - not as an error, not as silence.

Two operational traps recorded so they are not rediscovered: the upload filename must carry a
usable extension because the format is inferred from it, and WhatsApp voice notes are Opus in an
Ogg container whose acceptance varies by model. Both are handled by sending an explicit filename
derived from the mime type, and by surfacing a provider rejection as a `failed` callback with the
provider's own message rather than a generic error.

---

## 6. Wording

`app/services/media_extract/wording.py` renders every customer-facing string, so the far end sends
a string and formats nothing. Drafts are taken from the captain's `customer-wording.md` and the
four rules it carries are implemented as behaviour, not convention:

1. The 80 percent warning fires once per contact per period per modality, enforced by
   `warned_period` on the limit row, stamped in the same transaction as the decision.
2. The degradation notice is a separate kind with its own column, sent when degradation first
   happens in a period.
3. Notices carry `append: true` and are never returned instead of the answer.
4. Dates render as "1 September". Counts render as "X of Y left", never a percentage.

Changes from the drafts, flagged as the brief requires:

- The at-limit degradation text keeps the captain's meaning but is tightened to lead with the
  accuracy warning rather than the allowance, because the accuracy warning is the part that
  prevents harm. The allowance sentence follows it.
- The burst message is suppressed for the remainder of the window, so fifty images produce one of
  it. The draft did not say this and without it the pacing message becomes the spam.
- A new `not_enabled` variant for image is added, mirroring the live voice sentence in shape so
  the two features read as one, per the draft's own stated intent.

---

## 7. Frontend

Phase 1 is the frontend against mocks, and it comes before any backend code.

**Contact surface.** `ContactMediaAccessSection.tsx` in
`sorento_crm_frontend/app/(protected)/user-management/contacts/[id]/components/`, rendered
alongside the existing `ContactMarketSegmentSection` and `ContactAttachmentTypesSection`. Clone
`ContactAttachmentTypesSection.tsx` - it is the right precedent: single `{contactId}` prop, owns
its react-query keys, invalidate plus toast on success, and an `AlertDialog` in front of the
destructive edit.

It renders **both** modalities always, each with an explicit empty state, per the standing rule
that a detail page never hides a section on missing data.

**Settings surface.** `app/(protected)/user-management/settings/chatbot-media/page.tsx`, cloned
from the `portal-revisions` settings page, which is the most recent and smallest precedent and
already carries the `components/`, `hooks/`, `lib/`, `services/` layering this repo enforces.

Layering is the standing one: UI to hook to feature service to `lib/api-client`. `extractApiError`
is used, never hand-rolled. Every optional select is `clearable`. Both surfaces are verified at
375px and 1280px.

---

## 8. What gets measured, and how

Two measurements are owed and both are produced by this work rather than asserted.

**Fast-path latency.** The decide-and-record half, measured on its own, because it is what every
refusal and every idempotent replay costs and it bounds the floor of the call. Method: a pytest
benchmark against a seeded contact on local Postgres plus Redis, sampling over enough iterations
to report p50 and p99 separately for the accepted, replayed and refused paths. The replay path
matters most, because the recommended `retryOnFail` makes it the common case under transient
failure.

**Worst-case end-to-end call.** What n8n's node timeout has to clear, and what the lock budget is
spent on. Reported as the fast path plus measured extraction, plus the enforced
`media_sync_wait_seconds` ceiling, so the number is a bound rather than an average.

**Event-loop non-blocking, demonstrated not asserted.** A test issues a media call whose extraction
is stubbed to take several seconds and, while it is in flight, issues a second unrelated request to
a trivial endpoint on the same API process. The second request must return promptly. This is the
regression guard for the whole point of section 3.3b, and it is the thing that would silently rot
if someone later "simplified" the await into a direct call.

All three are reported in the PR description with numbers, not claims.

**Corpus extraction.** The three real Sorento images are run through the shipped extraction and
scored per field against the written ground truth as exact match, plausible-but-wrong, or refused.
Plausible-but-wrong is the outcome that matters and is reported explicitly, including whatever
still fails. The results land in
`documentation/plans/ideation/chatbot-media-endpoint-corpus-results.md` and are summarised in the
PR. An extraction path that has never been run against a real photo is not done.

---

## 9. The entity-hint question - DECIDED

**Decision, captain, 2026-08-14: Option A. Batch number, barcode, box dimension and product size
are emitted as unhinted `attributes[]`. The 14-value enum is NOT extended.**

The question and the reasoning that produced the recommendation are kept below, because the
reasoning is what a future change to this has to argue against.

**The entity-hint enum has no value for batch number, box dimension or barcode.**

The 14-value enum is fixed by `docs/flows/sub-query-reformulator.md:33-44` and is read by
`resolve-entity` as `allowed_entity_types[]`. A carton label yields three things it cannot express.

**Recommendation: carry them as unhinted `attributes[]`, do not extend the enum in this task.**

- Extending the enum is a change to a contract owned by the n8n side, and n8n is explicitly a
  separate follow-up. A CRM that emitted `hint: "batch"` today would emit a value
  `resolve-entity` does not accept, which fails or silently drops rather than degrading.
- Unhinted attributes are useful immediately with zero downstream change: they render in the
  confirmation message, so a dealer photographing a carton is told the batch and barcode were read
  even though nothing is looked up against them yet.
- It is reversible. If the captain wants a carton photo to be *answerable* on batch or barcode,
  that is a resolver capability first and an enum value second, and the extraction change is one
  line once the resolver can take it.

This was escalated rather than chosen silently, and the captain confirmed Option A.

---

## 10. Slice order

1. **S1** - settings columns, the two tables, both operator surfaces. Frontend mock first, then
   backend. This makes access and usage **visible and controllable before anything is enforced**.
2. **S2** - the fast path. Nothing is spent yet; the endpoint returns decisions and writes ledger
   rows.
3. **S3** - the job, the callback and the polling endpoint, with a stub extraction, so the async
   spine is proven before the expensive part is attached.
4. **S4** - image extraction and the corpus run.
5. **S5** - voice transcription.
6. **S6** - wording, threaded through everything above.

Each slice is a vertical tracer through model, migration, service, route and tests.

---

## 11. Things this deliberately does not do

- **No image storage.** Bytes are fetched, sent to the model and dropped. Storing customer photos
  raises a retention question nobody has asked for.
- **No product-code matching.** `resolve-entity` owns that and does it better.
- **No respond.io custom-field fallback.** The captain moved the gate to the CRM precisely because
  that pattern produced a silent three-week outage; a transitional fallback would keep the failure
  mode alive.
- **No fix for the blocking `AIExtractService.extract` call on the portal route.** It is live,
  independent, filed separately and rated low priority. This work does not touch it and does not
  copy it.
- **No n8n changes.** Separate task.
