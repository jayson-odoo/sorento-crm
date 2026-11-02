# CARD: PS-QUOTE-RULES (behaviour card, 2 Nov 2026)

Lane PS-QUOTE-RULES. Read of `main` at 46de2f6d. Every pointer below was checked in the code.

## What exists today (measured)

- Every quotation line already stores `is_non_standard` (product or set outside the project's
  series): `sorento_crm_backend/app/services/project_quotation_service.py:690-700`. It is shown as a
  flag only; nothing checks it before sending.
- There is already ONE approval gate on a quotation document, for minimum price:
  `app/services/project_quotation_approval_service.py`. `assert_issuable` (`:195`) blocks Issue when
  a line is below its floor and the document is not `approved`; "Send for approval" (`move`, `:380`)
  puts it on `pending_approval`; `approve` / `reject` need `projects.quotations.approve`
  (`:63`, `app/rbac/permission_registry.py:604`); Issue spends the approval (`mark_issued`, `:222`).
- "CK" in data = whoever holds `projects.quotations.approve`. Migration
  `alembic/versions/330_quotation_approval_gate.py:18-23` swept it to every role holding
  `projects.projects.manage` plus the role "Project Sales Manager". No person is hard-coded and
  none will be.
- "Final Negotiation" exists TWICE today:
  1. the manual flag `projects.is_critical` + `critical_at` (`app/models/projects.py:296-299`,
     `app/services/project_service.py:1371` `set_critical`), shown as the toggle
     "Critical / final negotiation" (`CriticalPanel.tsx:44`), and
  2. a stage rung `final_negotiation` on prod's project graph (made in the admin editor; edges in
     `alembic/versions/stg_0001_project_ladder_edges.py:29-41`). A fresh DB (and CI) has no such rung.
- There is no "discount request" object. The only management-approved discount is the
  "Send for approval" press on a quotation with a line below its minimum price.
- There is no separate proposal document yet (PS-PROPOSAL-QUOTATION adds it). This lane works on
  `ProjectQuotationDocument`; whatever that lane names a proposal inherits the same gate because
  the gate sits on the document.

## Rules (proposed)

B1. Off-series needs approval before sending.
1. A document "needs approval" when its current lines (the same latest-version-per-scope rule the
   gate uses today) carry at least one line below its floor OR at least one off-series line.
2. Issue (= send to the customer) is refused with 422 `quotation_needs_approval` until the
   document is `approved`. The message names both counts, e.g. "1 line is outside the project's
   series and 2 lines are below the minimum price, so this quotation needs a manager's approval
   before it can be sent to the customer."
3. Same Send for approval / Approve / Reject / Revise flow, same lock while pending, same
   permission, same notifications (copy names off-series lines too). One approval covers both
   reasons on that document.
4. Read from the STORED `is_non_standard` flag, never re-resolved (same rule as the floor, AC-E7):
   editing a series later does not retroactively block a quotation nobody changed.
5. A project with no series nominated has no off-series lines (`is_in_series` returns True,
   `project_pricing_service.py:1084`), so nothing changes for it.

B2. A discount request moves the project to Final Negotiation.
6. "Discount request" = the Send for approval press (or resubmit) on a document that has at
   least one below-floor line. An approval asked ONLY for off-series lines is not a discount.
7. On that press, in the same transaction:
   a. the critical flag is raised (`set_critical(True)`, stamps `critical_at` only on the
      transition into it), and
   b. if the project's graph has a `final_negotiation` rung and the project sits on an open
      (non-terminal) rung with a LOWER sort_order, the stage moves there (system move, a
      `stage_changed` feed row naming the requester). Not via the edge check, because Spec In
      has no edge to Final Negotiation on prod and the rule is the owner's, not the graph's.
   c. A project already at Final Negotiation or later (sponsorship_form, po_received, won, lost,
      dormant, any terminal rung) is not moved. No rung configured = flag only, logged.
8. Withdrawn (Revise while pending) or Rejected: the project STAYS in Final Negotiation and the
   flag stays raised. The negotiation happened; reverting would erase the stage clock and could
   undo a manual move someone made meanwhile. A manager lowers it by hand if the deal cooled.

## Examples

No dev DB is reachable from this cloud sandbox. Crew: please run
`documentation/plans/projects/ps-quote-rules-dev-examples.sql` on the dev copy and post the masked
output; the card's rule numbers above are what each query checks.
Synthetic cases the tests will use:
- A. Series "S1", one in-series line at default price: issues with no approval (unchanged).
- B. Same doc + one off-series line at default price: Issue 422; Send for approval -> pending;
  project stage NOT moved (no discount); Approve -> Issue OK; approval spent.
- C. One in-series line below floor, project at Spec In: Send for approval -> pending, project
  stage -> Final Negotiation, critical flag raised.
- D. Same as C but project at Sponsorship Form: flag raised, stage stays.
- E. C then manager rejects: stage stays Final Negotiation.

## Questions (each with a recommendation)

Q1. Approver for off-series lines: (a) the existing `projects.quotations.approve` holders,
    renaming its label to "Approve Quotations (minimum price, off-series)" (data-only migration,
    no DDL), (b) a new permission. Recommend (a): same people decide (management/CK), one grant
    path already swept to them; a second slug would 403 until someone grants it.
Q2. What counts as a "discount request": (a) Send for approval with a below-floor line,
    (b) also a customer's lower-price suggestion on the sign page, (c) any line priced below the
    default price. Recommend (a): it is the only discount management approves today, which
    matches "again approved by management" in the ruling.
Q3. Final Negotiation = (a) raise the flag AND move the stage rung forward, (b) flag only,
    (c) rung only. Recommend (a): the UI calls the flag "Critical / final negotiation" and
    prod's board has the rung; doing one leaves the other contradicting it.
Q4. Withdrawn/rejected discount: (a) project stays in Final Negotiation, (b) go back to the
    previous stage and lower the flag. Recommend (a), reasons in rule 8.
Q5. Off-series approval is spent at Issue like the floor approval, so each revision carrying an
    off-series line asks again: (a) yes, (b) approval sticks per product per document.
    Recommend (a): one gate, one rule, and a revision can change quantities on the line CK
    approved.

## Overlap with other PS lanes

- PS-PROPOSAL-QUOTATION: touches the same document, `quotationDecision.ts` and probably the
  approval service. I change `project_quotation_approval_service.py` (count + message + B2 hook),
  `QuotationApprovalPanel.tsx` copy and `quotationDecision.ts` only where the reason text lives.
- PS-REGISTRATION-V3: touches `project_service.py`; I only call `set_critical`.
