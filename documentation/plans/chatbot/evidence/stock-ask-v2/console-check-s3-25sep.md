# Console check, S3 (AC-SA318), 25 Sep 2026

Closes AC-SA318 ("Console check per `documentation/agents/chatbot-verification.md` against
an Availability only dealer contact: one turn per branch - B1 via Q > X, B1 via unset X,
B2, B3 with toggle on and off, B4; replies quoted in
`documentation/plans/chatbot/evidence/`").

## Environment note (deviation from the brief)

The brief assumed this sandbox's `DATABASE_URL` was already a bootstrapped prod-copy DB.
Measured instead: `scripts/cloud-env-setup.sh` bootstraps a CI-shaped, EMPTY Postgres
(`sorento_ci`) via `scripts.bootstrap_env` (reference data only - roles, permissions, order
statuses; zero `chatbot.turns`, zero `respond_contacts`, zero `products`, zero `users`).
`bash scripts/cloud-env-setup.sh --check` reported "all checks passed" before this session
started, confirming the DB was genuinely at this state rather than mid-setup.

The console-check script's own envelope-borrowing mechanism (`_base_envelope`, see
`scripts/chatbot_console_check.py`'s module docstring) requires an existing
`chatbot.turns` row for the contact, so a scenario contact had to be seeded, not just
reused. All scenario data (contact, categories, products, stock, the incoming shipment +
packing list, the access grant, the integration principal and the seed `chatbot.turns`
row) was seeded directly via SQLAlchemy against `sorento_ci`, matching the shape
`tests/chatbot/test_console_turn_endpoint.py`'s own fixtures (`seeded_contact_with_a_prior_turn`,
`tests/chatbot/test_engine.py::_envelope`/`CONTACT_ID = 437264483`) already establish for this
exact purpose - the SAME `CONTACT_ID` every other console-case file in this repo uses.

Two additional environment gaps were found and worked around (neither is an S3 code
defect, both are pre-existing sandbox/DB gaps):

1. **`api_call_log` table missing.** The `ApiCallLog` ORM model (`app/models/api_call_log.py`)
   exists, but `scripts.bootstrap_env`'s `Base.metadata.create_all(engine)` had not created
   it in this DB (a `create_all`-vs-import-order gap the bootstrap script's own comments
   describe for several other tables, e.g. reference-data rows it explicitly replays).
   Worked around additively: `Base.metadata.create_all(bind=engine, tables=[ApiCallLog.__table__])`
   after importing `app.main` (registers every model). No migration touched, no destructive
   DDL - the same "additive DDL only" rule `sorento_crm_backend/CLAUDE.md`'s shared-DB lesson
   states for schema drift.
