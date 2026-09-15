# Console check - head 0e93dcea5

Backend `:8081` on the `chatbot-focus-l1-stack` worktree at `0e93dcea5` (R-K round 2, R-M,
S-1, S-2), its own venv and `.env` (DATABASE_URL -> `sorento_ai_automation_focus_full`).
Same procedure as `console-check-final-c95f811bb.md`: all 8 files at **v20**
`ca4e0348-e240-44a5-8947-a48fcdc9e1ca`, `2026-09-15-focus.yaml` again at **v15**
`7cbcf54f-0b88-47df-beac-8f40dd25fb74`, `--sleep-seconds 8`, every run graded by its own
`test_run_id`. Raw logs on this machine, `/tmp/console-final-0e93dcea5/*.log`, not
committed.

**The first `2026-09-15-focus.yaml` v20 run is discarded and re-run.** Five of its fifty
turns carry a non-null `chatbot.turns.error`, all
`Error code: 429 ... Rate limit reached for gpt-5.4-mini ... tokens per min (TPM)` - the
known console-check hazard, and the owner was on the same stack. Reading
`chatbot.turns.error` first is what tells a rate limit from a regression: the errored run
scored 8/9 and its three "new" failures (G, the stock clarifier, R-A) are exactly the cases
whose turns 429'd. Re-run at `--sleep-seconds 14`: **0 errors, 11/6, identical to the
c95f811bb run, same six cases.** Every other run in this pass has zero errored turns
(checked per run id).

## Counts per file

| File | c95f811bb | this run | delta |
|---|---|---|---|
| 2026-09-06.yaml | 13 / 5 | **13 / 5** | unchanged, same five cases |
| 2026-09-07-growth-r1.yaml | 22 / 7 | **21 / 8** | +1, and it is the (c) below |
| 2026-09-07-pass5-item1.yaml | 1 / 0 | **1 / 0** | unchanged |
| 2026-09-12-answer-polish.yaml | 4 / 0 | **4 / 0** | unchanged |
| 2026-09-12-last-cost.yaml | 1 / 3 | **1 / 3** | unchanged (the grant state, below) |
| 2026-09-13-outstanding-report.yaml | 3 / 1 | **3 / 1** | unchanged |
| 2026-09-14-outstanding-owner-rounds.yaml | 9 / 3 | **9 / 3** | same count, DIFFERENT cases |
| 2026-09-15-focus.yaml (v20, re-run) | 11 / 6 | **11 / 6** | unchanged, same six |
| 2026-09-15-focus.yaml (v15) | 14 / 3 | **13 / 4** | `F` newly fails |

## The three pick-then-report witnesses: two thirds green, and the rest is the prompt

The previous pass recorded ONE (c) defect with six live witnesses. Where they stand now:

| witness | file | c95f811bb | this run |
|---|---|---|---|
| R16 - picker answer keeps the outstanding ask | owner-rounds | FAIL | **PASS** |
| R19 - scope question header shows customer names | owner-rounds | FAIL | **PASS** |
| R20 - no DO hint on the customer picker | owner-rounds | FAIL | **PASS** |
| merge D - detail list renders on the first pick | focus | FAIL | FAIL |
| merge E - customer picker scopes the report | focus | FAIL | FAIL |
| R-B/R-F - chin chun DO outstanding, both ledgers | focus | FAIL | FAIL |

**Said plainly: three of the six are green, three are not.** The v15 run of the R-B/R-F
chain (a clean run, zero errored turns) shows exactly which half moved and which did not:

| turn | message | `_open_question_before` | what happened |
|---|---|---|---|
| `fe149bb0` | `DO outstanding for chin chun` | none | the customer picker, and the parser emitted `order_status: "outstanding"` - **bare**, at v15 as well as v20 |
| `7060b31d` | `1` | `customer_pick`, `pick_or_yes_no`, 4 rows | the pick resolved (six ledgers in the header) and the turn asked the scope question |
| `ac518e04` | `1` | **`outstanding_scope`, `pick`, 3 rows** | the scope question was PERSISTED and this "1" answered it: `order_status: so_outstanding`, `outstanding_answer_applied: true`, the SO report rendered |

Turn 3's `_open_question_before` is the fix landing: chain e's middle turn now persists the
question its own reply asked, and the next number resolves it. What keeps the three cases
red is the other half, which was already recorded in the previous evidence doc and is not
this lane's code: **"DO outstanding" parses as a bare `order_status: "outstanding"`**, so
the document type never reaches the report and the case's `Delivery order outstanding` /
`Reply 1 for the delivery order list.` / `*DO Number:*` assertions cannot be met. #862
pre-scopes only on `do_outstanding` / `so_outstanding` / `outstanding_both`. Both prompt
versions do it, so it is a PROMPT fix.

## Classification

### (c) NEW - one, and it is not in the dialogue engine

