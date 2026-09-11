# Test report - Attribute-first asks

Plan: `PLAN-attribute-first-asks.md`. UAC: `attribute-first-asks-acceptance-criteria.md`.
Branch `feat/chatbot-attribute-first-asks`. Lane backend on the restored prod copy
(`sorento_ai_automation`, dump 2026-09-10, migration 511), MCP on 8765, console contact 482766833
(promotion case: 438930735, which has access levels).

## Pytest (Phase 2, red first then green)

| Set | Result |
|-----|--------|
| `tests/test_product_spec_search.py`, `tests/test_product_predicate_service.py`, `tests/test_resolve_predicate.py`, `tests/test_migration_511_attribute_first_lookup_sets.py` | 118 passed |
| `tests/chatbot/test_lane_require.py` (S1 to S4 + two fix rounds) | 125 passed together with `test_product_spec_search.py` |
| Fix round 3 (R14 to R28): the five lane files + migration test together | 246 passed, 0 failed (commit 238adb4df, origin/main merged, 511 reparented) |
| `tests/chatbot` full after fix round 3 | 1663 passed, 72 skipped, 5 xfailed, 5 failed (the same `test_s7_*` baseline) |

The 5 failures are `test_s7_dispatch_edges.py` (3) and `test_s7_ordering_and_offload.py` (2): the
Redis-outage turns die at `route.py:224` (`is_stock_check_denied`, a None settings row), a line
this lane never touched. Reproduced on a clean `main` checkout with the same venv: see the
"Baseline" line below.

Baseline (main, detached checkout of d6cb5b624 with the lane venv, 11 Sep 2026): the same five tests fail, `5 failed, 21 passed` on those two files. Not this lane.

## AC status

