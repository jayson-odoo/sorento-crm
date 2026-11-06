# REPORT: AutoCount end to end on db3 (AC-E2E-DB3), 6 Nov 2026

Plan `PLAN-ac-e2e-db3-06nov.md`, UAC `ac-e2e-db3-06nov-acceptance-criteria.md`. Codes, doc numbers and
quantities only (public repo); screenshots and raw read-back JSON are in crew's private files
(`crew/state/files/AC-E2E-DB3/`).

## Stack that ran

| Piece | What | Where |
| --- | --- | --- |
| CRM | local branch `local/ac-e2e-db3-stack` = origin/main 61e9d217 + #2173 77f47a1b + #2202 1bca21eb + #2219 8670e71a (never pushed) | BE 127.0.0.1:8318, FE :3318, RQ worker, private Redis :6418 |
| CRM DB | `sorento_staging_acdb3`: `scripts.bootstrap_env` (create_all + stamp head), then every migration's INSERT seeds replayed, then `seed_db3_staging.py --apply` | local Postgres |
| SS | foundryx-shared-service at #224 head f087b87a (detached worktree), fresh DB `foundryx_service_acdb3` via `scripts.bootstrap_db`, `CELERY_TASK_ALWAYS_EAGER=true` | 127.0.0.1:8319 |
| SS company | `SRT_DB3` (refPrefix `DB3`), AutoCount connection `https://hapi.sorento.cc.cd/api/db3`, Sorento sink -> CRM :8318 (contract "2"), write connection = db3 | |
| AutoCount | db3 test book through hapi; every check below read back with GET `{kind}byLastModified` | |

Masters into SRT_DB3 through SS ETL: 4274 debtors, 11970 items, 154 locations, 2352 branches, 10 UOM.
Suppliers (1088) and sales agents (133) went straight from hapi to CRM ingest (no SS HTTP preset, F3).

## Results

(filled in as the passes land)

## Findings

