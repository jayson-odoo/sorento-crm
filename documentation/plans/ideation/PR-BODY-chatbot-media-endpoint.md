feat: chatbot media endpoint - voice transcription and image recognition for contacts

## What this is

One CRM endpoint that gates, meters and performs voice transcription and image recognition for
chatbot contacts. n8n makes one call and waits on it. CRM half only; the n8n half is a separate
follow-up and nothing in that repo was touched.

The wire is synchronous, the execution is not. The handler commits the usage ledger inline,
enqueues to RQ, and awaits the result through `asyncio.to_thread` so the event loop keeps serving.
Past `media_sync_wait_seconds` it stops waiting and returns `status: pending` with the `job_id`.

Design contract: `documentation/plans/ideation/PLAN-chatbot-media-endpoint.md`.
Handoff / state: `documentation/plans/ideation/HANDOFF-chatbot-media-endpoint.md`.

**Do not merge this.** Review only.

## The four things the definition of done requires this PR to state

### 1. `lock:{contact}` - decision and evidence

**HOLD, and this reverses the recommendation made against the earlier async design.** The reversal
is stated rather than quietly amended because the reasoning is the part that matters.

Under the synchronous wire, hold-versus-release stopped being a choice. `call-spine` is
`waitForSubWorkflow: true` (`sorento-dispatcher/workflow.json:379`), so the dispatcher is blocked on
the spine and the spine is blocked on the CRM. There is no pause to release across. The earlier
release recommendation was answering a different question, whether to hold across an open-ended
suspension, and that question no longer exists.

So the question became whether holding is safe. It is a budget argument, and the budget closes:

| term | value | source |
|---|---|---|
| lock TTL | 120 s | `sorento-dispatcher/workflow.json:330` |
| existing spine turn | 5.0 - 18.4 s | `concurrency-plan.md:82,84,143`, `dym-probe-before-offer-plan.md:463` |
| fast path added here (p99, accepted) | ~0.011 s | measured, PLAN 15.1, N=300 x2 |
| extraction, `gpt-4o` | 6.51 s mean, 5.70 - 8.52 s | measured, N=5, temperature 0 |
| enforced ceiling | `media_sync_wait_seconds`, default 30 s | `app/api/v1/external/media.py:227` |
| **worst-case turn** | **~48.4 s against a 120 s TTL** | 18.4 + 0.011 + 30 |

Roughly 60 percent margin at the worst case. The ceiling is enforced by
`asyncio.wait_for(..., timeout=sync_wait_seconds)` rather than hoped for, so the wait cannot run
long however badly a provider behaves. That is a strict improvement on the status quo, where
nothing bounded a turn at all. Holding is also what the repo already does for this class of work:
voice runs `fetch-audio` then `whisper-transcribe` inline inside the spine
(`live-spine-sorento-consume-main/workflow.json:5057`, `:5083`) under the same lock.

**What has not changed and must be said out loud: spine p99 remains unmeasured**
(`concurrency-plan.md:148`). It is already risk #1 in that plan and this feature makes measuring it
more urgent, not less. The shipped mitigation is that `media_sync_wait_seconds` is an operator
setting, so if the lock proves tight the wait shortens without a deploy and the flow degrades to the
callback rather than breaking.

Supporting measurement (PLAN 15.3, UAC S3-01b, run as committed): an unrelated request answered in
15 - 18 ms while a 3.0 s extraction was in flight on the same process.

### 2. Spine resume - confirmed?

**No. Checked, not assumed: the spine cannot resume mid-flow today, and could not without new
construction.**

- Exactly one `n8n-nodes-base.wait` node exists in the whole n8n repo, in `sub-sendmsg`
  (`export/sub-sendmsg/workflow.json:357-367`). It has no `resume` property, so it is in default
  `timeInterval` mode, not `resume: webhook`. Its `webhookId` is auto-minted for every Wait node and
  is not evidence of webhook mode.
- That node is orphaned, zero inbound edges (`export/sub-sendmsg/TOPOLOGY.md:39-40`).
- `resumeUrl`, `$execution.resumeUrl` and `webhookSuffix` have zero occurrences repo-wide.
- The spine contains no Wait node at all.