| AC | Status | Evidence |
|----|--------|----------|
| 1301, 1302 | PASS | pytest, honest zero |
| 1303 | PASS | pytest, `derive_require` parametrize incl. scheme split and cert word from message |
| 1304 | PASS | pytest, body diff |
| 1305 | PASS | pytest, AND-mode code-shaped gate; console "check stock srtwc286" answers the forward block with no header |
| 1306 | PASS | pytest, class word scopes; console "which sink has incoming" → 47 kitchen sinks (was 620 products) |
| 1307, 1308 | PASS | pytest |
| 1309 | PASS | pytest shape lock |
| 1310 | PASS | pytest, five legs incl. incoming |
| 1311 | PASS | pytest; console "which sink has incoming" → 47 |
| 1312 | PASS | pytest, alias set; console "which basin has photo" clarifies as a document type (alias set empty by design, owner enters options) |
| 1313 | PASS | pytest, register spelling then set; console "which item has PPS cert" → 940 |
| 1314 | PASS | migration test, empty sets created on the prod copy |
| 1315 | PASS | pytest, first five ids and no row limit; console pages show 5 distinct products |
| 1316 | PASS | pytest; console "which tap has cert" → "908 taps have certificates. Showing 5.", "which item has PPS cert" → "940 products have PPS certificates. Showing 5." |
| 1317 | PASS | pytest (S4); console "which tap has cert" / "more" / "more" → Showing 5, 6 to 10, 11 to 15 |
| 1318 | PASS | pytest, expired-only counted and flagged |
| 1319 | PASS | pytest, miss names the set and the codes checked |
| 1320 | PASS | pytest; console "which water tap has cert" → "I don't know 'water tap' as a product type. Did you mean tap?" |
| 1321 | PASS | pytest, scheme miss names schemes on file |
| 1322 | PASS | body byte-identical without a leg intent; forward turns unchanged in the suite |
| 1323 | PASS | pytest, dealer stock parity |
| 1324 | PASS | `git diff --stat main..HEAD` touches neither `chatbot_parser_prompt.py`, `ai_prompt_registry.py` nor `sorento_crm_mcp/` |
| 1325 | PASS with notes | console pass 2 below |
| 1326, 1327 | PASS | pytest; console "which sorento bidet has cert" → "1 tap has certificates." plus the block for SRTWT5875 (a Sorento product whose product_type is bidet), no picker |
| 1328 | PASS | pytest; console PPS case |
| 1329 | PASS | console "which basin has photo" → "Types I know: Certification, Product Photos, Product Videos, Technical Specifications." (product-facing only) |
| 1330 | PASS | pytest; console sink case |
| 1331 | PASS | pytest (green on arrival: the AC-1326 bypass already covers the folded token); the pass-3 console miss for this utterance was a reload race, see below |
| 1332 | PASS | pytest, model reader never invoked on a HAS turn; phrase stripping green |
| 1333 | PASS | pytest (parity probe); console pass 6 trace: the promotion pick armed the carry and the "more" page's tool args carried `access_levels: ["Sorento Dealer", "Mocha Dealer", "Cabana Dealer"]` |
| 1334, 1342 | PASS | pytest; `_access_level_codes` accepts codes and bare tier tokens (the pick turn carried "Dealer") |
| 1335 | PASS | pytest, two-company scratch schema; security re-check closed S2 |
| 1336, 1343 | PASS | pytest, same-domain non-page answer and same-domain zero clarify both clear the carry; console pass 7 sequence 2: "more" after the clarify is not paged |
| 1337 | PASS with note | fixed paging phrases; "no more" declines but leaves the carry until the next business turn clears it |
| 1338 | PASS | pytest (register spelling, lookup keyword, regression); console "which item has PPS cert" -> "940 products have PPS certificates." on the head variant that drops PPS before the lane |
| 1339 | PASS | pytest; console "which bathroom accessory has stock" -> 837 (was a silent 0: every one of the 2,040 rows is category-sourced) |
| 1340 | PASS | pytest, category raw and "any product" fallbacks; no "a a match" |
| 1341 | PASS | pytest both directions plus the NULL shared arm; security re-check kill test |
| 1344 | PASS | dash scan of every lane file empty; pre-push guard |
| 1345 | PASS | pytest, seven inflections incl. "sijil" and "PPS certification" |
| 1346 | PASS | pytest; console pass 7 bathroom accessory "Showing 5." for five ids (pass 6 showed 4: ACC-SRT9012's only stock was in inactive warehouse SPARE/P) |
| 1348 | PASS | pytest, `["%"]`, `["%dealer"]`, `["d%r"]` select nothing (security re-check measured `["%"]` selecting seven codes before R24) |
| 1349 | PASS | pytest, `resolve_entity_body(tier_gate=...)` sends the recomposed names; single-tier contacts no longer count promotions of other tiers |
| 1350 | PASS | pytest, page-arm guard kill-tested by the tester; migration test asserts the chain, green after the reparent |
| 1351, 1352 | PASS | pytest (bound words leave the scope term; string bindings filter, numeric stay boosts); console "check stock water closet with s trap 250mm" -> "165 water closets have stock. Showing 5." and "any incoming for water closet with p trap" -> "13 water closets have incoming stock." (both clarified "water closet trap" before R27: a regression of the forward spec path found by the owner) |
| 1353 | PASS | pytest; console run 11 "which item has PPS cert" on the variant where the head drops the raw-"PPS" entity -> "940 products have PPS certificates." (run 10 answered the forward "Please provide the attachment type") |
| 1347 | PASS | pytest, four paging terms; console pass 8 sequence 2: the carry-less "more" answers "2,704 products have certificates. Showing 5." (the reused certificate question, unscoped) instead of "I don't know 'more'" |

## Console pass 7 (AC-1325, FINAL after fix round 3), lane backend WITHOUT reload, commit d331bec78

| Utterance | Reply first line |
|-----------|------------------|
| check stock srtwc286 | Stock details found for the requested products. (forward path, no header) |
| which water tap has cert | I don't know 'water tap' as a product type. Did you mean tap? |
| which tap has cert | 1,256 taps have certificates. Showing 5. (908 before R15: category-filed taps now count) |
| which sorento bidet has cert | 1 tap has certificates. (SRTWT5875) |
| which basin got stock | 539 wash basins have stock. Showing 5. (active warehouses only, R22) |
| which item has PPS cert | 940 products have PPS certificates. Showing 5. |
| which basin has photo | I don't know 'photo' as a document type. Types I know: Certification, Product Photos, Product Videos, Technical Specifications. |
| which sink has incoming | 52 kitchen sinks have incoming stock. Showing 5. |
| which bathroom accessory has stock | 837 bathroom accessories have stock. Showing 5. (pass 5: "Couldn't find a a match with stock.") |
| any shower set on promo (contact 438930735) | Which access level do you need for shower set? |

Multi-turn sequences (`pass6-sequences.yaml` in the session scratchpad, three cases):

| Sequence | Result |
|----------|--------|
| which tap has cert / more / more | Showing 5. / Showing 6 to 10. / Showing 11 to 15. (AC-1317) |
| which tap has cert / which water tap has cert / more | set answer / clarify / NOT paged (AC-1343). The third reply on d331bec78 read "I don't know 'more' as a product type": the head's entity reuse re-asked the certificate question with "more" as the only remainder word (R23). Rerun on 242af5589 (console pass 8, all three sequences PASS): "2,704 products have certificates. Showing 5." |
| any shower set on promo / 1 / more | tier ask / "I found 4 promotions for shower set." on the check_promotion lane with `access_levels: ["Dealer"]` / page with the recomposed tiers in the tool args (AC-1333). Promotion sets page by product, so a promotion file attached to several products appears on both pages; accepted |

Console pass 9 (final, commit 2a4112354 with origin/main merged): the same ten utterances and three sequences, identical replies to pass 7/8 (`console-run-9.txt`, `console-run-9-sequences.txt`).

Transcripts: `console-run-7.txt`, `console-run-7-sequences.txt`, `console-run-8-sequences.txt`, `console-run-9*.txt` in the session scratchpad.

## Console runs 10 and 11: the committed case file (owner test round, R27 and R28)

`tests/chatbot/console_cases/2026-09-11-attribute-first-asks.yaml` (14 cases: the ten utterances, the two spec-word turns, the three sequences) run with `scripts/chatbot_console_check.py` against the lane backend on the prod copy. Run 10 (commit e678723fb, R27 in): 13 passed, 1 failed: "which item has PPS cert" answered the forward attachment-type ask on a parser variant the head empties (R28). Run 11 (commit 238adb4df): 14 passed, 0 failed. Transcripts `console-run-10.txt`, `console-run-11.txt` in the session scratchpad.

Owner observations on the local stack that are DATA or configuration, not lane defects (plan row above the R27 table): "sorento bidet" is filed under category Tap (header noun), "water tap" and "valve" are missing category search synonyms, certificate PC 000373 (WCM Cold Tap) is linked to three Mocha kitchen sinks. Follow-up slice candidates: header echoes the customer's product_type word; the attachments listing filters by the recovered scheme.

## Console pass 4 (AC-1325, FINAL), lane backend started WITHOUT reload, commit 677d240b1

| Utterance | Reply first line |
|-----------|------------------|
| check stock srtwc286 | Stock details found for the requested products. (forward path, no header) |
| which water tap has cert | I don't know 'water tap' as a product type. Did you mean tap? |
| which tap has cert | 908 taps have certificates. Showing 5. |
| which sorento bidet has cert | 1 tap has certificates. (SRTWT5875, block with its WCM certificate file) |
| which basin got stock | 427 wash basins have stock. Showing 5. |
| which item has PPS cert | 940 products have PPS certificates. Showing 5. |
| which basin has photo | I don't know 'photo' as a document type. Types I know: Certification, Product Photos, Product Videos, Technical Specifications. |
| which sink has incoming | 47 kitchen sinks have incoming stock. Showing 5. |
| any shower set on promo (contact 438930735) | Which access level do you need for shower set? (existing promotion flow) |
| which tap has cert / more / more | Showing 5. / Showing 6 to 10. / Showing 11 to 15. |

Every page rendered five distinct products. Full transcript in the session scratchpad `console-run-4.txt`.

## Console pass 2 (AC-1325), lane backend, dry-run turns

| Utterance | Reply first line | Verdict |
|-----------|------------------|---------|
| check stock srtwc286 | Stock details found for the requested products. | forward path kept |
| which water tap has cert | I don't know 'water tap' as a product type. Did you mean tap? | clarify |
| which tap has cert | 908 taps have certificates. Showing 5. | set answer with files |
| which sorento bidet has cert | 1 tap has certificates. (SRTWT5875) | set answer; noun could read "Sorento bidet", accepted |
| which basin got stock | 427 wash basins have stock. Showing 5. | set answer |
| which item has PPS cert | 940 products have certificates. Showing 5. | correct set; header to gain "PPS" (polish) |
| which basin has photo | I don't know 'photo' as a document type. Types I know: ... | clarify; list to be product-facing only (polish) |
| which sink has incoming | 47 kitchen sinks have incoming stock. Showing 5. | set answer |
| any shower set on promo (contact 438930735) | Which access level do you need for shower set? 1. Dealer - has promotion | the promotion domain keeps its existing access-level flow |
| more, more (after the tap answer) | Showing 6 to 10. / Showing 11 to 15. | paging |

Pass 3 (after the polish commit) showed two regressions. "which sorento bidet has cert" (single
product entity variant) answered the miss copy once: its stored trace has NO fetch stage, while
three identical turns run afterwards on the same code all fetched and answered "1 tap has
certificates." The turn ran while uvicorn was reloading the polish commit; the final pass runs on a
backend started without reload. "which item has PPS cert" (attachment raw "PPS cert" variant)
answered "I don't know 'item pps'": the model phrase reader was invoked on the set path (R13,
AC-1332), fixed by the coder.

The parser emits different entities for the same sentence between runs (category vs product hint,
"PPS" vs "PPS cert", one entity "Sorento bidet" vs brand + category). The lane handles every
variant seen; the variants are listed under R2, R3, R4, R7, R12, R13 in the plan.

Pass 1 (before fix round 2) had five wrong turns; all are recorded with cause and rule in the plan
section "Console fix round 2".

## Latency (REV-N3)

`resolve_reference_post` for "which tap has cert" on the prod copy (908 qualifying families, 200
candidates emitted), three consecutive in-process calls: 203 ms, 91 ms, 133 ms. The model phrase
reader is off on the set path, so the resolve is SQL only.

## Review rounds

Fix round 3 re-check (11 Sep): security-reviewer closed B1 and S2, raised the certificate leg (R17, blocker) and the tier-token mismatch (R18); reviewer closed B1 and S4, found the same-domain carry gap (R19) and the certificate leg (N1). All adopted, red test first. Round 3 re-check verdicts (11 Sep, at d331bec78): security-reviewer closed the certificate blocker (all five legs 0 on a foreign child, 1 on an own child, shared NULL arm counts), R14 has no cross-company scheme oracle, R22 only narrows; open should-fix R25 (single-tier contacts) and nit R24 (LIKE wildcard), both fixed in 721d6313d / 2a4112354 with red tests first. Reviewer: R19 kill test bites (1 failed / 88 passed on revert), R17 both arms pinned (strict equality fails 16 tests), R15 has one caller and the AC-1308 repair still proves the union, R14 order of operations verified, R18 LIKE escaping (R24), R22 keeps the four scope tests meaningful. Verdict from both: ready.

Security review (11 Sep): one blocker (paging a promotion set dropped the tier filter), two
should-fix (promotion leg blind to access levels; class-label helpers cross-company). Correctness
review (11 Sep): one blocker (the legs' EXISTS subqueries escape the company listener; the AC-1310
tests could not see it), six should-fix. All adopted as rules in the plan (SEC-*, REV-*), each with a
red test before the fix. Repo-wide audit of the EXISTS pattern filed as #832.

## Deviations

- Phase 1 skipped by design: no UI surface. The lavish review page stands in for the mock.
- Console verification on the prod copy needed a minted integration key that is ALSO the `.env`
  `EXTERNAL_API_KEY` (scope resolver drift, issue #831, outside this lane).
- Alias and scheme lookup sets are created empty; the owner enters options on System > Lookup Sets.
