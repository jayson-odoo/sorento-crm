# PLAN: AutoCount end to end on db3 (AC-E2E-DB3)

Status: verification run complete 6 Nov 2026 (all UAC rows PASS or N/A, fixes landed on #2173 and SS #225); owner hand test pending (laneboard/scripts/2222.md). Verification lane, size M. Track: verification;
any trivial fix lands on the owning PR's branch after telling crew, never here.

Owner, 6 Nov 2026 ~16:00: "yes please for autocount end to end". Prove CRM + shared service (SS) + AutoCount
together on the db3 TEST book only, for every operation the AutoCount API lets us do.

UAC: `ac-e2e-db3-06nov-acceptance-criteria.md` (alongside).

## Pieces under test

| Piece | Where | State 6 Nov |
| --- | --- | --- |
| SS PO/SPO link, relocate, unlink | foundryx-shared-service #183 (AC-WRITE-LINK) | merged |
| SS QT/SO/PO/SPO create, edit, add line, link, unlink, relink | SS #191 (AC-WRITE-QTSO) | merged |
| SS fills `displayTerm` from the AutoCount debtor | SS #224 (SS-QTSO-DISPLAYTERM) | draft, head f087b87a, run locally, never merged here |
| CRM PO link UI on Stock Debt | CRM #2168 (AC-LINK-CRM-UI) | merged |
| CRM QT/SO create, update, cancel from project sales | CRM #2173 (AC-QTSO-CRM) | open, head 77f47a1b |
| CRM db3 staging kit (seed, runbook, SS contract) | CRM #2202 (AC-TEST-COMPANY) | open, head 1bca21eb |
| CRM re-keyed SO line is not a removal | CRM #2219 (AC-REKEY-SAME-LINE) | open, head 8670e71a |

## ARCHITECTURE (what runs where)

- **CRM stack**: a local-only branch `local/ac-e2e-db3-stack` = origin/main + #2173 + #2202 + #2219 merged
  locally (never pushed). Backend, worker and one frontend dev server, on ports outside the crew copy
  ranges (3100-3189, 8100-8189, 8200-8289). Env file `.env.staging` via `SORENTO_ENV_FILE`.
- **CRM database**: `sorento_staging_acdb3`, a fresh migrated database (template: an empty migrated base),
  NOT a copy of the shared dev DB (`sorento_prod_1104` is a 33 GB prod restore; lanes never copy or query
  prod copies). Masters and documents arrive from db3 through SS pushes and CRM pulls, so the copy holds
  no real customer data. Seeded with `scripts/staging/seed_db3_staging.py` (#2202): company SRT_DB3,
  `foundryx-esb` re-pointed at the local SS, push key, AutoCount switches ON, example.com superadmin.
- **SS**: own worktree at #224 head f087b87a, own database and Redis index, own port. Company SRT_DB3
  bound to db3 only (contract `CONTRACT-db3-local-staging-ss.md`). The crew SS on :8114 is not touched.
- **AutoCount**: hapi `https://hapi.sorento.cc.cd/api/db3/...` (reads open; writes only through SS, whose
  hardcoded guard allows the db3 path only). The MacBook Air tunnel (14331/14332) is SQL access to
  db1/db2 and is not needed for db3 (no SQL access to db3 exists).
- **Evidence**: every write is checked against AutoCount's own read API (GET by DocNo / byLastModified),
  not CRM state alone. Request, response, before/after rows go to a test report.

## Steps

1. Plan + UAC committed (this file).
2. Stand up SS at #224 head (own DB, migrations, company SRT_DB3 -> db3, write connection, keys).
3. Stand up CRM stack branch, create `sorento_staging_acdb3`, migrate, seed (dry run, then apply).
4. Pull db3 masters + docs into SRT_DB3 (SS poll / pushes; CRM pulls). Pick test fixtures: a db3 debtor
   with a credit term, items, a PO and SO pair for link tests.
5. Drive the real UI through each operation in the UAC (headless browser, Sonnet helper; lead verifies).
   After each write: hapi read-back, CRM state, screenshot.
6. Pull AutoCount -> SS -> CRM after the writes: no duplicate lines, no false "removed in AutoCount".
7. PASS/FAIL table + bugs (crew-note with file:line + minimal fix proposal) in
   `documentation/integrations/autocount/test-report-2026-11-06-e2e-db3.md`.
8. Owner hand-test script at `laneboard/scripts/<PR>.md`.

## Rules

- db3 only. Never db1/db2 live books, never prod.
- No product code in this lane. A bug found is reported on the owning PR; trivial fixes there only after
  telling crew.
- Every created/edited db3 document is listed in the test report's inventory (no deletes; AutoCount has
  no delete door anyway).

## Phase 2: SS write API v2 rerun (crew GO 11 Nov 2026)

SS #230 (main 4193fdc4) adds link existing row, change link, unlink, delete line, cancel (DELETE by DocNo) for QT/SO/PO;
SPO stays VENDOR_UNSUPPORTED. Owner wants LINKING results by morning. Resume notes (account may switch):
- Handoff with every path, env and secret location: `.claude/handoffs/20261111T0000Z-ac-e2e-db3-v2.md` (worktree-local).
- Stack: CRM worktree `sorento_crm-ac-e2e-db3-stack` on a new local branch = origin/main + #2223 head (never pushed),
  DB `sorento_staging_acdb3`; SS worktree `foundryx-shared-service-ac-e2e-db3` on SS main 4193fdc4, DB
  `foundryx_service_acdb3`. Fixtures: `crew/state/files/AC-E2E-DB3/reseed.sh <TAG>`; read-back `ac_read.py` there.
- Linking cases: L1 link an existing whole row, L2 change link, L3 unlink, L4 split + relocate regression, L5 SPO
  refused, P pull-back; each: AutoCount read-back, SO qty before/after, SS `ac_api_call_log` rows, screenshot.
- Progress (update as it lands): stack rebuild [x] (CRM cf5250c6 = main f6413b84 + #2223 2b9b0502; SS main 4193fdc4; fixtures PO-L 12294, SO-L 12297, SO-L2 12300), L1 [x] L1b [x] L2 [x] L3 [x] L4 [x] L5 [x] PASS, P partial (B12 on #2223), docs [x]; QT/SO Q1-Q3 wait for #2173 (AC-QTSO-CRM-2).
