# Console check - final pass, head c95f811bb

Backend `:8081` on the `chatbot-focus-l1-stack` worktree, commit `c95f811bb`
(`feat/chatbot-focus` with the general-rule round and the tester's branch merged in), its
own `venv`, its own `.env` (DATABASE_URL -> `sorento_ai_automation_focus_full`, the DB
every lane-1 evidence run has been graded against). Ran from
`chatbot-focus-l1-stack/sorento_crm_backend` as

```
venv/bin/python scripts/chatbot_console_check.py <file> \
  --base-url http://127.0.0.1:8081 --prompt-version <id> --sleep-seconds 8
```

Two prompt-version pins, the whole set at the first and `2026-09-15-focus.yaml` twice:

- **v20** `ca4e0348-e240-44a5-8947-a48fcdc9e1ca` - main's promoted SLIM text, what
  production runs today.
- **v15** `7cbcf54f-0b88-47df-beac-8f40dd25fb74` - `chatbot_semantic_parser@15`, this
  lane's own unpromoted parser v3.

Every run graded by its own `test_run_id` (printed on each log's header line), never a
timestamp window, because the same contact `437264483` is shared with the owner and with
other diagnostic sessions. **Zero turns in any of the 9 runs carry a non-null
`chatbot.turns.error`** (checked per run id). Raw logs on this machine,
`/tmp/console-final-c95f811bb/*.log`, not committed.

## Counts per file, against the merged-head baseline

Baseline column: `console-check-merged-d4ae8203b.md`, same 8 files, same two pins.

| File | baseline v20 | this run v20 | delta |
|---|---|---|---|
| 2026-09-06.yaml | 13 / 5 | **13 / 5** | unchanged, same five cases |
| 2026-09-07-growth-r1.yaml | 23 / 6 | **22 / 7** | see (a): one case flipped by a GRANT, one XPASS |
| 2026-09-07-pass5-item1.yaml | 1 / 0 | **1 / 0** | unchanged |
| 2026-09-12-answer-polish.yaml | 4 / 0 | **4 / 0** | unchanged |
| 2026-09-12-last-cost.yaml | 2 / 2 | **1 / 3** | (a): `purchase_orders.cost` is now granted |
| 2026-09-13-outstanding-report.yaml | 1 / 3 | **3 / 1** | +2 |
| 2026-09-14-outstanding-owner-rounds.yaml | 2 / 10 | **9 / 3** | +7, the SO grant landed |
| 2026-09-15-focus.yaml | 7 / 5 (12 cases) | **11 / 6 (17 cases)** | +4 pass; 5 cases are new (R-A to R-E) |
| 2026-09-15-focus.yaml at **v15** | 9 / 3 (12 cases) | **14 / 3 (17 cases)** | +5 pass, same 3 fails |

**Totals: 34 v20 failures across 8 files (identical headline number to the baseline, a
different composition), 3 at v15.** Every one is classified below.

## The data state moved under this run, and it explains four of the deltas

`contact_field_reveals` for contact `437264483` (queried on the run's own DB):

| field_key | granted | created_at |
|---|---|---|
| `inventory.sellable` | true | 2026-09-07 16:17 |
| `purchase_orders.placed` | true | 2026-09-08 03:07 |
| `purchase_orders.cost` | true | **2026-09-15 04:26** |
| `purchase_orders.supplier` | true | **2026-09-15 04:26** |
| `sales_orders.outstanding` | true | **2026-09-15 14:10** |

Three of those five were granted AFTER the baseline run, and they account for:

- **`2026-09-14-outstanding-owner-rounds.yaml` 2/10 -> 9/3.** The baseline classified all
  ten failures as (a) "contact Jayson lacks the sales-order key". The key landed today at
  14:10, and nine of the ten now pass with no code change on that path. The baseline's
  classification was right and is now confirmed from the other side.
- **`2026-09-12-last-cost.yaml` AC-32a flipping pass -> fail.** The case asserts the
  DEFAULT contact is DENIED (`'Sorry, you are not allowed to access purchase cost'`); with
  `purchase_orders.cost` granted at 04:26 the reply is the cost answer, so the case is now
  asserting a state the DB no longer holds. AC-32b / AC-32c fail on row selection rather
  than on the denial they failed on at the baseline - same cause, different surface.
- **`2026-09-07-growth-r1.yaml` A5 "PO for a product, and no supplier for a dealer".**
  Fails with `reply contains 'Supplier' and must not`; `purchase_orders.supplier` was
  granted at 04:26. Not a defect, the dealer now holds the reveal the case was written to
  prove is withheld.

None of the three is this lane's to fix. Either the grants come off the console contact or
those three cases are re-pointed at a contact without them; the case files say what they
assert, and the DB now disagrees with them.

## Classification

### (a) Data prerequisite / access

- `2026-09-12-last-cost.yaml` AC-32a, AC-32b, AC-32c (3) and `2026-09-07-growth-r1.yaml`
  A5 (1) - the grant table above.
- `2026-09-13-outstanding-report.yaml`'s one remaining failure, the six-turn journey case:
  turn 1 and turn 3 do not carry `1. Sales order list` / `2. Delivery order list`. The
  reply IS the report with its own header and the `Reply 1 for ...` offer line; this case
  predates R22's re-wording of the detail offer (it was written against the numbered list
  the lane printed in #862's first cut). Case-file wording, not behaviour: its three
  siblings in the same file (D17, R12, R13) all pass, and the numbered detail list renders
  correctly in `2026-09-14-outstanding-owner-rounds.yaml` R23.

### (b) Pre-existing, not this lane's regression

- **All five `2026-09-06.yaml` failures**, byte-for-byte the same cases as the baseline
  (MSK11A-QT's no-stock line, the `[A/C I]` leak on the not-found line, the roster
  swallowing a bare product code, the team-word escalate, the filter reply under an open
  roster). This file is dated 6 Sep and predates the lane branch point.
- **`2026-09-07-growth-r1.yaml` A1 (spec scoping), A6 x2 ("Quantity Received" naming)** -
  the same three the baseline reports.
- **`2026-09-07-growth-r1.yaml` D8 and A3** - both now reply with the ambiguous-customer
  picker (`Which customer do you mean?`) where the cases expect the orders list with SO
  blocks. The baseline reports both as failing too, under the coarser heading "SO/DO block
  field lists", and the baseline's raw logs were not committed, so the failure REASON
  cannot be diffed. What can be checked, and was: the picker's own condition
  (`gate.py`, `if not pick_applied and not cust_pinned and len(bases) > 1`) is
  **byte-identical between `d4ae8203b` and this head** (`git diff` on that hunk is empty),
  so the picker is not something this round started doing. Flagged rather than silently
  carried: if the owner wants "how many did all customers take of X" to fan out over every
  account instead of asking, that is a product decision about `len(bases) > 1`, not a
  regression to repair.
- **`2026-09-07-growth-r1.yaml` D10c is an XPASS**, not a failure: the case carries
  `expected_red_until` and now passes ("a product-set collision beside a resolved
  attachment type still gets its DYM", turn `c91db3bf`). The harness counts an XPASS in
  the failure total, which is the whole of growth-r1's 6 -> 7. The marker is stale and
  should come off the case.
- **`2026-09-15-focus.yaml` F, H, I at v20, all three PASS at v15** - the same shape the
  baseline documents for A / H / I / stock-clarifier: a bare digit or a casual turn fed to
  the shared deterministic engine behaves correctly under this lane's own parser shape and
  not under v20's. Two of the baseline's four (A, stock-clarifier) now pass at v20 as well;
  F joins the set (its turn 3 answers a stock miss where the case expects the small-talk
  acknowledgement). v20 is what production runs today and v15 is this lane's deliverable -
  the two-run difference is the reason the label moves, as the baseline says.

### (c) NEW - one defect, six live witnesses, on BOTH prompts

**The outstanding report does not survive a customer pick.** Six cases across two files
fail on it, and unlike everything in (b) they fail under v15 as well as v20, so no prompt
version hides it:

| case | file | what the turn does |
|---|---|---|
| R16 - picker answer keeps the outstanding ask | owner-rounds | turn 3: `That would search every delivery order we have - I need at least one filter to narrow it down.` |
| R19 - scope question header shows customer names | owner-rounds | turn 3: no `Sales order outstanding` / `Delivery order outstanding` block at all |
| R20 - no DO hint on the customer picker | owner-rounds | turn 3: no `Delivery order outstanding`, no `Outstanding: 5` |
| merge D - detail list renders on the first pick | focus | turn 1 has no `Reply 1 for the delivery order list.`; turn 2 has no rows |
| merge E - customer picker scopes the report | focus | turn 2 has no `Delivery order outstanding` |
| R-B/R-F - chin chun DO outstanding, both ledgers | focus | turn 2 has no report and no offer line; turn 3 has no `*DO Number:*` |

The trio for the last one, live, v15 `f79ea010` -> `2dae16f0` -> `6d93581b` and v20
`293f219e` -> `d7e1e8d7` -> `8ca1ef42` (the same three turns in both runs):

1. `DO outstanding for chin chun` -> the customer picker, three rows. Correct.
2. `1` -> the six-ledger scope header AND `Outstanding for which document?`. The document
   type the customer named in turn 1 is gone.
3. `1` -> **the identical reply again**. The number answered nothing.

Both turns 2 and 3 carry the same emission, and it names both halves of the cause:

```
message_type business_query   domain_hint order   order_status "outstanding"
entity_op "replace"   reference_positions []   open_question_answered "customer_pick"
```

- `order_status: "outstanding"` for a message that said **DO** - the parser gap. #862
  pre-scopes only on `do_outstanding` / `so_outstanding` / `outstanding_both`, so a bare
  `outstanding` arms the scope question the customer had already answered. Both prompt
  versions do this, so it is a PROMPT fix, not a lane one.
- `reference_positions: []` on turn 3 - the bare "1" never reached the engine as a
  position, so nothing could resolve the scope question; and `open_question_answered:
  "customer_pick"` says the turn was read as answering the CUSTOMER roster again, which is
  chain e's own symptom (the pick turn persists `customer_pick` even though its reply asked
  the scope question).

Both halves are pinned as reds on `test/chatbot-focus-red` (`c60f8d46f`,
`tests/chatbot/test_general_rules_15sep.py` group 5): the pre-scoping guard over
`do_outstanding` / `so_outstanding` / `outstanding_both` with and without a picker in
between, and "when a turn both answers and asks, the ask wins" over two question kinds and
four answer channels - 23 of those cases are red on this head, and
`TestTheQuestionAPickTurnAsksIsTheOneThatPersists` reproduces turn 2 exactly (reply asks
the scope question, persisted question comes back `customer_pick`).

No other failure in this run is unexplained by (a), (b) or (c).

## v15-only findings

v15's three failures are exactly the three (c) cases above (merge D, merge E, R-B/R-F) -
nothing is v15-specific this time. The baseline's two v15-only findings were
test-authoring bugs (a typographic apostrophe in `2026-09-15-focus.yaml`'s assertions);
both are fixed in the case file, and F / H / I now pass at v15 with the typographic quote
matched.

## What passes that did not at the baseline

Worth stating plainly, since the point of the pass is to know what moved:

- The whole R-A / R-C / R-D / R-E set of owner merge-test cases passes at both pins: the
  offer rides a roster born the same turn and a `yes` reaches the WAREHOUSE team
  (R-A), a product pick keeps the attachment type the same message named (R-C), the
  customer pick keeps the co-resolved product (R-D), and the header names the company
  rather than the debtor code (R-E).
- `2026-09-14-outstanding-owner-rounds.yaml` R15, R19b, R21 x2, R22a, R22b, R23, R24 - nine
  of twelve, where the baseline had two.
- `2026-09-15-focus.yaml` A and the stock clarifier now pass at v20 as well as v15.

## Turn ids referenced

| case / turn | v20 | v15 |
|---|---|---|
| R-B/R-F turn 1 (`DO outstanding for chin chun`) | `293f219e-313b-4e51-afd0-06eb4084a12d` | `f79ea010-4f0c-4b68-9949-40583d3474ea` |
| R-B/R-F turn 2 (`1`) | `d7e1e8d7-ded8-4cd7-a58f-7eb27054dd0b` | `2dae16f0-d2ff-47d2-8202-17b695f78385` |
| R-B/R-F turn 3 (`1`) | `8ca1ef42-204d-4281-b433-d1de222a7b5d` | `6d93581b-c8b0-4e47-84ea-a38dcab515d5` |
| R-D turn 1 / turn 2 (`delivery for chin chun product wc286`, `1`) | `427cdd1e` / `137b6c3d` | `fe747609` / `83698d52` |
| growth-r1 D10c (the XPASS) | `c91db3bf-6fb9-48f2-b004-4c134687f788` | - |

Run ids: 2026-09-06 `console-check-1789461730`, growth-r1 `console-check-1789462029`,
pass5-item1 `console-check-1789462415`, answer-polish `console-check-1789462426`,
last-cost `console-check-1789462469`, outstanding-report `console-check-1789462511`,
owner-rounds `console-check-1789462671`, focus v20 `console-check-1789463024`, focus v15
`console-check-1789463594`.

## Not run

`tests/chatbot/console_cases/2026-09-14-low-stock-report.yaml` exists in the directory and
is NOT part of this pass or of the baseline's eight - it belongs to the low-stock-report
lane (#909) and has no baseline count here to compare against. Said out loud rather than
left as a silent omission.
