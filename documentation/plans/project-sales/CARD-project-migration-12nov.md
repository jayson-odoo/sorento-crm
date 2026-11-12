# CARD: project import from the TOTAL SALES ORDER SUMMARY workbook (lane PROJECT-MIGRATION-TOOL)

Status: behaviour card v2 (Gate 1). Crew answered Q1-Q4 from prior owner rulings (section "Crew answers" below supersedes any rule above it); owner decisions d1-d5 pending; PO issuer data request answered (interim rule stands). No code yet. Track: L (lead pattern).
No screen is planned, so there is no mock (Gate 2 is only needed if the answers below add an upload screen).

All examples are the MASKED shape crew sent (fake names, fake amounts). Nothing real is in this file.

## What is true today (origin/main aa824637, read in this lane)

- No project importer exists. The importer patterns to copy:
  - preview and apply share one code path: `customer_import_service.py:189` `preview()` and `:199` `apply()` both call `_run()` `:217`. A blank cell means "not supplied" (`_changes()` `:665-692`).
  - row outcomes: `ImportOutcome` `import_outcome.py:65` and the code constants in `import_outcome_codes.py:15-174`.
  - the per-run ledger: `import_jobs` / `import_job_rows` (`app/models/job.py:33`, `:84`). Each ledger row has `row_number`, `outcome`, `code`, `message`, `identity`, `entity_type` and `entity_id`.
  - header normalising: `normalize_header` `import_alias_service.py:34` (NFKC, strips line breaks and padding).
  - multi-sheet reading: `every_sheet_rows` `scm/outstanding_reader.py:300`.
  - date parsing: `_to_date` `scm/outstanding_reader.py:157`.
  - the crew CLI skeleton: `scripts/merge_customers_by_code.py:101-113` (`--dry-run` by default, `--apply`, `--revert RUN_ID`, a required `--actor`).
- A project is created by `register_project` `project_service.py:316`:
  - its code comes from the `project` numbering rule, so the PS number cannot be the project code;
  - the near-duplicate check can be skipped with `skip_clash_check` `:329`;
  - template tasks are only created when a template is passed (`:431`).
- The registration lock is the unique index `uq_projects_company_developer_title` `models/projects.py:392-400`, on (company, developer party, normalised title), for staff and approved projects.
- `projects.admin_ref` `models/projects.py:342` and `purchase_orders.admin_ref` `:2265` are the "PS26-0143" filing reference. Neither is unique.
- A project's customer lives on `projects.sales_profile.customer_id` (with `customer_name` and `developer_name` as text).
- A PO (`projects.purchase_orders`, `models/projects.py:2211`):
  - needs a project (`project_id` NOT NULL) and is unique per (project, PO number) `:2304`;
  - starts as `draft`;
  - `po_source` is `contractor_direct` or `trading_house` `:2164`, and `issuing_party_id` names who issued it;
  - is created by `create_po` `project_po_service.py:374`. On the project's first PO, `create_po` moves the project to "PO received" and Won (`_advance_to_po_received` `:461`) and writes the project's activity entry.
- AutoCount sales orders sync into `sales_orders` (`models/order.py:639`, unique (company, `so_number`), `customer_id` and `debtor_code` on the row). A project order is `projects.sales_orders` (`models/project_so.py:442`, `so_id` unique), adopted by `ProjectSOAdoptionService.adopt_for_migration` `project_so_adoption_service.py:128`.
- Users have no staff code. The explicit key for a person is `users.email` (unique, `models/user.py`).

## (a) Column mapping

Columns are found by HEADING after `normalize_header`, on every monthly sheet. If a heading is missing, that sheet fails loudly with one `missing_header` error naming the heading; the other sheets go on.

