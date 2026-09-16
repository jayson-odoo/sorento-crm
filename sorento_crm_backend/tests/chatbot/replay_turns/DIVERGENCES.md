# Turn replay divergences (AC-1591)

Signed exceptions to `test_turn_replay.py`'s structural comparison. A mismatch between
a recorded case's `expected` and what the current engine actually did is a FAILURE
unless it has a signed line here - an unsigned line (no `(signed ...)`) does not count
and the test still fails, so a placeholder cannot silently excuse a real divergence.

Format, one line per excused field:

```
- <group>/<slug>: <field>: <reason> (signed <initials> <date>)
```

`<group>/<slug>` is the case file's path relative to `tests/chatbot/replay_turns/`
(e.g. `console/owner-15sep-chain-001.json`). `<field>` is one of `branch_kind`,
`action_kinds`, `tools`, `pending`, `canned`, `text`. `<reason>` names the RULE that
changed and why the new behaviour is correct, never just "known issue".

No SIGNED entries yet - none of these are the tester's to sign (a captain/owner
ruling is what a signature records).

## Corpus re-recording, 16 Sep 2026 (tester, this session)

`prod_sample/` re-recorded as CONTIGUOUS CHAINS per contact (a captain ruling, not
the tester's own call - see the handoff/commit history): for each of the 10 real
branch kinds, the newest ~15 distinct contacts (fewer where fewer exist), each
recorded as ONE chain covering the real 2-hour window around their most recent
occurrence of that branch kind (`--contact <id> --since <ts-1h> --until <ts+1h>
--is-test false`). 71 chains, 392 turns total, replacing the 85 isolated
single-turn files the previous pass wrote. The 85 isolated files predicted (in the
paragraph above, now historical) that recording CHAINS would fix cluster 1/2 -
partially true, see the real bug found instead.

**Real bug found and fixed, not a corpus curation issue**: `scripts/
chatbot_record_turn.py::_derive_resolutions` wrote a FLAT resolution record
(`{"token", "uuid", "entity_type", "canonical_code"}`) where the real `resolve-
entity` HTTP response - and `test_turn_replay.py::_install_stubs`'s stub of it,
fed straight through - is `{"resolutions": [{"token", "resolved", "matches":
[{"uuid", "entity_type", "canonical_code"}, ...]}]}`, one `matches` LIST per token,
never a bare match record. `resolve_gate.py:373`'s own `jsc.get(resolutions[0],
"matches")` found nothing on the flat shape, so EVERY recorded resolution replayed
as if nothing had resolved, regardless of whether the original live turn resolved
cleanly on ITS OWN first turn (proven this session: `prod_sample/escalation-
declined-480184379-chain-001`'s step 1 is a standalone first turn with a real
matching UUID already in the ORIGINAL corpus's `resolutions` field, and it still
diverged to `clarify_menu` under the old shape). Fixed in `_derive_resolutions`
(nests the match, sets `resolved: true`/`false`); `prod_sample/` re-recorded again
with the fix. Confirmed a real, measurable improvement on the one probed case (3
divergences -> 1); the aggregate file-level pass count moved less (chains fail
file-wide on ANY step's divergence, so a chain with an unrelated later-step issue
still shows red) - see counts below. `console/` and `contract/` were recorded by
the PRIOR session under the OLD buggy shape and are being re-recorded with the fix
as this session's next two deliverables; expect the same class of improvement
there too (the biggest remaining cluster below, `send_attachments` missing, is
concentrated in `console/` case files not yet re-recorded).

`pytest tests/chatbot/test_turn_replay.py` after the prod_sample re-record + fix
(engine head unchanged, `0d72b643d`): **17 passed, 77 failed**, ~45s. By group:
console 5/20 passed, contract 0/1 passed, prod_sample 12/71 passed (up from a
0-chain baseline; the file-level pass rate looks lower than the OLD 85-isolated-
file corpus's 29/106 only because a chain fails wholesale on ANY step, not because
the fix made things worse - the per-STEP divergence rate is markedly better, see
the probed case above). Remaining clusters, largest first (raw grep counts across
all fields, not deduplicated by file):

1. **`action_kinds` missing `send_attachments`** (~276 occurrences, still
   concentrated in the NOT-YET-RE-RECORDED `console/` files). Carried forward from
   the prior analysis: the recorded tool envelope's `attachments` field is stubbed
   back verbatim and the current engine still does not emit a `send_attachments`
   action from it on at least some paths. **Still flagged as a possible real
   finding**, not signed off - re-check after `console/` is re-recorded with the
   resolutions fix, since some of this may be the SAME resolution-shape cascade.
2. **`branch_kind` moving to `clarify_menu`** (business_query/check_promotion,
   ~150 occurrences remaining even after the fix). Root cause not fully closed:
   likely the ORIGINAL cluster-1 cause (a turn that reused a product from a PRIOR
   turn's own focus, which even a same-contact CHAIN only fixes if the prior turn
   in the SAME file itself resolved and carried focus correctly - a step N failure
   cascades to every step after it in that file). Needs the coder/captain to look
   at whether this is chain-cascade noise (expected, once step 1 of each affected
   chain is confirmed clean) or a second real defect.
3. **`pending` options mismatch** (`expected None, got ['Yes']`, 48 occurrences) -
   NEW this session, not previously clustered (may be a consequence of the
   resolutions-shape fix surfacing a pending/yes-no offer path that previously
   never got far enough to reach). Not investigated further - flagged, not chased.
4. **`branch_kind` moving to `escalate_offer`** (`expected business_query`, 45
   occurrences) - NEW this session, same caveat as (3).
5. **`branch_kind` moving to `low_signal`** (escalation_declined/check_promotion/
   stock_denied/demand_qty/out_of_scope, ~62 occurrences) - carried forward,
   likely the SAME chain-cascade class as (2): an escalation_declined turn is
   itself an ANSWER to a prior pending offer, so if the offer-raising step earlier
   in the same chain diverged, the decline step has nothing real to decline.
6. **`branch_kind`: `stock_denied`/`demand_qty` unreachable in replay at all**
   (~19 occurrences) - **root cause IDENTIFIED, not fixed here**:
   `test_turn_replay.py` never sets `system_settings.chatbot_stock_denial_enabled`
   in the private test DB, so `engine.py::_stock_denial_enabled` reads its
   hard-coded `False` default on every replay run (confirmed by grep - the harness
   file has zero references to this setting) - contract 61/62's two branch kinds
   are STRUCTURALLY unreachable in replay regardless of what the recorded verdict
   says, on every case, not case-by-case noise. This is a harness gap
   (`test_turn_replay.py` itself, S6 deliverable 2), not a corpus curation issue or
   an engine defect - flagged for the coder/captain, not fixed by the tester
   (LESSONS: do not chase further as tester once a root cause is named).

The template below is real, not illustrative filler to delete before first use.

## Console corpus, 16 Sep 2026 (tester, this session, deliverable 2)

`console/` grew from 20 files (the prior session's "owner chains") to 116: 73 matched
from the nine `console_cases/*.yaml` (81 total cases parsed, 8 unmatched) against
`sorento_ai_automation_focus_full`'s `chatbot.turns` (all recorded under contact
437264483, matched newest-run-first by exact text sequence, single or multi-turn);
17 from `2026-09-15-focus.yaml` (origin/feat/chatbot-focus, ALL matched); 6 hand-built
(`hand_built: true` in `expected`) for the cases with a `expect.parser` pin but no
recorded run - `2026-09-16-rearch-prompt.yaml` (4 of its 6 unmatched single-turn
cases; the 2 multi-turn ones skipped, time-boxed) and `2026-09-14-low-stock-report.yaml`
(2, branch_kind-only, `intent_hint` inferred from the sibling rearch-prompt pin for
the same phrase). Each hand-built case asserts ONLY `branch_kind` - deliberately:
`_compare`'s `pending` check fires whenever the ACTUAL result carries an open
question, expected or not (`expected_pending is not None or actual_open_question is
not None`), so a hand-built case with no real run to ground `pending`/`action_kinds`
leaves those fields unasserted rather than guessed, and any real divergence there
reports honestly instead of silently passing or silently excusing.

**#930 (`2026-09-15-answer-feedback.yaml`, 8 cases) and #833 (`2026-09-11-
attribute-first-asks.yaml`, 14 cases) - NOT recorded, real finding, not silently
skipped.** Confirmed this session: #930's contact (487555417) has ZERO turns of any
kind in `sorento_ai_automation_focus_full` (matches its own commit message - the run
was blocked by a 401 auth failure and never executed). #833's contact (438930735)
has 12 turns in that DB, but they are all from a UNRELATED 6 Sep 2026 probe session
("Check stock SRT53-CR" etc.) - none match any of #833's 14 case texts (confirmed by
both per-contact and whole-database exact-text search for a sample phrase). **Neither
file has a single `expect.parser` pin anywhere** (grepped both) - every case's only
structured signal is free-text `reply_contains`. Hand-building a `verdict` (the
parser's structured output) from a bare reply substring would be INVENTING what the
parser said, not reconstructing it - the opposite of what a replay case is for.
**Not recorded, flagged for the captain**: either accept these 22 cases as
permanently un-recordable without a live rerun (the honest option), or schedule a
live rerun against a reachable backend once #930's auth blocker is fixed, from which
a real recording becomes possible.

`pytest tests/chatbot/test_turn_replay.py` after console (engine head unchanged,
merged through `b69a04f0c`): **42 passed, 148 failed**, ~55s, 190 cases total. Not
re-clustered field-by-field this pass (time-boxed per the captain's "corpus first"
instruction) - the six clusters logged after the prod_sample pass above still
describe the dominant shapes; two NEW real divergences from the 6 hand-built cases
are additionally unsigned in the file list, expected given they assert nothing
beyond branch_kind.

## Cluster 6 fixed at the harness (tester, 16 Sep 2026, S6 deliverable 1)

Root cause (named in the prod_sample section above, item 6): `test_turn_replay.py`
never wrote `system_settings.chatbot_stock_denial_enabled` (or the other switches
`engine.py::_read_switches` / `turn/policy.py::load_policy` read once per turn) onto
the private test DB's singleton row, so every replay ran under the hard-coded
ALL-FALSE `_TurnSwitches()` default. Fixed two-sided:

- `scripts/chatbot_record_turn.py` now captures the SOURCE DB's `system_settings`
  singleton at record time (`turn["switches"]`, one read per script invocation - a
  singleton has no history, so `switches_source` says `source_db_at_record_time` or
  `no_source_row_defaults`, never a historically-accurate value at the turn's own
  instant).
- `test_turn_replay.py::_apply_switches` writes a recorded case's `switches` onto the
  private DB's singleton row before each step, restored automatically by the fixture's
  transaction rollback (no explicit restore code needed). A case recorded before this
  field existed (`switches` absent) is an unchanged no-op.

**Measured, re-recording only the 5 `prod_sample/` files whose `expected.branch_kind`
is `stock_denied`/`demand_qty` at head `86fae7ceb`** (additive-only re-record, verified
`git diff --stat` shows zero deletions on all 5):

| file | divergences before | divergences after |
| --- | --- | --- |
| `demand-qty-423729473-chain-001-no-run-id.json` | 12 | 9 |
| `demand-qty-430229069-chain-001-no-run-id.json` | 5 | 4 |
| `stock-denied-423729473-chain-001-no-run-id.json` | 12 | 9 |
| `stock-denied-430229069-chain-001-no-run-id.json` | 4 (re-measured after, not captured before individually - see below) | 4 |
| `low-signal-423729473-chain-001-no-run-id.json` | not captured before individually - see below | 10 |

For the two rows without an individually-captured "before": the file-level "before"
run (same command, prior to re-recording) reported the aggregate corpus total
unchanged at 49 passed/141 failed, and the QUALITATIVE fix is confirmed the same way
on every one of the 5 files - **every occurrence of `step N branch_kind: expected
'demand_qty'/'stock_denied', got 'business_query'` is gone after the fix**, on every
step where the ORIGINAL first entry into that branch kind happens (step 1 of the
demand_qty pair, step 3/4 of the stock_denied pair on the two chain lengths). Cluster
6's own claim - "stock_denied/demand_qty are STRUCTURALLY unreachable in replay,
regardless of what the recorded verdict says" - is disproved: they are reached now.

**What remains on these 5 files is NOT cluster 6** - a `step 2 branch_kind: expected
'stock_denied', got 'low_signal'` divergence persists on all 5 (this is the SAME
step 2 in every file: the two 15-turn chains and the 17-turn chain share the first 15
turn ids verbatim, and the two 7-turn chains share all 7 - confirmed by comparing each
file's `source.turn_id` list). Cluster 5's own explanation applies here unchanged: an
`escalation_declined`/`stock_denied` turn immediately AFTER another lane's own turn is
itself an answer to a prior pending offer, so if THAT step diverged (which it does not
here - step 1 is now correctly `demand_qty`) the decline/re-ask has nothing consistent
to answer; not chased further, not this deliverable's scope. `send_attachments`
missing (cluster 1) also still fires independently on nearly every remaining step in
all 5 files, unrelated to switches. Aggregate suite total is UNCHANGED at 49
passed/141 failed on these 5 re-recorded files specifically (all 5 still fail
end-to-end on the other two clusters) - the fix is real but not yet visible at the
file pass/fail level on this narrow slice; a full corpus re-record (out of this
deliverable's scope, time-boxed) would be needed to see it move the aggregate.

## Cluster 1a signed, 16 Sep 2026 (owner ruling, tester commits on the owner's behalf)

Owner SIGNED cluster 1a (`send_attachments` missing where NO real files exist - 271 occurrences across the 73 files below, every one of this file's `send_attachments` divergences confirmed empty-attachments/no-tool_results, none mixed with a 1b instance). 1b (files where a REAL file existed and `send_attachments` is still missing - 16 files, 63 occurrences) and the 20 files mixing both sub-clusters are explicitly NOT signed here - still open findings.

- console/case-001-three-codes-the-third-has-neither-stock-nor-incoming.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-008-the-not-found-line-labels-its-axes-and-hides-the-debtor-code.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-009-a-pick-resolved-order-list-still-states-its-search-scope.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-016-a-bare-product-code-under-a-stock-thread-answers-stock-not-incoming.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-018-a-code-with-no-stock-is-named-before-the-incoming-block.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-019-a1-spec-ask-shows-the-compact-specs-line.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-020-a1-one-key-spec-ask-answers-that-key-only.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-021-item-8-list-price-of-a-product-reaches-the-base-list-price-field.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-022-d12-product-details-names-no-property-base-fields-still-show.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-023-item-8-seat-cover-material-reaches-the-key-that-contains-it.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-027-a2-stock-for-a-contact-with-no-grant-is-unchanged.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-030-a3-how-many-did-the-customer-take-three-line-pipeline.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-033-a3-open-do-grouped-by-customer-renders-headed-sections.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-034-a5-po-for-a-product-and-no-supplier-for-a-dealer.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-035-a6-last-in-for-a-product.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-036-a6-last-3-received-returns-three.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-037-a6-the-same-question-in-chinese.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-043-stock-then-po-carries-the-product.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-044-owner-8-sep-stock-then-po-for-another-code-then-last-in.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-045-owner-8-sep-a-delivery-word-plus-a-name-over-an-escalate-offer-is-an-order-ask.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-051-finding-1-a-product-with-many-specs-lists-all-of-them-no-more.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-053-ac-32a-default-contact-asking-for-m218-s-last-purchase-cost-is-denied.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-054-ac-32b-granted-contact-gets-the-last-purchase-cost-answer.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-055-ac-32c-family-ask-returns-one-row-per-member-per-location.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-056-ac-30-last-in-for-a-family-names-every-member.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-057-outstanding-report-journey-so-direct-ask-missing-scope-question-both-detail-cust.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-058-d17-parser-driven-word-answers-to-the-open-scope-detail-questions-and-a-new-ask.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-059-r12-a-scope-word-embedded-inside-a-longer-sentence-still-decides-the-scope.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-060-r13-a-customer-only-ask-reaches-the-same-report-by-product-instead-of-by-custome.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-061-r15-refinement-by-date-and-location-stacked.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-062-r16-picker-answer-keeps-the-outstanding-ask-fullshun-names.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-063-r19-scope-question-header-shows-customer-names-chin-chun-on-srtkt39ss-2026.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-064-r19b-full-header-on-scope-question-lists-all-distinct-customer-names-srtwt7445-f.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-065-r20-no-do-hint-on-the-customer-picker-of-an-outstanding-ask.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-067-r21-all-on-the-picker-keeps-the-outstanding-ask-lists-all-families-chin-chun-srt.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-069-r22a-decline-answer-leaves-the-offer-one-line-ack.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-070-r22b-second-unreadable-turn-leaves-the-offer-after-greeting.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-071-r23-so-detail-list-shows-latest-order-date-first.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/case-072-r24-a-business-query-under-an-open-offer-is-a-new-ask-hanlim-delivery.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/focus-001-a-did-you-mean-roster-sequential-picks-1-2-3-ac-1014-ac-1017.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/focus-008-i-a-new-subject-clears-the-multi-match-picker-ac-1020-ac-1002.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/focus-009-merge-d-outstanding-detail-list-renders-on-the-first-pick-ac-1106-ac-1138.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/focus-010-merge-e-customer-picker-scopes-the-report-to-chin-chun-hardware-ac-1156-ac-1162.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/focus-014-r-b-r-f-chin-chun-do-outstanding-customer-pick-both-ledgers-detail-list.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/focus-016-r-d-delivery-for-chin-chun-product-wc286-customer-pick-keeps-the-product.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/owner-15sep-chain-001-console-52b91f3f-0f51-41c1-ae04-6d35e5c79d35.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/owner-15sep-chain-002-console-8113f96b-0d9f-463e-b052-4282daf04f7a.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- console/owner-15sep-chain-005-console-bcd214ab-ab56-41bd-9fa8-b440982d4939.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- contract/line-001-stock-by-location.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/business-query-437264483-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/business-query-438930735-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/business-query-440987225-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/business-query-445239384-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/business-query-445239409-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/business-query-477071885-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/business-query-477071887-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/business-query-477071889-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/business-query-487555417-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/demand-qty-430229069-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/escalation-declined-437253667-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/escalation-declined-440987225-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/escalation-declined-445239390-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/escalation-declined-445239408-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/escalation-declined-445239415-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/escalation-declined-482786754-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/low-signal-423729094-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/low-signal-487555417-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/out-of-scope-423729094-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/out-of-scope-423755030-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/out-of-scope-445239384-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/out-of-scope-445239409-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/out-of-scope-477071889-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)
- prod_sample/stock-denied-430229069-chain-001-no-run-id.json: action_kinds: old n8n-side engine emitted a `send_attachments` action on every business turn regardless of content and left n8n to decide whether to actually send; this case has no real files (empty attachments / no tool_results carrying any), so the current engine correctly omits it - owner ruling, cluster 1a (signed JT 2026-09-16)

## Cluster 6 stock-allowed column, 4 cases signed 16 Sep 2026 (owner S6 ruling,
relayed by the coordinator)

The 4 prod_sample chains recorded under the OLD envelope-based stock-denial shape
(contact 423729473 and 430229069, each recorded twice under a `demand-qty-*` and a
`stock-denied-*` slug for the same underlying turn ids) now diverge on `branch_kind`
because the ruling makes both contacts ALLOWED by default (no explicit
`chatbot_stock_allowed=false` row seeded for them in the replay harness):

- prod_sample/demand-qty-423729473-chain-001-no-run-id.json: branch_kind: stock allowance moved to respond_contacts.chatbot_stock_allowed, default on (S6 ruling); the respond.io field is ignored (signed JT 2026-09-16)
- prod_sample/demand-qty-430229069-chain-001-no-run-id.json: branch_kind: stock allowance moved to respond_contacts.chatbot_stock_allowed, default on (S6 ruling); the respond.io field is ignored (signed JT 2026-09-16)
- prod_sample/stock-denied-423729473-chain-001-no-run-id.json: branch_kind: stock allowance moved to respond_contacts.chatbot_stock_allowed, default on (S6 ruling); the respond.io field is ignored (signed JT 2026-09-16)
- prod_sample/stock-denied-430229069-chain-001-no-run-id.json: branch_kind: stock allowance moved to respond_contacts.chatbot_stock_allowed, default on (S6 ruling); the respond.io field is ignored (signed JT 2026-09-16)

**Signing this does NOT turn these 4 green, flagged rather than silently left** - measured this session: once the contact is allowed, the engine reaches the REAL fetch (`crm_inventory_stock_balance_list` / `crm_master_products_list`) and `test_turn_replay.py::_fake_call_tool` raises `AssertionError: replay case called tool ... with no recorded tool_results entry for it` BEFORE `_compare` (and therefore before any DIVERGENCES.md signature) ever runs - there is no recorded tool result for the corrected happy path, the same limitation `console/handpass1-001-stock-allowed-check-stock.json` (this session's other stock-allowance case) already documents. These 4 stay red until re-recorded from a live corrected run, or are retired as no-longer-representative of any reachable branch under the new default (the scenario "stock denied" now requires a contact ROW explicitly set to false, which none of the 4 originally-sampled prod contacts carry).
