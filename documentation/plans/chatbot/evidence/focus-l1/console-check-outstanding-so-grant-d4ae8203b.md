# Console check: outstanding-report cases after the SO-outstanding grant fix

Lane: `feat/chatbot-focus`, stack `http://127.0.0.1:8081`, backend at `d4ae8203b`,
DB `sorento_ai_automation_focus_full` (lane clone used only for this lane's console
testing). Prompt version `ca4e0348-e240-44a5-8947-a48fcdc9e1ca`.

Run date: 2026-09-15.

## Why this run happened

The 13 outstanding-report console cases could not be graded on this stack: every case
hit the `so_bucket_refused` redirect (`_OUTSTANDING_SO_GRANT = "sales_orders.outstanding"`
in `app/services/chatbot/lanes/business/__init__.py`) because test contact `437264483`
(respond_contacts.id `80560c8f-6358-4115-8b2c-e139ef31e48e`) had no
`contact_field_reveals` row for that key on this DB clone. This is a grading-environment
gap, not a code finding - closing it required only a DB grant, no code or case-file
changes.

## 1. Grant rows changed

Verified first that the contact's `access_agents` grant for the outstanding-report agent
(`order_enquiries`, per `app/services/chatbot/head/route.py:104` / `output_exchange.py:100`)
already existed and was active:

```
contact_agent_access: respond_contact_id=80560c8f-6358-4115-8b2c-e139ef31e48e,
agent code=order_enquiries, is_allowed=t, valid_from=2026-01-01, valid_to=2026-12-31
```
No change needed there.

`contact_field_reveals` BEFORE (4 rows, no `sales_orders.outstanding`):

```
 respond_contact_id                   | field_key                 | granted | created_at
 80560c8f-6358-4115-8b2c-e139ef31e48e | inventory.sellable        | t       | 2026-09-07 16:17:10.787984
 80560c8f-6358-4115-8b2c-e139ef31e48e | purchase_orders.placed    | t       | 2026-09-08 03:07:40.100366
 80560c8f-6358-4115-8b2c-e139ef31e48e | purchase_orders.cost      | t       | 2026-09-15 04:26:26.063901
 80560c8f-6358-4115-8b2c-e139ef31e48e | purchase_orders.supplier  | t       | 2026-09-15 04:26:27.012855
```

Inserted, mirroring the shape of the existing granted rows (same `created_by` as the
most recent grants on this contact):

```sql
INSERT INTO contact_field_reveals (id, respond_contact_id, field_key, granted, created_at, updated_at, created_by)
VALUES (gen_random_uuid(), '80560c8f-6358-4115-8b2c-e139ef31e48e', 'sales_orders.outstanding', true, now(), now(), '9993276c-a55e-4a54-9686-7138f5fa1306')
RETURNING *;
```

`contact_field_reveals` AFTER (5 rows):

```
 respond_contact_id                   | field_key                 | granted | created_at
 80560c8f-6358-4115-8b2c-e139ef31e48e | inventory.sellable        | t       | 2026-09-07 16:17:10.787984
 80560c8f-6358-4115-8b2c-e139ef31e48e | purchase_orders.cost      | t       | 2026-09-15 04:26:26.063901
 80560c8f-6358-4115-8b2c-e139ef31e48e | purchase_orders.placed    | t       | 2026-09-08 03:07:40.100366
 80560c8f-6358-4115-8b2c-e139ef31e48e | purchase_orders.supplier  | t       | 2026-09-15 04:26:27.012855
 80560c8f-6358-4115-8b2c-e139ef31e48e | sales_orders.outstanding  | t       | 2026-09-15 14:10:30.098837
```

New row id: `e1a9c3c5-f2d2-4e8f-9959-e19add9cabb1`.

This DB is a lane clone used only for console-check grading; the change is intended and
left in place, not committed anywhere (there is nothing to commit - it is a data row).

## 2. Pass/fail per file

Confirmed for every red below: `trace::text ilike '%so_bucket_refused%'` is `false` -
the grant fix is working, none of these reds are the grant gap recurring.

### `2026-09-14-outstanding-owner-rounds.yaml` (run `console-check-1789449050`) - **10 passed, 2 failed**

### `2026-09-13-outstanding-report.yaml` (run `console-check-1789449433`) - **1 passed, 3 failed**

## 3. Every red line, expected vs actual, turn id, error/trace

### File 1: `2026-09-14-outstanding-owner-rounds.yaml`

**R15 - refinement by date and location stacked** - turn 5 ("only BRW")
turn id `94639ef2-cdf7-4540-a78e-93b411ba2e84`, `chatbot.turns.error` = `` (empty),
`status=done`, `branch_kind=business_query`.

- Expected: reply contains `"Location: BRW"`, `"Order date: 01/09/2026 to 30/09/2026"`,
  `"Sales order outstanding"`; must NOT contain `"Outstanding for which document?"`.
