# P1 behaviour card (DRAFT): service jobs, send a technician to the site

Status: DRAFT, not filed. It waits for the owner's G-list notes on the review page
(`documentation/plans/after-sales/review/index.html`). Nothing is built until this card is approved.
Lane AFTER-SALES-REVIVE, port slice P1. Size L: new tables, migration, new screens, permissions.
PR title: "AFTER-SALES-P1: ...".

## What CS gets

- On a complaint: a **Site** and a **Service Jobs** section with a "Raise service job" action.
- A **Service Jobs** list.
- A **Service job** record page with a History tab.
- A **Dispatch board**.
- A **Technicians** list.

All of it sits under Complaint Management.

Source in #163:
- `service_job_service.py`, `service_job_status_graph.py`, `service_job_intake.py`
- `models/service_jobs.py`
- migrations 325, 326, 330, plus the site columns from 316/328

## Rules

1. **Site.** A complaint has one Site, stored as separate fields: address line 1, address line 2,
   postcode, city, state, country, contact on site, contact phone, and an optional map pin.
   - When a job is raised, it is prefilled from the complaint.
   - Today's `complaints.customer_address` (`sorento_crm_backend/app/models/complaints.py:37`) prefills
     address line 1 when the Site is empty.
2. **Raising a job.** A job is raised in one of two ways:
   - CS presses "Raise service job".
   - A Resolution marked "requires service job" is set. This needs a new column on `complaint_resolutions`
     (`sorento_crm_backend/app/models/complaint_master_data.py:25`).
   - A complaint gets at most one live job (any status except Cancelled or Verified). Pressing again opens
     the live job.
   - Clearing the resolution never deletes a job.
3. **Statuses.** The status flow is the one #163 built:
   - Main path: Proposed -> Confirmed -> On the way -> Arrived -> Completed -> Verified.
   - Back to Proposed: "Customer rejected the visit" (from Confirmed or On the way) and "Revisit needed"
     (from Arrived).
   - "Reopen: work not accepted": Completed -> Arrived.
   - Cancel: from Proposed or Confirmed.
   - Only the moves the current status allows are offered.
4. **Confirm.** Confirming needs a date and time AND who agreed it. A date alone does not confirm.
5. **Assign.** Assigning a technician writes an assignment row.
   - A rejected visit keeps its old assignment row in History.
   - A new assignment row starts the next try.
6. **Technicians.** Technicians are not system users (decision 4).
   - Fields: name, phone, employee or contractor, active.
   - CS presses On the way, Arrived and Completed on their behalf.
   - An inactive technician cannot be picked for a new assignment, but stays on old jobs.
7. **Times.** The job records scheduled from/to, arrived, completed and verified times.
   - Attend time = arrived minus confirmed date.
   - A value that cannot be worked out shows "-".
8. **Stalled.** A job is stalled when it is still Proposed past its scheduled date.
   - Stalled jobs sit at the top of the dispatch board.
   - A Confirmed job past its date is not stalled.
9. **Numbers.** Every job gets a number from the shared document numbering, `SV{yy}/{mm}-{seq}`,
   e.g. SV26/11-0001. This fixes #163's "Unnumbered".
10. **Owner standing rules for the screens:**
    - Lists: DataGrid with one toolbar row and "Create"; server-side sort; one line per row;
      multi-select filters (Status, Technician, Date range).
    - Rows: right-click row menu; no row icon buttons; countdown delete for a technician
      (hard delete only when no job uses it, else Archive).
    - Dates: dd/mm/yyyy and the shared date picker.
    - Record page: standard header with prev/next; a History tab on the job built on the shared history
      component (`sorento_crm_frontend/components/common/EventTimeline.tsx`).
    - Plus Excel export of the jobs list, and a user guide.
11. **Out of P1 unless the owner keeps them on the review page:**
    - G4 WhatsApp the customer
    - G5 send the job to the technician
    - G6 completion report
    - G7 charges and costs
    - G10 stalled alert notification

## Examples (shapes from the sandbox fake data; real masked rows requested below)

| # | Case | Expected |
|---|---|---|
| 1 | A complaint with a site and no job; CS presses Raise service job | Job SV26/11-0001, Proposed, site copied |
| 2 | CS confirms 13/11/2026 10:00 am, agreed by "Consumer on WhatsApp" | Confirmed; dispatch board 13/11/2026 under Unassigned |
| 3 | CS assigns Tech Alpha | Moves to Tech Alpha's column on 13/11/2026 |
| 4 | The customer rejects on the day | Back to Proposed; History shows the first try and its technician |
| 5 | A Proposed job dated 10/11/2026, viewed on 12/11/2026 | In "Stalled jobs" on the board |

`crew-ask: data request` to file with the card: 5 recent complaints where `required_on_site_support = true`,
with `customer_address`, `status` and `resolution_id`. Mask names, phones and addresses. The point is to see
how today's address text splits into Site fields.

## Edge cases

- The complaint is closed or voided: Raise is still allowed (a revisit after closure). See question 3.
- A complaint has no address: the job can be raised; Confirm still works; the Site shows "-".
- Two CS press Raise at once: one job (live-job guard plus a unique partial index).
- A resolution flag is set, but a Cancelled job exists: a new job is raised.
- The technician is deactivated while assigned: the job keeps them; the board still shows them that day.

## Questions (at most 5, recommendation first)

1. **Job number format.** (a) `SV26/11-0001` as #163 seeded; (b) the complaint number plus a suffix,
   e.g. `CMP2026-0148-1`.
   Recommendation: (a). It is one sequence and reads like the other document numbers.
2. **Site on today's complaints.** (a) Structured Site fields, prefilled from `customer_address` and editable
   on the complaint; (b) a free-text address only.
   Recommendation: (a). The board and a future map or route need a city and state.
3. **Raise on a closed or voided complaint.** (a) Allowed (revisits happen after closure); (b) blocked.
   Recommendation: (a), shown in History.
4. **Existing complaints with "Required on site support = Yes".** (a) No jobs are created for them, and CS
   raises one when needed; (b) one job is backfilled per open complaint.
   Recommendation: (a). No invented records.
5. **Who may dispatch.** (a) New permissions: service jobs view, dispatch, and technicians manage, granted to
   the roles that edit complaints today; (b) reuse the complaint edit permission.
   Recommendation: (a). The security reviewer checks the grant.

## Tests (red first, by the tester)

The tester writes these from this card and the UAC, before any code:
- graph moves (allowed and refused)
- confirm needs both a date and who agreed
- the live-job guard, including a race between two requests
- the auto-raise rule, including idempotency
- numbering
- stall
- permission gating
- list sort, filter and pagination (`tests/test_list_pagination_limit.py`, `tests/test_schema_uuid_id_principle.py`)
- vitest for the job page actions and the board
