# UAC - SCM order imports: captain feedback round (agents, duplicates, async, standard modal)

**Status:** Approved by captain 2026-08-14 ("the scm plan is also okay already, make sure it
covers the agents, async, using standard component, proceed"). Feedback source:
`firstmate/data/so-import-feedback/captain-feedback.md` sections 1-6.

## Journey

**Who.** The purchasing operator uploading AutoCount extracts: the outstanding dealer SO book,
and the PO + SPO history book. They arrive from SCM -> Reorder Planning -> Upload data, the
same place every SCM upload lives.

**Step 1 - choose the file.** Same dialog shape as GRN and SPO: drop or browse. Nothing runs
on drop (AC-5).

**Step 2 - Test.** An explicit button, user-triggered. The system answers in the file's own
terms: rows read, what would change, columns it could not place, rows needing a look. Zero
unrecognised columns on the captain's own files (AC-1).

**Step 3 - Confirm.** The job queues on the shared imports machinery; the upload drawer opens
and polls; the operator can leave (AC-4).

**Step 4 - read what happened.** Import-jobs detail: per-row outcomes, source file retained.
Both halves of a legitimately duplicated SO line present (AC-2). SO375073 classified from its
agent, not left unclassified (AC-3).

## AC-1 Every column in the captain's files is recognised

- **AC-1.1** Outstanding SO file: `Agent`, `Ref Doc No`, `Ref`, `Item Description`,
  `Discount`, `Total (Inc)`, `IB From PO` (header cell reads `IB From POKey`) all resolve.
  `Agent` lands in a real field consumed by AC-3; the rest map to stored fields where one
  exists or are seeded as deliberately-ignored aliases so they stop appearing as unrecognised.
- **AC-1.2** PO + SPO history file (27 columns, verified against the real
  `PO & SPO 2023.xlsx`): all resolve or are deliberately ignored, same rule.
- **AC-1.3** Aliases are seeded by migration under the existing doc types, replayed by
  `bootstrap_env` (CI runs no migration bodies). A future spelling is an alias row, not a
  release.

## AC-2 Duplicate SO lines are data; idempotency comes from grouped pairing

Verified against the captain's real file: 605 groups share `(doc, item, location)`; 567 of
them differ in qty/price/remaining (distinct lines, never duplicates); 38 are byte-identical
(the captain: "this is totally acceptable in 1 SO").

- **AC-2.1** The reader-level "the same line is stated twice" rejection is REMOVED. Every row
  loads. (The reader already kept the line; only the false problem-report goes.)
- **AC-2.2** There is NO per-line key in the export (no line number column - verified). Line
  identity within a `(doc_no, item_code, location)` group is positional: exact-date matches
  pair first, leftovers pair sorted by date; surplus incoming inserts, surplus existing
  closes. This is `outstanding_diff.py`'s existing behaviour, now the single authority.
- **AC-2.3** Re-import of the same file is idempotent: the second run pairs incoming lines
  against the now-existing lines and reads `unchanged`. Pinned by test with a two-identical-
  lines fixture.
- **AC-2.4** Two byte-identical lines: pairing between them is arbitrary and harmless (they
  are indistinguishable; either assignment yields the same DB state). Stated in a comment,
  pinned by test.

## AC-3 Agent classifies an order when nothing else does

- **AC-3.1** Classification precedence gains a fourth step, after the existing three and
  before the report: header's stored type -> type stated in file -> customer market segment
  -> **agent's demand class**. Only when all four miss is the document reported unclassified.
  Never defaulted (the existing rule stands).
- **AC-3.2** The agent's class comes from `sales_agents.demand_class` (AC-6). An agent code
  with no class set contributes nothing and the document falls through to the report.
- **AC-3.3** The mapping CONTENT is the captain's to fill: 38 codes exist in his file, the
  suffix (I/III/IV) is a division whose meaning is not derivable from the database (verified:
  it maps to neither company nor market segment). The system seeds the 38 codes with
  `demand_class` NULL and reports unmapped agents in the Test result. No guessing.
  **Split across slices:** S2 puts `unmapped_agents` on the preview AND apply responses;
  **S4** renders it in the Test result (`OutstandingPreview` gains the field,
  `ProblemSections` gains the section). Until S4 the fact is in the API and invisible on
  screen, so the AC is not met by S2 alone. Filling the classes in needs **S6** (AC-6.6).

## AC-4 Async on the existing import machinery

- **AC-4.1** Outstanding SO and outstanding PO apply, and purchase-history + sales-history +
  order-inquiry apply, run as queued import jobs: `JobService.create_job` (company snapshot,
  migration 303), `store_import_source_file`, `enqueue_job(queue_name="imports")`, worker
  task via `_apply_import_job_scope`, per-row outcomes via `ImportOutcome`, terminal counts
  via `completion_counts()`/`finalize()`. Appears in system-management/import-jobs for free.
- **AC-4.2** Preview/Test stays synchronous (it writes nothing and the operator is waiting
  for the answer), but runs at the same company scope the queued job will run at.
- **AC-4.3** The route refuses (400) when no single-company scope is active, before creating
  any job row - same rule as the customer importer, same reason (owned tables).
- **AC-4.4** The response contract changes from "the apply result" to "202 + job id". The FE
  reads outcomes from the job, not the response body.

## AC-5 Standard modal, standard components, test-then-upload

Captain: "use the same component as other uploads for the warning section... we supposed to
use test just like other import, then after we click upload, also should behave just like
other import."

- **AC-5.1** Nothing validates on file drop. Test is an explicit button.
- **AC-5.2** The warning / unrecognised-column / rejected-row section renders with the same
  shared component(s) the other import dialogs use - not a bespoke panel. If the SCM dialogs
  and the GRN/SPO dialogs currently render this differently, the shared extraction serves
  both and the PR names which component became the shared one.
- **AC-5.3** After Confirm: `notifyImportQueued()`, drawer opens, 5s polling to terminal,
  outcome surfaces on the job pages. No per-page status bar.
- **AC-5.4** Any place the SO/PO import genuinely must differ from GRN/SPO is stated in the
  PR description with its reason, never diverged silently.

## AC-6 The agent entity is a salesperson master, not a user, not a Respond contact

Captain's ruling (2026-08-14): "ideally i don't want agent to come from user, agent is like
salesperson master that is common in every ERP, cause these salesman shouldn't have user
account in our system, or optional at least." This supersedes the earlier open question about
reusing Respond contacts: agents are internal salespeople, Respond contacts are external
messaging counterparties, and ADR 0007's keep-entities-in-their-right-table reasoning applies.

- **AC-6.1** `sales_agents` (existing table: `sales_agent` unique, `description`,
  `is_active`, `internal_note`, `follow_up`) is the master. One row per agent CODE as it
  appears on documents (`SEAN I`, `SEAN III`, `LCL`). The code is the key.
- **AC-6.2** New nullable columns: `person_label` (groups SEAN I/III/IV for reporting -
  metadata, not identity), `demand_class` (AC-3), `company_id` NULL = shared master (agents
  sell for both companies in the captain's files; scoping decision recorded, not forced).
- **AC-6.3** NO link to `users` in this slice. A nullable `user_id` FK is future work, only
  if a salesman ever needs a login. NO link to `respond_contacts`.
- **AC-6.4** Import behaviour on an unknown agent code: create the row (is_active true,
  demand_class NULL) and report it in the Test result as "new agent, unclassified". Never
  block the file on it. The report is a `unmapped_agents` list of its own on both the preview
  and the apply response - never merged into the rejected-row lists, since nothing was skipped
  - and **S4** is the slice that renders it (see AC-3.3).
- **AC-6.5** Orders store the agent: outstanding SO import stamps the resolved agent onto the
  sales order (nullable FK). The future agent-serves-customer assignment is out of scope but
  must not be foreclosed: FK from a future join table to `sales_agents.id` remains possible.
  A document whose rows name two DIFFERENT agent codes keeps the first (an order has one
  salesperson, and half a document attributed to whoever the export listed second is worse)
  and reports both by name, exactly as a document naming two counterparties already does.
  Silent first-wins would let row order decide the order's demand class, invisibly and stably.
- **AC-6.6** The two annotation columns are editable by an admin: a list of `sales_agents`
  and an edit of `person_label` + `demand_class`, writing through
  `sales_agent_service.set_demand_class` so the closed vocabulary is enforced on that path
  too. **S6, BUILT** (branch `feat/scm-agent-master-ui`). Without it AC-3 is a mechanism with no way to
  feed it: the 38 classes can only be set from a Python shell. Scoped as list + edit only -
  no create (codes are learned from uploads) and no delete (orders name the row).

## Out of scope

- Filling in the 38 demand-class values (captain's data). The SCREEN he fills them in on is
  AC-6.6 and is in scope, as S6; the values themselves are his.
- Agent-to-customer assignment feature.
- Any `salesman_code_users` change (dormant, untouched).
- The 2 existing `sales_agents` rows: reported to the captain for keep-or-clean, not deleted.
