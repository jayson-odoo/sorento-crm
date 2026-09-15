# S6 test triage - files importing `head/`, `dialogue/` or `tail/` (AC-1592)

`PLAN-chatbot-turn-rearch.md` S6, `chatbot-turn-rearch-acceptance-criteria.md` AC-1592:
every file under `tests/` importing `head/output_exchange.py`, `tail/compile_state.py`,
`head/route.py`, `tail/pending.py` or `dialogue/` is PORT (which contract line, new file
name) or RETIRE (which deleted rule), no test of KEPT code touched, no test deleted by
the coder.

**Method.** `grep -rn` for the actual import statements (`from app.services.chatbot.head
import output_exchange`/`from app.services.chatbot.head.output_exchange import`, the
same shape for `head.route`, `tail.compile_state`, `tail.pending`, and
`app.services.chatbot.dialogue`) under `tests/`, confirmed against each hit's own line
(a looser first pass over the bare strings had noise - `test_rearch_s3_deletions.py`
matched on its own docstring TEXT naming the modules it guards, not a real import).
`pytest tests/chatbot/ --collect-only -q` cross-checked the result. No `dialogue/`
importer exists under `tests/` at all - either it was never given its own test file, or
it is only reached indirectly through `engine.run_turn`.

**Critical finding, measured this session, changes the urgency of this table.**
`app/services/chatbot/head/route.py`, `head/output_exchange.py`,
`tail/compile_state.py` and `tail/pending.py` **do not exist in this worktree today**
(`ls app/services/chatbot/head/` = `access.py`, `build_ctx.py`, `parser.py` only;
`ls app/services/chatbot/tail/` = `compose.py`, `member_offer.py`, `outcome.py`,
`reply_ladder.py` only - `head/route.py`/`head/output_exchange.py`/
`tail/compile_state.py`/`tail/pending.py` are ALREADY GONE, presumably deleted in the
coder's own S3 fix round, `eeddb6d10`, without the test suite being ported alongside).
This is not "will collection-error once the coder deletes these" - it errors NOW:
`pytest tests/chatbot/ --collect-only -q` reports **17 collection errors** out of 4482
collected, 12 of them `ModuleNotFoundError`/`ImportError` at the file's own top-level
import (blocking the WHOLE file, including any kept-code tests mixed into it), five
more found only by running collection (`test_ascii_digit_semantics.py`,
`test_dry_run_isolation.py`, `test_r3_dual_read.py` - all a real top-level import my
first grep pass missed; `test_parser_low_stock_publish.py` - transitively, it imports a
helper FROM `test_parser_growth_r1_reachability.py`, which top-level-imports
`head.route`; `test_parser_warehouse_arrival_cue.py` - a DIFFERENT, unrelated defect,
`ImportError: cannot import name 'SEMANTIC_PARSER_PROMPT_SLIM'`, nothing to do with
AC-1592, not triaged here). 17 files, not 13.

**Retirement scope, this commit.** Two files retired so far (both zero risk to KEPT
code - see each entry): `test_rearch_s0_domains_seed.py` (`383718165`, the S0
"table == constant" guardrail the plan itself names) and `test_domain_spec.py`
(`1e4004c0b`). The other 15 files below are triaged but NOT retired or ported yet -
several (marked MIXED) also exercise KEPT code (`lanes/business/gate.py`,
`resolve_gate.py`, `fetch.py`, `pickers.py`, `tier_gate.py`, `services.py`,
`answer.py`) in the SAME file as the doomed-module assertions, and splitting a doomed
assertion out of a file that also grades a kept node needs either the coder's new
module boundary (so the PORT lands somewhere real, not a guessed filename) or a
careful line-by-line split this pass did not have the budget to do safely. Doing it
now risked exactly what AC-1592 forbids - silently losing coverage of kept code while
chasing the doomed half. Flagged as the concrete next step, not silently deferred -
and URGENT: 12 of the 17 files are entirely uncollectable right now, so if any of
them also carries a kept-code test, that test is not running today, at all.

## Table

| file | lines | what it asserts | doomed import(s) | verdict |
|---|---|---|---|---|
| `test_domain_spec.py` | 409 | `contracts.DOMAIN_SPEC` and every dict derived from it (`BARE_ENTITY_TYPE_BY_DOMAIN`, `DOMAIN_SWITCH_WORDS`, `CHATBOT_READ_ONLY_TOOLS`) never drifted from a FROZEN "before" snapshot of the six literals D9 collapsed; `head.output_exchange.derive_routing` exercised only as a DOMAIN_SPEC consumer | `head.output_exchange` | **RETIRED this commit.** Rule: D9's "nothing moved" snapshot check has nothing left to check once `DOMAIN_SPEC` itself is deleted (AC-1594) - the file's own docstring states its entire purpose is proving DOMAIN_SPEC parity. No kept-code assertion found in it (confirmed: every import is DOMAIN_SPEC-derived or a DOMAIN_SPEC consumer). |
| `test_replay.py` (+ `_corpus.py`, `divergences.py`) | 772 (+615, +1231) | Grades the Python port's output against REAL n8n node executions, byte-for-byte, per NODE - `head.build_ctx`, `head.route.route_turn`, `head.output_exchange.output_exchange`/`suggest_follow_up` (doomed) **alongside** `lanes/business/gate.run_gate`, `resolve_gate.*`, `pickers.*`, `tier_gate.tier_gate`, `fetch.*` (six functions), `tail.outcome.build_outcome`/`escalate_catalog`, `tail.member_offer.*`, `tail.compile_state.compile_current_state`/`seal` (doomed), `tail.compose.crossdomain_compose` - ALL in one file, one runner per node | `head.route`, `head.output_exchange`, `tail.compile_state` | **MIXED, not touched.** Contract line 98 ("replay corpus for kept nodes") names exactly this file's OWN purpose for the nodes that survive (`gate`, `resolve_gate`, `pickers`, `tier_gate`, `fetch`, `tail.outcome`, `tail.member_offer`, `tail.compose` - all listed "kept" in the plan's own "What exists and is kept"). This lane's NEW `test_turn_replay.py` (S6 deliverable 1-2, `f38ae3f52`) supersedes the DOOMED nodes' OWN grading (it grades the same real turns end to end through `engine.run_turn`, which is the whole point once there is no separate n8n-shaped `route_turn`/`output_exchange` node to compare node-by-node) - RETIRE is the right call for the `build-ctx`/`route-turn`/`output-exchange` RUNNERS specifically, once identified line-accurately; PORT is not needed since the replacement already exists. The KEPT-node runners (gate/resolve_gate/pickers/tier_gate/fetch/tail.outcome/tail.member_offer/tail.compose) must stay untouched. Next step: a surgical edit removing only the three doomed runners (`_run_build_ctx` is arguably KEPT-adjacent since `build_ctx` itself is not in AC-1594's delete list - re-check before touching it) and their own parametrize entries from `_corpus.py`, never the file wholesale. |
| `test_crossdomain_ladder.py` | 1358 | `run_crossdomain`'s purchase-order ladder rung (contract 3, "zero or short stock climbs the ladder") - business logic in `lanes/business` (kept); `head.route.DEFAULT_UNSUPPORTED_DOMAINS` used once, incidentally, to build a route decision at the edges | `head.route` | **PORT**, contract line 3. The ladder logic itself lives in kept code; only the one incidental `DEFAULT_UNSUPPORTED_DOMAINS` read needs its import swapped to wherever the coder's `turn/policy.py`-era `Policy` object exposes the same "unsupported domains" fact (`chatbot_domains.supported` per the plan's "policy" section) - a one-line import fix once that accessor exists, not a rewrite of this file's ~1358 lines of ladder assertions. |
| `test_growth_r1_review_fixes.py` | 948 | Second-rendering defects (restricted-field drop over `group_by`, ladder absence line, summary filter) - real contract-relevant behaviour (`lanes/business/answer.py`, kept), reached via `tail.pending.escalation_team`, `head.output_exchange.output_exchange`, `head.output_exchange._switch_word_domain` | `head.output_exchange`, `tail.pending` | **PORT**, pending the coder's `turn/compose.py` stabilizing (measured this session: `engine.run_tail` still calls the OLD `outcome_mod`/`reply_ladder` for most paths, not `turn/compose.py`, so there is no stable target file yet - porting now would guess at an API that has not settled). The underlying RULES (second-rendering must agree with the first) are still real and must be re-asserted once compose.py's own shape is confirmed. |
| `test_load_script_seeding.py` | 531 | A LOAD/SEED SCRIPT fix (`_seed_contacts` needs `workspace_id` + `contact_agent_access`), verified end to end by checking `head.output_exchange.derive_routing` no longer denies the seeded turn | `head.output_exchange` | **PORT**, low confidence on the target - this file is really testing a SCRIPT (`scripts/chatbot_load.py`), and `derive_routing` is only its verification oracle. Once the new engine exists, the verification step should call `engine.run_turn` (or whatever ROUTE stage function replaces `derive_routing`) instead; the seeding fix itself is unaffected and needs no re-proving. |
| `test_output_exchange_rules.py` | 1124 | D16's "the LLM does language, code does everything else" rules, unit-tested directly against `output_exchange`/`derive_routing` | `head.output_exchange` | **PORT**, largest file in scope. Some individual rules may turn out to be RETIRE rather than PORT once the coder's composer is stable - the plan's "Fetch and compose" section says composers return DATA first (`Answer`), text applied by "the #930 grammar" afterward, which is a different shape than `output_exchange`'s post-process-a-string approach; a rule that only existed to patch a string after the fact may have no equivalent once nothing produces a raw string to patch. Flagged, not resolved - the coder's compose.py shape decides which. |
| `test_output_exchange_unit.py` | 168 | The dash-normalizer coverage gap (`suggest_follow_up`, not `output_exchange`/`post_process`) | `head.output_exchange` | **PORT**, contract line 55 ("dash fold"). Small, self-contained - should be one of the first ports once the target function exists. |
| `test_parser_growth_r1_reachability.py` | 560 | Parser reachability for `so_outstanding`, `purchase_order`, `group_by`/`top_n`, `spo_allocation` end to end through `head.route.decide` and `head.output_exchange._required_emission_keys`/`DOMAIN_BLOCKED_HINTS` | `head.route`, `head.output_exchange` | **PORT**, several contract lines (AC-905/907/908/909-910/911 in growth-r1's own numbering; maps onto this plan's domains/answers lines 1-25 territory). Business-relevant (these are real supported domains), needs the new ROUTE stage. |
| `test_route_unit.py` | 332 | `head.route.decide`/`route_turn` unit properties a fixture cannot show: the R1/H1 `stock_denied`/`demand_qty` flag-gated vocabulary fix | `head.route` | **PORT**, contract line 61 ("stock denial switch"). Direct unit test of the doomed module's OWN logic - needs the new ROUTE stage's equivalent decision function. |
| `test_s6c_answer_lane.py` | 2774 | Overwhelmingly KEPT-code tests (`lanes/business/answer.py`, `sub_answer.py`, `miss_suggest.py`, `services.AnswerServices`) - `head.route.decide` appears in exactly TWO test functions (`TestChatbotCompletedLanesEngineWiring::test_with_the_switch_on_the_arm_stamps_and_the_answer_is_the_quantity_verdict` line 1617, `test_...default_r1_position...` line 1654), both about the R1 stock-denial flag's interaction with the completed-lanes gate | `head.route` | **MIXED, not touched.** The other ~2770 lines are kept-code tests and MUST NOT be touched by this triage. PORT scope is exactly those two test functions' `from app.services.chatbot.head.route import decide` line, once the new ROUTE stage exists - everything else in the file stays as-is. |
| `test_s8a_hardening.py` | 657 | Hardening rules (D14/D15/R5, write-only contract, `_assert_emission` container-type check) directly against `head.output_exchange.output_exchange`/`post_process`/`ParserOutputError` | `head.output_exchange` | **PORT**, safety-relevant (contract lines 68-70, dry-run isolation / harness injections / dedupe territory). Should be an early port given its D14/D15 subject matter overlaps this lane's own D14 guarantees. |
| `test_tail_units.py` | 1094 | Two fixes node replay cannot show (AC-205/H29 and one other), against `tail.compile_state.compile_current_state` and `head.output_exchange.offer_is_open` | `tail.compile_state`, `head.output_exchange` | **PORT, but flagged as a likely RETIRE once confirmed** - AC-205/H29 are pre-rearch ticket numbers, and this lane's own S2 tests (`test_rearch_s2_pending_one_object.py`, `test_rearch_s2_focus_rules.py`, already green) may already cover the SAME ground under the new `turn/pending.py`/`turn/apply.py` shape, in which case this file is RETIRE (superseded), not PORT (duplicate). Needs a coder or captain read of whether the S2 suite's own cases already encode these two fixes before deciding; not resolved here. |
| `test_warehouse_entity.py` | 442 | Warehouse entity extraction into `warehouse_ids` (contract 19, "twelve named entity kinds"), against `head.output_exchange.output_exchange` | `head.output_exchange` | **PORT**, contract line 19. Self-contained, should port cleanly once the ROUTE/APPLY stage's warehouse-entity handling exists (likely `turn/apply.py`'s `narrow`/`plan` functions per the PLAN's APPLY contract). |
| `test_ascii_digit_semantics.py` | 168 | ASCII-digit normalization rules against `head.output_exchange` (plus `jsc`, kept) | `head.output_exchange` | **PORT**, self-contained, small - group with `test_output_exchange_unit.py` and `test_r3_dual_read.py` as early ports. |
| `test_dry_run_isolation.py` | 1042 | **D14 itself** - the dry-run-writes-nothing guarantee this lane's OWN replay harness depends on (`dispatch`, `engine`, `lanes.business` all KEPT; `FetchServices` KEPT; `tail.compile_state` the only doomed import) | `tail.compile_state` | **MIXED, URGENT.** The single largest file in this newly-found group and the most safety-relevant: D14 is a governing invariant named throughout the plan (S6's own `test_turn_replay.py` relies on the SAME guarantee to keep a replay run from writing outside `chatbot.turns`). Right now this whole 1042-line file is UNCOLLECTABLE, so D14's dedicated test coverage is not running AT ALL, not "will need porting later." Highest-priority item in this table - needs the one `tail.compile_state` import identified and swapped (or the assertion re-pointed at whatever the new tail persists through, `conversation_variables_service.overwrite_for_contact` per `engine.py::run_tail`, measured this session) before anything else in this list. |
| `test_r3_dual_read.py` | 164 | R3 dual-read property against `head.output_exchange` only | `head.output_exchange` | **PORT**, self-contained, small. |
| `test_parser_low_stock_publish.py` | - | Not independently broken - imports a helper FROM `test_parser_growth_r1_reachability.py`, which top-level-imports `head.route`; fails transitively | `head.route` (transitive) | **Resolves itself** once `test_parser_growth_r1_reachability.py` is ported - no separate action. |
| `test_parser_warehouse_arrival_cue.py` | - | `ImportError: cannot import name 'SEMANTIC_PARSER_PROMPT_SLIM' from app.services.chatbot_parser_prompt` | none (unrelated) | **Out of AC-1592 scope** - a pre-existing, different defect, not a `head`/`tail`/`dialogue` import. Flagged for the captain, not triaged as part of this deliverable. |

## Summary

17 files found (13 by direct import grep + 2 by full-tree collection + 1 transitive +
1 out-of-scope). Retired 2, one URGENT unresolved, 12 PORT (2 needing a decision
first), 2 MIXED needing a surgical split, 1 resolves itself, 1 out of scope.

- **Retired (this lane, S6):** 2 files - `test_rearch_s0_domains_seed.py`
  (`383718165`), `test_domain_spec.py` (`1e4004c0b`). Both wholly obsolete, zero
  kept-code risk.
- **URGENT - the one item in this table that should not wait for a port round:**
  `test_dry_run_isolation.py`, D14's own dedicated coverage, currently fully
  uncollectable (see its table row).
- **PORT, self-contained (safe for a coder or the tester to pick up next, in
  roughly ascending risk order):** `test_output_exchange_unit.py`,
  `test_ascii_digit_semantics.py`, `test_r3_dual_read.py`, `test_warehouse_entity.py`,
  `test_route_unit.py`, `test_s8a_hardening.py`, `test_load_script_seeding.py`,
  `test_parser_growth_r1_reachability.py`, `test_crossdomain_ladder.py` (one-line
  import swap), `test_output_exchange_rules.py`, `test_growth_r1_review_fixes.py`.
- **PORT, needs a decision first:** `test_tail_units.py` (possible duplicate of
  already-green S2 tests - check before porting, may be RETIRE instead).
- **MIXED, needs a surgical split (not a wholesale retire or port) so kept-code
  coverage is never lost:** `test_dry_run_isolation.py` (see URGENT above),
  `test_replay.py` (+ `_corpus.py`, `divergences.py`) - three doomed node runners
  out of eight total; `test_s6c_answer_lane.py` - two test functions' import line
  out of ~2774 lines.
- **Resolves itself once its source ports:** `test_parser_low_stock_publish.py`.
- **Out of AC-1592 scope, different defect:** `test_parser_warehouse_arrival_cue.py`.
- **No `tests/` file imports `dialogue/` directly** - either untested directly today
  or only reached through `engine.run_turn`'s own integration tests (`test_engine.py`
  and friends, none of which import `dialogue` by name).