- Actual reply:
  ```
  Product: all
  Customer: CNK HARDWARE SDN BHD (PROJECT), CNK HARDWARE SDN BHD
  Location: BRW
  Order date: 01/09/2026 to 30/09/2026
  Outstanding for which document?
  1. Sales orders (not yet transferred to DO)
  2. Delivery orders (not yet delivered)
  3. Both
  ```
- Finding: the location refinement ("only BRW") re-armed the scope question instead of
  keeping the already-answered scope (`both`, set in turn 2) and just narrowing by
  location, as turn 3's date refinement correctly did. A real behavior defect in
  location-refinement handling, not the grant.

**R20 - no DO hint on the customer picker of an outstanding ask** - turn 3 ("all")
turn id `36aaf33a-74cd-43c6-be30-7fd2dbddd9af`, `chatbot.turns.error` = `` (empty),
`status=done`, `branch_kind=business_query`.

- Expected: reply contains `"Customer: CHIN CHUN HARDWARE SDN BHD"`,
  `"Delivery order outstanding"`, `"Outstanding: 5"`; must NOT contain `"(MCH, SRT)"`.
- Actual reply:
  ```
  Product: SRTKT39SS
  Customer: CHIN CHUN HARDWARE SDN BHD - [A/C I]
  Location: all
  Order date: 01/01/2026 to 31/12/2026

  *Sales order outstanding*
  No open sales order.

  *Delivery order outstanding*
  No outstanding delivery order.

  Would you like me to escalate to customer service team?
  ...
  ```
- Finding: the picked customer ledger (`CHIN CHUN HARDWARE SDN BHD - [A/C I]`) returned
  zero SO/DO rows where the case expects `Outstanding: 5` DO qty. Either the case's data
  assumption (SRTKT39SS / chin chun DO=5, documented in the file header as sourced from
  `sorento_ai_automation_0907`) no longer holds on this lane clone, or the customer
  resolved by "1" differs from the ledger the case author tested against. Not the grant
  gate (no `so_bucket_refused`), and not a parser/network error - a data/case drift.

### File 2: `2026-09-13-outstanding-report.yaml`

**"outstanding report journey - SO direct ask, missing-scope question, both, detail,
customer filter, miss"** - all six turns run as one conversation; the failure cascades
from turn 2 onward.

- turn 1 (`"Srtwt7443 sales order outstanding for IB"`), turn id
  `51962472-f635-4da5-8a54-27c50227eb36`, error=``, status=done, branch_kind=business_query.
  - Expected reply contains `"1. Sales order list"`.
  - Actual reply ends with `"Reply 1 for the sales order list."` - same offer, different
    literal wording than the case asserts. All other `reply_contains` items are present
    (full SO summary: Outstanding 3,530 at BRW-IB, By location/By customer breakdown).
    Wording-only mismatch against the assertion string, not a missing feature.

- turn 2 (`"SRTWT7445 outstanding in 2026"`), turn id
  `9a23ec02-5b52-4538-8f66-20962e3cf9cc`, error=``, status=done, branch_kind=business_query.
  - Expected: reply asks the scope question (matches) AND `pending_kind: outstanding_scope`.
  - Actual reply text matches (`"Outstanding for which document? 1. Sales orders... 2.
    Delivery orders... 3. Both"`), but the script's `pending_kind` check (reads
    `variables.pending.kind` from the response body, falling back to the turn's
    `trace` "remembered" stage `session_patch`) returned `None` - the pending marker was
    not written even though the question text rendered correctly.

- turn 3 (`"3"`), turn id `dd5839a2-ea48-41b4-ae0c-c808ab5982ce`, error=``, status=done,
  branch_kind=business_query.
  - Expected: both-scope report for SRTWT7445 in 2026 (3 open SO lines, DO rows across
    2026); `pending_kind: outstanding_detail`.
  - Actual reply: `"No open sales order."` / `"No outstanding delivery order."` followed
    by an unrelated escalation offer (routing picker to 6 CS agents). This is the
    downstream consequence of turn 2's missing pending marker: `"3"` was not recognized
    as the answer to the open scope question, so it ran as (or fell through to) a fresh,
    empty-result query instead of resolving `scope=both` against the carried filters.

- turn 4 (`"1"`), turn id `05eeac36-2481-49f1-90eb-fcaf0a9e7b77`, error=``, status=done,
  branch_kind=`out_of_scope` (expected `business_query`).
  - Expected: per-SO detail list (`"SO Number:"`, `"Ordered:"`, `"Transferred to DO:"`,
    `"Outstanding:"`, `"Order Date:"`).
  - Actual: empty reply text, routed to `out_of_scope`. Cascading from turn 3: since
    turn 3 left an escalation-routing picker open (not the `outstanding_detail` offer),
    `"1"` had no valid pending offer to resolve against.
  - Turns 5-6 were not separately flagged as red in the log (the case is graded as one
    failing case), but their filters would already be corrupted by the same cascade.

