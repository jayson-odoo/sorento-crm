# Container Status workbook, per company - User Acceptance Criteria

Status: complete (pending review)
Plan: `documentation/plans/purchasing/PLAN-container-status-per-company.md`
Supersedes the single-global-workbook rule stated in
`documentation/plans/purchasing/PLAN-container-status-tracking.md`.

## Journey

**Actor A - the Mocha office user.** Arrives at Procurement Management -> Packing Lists,
opens the toolbar menu, picks "Import container status", drops this week's workbook.
The system already knows which company they are working in (their active company, the one
already shown in the company switcher), so it never asks. Upload finishes, the parse runs,
and the file is published to the library as Mocha's current Container Status. Nothing about
Sorento moves. When the same user later picks "Download container status", they get Mocha's
sheet, because that is the company they are standing in.

**Actor B - the Sorento office user**, in parallel, has their own current workbook. Their
download link, their library row, and their MCP answers are unaffected by anything Mocha
uploads. They never learn that Mocha uploaded at all.

**Actor C - a dealer contact who buys from both Mocha and Sorento**, on WhatsApp, asks the
assistant "send me the container status list". The system already knows which companies that
contact belongs to (`respond_contact_companies`). It finds a current workbook in each and
comes back with both, each one labelled by its company, so the contact (or the agent on their
behalf) can say which one they meant. It never silently picks one, and it never returns two
files that look identical.

**At the end:** each company holds exactly one current workbook. A stale sheet is in the
trash, recoverable, and its import job still holds its own retained copy.

## Acceptance criteria

### Group A - one current workbook PER COMPANY (`[BE]`)

- **AC-A1** Given Sorento has a live Container Status workbook, when a Mocha user imports a
  Container Status workbook, then Sorento's row is still live (`is_deleted = false`) and
  Mocha's new row is live.
- **AC-A2** Given a company has three live Container Status workbooks, when
  `enforce_single_current` runs, then exactly one survives for that company - the newest by
  `uploaded_at` - and the other two are soft-deleted (`is_deleted = true`, `deleted_at` set,
  the rows and bytes intact).
- **AC-A3** Given two workbooks of the SAME company share `uploaded_at` to the microsecond,
  when the rule runs, then the survivor is the one with the higher `id` (deterministic
  tie-breaker), and the other company's survivor is unaffected.
- **AC-A4** Given the rule has already run, when it runs again, then it trashes nothing and
  returns 0 (idempotent, per company, at any number of repeats).
- **AC-A5** Given legacy workbooks with `company_id IS NULL` (published before company
  stamping), when a company imports a new workbook, then the newest NULL-company row stays
  live and is not trashed by that company's upload; the NULL rows are ranked only against
  each other.
- **AC-A6** Rows already soft-deleted by the previous global rule stay soft-deleted. Nothing
  in this change resurrects them.
- **AC-A7** Given an import job whose `company_id` snapshot is NULL (enqueued under a `None` /
  `UNSET` scope, the n8n / X-API-Key path), when its workbook is published, then the
  attachment is stamped with the incumbent company (Sorento), never NULL. A published
  workbook can never be company-less, because `Attachment` is company-SHARED and a live NULL
  row would be visible to every company at once while no company's future import could ever
  supersede it.
- **AC-A8** Migration `323_cs_company_backfill` stamps the incumbent company on every existing
  Container Status attachment whose `company_id` is NULL, live or already trashed. It leaves
  `is_deleted` untouched, leaves rows already attributed to another company alone, and running
  it twice changes nothing.

- **AC-A9** Given a workbook that was published and has since been trashed (superseded by a
  newer import, or trashed deliberately), when its import job is published again (a retry or
  a backfill re-run), then no second row is written for the same storage key, the trashed row
  stays trashed, and the company's current workbook stays live. Re-publishing an older job
  must never name a stale sheet as the keeper.

  AC-A5 therefore describes defensive behaviour, not a steady state: after AC-A7 and AC-A8 no
  NULL-company workbook exists, and the NULL partition only contains a stray row if one is
  written by hand.

### Group B - the "latest" download link is company-aware (`[BE]`)

- **AC-B1** Given the caller's active company is Mocha and both companies have a current
  workbook, when they `GET /api/v1/procurement/packing-lists/container-status/latest`, then
  they receive Mocha's workbook.
- **AC-B2** The response carries `company_id` and `company_name` alongside `attachment_id`,
  `url`, `filename`, `size`, `uploaded_at`.
- **AC-B3** Given the caller's active company has never imported a workbook and no legacy
  NULL-company row exists, then the endpoint returns 404 with the existing "No Container
  Status workbook has been imported yet." message.
- **AC-B4** Given the caller's company has its own workbook AND a legacy NULL-company
  workbook exists, then the owned workbook wins regardless of which is newer.

### Group C - entity resolution returns every company's current workbook (`[BE]`)

- **AC-C1** Given a Respond contact granted both Mocha and Sorento (via
  `respond_contact_companies`) and each company has a current workbook, when the contact
  resolves "container status", then TWO attachment matches come back, one per company.
- **AC-C2** Each match carries `company_id` and `company_name` at the match level, matching
  the attribution shape already emitted for products
  (`tests/test_resolve_entity_company_attribution.py`).
- **AC-C3** The same attribution is present on the domain-hint short-circuit path
  (`domain_hint="container status"` -> `_resolve_with_domain_hint`), which is the path a
  document request actually takes.
- **AC-C4** Given a contact granted only Sorento, when they resolve "container status", then
  exactly ONE match comes back and it is Sorento's. Mocha's workbook is never visible to them.
- **AC-C5** Attribution is additive: it changes which rows resolve only through the existing
  company scope, never through a new filter of its own.
- **AC-C6** Given an `X-API-Key` caller that passes no `contact_id` / `space_id` (scope `None`,
  all companies, the documented backward-compat path), when it resolves "container status",
  then it gets one workbook PER COMPANY, each attributed, and the result reports
  `resolved: false` / `ambiguous: true`. This is a deliberate behaviour change from the single
  global workbook: an all-companies caller that wants one answer must pass contact identity.

### Group D - the document surface distinguishes the two currents (`[BE]` / `[MCP]`)

- **AC-D1** `AttachmentResponse` carries `company_id` and `company_name`.
- **AC-D2** The MCP `crm_resource_attachments_list` render shows the owning company on each
  item, so two rows both named "Container Status 2026.xlsx" are tellable apart without the
  UUID (which is deliberately absent from the customer-facing render).
- **AC-D3** A shared / company-less attachment (`company_id IS NULL`) renders with no company
  line rather than an empty one.

### Group E - regressions held (`[T]`)

- **AC-E1** The workbook parser is untouched: joint tabs ("Arrived - Joint Mocha Container")
  still parse exactly as before. `tests/test_container_status_parser.py` stays green unmodified.
- **AC-E2** The existing single-company behaviour in `tests/test_container_status_document.py`
  still holds (those fixtures insert company-less rows, which now rank within the NULL
  partition).
