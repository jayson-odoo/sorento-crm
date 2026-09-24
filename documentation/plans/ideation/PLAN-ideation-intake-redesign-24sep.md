# PLAN - Ideation intake redesign (issue #1172)

**Status:** grilled 24 Sep 2026, ready for tickets, lavish review round 1 folded 24 Sep 2026.
Track: full (shared-service migration for `ideas.title`, `ideas.submitter_tier`, the idea-number
sequence; two repos).
**UAC:** `ideation-intake-redesign-24sep-acceptance-criteria.md` (this plan fulfils it; the
Journey is there).
**Evidence:** PR #1176, `documentation/plans/ideation/REVIEW-ideation-flow-ux-24sep.md`
(findings F1 to F10), and the code map comment on #1172.
**Not in this plan (in flight):** #1178 (an open draft keeps the ideate lane on a question or
bare confirm), #1179 (test turns reach the real intake with `is_test`; sorento PR #1182,
shared-service PR #84). R8 housekeeping is PR #1181.
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
| `link` | str? | yes | S1 | null for WhatsApp-source ideas (R6) |

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

**Shared-service part** (branch in foundryx-shared-service):

- `shared-service:service_backend/modules/ideation/services/intake_definitions.py`: `problem`
  required, the other three optional (R1). The form-engine document keeps all four.
- `shared-service:service_backend/modules/ideation/models.py` + migration: `title`,
  `submitter_tier`, `idea_number` + sequence + backfill, skip storage (above).
- `shared-service:service_backend/modules/ideation/routers/intake.py`: the new request and
  response fields (Contract section); 422 for a title over 8 words.
- `shared-service:service_backend/modules/ideation/services/intake.py`:
  - `next_field`: first optional key not answered and not skipped, fixed order
    proposed_solution, impact, department; `review` when `problem` is set and `next_field`
    is null.
  - Duplicate: same check as today (pg_trgm similarity), limited to `is_test = false`; returns
    `duplicate_candidate` and writes nothing else. `duplicate_choice: "vote"` upvotes the
    candidate and closes the draft (`voted`); `"separate"` records that this draft declined
    that candidate (so it is not offered again) and carries on.
  - `cancel: true` closes the draft (`cancelled`).
  - `confirm: true` in `review` captures and assigns `idea_number`.
  - `link` null when the idea's source is `whatsapp`; the `complete` template becomes "Your
    idea <idea_number> has been captured. We will update you on WhatsApp." (R6).
  - Templates for `duplicate_candidate` ("Similar idea exists: <title>. Vote for that one, or
    keep yours separate?") and for each `next_field`, each ending in one question: they are
    the R5 fallback, so they must meet the same rules as the LLM reply.
- Board, ideas list and detail show `title`, falling back to `problem` when null (R2); triage
  views show `submitter_tier` (R7).
- **Tests (pytest, shared-service):** AC-1101 to AC-1117, including a concurrency test for the
  sequence (AC-1112) and the old-sorento request shape (AC-1117).

**Sorento part:** none in code. The S1 ticket updates this plan's Contract section with the
real shared-service field names if they differ.

### S2 - Sorento payload, title extraction, duplicate ask, semantic review

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
    not ask (reading proposed) (AC-1206). Open question this reading raises, not resolved here:
    S1's `next_field` sequence today still nominates `department` as something to actively ask
    about; if the bot is never to ask it, that sequence may need to drop it - flagged for the
    owner alongside the reading above;
  - `_TERMINAL_STATUSES` becomes `{"complete", "voted", "cancelled"}` (AC-1215);
  - the pointer keeps `next_field` (the extractor's context next turn) alongside `missing`,
    and the candidate title while `duplicate_candidate`.
- `app/services/chatbot/lanes/ideate.py::build_reply`: drop the link append (AC-1216).
- `app/schemas/external/ideation.py` / MCP `crm_ideation_turn`: no change (the new fields are
  between sorento and shared-service only; `IdeationTurnResponse.link` stays for shape but is
  null).
- **Tests (pytest, sorento):** `tests/test_ideation_turn.py` (payload fields, terminal
  statuses, duplicate default, tier, department) and `tests/test_ideation_parser.py` or a new
  `tests/test_ideation_extractor.py` (guards, with a stubbed provider). AC-1201 to AC-1216.
  Console cases AC-1217, AC-1218.

### S3 - LLM replies with template fallback

**Shared-service part:** none beyond S1 (the facts are in the S1 response; the templates are
the fallback).

**Sorento part:**

- One function, `compose_ideate_reply(db, *, result, user_message) -> str`, in
  `app/services/ideation_turn_service.py` (no new module: one caller today). Builds a facts
  block from `status`, `title`, `captured`, `next_field`, `duplicate_candidate`,
  `idea_number`, sends it with the user's message to the same provider plumbing the extractor
  uses (`get_provider`, `AIAssistantConfigService`), prompt key `ideate_reply` in
  `ai_prompt_registry` (fallback text in code, like `ideate_extractor`).
- Checks, then fallback to `result["reply_text"]` on any failure (AC-1302 to AC-1305):
  non-terminal ends in exactly one `?`/`？`; `complete` contains `idea_number` and no
  `http`; `duplicate_candidate` contains the candidate title. Facts never come from the model:
  if the number or title is missing or altered, the template wins.
- The media menu (`menu_text`) is still appended after the composed reply, as today.
- Not-allowed: in `app/services/chatbot/lanes/canned.py::access_denied_text`, when the agent
  is `ideation`, compose through the same function with facts `{denied: "ideation"}`, falling
  back to today's `copy.render("access_denied", ...)` (AC-1307). Other agents unchanged: one
  case, one branch.
- **Tests (pytest, sorento):** a new `tests/test_ideation_reply.py` with a stubbed provider:
  each status, each fallback trigger, the Malay case, the denial branch. Console cases AC-1308,
  AC-1309.

### S4 - 24h reminder and close

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
> not ask (reading proposed, S2's department bullet and AC-1206 above). This supersedes the
> "inferred from the contact's company when known" clause in R1; R1 itself is left as originally
> quoted above for the record.

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
| F9 tracking link needs SSO | S1 `link` null + S2 no append (R6) |
| F10 no title | S1 column + S2 extraction (R2) |

## Out of scope

- WhatsApp status updates to the submitter after capture (R6, later slice). Trigger to plan
  it: the first status change after capture that the owner wants the submitter told about.
- Category (R2).
- #1178, #1179, #1181.

## Open items for the S1 ticket (not owner questions)

- Confirm the shared-service field and status names above against the four files, and fix the
  Contract section in the same PR.
- Confirm where the duplicate check runs today (first turn only, or every turn) and keep that
  timing; the review saw it on the first turn.