**D17 - parser-driven word answers to the open scope/detail questions, and a new ask
mid-offer**

- turn 1 (`"SRTWT7445 outstanding both"`), turn id
  `bc265762-98c8-4d47-93e8-fba53ab5b836`, error=``, status=done, branch_kind=business_query.
  - Expected: `pending_kind: outstanding_detail`.
  - Actual: reply text is a correct full both-scope report ending in `"Reply with a
    number for detail: 1. Sales order list 2. Delivery order list 3. Both lists"`, but
    `pending_kind` again reads `None` by the same mechanism as turn 2 above - the same
    "pending marker not written" finding, on the `outstanding_detail` offer this time.

- turn 3 (`"SO list"`), turn id `8cf68de8-1693-4a6a-96db-91df8d8f589f`,
  **`status=failed`**, `branch_kind` = null.
  - `chatbot.turns.error`:
    ```
    parser provider call failed: Error code: 429 - {'error': {'message': 'Rate limit
    reached for gpt-5.4-mini in organization org-j8KgkM3oUzK9d2XUrhuwXrZK on tokens per
    min (TPM): Limit 200000, Used 198425, Requested 11625. Please try again in 3.015s.
    Visit https://platform.openai.com/account/rate-limits to learn more.', 'type':
    'tokens', 'param': None, 'code': 'rate_limit_exceeded'}}
    ```
  - Environmental: OpenAI TPM rate limit on `gpt-5.4-mini`, not a code or grant defect
    (matches the known `project_console_check_openai_tpm_429` gotcha; the script's
    single 429 retry was not enough headroom here at `--sleep-seconds 8`).

- turn 5 (`"SRTWT7445 outstanding"`), turn id
  `c93c1601-015c-42fe-a03c-83a75d268626`, error=``, status=done, branch_kind=business_query.
  - Expected: `pending_kind: outstanding_scope`.
  - Actual: reply text correctly asks the scope question, but `pending_kind` again reads
    `None` - same missing-marker finding as turns 1 and 2 above, now confirmed across
    all three: `outstanding_scope` (turns 2, 5) and `outstanding_detail` (turn 1) offers
    all fail to persist `variables.pending.kind`.

- turn 6 (`"everything"`), turn id `ed28dd22-0b72-4039-8204-ea2b9e7dad00`,
  **`status=failed`**, `branch_kind` = null.
  - `chatbot.turns.error`:
    ```
    parser provider call failed: Error code: 429 - {'error': {'message': 'Rate limit
    reached for gpt-5.4-mini in organization org-j8KgkM3oUzK9d2XUrhuwXrZK on tokens per
    min (TPM): Limit 200000, Used 198906, Requested 11217. Please try again in 3.036s.
    Visit https://platform.openai.com/account/rate-limits to learn more.', 'type':
    'tokens', 'param': None, 'code': 'rate_limit_exceeded'}}
    ```
  - Same environmental 429, not a code or grant defect.

**R13 - a customer-only ask reaches the same report, By product instead of By customer**

- turn 1 (`"outstanding report for hanlim"`), turn id
  `1bd12a11-f00b-41a0-b91d-9d24832133dd`, error=``, status=done, branch_kind=business_query.
  - Expected: `pending_kind: outstanding_scope`.
  - Actual: reply text correctly lists all six HANLIM ledgers and asks the scope
    question, but `pending_kind` again reads `None` - the same missing-marker finding.
  - Turn 2 (`"3"`) was not separately flagged red in the log for this case.

## Summary of distinct findings (not softened)

1. **`variables.pending.kind` is not being persisted** for `outstanding_scope` and
   `outstanding_detail` offers on this build, even though the offer text renders
   correctly - confirmed on 4 separate turns across 3 cases (case 1 turn 2, D17 turns 1
   and 5, R13 turn 1). This is the root cause of the case-1 cascade (turn 3's `"3"` not
   resolving the scope question, turn 4's `"1"` landing in `out_of_scope`).
2. **R15 turn 5**: a location-only refinement re-arms the scope question instead of
   narrowing the already-answered scope.
3. **R20 turn 3**: a picked customer ledger returns zero SO/DO rows against a case that
   asserts `Outstanding: 5` DO qty - data/case drift on this lane clone, not reproduced
   as a grant or code failure.
4. **Turn 1 wording**: `"Reply 1 for the sales order list."` vs the asserted literal
   `"1. Sales order list"` - cosmetic assertion mismatch, not a missing feature.
5. **Two OpenAI TPM 429s** (D17 turns 3 and 6) - environmental, not reproducible as a
   code defect from this run alone.

None of the 5 reds above are the `so_bucket_refused` grading gap this run was launched
to close - that gap is confirmed closed (no red carries `so_bucket_refused` in its
trace).