**Consequence, and why this is not a blocker:** under the synchronous wire the CRM does not depend
on resume existing, because the primary path returns the result on the same call. The callback stays
transport-agnostic so the fallback works whatever n8n builds later: n8n supplies an opaque
`callback_url` plus optional `callback_headers` and the CRM POSTs there and cares about nothing
else. A `GET` polling endpoint covers the case where neither is wanted, and is what n8n should call
after a `status: pending`.

One structural fact recorded so it is not rediscovered: extracted text must land in the queue item
upstream of `tf-message` (`live-spine-sorento-consume-main/workflow.json:2706`), because roughly
fifteen downstream nodes read `$('tf-message')` by name. That is the trick `patch-transcript`
already uses for voice.

### 3. Corpus results

Full results: `documentation/plans/ideation/chatbot-media-endpoint-corpus-results.md`.

**What held.** Trap A (five codes on one line, one subject) and Trap B (`#N/A` is not a line item)
both passed on the real document. Trap E passed cleanly, product size and box dimension captured
under distinct kinds on an angled warehouse photo, confirming that the carton failure was schema
coverage rather than vision. Trap C's core mechanism held: printed-versus-handwritten disagreement
detected, both sources named, entity marked `confident: false` rather than silently picking one.

**Five defects exposed, all mine rather than the model's, all fixed.**

1. Conflict confidence leaked across lines: `_apply_conflicts` matched by `kind` alone, so one
   genuine quantity conflict marked four unrelated correct quantities `confident: false`.
   `MediaAttribute` now carries `entity_raw`. This matters more than its size suggests, since
   S4-03's entire value is that `confident: false` means something.
2. Dates had nowhere to go, so a legible `13/08/2026` was dropped and the ambiguous-date rule was
   unreachable. `document_date` attribute kind added.
3. Form reference numbers likewise: a return-authorisation number fitted no hint and was dropped on
   one image, stretched into hint `attachment` on another. `document_number` kind added.
4. An entity could reappear as a spurious attribute (a product code inside a description came back
   as `batch_number`). Prompt forbids it, schema drops it.
5. `wording._conflict_sentence` discarded `conflict.note`, which is fatal for an ambiguous date:
   the customer would read "I can see 11/08/2026, which one should I use?", a question naming one
   value and offering no alternatives. Now rendered.

**One prompt gap.** On the skewed, stamped, written-on photo the model returned the whole line-item
table and nothing from the header block. Not degraded, absent. Rule 11 makes the header an explicit
named target.

**The Trap C regression, and the honest outcome of the decision rule.** Rule 18 did nothing (arm C,
0/5), so the pre-registered clause fired and its action was to delete rules 11 and 14. Two more arms
were run before executing it:

| arm | prompt | model | conflict fired | header |
|---|---|---|---|---|
| A | current | gpt-4o-mini | 0/5 | 5/5 |
| B | run-1 | gpt-4o-mini | 5/5 | 0/5 |
| C | current + rule 18 | gpt-4o-mini | 0/5 | 5/5 |
| D | current minus rules 11 and 14 | gpt-4o-mini | 0/5 | customer lost 0/5 |
| E | current, unchanged | **gpt-4o** | **5/5** | retained |

**Arm D falsified the premise the prescribed action rested on**: deleting the two rules does not
restore conflict detection, and it costs the customer field. Executing it anyway would have followed
the letter of a rule whose reasoning the evidence had already destroyed. **Arm E found the actual
cause**: on `gpt-4o` the unchanged prompt fires the conflict 5/5, keeps the header, and the
`16`-for-`6` misread does not reproduce once after being identical in all 20 preceding
`gpt-4o-mini` calls. It is also faster (6.5 s vs 9.7 s mean) and uses roughly 13x fewer prompt
tokens on the same image.

So the rules stayed and the tier changed. Standard `gpt-4o`, degraded `gpt-4o-mini`, both seeded by
migration 358. This is the strongest available justification for telling a contact accuracy has
dropped: at the degraded tier the failure is measured, not hypothetical, and it is the bad kind -
the model hands back a confident wrong number rather than failing visibly.

**Honest note on the measurement itself:** the tester's first arm E attempt applied the model
override only inside a probe, so the five real calls silently ran on `gpt-4o-mini`. It caught this
by asserting the model on each returned row, discarded the run, fixed it and re-ran. The numbers
above are the corrected run.

**Still unverified:** because image 02's header was never attempted, the two baseline defects named
for that image (`J&Y` read as `JAY`, `11/08/2026` read as November) are unverified rather than
fixed. Rules 1 and 3 could not be scored on a field the model did not attempt.

