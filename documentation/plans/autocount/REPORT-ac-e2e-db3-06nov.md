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
| E5 | Quotation update (v2, qty 3 -> 5, re-issued + accepted) | PASS on the 3rd run (run 1: B6 405, run 2: B7 `FIELD_NOT_EDITABLE: docDate`) | QT-000006 row 12148 3 -> 5, row 12149 2, same DocKey 12147, no duplicate rows | dialog "AutoCount answered: ignored: remark2, remark3, remark4." (F13) |
| B4p | Split keeps price/date (SS #225 940a6345): FXT-1106-PO3 (blank agent) row 12151 10 @ HQ 2.5 -> SO3 rows 12153 (3 @ HQ) and 12154 (4 @ BRW-AM) | PASS | 12151 = 3 @ HQ; new 12156 3 @ HQ and 12158 4 @ BRW-AM, both UnitPrice 2.5, DeliveryDate 2026-11-27; Total 25.0 unchanged | 3 lines, links stored, no duplicates |
| E6 | Project SO "Create in AutoCount" (PSO-000001, built from the customer PO + delivery schedule, published) | PASS (run 1 refused in CRM: customer PO had no issuing party, staging data) | SO1, DocKey 12159: debtor 300-S057, term "Net 90 days", rows 12160 SRTKT38SS 5 and 12161 SRTKT1631SS 2, UOM UNIT, BRW-AM, delivery 2026-11-30 | toast "SO1 created in AutoCount" |
| E7 | SO amendment (schedule v2: SRTKT1631SS 2 -> 3) -> publish -> "Update in AutoCount" | PASS through the CRM API for publish + update (the page crashes after create, B8; publish needs an OCN approver nothing sets, B9; stale stamp, B10) | row 12161 2 -> 3, DtlKeys kept (12160, 12161), Total 2130 | "SO1 updated in AutoCount" |
| P1/P2 | AutoCount -> SS -> CRM after E6/E7 | PASS | n/a | `public.sales_orders` `DB3:12159` = 1 row; lines `DB3:12159:12160` 5 and `:12161` 3, both open, `removed_unreferenced` false, no duplicates |
| R1 | SO "Cancel in AutoCount" | PASS (greyed, no write) | SO1 unchanged | before create "Not in AutoCount yet"; after create "Waiting for AutoCount" (cancel_doc is VENDOR_UNSUPPORTED; the text should name that, minor) |
| R5 | Delete in AutoCount | PASS (not offered) | n/a | no AutoCount delete on quotation or SO menus |
| R6 | Debtor with no credit term | N/A live: none of the 4274 db3 debtors lacks a term; covered by SS #224 unit tests | | |

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
| B7 | CRM #2173 | Edit (PATCH) bodies put `docDate` inside `header` (:670 SO, :1019 QT) -> SS `FIELD_NOT_EDITABLE: docDate`; and top-level docDate is the date SS looks the document up by, so it must be the document's own date, never today | FIXED on #2173: 8e147f9b red, 287c7098, 202ac170, 0feb4ba8 red, 118302b0; reviewer READY; head f44a9f51 |
| B8 | CRM main | SO amendment page crashes right after "Create the amendment": GET `/project-sales/amendments/{id}` returns rows under `delta` but `AmendmentReviewClient.tsx:442-447` reads `detail.rows/unmatched/from/to` -> `AmendmentDeltaSummary.tsx:51` `undefined.forEach`. The created amendment id lives only in client state, so after a reload the proposed amendment cannot be reached, and a second one can be created | Own lane: read `detail.delta.*`; list existing proposed amendments on the revisions page |
| B9 | CRM main | `publish_amendment` refuses without `order_change_notices.approver_id` (`project_so_delta_service.py:791`) and no code path sets it (grep `app/services`, `app/api`): no amendment to a published SO can ever be published | Own lane: an approve action for the change notice |
| B10 | CRM #2173 | `autocount_last_modified` is refreshed only by the CRM's own write answers (:602, :689, :783); after any AutoCount-side change Update is refused DOC_STALE "open Compare first", and Compare (reconcile) does not refresh it | Refresh from the SS GET documents read before the PATCH, or in reconcile. Posted on #2173 |
| F11 | CRM #2173 | SS `IDEMPOTENCY_CONFLICT` is shown as "AutoCount refused: . Nothing was changed." (blank reason) | Map the code to a sentence (moot once B5's key fix is in, round 6) |
| F12 | CRM #2173 | `_since` (:129-135) reads AutoCount's zone-less `LastModified` as UTC; AutoCount stamps are Malaysia local (a 6 Nov 18:04 change reads "since 07/11/2026") | Treat zone-less stamps as +08:00 |
| F13 | SS | QT edit answers `mismatch FIELD_IGNORED remark2, remark3, remark4` although the requested change landed; the CRM shows it as "AutoCount answered: ignored: ..." | SS: do not send/compare untouched remarks |
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
| FXT-1106-PO1 (edits) | 12127 | SS edit: purchase agent set; row 12128 20 -> 21 (to change B3's key); E1/E2 splits | 12128 12 @ HQ, 12139 4 @ HQ (FromSO 12130), 12141 5 @ BRW-AM (FromSO 12131) |
| FXT-1106-PO2 (split) | 12132 | E1b split (blank agent) | 12133 1 @ HQ, 12146 2 @ HQ (FromSO 12135) |
| FXT-1106-PO3 | 12150 | SS create (B4 fixture, blank agent) + 2 splits | 12151 3 @ HQ, 12156 3 @ HQ (FromSO 12153), 12158 4 @ BRW-AM (FromSO 12154) |
| FXT-1106-SO3 | 12152 | SS create (fixture) | 12153 3 @ HQ, 12154 4 @ BRW-AM |
| QT-000006 | 12147 | E4 create, E5 update (CRM QT-2026-0001) | 12148 SRTKT38SS 5, 12149 SRTKT1631SS 2 |
| SO1 | 12159 | E6 create (CRM PSO-000001), ref edit (re-push), E7 update | 12160 SRTKT38SS 5, 12161 SRTKT1631SS 3 |

Nothing was deleted or cancelled (AutoCount has no delete door; cancel is refused).

## Staging setup gaps hit on the way (for the runbook, #2202)

Fresh create_all DB (not a dev copy): no `system_settings` row, no `tenant_modules`, no fulfilment-planning
warehouse, no migration-body seeds (replayed every migration's INSERTs), customers pushed before sales agents
(no agent link -> no derived location), agent refs must be `agent:<code>` (the SS sink's key), a project needs
a developer party (quotation recipient) and the customer PO an issuing party (SO debtor), and a project PO's
lines/delivery schedule only come from an AI read of a PDF (seeded by SQL here).

## Phase 2: linking on SS write API v2 (11 Nov 2026)

SS #230 (SS main 4193fdc4) turned on, for PO: link an existing whole row, change link, unlink, delete line, cancel
(DELETE by DocNo); QT/SO: delete line, cancel. SPO stays `VENDOR_UNSUPPORTED`. The 6 Nov refusals R1 (cancel), R2
(whole-row link), R3 (unlink / move) and R5 ("no delete door") are therefore no longer expected; they were true on
6 Nov against SS #224/#225. Stack: CRM main f6413b84 + #2223 2b9b0502 (local, never pushed), SS main 4193fdc4,
DBs `sorento_staging_acdb3` / `foundryx_service_acdb3`. Every write from the Stock Debt UI, read back with hapi;
SS `ac_api_call_log` shows 9 PUTs for the 5 writes, all 200.

| ID | Operation | Result | AutoCount read-back after | CRM side |
| --- | --- | --- | --- | --- |
| L1 | Link an existing WHOLE row: FXT-1111-PO-L row 12295 (3 @ HQ) -> FXT-1111-SO-L row 12298 | PASS ("Linked. FXT-1111-SO-L line 16 now covered by PO FXT-1111-PO-L (3).") | row replaced: new 12303 3 @ HQ FromSODtlKey 12298; 12296 untouched; Total 28.0 | open line linked `DB3:12297:12298` (B12 copy) |
| L1b | Whole row + relocate: row 12296 (4 @ HQ) -> SO-L row 12299 (BRW-AM) | PASS | new 12305 4 @ BRW-AM FromSO 12299; price 4.00, date 26/11 kept | as L1 |
| L2 | Change link: the L1 row -> FXT-1111-SO-L2 row 12301 ("Move PO to another sales order...") | PASS ("Moved. FXT-1111-SO-L2 line 16 now covered by PO FXT-1111-PO-L (3).") | new 12307 3 @ HQ FromSO 12301 | open line `DB3:12294:12307` linked to `DB3:12300:12301` |
| L3 | Unlink the L1b row | PASS ("Unlinked. FXT-1111-SO-L line 32 is no longer covered by PO FXT-1111-PO-L (4).") | new 12308 4 @ BRW-AM FromSO 0; qty, price, date kept; location stays BRW-AM | open line, no link |
| L4 | Split regression: FXT-HT-PO-A row 12172 (10 @ HQ) -> FXT-HT-SO-A row 12174, qty 3 | PASS | 12172 7 @ HQ + new 12310 3 @ HQ FromSO 12174; price 3.00, date 27/11 on both; Total 30.0 | 2 open lines matching |
| L5 | SPO actions | PASS (none offered; SS capability `VENDOR_UNSUPPORTED`) | n/a | Decide menu: Link / Unlink / Move only |
| P | Pull back into the CRM | PARTIAL: each AutoCount row has exactly one OPEN CRM line with the right qty, location, link; but see B12 | n/a | 4 extra cancelled "removed in AutoCount" lines on PO-L, two of them carrying the live refs 12307 / 12308 |

**B12 (CRM, #2223 service + ingest order):** during the link call SS pushes the read-back to the CRM ingest, which
retires the old line (its DtlKey is gone) and creates a new line for the new DtlKey; then
`stock_debt_po_link_service._apply` (`:391-395`) applies `replacedLines` and renames the retired line to the new
DtlKey. Each link / move / unlink therefore shows a line "removed in AutoCount", the CRM line id changes every time,
and a live ref can sit on an open and a cancelled line at once. Posted with fix options on #2223.

db3 documents written in phase 2: FXT-1111-PO-L (12294), FXT-1111-SO-L (12297), FXT-1111-SO-L2 (12300),
FXT-HT-PO-A (12171) and FXT-HT-SO-A (12173) via `reseed.sh A`. Evidence (screens, JSON, call log, CRM selects):
crew/state/files/AC-E2E-DB3/v2/ (private).

### Phase 2b: rerun on the B12 fix (11 Nov 2026)

Stack: #2223 head 3d5cbdb6 (contains main f6413b84, live on prod) + SS main 4193fdc4 (live). Fresh documents; every
step from the Stock Debt UI, read back in AutoCount, and the CRM PO lines checked after each step.

| ID | Operation | AutoCount | CRM PO lines | AutoCount after |
| --- | --- | --- | --- | --- |
| R1 | Whole-row link FXT-1111-PO-M row 12312 (3 @ HQ) -> FXT-1111-SO-M row 12315 | PASS | PASS (line eff6557f... kept, re-keyed to 12325) | 12325 3 @ HQ FromSO 12315; total 35.0 |
| R1b | Whole row + relocate: row 12313 (4 @ HQ) -> SO-M row 12316 (BRW-AM) | PASS | PASS (line b7e3a5d8... kept, re-keyed to 12327) | 12327 4 @ BRW-AM FromSO 12316 |
| R2 | Change link: 12325 -> FXT-1111-SO-M2 row 12318 | PASS | PASS (eff6557f... -> 12329, link `DB3:12317:12318`) | 12329 3 @ HQ FromSO 12318 |
| R3 | Unlink 12327 | PASS | PARTIAL (B13: line re-keyed to 12330 and open, but `from_so_line_ref` still `DB3:12314:12316`) | 12330 4 @ BRW-AM FromSO 0; qty, price, date kept |
| R4 | Split 3 of FXT-HT-PO-B row 12320 (10 @ HQ) -> FXT-HT-SO-B row 12322 | PASS | PASS (eede9267... kept, now 7; one new line for 12332) | 12320 7 @ HQ + 12332 3 @ HQ FromSO 12322; price 3.00, date 27/11; total 30.0 |

After every step: exactly one CRM line per AutoCount row, all open, none "removed", source_refs unique and equal to
AutoCount's DtlKeys; replaced rows keep their CRM line id. SO quantities unchanged. B12 is fixed. **B13** (posted on
#2223): `stock_debt_po_link_service.py:496` clears the link only when `FromSODtlKey is None`, but AutoCount returns
`0` for an unlinked PO row, so the CRM keeps the old `from_so_line_ref` after an unlink (the drill already shows the
SO line uncovered). Documents: FXT-1111-PO-M 12311, FXT-1111-SO-M 12314, FXT-1111-SO-M2 12317, FXT-HT-PO-B 12319,
FXT-HT-SO-B 12321. Evidence: crew/state/files/AC-E2E-DB3/v3/ (private). CI could not run (GitHub Actions billing
block); this db3 run is the proof.
