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

Every write below was made from the CRM UI (headless browser) on the db3 test book and read back with
hapi. "SS" = local SS #224 + #225 merged (from the second link run on).

| ID | Operation | Result | AutoCount read-back after | CRM side |
| --- | --- | --- | --- | --- |
| E1 | Stock Debt split link 4, FXT-1106-PO1 row 12128 (21 @ HQ) -> FXT-1106-SO1 row 12130 (HQ) | PASS (3rd run; run 1 hit B1, run 2 hit B3) | 12128 = 17 @ HQ; new 12139 = 4 @ HQ, FromSODtlKey 12130 | 1 row per AutoCount row; link in `from_so_line_ref` = `DB3:12129:12130` |
| E2 | Split + relocate 5 -> SO1 row 12131 (BRW-AM) | PASS | 12128 = 12 @ HQ; new 12141 = 5 @ BRW-AM, FromSODtlKey 12131 | `DB3:12127:12141` linked to `DB3:12129:12131`; no duplicates, nothing removed |
| E1b | Split 2 on a PO with a BLANK purchase agent: FXT-1106-PO2 row 12133 (3 @ HQ) -> FXT-1106-SO2 row 12135 | PASS on SS #225 (B1 fix; request carried no PurchaseAgent) | 12133 = 1 @ HQ; new 12146 = 2 @ HQ, FromSODtlKey 12135 | link stored, no duplicates |
| G1 | Over-link guard (SO1 HQ line already covered) | PASS | no write | "Link to PO... Already covered by PO FXT-1106-PO1" greyed |
| R2 | Whole-row link (PO2 row 3 = SO2 need 3) | PASS (refused before any write) | PO2 unchanged | "Linking the whole PO line: Waiting for AutoCount" |
| R3 | Unlink / move PO to another SO | PASS (greyed) | n/a | "Unlink from PO... Waiting for AutoCount", "Move PO to another sales order... Waiting for AutoCount" |
| R4 | SPO link / unlink | PASS at SS (no SPO with rows in db3, no CRM screen offers it) | n/a | SS `VENDOR_UNSUPPORTED` (table below) |
| E4 | Quotation "Create in AutoCount" (QT-2026-0001, project PPF2611001) | PASS after the #2173 UOM fix (run 1 refused by AutoCount for UOM "EA", F10) | QT-000006, DocKey 12147: debtor 300-S057, DisplayTerm "Net 90 days" (SS #224), rows 12148 SRTKT38SS 3 @ BRW-AM 285, 12149 SRTKT1631SS 2 @ BRW-AM 235, UOM UNIT | CRM stores QT-000006 on the document |
| E5 | Quotation update (v2, qty 3 -> 5, re-issued + accepted) | FAIL (B6) | QT-000006 unchanged | "AutoCount refused: AutoCount returned an error." |
| R5 | Delete in AutoCount | PASS (not offered) | n/a | quotation gear has no AutoCount delete |

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
| B5 | CRM #2173 | Create/update/cancel idempotency keys are fixed per document or order (`project_autocount_write_service.py:570, :754, :881, :981, :1064`). SS replays a stored answer for the same body and answers `IDEMPOTENCY_CONFLICT` for another body (SS `write_back/operations.py:851-856`). After one AutoCount refusal a corrected retry is refused (seen live: 409, shown as "AutoCount refused: . Nothing was changed."); a project SO can never be created after one refusal | Add a short body hash to the key. Posted on #2173 |
| B6 | CRM #2173 vs SS | QT update (:941) and SO update (:659) first call `read_document` = `GET /api/v1/autocount/documents/{kind}/{docKey}` (`foundryx_autocount_client.py:294-298`); SS has only POST/PATCH document routes (`write_v1.py:274-365`) -> 405 -> every update fails | Crew decision (a): SS adds the GET route on #225 |
| F10 | CRM #2173 + SS preset | CRM sent the project line uom `EA`; AutoCount items are `UNIT` (prod: products.base_uom UNIT 11,491 of 12,031; project SO lines EA 21,931). Refused "The value of column ItemCode and UOM in table Quotation Detail does not exist in its master file." | FIXED on #2173 (crew rule: send the product's AutoCount base UOM): red ea752b64, fix 96b64bba, test af6d22ac, reviewer READY |
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