### 4. The entity-hint question

**Answered, not outstanding. Captain, 2026-08-14: Option A.** Batch number, barcode, box dimension
and product size are emitted as unhinted `attributes[]`; the 14-value enum is not extended.

The enum is fixed by `docs/flows/sub-query-reformulator.md:33-44` and read by `resolve-entity` as
`allowed_entity_types[]`. Extending it changes a contract the n8n side owns, and a CRM emitting
`hint: "batch"` today would emit a value `resolve-entity` rejects, failing or silently dropping
rather than degrading. Unhinted attributes are useful immediately with zero downstream change: they
render in the confirmation message, so a dealer photographing a carton is told the batch and barcode
were read. It is reversible: making a carton photo answerable on batch is a resolver capability
first and an enum value second.

This was escalated rather than chosen silently.

## Review findings, and what was done about them

PLAN section 16 records each in full. Three blockers, all fixed:

- **The voice quota was not enforced at all.** `media_access_service.py` checked
  `settings.image_degraded_model` for both modalities, so a voice contact over quota fell into a
  degrade branch with no voice model to degrade to. Fixed by giving voice its own
  `media_voice_degraded_model` (NULL default, migration 359) and wiring `job.tier` into
  `_extract_voice`. Image ships seeded because its tiers were measured; voice ships unseeded because
  they were not. NULL means hard refusal, not silent degradation. The captain's degrade-not-refuse
  decision is honoured by the mechanism existing and being one setting away, not by pretending a
  degradation happened.
- **The settings page could never show its error state.** `isLoading || !draft` was evaluated before
  `isError`. Fixed, and guarded as `isError && !draft` so a failed background refetch does not
  discard operator edits.
- **No frontend tests on a slice with four [FE] acceptance criteria.** 25 vitest tests added. The
  error-state regression was mutation-tested: revert to the buggy ordering, watch the test fail with
  the exact symptom, restore, confirm zero diff.

Section 16.7 records a self-correction: 16.1 justified the NULL default as "one setting away", but
no UI control existed at the time, so the claim was false when written. A control was added to make
it true. The shared `ModelField` defaults its empty label to "Inherit", which would have asserted in
the UI the exact falsehood the fix exists to remove, so it takes an `emptyLabel` and passes
"Not set".

## Migrations

Four migrations, verified rather than assumed: schema built at merge base, stamped `885010d94677`,
all four run forward, DDL and seeds and grants checked by direct query, all four downgraded, then
re-upgraded and re-verified. 193 media tests then passed against migration-produced DDL rather than
`create_all` DDL.

Found while doing that, and **pre-existing, not from this branch**: `alembic upgrade head` is broken
repo-wide from a true base. No migration creates `conversation_sla_tracking`, yet three reference it
(008, `241_sla_takeover_requests`, `portal_rev_0001`). Migration 008 dates to 2026-01-27 and the
merge base is the tip of main. It is hidden because `tests/_pg_fixture.py` builds schema with
`Base.metadata.create_all()`. Out of scope here (300+ migrations) and left alone.

## Tests

**New coverage.** pytest for S1 through S6 across `test_media_access_service.py`,
`test_media_process_endpoint.py`, `test_media_job_lifecycle.py`, `test_media_extract_*`,
`test_media_settings_columns.py`; 25 vitest tests across `page.test.tsx` and
`ContactMediaAccessSection.test.tsx`. 193 media tests pass against migration-produced DDL.

**Regression attribution: this branch caused zero regressions.**

The full serial suite on this branch is `123 failed, 6038 passed, 9 skipped, 13 xfailed`,
reproduced twice independently. That number is not reportable on its own, so it was attributed
against the merge base:

| set | count |
|---|---|
| failing on **both** branch and `db607931` (pre-existing) | 119 |
| **branch-only** (candidate regressions) | 4 |
| **baseline-only** (fixed or flaky) | 0 |

Method: the 123 failures live in 35 files. Those 35 files were run on branch
(`123 failed, 355 passed`, collected 478) and again on `db607931` (`119 failed, 359 passed`,
collected 478, same database, same `pytest -q -p no:randomly`). Collected counts match exactly, so
there is no selection skew to explain away. Running the 35 files alone reproduced all 123 branch
failures exactly, which is what makes the targeted comparison trustworthy: it is not masking
ordering effects, because the narrow run and the full run agree.

