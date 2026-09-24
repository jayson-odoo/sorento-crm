# PLAN - Ideation intake redesign (issue #1172)

**Status:** approved by the owner 24 Sep 2026 (lavish review, "ok cool, proceed"), R18 framework
constraint binding; tickets pending; nothing built.
Track: full (shared-service migration for `ideas.title`, `ideas.submitter_tier`,
`ideas.status_token`, the idea-number sequence; two repos).
**UAC:** `ideation-intake-redesign-24sep-acceptance-criteria.md` (this plan fulfils it; the
Journey is there).
**Evidence:** PR #1176, `documentation/plans/ideation/REVIEW-ideation-flow-ux-24sep.md`
(findings F1 to F10), and the code map comment on #1172.
**Not in this plan (in flight):** #1178 (an open draft keeps the ideate lane on a question or
bare confirm), #1179 (test turns reach the real intake with `is_test`; sorento PR #1182,
shared-service PR #84), #863 (chatbot focus feature, needed only for sample (h)'s automatic
mid-draft-detour return, see Dependencies). R8 housekeeping is PR #1181.
**Classification:** core change to the existing ideate lane (sorento) and the existing
ideation module (shared-service). No new module, no new endpoint, no new table in sorento.

## How the facts below were checked

- **Sorento:** every sorento path and line was read on `origin/main` (855ccf0c) in this lane.
- **Shared-service:** `jayson-odoo/foundryx-shared-service` was NOT readable from this planning
  session (GitHub access scoped to sorento-crm only). The shared-service facts below come from
  what sorento sends and reads today (verified in sorento code), PR #1176's review (which ran a
  local shared-service and quoted its replies and rows), and the #1172 code map. The four
  files the plan touches are named as `shared-service:<path>` from the brief:
  `service_backend/modules/ideation/services/intake.py`,
  `service_backend/modules/ideation/services/intake_definitions.py`,
  `service_backend/modules/ideation/models.py`,
  `service_backend/modules/ideation/routers/intake.py`.
  **First task of the S1 ticket:** read those four files and correct this plan where it
  disagrees (field names, where the duplicate check runs, how answers are stored). Anything
  marked "(to confirm in S1)" is an assumption, not a fact.

## Current state (verified)

Sorento, per turn (`sorento_crm_backend/app/services/ideation_turn_service.py::handle_turn`):

1. Reads the pointer from `session_vars.ideation` (`draft_id`, `status`, `missing`,
   `transcript`, media state).
2. Runs `extract_ideate_turn` (`app/services/ideation_extractor.py`), a schema-forced LLM call
   returning `{fields, remove, confirm}`; `confirm` is forced false unless `status == "review"`
   (line 157 onward).
3. POSTs to `{base_url}/ideation/intake/create-idea` (`_CREATE_IDEA_PATH`) with
   `product_id`, `submitter_contact_id` (phone), `message_text`, `raw_transcript`, `fields`,
   `remove`, `confirm`, and optionally `submitter_name`, `attachments`, `draft_id`,
   `discard_draft_id`. PR #1182 adds `is_test`.
4. Reads `status`, `draft_id`, `reply_text`, `link`, `missing` from the response. Clears the
   pointer on `complete` / `duplicate` (`_TERMINAL_STATUSES`), keeps it otherwise.

The lane (`app/services/chatbot/lanes/ideate.py::build_reply`) appends `link` on `complete`
when the text does not already hold it.