| Col | Heading | Goes to | Notes |
|---|---|---|---|
| A | RUNNING PS NUMBER | `purchase_orders.admin_ref`; on a NEW project also `projects.admin_ref` = the lowest PS number of its group | The row identity. Must match `^PS\d\d-\d{4}$`, otherwise the row is not a data row. |
| B | SALES PERSON | `purchase_orders.sales_person` (text, trimmed); the project's `owner_user_id` only through the People mapping | Never matched to a user by name. |
| C | CUSTOMER SERVICE | text only, kept in the PO notes line `CS: <name>` | The CRM has no customer-service field on a project or PO (Q3). |
| D | CUSTOMER | the dealer who placed the PO: `sales_profile.customer_id` on a new project; on the PO, `po_source = trading_house` and `issuing_party_id` = that customer's trading-house party | Linked only by debtor code (see b). |
| E | PROJECT NAME | a new project's title, through the Projects mapping | See (c). |
| F | DEVELOPER | a new project's `developer_party_id`, through the Developers mapping; the text is also kept in `sales_profile.developer_name` | `END USER` and other remarks are mapped to "none" by the human. |
| G | PO NUMBER | `purchase_orders.po_number`, as text | An integer cell is written as its digits; a cell that lost a leading zero is flagged `po_number_numeric` (the zero cannot be recovered). |
| H | TOTAL VALUE | `po_amount` | `-` gives an empty amount, and the row is cancelled (see M/N). |
| I | DATE | `po_date` | A date outside the sheet's year or month is imported as written and flagged (`date_other_year`, `date_other_month`). It is never "fixed". |
| J | AMENDED DATE | the PO notes line `Amended: <text as written>` | No PO field exists for it. A date inside the text is not parsed. |
| K | SCHEDULE YES/NO | the PO notes line `Schedule: <value>` | An unknown value (anything other than YES, NO, O/C) is kept and flagged `schedule_unknown` (Q4). |
| L | DELIVERY DATE | a real date goes to the notes as `Delivery: dd/mm/yyyy`; text goes to the notes as written | No PO field exists for it. Free text is never turned into a date. |
| M | OUTSTANDING | `CANCELLED...` makes the row cancelled; `on hold <date>` goes to the notes as written | Q4. |
| N | SO NUMBER | split on `,` and trimmed; each `SO` + 6 digits is looked up in the synced `sales_orders` by `so_number` and linked to the project and the PO | `CANCELLED...` makes the row cancelled; `refer PS26-NNNN` goes to the notes and is flagged; an SO number not found in the sync is flagged `so_not_synced` and the PO imports without that link. |
| O | REMARKS | any `WAIVE TRANS*` spelling goes to the notes as `Waive transport charge`; `CANCEL*` makes the row cancelled; anything else goes to the notes as written | |
| P..AK | (none) | ignored | Including the whitespace cell `Q8`. |

## (b) How a row finds its links: explicit keys only, never a name

Pass 1 (`--emit-mapping`) writes `mapping.xlsx`:

- One sheet per kind (Customers, Projects, Developers, People), each listing the distinct strings with their row counts.
- Each string is normalised only by trimming, collapsing spaces and upper-casing, so `CUSTOMER 001 SDN BHD ` and `customer 001 sdn bhd` are one line. Two different spellings stay two lines.
- Reference sheets list the existing CRM records to copy keys from: projects (code + title), developer parties (name + id) and users (name + email).
- A suggestion column may show a likely match. The tool never reads it.

A human fills the key column:

| Sheet | One line per | Human fills | Allowed values |
|---|---|---|---|
| Customers | customer string | `debtor_code` | an existing `customers.customer_code`, or `SKIP` |
| Projects | (customer string, project string) pair, blank project included | `target` | an existing project code; `NEW:<label>` (pairs with the same label become ONE new project, titled `<label>`); or `SKIP` |
| Developers | developer string | `party` | an existing developer party id; `NEW` (create one party with this name, a human decision); or `NONE` |
| People | salesperson string, CS string | `email` | an existing user's email, or `NONE` (the text is kept, there is no owner link) |

Pass 2 (`--mapping mapping.xlsx`, dry run, then `--apply`):

- **Customer.** First, the row's own SO numbers: when they resolve in the sync to one customer, that customer is used (an explicit key). Otherwise the Customers mapping. If both exist and disagree, the row is `needs_review: customer_conflict`. If neither exists, it is `needs_review: customer_unmapped`. The dealer's trading-house party is the existing party whose `customer_id` is that customer; if there is none, one is created from the customer record (by key, not by name).
- **Project.** The Projects mapping only. A blank target is `needs_review: project_unmapped` and the row is not imported.
- **Developer.** The Developers mapping only. Blank is `needs_review: developer_unmapped`. A project whose rows map to different developers is `needs_review: developer_conflict`.
- **Salesperson.** The People mapping. The owner of a new project is the salesperson on its lowest PS row. A blank owner falls back to the `--actor` user and is flagged `owner_defaulted`.
- `mapping.xlsx` is merged on re-emit: lines already filled keep their values, and new strings are added as blank lines.