**The 4 branch-only failures were run down to cause, not reported as ids.** None of them can be
caused by this diff, because the code each one exercises is byte-identical between the two commits
(verified with `git diff db607931..HEAD` per path, all empty), as are the four test files:

- `test_m2_demand.py::test_demand_stat_matches_golden[B2155-NL-BLUE@BRW-IB]` and `[SRTPTFE1207@BRW]`
  fail with `demand_stat not written`. All 6 golden SKUs fail on branch; 4 of the same 6 already
  fail on baseline. `app/services/scm/` has zero diff. This is a golden-set suite asserting against
  the shared production-copy database, already majority-broken at the merge base, drifting across
  the roughly 90 minutes between the two runs while other lanes wrote to the same database.
- `test_audit_contact_attribution.py::test_endpoint_display_resolution` fails reading its own
  just-created row back from `GET /api/v1/audit/logs/`, which defaults to `limit=50`. Zero diff in
  `audit_service.py` and the audit route. The shared `audit_logs` table takes continuous writes from
  every other agent on this machine, so the fresh row can fall off page 1 before the GET lands.
- `test_ticket_intake.py::test_invalid_preview_priority_rejected` expects a raise that did not
  happen. Zero diff in `ticket_intake_service.py`. Three sibling tests in the same file already fail
  identically on **both** sides, so this file is stale against current service behaviour
  independently of this branch.

**Read this honestly:** those 4 are not clean passes, they are flaky tests inside suites that are
already failing at the merge base. The claim being made is the narrow one the evidence supports -
this branch did not cause them - not that the suite is healthy.

**A methodological asymmetry, disclosed rather than buried.** The baseline had to be chunked into 6
runs to survive machine memory pressure, while the branch ran as one invocation. That asymmetry is
safe in the only direction that matters: more isolation makes baseline tests *more* likely to pass,
which can invent branch-only failures but cannot hide real ones. So it can only inflate the 4, never
shrink it below the truth.

**Zero of the 123 failures are media tests**, on either side.

**Pre-existing, and left alone:** the 119 are dominated by the `tests/scm/` golden-set suite and by
the documented "CI database has no data" class in CLAUDE.md, where tests borrow a row with
`LIMIT 1` from the shared production-copy database. Fixing that is not this branch's job.

## Browser sign-off of the two operator surfaces

Done against a production build (`next build` + `next start`), not a dev server, with a real login
and a live backend. Both surfaces were reached by clicking, not by typing a deep URL.

**Settings -> Chatbot Media.** The tab renders in the settings tab bar and routes to
`/user-management/settings/chatbot-media`. Every field loads from the singleton row with the
shipped defaults (50 photos, 100 voice notes, 120s clip ceiling, warn at 80 percent, burst 5 per
60s, 10 entities, 30s synchronous wait, 45s extraction ceiling, Whisper v1). Voice degraded model
reads "Not set", which is the shipped state, and carries no warning; image degraded model is blank
here and does carry its warning, and that warning clears the moment a model is named. Validation was
exercised live: an extraction ceiling of 20 against a 30s wait produces the cross-field sentence and
disables Save, a 999s wait produces the range sentence, and Reset restores both and re-enables Save.
Saving unchanged values round-trips as `POST /api/v1/user-management/settings/general` 200 followed
by a refetch.

**The failed-load state was verified for real**, since that was the point of review finding 16.3. With
the backend stopped, the page renders "Chatbot media settings could not be loaded. Reload the page
to try again." rather than skeletons that never resolve. A backend that hangs instead of refusing
still renders skeletons, which is correct: a hang is loading, not an error.