Every PORT/MIXED item above is a real target for a FOLLOW-UP tester or coder pass
once `app/services/chatbot/turn/compose.py` (and whatever ROUTE-stage module
replaces `head/route.py`) has a stable shape - porting against a module that
`engine.run_tail` does not yet call for most paths (measured this session) would be
guessing at a contract line the coder has not built yet, which is exactly what
"write to the test list, do not invent scope" warns against.

## Execution log (AC-1592, this session, continuing from `a5419f97e`)

Executing the 15 pending verdicts above. One row updated per action; the analysis
above is left as-is (historical record) rather than rewritten in place.

- **`test_dry_run_isolation.py` - URGENT, done (`8a64a713b`).** Only one of its nine
  classes used the doomed import (`TestLiveTailSessionPatchAbsentIsPreserved`,
  finding 6). Confirmed the rewritten `engine.py::run_tail` has no "sealed reply" /
  `session_patch` concept at all - it builds the five-key payload directly from
  `State`/`Pending` every call, so the absent-vs-explicit-empty ambiguity that class
  existed to guard cannot occur in the new write site. RETIRED that one class (rule
  named in the file and the commit body); the other 8 classes (findings 1-5,
  escalation preview, canned words) are unrelated to the doomed import and were not
  touched. File now collects; 13/13 pass.

