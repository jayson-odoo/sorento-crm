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
