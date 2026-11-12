# PLAN: Project import with a value mapper (lane PROJECT-MIGRATION-TOOL)

Status: Build, slice 1 (backend) in progress. Card v3 + mock v1 approved by the owner on 13 Nov, 00:02 ("ok make sure the imoprt works with the file I gave you"). Track: L (lead pattern; new screen, one additive migration, new permissions, upload surface). One branch, one PR (#2385); slices land as commits.

Contract: `CARD-project-migration-12nov.md` (v3 sections win) and the UAC `project-import-12nov-acceptance-criteria.md` (AC-PI-01..51).
Masked file shape: `project-import-file-shape.md`. Mock: `documentation/mockups/PROJECT-IMPORT/index.html`.

## Slices

1. **Backend.** Tests first (tester), then code (coder):
   - the fixture builder, the reader, value maps (model + migration), the run service (create / columns / lines / preview / apply / revert), the SO link function, routes, the job, permissions;
   - kill tests on: the permission check, company scope, "no similarity match", preview writing nothing, create-only, and no notification.
2. **Frontend.** Vitest first, then code:
   - the menu entry, runs list, Create dialog, run page with steps, Columns, Values tabs, Preview, Results / History / Revert;
   - a browser pass at 1280 and 375 px on seeded masked data.
3. **Review and DoD.** Reviewer (opus/high), security-reviewer (opus/high), user guide, crew-tests, hand-test script, the real-file dry run by crew.

## Backend contract (tests are written against THIS; the coder may not change it without the lead)

### Model and migration

- `app/models/project_import.py`: `ProjectImportValueMap`, table `projects.import_value_maps`, `CompanyScopedMixin`.
  - Columns:
    - `id` uuid str pk;
    - `company_id`;
    - `kind` String(16): `customer` | `project` | `developer` | `person`;
    - `customer_value_key` String(255) NOT NULL, default `''` (projects only; `''` otherwise, so the unique key has no nulls);
    - `value_key` String(255) NOT NULL;
    - `value_text` Text;
    - `action` String(8): `link` | `create` | `skip` | `none`;
    - `target_id` String(64) nullable;
    - `new_title` Text nullable;
    - `set_by_user_id` String FK `users.id` SET NULL;
    - `set_at`, `created_at`, `updated_at`.
  - Unique key: (company_id, kind, customer_value_key, value_key).
- Migration `alembic/versions/pimp_0001_project_import_value_maps.py`:
  - `down_revision = "acqs_0001_project_ac_write"` (re-parent with `./scripts/alembic-reparent.sh` before the PR is ready);
  - additive only, `CREATE TABLE IF NOT EXISTS`-safe;
  - revision id at most 32 characters.
- No other table changes. The run is an `import_jobs` row:
  - `job_type = "project_po_register"`;
  - `job_metadata` holds `run_no` (`PIM-0001`, per company, count + 1), `phase` (`draft` | `previewed` | `importing` | `imported` | `reverted`), `sheets` (ticked names), `columns` ({field: header | "ignore"}), `preview_counts`, `result_counts`, `imported_at`.
  - The file is stored like every import (`source_file_key` / `source_file_provider`).

### Field keys (column step)

`ps_number`, `salesperson`, `customer_service`, `customer`, `project_name`, `developer`, `po_number`, `po_value`, `po_date`, `amended_date`, `schedule`, `delivery`, `outstanding`, `so_number`, `remarks`.
Required: `ps_number`, `customer`, `po_number`. Header aliases are seeded for the file's own headings under doc type `project_po_register` (in `import_alias_service` defaults or the migration; coder's choice, tested by AC-PI-09).

### Modules

