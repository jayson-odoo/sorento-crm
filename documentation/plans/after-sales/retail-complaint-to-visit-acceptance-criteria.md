# UAC - From a lodged retail complaint to a technician at the door

**Companion to:** `PLAN-retail-complaint-to-visit.md`
**Extends:** `after-sales-warranty-acceptance-criteria.md` (S1-S6 built). This covers what happens
AFTER a retail complaint lands, up to a technician being sent.
**Status:** Phase A (S7a) IMPLEMENTED 2026-08-08 - migration 330, verified end to end on a prod
build. Phase B (S7b) IN BUILD from 2026-08-09; its rulings are recorded below. Phases C and D
pre-code. Every AC self-verified end-to-end on the stated side(s) before handoff.
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

### Phase B rulings - decided 2026-08-09, before the gate

Eleven things AC-P1 to AC-P8 leave open. Each is ruled here so the red suite can assert it
rather than the implementer inventing it.

- **AC-P0a [FE][BE]** The screens live at `/warranty-management/*` under module key
  `warranty`, with slugs `warranty.*` - NOT under `/master-data-management/*`. Reason:
  `lib/route-module-map.ts` maps the `/master-data-management` prefix to moduleKey
  `product`, so a warranty editor placed there is gated by the *product* module. Uninstall
  warranty and its editor keeps standing; install warranty alone and it is unreachable.
  `app/modules/runtime/permission_module_map.py` already declares `warranty -> warranty`
  and nothing uses it yet, which is the mapping this slice is meant to consume.
  `manifest.ROUTER_PREFIX` and `EXPORT_FILES_FRONTEND` are updated in the same slice, or
  the module exports a surface it does not carry.

- **AC-P2a [BE][FE]** Given an open-ended policy in force, When an admin publishes the next
  version through **Supersede**, Then in ONE transaction the incumbent's `effective_to` is
  set to the day before the new `effective_from` and the new policy is created. Reason:
  AC-P2's refusal is right, and on its own it turns the screen's main job - publishing
  version N+1 - into a two-step an admin must perform in the correct order. A refusal with
  no supported path is a screen that says no to the only thing it exists for.

- **AC-P2b [BE]** Overlap arithmetic is the same arithmetic `policy_in_force` reads by:
  both ends INCLUSIVE, NULL `effective_to` meaning open-ended. Two policies of the SAME
  company overlap when `a.from <= coalesce(b.to, infinity)` AND `b.from <= coalesce(a.to,
  infinity)`. Policies of different companies never overlap each other. The refusal names
  the other version and its range, because "overlaps an existing policy" is not something
  an admin can act on.

- **AC-P2c [BE]** No database-level exclusion constraint is added, and the reason is
  recorded so a later reviewer does not "tighten" this into a deploy outage. The constraint
  that would express AC-P2b is
  `EXCLUDE USING gist (company_id WITH =, daterange(effective_from, coalesce(effective_to,
  'infinity'), '[]') WITH &&)`, which needs **`btree_gist`**. Measured 2026-08-09 on the dev
  database: installed extensions are `plpgsql`, `pg_trgm`, `vector` only - `btree_gist` is
  *available* but not installed, and whether `CREATE EXTENSION` is permitted on the managed
  production instance is not something this slice can verify. A migration that might be
  refused at deploy time is a worse trade than a service guard on a table with two writers
  and tens of rows. Revisit as a follow-up once `btree_gist` is confirmed creatable on
  prod; the service guard and `policy_in_force`'s deterministic tie-break stand until then.
  (Also measured: exactly ONE policy row exists today, so no overlap is being tolerated -
  this is a forward-looking guard, not an amnesty for existing data.)

- **AC-P3a [BE][MIG]** The duration/lifetime exclusion (`is_lifetime` XOR a positive
  `duration_months`) is enforced in the service, and ALSO as a CHECK constraint. Measured
  2026-08-09: all **41** existing `warranty_terms` rows satisfy it, so the constraint is
  written. Had any row failed, the constraint would have been dropped from the slice and
  said so - editing live rows to fit a constraint nobody asked for is not a migration.

- **AC-P6a [BE]** The rule tester runs the PRODUCTION ranking, not a copy of it.
  `resolve_kind` is refactored to delegate to a new `resolve_kind_match()` that returns the
  winning match (`_RuleMatch` gains the `rule` that produced it); `resolve_kind` returns
  `.kind` and its existing contract is unchanged. A tester with its own ranking agrees with
  production right up to the day it matters.

- **AC-P6b [BE]** The tester accepts an OPTIONAL unsaved candidate rule and ranks it
  alongside the saved ones, marked as unsaved. AC-P6 says "before saving": the admin's real
  question is whether the rule they are about to write will win, and a tester that can only
  see saved rules cannot answer it.

- **AC-P6c [FE]** The tester lists every rule that matched, in rank order, not only the
  winner. A mapping that wins by one tie-break is a different fact from a mapping that is
  the only match, and only the second one is safe to stop thinking about.

- **AC-P7a [BE][FE]** The Kinds list carries `rule_count` AND `term_count`, and zero is
  flagged on both. AC-P7 names only rules; a Kind that no Term covers returns `no_term` for
  every product that reaches it, which is the same invisible dead end one column further
  along and the same one-line fix.

- **AC-P8a [BE][FE]** Deleting a Term does not delete assessments:
  `warranty_assessments.term_id` is ON DELETE SET NULL and the snapshot columns keep the
  verdict readable without it. The delete confirmation names how many assessments reference
  the Term, per the repo's confirm-before-destroy rule.

- **AC-P9 [BE]** Terms are reachable only through their Policy
  (`/warranty-policies/{policy_id}/terms`), and the Policy is loaded FIRST so one outside
  the caller's company scope 404s. Reason: `WarrantyTerm` is deliberately not
  company-scoped, because it is only ever reachable through `policy_id` - which makes an
  unguarded nested route hand another company's terms to anyone who guesses an id.

- **AC-P10 [FE]** The Policies tab names the active company; the Kinds and Rules tabs state
  that they are shared across companies. This is a scope indicator, not feature prose, and
  is deliberately exempt from AC-X1: an admin editing a shared vocabulary from inside a
  company-scoped area will otherwise assume the edit is scoped, and be wrong.

- **AC-P11 [MIG]** Slugs are `warranty.policies.{view,add,edit,delete}` and
  `warranty.kinds.{view,add,edit,delete}`. Terms ride the policies slug and kind rules ride
  the kinds slug - a rule has no life apart from the Kind it points at, and a slug nobody
  will ever grant separately is a slug that rots. Reads take
  `require_permission_with_api_key`, writes take `require_permission`. Both slugs are
  granted to the provisioned roles in the same migration that creates them (AC-X4), which
  means the migration does more than call `sync_permissions` - that seeds the slug and
  grants nobody.

- **AC-P12 [BE]** Deleting a Kind is REFUSED while any Term or Kind Rule references it, and
  the refusal names both counts. Reason: `warranty_terms.kind_id` and
  `warranty_kind_rules.kind_id` are both ON DELETE CASCADE, so the obvious hard delete
  silently removes warranty promises from every policy at once, and the assessments that
  quoted them keep a snapshot pointing at a term that no longer exists. A master-data
  delete must not be able to rewrite the policy document.

- **AC-P13 [FE]** Deleting a Policy DOES cascade its Terms - they have no life apart from
  it - so the confirmation names how many Terms will go with it. A count is the difference
  between a considered delete and a discovered one.

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
