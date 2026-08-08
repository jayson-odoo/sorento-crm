# UAC - From a lodged retail complaint to a technician at the door

**Companion to:** `PLAN-retail-complaint-to-visit.md`
**Extends:** `after-sales-warranty-acceptance-criteria.md` (S1-S6 built). This covers what happens
AFTER a retail complaint lands, up to a technician being sent.
**Status:** Pre-code. Every AC self-verified end-to-end on the stated side(s) before handoff.
**Decisions:** `adr/0009` (Service Job is requester-agnostic) - `adr/0010` (Warranty Terms scope to Kind) - `adr/0001` (status engine is core).
**Legend:** `[BE]` pytest - `[FE]` vitest/playwright - `[E2E]` full FE->BE->DB - `[MIG]` migration/data - `[CFG]` tenant-side configuration, not code - `[T]` CI guard.

Convention: **Given / When / Then**, observed against the real stack for the side marked.

---

## Journey (Phase 0 - governing; every AC traces to a step here)

The actor is **Agnes**, Customer Service. A retail complaint has just landed from the
consumer portal. The consumer has already been told we have it (S3 acknowledgement).

**Step 1 - She reads what came in.** The complaint shows the products as the consumer
described them, the site, the photos, and the fault. Nothing is asked of her that the
lodgement already answered.

**Step 2 - She sets the root cause and the resolution.** One decision, from Sorento's own
vocabulary. She does NOT also decide whether somebody has to go to the site: that follows
from the resolution she picked, and asking her to remember which resolutions imply a visit
is asking her to hold a table in her head.

