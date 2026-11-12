# UAC: Project import (lane PROJECT-MIGRATION-TOOL)

Source of truth: `CARD-project-migration-12nov.md` v3 (owner approved card v3 + mock v1, 13 Nov 00:02: "ok make sure
the imoprt works with the file I gave you"). Mock: `documentation/mockups/PROJECT-IMPORT/index.html`.
The v3 open questions take the card's recommendations: admin-only `projects.import.run`, revert with no time limit
(edited records always kept), first real run on a dev copy by crew.

Terms:
- **Folded** value: trimmed, inner whitespace collapsed to one space, upper-cased. Nothing else is changed.
- **Run**: one uploaded file, one `import_jobs` row with `job_type = project_po_register`.
- **Line**: one distinct folded value of one kind (customer, project pair, developer, person) in a run.

## Reader (workbook)

- AC-PI-01: Columns are found by HEADING (`normalize_header`), not by position, on every sheet. A file with the columns in another order reads the same.
- AC-PI-02: A monthly sheet missing a required heading (PS number, Customer, PO number) gives ONE sheet-level `missing_header` error naming that heading. The other sheets are still read.
- AC-PI-03: Sheet names are matched after trimming (`MAC'26 ` = `MAC'26`). A sheet with no PS-number heading (`SUMMARY JAN-JUN`) is listed as "no PS numbers", is unticked by default, and gives no rows.
- AC-PI-04: A row is a data row only when column A (trimmed) matches `^PS\d\d-\d{4}$`. Total rows, roll-up blocks and their titles are not counted as rows at all.
- AC-PI-05: A PS row with no customer is `skipped: placeholder`.
- AC-PI-06: A PS row whose year part is not `26` is `skipped: other_year` (owner d4).
- AC-PI-07: Cell quirks read correctly:
  - a header with line breaks and padding;
  - an integer PO number becomes its digits as text and is flagged `po_number_numeric`;
  - `-` in TOTAL VALUE gives no amount;
  - dates as real Excel dates;
  - text dates kept as typed;
  - a comma SO list (`,` or `, `) gives each SO;
  - junk whitespace cells are ignored.
- AC-PI-08: Invalid uploads are refused with HTTP 422 and a plain message: not an xlsx, over 10 MB, unreadable, or no sheet with a PS-number heading.

## Columns step

- AC-PI-09: The header probe returns, per selected sheet, each heading as written plus one sample. Each heading resolves through `import_field_alias` under doc type `project_po_register`.
- AC-PI-10: Saving a column choice stores it as an alias, so a second file with the same headings needs no column choice. `ignore` is a saved choice.
- AC-PI-11: Preview is refused (422 naming the field) while PS number, Customer or PO number has no column.

## Values step

- AC-PI-12: Lines are listed per kind with row counts:
  - customer: folded column D;
  - project: (folded customer, folded project) pair, from rows that have a project name only;
  - developer: folded column F;
  - person: folded salesperson and folded customer-service values.
- AC-PI-13: Rows with no project name are `skipped: no_project_name` (owner d1). They are listed by PS number in the preview and never appear as Projects lines.
- AC-PI-14: A line whose folded value (and, for projects, folded customer) has a saved map for the SAME company is prefilled with that choice and shows who set it and when (dd/mm/yyyy). Two things are always "To do":
  - a value never saved;
  - a value saved only by ANOTHER company.
- AC-PI-15: Nothing is linked by similarity. There is no fuzzy, prefix or contains match anywhere. A different spelling is a different line.
- AC-PI-16: Setting a line stores (or replaces) one `import_value_maps` row with `set_by_user_id` and `set_at`. The allowed actions per kind:

  | Kind | link to | create | skip | none |
  |---|---|---|---|---|
  | customer | an existing customer | no | yes | no |
  | project | an existing project | yes, with `new_title` | yes | no |
  | developer | a developer party | yes | no | yes |
  | person | a user | no | no | yes |

  The linked record must belong to the run's company (otherwise 422).
- AC-PI-17: Bulk set applies one action to every listed line by calling the same function as a single set, once per line. If one line is invalid, nothing is saved and the error names that line.
- AC-PI-18: The "to do" count per kind equals the number of lines the "To do" filter returns.
- AC-PI-19: Customer from the sales order:
  - When every SO number on a customer's rows resolves in the synced `sales_orders` (same company) to ONE customer, that line reads "From SO" and needs no human.
  - If a human also mapped it to a different customer: when both customers are the SAME shop (same `customer_group_id`, or the same `ledger_family_key(customer_name)`), the SO customer is used and counted as `customer_same_shop_so_used`.
  - Otherwise the rows are `needs_review: customer_conflict`.

## Preview and import (same function)

- AC-PI-20: Preview runs the exact import function and rolls back. Afterwards there is no new project, PO, party, project sales order or audit row. Only the run's own bookkeeping is kept: its report rows and its "Previewed" History entry (AC-PI-48a).
- AC-PI-21: Import of a row with all links set creates:
  - the project (only on the first row of a "create" group);
  - the PO;
  - the SO links.

  The outcome is `created` with the code `project_and_po_created`, or `po_added` when the PO goes onto an existing or already-created project.
- AC-PI-22: Lines set to "create" with the same `new_title` (folded) in one run become ONE project.
  - After the run, each such line is rewritten to "link" to the created project, so a later file adds to it.
  - The project is made with `register_project(skip_clash_check=True)`, recorded as `clash_check_skipped` on the row.
  - `admin_ref` = the lowest PS number of its rows.
  - `sales_profile.customer_id` = the row customer; `sales_profile.developer_name` = the column F text.
  - Owner = the user mapped for the salesperson on its lowest PS row. Without a mapping, the owner is the importing user, flagged `owner_defaulted`.
  - No template, no lead source.
- AC-PI-23: Developer:
  - link uses that party;
  - "create" makes exactly one developer party per line, named as the line's text, and rewrites the line to link;
  - "none" gives no developer.
  - Rows of one new project whose developer lines differ are `needs_review: developer_conflict`.
- AC-PI-23a: A "create" developer line whose name an active party already carries is never linked to that party silently. This would happen because `create_party` returns an existing same-name party.
  - The line's rows are `needs_review: developer_exists`, and the message names the existing party.
  - Nothing is created or linked.
  - The person then links the line to that party, or keeps "create" after the party is renamed.
  - This refusal is the only place a name is compared, and it never links anything.
- AC-PI-24: A new project that would hit the registration lock (same company + developer + normalised title as a staff or approved project) is `needs_review: registration_lock`. The message names that project's code. Nothing is bypassed.
- AC-PI-25: The PO gets:
  - `po_number` as text;
  - `po_date` as written;
  - `po_amount`;
  - `admin_ref` = the PS number;
  - `sales_person` = column B trimmed;
  - `po_source = contractor_direct`;
  - `issuing_party_id` = an existing party whose `customer_id` = the row customer, if exactly one exists, otherwise null.

  No party is ever created from a customer. The PO status is `draft`.
- AC-PI-26: PO notes, one line each, in this order, only when present:
  1. `CS: <text>`
  2. `Amended: <text as typed>`, or a real date as dd/mm/yyyy
  3. `Schedule: <text as written>` (owner d2: no flag, no logic)
  4. `Delivery: dd/mm/yyyy` for a real date, or `Delivery: <text as typed>`
  5. `Outstanding: <text>` (on hold)
  6. `Waive transport charge` for any `WAIVE TRAN*` / `WAIVE TRAS*` / `WAIVE TRASN*` spelling
  7. `SO note: <text>` for a non-SO text in column N, such as `refer PS26-0022`
  8. `Remarks: <text>` for any other remark
- AC-PI-27: Cancelled rows are `skipped: cancelled` and listed by PS number. A row is cancelled when column H is `-`, or column M, N or O starts with `CANCEL` (case-insensitive).
- AC-PI-28: Date flags: a PO date outside 2026 is flagged `date_other_year`; a PO date in a month other than the sheet's month is flagged `date_other_month`. Both rows are imported as written.
- AC-PI-29: SO links:
  - each SO number that resolves to a synced `sales_orders.so_number` (same company) is adopted (`adopt_for_migration`), then linked to the project and the PO through ONE new shared function `link_sales_order_to_project`;
  - an SO not found is flagged `so_not_synced` and the PO is still imported;
  - on a later run, a now-synced SO of an already-imported row is linked: outcome `updated: so_linked`;
  - an SO already linked to ANOTHER project is `needs_review: so_on_other_project` and is not moved.
- AC-PI-30: Identity and duplicates:
  - a PS number already on a PO of the same company is `unchanged` when every supplied field is equal;
  - otherwise it is `unchanged` with the flag `changed_in_file` naming the fields, and NOTHING is written;
  - a PS number twice in the file is `error: ps_duplicate_in_file` on both rows;
  - two CRM POs with the PS number is `error: ps_duplicate_in_crm`;
  - a PO number already on the target project under another PS number is `needs_review: po_number_taken`.
- AC-PI-31: Create-only: no existing project or PO field is ever updated, and a blank cell never clears anything. Two exceptions:
  - the SO link of AC-PI-29;
  - the CRM's own PO rule: the first PO added to an existing linked project moves it to "PO received" and Won (`create_po`). Revert removes the PO but does not move the status back, because the PO was real (security N6, review minor 3).
- AC-PI-31a: A bulk "create" on project lines without a common title gives each line its own title, so N lines make N projects. Lines become one project only when a person gives them the same title (review M5).
- AC-PI-31b: A PO date given as unreadable text imports with no date and is flagged `po_date_unreadable`. A column N cell holding an SO number and text keeps both: the SO is linked, and the text goes into the notes.
- AC-PI-32: Importing the same file twice: the second run has zero created and zero updated rows, every imported row is `unchanged`, and the project and PO counts are equal before and after.
- AC-PI-33: One bad row never fails the batch: each row runs in a savepoint, a row error is reported, and the rest of the batch goes on. Rows that need review are left out and counted in the result notice.
- AC-PI-34: No notification, email, WhatsApp, outbound message or project task is written by an import. The shared invoiced sales total (`app/services/sales/invoiced_sales.py`) is unchanged.
- AC-PI-35: Every created record (project, sales profile, PO, party, project sales order) has an `import_job_rows` row under the run with `entity_type` and `entity_id`. The run's counts match the rows.
- AC-PI-36: The import runs as a queued job on the `imports` queue. Its status reads through the existing jobs endpoints, and preview is synchronous.

## Revert

- AC-PI-37: Revert removes every record the run created, children first. These are kept and reported as `revert_kept_edited`:
  - a record updated after the run finished;
  - a record that has a child record not created by the run (a quotation, another PO).

  The run status becomes `reverted`.
- AC-PI-37a: These are also kept as `revert_kept_edited`:
  - a record with ANY child row the run did not create (tasks, samples, PO versions, delivery schedules, order inquiries, amendments and every other cascading child);
  - a PO whose SO was adopted before the run.

  Revert puts back only the lines the run itself rewrote from "create" to "link". Any other line whose target was removed is deleted and reads "To do" again (security B1, review RB1).
- AC-PI-38: A second revert of the same run changes nothing. A preview-only run cannot be reverted.

## Access

- AC-PI-39: Permissions:
  - Reading runs, lines and results needs `projects.import.view`.
  - Creating a run, setting lines, preview, import and revert need `projects.import.run`.
  - Both are in `app/rbac/permission_registry.py` and granted to admin by default.
  - A user without the permission gets 403.
- AC-PI-40: Runs and maps are company-scoped. A run or map of another company reads as 404, and its saved maps are never offered.
- AC-PI-40a: Upload limits and import safety:
  - an upload whose uncompressed size, compression ratio, declared sheet size, rows or sheet count exceeds the caps is refused with a 422;
  - person targets must be active users of the run's company;
  - the import job is queued only after the request commits;
  - a redelivered job never changes an imported run;
  - a parked revert re-checks `projects.import.run` when it commits;
  - column choices are saved only for headings in the run's file.

  An import-only user sees the names of the company's projects, customers and parties in the pickers. That is accepted: the tool is admin-only (security N5).
- AC-PI-41: No log line or error message carries a customer, project or person name beyond what the screen shows the same user.

## Screen (mock v1)

- AC-PI-42: Project Sales > Configuration > Project import, in both menu trees, gated by `projects.import.view`.
- AC-PI-43: The runs list is the standard DataGrid:
  - one toolbar row: Search, Filters (Status, Uploaded by: multi-select), Columns, Create;
  - every column sorts on the server;
  - single-line rows;
  - clicking a row opens the run;
  - empty state per mock A0.
- AC-PI-44: Create dialog: `FileDropzone` (xlsx only) and sheet ticks with row counts. Next opens the run page.
- AC-PI-45: Run page:
  - header: run no. + status pill, file name subtitle, pager, one main button;
  - `WizardSteps` Columns > Values > Preview > Import;
  - Columns uses `ImportColumnMapper`.
- AC-PI-46: Values: line tabs with "N to do" counts.
  - Each tab is a DataGrid: Value in file, Rows, Linked to (picker), Set by.
  - Bulk "Set to" acts on ticked lines.
  - Customer picker = `SearchableSelect` + `useFetchCustomerOptions` (the register form's customer picker; `CustomerDebtorCombobox` is the portal's free-text debtor box); others = `SearchableSelect`.
- AC-PI-47: Preview:
  - outcome tiles, a rows DataGrid (Sheet, Row, PS no., Customer, Project, PO no., PO date, Outcome, Reason);
  - Outcome / Reason / Sheet are multi-select filters;
  - clicking a needs-review row opens the blocking line;
  - Import is the one main button.
- AC-PI-48: Results: breakdown by reason (`OutcomeBreakdownCard`), rows (`ImportJobRowsCard`), and tabs Results | Values | History (`AuditTrail`). Revert sits in the gear menu as a `DeferredActionButton` countdown with Cancel and no confirm dialog.
- AC-PI-48a: The run's History tab lists one entry per action: Uploaded, Columns saved, Value linked (per kind, bulk included), Previewed, Imported, Reverted.
  - Each entry shows who and when, through `GET /api/v1/audit/logs?entity_type=project_import_run`.
  - It is readable with `projects.import.view` alone.
  - No ids or file values appear in the action text.
  - Reason labels come from the API (`labels` on report rows, `code_labels` on the run); the frontend keeps no copy of the label table.
  - The Project Sales layout lets `/project-sales/import` through on `projects.import.view` alone; every other Project Sales page keeps its own gate.
- AC-PI-49: Every date reads dd/mm/yyyy via `formatDate`. No UUID shows anywhere. Usable at 375 and 1280 px.

## The owner's file

- AC-PI-50: A masked fixture builder (`sorento_crm_backend/tests/fixtures/project_import/build_so_summary.py`) reproduces the shape in `documentation/plans/project-sales/project-import-file-shape.md`:
  - the 9 sheets in order, SUMMARY in the middle, trailing-space names;
  - headers verbatim with line breaks and padding;
  - Q8 junk, the total formula row, the roll-up block, AUG placeholders;
  - every dirty pattern.

  A test runs the full preview on it and asserts the exact expected counts per outcome and code.
- AC-PI-51 (DoD): crew runs a dry run of the REAL file on a local test copy and posts the masked counts. Any row that errors or reads wrong is fixed before the hand test.