**Contact detail -> Media Access.** Both panels render for a contact that has never been configured,
showing "Not enabled", used 0 of the inherited limit, the reset date, "Default (50)" / "Default
(100)" / "Default (120s)", and the "Never configured" line. Turning photos on is one click and
round-trips as `PUT .../media-access/image` 200 plus a refetch, after which the panel reads
"Enabled" and stamps who changed it. Turning it off goes through the confirmation dialog ("Turn off
photos? The bot will stop reading photos from this contact and will tell them to type instead") and
only then issues the PUT. The limits dialog refuses 5000 clip seconds inline and disables Save;
saving 25 and 90 persists and the panel switches to "Override (25)" and "Override (90s)", with the
allowance line following the override.

One defect came out of this and is fixed in the branch: the limits dialog rendered without an
accessible description, which React reports as a missing `Description` for `DialogContent`.

Two observations that are **not** this branch's doing, recorded because the sign-off found them:

- Row click on the contacts list does not navigate to the contact in a production build. The row
  carries the handler and the element is hit-testable, but no navigation and no request follows.
  `ContactsList.tsx` and `data-grid-table.tsx` are byte-identical to the merge base.
- The dev database has this branch's media columns and all three media tables already present while
  `alembic_version` still reads `353_project_order_inquiry_rename`, so its schema was advanced
  without being stamped. Nothing was changed there to find this out.

## Added on captain review (2026-08-15)

Two requests came out of the captain's first look at the PR, both bundled here at their ask so the
PR is reviewed once.

### Google Gemini as a third provider (`5fef3c0e`)

The captain will most likely run image processing on Gemini, and the provider list offered only
OpenAI and Anthropic. Adding a menu entry alone would have let an operator pick Gemini and then
fail every extraction, since `get_provider` raised for anything else. So this wires it at every
layer the Anthropic key already touches: a `GeminiProvider` speaking the REST API over `httpx`
(chat with images, tools, JSON mode; embed; connection test), migration `361_ai_config_gemini_key`
adding the key column (additive, idempotent, real downgrade), the key on the schemas and settings
service, a Gemini key field beside the Anthropic one under System Management -> AI Assistant, the
model lists, and the media lane's key and default-model resolution.

Two things worth reading in the commit message before changing them: Gemini 2.5 thinks by default
and thinking tokens come out of the same output budget, so the provider sets an explicit thinking
budget on top of the caller's `max_tokens` (a dense receipt would otherwise exhaust the budget before
one answer token and every image job would fail); and the media lane resolves its Gemini key from its
own column, then the generic assistant key only when the assistant is itself on Gemini, then the env,
so an OpenAI key is never posted to Google.

Review of the slice found the thinking-budget trap, two other callers that else-assumed the other
provider when picking a default model (unified onto one table), and a handful of smaller items
(reasoning tokens in the usage row, image placement relative to tool-result turns, tools plus JSON
mode refused before the network call, the missing-key error naming its provider); all fixed. The
embedding path stays on OpenAI by design and keeps choosing an OpenAI key, now pinned by a test.

**Not verified against a live Gemini key.** None was available here; the request and response
shapes are pinned by tests against the documented API. The first real extraction happens when a key
is pasted into the settings form.

### Contact detail page as route tabs (`8587e5ed`)

The captain asked that the contact page follow the users form: tabs, related information grouped
per tab, per the binding rule that read and edit views present the same layout. It is now a layout
with four route tabs (Profile, Access, Routing, Chat) modelled on `users/[id]/layout.tsx`, owning
the single contact fetch through a context so tabs never refetch, with prev/next keeping the open
tab. Media Access moved to the Access tab beside Access Agents. The header strip carries only
metadata with no edit counterpart (Respond.io ID, Created At, Updated At); Phone Number and
Respond.io Workspace stayed in the Profile card because the edit dialog edits both.

Review caught that first draft putting those two fields in the header only (fixed), the layout
calling the network directly (moved into hooks over a service), a UUID that could reach the delete
dialog, timestamp formatting, and an optional select that could not be cleared. 40 vitest cases
cover the tab shell and the existing sections.

**Browser walk of the four tab routes: partially done, honestly.** On a dev server the Profile tab
was confirmed rendering with the four tabs, the header strip, phone first and workspace last in the
card, and Media Access absent from Profile. Clicking into Access, Routing and Chat did not complete
before this write-up because the machine was at load 120+ with thirteen concurrent dev servers and
the browser tooling stalled; the URL never changed because the dev route compile never returned,
not because of a handler defect (the handler is byte-for-byte the users layout's). To be finished
when the machine is quiet, and stated here rather than implied.

## Known unmet, stated rather than papered over

- **A persisted Playwright spec for the operator surfaces**, now including the four contact tab
  routes. The interactive sign-off covers the settings and media panels; a committed regression spec
  does not exist yet.
- **Browser walk of the Access / Routing / Chat tabs**, per the section above.
- **A live Gemini call**, per the section above.
- **RQ worker end-to-end against the `queue_service` socket-timeout change** is unverified.
- **No corpus re-run through the changed voice path** after the voice-quota fix.