## (c) Identity

- One PS number is one PO. A PO is found again by (company, `purchase_orders.admin_ref`). If two CRM POs carry the same PS number, the row is `error: ps_duplicate_in_crm` and nothing is written.
- A PS number that appears twice in the file is `error: ps_duplicate_in_file` for both rows.
- A project is never derived from the row. It comes from the Projects mapping, so about 577 names (643 customer + project pairs) become as many projects as the human decides.
- The 27% of rows with no project name list as `(customer, blank)` pairs, defaulting to `SKIP` (Q1).
- A PO number already on the target project under another PS number is `needs_review: po_number_taken` (the unique key `:2304`). This covers the 3 repeated customer + PO pairs.

## (d) Re-runs and change detection

- Same file twice: every row that was imported reads `unchanged`, and nothing is written.
- A later version of the file adds only new PS rows.
- A row whose file values differ from the CRM's PO (amount, date, PO number, SO list, notes) is reported as `changed_in_file` with the field names. It is NOT written (Q2).
- Nothing the import wrote is ever overwritten, so a human edit in the CRM always survives. A blank cell never clears a CRM value.
- An already-imported row whose SO numbers have since been synced gains the missing SO link. This is the one additive update. It is reported as `updated: so_linked`.

## (e) Dry-run report

- Dry run is the default. Apply runs the same function with writes kept, and the dry run is that same run rolled back.
- Per run: totals by outcome (created, updated, unchanged, skipped, error, needs_review), per sheet and overall, with one count per reason code.
- Per row: sheet, Excel row number, PS number, outcome, reason codes, and what it would create (new project label or existing project code, PO, SO links).
- Two copies:
  - the full xlsx for crew (it contains names);
  - a shared copy with names replaced by the mapping line number (`customer #12`, `project #40`) and no amounts. Only the shared copy may be posted.
- Every run, dry or apply, gets an `import_jobs` row (`job_type = project_migration`). Its rows are `import_job_rows`.

## (f) What is skipped

- Rows whose column A is not a PS number. This covers the total row, the salesperson roll-up block and its title rows.
- Pre-numbered blank rows (PS number only, no customer): `skipped: placeholder`.
- The whole `SUMMARY JAN-JUN` sheet: `skipped: summary_sheet`. It is read as a cross-check only: each of its POs is reported as found or not found among the imported rows.
- Cancelled rows (`-` value, `CANCELLED` in M, N or O): `skipped: cancelled`, listed in the report (Q4).
- Mapping `SKIP` lines: `skipped: mapped_skip`.
- Sheet names are matched after trimming, so a trailing space is fine.

## (g) Status of a migrated project, and the registration rules

