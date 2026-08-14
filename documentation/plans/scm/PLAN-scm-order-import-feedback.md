# PLAN - SCM order imports: agents, duplicates, async, standard modal

**Status:** S1 + S2 built (branch `feat/scm-order-import-feedback`, backend only, uncommitted).
S3, S4, S5 not started. S6 planned, captain's go pending. Contract:
`UAC-scm-order-import-feedback.md` (same directory). Captain feedback sections 1-6 in
`firstmate/data/so-import-feedback/captain-feedback.md`.

**S1 + S2 ship the agent data with NO surface on it.** `unmapped_agents` is on both the
preview and the apply response, and nothing renders it: the FE `OutstandingPreview` type does
not carry the field, so "new agent, unclassified" (AC-6.4) is true of the API and invisible to
the operator until **S4** adds the section. Likewise the demand class an agent carries can be
set only through `sales_agent_service.set_demand_class`, with no admin screen until **S6**.
Both gaps are deliberate ordering, not oversights, and each is closed by exactly one slice
below.

**Deviation, S2/AC-1.2 (PO + SPO history aliases): NOT built.** The 27 header spellings of
`PO & SPO 2023.xlsx` are recorded nowhere this repo can read - the verified-facts note below
states the column COUNT, not the names, and the file itself is not in the tree. Seeding
invented spellings would produce alias rows that match nothing while reading as done, so the
AC moves to S5, which reads that format and must have the real header row in front of it
anyway. AC-1.1 (the outstanding-SO file) is built in full.

## Verified facts the plan is built on (do not re-derive)

- Outstanding SO file: 4,349 rows, 38 distinct agent codes decomposing to 16 people via a
  `(base name, I|III|IV)` split; no `II` exists; suffix maps to NEITHER company nor market
  segment in the DB, so its meaning is not derivable - hence AC-3.3 (seed codes, class NULL).
- 605 duplicate-key groups; 567 differ in qty/price/remaining; 38 byte-identical. No line
  number column exists in the export.
- The reader ALREADY keeps duplicate lines (`result.lines.append` is unconditional); only the
  false RowProblem is emitted. `outstanding_diff.py` already groups by (doc, item, location)
  and pairs exact-date-then-date-order.
- `PO & SPO 2023.xlsx`: one sheet, 27,192 rows, 27 columns, 13,641 PO (`202...`) + 13,550
  SPO (`SPO...`). `Shipping Order` flag agrees with the prefix except 10 rows - discriminate
  on the Doc No PREFIX, never the flag (a misfiled row would silently become netting supply,
  ADR-337).
- `sales_agents` exists (2 rows, no company_id); `salesman_code_users` exists (0 rows,
  user-FK NOT NULL - wrong shape for a master, leave dormant). **Corrected during S1:** the
  table belongs to the UNMERGED AutoCount branch (`sorento_crm-autocount`, model
  `app/models/sales_agent.py`, migration `303_autocount_slice2_masters`), which is why main
  has no model and no migration for it. S1's migration reproduces those five columns verbatim
  and only ADDS to them, so the two chains describe one table. Its 2 rows are `ZZT`-prefixed
  test residue (`ZZT Loh Han Cong`, `ZZT Agnes Tan`), not master data - the captain's
  keep-or-clean question answers itself.
- Current apply routes are fully synchronous (parse + write + commit inline; the sales-history
  504 already proved the failure mode at 72k lines).

## Slices, in build order

### S1 - Agent master (backend only)

1. Migration: `sales_agents` gains `person_label` (nullable), `demand_class` (nullable,
   values validated against the market-segment-to-class vocabulary), `company_id` (nullable
   uuid, NULL = shared master), `source` (varchar, 'manual'|'import'). Seed the 38 codes from
   nothing - they arrive via import (AC-6.4), no hardcoded seed.
2. `sales_orders` gains nullable `sales_agent_id` FK.
3. Service: `sales_agent_service.resolve_or_create(db, code)` - normalised on
   `upper(btrim())`, creates with `source='import'`, returns row. Used by the import task.
4. pytest: resolve-or-create idempotent; unknown code creates + reports; demand_class
   vocabulary enforced.

### S2 - Aliases + reader fix + agent classification (backend)

