# Full-suite (`tests/chatbot`) triage, 16 Sep 2026 (tester, coordinator's pre-PR-gate item 1)

Command: `pytest tests/chatbot -q -p no:cacheprovider --tb=line` (private test DB
`sorento_ai_automation_rearch_test`), run TWICE this session:

1. Head `c815e5bd7` (before merging coder 8's fix round): **653 failed, 3160 passed,
   21 skipped, 5 xfailed, 273 warnings, 7 errors** (3846 collected, 232s).
2. Head `5b079877f` (coder 8's fix round `c3bfd6d6c` merged in, plus this session's
   two fixture-grant fixes - see "Fixture items" below): **649 failed, 3164 passed,
   21 skipped, 5 xfailed, 273 warnings, 7 errors** (3846 collected, 331s). **This
   second run is the one the table below measures** - the file-level totals and
   every cluster are from the merged-head run.

Raw logs: `/tmp/full_suite_16sep.txt` (run 1), `/tmp/full_suite_16sep_merged.txt`
(run 2) - neither committed, regenerate with the command above; a 650/656-line
matcher captured ~99% of individual failure lines for clustering, file-level totals
below are complete via a separate 100%-coverage pass.

**Coordinator's own measurement on the coder's side ("1577 failed, 972 in
test_replay.py") does not appear here - explained, not a discrepancy.** That number
was measured before this tester's B2 retirement commits (`c815e5bd7` and earlier,
already on `test/chatbot-turn-rearch-red` since mid-session) had reached the coder's
branch history point coder 8 was looking at. Both runs in this table already sit
AFTER that collapse (`test_replay.py` is 53 in both, `test_worlds.py` is 193 in
both, unchanged by this merge - coder's changes this round did not touch either
file). No further collapse to expect from this merge alone.

## Fixture items (fixed before this pass, per the coordinator's message)

- **`PUT /contacts/{id}/chatbot` now requires `user_management.contacts.edit`**
  (coder 8's just-merged permission gate, confirmed correct - not a route bug).
  Added the grant to `test_rearch_s6_stock_allowed.py:55`, `test_rearch_s5_
  config_routes_commit.py:60`, `test_rearch_s5_config_routes.py:77`'s `_permissions`
  fixtures. 42/42 pass across the three files; none of the three appear in the
  merged-head failure list anymore (commit `5b079877f`).
- **`settings/chatbot/page.test.tsx:228`** - verified on the merged head: tester 7's
  fix (`657743ab5`) IS present (`git log -1` on the file confirms it as the last
  touch) and the file is green, 8/8, via `npx vitest run`. No code change needed;
  coder 8 was very likely looking at a pre-pull state.

**No fixes beyond the two fixture items above** - table only, per instruction. Class
legend:

- **ENV** - test/DB/fixture state, not a code defect (missing seed, wrong `.env`, no
  OpenAI key reachable, missing permission grant on a test user).
- **STALE TEST** - asserts a retired head/tail/dialogue behaviour (AC-1592: port or
  retire, rule named).
- **ENGINE DEFECT** - measured behavioural gap in currently-live code, needs a coder fix.
- **UNCLASSIFIED** - counted, not individually root-caused this pass (see "Long tail").

## File-level totals (complete, 654/654 matched failure lines + 7 collection errors)

| file | failed | primary theme(s) |
| --- | --- | --- |
| `test_worlds.py` | 193 | `SUGGESTED_TEAMS` import (135, STALE), casual_llm/no OpenAI key (42, ENV), misc `--tb=line` msg variants (16) |
| `test_turn_replay.py` | 117 | the S6 replay gate - already triaged in `replay_turns/DIVERGENCES.md` + `PENDING-LIVE-RERUN.md` this session (T4 diagnosed, composite chains, etc.) - not re-litigated here |
| `test_outstanding_lane.py` | 59 | `KeyError 'variables'` (old nested session shape, STALE, 9), casual_llm/no OpenAI key (ENV, ~10), scope-question/report-tool assertions (ENGINE DEFECT candidates, ~6), misc |
| `test_replay.py` | 53 | KEPT-node divergences vs real n8n captures, unregistered in `tests/chatbot/divergences.py` (`output-structurer` 19 + `disallowed-entity-gate`/`resolve-exit-*`/`annotate-incoming-picker` ~25) - ENGINE DEFECT candidates, pre-existing (not touched by this session's B2 retirements, confirmed) |
| `test_growth_r1_review_fixes.py` | 46 (45 matched + 1 collection var) | `head/output_exchange.py` deleted (STALE, B2 item, ruling pending from coordinator's item 3) |
| `test_s6a_gate_dry_run_and_seams.py` | 17 | `engine.decide` deleted (STALE, "delegate seam" architecture theme) |
| `test_s3_switch_and_complete_by_body.py` | 15 (8 failed + 7 errors) | `result.delegate` / "needs a DELEGATED turn" (STALE, same delegate-architecture theme) |
| `test_foundre_rung_end_to_end.py` | 12 | "PO rung never ran" / "no crossdomain event persisted" - crossdomain/fan-out feature not firing end to end (ENGINE DEFECT candidate - see below, real feature the plan requires) |
| `test_s3_canned_and_ideate.py` | 12 | canned-branch reply text mismatch + `KeyError` (mixed STALE/ENGINE DEFECT, not fully split this pass) |
| `test_engine.py` | 11 | `engine._drop_*` deleted (STALE, delegate-architecture theme) |
| `test_r3_pending_end_to_end.py` | 11 | `KeyError 'variables'` (STALE, same nested-shape theme as `test_outstanding_lane.py`) |
| `test_s6_s7_integration.py` | 9 | `('done', None)` / exit-matrix tuple mismatches (STALE, delegate-architecture theme - "exit matrix" is an old-pipeline concept) |
| `test_engine_failure_paths.py` | 8 | `engine.decide` / "still delegates" (STALE, delegate-architecture theme) |
| `test_parser_low_stock_words.py` | 7 | `SEMANTIC_PARSER_PROMPT_SLIM` import missing (STALE or ENGINE rename - not resolved this pass, see below) |
| `test_harness_injections.py` | 6 | `KeyError 'stage'` (STALE, trace-shape theme) |
| `test_s5_escalation_lane.py` | 6 | `KeyError 'stage'` (STALE, trace-shape theme) |
| `test_trace_legibility.py` | 6 | branch_kind mismatches (`clarify_menu` vs `escalate_offer`, `None` vs `out_of_scope`) - ENGINE DEFECT candidate, not individually confirmed this pass |
| `test_engine_company_scope.py` | 4 | `KeyError 'resolve_gate'` (STALE, trace-shape theme) |
| `test_last_cost_gate.py` | 4 | not sampled this pass |
| `test_parser_user_block_parity.py` | 4 | `engine._pending_*` deleted (STALE, delegate-architecture theme) |
| `test_s6c_answer_lane.py` | 4 | `engine.decide`-family (STALE, delegate-architecture theme) |
| `test_s6c_engine_paths.py` | 4 | `None == 'business_query'` branch_kind (STALE/delegate theme, "H11 zero tools" is an old-pipeline naming) |
| `test_complete_turn.py` | 3 | pre-existing, unrelated to this session's B2 edit (confirmed: the edited `TestGuards` class is fully green on its own) - not sampled further this pass |
| `test_console_turn_endpoint.py` | 3 | session-carry-across-turns assertion (ENGINE DEFECT candidate, not confirmed) |
| `test_low_stock_lane.py` | 3 | `contracts.DOMAIN_SPEC` deleted (STALE, AC-1594 explicit deletion, real successor `turn/policy_rows.py`) |
| `test_pass4_item1a_team_clarify_consumed.py` | 3 | not sampled beyond one line |
| `test_pass5_item2_member_offer_business_query_filter_route.py` | 3 | casual_llm/no OpenAI key (ENV) |
| `test_s7_dispatch_edges.py` | 3 | Redis-outage-during-ordering assertion (ENGINE DEFECT candidate, not confirmed) |
| `test_s7_ordering_and_offload.py` | 3 | `'done' in ('delegated','failed')` (STALE, delegate-architecture theme) |
| `test_trace_persistence.py` | 3 | `None == 'crm_inventory_stock_balance_list'` tool-event read (ENGINE DEFECT candidate, not confirmed) |
| `test_completed_lanes_switch.py` | 2 | `None == 'low_signal'` branch_kind, possibly S9's empty-policy-table gap (see priority-2/3 items) |
| `test_pass5_item1_photo_attachment_alias.py` | 2 | not sampled |
| `test_rearch_s3_attribute_first.py` | 2 | not sampled |
| 15 files at 1 failure each | 15 | not sampled individually this pass (see raw log) |

## Cross-cutting themes (span many files, sized precisely)

These are NOT separate from the file rows above - the file rows already attribute their
share; this section names the SHARED root cause so it is fixed once, not per file.

| theme | total occurrences | signature grep | class | rule / notes |
| --- | --- | --- | --- | --- |
| **"Delegate-architecture" test suite** - reads/writes the OLD engine's trace `stage` key, `session_vars["variables"]` nested shape, or a trace's `resolve_gate` key; monkeypatches/reads `engine.decide`, `engine._drop_*`, `engine._pending_*`, `.delegate`, or asserts a `('done'/'delegated'/'failed', ...)` tuple | **179** (105 `KeyError` + 74 `AttributeError`) + a handful of tuple-assertion variants | `KeyError: '(stage\|variables\|resolve_gate)'`, `AttributeError:.*(decide\|_dro\|_pen\|delegate)` | **STALE TEST**, AC-1592 | An entire generation of test files (`test_s3_*`, `test_s5_*`, `test_s6_s7_integration.py`, `test_s6a_*`, `test_s6c_*`, `test_s7_*`, `test_engine*.py`, `test_r3_pending_end_to_end.py`, `test_harness_injections.py`, `test_parser_user_block_parity.py`, `test_pass4_*`/`test_pass5_*`) predates the S0-S6 rearch and was never migrated off the pre-rearch "head hands off to a lane which delegates" pipeline shape. This is the single biggest classifiable bucket in the whole suite (27%) - needs a captain ruling on port-vs-retire scope before any coder time, not a per-file guess. |
| **T3 - casual lane live LLM call, no OpenAI key reachable in test env** | **~78** (42 in `test_worlds.py`'s own "failed at casual_llm: None" wording + 36 as `lanes/casual.py`'s literal fallback text "Sorry, I can't reply to that right now..." surfacing as the actual reply in `test_outstanding_lane.py` and others) | `failed at casual_llm: None`, `Sorry, I can't reply to that right now` | **ENV / harness gap (T3)** | Confirmed root cause: `app.services.chatbot.lanes.casual.ClarifierError: no API key configured for provider 'openai'`. Already on the coordinator's queue as T3 - `test_turn_replay.py` needs the casual lane stubbed the same way the parser is; this measurement shows the SAME gap also hits `test_worlds.py` and several other files directly (not just the replay gate), so T3's fix should stub at a shared seam (`lanes/casual.py`'s LLM call site, or `conftest.py`'s autouse fixtures) rather than per-file. |
| **KEPT-node divergences unregistered in `tests/chatbot/divergences.py`** (the node-replay corpus's OWN divergence file, distinct from `replay_turns/DIVERGENCES.md`) | **~53** (all of `test_replay.py`'s remaining failures: `output-structurer` 19, `disallowed-entity-gate`/`resolve-exit-*`/`annotate-incoming-picker` ~34) | `diverges from the captured n8n output and is not registered` | **ENGINE DEFECT candidate** | Pre-existing (measured: none of these are among the 5 runners this session's B2 commit retired - `gate`, `resolve_gate`, `pickers`, `tier_gate`, `fetch` are explicitly KEPT nodes per `test-triage.md`). One reproducing test id: `test_replay.py::test_full_corpus_replay[output-structurer/sub-get-results/gr-15192601]`. Needs a coder/owner look: either a real regression in a still-live function, or an intentional change that needs a `divergences.py` entry (same shape as the `replay_turns/DIVERGENCES.md` signing this session already did for the OTHER divergence file). |

## Named single-issue findings worth flagging directly

- **`test_foundre_rung_end_to_end.py::TestAC921ThePORungReachesTheCustomer`** (12
  failures) - "the PO rung never ran on a real turn" / "no crossdomain event
  persisted" - this is the crossdomain/fan-out feature (PLAN's own "fan-out" concept,
  contract 115) failing END TO END through `engine.run_turn`, not a deleted-import
  problem. **ENGINE DEFECT candidate**, not a stale-architecture symptom - flagging
  for the coordinator to route to coder 8 rather than bucket with the delegate theme.
- **`test_low_stock_lane.py::TestDomainWiring`** - `contracts` module has no attribute
  starting `'D...'` (confirmed: `DOMAIN_SPEC`, AC-1594's own explicit deletion list).
  **STALE TEST**, clean AC-1592 port target: `turn/policy_rows.py`'s domain-row table
  is the confirmed successor (same table `lanes/business/resolve_gate.py` already
  reads for `domain_switch_words`).
- **`test_parser_low_stock_words.py`** - `SEMANTIC_PARSER_PROMPT_SLIM` no longer
  exists under `app.services.*`; not traced to a rename/successor this pass (the UAC's
  D-list mentions a slimmed prompt lineage but this exact name was not found live
  anywhere in `app/`) - needs a closer look before classifying STALE vs ENGINE.

## Long tail (not individually triaged this pass)

12 files at exactly 1 failure each, on the merged head (`test_broaden_domain_switch_
e2e.py`, `test_import_boundary.py`, `test_pass4_item1b_marketing_ambiguous_clarify.py`,
`test_pass4_item2_last_month_keeps_customer_scope.py`,
`test_pass4_item3_last_month_under_member_offer.py`,
`test_pass4_item4_issue708_partial_pick_scope.py`,
`test_rearch_s3_journey_chain.py`, `test_rearch_s4_prompt_blocks.py`,
`test_s5_escalation_seams.py`, `test_s6b_fetch_lane.py`,
`test_s8_switches_in_settings.py`, `test_spec_visibility_projection.py`) -
`test_rearch_s5_config_routes.py` and `test_rearch_s5_config_routes_commit.py` were
in this list on the pre-merge run and are GONE now (the fixture-grant fix above).
Full list and messages in `/tmp/full_suite_16sep_merged.txt`, not preserved as a
committed artifact (regenerate with the command at the top of this file). Several are
very likely one-off instances of the same delegate-architecture or T3 themes above
(not confirmed per-file this pass); `test_rearch_s3_journey_chain.py` and
`test_rearch_s4_prompt_blocks.py` are rearch-native files so their single failures are
worth a closer look before assuming STALE.

## Method note

Failure lines parsed from `--tb=line` output via a regex tolerant of parametrize ids
containing spaces (matched 650/656 = 99% on the merged-head run; the file-level
totals table above is independently 100%-complete via a separate per-file count that
does not depend on message-parsing). Clustered by `(file, normalized signature)`,
then re-aggregated by signature alone to find cross-cutting themes, then by file
alone for completeness. Every classification above that names a specific
line/import/attribute was grep-confirmed against the current source this session,
not inferred from the message text alone; classifications marked "not confirmed" or
"candidate" are message-text-only and need a closer look before acting on them. The
cross-cutting-theme occurrence counts (179 delegate-architecture, ~78 T3, ~53
unregistered-divergence) were measured on run 1 (`c815e5bd7`) and not re-counted on
the merged head - the delta between the two runs is exactly the 4 fixture-grant
fixes (all in files outside those three themes), so the theme counts are still
accurate to within that same 4.