- `app/services/project_import/reader.py`
  - `fold(value) -> str`: trim, collapse whitespace, upper. `None` gives `''`.
  - `probe(content: bytes) -> list[SheetProbe]`. A `SheetProbe` has `name` (as written), `name_trimmed`, `has_ps_heading`, `row_count` (PS rows with a customer), `columns: list[{position, header, sample, field}]`.
  - `read_rows(content: bytes, *, sheets: list[str], columns: dict[str, str]) -> ReadResult`. A `ReadResult` has `rows: list[SourceRow]` and `sheet_errors: list[{sheet, code, heading}]`.
  - `SourceRow` (dataclass): `sheet`, `row_number`, `ps_number`, `salesperson`, `customer_service`, `customer`, `project_name`, `developer`, `po_number: str | None`, `po_number_numeric: bool`, `po_value: Decimal | None`, `value_dash: bool`, `po_date: date | None`, `amended: date | str | None`, `schedule: str | None`, `delivery: date | str | None`, `outstanding: str | None`, `so_cell: str | None`, `so_numbers: list[str]`, `remarks: str | None`.
  - Reuse `normalize_header` (`app/services/import_alias_service.py:34`) and `every_sheet_rows` (`app/services/scm/outstanding_reader.py:300`).
  - Promote `_to_date` (`outstanding_reader.py:157`) to a public `to_date`, keeping the private name as an alias.
- `app/services/project_import/service.py`
  - `create_run(db, *, company_id, user_id, filename, content) -> ImportJob`: 422 on a bad upload (AC-PI-08).
  - `save_columns(db, run, *, sheets, columns, user_id) -> None`: saves aliases (AC-PI-10).
  - `list_lines(db, run, *, kind, status=None) -> list[dict]`. Each line has `kind`, `customer_value_key`, `value_key`, `value_text`, `customer_text`, `rows`, `action`, `target_id`, `target_label`, `new_title`, `source` (`saved` | `so` | None), `set_by_name`, `set_at`, `status` (`todo` | `set`).
  - `set_line(db, run, *, kind, value_key, customer_value_key="", action, target_id=None, new_title=None, user_id) -> dict`.
  - `bulk_set(db, run, *, kind, keys: list[tuple[str, str]], action, target_id=None, new_title=None, user_id) -> list[dict]`: all or nothing, calling `set_line` once per key.
  - `preview(db, run, *, user_id) -> dict`, `apply(db, run, *, user_id) -> dict`. Both are ONE internal `_run(..., persist: bool)`.
    - Report: `{"counts": {outcome: n}, "codes": {code: n}, "rows": [{sheet, row_number, ps_number, customer, project, po_number, po_date, outcome, codes: [..], message}]}`.
    - Outcomes: `created`, `updated`, `unchanged`, `skipped`, `needs_review`, `error`.
  - `start_import(db, run, *, user_id) -> str`: enqueues `process_project_import` on the `imports` queue and returns the job id.
  - `revert(db, run, *, user_id) -> dict`: `{"removed": {entity_type: n}, "kept": [{entity_type, label, reason}]}`.
- `app/services/project_so_link.py`: `link_sales_order_to_project(db, *, project_sales_order, project, purchase_order) -> None`, the ONE shared function (AC-PI-29). It refuses with 409 when the order is already on another project.
- New outcome codes go in `app/services/import_outcome_codes.py`, with `label_for` labels in plain words:
  - `project_and_po_created`, `po_added`, `no_project_name`, `placeholder`, `other_year`, `cancelled`, `mapped_skip`;
  - `project_unmapped`, `customer_unmapped`, `developer_unmapped`, `customer_conflict`, `customer_same_shop_so_used`, `developer_conflict`, `registration_lock`, `po_number_taken`, `so_on_other_project`;
  - `ps_duplicate_in_file`, `ps_duplicate_in_crm`, `changed_in_file`, `so_linked`, `so_not_synced`, `po_number_numeric`;
  - `developer_exists`, `date_other_year`, `date_other_month`, `owner_defaulted`, `clash_check_skipped`, `missing_header`, `revert_kept_edited`.
- Task `process_project_import(job_id)` in `app/tasks/import_tasks.py`: calls `service.apply`. Restart the worker after editing it.
- The run is the audit actor: `stamp_actor(AuditActor(actor_type="user", user_id=..., job_id=run id))` (`app/audit_context.py:70`).
- Revert in the gear menu: register the record action `project_import_run.revert` in `app/services/record_actions.py` and park it through the existing `POST /api/v1/pending-actions` (`app/api/v1/system/pending_actions.py`). The handler calls `service.revert`.

