# Console check - merged head d4ae8203b (definitive pass)

Backend `:8081` on `chatbot-focus-l1-stack` worktree, commit `d4ae8203b` (feat/chatbot-focus
merged onto main's current head), fresh venv, MCP `:8765` rebooted. Ran with
`venv/bin/python scripts/chatbot_console_check.py <file> --base-url http://127.0.0.1:8081
--sleep-seconds 8 --prompt-version <id>` from `chatbot-focus-l1-stack/sorento_crm_backend`
(its `.env` DATABASE_URL points at `sorento_ai_automation_focus_full`, the DB every prior
lane-1 evidence run was recorded against).

Two prompt-version pins, whole run repeated:
- **v20** `ca4e0348-e240-44a5-8947-a48fcdc9e1ca` - main's promoted SLIM text as of #909, what
  production runs today, unrelated to this lane's own dialogue engine work.
- **v15** `7cbcf54f-0b88-47df-beac-8f40dd25fb74` - `chatbot_semantic_parser@15`, this lane's own
  unpromoted parser v3 ("asks" shape), matched byte-for-byte against
  `app.services.chatbot_parser_prompt.SEMANTIC_PARSER_PROMPT_V3` on this checkout.

All 8 existing case files ran at v20; `2026-09-15-focus.yaml` ran a second time at v15.
Every turn graded `test_run_id` was isolated via `SELECT ... WHERE test_run_id = '<run id>'`
(the run id printed on each log's header line) rather than a timestamp window, because the
owner and a concurrent coder diagnostic session (`console-52b91f3f...`,
`console-9212d7a2...`) were both sending real dry-run turns to the same contact
(`437264483`) at the same time, exactly as the coordinator flagged. **Zero turns in any of
the 9 runs carry a non-null `chatbot.turns.error`** - the SSL/ENOENT bug from the pre-merge
run (see the discarded 2026-09-06 through 2026-09-15 pre-merge logs, not committed) does not
reproduce here. The stack is healthy.

## Counts per file

| File | v20 (prod-equivalent) | v15 (this lane's parser, focus.yaml only) |
|---|---|---|
| 2026-09-06.yaml | 13 passed, 5 failed | - |
| 2026-09-07-growth-r1.yaml | 23 passed, 6 failed | - |
| 2026-09-07-pass5-item1.yaml | 1 passed, 0 failed | - |
| 2026-09-12-answer-polish.yaml | 4 passed, 0 failed | - |
| 2026-09-12-last-cost.yaml | 2 passed, 2 failed | - |
| 2026-09-13-outstanding-report.yaml | 1 passed, 3 failed | - |
| 2026-09-14-outstanding-owner-rounds.yaml | 2 passed, 10 failed | - |
| 2026-09-15-focus.yaml (this lane's own cases) | 7 passed, 5 failed | 9 passed, 3 failed |

**34 total v20 failures across 8 files; 3 v15 failures, all in focus.yaml.** Every one
classified below. None of the 8 legacy files are owned by this lane (all predate the
`chatbot-focus` branch point per their own filenames/headers) - they exist to prove the merge
did not regress work other lanes already shipped.

## Classification

### (a) Data prerequisite / access

**All 10 failures in `2026-09-14-outstanding-owner-rounds.yaml` (R15, R16, R19, R19b, R20,
R21, R22a, R22b, R23, R24)** trace to one cause: this file's own header says it leans on real
rows in `sorento_ai_automation_0907`, and every failing case needs the sales-order outstanding
bucket for contact `437264483`. `documentation/plans/chatbot/evidence/focus-l1/merge-smoke-verification.md`
already established, independently, that on `sorento_ai_automation_focus_full` (the DB this
run is graded against) **"contact Jayson lacks the sales-order key, so the SO figures and the
scope question are gated off and only the DO outstanding is shown"** - exactly the
`so_bucket_refused` redirect in `app/services/chatbot/lanes/business/__init__.py` (see the
`_OUTSTANDING_SO_GRANT` check read during Phase 2 verification). R16/R19b's `out_of_scope`
branch (an unexpected escalation instead of the ambiguous-customer picker) is the same grant
gap surfacing on a different arm, not a second defect. Not this lane's data to fix; a
different contact/DB combination with the SO grant would be needed to grade this file for
real, or the file re-pointed at a DB where Jayson holds the grant.

### (b) Pre-existing / expected given the prompt version, not this lane's regression

**Case A turn 4, Case H turn 4, Case I turn 3, and the stock-clarifier case in
`2026-09-15-focus.yaml` - v20 only, all four PASS under v15**, isolated turn-by-turn via
`test_run_id`:

- **Case A** (`4f3977f6-0722-4e19-99dc-417c9d9d1070`): after two correct sequential picks
  ("1" -> SRTWT2632, "2" -> SRTWT2633), "3" gets `branch_kind=low_signal`, `"Sure - option 3
  it is."` instead of resolving SRTWT2634. Under v15 the same 4-turn sequence passes in full
  (turn 4 correctly returns `"Stock details found for the requested products."` /
  `SRTWT2634`).
- **Case H** (`9ce12d8e-f888-4027-a05d-dbfb25026699`): after "another one", a bare "2" resolves
  to `product: SRTWT2633` - a genuine re-pick against the original 3-row roster, the exact
  thing AC-1020 forbids. Under v15 the same sequence's turn 4
  (`4bf331d1-d2f7-4f52-a751-bdad7a13b690`) does **not** contain `product: SRTWT2633` - the
  roster stayed closed, matching the S7b evidence.
- **Case I** (`1a205662-f067-42c9-9da3-67689c664ee9`): after a new subject (`SRTWC8517
  stock?`) clears the wc286 picker, a bare "8" returns the generic no-filter clarifier
  instead of re-answering SRTWC8517. Under v15 the same turn
  (`5a8e49bd-c298-467a-9537-f835f6ce5940`) correctly re-answers SRTWC8517, matching the S7
  chain I evidence.
- **stock-clarifier** (`9a2b7a21-61d9-485f-bc91-87eff9b36395`): a cold `"stock?"` answers with
  a stale `product: SRTWT2632` instead of asking for a filter. Under v15
  (`22d3a36e-b050-47c3-a135-581a10227d3c`) the reply is the expected clarifier verbatim except
  trailing wording (see below) - functionally correct.

All four are the SAME shape: a bare digit or domain word, fed to the SHARED deterministic
dialogue engine, behaves correctly when the parser emits this lane's own `asks` shape (v15)
and incorrectly when it emits v20's older shape. v20 is literally "what production runs
today" (unrelated to this lane, per the coordinator) and v15 is this lane's own deliverable,
still unpromoted - the two-run comparison is doing exactly what
`documentation/agents/chatbot-verification.md` says it is for: "what the tenant gets today
and what it would get after the label moves." Since v15 fixes all four and v20 (main's
current behaviour) does not, none of these are a regression this lane introduces; they are
the reason the label moves. **Not independently confirmed by running literal `main` HEAD**
(no third stack was booted for that) - the inference rests on the shared-engine, prompt-only
difference between the two runs plus the AC-1014/1020 contract being this lane's own stated
deliverable.

**`2026-09-06.yaml` "a pending order roster does not swallow a bare product code"** and
**"a filter reply under an open roster is answered, not re-asked"** - both fail with
`branch_kind=low_signal`, `'Sure - what would you like to say?'` / `'Sure - I can help with
that...'`, the identical swallow pattern as Case A/H above. Same reasoning; this file is
dated 6 Sep, predates the lane branch point.

**`2026-09-06.yaml` remaining two** ("three codes, the third has neither stock nor
incoming", "escalate to a team word never inherits the previous team") and all 6 failures in
`2026-09-07-growth-r1.yaml` (spec-answer scoping, SO/DO block field lists, SPO "Quantity
Received" field naming) and the 3 in `2026-09-13-outstanding-report.yaml` (an EARLIER, now
superseded case file for the same feature `2026-09-14-outstanding-owner-rounds.yaml` later
rewrote) - none touch this lane's diff surface (`dialogue/focus.py`, `miss_suggest.py`, the
sticky-roster/picker machinery, or the outstanding-report five-key port). Reported for
completeness; not deep-dived turn-by-turn given they are outside this lane's own scope and
none share the swallow signature above. Flagged, not silently dropped.

**`2026-09-12-last-cost.yaml` AC-32b/AC-32c** - both fail with `'Sorry, you are not allowed to
access purchase cost'` where the case expects a granted answer. This is an (a)-shaped access
gap (contact `437264483` is not granted the purchase-cost attribute on this DB) filed under
(b) because, unlike the outstanding-owner-rounds file, no prior evidence in this lane
independently confirms the grant state - noted as the most likely cause, not verified via a
grants query.

### (c) NEW candidate regression

**`2026-09-06.yaml` "the not-found line labels its axes and hides the debtor code"** - the
reply contains `[A/C I]` where the case asserts it must not. This is a customer-identifier
leak on a not-found line, adjacent to but distinct from the coordinator's R-E finding (R-E is
about a picked row's `raw`/`canonical_code` swap showing a debtor CODE like `300-G013`; this
is the `[A/C I]` account-type suffix showing on an unrelated not-found branch). Flagged for a
closer look; not root-caused here since it sits outside this lane's own case file and the
coordinator's diagnosis is already in flight for the adjacent R-E shape.

No other failure in this run is unexplained by (a) or (b) above.

## v15-only cosmetic findings (not counted as regressions)

Two of v15's three failures are test-authoring bugs in `2026-09-15-focus.yaml` itself, not
lane defects, found while isolating turns by `test_run_id`:

- **Case F turn 3** (`5b873a1a-7014-45b3-a050-b22c1e384173`): live reply is `"You’re welcome!
  Happy to help."` using a typographic right single quote (U+2019); my `reply_contains`
  assertion used a straight ASCII apostrophe (`"You're welcome! ..."`), which does not match
  as a substring. Turn 4 (`4bf331d1-...`) confirms the roster survived correctly
  (`product: SRTWT2633`). The v20 run of the same case fails for an unrelated reason (b),
  above (different wording entirely, not just the apostrophe).
- **Case H turn 4** (`293cdcdc-bbe9-49ec-b0d3-a116f6364012`): live reply is `"Could you share
  the options you’re choosing from?"`, again a typographic apostrophe against my straight-quote
  assertion. Functionally correct (no re-pick).
- **Case H turn 3** (`560833dc-87f0-4d61-8d4f-77aa052139ca`): `"Sure - would you like SRTWT2633
  or SRTWT2634 instead?"` instead of the expected `"Do you mean you want another option from
  the list?"` - the topic-reset acknowledgment is LLM-composed and varies in wording call to
  call (the S6/S7 evidence itself documents this variance for the same reply slot). The turn 4
  invariant (no re-pick) still holds.
- **stock-clarifier**: v15's reply matches the expected sentence except the trailing clause
  ("Give me a product code, warehouse," vs "Give me a product code or warehouse, and I can
  look it up.") - wording variance, not functional.

Will tighten `2026-09-15-focus.yaml`'s apostrophe-bearing assertions in a follow-up commit so
they match the live typographic quote rather than a fixed straight one.

## Turn ids referenced above

| Case / turn | v20 turn id | v15 turn id |
|---|---|---|
| A turn 4 ("3") | `4f3977f6-0722-4e19-99dc-417c9d9d1070` | `ae96667b-0e33-4e27-89ff-d49fd8ef9405` (PASS) |
| F turn 3 ("thanks") | `fb30937a-a462-4619-bf89-be3d018730fd` | `5b873a1a-7014-45b3-a050-b22c1e384173` |
| H turn 3 ("another one") | `192535fd-69c8-44d2-9ffe-587ea50c6298` | `560833dc-87f0-4d61-8d4f-77aa052139ca` |
| H turn 4 ("2") | `9ce12d8e-f888-4027-a05d-dbfb25026699` | `293cdcdc-bbe9-49ec-b0d3-a116f6364012` |
| I turn 3 ("8") | `1a205662-f067-42c9-9da3-67689c664ee9` | `5a8e49bd-c298-467a-9537-f835f6ce5940` (PASS) |
| stock-clarifier | `9a2b7a21-61d9-485f-bc91-87eff9b36395` | `22d3a36e-b050-47c3-a135-581a10227d3c` |

Raw logs (not committed, reference only): `/tmp/console-check-focus-l1/merged/*.log` on this
machine.
