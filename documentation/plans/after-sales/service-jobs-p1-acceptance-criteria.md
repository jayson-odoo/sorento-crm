# UAC: After-sales P1, service jobs

Status: in build (lane AFTER-SALES-REVIVE, PR #2365). Plan: `PLAN-service-jobs-p1-12nov.md`.
Dates in examples are dd/mm/yyyy. Times are MYT.

## A. Site on the complaint

- **A1.** A complaint carries these Site fields: address line 1, address line 2, postcode, city, state,
  country, contact on site, contact phone and an optional pin (latitude, longitude). They are saved through
  the complaint update API, and the complaint GET returns them.
- **A2.** The detail page shows a Site card in that field order. The complaint edit form shows the same
  fields in the same order. A field with no value shows "-".
- **A3.** When the Site is empty and the complaint has `customer_address`, the edit form pre-fills address
  line 1 with it. Nothing is written until the user saves.

## B. Raising a job

- **B1.** `POST /complaints/{id}/service-jobs` creates a job in status Proposed with a job number
  `SV{yy}/{mm}-{seq:4}` (e.g. SV26/11-0001), using the complaint's company. The response is 201.
- **B2.** If the complaint already has a live job (any status except Cancelled or Verified), the same call
  returns that job with 200 and creates nothing.
- **B3.** Two concurrent raise calls for one complaint leave exactly one live job.
- **B4.** A complaint whose live job is Cancelled or Verified can raise a new job.
- **B5.** Raise works on a complaint in any status, closed and voided included.
- **B6.** Setting a resolution that has `requires_service_job = true` on a complaint raises a job (B1/B2
  rules apply). The complaint save is never failed by this.
- **B7.** Setting a resolution without the flag, or clearing the resolution, never creates or deletes a job.
- **B8.** Raise needs `complaint_management.service_jobs.dispatch`. Without it the call is 403.

## C. Moving a job

- **C1.** Confirm (Proposed -> Confirmed) needs `scheduled_from` and a non-blank `customer_agreed_by`.
  A missing one is refused with 422 and a message naming the field. `scheduled_to` is optional and, when
  given, must not be before `scheduled_from`.
- **C2.** Assign sets the technician on a job in Proposed or Confirmed. An inactive technician is refused
  with 422. Re-assigning replaces the technician, and History shows old -> new.
- **C3.** The allowed moves are exactly these. Any other move is refused with 409 and nothing changes.
  - confirmed -> on_the_way
  - on_the_way -> arrived
  - confirmed -> arrived
  - arrived -> completed
  - completed -> verified
  - confirmed -> proposed (reason "Customer rejected the visit")
  - on_the_way -> proposed (reason "Customer rejected the visit")
  - arrived -> proposed (reason "Revisit needed")
  - proposed -> cancelled
  - confirmed -> cancelled
  - completed -> arrived (reason "Reopen: work not accepted")
- **C4.** Arrived stamps `arrived_at`, Completed stamps `completed_at` and Verified stamps `verified_at`. A
  move back to Proposed clears the schedule and `customer_agreed_by` but keeps the technician. A reason is
  required for the moves to Proposed and for Cancel.
- **C5.** Every move needs `complaint_management.service_jobs.dispatch`.
- **C6.** Each create, confirm, assign and move writes an audit row on the job. The job's History tab shows
  who, when, the action, and old -> new for status, technician, scheduled date and agreed by.

## D. Lists and pages

- **D1.** `GET /service-jobs` is server-paginated, sorted and filtered.
  - Sorts: job no., complaint no., status, scheduled, technician, city, customer. Each sorts asc and desc,
    and the order holds on page 2.
  - Filters: status (multi), technician (multi), scheduled date range.
  - Search: job no., complaint no., customer name, city.
- **D2.** The list has one toolbar row (Search, Filters, Columns) and no Create.
  - One line per row.
  - Clicking a row opens `/complaint-management/service-jobs/{id}`.
  - Right-clicking a row shows Open complaint plus the moves the job's status allows.
  - No icon buttons on rows.
- **D3.** The job page header shows: job number + status pill on one line, a subtitle with the complaint
  number and customer, prev/next following the list's filters and sort, a gear with the secondary moves, and
  ONE filled button for the next step:
  - Proposed: Confirm date
  - Confirmed with no technician: Assign technician
  - Confirmed with a technician: On the way
  - On the way: Arrived
  - Arrived: Complete
  - Completed: Verify
  - Verified or Cancelled: none
- **D4.** Confirm date and Assign technician open in a centred dialog. The date is the shared date picker
  with time, reads dd/mm/yyyy and has no browser-native date input.
- **D5.** The job page has two tabs, Details (Visit card, Site card) and History. Date-times read
  "dd/mm/yyyy, h:mm am/pm". An unknown value shows "-".
- **D6.** The complaint detail page has a Service Jobs section listing the complaint's jobs, one line each
  (job no., status pill, scheduled, technician), and one "Raise service job" button. When a live job exists,
  the button is not shown. When there are no jobs, the section shows a heading + a hint with no CTA, as in
  `DESIGN-LANGUAGE.md` section 6.
- **D7.** The sidebar's Complaint Management group gains Service Jobs, Dispatch Board and Technicians. They
  are visible only with service_jobs.view (Technicians: also with technicians.manage).

## E. Dispatch board

- **E1.** The board shows one day, picked with the shared date picker (dd/mm/yyyy), with Previous, Next and
  Today buttons.
- **E2.** Columns: "Unassigned" first, then one per active technician who has a job that day (by name).
  Jobs scheduled that day (MYT) are listed in time order.
- **E3.** "Stalled jobs" on top lists every job that is Proposed with `scheduled_from` before now, oldest
  first, whatever the selected day is. A Confirmed job past its date is not stalled.
- **E4.** A card shows job no., time, city and status pill. Clicking it opens the job page.

## F. Technicians

- **F1.** The Technicians list is a DataGrid with Search + Create. Columns: Name, Phone, Type
  (Employee / Contractor), Active. Each is sortable on the server.
- **F2.** Create and Edit open the same centred dialog. Name is required, and type is Employee or
  Contractor.
- **F3.** Delete is the countdown action, with no confirm dialog. A technician on any job cannot be deleted
  (409, "in use, archive instead"). Archive sets the technician inactive, and an inactive technician is not
  offered on Assign.

## G. Resolutions master

- **G1.** The resolution dialog has a "Requires service job" checkbox (default off), and the resolutions
  list has a column for it.

## H. Guards

- **H1.** Every new id is a uuid. The list endpoints respect the pagination limit cap
  (`tests/test_schema_uuid_id_principle.py`, `tests/test_list_pagination_limit.py`).
- **H2.** A fresh `bootstrap_env` database can raise and confirm a job, so the graph and numbering rule
  are seeded.
- **H3.** Company scoping:
  - a user who cannot see a complaint gets 404 for its jobs;
  - list rows are limited to the complaints the user can see (the same scope as the complaints list,
    including view_own).