1. Alias migration for the 7 SO columns (AC-1.1) and the PO/SPO history columns (AC-1.2),
   with deliberately-ignored mappings where no stored field exists. `bootstrap_env` replay.
2. Remove the "stated twice" RowProblem from `outstanding_reader.py` (AC-2.1). The diff layer
   is untouched - it is already correct.
3. `_classify_demand` gains step 4: agent's `demand_class` via the document's agent code
   (AC-3.1/3.2). Unmapped agent -> falls through to the existing report.
4. Outstanding SO apply stamps `sales_agent_id` (AC-6.5).
5. pytest: the captain's duplicate examples (identical pair + differing pair) import both
   halves; re-import reads unchanged (AC-2.3/2.4); SO-shaped fixture with agent-only
   classification resolves; agent unmapped -> reported not defaulted.

### S3 - Async conversion (backend)

1. New task functions in `app/tasks/import_tasks.py` per channel (outstanding SO, outstanding
   PO, purchase history, sales history, order inquiry), each: `_apply_import_job_scope` ->
   service apply -> `ImportOutcome` per row -> `complete_job(**completion_counts(),
   result=finalize(...))`. `update_job_progress(total_rows=...)` immediately after read.
2. Routes: keep `.../preview` synchronous at request scope (AC-4.2); `.../apply` becomes
   202 + job creation + `store_import_source_file` + enqueue, mirroring
   `app/api/v1/procurement/grn.py`. 400 before any job row when no single-company scope
   (AC-4.3). Job types named per channel (`outstanding_so_import`, `po_history_import`, ...)
   and labelled in `upload_activity` + both FE label maps.
3. The per-row outcome mapping: reader problems -> skipped with codes; diff results ->
   created/updated/unchanged/closed counts. Closed lines are recorded per row (they are the
   destructive half and belong in the job detail).
4. pytest: route 400-without-scope (job table stays empty); 202 + job row + source file;
   task path per-row outcomes land; worker-scope stamping (company snapshot honoured).

### S4 - Standard modal (frontend)

1. Rework the SCM upload dialogs (outstanding, history, order-inquiry channels) to the
   GRN/SPO behaviour contract: file select does NOTHING; Test button runs preview; Confirm
   queues and calls `notifyImportQueued()` (AC-5.1/5.3).
2. Shared warning/rejected-rows section: extract the component GRN/SPO use (or the customer
   importer's result panel if that is the settled one - the coder reads all three and names
   the winner in the PR) into `components/common/` and use it in BOTH the SCM dialogs and at
   least one existing dialog to prove it is genuinely shared (AC-5.2).
3. **Surface `unmapped_agents` in the Test result (AC-6.4 / AC-3.3).** The backend has
   returned it on BOTH responses since S2 and no screen reads it, so today an upload invents
   master rows the operator is never told about. Concretely:
   `app/(protected)/scm/reorder/services/outstandingImportService.ts` gains
   `unmapped_agents: OutstandingAgentNotice[]` (`{ code: string; is_new: boolean; reason:
   string }`) on `OutstandingPreview` AND on `OutstandingApplyResult` - the backend already
   sends the same key on both, and the commit's copy is the one that says which agents THIS
   upload created. `ProblemSections` in `components/OutstandingUploadDialog.tsx` gains a
   section for it, beside the unmapped-headers / row-problems / resolution-issues ones it
   already renders, worded as the backend words it ("new agent, unclassified") and NOT mixed
   into the rejected-row lists: nothing is skipped and no row failed, so putting it there
   would make a clean file read as a broken one. Empty list = no section.
4. vitest: no-validate-on-drop pinned (dropping a file fires no fetch); test-then-upload
   flow; warning section renders skip vs non-skip warnings without the false "rows are
   skipped" claim (the customer-importer B3 lesson); a preview carrying `unmapped_agents`
   renders the codes, and an empty one renders no section.
5. Playwright MCP verification against a real stack, sidebar-first, on the captain's own two
   files. Prod build for handoff.

### S5 - PO/SPO history split (backend, extends the existing history channel)

The real header row of `PO & SPO 2023.xlsx`, read from the file on 2026-08-14 (the earlier
draft of this PLAN recorded only the count, which blocked AC-1.2 in S2; the aliases belong
here with the structured reading):