### Routes: `app/api/v1/projects/project_import.py`, mounted with the projects routers

| Method | Path (under `/api/v1/projects/import`) | Permission |
|---|---|---|
| GET | `/runs` (DataGrid: page, limit, sort, dir, query; status, uploaded_by multi) | `projects.import.view` |
| POST | `/runs` (multipart `file`) gives 201 + run with `sheets` probe | `projects.import.run` |
| GET | `/runs/{run_id}` | view |
| PUT | `/runs/{run_id}/columns` `{sheets, columns}` | run |
| GET | `/runs/{run_id}/lines?kind=&status=` | view |
| PUT | `/runs/{run_id}/lines` `{kind, customer_value_key, value_key, action, target_id, new_title}` | run |
| PUT | `/runs/{run_id}/lines/bulk` `{kind, keys:[[customer_value_key, value_key]], action, target_id, new_title}` | run |
| POST | `/runs/{run_id}/preview` gives the report counts | run |
| GET | `/runs/{run_id}/rows` (DataGrid; outcome, code, sheet multi) | view |
| POST | `/runs/{run_id}/import` gives 202 `{job_id}` | run |

- Revert goes through pending actions (above).
- `projects.import.view` and `projects.import.run` are added to `app/rbac/permission_registry.py`.
- A run of another company gives 404.

## Fixture (AC-PI-50)

`sorento_crm_backend/tests/fixtures/project_import/build_so_summary.py`: `build_workbook(path=None) -> bytes`, built with openpyxl and fully deterministic. It writes a FULL-SIZE masked workbook with the exact structure of `project-import-file-shape.md`:

- the 9 sheets in order, with the trailing-space names;
- headers verbatim;
- PS26-0001..1398 contiguous, 1282 data rows + 116 AUG placeholders;
- the total formula row, the roll-up block, the Q8 junk;
- the SUMMARY sheet with merged cells.

