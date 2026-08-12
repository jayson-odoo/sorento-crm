# PLAN - One status field for purchase requests and sponsorship forms

> Status: SCOPED, NOT STARTED. 2026-08-10.
>
> Raised by the user while reviewing the Form SLA Undo correction message: *"why approved
> already still under submitted state, why pending approval already still under submitted
> state"*, then *"I really want to get this approval status out of the way to enjoy the
> benefit of this once and for all"*.
>
> **Decision: the full refactor, to a single column.** A display-only fix was considered
> and rejected - it hides the contradiction instead of removing it.

## The problem, in the data

`purchase_requests` (which backs BOTH purchase requests and sponsorship forms) carries
two parallel state columns - `status` and `approval_status` - and neither is
authoritative. Both are plain `varchar`, so nothing constrains the pairing.

Every combination live on the dev database (a copy of production):

| `status` | `approval_status` | rows | `submitted_at` set | last seen |
|---|---|---|---|---|
| approved | approved | 31 | 31 / 31 | 2026-08-10 |
| draft | *(null)* | 23 | 0 / 23 | 2026-08-10 |
| processed_by_cs | approved | 18 | 18 / 18 | 2026-08-10 |
| submitted | pending | 18 | 18 / 18 | 2026-08-10 |
| rejected | rejected | 11 | 11 / 11 | 2026-08-04 |
| submitted | *(null)* | 4 | 4 / 4 | 2026-08-06 |
| **draft** | **approved** | **5** | **0 / 5** | 2026-04-07 |
| **draft** | **rejected** | **5** | **0 / 5** | 2026-05-09 |
| **draft** | **pending** | **2** | **0 / 2** | 2026-05-09 |

**12 rows are in states that cannot both be true.** A draft that is also approved is not
a rendering problem - it is corrupt data the schema permits, and nothing stops more of it
appearing tomorrow.

Note also `approved | approved` (31) and `rejected | rejected` (11): 42 rows where the two
columns carry one fact twice. Duplication is not benign here; it is exactly what lets them
drift apart.

## The cost being paid now

With no column answering "what state is this form in", every surface derives it, and each
derivation is a separate copy of the same rule:

1. `PurchaseRequestsList.tsx` - `getDisplayStatus()`, the reference implementation
2. `PurchaseRequestDetail.tsx` - its own CTA gating on `approval_status` + `status`
3. `app/(auth)/portal/lib/portal-client.ts` - `SUBMISSION_STATUS_LABELS`, contact-facing
4. `app/services/form_action_notify.py` - `_pr_display_status()`, written 2026-08-10 for
   the undo correction message, and the direct trigger for this document

Four copies, two languages. They have already disagreed: an approved-then-processed
request read "Approved" in one place and "Processed by CS" in another, which is why a
terminal-CS-wins clause had to be pasted into three of them. Writing the fourth copy is
what made the underlying problem worth fixing rather than papering over again.

Surface: **80 backend references across 14 files**, **45 frontend references across 13
files**, **0 in the MCP server** - which removes one class of external breakage.

## Target model

One column, one truth:

```
status ∈ { draft, submitted, pending_approval, approved, rejected,
           processed_by_cs, closed, voided }
```

`pending_approval` becomes a real state instead of the implicit
`status='submitted' AND approval_status='pending'` pairing.

`approval_status` stops being state and is **dropped outright at S6** (decided
2026-08-10 - not retained as `approval_decision`). Nothing is lost: decision provenance
already lives in its own columns (`approved_at`, `approved_by`, `rejected_by_id`,
`approval_comments`), which are untouched, and `status` itself records the outcome.

## Backfill

Derived, not judged. `submitted_at` cleanly separates the two eras: it is set on
**82 / 82** coherent rows and on **0 / 12** contradictory ones, and the contradictions
stop on 2026-05-09 while `submitted | pending` begins 2026-05-04. The 12 are one legacy
cohort from before the lifecycle column was maintained, where `approval_status` +
`approved_at` were the working state and `status` was simply never advanced.

So the decision column is the truth for exactly that cohort, and `status` is the truth
everywhere else:

| selector | new `status` | rows |
|---|---|---|
| `status='draft' AND approval_status IS NULL` | `draft` | 23 |
| `status='submitted' AND approval_status IS NULL` | `submitted` | 4 |
| `status='submitted' AND approval_status='pending'` | `pending_approval` | 18 |
| `status='approved'` | `approved` | 31 |
| `status='rejected'` | `rejected` | 11 |
| `status='processed_by_cs'` | `processed_by_cs` | 18 |
| `status='closed'` / `'voided'` | unchanged | 0 |
| **`submitted_at IS NULL AND approval_status IS NOT NULL`** (the legacy 12) | **`approval_status`, mapped: pending -> `pending_approval`** | 12 |

The legacy selector is asserted in the migration: if it matches anything other than the
12 known rows at deploy time, the migration stops rather than guessing.

**Decided 2026-08-10:** `PR-VERIFY-001` and `SF-VERIFY-001` are test data and are
**deleted**, not migrated - so the cohort is 10 rows, and the migration's assertion
expects 10 after the delete.

## Slices

- **S1 - one derivation, server-side.** Backend emits `display_status`; the four local
  copies are deleted. No schema change, so it lands and ships on its own, and it is the
  read-side landing pad every later slice writes into. Not a substitute for the rest.
- **S2 - widen the value set.** Add `pending_approval` as an accepted `status` value.
  Nothing writes it yet. Reads treat it as equivalent to the old pairing.
- **S3 - writes.** Every service that sets state sets `status` only:
  `_apply_approval_decision`, `set_pending_approval`, `reject_submitted`,
  `_finalize_request`, `void_request`. `approval_status` is kept in sync by the service
  for one release so a mid-deploy mixed fleet cannot break.
- **S4 - backfill + constraint.** Run the table above, then add the CHECK. Must land
  strictly after S3: the constraint rejects writes that pass today, which is the point,
  but any path still writing the old pairing turns into a 500.
- **S5 - reads.** Sweep the 45 FE / 80 BE references onto `status` (most collapse to
  reading one field, since S1 already centralised the display rule).
- **S6 - drop `approval_status`.** Only after a release in which nothing reads it, and
  only after the n8n grep in Risk 2.

## Risks

1. **Contact-facing surfaces.** `portal-client.ts` and `app/(auth)/approval/page.tsx` map
   these values into copy a customer reads. A missed value shows a raw column value to a
   customer. S1 concentrates this into one place before anything moves.
2. **n8n.** The MCP catalog has zero references, but n8n workflows may read
   `approval_status` straight off API responses. Grep the workflows before S6, not after.
3. **Form-SLA event wiring.** `resolve_event` values (`approved`, `reject_submitted`) are
   matched against `form_sla_configs` rows. Changing state names without updating that
   config silently stops stages resolving - a failure with no error.
4. **Sequencing against Form SLA Undo.** The undo `capture` lists name `approval_status`
   explicitly, and both features touch the same five service methods. Undo is complete but
   uncommitted on `feat/form-sla-undo`; land it first, then start S1.
5. **`users.status` is a PG enum the model maps as `String`** and that has bitten before.
   Prefer a CHECK constraint here over an enum - cheaper to extend, same guarantee.

## Decided

- **Drop `approval_status` at S6.** Not retained as history - the provenance columns
  already cover it.
- **Delete `PR-VERIFY-001` / `SF-VERIFY-001`** rather than migrating test data.

Nothing outstanding. Ready to start once Form SLA Undo is committed (Risk 4).