- **`test_output_exchange_unit.py` - PORT, done, RED for real reasons.** New file
  `test_rearch_port_output_exchange_unit.py`. Both properties probed directly
  against the real current code (no mocking): (1) the Unicode-dash fold - the old
  normaliser moved conceptually to `resolve_gate._PRODUCT_FOLD`/`_token_of`, but
  that regex is ASCII-only (`[-\s]+`), so a MINUS SIGN (U+2212) or EN DASH (U+2013)
  in a product code's raw text now survives into the resolver's match token
  unchanged - **exec 12053189's original production incident is reproduced in the
  new architecture**, confirmed by direct call to `_token_of`. (2) The F3
  domain-hint enum guard - `contracts.coerce_domain_hint` exists but has no call
  site anywhere in this worktree (`grep -rn coerce_domain_hint app/services/
  chatbot/` finds only its own definition and one comment); `turn/apply.py` reads
  `verdict.get("domain_hint")` raw into `Plan.domains` with no coercion - confirmed
  by direct call to `apply()` with `domain_hint="purchasing"` (F3's own incident
  value), which survives straight through. Both are genuine engine regressions
  found by this triage, not fixture bugs - 3 of 5 ported tests RED for that reason,
  2 control tests (declared domain, ASCII hyphen) green. **Not the tester's fix to
  make** - flagged for the captain/coder. Original file retired (`git rm`), fully
  superseded by the port.