**A uuid and an ISO timestamp reach a customer-facing reply on the grouped order list.**
`2026-09-07-growth-r1.yaml` "A3 open DO grouped by customer renders headed sections"
("open DO by customer for C-FH14"), turn `39afe572-240f-4691-8e36-5d3b69a86dd9`, caught by
the case's own `no_uuid` guard. The row's `Status` field renders a whole status-history
record joined with " - " instead of the status label (from the turn's trace, the row's
`response` payload having been dropped by the 512 KB cap):

```
*Status:* DELIVERED - 6 - 2025-12-16T03:29:34.488097 -
86180603-e61b-4bad-9667-686ca0906aa6 - Order delivered to customer -
Picked Up / In Transit - true
```

The uuid matches no row in `customers` / `products` / `warehouses` / `companies` /
`transporters` / `suppliers`, which fits a status-history id. **Re-running that one case
did not reproduce it**, because the parse took a different path the second time (the same
sentence armed the outstanding scope question instead of the grouped list, and the leak
lives on the grouped-list path only) - so it is recorded with the turn id and the rendered
string rather than a reproduction recipe. It sits on the order-list field rendering, not on
anything this lane touched; the `no_uuid` guard is what makes it visible at all.

### (b) Pre-existing or prompt-side, not this round's code

**The three owner-rounds cases that changed sides (R15, R21, R21 guard).** All three trace
to the model volunteering a `reference_positions` for a WORD, which is the same class as
issue #933 and as the "another one" xfail on the test branch. Raw emissions:

| turn | message | raw emission | consequence |
|---|---|---|---|
| `b5079fd4` | `only BRW` | `entities: []`, `reference_positions: []` | BRW was not extracted AT ALL, so there is nothing to narrow with and the turn re-prints the question |
| `8ad772a7` | `all` | `entity_op: clear`, **`reference_positions: [3]`** | `_select_all_over_a_menu` is gated on "no volunteered position", so "all" was read as picking option 3 |
| `7a50fbef` | `all` | `entity_op: clear`, **`reference_positions: [3]`** | same, over the customer picker: one family instead of every family |

The gate is documented in `output_exchange._select_all_over_a_menu` ("a volunteered
position disables the expansion"), so a model that answers "all" with a number turns the
noise into a wrong answer. Worth hardening on the same ruling as #933 - the word "all" over
a menu could beat a single volunteered position - but it is not a regression of this round.
`a4323165` (an "all" turn in the R21 chain) came back with an EMPTY reply, which is a D13
concern of its own; flagged, not root-caused.

**Everything else is the previous pass's own (b) list, unchanged**: all five
`2026-09-06.yaml` cases; growth-r1 A1 / D8 / A3 / A6 x2 (and D10c is still an XPASS whose
`expected_red_until` marker is stale); focus `F` / `H` / `I` at v20, which pass at v15 and
are the prompt-shape difference the label move is for. `F` now fails at v15 too, on the
small-talk turn's wording ("You're welcome! Happy to help." did not come back) - LLM
wording variance on a clarifier reply, the same class the previous doc records for case H
turn 3.

### (a) Data prerequisite / access

Unchanged from the previous pass and re-confirmed: `last-cost` AC-32a / AC-32b / AC-32c and
growth-r1 A5 are the `purchase_orders.cost` and `purchase_orders.supplier` grants that
landed on 15 Sep 04:26 (the cases assert a DENIAL the DB no longer produces), and
`2026-09-13-outstanding-report.yaml`'s one failure is the journey case's pre-R22 wording.

## Turn ids referenced

| what | turn id |
|---|---|
| uuid in the grouped order list (c) | `39afe572-240f-4691-8e36-5d3b69a86dd9` |
| R15 turn 5 `only BRW`, no entity extracted | `b5079fd4` |
| R21 turn 2 `all` -> position 3 | `8ad772a7` |
| R21 guard `all` -> position 3 | `7a50fbef` |
| R21 chain `all` with an empty reply | `a4323165` |
| R-B/R-F chain at v15 (arm / pick / answer) | `fe149bb0` / `7060b31d` / `ac518e04` |

Run ids: 2026-09-06 `console-check-1789472784`, growth-r1 `console-check-1789473093`,
pass5-item1 `console-check-1789473462`, answer-polish `console-check-1789473473`,
last-cost `console-check-1789473516`, outstanding-report `console-check-1789473558`,
owner-rounds `console-check-1789473718`, focus v20 (discarded, 5 rate-limited)
`console-check-1789474056`, focus v15 `console-check-1789474694`, focus v20 re-run
`console-check-1789475344`, the single-case uuid recheck `console-check-1789476278`.

## Not run

`tests/chatbot/console_cases/2026-09-14-low-stock-report.yaml`, for the same reason as last
time: it belongs to the low-stock-report lane (#909) and has no baseline count here.
