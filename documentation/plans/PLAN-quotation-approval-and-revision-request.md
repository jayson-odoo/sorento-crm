# PLAN - Price-floor approval gate, and customer revision requests

**Status:** S14, S15, S16 implemented 2026-08-06 (see "Decisions taken while building S14-S16"
below). S17 in progress separately.
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

## Decisions taken while building S14-S16 (2026-08-06)

Answers to the questions above, plus the two deviations from the slice table. Recorded here
because the plan is the contract for this work.

**The graph.** Five rungs, `entity_type = 'quotation'`, default scope only (no forks: a price
floor is a company policy, not a per-template one). Nothing is terminal - a quotation at
`Issued` is revised and issued again, and a rejected one is re-priced and asked again, so a
terminal flag on either would strand the document. `rejected` sorts BETWEEN `draft` and
`pending_approval` (sort_order 1) because the shared frontend helper `splitStatusMoves` reads
sort order to tell an advance from a correction, and being sent back is a step backwards;
sorted after `issued` it would have made Reject the primary button out of `pending_approval`.

| from | to | label | who fires it |
|---|---|---|---|
| draft | pending_approval | Send for approval | salesperson (edit rights only) |
| pending_approval | approved | Approve | manager, `projects.quotations.approve` |
| pending_approval | rejected | Reject | manager, same slug, reason required |
| rejected | draft | Back to draft | salesperson (edit rights only) |
| approved | issued | Issued to the customer | the system, stamped by `issue()` |
| issued | pending_approval | Send for approval | salesperson (edit rights only) |

`rejected -> draft` is confirmed as the salesperson's own move with no extra grant: it is just
"edit and re-price", and the edit rights they need to change the quotation at all are the
check.

**DEVIATION 1 - `approval_status_id` is NULL on create, not the initial rung.** The slice table
said "defaulting to the graph's initial state on create". It does not. DoD item 1 says a
quotation with no below-floor line is completely unaffected, and stamping `draft` on every
document created would enrol every quotation ever written into an approval lifecycle for the
sake of the minority that discount past the floor. NULL therefore reads as "sitting at the
graph's initial rung, and has never had to say so": the move service resolves the initial rung
as the from-position when the column is empty, so asking for approval is still ONE press. There
is deliberately no backfill for existing rows, for the same reason.

**DEVIATION 2 - explicit "Send for approval", not auto-submit on the first Issue press.** The
slice table offered either. Explicit wins on four counts:

1. A 422 that also mutates is a trap. The route's exception path rolls back, so an auto-submit
   would have to be committed before the refusal was raised - and a retry then takes a different
   path from the first press.
2. It matches the `quotation_document_unsigned` gate the salesperson already knows: the server
   refuses, the header names the reason, and a separate button does the thing.
3. Submitting pings a manager. Doing that as a side effect of a press that was meant to send the
   quotation means an accidental Issue has already escalated.
4. It reuses `availableStatusMoves` / `splitStatusMoves` honestly: the graph's own
   `draft -> pending_approval` edge IS the primary move those helpers surface, by the label the
   admin gave it. Auto-submit would have hardcoded the move inside `issue()` and left the shared
   helpers with nothing to render.

The block on screen therefore always carries reason AND action: "2 lines are priced below their
floor, so this quotation needs a manager's approval before it can be sent to the customer" with
a `Send for approval` button beside it, and the Issue CTA disabled with a matching title.

**Issuing spends the approval.** `issue()` moves an `approved` document to `issued`. A manager
approved THOSE prices; leaving it on `approved` for good would let the next revision drop
another line under the floor and go out on a decision nobody made about it.

**Reading the graph from the salesperson's screen.** `GET /project-sales/quotation-approval-graph`,
gated on `projects.projects.view`. The admin route `/statuses/graph/{entity_type}` is gated on
`system.statuses.view`, which only Admin holds, so the block could not have read the graph
through it. Same `StatusGraphResponse` shape, so the shared FE helpers read it unchanged.

**Approve / reject are not generic status moves.** Both edges exist, and the generic
`POST .../approval-status` route refuses them with 422 `quotation_status_not_self_serve`.
Reaching `approved` through a route that asks for no permission, or `rejected` through one that
asks for no reason, would make both rules decorative. `issued` is refused there too: it is
stamped by issuing, never claimed.

**Grant sweep (DoD 3).** Migration `330_quotation_approval_gate` seeds
`projects.quotations.approve` and grants it to every role already holding
`projects.projects.manage` (the sales-manager grant) plus any role named "Project Sales
Manager". On the dev database that resolved to `Project Sales Manager` and `Admin`.

## Definition of done

1. A quotation with no below-floor line is completely unaffected - same Issue flow as today.
2. A below-floor quotation cannot be issued without `approved` status; the block names the
   reason and offers the way to request it.
3. Approve/reject are permission-gated, and the grant is swept to the intended role.
4. Request changes on the counter-sign page captures feedback, notifies the salesperson, and the
   page reflects the new state without a reload.
5. Verified at 375px and 1280px on a prod build, against real data.

## S17 as built (2026-08-06)

Three decisions the slice had to take that the plan left open, recorded here because they are the
contract the tests pin:

