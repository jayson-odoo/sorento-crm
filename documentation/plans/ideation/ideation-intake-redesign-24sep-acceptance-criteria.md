# UAC - Ideation intake redesign (issue #1172)

**Status:** grilled 24 Sep 2026, ready for tickets
**Plan:** `PLAN-ideation-intake-redesign-24sep.md` (this file is the contract it fulfils)
**Evidence:** PR #1176, `documentation/plans/ideation/REVIEW-ideation-flow-ux-24sep.md` (findings F1 to F10)
**Repos:** sorento-crm (this repo) and foundryx-shared-service (cited as `shared-service:<path>`)

Tags: `[SS]` shared-service backend, `[BE]` sorento backend, `[T]` covered by pytest in the named
repo, `[C]` covered by a console YAML case (`tests/chatbot/console_cases/`, needs #1179 merged),
`[L]` live console walk at the end of the lane.

## Journey

Actor: a business user (dealer staff or internal staff) on WhatsApp who holds the `ideation`
access agent. They know their idea; they do not know the intake's field names.

1. **They say the idea in their own words**, in any language ("i have an idea, the price tag
   should show promo price in red"). The system already knows who they are (phone, name, tier,
   and, when linked, their company), so it never asks for any of that.
2. **The bot confirms it understood** in the user's language, restates the idea under a short
   title it made itself, and asks ONE optional question (the proposed solution).
3. **Each optional question is asked once.** The user may answer, or say "skip", "don't know",
   "later", "dunno lah"; either way the bot moves on. A question about the question ("what do
   you mean impact?") gets a plain explanation and the same question again, never a menu.
   Department is not asked when their company is known.
4. **If a similar idea already exists**, the bot names it ("Similar idea exists: <title>") and
   asks whether to vote for that one or keep this one separate. Saying anything else keeps it
   separate.
5. **Review.** The bot shows the title and what it captured and asks whether to submit. "yes",
   "ok", "boleh", "submit" all submit. A change request is applied and the review is shown
   again. "cancel" closes the draft.
6. **Done.** The bot replies with the idea number (e.g. IDEA-0123) and says they will be updated
   on WhatsApp. No link.
7. **If they walk away**, after 24 hours idle they get one WhatsApp reminder; if they still do
   not answer, the draft closes quietly.

What they hold at the end: an idea number, and nothing to remember.

## Group A - Shared-service contract (S1)

- **AC-1101 [SS][T]** Given the ideation intake definition, when it is loaded, then `problem` is
  the only required field and `proposed_solution`, `impact`, `department` are optional
  (Journey 1, 3; R1). The form-engine document still lists all four fields.
- **AC-1102 [SS][T]** Given a draft with `problem` filled and no optional field answered or
  skipped, when `create-idea` is called, then `status` is `collecting` and `next_field` names
  the first optional field not yet answered or skipped, in the order proposed_solution, impact,
  department (Journey 3).
- **AC-1103 [SS][T]** Given a call carrying `skip: ["impact"]`, when it is applied, then impact
  is recorded as skipped on the draft and is never returned as `next_field` again (R1).
- **AC-1104 [SS][T]** Given `problem` filled and every optional field answered or skipped, when
  `create-idea` is called, then `status` is `review` and `next_field` is null (Journey 5).
- **AC-1105 [SS][T]** Given a call carrying `title` (1 to 8 words), when applied, then
  `ideas.title` holds it and the response echoes it; a `title` over 8 words is rejected with 422
  (R2).
- **AC-1106 [SS][T]** Given the board, the ideas list and the idea detail, when an idea with a
  title is shown, then the title is the visible label; an idea without one (created before this
  lane) shows its problem text as today (R2).
- **AC-1107 [SS][T]** Given a new draft whose problem is similar to an existing non-test idea of
  the same product, when `create-idea` is called, then no upvote is written, the draft stays
  open, `status` is `duplicate_candidate` and `duplicate_candidate` carries
  `{idea_number, title}` (R4, F7, F8).
- **AC-1108 [SS][T]** Given only test ideas (`is_test = true`, from #1179) are similar, when a
  live draft is checked, then no candidate is returned (R4).
- **AC-1109 [SS][T]** Given a draft in `duplicate_candidate`, when the next call carries
  `duplicate_choice: "vote"`, then the candidate gets one upvote from this submitter, the draft
  is closed (not left as an orphan row), and `status` is `voted` with the candidate's
  `idea_number` (R4, F7).
- **AC-1110 [SS][T]** Given a draft in `duplicate_candidate`, when the next call carries
  `duplicate_choice: "separate"` (with or without `fields`), then the draft continues as a
  normal draft and the same candidate is not offered again for this draft (R4).
- **AC-1111 [SS][T]** Given a draft in `review`, when a call carries `confirm: true`, then the
  idea is captured, gets the next `idea_number` from a new sequence formatted `IDEA-` plus at
  least four digits (IDEA-0001, IDEA-0123, IDEA-12345), and `status` is `complete` (R6).
- **AC-1112 [SS][T]** Given two ideas captured concurrently, when both complete, then their
  idea numbers differ (sequence, not max+1) (R6).
- **AC-1113 [SS][T]** Given any open draft, when a call carries `cancel: true`, then the draft
  is closed, no idea number is minted, and `status` is `cancelled` (R3; also used by the S4
  close).
- **AC-1114 [SS][T]** Given a `complete` for a WhatsApp-source idea, when the response is built,
  then `link` is null and the fallback `reply_text` names the idea number and says the user
  will be updated on WhatsApp (R6, F9).
- **AC-1115 [SS][T]** Given a call carrying `submitter_tier: "dealer"`, when the idea is
  created, then `ideas.submitter_tier` holds `dealer` and triage views show it (R7).
- **AC-1116 [SS][T]** Given every response, then it carries `status`, `draft_id`, `reply_text`,
  `missing`, `next_field`, `title`, `captured`, `duplicate_candidate`, `idea_number`, `link`
  as defined in the plan's Contract section, with null where not applicable (R5: sorento needs
  facts, not prose).
- **AC-1117 [SS][T]** Given an old sorento that sends none of the new fields, when
  `create-idea` is called, then it still works: no title, no tier, no skip, and the duplicate
  path returns `duplicate_candidate` (the old sorento treats an unknown status as non-terminal
  and keeps the pointer). Deploy order is shared-service first.

## Group B - Sorento payload, title, duplicate ask, semantic review (S2)

- **AC-1201 [BE][T]** Given an ideate turn, when the extractor runs, then its output is
  `{fields, remove, skip, title, review_action, change_text, duplicate_choice}` and `confirm` is
  no longer read from the model (R3).
- **AC-1202 [BE][T]** Given a message that states the idea, when extracted, then `title` is a
  short label of at most 8 words; a longer model output is cut to its first 8 words before it
  is sent (R2).
- **AC-1203 [BE][T]** Given the pointer's `next_field` is `impact` and the user says "dunno lah,
  can skip this one?", when extracted, then `skip == ["impact"]` and the payload carries it
  (R1, F4, F5).
- **AC-1204 [BE][T]** Given `next_field` is `impact` and the user asks "what do you mean
  impact?", when extracted, then `skip` is empty and no field is set; the turn stays in the
  ideate lane (F2 is #1178's; this AC pins only the extraction).
- **AC-1205 [BE][T]** Given `skip` names `problem`, when the payload is built, then `problem`
  is dropped from `skip` (only optional fields can be skipped, deterministic guard).
- **AC-1206 [BE][T]** Given the contact has a primary `respond_contact_customers` link, when
  the first turn of a draft is built, then `fields.department` is the linked customer's name
  unless the user supplied one; with no link, department is left to be asked (R1).
- **AC-1207 [BE][T]** Given the contact has access types, when any payload is built, then
  `submitter_tier` is the code of the first `ContactAccessType` in the relationship's order
  (`sort_order`, then `code`); with none, the key is omitted (R7).
- **AC-1208 [BE][T]** Given status `review` and the user says any of "yes", "ok", "boleh",
  "submit", "confirm", "can you just submit it already", when extracted, then
  `review_action == "submit"` and the payload carries `confirm: true` (R3, F6).
- **AC-1209 [BE][T]** Given status `review` and the user says "change the impact to faster
  checkout", when extracted, then `review_action == "change"`, `change_text` holds the change,
  `fields.impact` is set, and the payload carries `confirm: false` (R3).
- **AC-1210 [BE][T]** Given status `review` and the user says "cancel" / "never mind, drop it",
  when extracted, then `review_action == "cancel"`, the payload carries `cancel: true`, and the
  pointer is cleared on the `cancelled` response (R3).
- **AC-1211 [BE][T]** Given status is NOT `review`, when the model emits `review_action:
  "submit"`, then the payload carries `confirm: false` (existing AC-11b guard, kept). A
  `cancel` outside review is honoured (a user may drop a draft at any step).
- **AC-1212 [BE][T]** Given a response with `status: duplicate_candidate`, when the turn
  returns, then the pointer is kept with `status: duplicate_candidate` and the reply names the
  candidate's title and asks vote-with-it or keep-separate (R4).
- **AC-1213 [BE][T]** Given the pointer is `duplicate_candidate` and the user says "vote for
  that one", when extracted, then `duplicate_choice == "vote"` and the payload carries it; on
  `status: voted` the pointer is cleared (R4).
- **AC-1214 [BE][T]** Given the pointer is `duplicate_candidate` and the user says anything
  that is not a vote ("keep mine", or a new detail about the idea), when the payload is built,
  then it carries `duplicate_choice: "separate"` plus any extracted fields (R4 default).
- **AC-1215 [BE][T]** Given the terminal statuses, then `complete`, `voted` and `cancelled`
  clear `session_vars.ideation`, and `duplicate` is no longer produced (R4).
- **AC-1216 [BE][T]** Given a `complete` response, when the lane builds the reply, then no link
  is appended (R6).
- **AC-1217 [C]** Console case: idea, skip solution, answer impact, "boleh" submits; the reply
  carries an `IDEA-` number and no URL.
- **AC-1218 [C]** Console case: the same idea twice; the second names the first by title and
  "keep separate" continues the draft.

## Group C - LLM replies with template fallback (S3)

- **AC-1301 [BE][T]** Given a `create-idea` response, when the reply is composed, then the LLM
  receives only the facts listed in the plan (status, title, captured, next_field,
  duplicate_candidate, idea_number) plus the user's message for language, and the output is
  the reply (R5).
- **AC-1302 [BE][T]** Given a non-terminal status, when the LLM reply is accepted, then it ends
  with exactly one question mark (`?` or the full-width `？`) as its last non-space character
  and contains no other (R5).
- **AC-1303 [BE][T]** Given `complete`, when the LLM reply is accepted, then it contains the
  `idea_number` verbatim and no URL (R5, R6).
- **AC-1304 [BE][T]** Given `duplicate_candidate`, when the LLM reply is accepted, then it
  contains the candidate title verbatim (R4, R5).
- **AC-1305 [BE][T]** Given the LLM call fails, times out, returns empty, or fails any check in
  AC-1302 to AC-1304, when the reply is composed, then the shared-service `reply_text` is used
  unchanged (R5).
- **AC-1306 [BE][T]** Given a Malay message ("saya ada idea, tanda harga patut tunjuk harga
  promo warna merah"), when the reply is composed with a stubbed provider, then the language
  hint sent to the model is taken from the user's message (R5).
- **AC-1307 [BE][T]** Given the parser denies the `ideation` agent (`suggested_agent ==
  "ideation"`, access check fails), when the access-denied reply is composed, then it goes
  through the same LLM composer with facts `{denied: "ideation"}`, and falls back to the
  existing `access_denied` template text on any failure (R5, R7). Other agents' denials are
  unchanged.
- **AC-1308 [C]** Console case: "what do you mean impact?" gets an explanation of impact that
  ends in the impact question.
- **AC-1309 [C]** Console case: a Malay idea gets a Malay reply.

## Group D - 24h reminder and close (S4)

- **AC-1401 [BE][T]** Given a contact whose `session_vars.ideation.updated_at` is more than 24
  hours old and has no `reminded_at`, when the sweep runs, then one message is sent through
  `send_text_or_template` with use case `ideation_draft_reminder` and `reminded_at` is written
  into the pointer (R3).
- **AC-1402 [BE][T]** Given a pointer with `reminded_at` more than 24 hours old and no newer
  `updated_at`, when the sweep runs, then shared-service is called with `cancel: true` for that
  draft, the pointer is cleared, and no message is sent (R3: reminder, then close).
- **AC-1403 [BE][T]** Given the user replies after the reminder, when the ideate turn runs,
  then `updated_at` moves and `reminded_at` is dropped, so the 24h clock restarts.
- **AC-1404 [BE][T]** Given the sweep runs twice in the same minute, then at most one reminder
  is sent per draft (the `reminded_at` write is the idempotency key).
- **AC-1405 [BE][T]** Given the reminder send raises (window closed and no template mapped:
  `TemplateSendSkipped`), when the sweep runs, then `reminded_at` is still written, the failure
  is logged to `integration_logs`, and the draft closes on the next 24h tick as normal.
- **AC-1406 [BE][T]** Given `outbound_enabled = false` on the contact, when the sweep runs,
  then the existing client-boundary switch (`assert_outbound_enabled`) refuses the send, it is
  handled exactly as AC-1405, and the draft closes on the same schedule as any other (no
  special case in the sweep).
- **AC-1407 [BE][T]** Given a shared-service outage during a close, then the pointer is kept
  and the next tick retries.
- **AC-1408 [BE][T]** Given the scheduler starts, then the sweep job is registered at a
  15-minute interval.

## Group E - Lane close

- **AC-1501 [L]** Live console walk of the Journey on the lane stack against a local
  shared-service, transcript saved under `documentation/plans/ideation/evidence/intake-redesign/`.

## Out of scope

- Status updates to the submitter over WhatsApp (R6: a later slice).
- #1178 (open draft keeps the ideate lane on a question or bare confirm) and #1179 (test turns
  reach the real intake with `is_test`): in flight separately.
- Plan Status housekeeping: PR #1181 (R8).
- Category (R2: no category).