- A migrated project is a staff project (`approval_state` NULL). It gets a code from the numbering rule, starts on the first funnel rung, and moves to "PO received" + Won when its first PO lands (the CRM's own rule in `create_po`).
- Imported POs are `draft`, the same as a hand-keyed PO. No approval is claimed on anyone's behalf.
- The near-duplicate check is skipped on purpose (`skip_clash_check=True`) because the human mapping made the decision. Each skip is recorded on the run's row (`clash_check_skipped`).
- The registration lock index is never bypassed. A `NEW:` label that hits an existing project with the same developer and title is `needs_review: registration_lock` naming that project's code. The human then maps the line to that code instead.
- No template tasks, no notifications and no lead source are set.

## (h) Audit and rollback

- Every created record (project, sales profile, PO, party, project sales order link) gets one `import_job_rows` line with `entity_type` + `entity_id` under the run's `import_jobs` row. That is the run tag; no new column is needed.
- The run acts as the `--actor` user. The audit carries the run id as `job_id` (`stamp_actor`, `app/audit_context.py:70`).
- `--list-runs` shows the runs. `--revert RUN_ID` removes what that run created, newest first:
  - a dry run of the revert shows the counts first;
  - a record that was changed in the CRM after the run (any update, or a child record such as a quotation not made by the run) is kept and reported `revert_kept_edited`.
- Commits happen per sheet, with a savepoint per row: one bad row never fails the batch. The largest transaction is one sheet, about 220 rows.

## (i) Worked examples (masked shape)

1. **Normal row.** `PS26-0178 | BELLA | LUNA | CUSTOMER 007 | PROJECT 004 | DEVELOPER 003 | EM/PO/7534320 | 581.15 | 01/04/2026 | YES | 02/04/2026 | SO462360 | WAIVE TRANSPORT CHARGE`
   - Customer from the SO's debtor.
   - Project per the mapping, say `NEW:PROJECT 004`. A new project is created with owner = BELLA's mapped user and developer = the mapped party.
   - PO `EM/PO/7534320`, 581.15, 01/04/2026, admin_ref PS26-0178, notes `CS: LUNA / Schedule: YES / Delivery: 02/04/2026 / Waive transport charge`.
   - SO462360 is linked to the project and the PO.
   - Outcome: `created`.
2. **Multi-SO row.** PS26-0165, SO cell `SO466355,SO466352, SO466351`, no project name.
   - With the default `SKIP` for `(CUSTOMER 006, blank)`: `skipped: mapped_skip`.
   - If the human maps it to a project: one PO and three SO links. Any SO not yet synced shows `so_not_synced`, and the next run links it.
3. **Cancelled row.** PS26-0139, value `-`, SO `CANCELLED 11/5/2026`: `skipped: cancelled`.
4. **Amended row.** PS26-0152, J `amend 9/9/9999`: the PO imports, with the notes line `Amended: amend 9/9/9999`. No date is parsed and no flag is raised.
5. **Year typo, no project name.** PS26-0100 dated 02/01/2025 on the JAN'26 sheet:
   - if mapped, it imports dated 02/01/2025, flagged `date_other_year`;
   - unmapped, it is `needs_review: project_unmapped`.

## Questions (each with a recommendation)

1. **Grouping and rows with no project name.** A row is a PO, not a project.
   - (a) Recommended: group only through the Projects mapping (a human decides which pairs share one project). Blank project name pairs default to SKIP; the human may still map one to a project.
   - (b) Every PS row its own project (about 1,280 projects, many of them duplicates).
   - (c) A per-customer "Trade orders" project for blank-name rows. This puts about 345 POs into the funnel as fake projects.
2. **What may the import change in records that already exist?**
   - (a) Recommended: create new projects and POs only, and attach new POs to an existing project when the mapping names its code. Never edit an existing project or PO field; changed rows are reported only.
   - (b) Also update PO fields when the CRM value still equals what the import wrote last time.
3. **Salesperson and customer service.**
   - (a) Recommended: a People mapping to user emails for the project owner. Customer service stays text in the PO notes.
   - (b) No mapping: both stay text, and every project is owned by the person running the import.
4. **SCHEDULE codes and cancelled / on hold rows.**
   - What do `O/C`, `CBD` and `YS` mean? Recommended: keep the value as written in the notes and flag anything other than YES, NO, O/C.
   - Cancelled rows: (a) skip and list them (recommended: the CRM has no cancelled PO state); (b) import as a PO with the notes `Cancelled <date>`.
   - On hold: import, with the text kept in the notes.
5. **Scope and cadence.**
   - Sheets: JAN to AUG 2026 only (recommended), or older years too (a different PS prefix, PS25-).
   - Will the owner re-send the file monthly? Recommended: yes, assumed. Idempotent re-runs are built in either way.

## Reuse plan (no second copy of logic)

| Piece | Reuse | How |
|---|---|---|
| preview == apply | `customer_import_service._run` shape | copy the shape, no shared base class (one other user) |
| row outcomes, codes | `ImportOutcome` `import_outcome.py:65`, `import_outcome_codes.py` | as is; add this importer's codes |
| run ledger, run tag | `import_jobs` / `import_job_rows` `models/job.py:33,:84` | as is (no migration) |
| headers | `normalize_header` `import_alias_service.py:34` | as is |
| sheets | `every_sheet_rows` `scm/outstanding_reader.py:300` | as is |
| dates | `_to_date` `scm/outstanding_reader.py:157` | promote to a public shared function (it is private today, and two other copies exist) |
| create project | `register_project` `project_service.py:316` | as is, `skip_clash_check=True` |
| create PO + status move | `create_po` `project_po_service.py:374` | as is; `sales_person` / `admin_ref` set after, in the same savepoint |
| create party | `create_party` `project_reference_service.py:215` | only for a `NEW` developer line; its name lookup is not used for matching |
| adopt synced SO | `ProjectSOAdoptionService.adopt_for_migration` `project_so_adoption_service.py:128` | as is; one new shared function `link_sales_order_to_project(pso, project, po)` sets the project + PO (none exists today; PROJECT-RELATED-RECORDS may want the same one) |
| CLI, actor, revert | `scripts/merge_customers_by_code.py`, `scripts/rollback_oi_sheet_upload.py` | copy the skeleton |

## Timing plan (for crew, after the owner's OK)

- Dry run on a dev copy with the real file. Crew sends back only the shared report.
- Then a timed apply on a prod-size copy: rows per second, peak memory, longest transaction, and the locks held (per-sheet commit).
- Expected size: about 1,282 data rows, which should take seconds, not minutes, so no background job is planned. A run over 60 s would become an RQ job.

## Crew answers (12 Nov 2026, from prior owner rulings; supersede the rules above)

1. Grouping: rows join a project ONLY through the Projects mapping a person fills. Blank-name rows: owner decision d1 (default until then: SKIP, listed by PS number).
2. Customer = the dealer in column D, linked by debtor code: the SO's debtor first, else the Customers mapping.
3. `customer_conflict` only for a different shop. When the SO debtor and the mapped debtor are accounts of the SAME shop, the SO debtor is used with no review. "Same shop" means both `customers` rows share a `customer_group_id` or the same `ledger_family_key(customer_name)` (`app/services/ledger_family.py:134`), compared between two keyed records, never against the sheet text. The dry run counts these as `customer_same_shop_so_used`.
4. Q2 = (a): create only. Never edit an existing project or PO. `changed_in_file` is reported only, and a blank never clears.
5. Q3 = (a): the People mapping to user email sets the project owner; CS stays text in the PO notes, no new field. Who fills the mapping: owner decision d3.
6. Cancelled rows: skip and list by PS number. On hold: import, text in the notes. Schedule code meanings: owner decision d2; until then keep as written and flag unknown codes.
7. Messy cells (2025 dates, lost leading zeros, free-text delivery): import as written and flag, never fix.
8. Dates in the notes read dd/mm/yyyy; text dates stay as typed.
9. No emails, WhatsApp, notifications or template tasks from the import. On the dev copy, prove that `create_po` and the Won move send nothing and change no sales total (a test asserts no notification / outbound rows are written and the shared sales total is unchanged).
10. Developer `NEW` only where the person writes `NEW`.
11. PO issuer: mirror how hand-keyed dealer POs record `po_source` and the issuing party on the dev DB (data request filed). The PO form defaults to `contractor_direct` with no issuer (`PurchaseOrderDialog.tsx:76,79`). No trading-house party is created from a customer unless the dry run lists every new party first. Until the data answers: no party is created, and `issuing_party_id` is set only when an existing party already carries `customer_id` = the row's customer.
    - Data answer (12 Nov prod clone, counts only): exactly 1 project PO exists (`contractor_direct`, no issuer), so there is no hand-keyed pattern to mirror. Parties: 212 developer, 1562 architect, 3 trading house (1 keyed to a customer), every other role unkeyed. RULED: the interim rule stands. `po_source = contractor_direct`; `issuing_party_id` only when an existing party already carries `customer_id` = the row's customer (today that can match at most 1 party); no party is ever created from a customer. The import will be almost the whole PO table, so the dry run states the before/after PO count.
12. The real file, `mapping.xlsx` and the full report never leave the owner's Mac. Crew runs the real-data dry run locally; only the masked shared report is posted. Nothing runs on prod; the live-run method is owner decision d5.

Owner decisions pending: d1 blank-name rows, d2 schedule codes O/C CBD YS, d3 who fills the mapping, d4 years + one-time vs monthly, d5 live run (CLI command vs upload page; an upload page adds the mock gate).
