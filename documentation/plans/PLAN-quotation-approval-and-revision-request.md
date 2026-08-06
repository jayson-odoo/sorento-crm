# PLAN - Price-floor approval gate, and customer revision requests

**Status:** written 2026-08-05, not started.
**Parent:** `PLAN-project-quotation-document.md` (S1-S8, shipped), `PLAN-quotation-edit-view.md` (S10-S13, shipped)
**Slug:** quotation-approval-and-revision-request

## Why

Two more items from the same 2026-08-05 client review.

1. Price floors already exist and already flag a line (`is_below_floor`, `floor_value_applied`,
   `is_non_standard` on every `project_quotation_lines` row, computed by
   `project_quotation_service._apply_guardrails`, config CRUD at `/config/price-floors`,
   resolution in `project_pricing_service.resolve_floor`). None of it is enforced: a quotation
   with every line below floor issues exactly as freely as one that isn't. The client wants a
   real gate: below-floor pricing must reach a manager before it can be sent to the customer.
2. The counter-sign page only offers Accept. A customer who wants a lower price today has no
   button - they have to message someone outside the system. The client wants a "Request
   changes" action that captures feedback back into the CRM.

## Decisions taken with the client, 2026-08-05

- **Gate mechanism: register `quotation` as an entity_type in the generic status engine**
  (`app/models/status.py`, ADR-0001), NOT a dedicated `approval_status` column like PR/SF. This
  is the client's explicit choice over the recommendation (PR/SF's own pattern) - honour it. A
  quotation's flat `outcome` (`open`/`won`/`lost`, `project_quotation_service.py:709`) is
  UNCHANGED and stays orthogonal, the same way it already is for projects (a project has both a
  `status_id` graph position and its own separate fields). The new graph node is `pending_approval`
  between the existing implicit draft state and issuing.
- **Approver: a permission slug**, e.g. `projects.quotations.approve`, not a team-tier
  resolution. No team-set configuration to build; Approve/Reject render for anyone holding the
  grant. Note for the DoD gate (PRINCIPLES.md #3): whichever role should hold this (Sales
  Manager) needs the grant swept in, not left for someone to notice later.
- **Gate point: Issue, not Sign.** Signing (the internal signature) stays allowed at any price -
  it is readiness, not dispatch. `issue()` in `project_quotation_document_service.py` refuses
  when any line on any scope being issued is below floor and the quotation's current status is
  not `approved` (or has never needed approval, i.e. no line was ever below floor).
- **Revision request: feedback captured, salesperson revises manually.** A "Request changes"
  action beside Accept on the counter-sign page, with a required text box. Captured onto the
  issue (a new column, mirroring how `accepted_at`/`customer_signature_id` already capture
  acceptance), a project activity entry is written, and the assigned salesperson is notified
  (existing notification service, same channel `notify_floor_breach` already uses). The system
  does **not** auto-open a new revision - the salesperson presses the existing `Revise to vN`
  themselves once they have read it. Mirrors `accept_issue`'s shape closely enough that whoever
  builds it should read it first and follow the same idempotency/locking care (a double-submit
  must not double-notify).

## Slices

| # | Slice | Ships |
|---|---|---|
| **S14** | Quotation entity_type + statuses seed | Register `quotation` in `statuses`/`status_transitions` (mirror `project_seed_service.py`'s `PROJECT_ENTITY` seeding exactly - same shape, new `entity_type`). Minimum graph: `draft -> pending_approval -> approved -> issued`, `pending_approval -> rejected -> draft`. `status_id` FK added to `ProjectQuotationDocument` (the thing that gets issued), nullable, defaulting to the graph's initial state on create. |
| **S15** | The gate | `issue()` refuses (422, a code the FE can render, e.g. `quotation_below_floor_pending_approval`) when any line across the scopes being issued has `is_below_floor=True` and `status.key != 'approved'`. A quotation with NO below-floor line skips the graph entirely - never touches `pending_approval` - so nothing changes for the common case. Submit-for-approval action moves `draft -> pending_approval` (or the gate above triggers it automatically the first time Issue is pressed and a below-floor line exists - decide which reads better against `availableStatusMoves`/`splitStatusMoves`, the shared FE helpers already built for `ProjectStatusAction.tsx`, and reuse them rather than a quotation-specific status widget). |
| **S16** | Approve / reject | Two routes, permission-gated on the new slug. Approve moves to `approved` (and the issue proceeds on the next Issue press); reject moves to `rejected`, which the salesperson can move back to `draft` (edit, reprice, resubmit). Both write an activity entry naming who and, for reject, why (a reason field, required). |
| **S17** | Request changes | New column(s) on `project_quotation_issues` (e.g. `changes_requested_at`, `changes_requested_note`), a route on the public counter-sign path beside `accept`, a "Request changes" button and required feedback box on `QuotationSignClient.tsx`, a project activity entry, and a notification to the assigned salesperson. The accepted-state and requested-changes-state must both render clearly on the counter-sign page afterward (an already-decided state, not a form still waiting). |

## Open engineering questions for whoever builds S14-S16

- Exact transition set and who can move `rejected -> draft` (presumably the salesperson, no
  permission gate beyond normal edit rights, since it is just "try again").
- Whether `status_id` lives on `ProjectQuotationDocument` or on the issue - lean toward the
  document, since approval gates the NEXT issue, not a specific past one, and a document can be
  revised (new version) while still carrying the same approval position.
- The exact wording of the 422 and the on-screen banner, matching the tone of the existing
  `quotation_document_unsigned` gate (a clickable next action, not just a reason).

## Definition of done

1. A quotation with no below-floor line is completely unaffected - same Issue flow as today.
2. A below-floor quotation cannot be issued without `approved` status; the block names the
   reason and offers the way to request it.
3. Approve/reject are permission-gated, and the grant is swept to the intended role.
4. Request changes on the counter-sign page captures feedback, notifies the salesperson, and the
   page reflects the new state without a reload.
5. Verified at 375px and 1280px on a prod build, against real data.