`Item Code, Qty, Transfered Qty, Remaining Qty, Loading Date, Agent, Location, Doc No,
Doc Date, Delivery Date, Ref, Description, Creditor Name, Shipping Order, ICB Name,
Account Book, Is Posted, Running No, Post Gross Figure, Enable Auto Price, ICB To DocNo,
IB From SOKey, Import Post, Desc2, Width, Standard Price, FromSODocList`

1. The purchase-history reader accepts the structured 27-column format alongside the banded
   report format it reads today (detect by header shape). One reader, two writers: rows
   route by Doc No prefix - `SPO...` -> SPO history writer, else PO history writer.
2. SPO history lands closed/fully-received exactly like PO history (this is HISTORY, never
   netting supply - same rule the channel already enforces).
3. pytest: real-shaped fixture with both families; the 10 flag-disagreeing rows follow the
   prefix; totals reconcile (13,641 + 13,550 + header = 27,192).

### S6 - The agent master gets a screen (backend + frontend). PLANNED, NOT STARTED

Captain's go pending. Everything above assumes the client fills in `demand_class` on 38 rows,
and today the only way to do that is `sales_agent_service.set_demand_class` from a Python
shell. So the classification the whole of AC-3 is built on cannot actually be entered, and
S1's honest report ("this agent carries no demand class") points the operator at a screen that
does not exist.

Deliberately MINIMAL - a list and an edit of the two annotation columns, not a CRUD master:

1. List: DataGrid of `sales_agents` (code, `person_label`, `demand_class`, `source`,
   `is_active`), search on the code. No create and no delete - a row is created by an upload
   meeting a code, which is the only place the codes are known, and deleting one would
   orphan the orders that name it.
2. Edit: modal, two fields, `person_label` free text and `demand_class` a clearable
   `SearchableSelect` over `DEMAND_CLASSES` plus unset. Writes through
   `sales_agent_service.set_demand_class` (which already refuses a word the policy cannot
   weigh, and already refuses to create an agent on the way past) plus the label.
3. **The AutoCount merge is the constraint on where this lands.** That branch already ships a
   read-only mirror page for this table at
   `master-data-management/sales-agents` (list + `[id]` detail), whose backend is
   `app/api/v1/master_data/sales_agents.py` with a `PATCH /{id}/annotation`. Three things must
   not be lost when the two chains meet:
   - `MirrorAnnotationUpdate` allows `internal_note` and `follow_up` ONLY (`extra="forbid"`),
     so `person_label` and `demand_class` must be added to it or the merged page silently
     cannot write them;
   - `SalesAgentResponse` does not declare them either, and FastAPI's `response_model` drops
     any field a schema does not declare, so the values would read as absent on a page that
     is in fact holding them;
   - `_MirrorBase.source` is `Literal["autocount", "manual"]` while S1's `source` column
     carries `manual` or `import`. An import-created agent would fail response validation on
     that page. Widen the literal (or map it) as part of the merge.
   Preferred shape: extend that existing page rather than build a second one, and if S6 ships
   before the merge, build it there so the two are the same surface by construction.
4. pytest: `set_demand_class` route happy path + auth denial + a word outside the vocabulary;
   a `source='import'` row serialises. vitest: the select offers exactly the two classes plus
   clear, and saving invalidates the list.

## Sequencing note

S1 and S2 are one PR (agent + classification are the same story). S3 + S4 are one PR (async
and the modal are two sides of one contract change). S5 rides with S3's task work or follows.
S6 is independent of all of them and gated on the captain's go; it is what turns AC-3 from a
mechanism into a feature, so it should not wait behind S5.
Each PR: tests in-phase, browser verification for S4, `/code-review` before handoff.

## Risks

- The async conversion changes the apply response contract; the FE must move to job-based
  outcomes in the same PR or the drawer shows a job the page never linked to.
- The shared warning component touches GRN/SPO surfaces; regression tests on those dialogs
  are part of S4, not optional.
- `sales_agents.company_id` NULL-as-shared echoes the container_size cross-tenant read noted
  in the allowlist; acceptable for a master table, recorded in the migration docstring.
- The demand-class map ships empty: until the captain fills it, SO375073-class documents keep
  reporting unclassified. That is the designed behaviour, not a failure.