**Step 3 - The visit exists, if it is needed.** Where the resolution requires one, a
Service Job is already there when she looks, carrying the site the complaint reported (not
the customer record's address - AC-B3). Where it does not, no job is raised and nothing
clutters the case.

**Step 4 - She calls to agree a date.** A consumer is a person with a job; a date is a
conversation, not a form field. She triggers the call from the case, which opens the
contact's Respond conversation. When the call ends, the fact of it - who, how long,
completed or missed - lands on the Service Job by itself. The next person to open the case
can see that somebody already tried.

**Step 5 - She proposes the date they discussed.** She types it and presses Propose. The
consumer receives a WhatsApp message naming the date, with **Confirm** and **Reject**.
Until they answer, the job is not confirmed and nobody is sent.

**Step 6 - The consumer answers, and the system listens.** Confirm marks the job Confirmed,
recording that the consumer agreed and when - no typing by Agnes. Reject asks them for a
time that suits, captures the reply, and parks the job as waiting on the customer.

**Step 7 - Only now is a technician assigned.** Sending one to a date nobody agreed is the
wasted van this slice exists to prevent.

**Step 8 - The dispatcher sees the month.** Not one day at a time: who is working which
day, where the capacity is, and which jobs still have no date at all.

**What Agnes holds at the end:** a job with an agreed date, an accountable technician, and
a record of the call that got there. **What the consumer holds:** a message they can point
at, in the thread they already use.

---

## Phase A - The resolution decides whether a visit is needed (S7a)

- **AC-V1 [BE][MIG]** Given the `complaint_resolutions` master table, When migrated, Then it
  carries `requires_service_job` (boolean, NOT NULL, default false), and every existing row
  is false - because no existing row was chosen under this rule and defaulting them true
  would raise a job for every historical complaint touched afterwards.

- **AC-V2 [BE]** Given a resolution with `requires_service_job = true`, When it is set on a
  complaint that has no open Service Job, Then exactly one job is raised through the same
  `raise_job_for_source` the manual button uses, copying the complaint's site.

- **AC-V3 [BE]** Given a complaint that already has a job in any non-terminal state, When a
  requiring resolution is set (or re-set), Then no second job is raised. A duplicate reads
  as a revisit in every report that counts them.

- **AC-V4 [BE]** Given a complaint whose only job is `cancelled`, When a requiring resolution
  is set, Then a NEW job is raised - a cancelled visit is not a visit.

- **AC-V5 [BE]** Given a resolution with `requires_service_job = false`, When it is set,
  Then no job is raised and no existing job is touched. Un-setting a resolution never
  deletes a job: somebody may already have been dispatched.

- **AC-V6 [BE]** Given job creation fails (numbering, graph unseeded), When the resolution
  is saved, Then the resolution still saves and the failure is logged - the clinical
  decision is not lost to a dispatch problem.

- **AC-V7 [FE]** Given the Resolutions master-data screen, When an admin edits a resolution,
  Then `requires_service_job` is an editable field with its effect stated in one short label,
  and the list shows which resolutions carry it.

- **AC-V8 [E2E]** Given a retail complaint with no job, When Agnes picks a requiring
  resolution and saves, Then the Service Jobs section shows one job in Proposed without a
  page reload.

## Phase B - Warranty policy configuration (S7b)

Context: the engine is built and writes assessments. It reads 31 kinds, 41 terms and **2
kind rules**. Two rules for thirty-one kinds is why most reported products reach no Kind and
so get no verdict. The feature is not broken; it is unconfigurable.

- **AC-P1 [BE][FE]** Given the Warranty Policies screen, When an admin creates a policy,
  Then it carries a version, an effective-from date and an optional effective-to, and the
  pair (company, version) is unique.

- **AC-P2 [BE]** Given two policies with overlapping effective ranges, When saved, Then the
  save is refused naming the overlap - a complaint is judged against the version in force on
  its purchase date, and two candidates make that answer arbitrary.

- **AC-P3 [BE][FE]** Given a policy, When an admin adds a Term, Then it names one Kind and
  one part, with either a duration in months or lifetime (never both, never neither), an
  optional defect-type restriction, whether installation is included, and any registration
  bonus months.

- **AC-P4 [FE]** Given a Kind, When viewed, Then every Term under it is listed together -
  a Water Closet carries three simultaneously that disagree on all four dimensions, and a
  screen that shows one at a time cannot be checked against the policy document.

- **AC-P5 [BE][FE]** Given the Kind Rules screen, When an admin adds a rule, Then it names a
  match type (`category`, `model_prefix`, `model_list`, `series`), a value, and a priority,
  and higher priority wins before match-type specificity (AC-D20).

- **AC-P6 [FE]** Given a product code typed into a rule tester, When submitted, Then the
  resolved Kind is shown along with the rule that decided it - so an admin can tell a
  working mapping from a lucky one before saving.

- **AC-P7 [FE]** Given the Kinds list, When shown, Then each Kind states how many rules
  currently reach it, and zero is visibly flagged. A Kind no rule reaches can never be
  assessed, and that is invisible today.

- **AC-P8 [BE]** Given a term or rule is edited, When saved, Then existing
  `warranty_assessments` are NOT recomputed - an assessment is what was decided at the time,
  and silently rewriting history is how a verdict a consumer was told stops matching the record.

## Phase C - Propose a date, and let the consumer answer (S8)

**Prerequisite [CFG]:** Voice Calls must be enabled on the Sorento Respond.io workspace, and
the `Call Ended` webhook pointed at this system. Verified externally: respond.io publishes a
**`Call Ended` webhook** (call id, direction, status, timestamps, duration, plus recording /
transcript / summary when enabled) but **no call-history API**. Calls therefore arrive as
events; they cannot be fetched retrospectively. If a call ends while the webhook is
misconfigured, that call is simply not on the record - there is no backfill.

- **AC-C1 [BE][MIG]** Given the service_jobs table, When migrated, Then it carries
  `proposed_scheduled_from`, distinct from `scheduled_from`. A date we suggested is not a
  date anyone agreed to, and one column for both recreates the "Service Date: TBA wearing a
  Confirmed badge" failure S6 exists to prevent.

- **AC-C2 [FE]** Given a Proposed job, When Agnes uses "Trigger call", Then the contact's
  Respond conversation opens in a new tab, resolved through `respond_io_id` (never the
  internal contact id).

- **AC-C3 [BE]** Given a `Call Ended` webhook for a contact with an open Service Job, When
  received, Then a call record is stored against that job with its status, direction and
  duration, and the payload is logged in the integration outbox whether or not it matched.

- **AC-C4 [BE]** Given a `Call Ended` webhook whose contact has NO open job, When received,
  Then it is logged and dropped without error - not every call is about a visit.

- **AC-C5 [FE]** Given a job with calls recorded, When opened, Then they are listed with
  who called, when, how long and whether it connected.

- **AC-C6 [BE][FE]** Given Agnes enters a date and presses Propose, Then
  `proposed_scheduled_from` is set, the job STAYS Proposed, and a WhatsApp template naming
  the date goes out with Confirm and Reject.

- **AC-C7 [BE]** Given the consumer taps Confirm, When the reply is ingested, Then the job
  moves to Confirmed with `scheduled_from` = the proposed date and
  `customer_agreed_by` = "Consumer on WhatsApp", with no staff input. AC-F5's two-part rule
  is satisfied by real agreement, not bypassed.

- **AC-C8 [BE]** Given the consumer taps Reject, When ingested, Then the job stays Proposed,
  `proposed_scheduled_from` is cleared, `waiting_on_party` = customer, and a follow-up asks
  for a time that suits.

- **AC-C9 [BE]** Given a reply that is neither button (free text), When ingested, Then it is
  attached to the case for Agnes and changes no status. Parsing "can ah, but after 5pm lah"
  into a datetime is a guess wearing an appointment.

- **AC-C10 [BE]** Given a job that is not Confirmed, When a technician assignment is
  attempted, Then it is refused with a message naming the reason - enforced in
  `assign_technician`, not only hidden in the UI.

- **AC-C11 [BE]** Given a duplicate webhook delivery (same call id or same reply message id),
  When received, Then it is ignored. Respond retries, and a retried Confirm must not
  re-confirm a job somebody has since rescheduled.

## Phase D - Calendar dispatch board (S9)

- **AC-D1 [FE]** Given the dispatch board, When opened, Then it defaults to a month view
  with one block per day showing that day's jobs.

- **AC-D2 [FE]** Given a day block, When clicked, Then a day view opens showing time of day
  down one axis and technicians across, so capacity is visible rather than inferred.

- **AC-D3 [FE]** Given a job on the calendar, When clicked, Then a popup shows its details
  with a link to its own page, and the actions available in the panel today.

- **AC-D4 [FE]** Given jobs with no date, When the calendar is shown, Then they remain
  reachable in a list beside it. A calendar's blind spot is exactly the job with no day, and
  that is the job most likely to be forgotten.

- **AC-D5 [FE]** Given a month with no jobs, Then the empty state says so per the CRUD
  standard rather than rendering an empty grid.

- **AC-D6 [FE]** Given any of the above at 375px, Then it is usable - the month grid falls
  back to a list rather than overflowing horizontally.

## Cross-cutting

- **AC-X1 [T]** No new screen carries explanatory prose. Feature explanation belongs in the
  docs (cursor rules); a screen that describes itself has already failed.

- **AC-X2 [FE]** Every new listing uses the shared `DataGrid`, every new dialog the shared
  dialog, per ARCHITECTURE-RULES.

- **AC-X3 [BE]** Every outbound WhatsApp writes an `integration_log` on success AND failure.

- **AC-X4 [BE]** Every new permission is granted to the provisioned roles in the same
  migration that creates it (DoD gate 3).