- **`test_ascii_digit_semantics.py` - RETIRE, not PORT (verdict revised from the
  original table's PORT).** Its whole premise (Python regex must match JS `\d`/`\b`
  semantics so a full-width digit does not get misread as a roster pick) no longer
  applies: `turn/apply.py` is explicitly forbidden from calling `re.` or reading
  `.text` at all (`test_rearch_s2_apply_is_pure.py::
  test_turn_package_never_calls_re_dot_or_reads_dot_text`, a grep guard) - digit/pick
  detection moved from Python regex-on-raw-text to the PARSER's own structured
  `answers_open_question`/`reference_positions` fields (any script, any language, no
  regex needed - D16, "the LLM does language, code does everything else"). Grepped
  the whole `app/services/chatbot/` tree for the file's own regex names
  (`_BARE_NUMBER_RE`, `_DIGITS_ONLY_RE`, `_ISO_DATE_RE`, `_SHORT_DATE_RE`,
  `_OPTION_ANY_RE`): none exist anywhere outside the deleted module. The replacement
  mechanism already has its own coverage: `test_rearch_s2_number_answers.py` (34
  tests, confirmed green this session) exercises "a number against a pending roster
  resolves through apply()" via the parser's structured fields. No equivalent seam
  to port to, by design, not by omission - retired, rule named here and in the
  commit body.

- **`test_r3_dual_read.py` - RETIRE, not PORT (verdict revised).** R3's whole
  purpose was bridging TWO in-flight representations of "an escalation offer is
  open" during the OLD engine's own migration: a frozen string match
  (`"would you like me to escalate"`) from before S2, and a `pending.kind ==
  "escalation_offer"` marker after it - both readable because the CRM and n8n wrote
  sessions at different moments during that migration. Grepped for `offer_is_open`
  and `escalation_offer` across `turn/` and `engine.py`: zero hits. The rearch's own
  `State`/`Pending` contract (`turn/state.py`, `turn/pending.py`,
  `_turn_helpers.PENDING_KINDS`) is now the SOLE source of truth for what is
  pending - an open escalation question is one of three real `Pending.kind` values
  (`team_pick`, `member_offer`, `company_pick`, all routed to `escalate_offer` by
  `turn/route.py::_ASK_BRANCH`), never a string or a migration-era marker to dual-
  read. Already covered by `test_rearch_s3_team_pick_and_866.py` (7/7 green per the
  prior session's handoff) and the S2 pending-state suite. Retired.