Shared-service (from the review's walk): four required fields; fixed templates ("Here's what
I've got so far ... Still need: ..."); duplicate check upvotes the match and leaves the new
draft row orphaned (F7); `complete` returns "Your idea has been captured. Track it here:
<link>" (F9); no title (F10).

Access: the parser's `routing.suggested_agent` is `ideation` for ideate turns
(`app/services/chatbot/contracts.py`, `SUGGESTED_AGENTS`), checked against
`access_agents` / `contact_agent_access` (`app/models/access.py`); a denial renders
`copy.render("access_denied", team=...)` in `app/services/chatbot/lanes/canned.py::access_denied_text`.

## Contract (sorento <-> shared-service, `POST /ideation/intake/create-idea`)

One endpoint, as today. Every change is an additive optional field, so an old sorento keeps
working against a new shared-service (AC-1117). **Deploy order: shared-service first.**

### Request fields

| Field | Type | Today | Slice | Meaning |
|---|---|---|---|---|
| `product_id` | str | yes | - | unchanged |
| `submitter_contact_id` | str (E.164) | yes | - | unchanged |
| `submitter_name` | str? | yes | - | unchanged |
| `message_text` | str | yes | - | unchanged |
| `raw_transcript` | str | yes | - | unchanged |
| `fields` | {key: str} | yes | - | unchanged; keys problem, proposed_solution, impact, department |
| `remove` | [key] | yes | - | unchanged |
| `confirm` | bool | yes | - | unchanged; sorento sets it from `review_action == "submit"` (S2) |
| `draft_id`, `discard_draft_id`, `attachments` | | yes | - | unchanged |
| `is_test` | bool | #1182 | - | unchanged (owned by #1179) |
| `title` | str? (1 to 8 words) | new | S1/S2 | short label; latest value wins; 422 over 8 words |
| `skip` | [key]? | new | S1/S2 | optional keys the user declined; never asked again |
| `cancel` | bool? | new | S1/S2 | close the open draft; no idea number |
| `duplicate_choice` | "vote" \| "separate"? | new | S1/S2 | answer to a `duplicate_candidate` |
| `submitter_tier` | str? | new | S1/S2 | the contact's access type code (R7) |

### Response fields

| Field | Type | Today | Slice | Meaning |
|---|---|---|---|---|
| `status` | str | yes | S1 | `collecting`, `review`, `duplicate_candidate` (new), `complete`, `voted` (new), `cancelled` (new). `duplicate` is retired. |
| `draft_id` | str | yes | - | unchanged |
| `reply_text` | str | yes | S1 | the template text; now the FALLBACK only (R5) |
| `missing` | [key] | yes | S1 | required fields still empty (after S1: only `problem` can appear) |
| `next_field` | key? | new | S1 | the one optional field to ask next, null when none |
| `title` | str? | new | S1 | the stored title |
| `captured` | {key: str} | new | S1 | the draft's current answers (skipped keys absent) |
| `duplicate_candidate` | {idea_number, title}? | new | S1 | set only on `duplicate_candidate` |
| `idea_number` | str? | new | S1 | `IDEA-0123` on `complete`; the candidate's on `voted` |
| `link` | str? | yes | S5 | R6 originally said null for WhatsApp-source ideas; **R13 (lavish review round 3, confirmed):** carries the S5 public status-page URL for every idea regardless of source - `{product_domain_base}/public/ideas/{status_token}`, a signed per-idea token, no login, title/status/idea_number only. Not the old SSO-gated `/ideas/{id}` page. |

No idea UUID is carried into any user-facing reply; sorento only ever shows `idea_number` and
`title` (cursor rule: no UUIDs in UI, applied to WhatsApp copy too).

### Shared-service storage (S1, to confirm in S1)

- `ideas.title` text null (R2).
- `ideas.submitter_tier` text null (R7).
- `ideas.idea_number` text unique null, filled on capture from a new Postgres sequence,
  formatted as `IDEA-` plus the number zero-padded to at least four digits, growing past
  9999 (so not a plain `lpad(..., 4)`, which truncates longer values; AC-1111). Existing
  captured ideas are backfilled in `created_at` order in the same migration.
- Skipped optional fields: stored on the draft where answers already live (a skipped marker in
  the existing answers structure), no new table. If answers are columns rather than a map,
  one `skipped_fields` jsonb column on `ideas`.
- `cancelled` / `voted`: terminal statuses on the draft row, or the row deleted, whichever the
  existing status engine (draft -> captured -> triaged -> ...) allows without a new graph edge
  from anywhere but `draft`. Either way the review's orphan draft (F7) no longer exists.

## Slices

Each slice: tests in both repos written first (tester, then coder), one console YAML case in
`sorento_crm_backend/tests/chatbot/console_cases/2026-09-24-ideation-intake.yaml` once #1179
has merged (before that, the console never reaches the intake), and a live console walk at
the end of the lane (AC-1501).

### S1 - Shared-service contract

**Side (R18):** shared-service intake only (`intake_definitions.py`, `models.py`,
`routers/intake.py`, `services/intake.py`). No sorento file touched. Engine: untouched.

**Shared-service part** (branch in foundryx-shared-service):

- `shared-service:service_backend/modules/ideation/services/intake_definitions.py`: `problem`
  required, the other three optional (R1). The form-engine document keeps all four.
- `shared-service:service_backend/modules/ideation/models.py` + migration: `title`,
  `submitter_tier`, `idea_number` + sequence + backfill, skip storage (above).
- `shared-service:service_backend/modules/ideation/routers/intake.py`: the new request and
  response fields (Contract section); 422 for a title over 8 words.
- `shared-service:service_backend/modules/ideation/services/intake.py`:
  - `next_field`: first optional key not answered and not skipped, fixed order
    proposed_solution, impact - **department is dropped from this sequence entirely (R15,
    lavish review round 3: "i think don't need to ask department ba")**; it is never
    nominated as `next_field`, only ever captured when the dealer volunteers it. `review` when
    `problem` is set and both proposed_solution and impact are each answered or skipped,
    regardless of whether department was ever mentioned.
  - Duplicate: same check as today (pg_trgm similarity), limited to `is_test = false`; returns
    `duplicate_candidate` and writes nothing else. `duplicate_choice: "vote"` upvotes the
    candidate and closes the draft (`voted`); `"separate"` records that this draft declined
    that candidate (so it is not offered again) and carries on.
  - `cancel: true` closes the draft (`cancelled`).
  - `confirm: true` in `review` captures and assigns `idea_number`.
  - `link` carries the S5 public status-page URL for every idea, WhatsApp source included (R13,
    confirmed - supersedes R6's "null for WhatsApp" and round 2's proposal; see S5 below for the
    page itself).
  - All templates are point form (R10, amended by R16 to put Problem first): `complete` becomes
    line 1 the title, line 2 "Idea <idea_number> is in. We'll update you on WhatsApp.", line 3
    "Track it here: <link>"; `duplicate_candidate` becomes line 1 "Similar idea exists:
    <title>", line 2 "Vote for that one, or keep yours separate?"; each `next_field` template
    becomes the title line, then one line per field present in the order Problem, Solution,
    Impact, Department (Problem always present - it is the one required field), then the
    field's question alone as the last line. All of them are the R5 fallback, so they must meet
    the same shape rules as the LLM reply (AC-1310).
- Board, ideas list and detail show `title`, falling back to `problem` when null (R2); triage
  views show `submitter_tier` (R7).
- **Tests (pytest, shared-service):** AC-1101 to AC-1117 (AC-1102/AC-1104 updated for R15's
  department drop), including a concurrency test for the sequence (AC-1112) and the
  old-sorento request shape (AC-1117).

**Sorento part:** none in code. The S1 ticket updates this plan's Contract section with the
real shared-service field names if they differ.

### S2 - Sorento payload, title extraction, duplicate ask, semantic review

**Side (R18):** sorento ideate lane / `ideation_turn_service.py` (`ideation_extractor.py`,
`ideation_turn_service.py::handle_turn`, `lanes/ideate.py::build_reply`) - all lane-side
services the ideate lane already calls, none of it `app/services/chatbot/turn/*`. Engine:
untouched.

**Shared-service part:** none beyond S1 (S1 must be deployed first).

**Sorento part:**

- `app/services/ideation_extractor.py`: the schema becomes `{fields, remove, skip, title,
  review_action, change_text, duplicate_choice}`; `review_action` is `"submit" | "change" |
  "cancel" | "none"`, `duplicate_choice` is `"vote" | "separate" | "none"` (strict-mode
  enums, every property required, as today). The context block gains `next_field` and the
  duplicate candidate title. Deterministic guards after the model:
  - `title` cut to 8 words (AC-1202);
  - `skip` limited to optional keys (AC-1205);
  - `review_action == "submit"` only counts in `review` (AC-1211, the existing guard moved).
  `IdeateExtraction` gains the new fields; `confirm` stays on it, derived, so
  `handle_turn` keeps one place that sets it.
- **R17 (lavish review round 3, 24 Sep 2026):** the model decides which field a message
  updates by the meaning of the whole draft-so-far, never by which field `next_field` hinted -
  the hint is only a hint. A message that reads as more problem detail while `next_field` is
  `proposed_solution` updates `fields.problem` (the extractor merges/extends it, not
  `fields.proposed_solution`), and the next turn asks `proposed_solution` again - or moves on
  if the user skips it on a later turn - without treating the mismatch as an error (AC-1219).
- `app/services/ai_prompt_registry.py::_ideate_extractor_fallback`: rewritten for the new
  schema, with the review and skip examples from the review doc (yes / ok / boleh / submit;
  skip / don't know / later / dunno lah). **Before S2 ships:** check prod
  `ai_prompt_versions` for a published `ideate_extractor` version; if one exists, publish the
  new text as a version (the fallback alone would not reach live turns). No migration seeds
  one today (`grep ideate_extractor alembic/versions` is empty).
- `app/services/ideation_turn_service.py::handle_turn`:
  - payload gains `title`, `skip`, `cancel`, `duplicate_choice`, `submitter_tier`;
  - `duplicate_choice` defaults to `"separate"` when the pointer's status is
    `duplicate_candidate` and the extractor did not say `vote` (AC-1214);
  - `submitter_tier`: first code of `RespondContact.access_types` (relationship already
    ordered by `sort_order, code`, `app/models/access.py`); read in `_get_contact_row`, which
    today selects only phone, names and session_vars (AC-1207);
  - department: captured as free text from the dealer's own words in the message when present,
    stored as typed (no lookup against `respond_contact_customers`) - it is already one of the
    keys the extractor's `fields` map carries, so no extractor change is needed beyond the
    existing field extraction. It is NOT a second required question (the one required field
    ruling stands), so when the dealer never mentions it the field stays blank and the bot does
    not ask (R14, confirmed - "yes"; R15, confirmed - dropped from S1's `next_field` sequence
    too, so it is never actively asked in any turn) (AC-1206);
  - `_TERMINAL_STATUSES` becomes `{"complete", "voted", "cancelled"}` (AC-1215);
  - the pointer keeps `next_field` (the extractor's context next turn) alongside `missing`,
    and the candidate title while `duplicate_candidate`.
- `app/services/chatbot/lanes/ideate.py::build_reply`: drop the link append (AC-1216) - the
  composed reply carries the link itself now (S3), not a raw string append.
- `app/schemas/external/ideation.py` / MCP `crm_ideation_turn`: no change (the new fields are
  between sorento and shared-service only; `IdeationTurnResponse.link` stays for shape, and now
  carries the S5 URL like every other response - R13).
- **Tests (pytest, sorento):** `tests/test_ideation_turn.py` (payload fields, terminal
  statuses, duplicate default, tier, department) and `tests/test_ideation_parser.py` or a new
  `tests/test_ideation_extractor.py` (guards, with a stubbed provider, including R17's
  semantic-field-capture guard, AC-1219). AC-1201 to AC-1216, AC-1219. Console cases AC-1217,
  AC-1218.

### S3 - LLM replies with template fallback

**Side (R18):** sorento `ideation_turn_service.py` plus one existing shared seam,
`lanes/canned.py::access_denied_text` (a function every lane's denial already calls; this adds
one `if agent == "ideation"` branch inside it, not a new engine concept). Not
`app/services/chatbot/turn/*`. Engine: untouched, with that one named exception.

**Shared-service part:** none beyond S1 (the facts are in the S1 response; the templates are
the fallback).

**Sorento part:**

- One function, `compose_ideate_reply(db, *, result, user_message) -> str`, in
  `app/services/ideation_turn_service.py` (no new module: one caller today). Builds a facts
  block from `status`, `title`, `captured`, `next_field`, `duplicate_candidate`,
  `idea_number`, and `link` (R13, confirmed - the S5 status-page URL, on every response), sends
  it with the user's message to the same provider plumbing the extractor uses (`get_provider`,
  `AIAssistantConfigService`), prompt key `ideate_reply` in `ai_prompt_registry` (fallback text
  in code, like `ideate_extractor`).
- Checks, then fallback to `result["reply_text"]` on any failure (AC-1302 to AC-1305, AC-1310,
  AC-1311): point form (R10, amended by R16) - the title (or the duplicate candidate's title)
  first, then one line per field present, in order Problem, Solution, Impact, Department
  (Problem always present - it is the one required field, echoed back from the very first
  reply), skipped or unanswered fields omitted, a reply that packs fields into one sentence
  fails; non-terminal ends in exactly one `?`/`？` as its own final line; `complete` contains
  `idea_number` verbatim and at most the one URL named by `link` and no other `http`;
  `duplicate_candidate` contains the candidate title. Facts never come from the model: if the
  number, title, or link is missing or altered, the template wins.
- The media menu (`menu_text`) is still appended after the composed reply, as today.
- Not-allowed: in `app/services/chatbot/lanes/canned.py::access_denied_text`, when the agent
  is `ideation`, compose through the same function with facts `{denied: "ideation"}`, falling
  back to today's `copy.render("access_denied", ...)` (AC-1307). Other agents unchanged: one
  case, one branch.
- **Tests (pytest, sorento):** a new `tests/test_ideation_reply.py` with a stubbed provider:
  each status, each fallback trigger, the Malay case, the denial branch, the point-form shape
  with Problem first (AC-1310), and the link line (AC-1311). Console cases AC-1308, AC-1309.

### S4 - 24h reminder and close

**Side (R18):** sorento `ideation_turn_service.py` plus one new scheduler tick,
`app/scheduler/task_scheduler.py::_ideation_idle_sweep_tick`, the same shape as the existing
unrelated `_chatbot_delegated_sweep_tick` - a cron-style job outside the per-turn pipeline, not
`app/services/chatbot/turn/*`. Engine: untouched.

**Shared-service part:** none beyond S1 (`cancel: true`).

**Sorento part:**

- No new table: the pointer already carries `updated_at` (`_now_iso()`, written every turn).
  The sweep adds `reminded_at` to the same blob.
- `sweep_idle_ideation_drafts(db)` in `app/services/ideation_turn_service.py`: selects
  `respond_contacts` where `session_vars ? 'ideation'`, then in Python:
  - `updated_at` older than 24h and no `reminded_at` -> send the reminder, write
    `reminded_at`;
  - `reminded_at` older than 24h -> `call_create_idea` with `{product_id, draft_id,
    cancel: true, submitter_contact_id}`, then clear the pointer; on outage keep it
    (AC-1407).
  Written with `overwrite_for_contact`, reading the row fresh, preserving other keys (as
  `handle_turn` does). Test turns never reach it: #1182 stops test turns writing the pointer.
- Send: `send_text_or_template(db, identifier=..., text=<reminder>, use_case=
  "ideation_draft_reminder")` (`app/services/respond_messaging_service.py`). The reminder is
  due at 24h idle, which is exactly when the WhatsApp free-text window closes, so it will
  almost always go as a template: add `"ideation_draft_reminder"` to
  `TEMPLATE_DEFAULT_USE_CASES` (`app/models/respond_template.py`, a tuple, no migration) and
  map an approved template in System Settings before go-live. Unmapped -> the send is skipped
  and logged, the draft still closes (AC-1405). Reminder text: fixed ("Your idea "<title>" is
  still open. Reply to finish it, or say cancel."), not the LLM: nobody's message to take a
  language from, and a template has fixed wording anyway.
- Tick: `_ideation_idle_sweep_tick` in `app/scheduler/task_scheduler.py`, same shape as
  `_chatbot_delegated_sweep_tick`, `IntervalTrigger(minutes=15)` (AC-1408). Runs only in the
  worker with `ENABLE_SCHEDULER=true`, like every other tick.
- `handle_turn` drops `reminded_at` when it rewrites the pointer (it already rebuilds the blob
  from scratch each turn, so this is a test, not a code change) (AC-1403).
- **Tests (pytest, sorento):** a new `tests/test_ideation_idle_sweep.py` with frozen time and
  stubbed send / create-idea: AC-1401 to AC-1408.

### S5 - Public idea status page (R13, "commit to public status page slice")

**Side (R18):** shared-service only - a new model column + migration, a new public router, a
new public frontend page. No sorento file touched beyond what S3 already reads (`link` is
already a fact in the composer's facts block). Engine: untouched.

Graduated from the Dependencies section's `S-link` placeholder to a real slice in this plan
(lavish review round 3, 24 Sep 2026). Resolves F9 for good: a WhatsApp-only submitter gets a
link they can open with no CRM login, showing only title, status and idea number - never any
dealer or customer data, never another idea's data.

**Shared-service part** (branch in foundryx-shared-service):

- `shared-service:service_backend/modules/ideation/models.py` + migration: `ideas.status_token`
  text, unique, a signed/random per-idea value (`secrets.token_urlsafe`-class generation, not
  the sequential `idea_number` and not the row's UUID), minted once on capture (idempotent,
  alongside `idea_number` in the same transition).
- New PUBLIC route, mounted `"public": true` like the existing `/embed/session` family in
  `shared-service:service_backend/modules/ideation/routers/` - no JWT, no `require_module`
  gate, the token itself is the credential: `GET /public/ideas/{token}` returns `{title,
  status, idea_number}` only. An unknown, malformed, or another idea's token returns 404 - no
  enumeration hint, no distinguishing "wrong token" from "right token, no access".
- New public, chrome-less frontend page, `service_frontend/app/public/ideas/[token]/page.tsx`
  (no `(protected)` wrapper, no SSO exchange - the URL itself is the credential) rendering
  those three fields; an unknown token renders a plain not-found page, never a stack trace or a
  login prompt.
- `mint_idea_link` (or its S5 replacement) returns this new page's URL -
  `{product_domain_base}/public/ideas/{status_token}` - for `link` on every idea regardless of
  source, WhatsApp included, and regardless of `is_test` (the tracking link already mints for a
  test turn per #1179; S5 keeps that true for its own link).
- **Tests (pytest, shared-service):** AC-1601 to AC-1604.

**Sorento part:** none beyond S3 (already composes `link` into the point-form `complete` reply,
R13; the URL shape changing from the old SSO page to the S5 public page is invisible to
sorento - it is still just a string in the response).

## Decisions made in planning (beyond the rulings)

- **P1 One endpoint, additive fields.** No new shared-service route for vote or cancel: they
  are two more optional fields on the call sorento already makes, and it keeps deploy order
  trivial (AC-1117).
- **P2 Skips are explicit.** The extractor emits `skip`; a field is not skipped just because a
  turn did not fill it, so "what do you mean impact?" does not lose the question (AC-1204).
  "Asked once" then holds because shared-service never returns a skipped or answered field as
  `next_field` again.
- **P3 Tier is one code.** R7 says "the submitter's tier"; a contact can hold several access
  types, so sorento sends the first in the relationship's existing order. Trigger for a list:
  triage asks to filter on a second type.
- **P5 No new sorento module or table.** Reply composer and idle sweep sit in
  `ideation_turn_service.py`; state stays in `session_vars.ideation`.

## Rulings (owner, grill of 24 Sep 2026, binding, quoted)

> **R1 Fields:** only the idea text (problem) is required. Proposed solution, impact and
> department are asked once each, optional, skippable by any natural "skip / don't know /
> later"; department is inferred from the contact's company when known and only asked when
> unknown. Shared-service intake definition changes accordingly (required flags); the
> form-engine document keeps the four fields.

> **R2 Title:** sorento's extractor generates a short title (max 8 words) from the idea text and
> sends it in the payload; shared-service stores it (new column ideas.title) and the board and
> lists show it. No category.

> **R3 Review turn is semantic:** the parser emits submit / change / cancel (with the change
> text) for a draft under review; the engine applies it deterministically. Accepts natural
> yes/ok/boleh/submit as submit. Cancel closes the draft. No auto-submit. A draft idle for 24
> hours gets one WhatsApp reminder, then closes (sorento side scheduler task).

> **R4 Duplicate:** no auto-upvote. When the intake finds a similar non-test idea, the bot names
> it ("Similar idea exists: <title>") and asks vote-with-it or keep-separate; default keep
> separate when the user moves on. Shared-service returns the candidate instead of acting;
> sorento asks; a second call applies the choice.

> **R5 Replies:** written by the LLM in sorento from the intake's facts (captured, still open,
> duplicate candidate, idea number), in the user's language, always ending with the one
> question asked. The shared-service template text is the fallback when the LLM fails. Facts
> never come from the LLM. The not-allowed reply gets the same treatment.

> **R6 After submit:** reply with the idea number (shared-service returns a short human number,
> e.g. IDEA-0123, new sequence) and "we will update you on WhatsApp". No tracking link for
> WhatsApp submitters. Status updates over WhatsApp are a later slice, listed in the plan as
> out of scope.

> **R7 Access:** unchanged. The ideation access agent (access_agents code ideation,
> contact_agent_access per contact) gates the lane. The idea carries the submitter's tier
> (contact access type) for triage.

> **R8 Housekeeping:** plan Status lines fixed by PR #1181.

> **R9 Slice order:** S1 shared-service contract (required flags, title, duplicate candidate,
> idea number, tier); S2 sorento payload + title extraction + duplicate ask + semantic review;
> S3 LLM replies with template fallback; S4 24h reminder and close. Each slice: pytest per
> repo, console YAML case (possible once #1179 lands), live console at the end.

Lavish review 24 Sep 2026: owner asked for sample conversations; added below the Journey.

> **Lavish review 24 Sep 2026 - Department (amends R1):** owner, replying to the P4 assumption
> that department comes from the linked customer name: "hmm department is just free text
> thought." Department is free text captured from the dealer's own words when given, never
> derived from `respond_contact_customers`; it stays optional and is not a second required
> question, so when the dealer never mentions it the field simply stays blank and the bot does
> not ask (confirmed by R14; also see R15, S2's department bullet, and AC-1206 above). This
> supersedes the "inferred from the contact's company when known" clause in R1; R1 itself is
> left as originally quoted above for the record.

Lavish review round 2, 24 Sep 2026: owner walked the sample conversations and raised three more
points, folded below.

> **R10 Point form (lavish review round 2, 24 Sep 2026):** owner, on the review turn's
> one-sentence recap ("Here's ... solution: ...; impact: ..."): "i think our answer needs to be
> more point form, is it because it is llm so it is like that very random?" and, repeated,
> "again i need the answer to be more point form." To be plain about the second half of the
> owner's question: the one-sentence wording in this plan's own sample conversations was this
> plan's own proposed wording, never LLM output and never LLM randomness - nothing about an LLM
> makes a reply less point-form; the shape is a rule the composer (and its template fallback)
> both have to satisfy either way. Ruling: the review turn and every confirmation that recaps
> the draft (the initial understanding turn, a next-field ask, the review turn, the
> `duplicate_candidate` reply, and the `complete` reply) are point form - line 1 the generated
> title (the candidate's title for `duplicate_candidate`; the completion headline for
> `complete`), then one short line per captured field present so far in the fixed order
> Solution, Impact, Department (only the fields present; a skipped or not-yet-answered field is
> left out, never shown as blank), then the one question on its own final line (no question
> line on a terminal reply). A plain clarifying answer ("what do you mean impact?") is not a
> recap and keeps its own prose shape, still ending in the one question. See AC-1310.

> **R11 Tracking link in the confirmation (lavish review round 2, 24 Sep 2026, PROPOSED - owner
> to confirm):** owner, on "Got it - idea IDEA-0184 is in": "do they have the link to view
> this?" Checked against `foundryx-shared-service` (read-only): the shared-service already
> mints a link on every `complete` today via
> `service_backend/modules/ideation/services/sinks.py::mint_idea_link`, returned as the existing
> `link` response field - `{product_domain_base}/ideas/{idea_id}`. R6 forced this field to null
> for a WhatsApp-source idea, precisely because that page lives at
> `service_frontend/app/(protected)/ideation/ideas/[id]/page.tsx` - the SAME SSO-gated CRM page
> F9 flagged, not a separate public tracking page; there is no other, public, tracking-only page
> in the shared-service codebase today (its only other idea-facing surface, `/embed/ideas/{id}`,
> also requires a signed embed assertion minted by a logged-in CRM host, not something a bare
> WhatsApp contact holds). Plainly: a link a WhatsApp-only dealer can open without a CRM login
> does not exist today. If the owner wants one, that is a new small slice - a public, read-only
> idea status page in the shared service - named `S-link` (proposed, not yet planned) in the
> Dependencies section below, not something this proposal can hand them by reusing `link` as is.
> Proposal, pending the owner's confirmation with that fact in hand:
> stop forcing `link` to null for a WhatsApp source: send both the idea number and the link in
> the `complete` confirmation, point form (R10) - line 1 the title, line 2 the idea number and
> the WhatsApp-update line, line 3 "Track it here: <link>" when the product has one configured.
> If confirmed, this amends R6 and requires rewriting AC-1114 (currently: `link` is null for a
> WhatsApp source) and the "no URL" clause of AC-1303 in the same change; neither is rewritten
> here. See AC-1118 (shared-service) and AC-1311 (sorento).

> **R12 Mid-draft detour (lavish review round 2, 24 Sep 2026):** owner: "what happen if they ask
> about other things midway like ask stock, then come back to this, i believe our focus feature
> support this right?" Answer: the ideation draft itself is never at risk - its pointer lives on
> `session_vars.ideation` on the contact's session, independent of whatever lane any other turn
> runs in, so a stock question in between changes nothing about the draft. Whether the RETURN is
> automatic (the bot notices "ok back to my idea" and resumes the same field on its own) depends
> on two pieces not in this plan: the chatbot's focus feature (#863, open) and the open-draft
> lane rule (#1178, PR #1185, open) - the same lane-stickiness problem F3 named for a bare
> "confirm", generalised here to any short return-to-lane phrase. Until both land, the dealer
> resumes by naming the idea again rather than a bare "back to my idea" being enough. See sample
> (h) and the Dependencies section below.

Lavish review round 3, 24 Sep 2026: owner walked the round-2 fold and gave five more rulings,
folded below as R13 to R17.

> **R13 Commit to the public status page slice (amends R11, confirmed):** owner: "commit to
> public status page slice." `S-link` (named as a not-yet-planned dependency in round 2) becomes
> a real slice in this plan, S5: a public, read-only idea status page in the shared service,
> reached by a signed, unguessable token link minted per idea, showing title, status and idea
> number only - no dealer or customer data, and never another dealer's idea. The WhatsApp
> confirmation carries that link alongside the idea number. This confirms R11 outright: AC-1118
> and AC-1311 lose their PROPOSED tag, and AC-1114 and AC-1303 are rewritten to match (both
> `link` no longer null for WhatsApp, and "no URL" narrowed to "no URL other than `link`"). See
> S5 above and AC-1601 to AC-1604.

> **R14 Department reading confirmed:** owner: "yes" (to the round-2 department reading). The
> "(reading proposed)" tags on that reading are removed throughout - department is free text,
> captured only when volunteered, never asked as its own question, settled.

> **R15 Department dropped from the ask sequence:** owner: "i think don't need to ask department
> ba." This resolves the open question S2's department bullet raised in round 1: `department` is
> removed from S1's `next_field` sequence entirely (was proposed_solution, impact, department;
> now proposed_solution, impact). It is never nominated as a field to actively ask about, in any
> turn - captured only when the dealer says it unprompted, exactly as R14 already settled.

> **R16 Problem first in every recap:** owner, on sample (a)'s review-turn recap: "need to
> collect the problem statement, first one is the problem statement right." Correct, and this
> plan's own point-form ordering (R10) missed it: the one required field is the problem
> statement, and every point-form recap - including the very first understanding turn, right
> after the opening message - lists a "Problem: ..." line as the FIRST field line under the
> title, before Solution, Impact or Department (each still only shown when present). The
> understanding turn that follows the dealer's opening message now always has this shape: title,
> Problem (always present - it is what made the draft exist), then the first optional question.
> Amends R10's field order; all sample conversations are rewritten accordingly.

> **R17 Semantic field capture, not deterministic slot-filling:** owner: "what if the user answer
> something that is like problem statement when we ask for solution, we should be able to cater
> for that, our design for this information should be conversational, semantic and not too
> deterministic." Ruling: the field a message updates is decided by the meaning of the whole
> draft so far (the intake's LLM extraction), never by which field `next_field` happened to ask -
> the asked field is only a hint, not a routing key. A reply that reads as more problem detail
> updates the Problem line (even while `proposed_solution` was the one asked) and the bot asks
> the same optional field again, or moves on once it is later answered or skipped - no
> complaint, no "that wasn't what I asked" branch. See AC-1219 and sample (i).

> **R18 Approval, framework constraint (owner, on the plan page, 24 Sep 2026):** "ok cool,
> proceed, make sure we implement this with no too much customization of our chatbot engine,
> the framework should still the same, to allow scalability."

## Framework constraint (R18)

The plan is approved to build. R18 is a hard constraint on HOW, not a new feature: the shared
chatbot engine - `app/services/chatbot/turn/*` (the parser-only decider `decide.py`, `apply.py`,
`route.py` and the rest of the turn pipeline), and the lanes registry that dispatches to
`app/services/chatbot/lanes/*` - is not changed by this plan, except where a slice already names
an existing seam in it (S3's `access_denied_text` branch is the one such seam, and it is one
`if agent == "ideation"` case added to an existing function, not a new engine concept). Every
other piece of behaviour in this plan lives in the ideate lane handler
(`app/services/chatbot/lanes/ideate.py`) and `app/services/ideation_turn_service.py` on the
sorento side, or in the shared-service intake and its frontend on the other. The point-form
composer (S3), semantic field capture (S2, R17) and the public status page (S5) are all
intake-side or lane-side, never engine-side: nothing here adds a new engine branch, a new
`_LANE_BRANCH` entry, or an ideation-specific routing rule beyond the one general rule #1178
already adds for every lane (an open draft/pending state keeps its own lane on a hesitation or a
bare confirmation) - `ideate` is already a known lane in the engine's routing today
(`app/services/chatbot/turn/route.py::_LANE_BRANCH`), so this plan adds no new lane either.

## Review findings -> where they land

| Finding (PR #1176) | Landed by |
|---|---|
| F1 console never shows the real reply | #1179 (not this plan) |
| F2 clarification question leaves the lane | #1178 (not this plan); S3 answers it once it stays |
| F3 bare "confirm" falls to a greeting | #1178 (not this plan) |
| F4 skip / hesitation ignored | S1 `next_field` + S2 `skip` + S3 reply |
| F5 four mandatory fields | S1 (R1) |
| F6 `confirm` keyword gate | S2 `review_action` (R3) |
| F7 orphan draft on duplicate | S1 (draft stays open, then voted / separate) |
| F8 no way to disagree with duplicate | S1 + S2 (R4) |
| F9 tracking link needs SSO | Resolved by S5 (R13): a public, token-gated status page, no SSO, no CRM login, title/status/idea number only. Superseded the original S1 `link` null + S2 no append (R6) and round 2's proposal (R11). |
| F10 no title | S1 column + S2 extraction (R2) |

## Dependencies

Not owned by this plan; needed only for the AUTOMATIC part of sample (h)'s mid-draft detour
(R12). The draft itself never depends on either - `session_vars.ideation` survives any number of
other-lane turns on its own.

- **#863 (chatbot focus feature, open):** an automatic, seamless return from a mid-draft detour
  (a stock/order/etc. question asked while an ideation draft is open) back into the ideate lane
  on the same field, without the dealer naming the idea again.
- **#1178 (open draft keeps its lane, PR #1185, open):** a short return phrase ("ok back to my
  idea") staying in the ideate lane rather than falling through to a generic reply - the same
  lane-stickiness problem F3 named for a bare "confirm", generalised to any return-to-lane
  utterance.
- Without either: the draft is intact, but the dealer resumes by naming the idea explicitly
  (e.g. "back to my idea about the slow moving stock filter") rather than a bare "ok back to my
  idea" being enough.
- ~~`S-link` (proposed, not yet planned)~~ - **graduated to S5 in this plan (R13, lavish review
  round 3).** No longer a dependency; see the S5 slice above.

## Out of scope

- WhatsApp status updates to the submitter after capture (R6, later slice). Trigger to plan
  it: the first status change after capture that the owner wants the submitter told about.
- Category (R2).
- #1178, #1179, #1181, #863.

## Open items for the S1 ticket (not owner questions)

- Confirm the shared-service field and status names above against the four files, and fix the
  Contract section in the same PR.
- Confirm where the duplicate check runs today (first turn only, or every turn) and keep that
  timing; the review saw it on the first turn.