2. **Company scope for a chatbot turn is resolved off the CONTACT, not the API key**
   (`app.services.company_scope_resolver.resolve_contact_company_scope`, read via
   `respond_contact_companies` - `engine.py`'s own comment: "the chatbot turn engine... calls
   resolver/stock/promotion code IN PROCESS and so never runs that [request] dependency").
   Without a `respond_contact_companies` row for the seed contact, every company-scoped read
   inside a turn (products, categories, stock, the resolver itself) sees zero rows,
   fail-closed - read as "Couldn't find: X" rather than an auth error, which cost real time
   to diagnose. Seeded one row, company = the DB's single seeded company
   (`00000000-0000-0000-0000-000000000001`, "Sorento").

None of the above are committed - the throwaway seed script stayed in the session's private
scratch directory, per the brief's default.

The `chatbot_semantic_parser` prompt / `ai_assistant_configs` singleton auto-creates on first
use with an empty `api_key_ciphertext`; `resolve_config` (called unconditionally, even on a
`--mock-parser` turn - it is the parser CONFIG resolution, not the parser CALL) raises when
that key is empty. Set `ai_assistant_configs.api_key_ciphertext` to a placeholder string (never
actually sent - the mocked turn never reaches `parser.parse`) to clear it.

The MCP server (`sorento_crm_mcp`, package already installed in the backend venv) was not
running; the engine calls it in-process over HTTP for every domain fetch
(`ai_assistant_service.call_tool` -> `settings.ai_assistant_mcp_url`, default
`http://localhost:8765/mcp`). Booted it:

```
cd sorento_crm_mcp
CRM_BASE_URL=http://localhost:8000 EXTERNAL_API_KEY=cloud-lane-test-key \
    /home/user/sorento-crm/sorento_crm_backend/venv/bin/python -m sorento_crm_mcp
```

The console-check API key used throughout is `.env.ci-tests`'s `EXTERNAL_API_KEY`
(`cloud-lane-test-key`) - deliberately, not a fresh integration key: authentication goes
through the new `integration_api_keys` hash lookup, but
`company_scope_resolver._api_key_valid` (a second, older check that decides whether to apply
company scope to a request AT ALL) still compares the presented header byte-for-byte against
the legacy `settings.external_api_key` env var. A bespoke key authenticates fine but resolves
an UNSET (fail-closed) scope on every plain HTTP call this session made directly (e.g. the
`/system/references/resolve` probes below) - sharing the value satisfies both checks. The
integration's `act_as_user_id` principal holds the seeded DB's `admin` role, which short-circuits
`UserPermissionService.check_user_has_permission` (superadmin/admin check) past the
`integration.chat_turn.submit` permission gate.

## Scenario data

Contact: `respond_io_id = "437264483"` (the console-case convention contact; matches every
other file under `tests/chatbot/console_cases/`), stock visibility policy `mode=availability`
(a `stock_visibility_policies` row with `contact_id` = the internal id, R1's "Availability
only" scope), `packing_list_allowed` flipped between the two B3 runs (see below), warehouse
`SA318W1` named in the policy's `warehouse_ids`.

Categories:
- `SA318CAP` - `chatbot_max_qty = 200`, `chatbot_eta_offset_days = 7`.
- `SA318UNCAP` - both NULL (R2: unset means 0/no cap).

Products (all inherit their category's X/Y - product-level `chatbot_max_qty` /
`chatbot_eta_offset_days` left NULL, R2's resolution rule):
- `SA318A` (SA318CAP) - too_big via Q(250) > X(200).
- `SA318B` (SA318UNCAP) - too_big via unset X (X resolves to 0).
- `SA318C` (SA318CAP) - in_stock: 200 on hand in the policy warehouse, ask 50.
- `SA318D` (SA318CAP) - incoming: 0 on hand, a qualifying R5 shipment (`SA318-SHIP-1`,
  `shipment_status = in_transit`, `estimated_arrival_date = 2026-10-12`, `attachment_id` set,
  line `quantity_shipped=150`, `quantity_received=0`, `line_status=in_transit`) - told date
  `2026-10-12 + Y(7) = 19/10/2026`.
- `SA318E` (SA318CAP) - no_incoming: 0 on hand, no shipment.

`branch()` (`app.services.stock_ask_branch.branch`) was confirmed by hand against these
numbers BEFORE writing the case files' `reply_contains`, per the brief's instruction:
`branch(250, 200, 0, None) = too_big`; `branch(20, 0, 0, None) = too_big` (X unset -> 0);
`branch(50, 200, 200, None) = in_stock`; `branch(150, 200, 0, date(2026,10,12)) = incoming`;
`branch(150, 200, 0, None) = no_incoming`.

## Commands run

```
cd sorento_crm_backend
SORENTO_ENV_FILE=.env.ci-tests venv/bin/python scripts/chatbot_console_check.py \
    tests/chatbot/console_cases/2026-09-25-stock-ask-v2-s3-branches.yaml \
    --base-url http://127.0.0.1:8000 --api-key cloud-lane-test-key --mock-parser
```

Output:

```
console-check-1790322722  3 cases against http://127.0.0.1:8000  parser prompt: whatever the `production` label points at
lane switches before: enabled=False lanes=[]
lane switches for the run: enabled=True lanes=13
PASS  B1 via Q>X and B1 via unset X, one multi-product turn (R14 sample g) branch=business_query  'Sorry, we do not have enough stock for that quantity.  1. SA318A x 250: the quantity is more than what I can confirm her'
PASS  B2 - in stock                                branch=business_query  'Yes, we have stock.  1. SA318C x 50: yes, we have stock, please refer to your salesman to proceed. Yes, we have stock.  '
PASS  B4 - no stock and no incoming                branch=business_query  'Sorry, we do not have enough stock for that quantity.  1. SA318E x 150: no stock and no incoming at the moment, please r'
lane switches restored: enabled=False lanes=[]

3 passed, 0 failed  (console-check-1790322722)
```

Then, for B3, run twice with the toggle flipped between runs (`UPDATE respond_contacts SET
packing_list_allowed = <true|false> WHERE respond_io_id = '437264483'`):

```
SORENTO_ENV_FILE=.env.ci-tests venv/bin/python scripts/chatbot_console_check.py \
    tests/chatbot/console_cases/2026-09-25-stock-ask-v2-s3-incoming-packing-list.yaml \
    --base-url http://127.0.0.1:8000 --api-key cloud-lane-test-key --mock-parser
```

Output (toggle ON):

```
console-check-1790322700  1 cases against http://127.0.0.1:8000  parser prompt: whatever the `production` label points at
lane switches before: enabled=False lanes=[]
lane switches for the run: enabled=True lanes=13
PASS  B3 - incoming with ETA (run with packing_list_allowed both true and false) branch=business_query  'Here is the stock availability for the requested products.  1. SA318D x 150: no stock at the moment, ETA 19/10/2026. Her'
lane switches restored: enabled=False lanes=[]

1 passed, 0 failed  (console-check-1790322700)
```

Output (toggle OFF):

```
console-check-1790322709  1 cases against http://127.0.0.1:8000  parser prompt: whatever the `production` label points at
lane switches before: enabled=False lanes=[]
lane switches for the run: enabled=True lanes=13
PASS  B3 - incoming with ETA (run with packing_list_allowed both true and false) branch=business_query  'Here is the stock availability for the requested products.  1. SA318D x 150: no stock at the moment, ETA 19/10/2026. Her'
lane switches restored: enabled=False lanes=[]

1 passed, 0 failed  (console-check-1790322709)
```

Both runs' `reply_contains` graded identically (the reply TEXT does not carry the
attachment) - the attachment finding below is the second half of this branch's evidence,
read directly off `chatbot.turns.response->'actions'` for each run's own row, as the case
file's own header says to.

## The six branches, replies verbatim

Read via `SELECT response->'reply'->>'text' FROM chatbot.turns WHERE contact_respond_id =
'437264483' AND is_test = true ORDER BY created_at DESC` immediately after each run (dry
runs still write `chatbot.turns`, per `documentation/agents/chatbot-verification.md`).

**B1 via Q > X** (`SA318A`, asked 250, X=200) and **B1 via unset X** (`SA318B`, asked 20, X
unset) - one multi-product turn, R14 sample (g)'s own shape:

```
Sorry, we do not have enough stock for that quantity.

1. SA318A x 250: the quantity is more than what I can confirm here, please refer to your salesman.

2. SA318B x 20: the quantity is more than what I can confirm here, please refer to your salesman.
```

Both lines read identically to the dealer, confirming R14/AC-SA313: the "no cap set for
`<category>`" wording is S4's own AGENT-notification reason (not built in this slice),
never a sentence the dealer is sent.

**B2 - in stock** (`SA318C`, asked 50, 200 on hand):

```
Yes, we have stock.

1. SA318C x 50: yes, we have stock, please refer to your salesman to proceed.
```

**B3 - incoming, ETA** (`SA318D`, asked 150, 0 on hand, shipment 2026-10-12 + Y=7 ->
19/10/2026) - identical reply text both toggle runs:

```
Here is the stock availability for the requested products.

1. SA318D x 150: no stock at the moment, ETA 19/10/2026.
```

**B4 - no stock, no incoming** (`SA318E`, asked 150, 0 on hand, no shipment):

```
Sorry, we do not have enough stock for that quantity.

1. SA318E x 150: no stock and no incoming at the moment, please refer to your salesman.
```

## B3 `send_attachments` finding

Read via `SELECT response->'actions' FROM chatbot.turns WHERE id = '<turn id>'` for each
run's own final (quantity-stating) turn:

**Toggle ON** (`respond_contacts.packing_list_allowed = true`), turn `d72da7ff-c201-4601-9f72-d2d0557d1716`:

```json
[
  {"kind": "send_message", "text": "Here is the stock availability for the requested products.\n\n1. SA318D x 150: no stock at the moment, ETA 19/10/2026.", "dry_run": true, "result_set": [], "quick_replies": null},
  {"kind": "send_attachments", "dry_run": true, "attachments_src": [{"url": "https://example.test/sa318-packing-list.pdf", "filename": "SA318-packing-list.pdf", "mimeType": "application/pdf"}]}
]
```

`send_attachments` IS present, carrying the seeded shipment's packing list attachment.

**Toggle OFF** (`respond_contacts.packing_list_allowed = false`), turn `2bb5f8f7-49f2-42f4-b268-58b92d1612b0`:

```json
[
  {"kind": "send_message", "text": "Here is the stock availability for the requested products.\n\n1. SA318D x 150: no stock at the moment, ETA 19/10/2026.", "dry_run": true, "result_set": [], "quick_replies": null}
]
```

`send_attachments` is ABSENT - only `send_message`. Text is byte-identical between the two
runs (as expected: R6/AC-SA311 gate the ATTACHMENT on the toggle, never the wording).

This confirms AC-SA311 ("`packing_list` is present on an `incoming` entry only when the
asking contact's `packing_list_allowed` is true") and AC-SA314 ("Engine: B3 with
`packing_list` present emits one `send_attachments` action with that file; without it, no
attachment action") against a real turn through the real backend, not just the pytest suite.

## Files

- `tests/chatbot/console_cases/2026-09-25-stock-ask-v2-s3-branches.yaml` (B1 via Q>X, B1 via
  unset X, B2, B4).
- `tests/chatbot/console_cases/2026-09-25-stock-ask-v2-s3-incoming-packing-list.yaml` (B3,
  run against both toggle states).
- This file.

## Result

All six AC-SA318 branches (B1 via Q > X, B1 via unset X, B2, B3 with the toggle on, B3 with
the toggle off, B4) pass for the right reason: each reply is graded on the exact R14
sentence, not the generic error reply or a `branch_kind`-only assertion (the pitfall
`documentation/agents/chatbot-verification.md` and this repo's other console-case files both
name). No case was weakened to pass. No S3 code defect was found; the two environment gaps
above are pre-existing sandbox/DB gaps, not part of this slice's diff, and were worked around
additively (a missing table created, one data row seeded) rather than by touching any
migration or application code.