It seeds every dirty pattern at known PS numbers (see the shape doc's counts). It also exports `EXPECTED`, a dict of the preview counts per outcome and code that a test asserts, so the builder is the single source of the expected numbers. Fake names only (`CUSTOMER 001 SDN BHD`, `PROJECT 001 SAMPLE NAME`, `DEVELOPER 001`, `ALVIN`). No binary xlsx is committed.

## Test list (tester writes these RED first)

Backend, Postgres via `tests/_pg_fixture.py`, `SORENTO_ENV_FILE=.env.ci-tests`:

| File | Covers |
|---|---|
| `tests/test_project_import_reader.py` | AC-PI-01..08 (in-memory openpyxl books) |
| `tests/test_project_import_lines.py` | AC-PI-12..19 (fold, pairs, saved maps per company, no similarity match, bulk all-or-nothing, To do count, From SO, same-shop) |
| `tests/test_project_import_run.py` | AC-PI-20..36 (preview writes nothing, create/po_added, create groups, developer, registration lock, PO fields, notes order, cancelled, date flags, SO link / not synced / other project, duplicates, create-only, idempotent second run, savepoint per row, no notification + invoiced total unchanged, ledger rows) |
| `tests/test_project_import_revert.py` | AC-PI-37..38 |
| `tests/test_project_import_api.py` | AC-PI-08..11, 39..41 (403 without permission, 404 cross-company, 422s, no names in logs) |
| `tests/test_project_import_fixture.py` | AC-PI-50 (full fixture preview equals `EXPECTED`) |

Frontend vitest (slice 2): `services/projectImportService.test.ts`, the Values tab (To do count = filter, bulk calls the line endpoint), the Preview filters, the menu entry gated by permission.

Global guards: `tests/test_schema_uuid_id_principle.py`, `tests/test_list_pagination_limit.py`.

## Reuse (crew-done lists these)

`normalize_header`, `every_sheet_rows`, `to_date` (promoted), `ImportOutcome` + codes, `import_jobs` / `import_job_rows`, `import_field_alias`, `register_project(skip_clash_check=True)`, `create_po`, `create_party` (only for a "create" developer line), `ProjectSOAdoptionService.adopt_for_migration`, `ledger_family_key` + `customer_group_id`, pending actions + `record_actions`, `stamp_actor`.
FE: `FileDropzone`, `WizardSteps`, `ImportColumnMapper`, `DataGrid` + `buildDataGridParams`, `SearchableSelect`/`SearchableMultiSelect` (customer via `useFetchCustomerOptions`), `userSelectService`, `OutcomeBreakdownCard`, `ImportJobRowsCard`, `useImportJobDrawer`, `DeferredActionButton`, `AuditTrail`, `PageHeader`, `RecordNavigation`, `formatDate`.

## DoD (beyond PRINCIPLES)

- [ ] red-proof and kill-proof posted
- [ ] crew-tests line on the exact head
- [ ] reviewer + security-reviewer clean
- [ ] browser pass at 1280 / 375 on seeded masked data
- [ ] **real-file dry run by crew**: crew runs a preview of the owner's real TOTAL SALES ORDER SUMMARY 2026 file on a local test copy and posts masked counts per outcome and code. Every `error` row is explained or fixed before the hand test, and the hand test uses that file.
- [ ] user guide `documentation/user-guides/` page for Project import
- [ ] hand-test script `laneboard/scripts/2385.md`
- [ ] standing rules self-check

## Frontend contract (slice 2; tests are written against THIS)

Backend as built (head 8094525d):
- `/api/v1/projects/import/runs` returns `{data|items, total}`: read the route.
- `/runs/{id}` gives the run, with `sheets`, `columns`, `missing_columns`, `preview_counts`, `preview_codes`, `result_counts`, `result_codes`.
- `/runs/{id}/lines?kind&status&page&limit&sort&dir&query` returns `{items, total}`.
- `/runs/{id}/lines/summary` returns `{kind: {total, todo}}`.
- `PUT /runs/{id}/lines`, `PUT /runs/{id}/lines/bulk`, `POST /runs/{id}/preview`.
- `/runs/{id}/rows?outcome&code&sheet&sort&dir&page&limit&query`.
- `POST /runs/{id}/import` returns 202 `{job_id}`.
- Revert is the pending action `project_import_run.revert`.

Files:
- `app/(protected)/project-sales/_shared/services/projectImportService.ts`: one function per route above. It uses `lib/api-client`, `extractApiError` and `buildDataGridParams`, and never hand-builds `URLSearchParams` for page/limit/sort/dir/query.
- `app/(protected)/project-sales/_shared/hooks/useProjectImport.ts`: react-query reads plus mutations. On success, invalidate and toast. On error, the extracted message and a toast.
- `app/(protected)/project-sales/import/page.tsx` + `components/ProjectImportListClient.tsx`: the runs DataGrid, plus `components/CreateImportDialog.tsx`.
- `app/(protected)/project-sales/import/[runId]/page.tsx` + `components/ProjectImportRunClient.tsx`, which holds `ColumnsStep.tsx`, `ValuesStep.tsx`, `PreviewStep.tsx` and `ResultsView.tsx`.
- `config/menu.config.tsx` (both trees): Project Sales > Configuration > "Project import" at `/project-sales/import`, permission `projects.import.view`. Also add `projects.import.view` to `_shared/projectViewPermissions.ts`, so a user holding only that permission reaches the page.

Behaviour (mock v1 is the picture):
- The run page shows the step from `status`: draft goes to Columns, or to Values once the required columns are set; previewed goes to Preview; importing / imported / reverted go to Results.
- Values: the tab label shows "N to do" from `/lines/summary`; the "To do" filter calls `lines?status=todo`; the bulk "Set to" calls `PUT lines/bulk` ONCE with every ticked key.
- Preview: tiles from `preview_counts`; Import is the only primary button; Outcome / Reason / Sheet are `SearchableMultiSelect` filters; a needs-review row click switches to Values on the blocking kind.
- Results: `OutcomeBreakdownCard` + `ImportJobRowsCard` (or their data shape), tabs Results | Values | History (`AuditTrail`), and Revert as a `DeferredActionButton` in the gear menu.
- Every date goes through `formatDate` (dd/mm/yyyy). No UUID is rendered.