| # | Where | Finding | Proposal |
| --- | --- | --- | --- |
| F1 | CRM #2173 | Migration `acqs_0001_project_ac_write` has `down_revision = "pol_0001_stock_debt_link_po"`; main's head is `ptag_0016_accessories`, so main + #2173 has two heads | Pre-merge gate: `./scripts/alembic-reparent.sh` on #2173 (the stack re-parented locally) |
| F2 | CRM #2202 runbook | On a database that is not a dev-DB copy the kit needs more than the seed: no `system_settings` row (seed refuses), no `tenant_modules` rows (sidebar shows only Dashboards/Ideas, module routes redirect to /), no warehouse with `fulfilment_planning` (Stock Debt empty), and create_all skips migration-body seeds (`project_lead_source`, `my_state` lookups: project registration cannot start) | Runbook: say "copy the dev DB" is required, or add a "fresh DB" section listing these four steps |
| F3 | SS presets | `HTTP_PRESETS` (`modules/autocount/presets.py:1696-1706`) has no supplier or sales agent preset, so an API-only book (db3) never sends creditors or agents to the CRM; a PO pushed later is retryable on a CRM that lacks the supplier | SS backlog: HTTP presets for `creditorbypage` and `salesagent` |
| F4 | SS presets | Document presets are SQL-only (`presets.py:1112-1125`); for db3 the only AutoCount -> SS -> CRM path for PO/SO/QT is the write-back read-back push. Documents keyed in AutoCount by hand never reach the CRM | SS backlog: HTTP document feed for SO/PO (the doc-feed pattern already covers DO/GRN) |
| F5 | SS ETL | All 92 db3 ItemGroups fail ("field 'name' (Description) - required"), every ItemGroup Description is blank in db3 | Map name from the code when Description is blank |
| F6 | CRM #2202 contract | Contract shows refs as `db3:BR:...`; with the SS company's required refPrefix the refs are `DB3:...` | Contract wording only |
| B1 | SS write-back (merged #183/#191) | A PO whose read-back `PurchaseAgent` is blank cannot be split-linked or edited: the edit PUT echoes `"PurchaseAgent": ""` and AutoCount answers 500 "The value of column PurchaseAgent in table Purchase Order does not exist in its master file." Cause `modules/autocount/write_back/payloads.py:76-80` (`_pick` copies blank keys), used by `po_header` :84 and `_doc_header` :374 | Omit blank master-reference header keys (`PurchaseAgent`, `SalesAgent`) from edit/link bodies. Filed: crew-note on SS #224 |
| B2 | SS write-back | On `VENDOR_ERROR` the answer's `message` is empty although `ac_write_action.response_json` holds AutoCount's text, so the CRM can only say "AutoCount did not accept it. Nothing was changed." | Carry the vendor text in `message` (same crew-note) |
| B3 | CRM main (#2168) | `stock_debt_po_link_service.py:335-343` `_intent_key` = hash(path + body + PO row qty). After a `vendor_error` that wrote nothing, the row qty is unchanged, so every later attempt sends the same Idempotency-Key and SS replays the stored failure (502) without calling AutoCount: the link can never be retried from the UI, even after the cause is fixed in AutoCount | Add the PO's AutoCount `LastModified` (or an attempt nonce after a definite refusal) to the key; or SS stops replaying a stored `vendor_error` that wrote nothing |
| B4 | AutoCount + SS verify | Split link: SS sends the new linked row with `UnitPrice 1.0` and `DeliveryDate 2026-11-20` (ac_write_action request), AutoCount stores the transferred row with `UnitPrice 0.0` and no delivery date, and SS answers `done`. FXT-1106-PO1 Total went 21 -> 12 after E1+E2 (9 units now priced 0). Same shape on 4 Nov FXT-1104d-1 | AutoCount question (does a FromSO transfer row ignore UnitPrice/DeliveryDate?); SS read-back verify should compare price/date on the new row and answer `mismatch` |
| F7 | CRM #2173 | A quotation with no recipient party is refused `ac_missing_debtor` "No debtor code on the customer." before SS is called (correct refusal, misleading text) | Say "This quotation has no recipient customer" when `recipient_party_id` is empty |
| F8 | CRM project sales (UNVERIFIED as a product bug) | In the register wizard the customer pick did not stick on this copy (4274 customers); setting the customer afterwards with Edit project created no developer party, so the proposal and quotation carry no recipient. Staging fix: a developer party for 300-S057 linked to the project and both documents | Worth a separate look; out of this lane's scope |
| F9 | Staging data | The derived quotation location needs customer -> sales agent -> agent location group -> `BRW-<group>`. Customers were pushed before sales agents existed, so no agent link; staging fix: 300-S057 linked to its db3 agent, agent group `AM` | Push agents before customers (runbook order) |

## Refusals checked directly on SS (no CRM screen exists or as a second check)

All answered `outcome: refused, errorCode: VENDOR_UNSUPPORTED`, and AutoCount `LastModified` was unchanged
afterwards (read-back):

| Call | Target |
| --- | --- |
| `POST /documents/sales-orders/12134/cancel` | FXT-1106-SO2 |
| `POST /documents/sales-orders/12134/lines/12135/delete` | FXT-1106-SO2 row 12135 |
| `POST /documents/purchase-orders/12132/cancel` | FXT-1106-PO2 |
| `POST /spo-links`, `/spo-links/relink`, `/spo-links/unlink` | SPO 12036 (FXT-1104b-S3) to FXT-1106-PO2 row 12133 |

## db3 documents written by this lane

| DocNo | DocKey | How | Rows |
| --- | --- | --- | --- |
| FXT-1106-PO1 | 12127 | SS create (fixture) | 12128 SRTKT38SS 20 @ HQ |
| FXT-1106-SO1 | 12129 | SS create (fixture), term filled by SS #224 from debtor ("Net 90 days") | 12130 4 @ HQ, 12131 5 @ BRW-AM |
| FXT-1106-PO2 | 12132 | SS create (fixture) | 12133 3 @ HQ |
| FXT-1106-SO2 | 12134 | SS create (fixture) | 12135 3 @ HQ |

Nothing was deleted or cancelled (AutoCount has no delete door; cancel is refused).