- **Three columns, not two.** `changes_requested_at`, `changes_requested_note` and
  `changes_requested_by_name`. The third exists because acceptance gets a name for free off the
  signature row and a request has no signature: without it the salesperson is handed feedback
  from "somebody". The row holds the LATEST request; every request is also written to the project
  activity feed, so history survives an overwrite.
- **Accepted beats requested, and the ordering is asymmetric.** `POST .../request-changes` on an
  accepted issue is refused `409 quotation_already_accepted`: the counter-signature won every
  scope and moved the project's outcome, so a request standing beside it would be unreadable. The
  reverse IS allowed - somebody who asked for changes can still sign - the request stays on the
  row as history, and every surface (counter-sign page, Signatures tab badge) renders acceptance
  in preference to it. The read inside `request_changes` is `FOR UPDATE`, so two submissions from
  one thumb serialise instead of both notifying.
- **Idempotent on the words, not on the row.** The same note twice is one request: no new stamp,
  no second activity row, no second notification. Different words get through and notify again,
  the property `floor_breach_dedup_key` exists for (`changes_requested_dedup_key` mirrors it).
- **`quotation_changes_requested` is deliberately NOT a meaningful activity template.** A request
  nobody has answered is exactly when a project should look unattended; advancing the staleness
  clock here would clear the badge the moment the customer complains.
- Recipient is the project's `owner_user_id`, falling back to management only when the project has
  no owner, so the message is never dropped.

## S17b - the salesperson finding out (2026-08-06 client review)

The client's review of S17 was one question with the answer inside it: *"when i request changes,
how can i see it from the system?"* They had gone looking and could not find it. It WAS recorded -
on the Signatures tab - and a tab the salesperson has no reason to open is not where "the customer
is waiting on you" belongs. Two other header items came in the same review.

**1. The change request is on the document, not behind a tab.**

- New `QuotationChangesRequestedPanel.tsx`, the same family as `QuotationApprovalPanel`: a strip
  directly under the page header that renders NOTHING in the ordinary case, and when it appears
  names the reason AND offers the next action as a click.
- It carries the customer's **verbatim words** (newlines kept, never truncated), who said them and
  when. "They asked for changes" is a notification; what a salesperson acts on is the sentence.
- The button is the **existing** document-level revise entry point (`startEditing()` ->
  `ReviseToEditDialog`), not a second one. The system still does not open a revision by itself.
  Labelled **"Revise this quotation"**, deliberately NOT "Revise to vN": the Scopes tab already
  carries a per-scope button by that exact name (`QuotationVersionEditor`), and two identically
  worded controls acting on different things - one scope vs the whole document - is worse than a
  vaguer label. The dialog that opens names the scopes and the version it will mint.
- With no frozen scope left (a revision is already open) the label reads "Edit this quotation",
  because that is what the click will actually do.

**Contract change.** The banner and the list read the decision off the DOCUMENT, so
`serialize_document` gains five keys and `ProjectQuotationDocumentResponse` declares them:
`accepted_at`, `changes_requested_at`, `changes_requested_note`, `changes_requested_by_name` and
`customer_decision` (`"accepted" | "changes_requested" | null`). Read off the **latest issue
only**, so revising and re-issuing clears it rather than nagging about a request already answered.
`customer_decision` is where the accepted-beats-requested rule is resolved **once**: the FE reads
it through `hasOpenChangeRequest` / `quotationStanding` and never re-derives it from the two
timestamps. That is the third manual builder for this entity (`serialize_document`,
`serialize_issue`, `serialize_sign_page`), so `test_the_customers_answer_reaches_the_wire...`
pins it at the HTTP seam, where this codebase has silently dropped a new field before.

**Yes, it belongs on the project's Quotations list too.** It rides the existing Status column
(Draft / Issued / Changes requested / Accepted) rather than a new one: the customer's answer IS
where the quotation stands, and a second, mostly-empty column would push the money off a 375px
screen. The column widened 120 -> 150 for the longest label. No column was added or removed, so
saved per-user column orders under `projects.projects.view::project-quotation-documents` stay
valid and the listing key does not need suffixing.

**2. Edit moved into the gear.** Client, with the header buttons circled: *"edit should be in gear
button"*. The rule was already in this screen's own docblock - ONE primary CTA, every other action
behind the gear - and Issue is the CTA. Only the **entry point** moved. The edit SESSION controls
(Cancel, Save) stay in the header where they are: once a session is open they are the active
controls for the screen. The `ReviseToEditDialog` path works unchanged from its new home.

**3. The downloads chip is bordered.** Client: *"the download should have border just like
complaint, we should use the same exact element"*. It always WAS the same component
(`EntityDownloadsButton`); the complaint detail header passes `h-8 border border-border` and the
quotation header passed nothing, so it rendered borderless beside two bordered buttons and read as
not clickable. The same three classes are now passed here.

**Decision: the border stays a call-site className, not a component default.** Of the three call
sites two want it (complaint detail header, quotation header) and one must NOT (the complaints
DataGrid "Print Count" cell, where a bordered chip would read as a nested button and add chrome to
every row). Two out of three is not "every call site", and flipping the default would mean editing
a complaint surface the client did not complain about in order to opt it back out. Revisit if a
third bordered header appears.
