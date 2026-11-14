# Behaviour card: Order Change Notice slice 2, look and act like the purchase request (OCN-ORDER-CHANGE-NOTICE B)

Status: card for owner review (no code yet). Track: full (the CS change touches the shared SLA routing).
Base: slice 1 (PR #2384, head 7b7af55a). Evidence: `ASSESSMENT-ocn-slice2-align-14nov.md` (same folder, every
claim with file:line).

## Owner words (14 Nov, hand test PASS on slice 1, via crew)

1. CS in charge: derive it from the salesperson routing configured on the contact, no manual pick.
2. Remove the explanation text shown when choosing the change type (exchange etc.) and remove the disclaimer.
3. The form must REUSE the purchase request form components: same tab strip with aligned icons, same action
   buttons and wording (e.g. "Processed by CS", not "Mark done").
4. Assessment: how the notice aligns to purchase request / sponsorship form so all look the same and differ only
   in fields.

## Why it looks different today (one cause)

The purchase request and sponsorship form detail sits inside ONE shared tab shell set up on the page
(`FormDetailTabsWithRevisions` / `FormDetailWithSLATabs`, sla-management/_shared), with the record header
portalled above the tabs (`RecordCardSlot`). Complaint, stock inquiry and sample request use the same shell.
The notice built its own tabs inside its detail component (Details / Conversation / SLA / History, no icons).
The shell already accepts `order_change_notice` (type unions include it), so the notice can move into it.

## Rules after slice 2 (plain words)

**Layout (same as the purchase request, only the fields differ)**
- Tab strip from the shared shell: **Details**, **Comments (N)**, **SLA Tracking**, with the same icons and order.
  Revisions joins when the notice gets its revision history (already planned for a later slice).
- History moves from its own tab to an **Audit Trail** card at the bottom of Details, exactly like the purchase
  request, complaint and stock inquiry (they have no History tab). Same shared AuditTrail component.
- Header like the purchase request: "Order Change Notice - OCN26-0001" with the date as the subtitle, above the
  tabs; the status pill on the document card (not twice).
- Gear menu gains the purchase request's SLA items: Escalate, Extend, Reassign (shared components, not copies).
- Banners like the purchase request: rejection reason, void banner (shared `RejectionReasonBanner`, `VoidBanner`).
- Void uses the shared `VoidDialog`.
- Sign-off block: the purchase request's layout (Requested by / Approved or Rejected by + date / comments);
  "Requested by" then lives in the sign-off like the purchase request, not twice.
- A voided notice's comment thread becomes read-only (as on the purchase request).

**Buttons and words (stored statuses and SLA events already match; only words change, no backend rename)**

| Step | Today | After |
|---|---|---|
| Admin passes it on | Send for approval | **Change to pending approval** (Q4) |
| Admin returns it | Send back | **Reject** -> "Confirm reject" (Q4) |
| Approver | Reject / Approve | **Approve** (green, thumbs up) then **Reject**, same icons as the purchase request |
| Customer Service | Mark done | **Processed by CS** (green, badge icon); dialog title "Mark as processed by CS?", confirm "Processed by CS" |
| Status word | Done | **Processed by CS** (list, pill, History, project Related tab, notifications, assistant) |
| Raiser | Submit / Save as draft | unchanged (the notice is raised in the CRM; the purchase request's raiser submits from the portal) |

The Customer Service step's comment box stays ("Customer Service comment (optional)"): the notice stores it;
the purchase request sends a message to a contact instead, which a notice does not have.

**C.S. in charge (owner item 1)**
- No picker. The CS person is chosen the way the purchase request chooses it: from the **Requested by** contact's
  routing rules (Contacts > contact > Routing), evaluated when the Customer Service step starts (after approval).
  No rule match -> the Customer Service team's round robin, as today.
- The notice shows "C.S. in charge" read-only: "-" until approval, then the person the CS step was given to.
- This also fixes a slice-1 defect: today the picked "C.S. Incharge" and the person the CS SLA task goes to are
  unrelated (the CS task is always round robin).
- Own-records: a CS person still sees the notices they are C.S. in charge of.

**Change type box (owner item 2)**
- Removed from the form and the detail: the guide text under the type buttons ("Swap a product for another one...").
- The "Risk: High" line in the same box: see Q1. The list keeps its Risk column and Risk filter.

**What does not change**
- Fields, numbering, approval chain, SLA stages and hours, permissions, per-contact visibility (round 20),
  Requested by, the amendment link, the project Related tab, the list's own columns (it already follows the
  fixed-width rule).
- Nothing touches the sales order, PO or AutoCount.

## Worked examples (fake data)

1. Sales Person A raises OCN26-0041 (Exchange). Requested by = Sales Person A's contact, whose routing says
   "customer debtor type Project -> CS Person A". Admin A: **Change to pending approval**. Manager A: **Approve**.
   The CS step starts and goes to CS Person A; the notice shows C.S. in charge: CS Person A. CS Person A:
   **Processed by CS**, comment "Collection booked". Status pill and list read "Processed by CS".
2. Same, but the contact has no routing rule that matches: the CS step goes round robin to the next Customer
   Service member; C.S. in charge shows that person.
3. Admin A clicks **Reject** on a submitted notice with "Agree penalty charge first": status Rejected, the
   rejection banner shows the reason, the raiser amends and resubmits (Appealed), as on the purchase request.
4. A voided notice: the void banner shows who and why; the Comments tab is read-only.

## Edge cases

- A notice approved before slice 2 keeps its existing CS assignee; only CS steps that start after slice 2 use the
  routing.
- Requested by blank (a user with no linked contact): no routing contact -> round robin.
- A routing rule set to "No CS" on the contact: see Q2.
- A rule whose condition names a purchase-request-only field (project value, sales type, product lines) cannot
  match a notice and falls through to the next rule or round robin.
- Old History rows that say "Done" read "Processed by CS" afterwards (words are read at display time; no data
  change).

## Size

Tab shell M, header S, buttons / dialogs / words M, SLA gear items S, CS routing M (shared SLA service + a purchase
request regression test), guide text S. Overall M-L, one PR. No migration, no route rename, no permission change.
No mock: the result is the purchase request layout with the notice's fields (a mock would only copy the PR screen).

## Questions (at most 5, each with a recommendation)

**Q1. Which text is "the disclaimer"?** The word "disclaimer" is not in the screen. Candidates: (a) the
"Risk: High" line in the change-type box; (b) the Customer Service comment's empty hint "Nothing from Customer
Service so far."; (c) the user-guide sentence "The risk is shown for information...". Recommendation: (a): remove
the whole box (risk line + guide text) from the form and detail, keep the Risk column and filter on the list.

**Q2. A "No CS" routing rule on the contact.** On a purchase request it ends the form at approval (no CS step).
(a) Honour it on the notice too (no CS step; approved is the end); (b) ignore it and round robin. Recommendation:
(a), same rule as the purchase request.

**Q3. When does the notice show its C.S. in charge?** (a) After approval, when the CS step starts ("-" before);
(b) a preview from the rules on the draft (may differ from the final person when someone covers or is not
eligible). Recommendation: (a), it is always the real person.

**Q4. Rename the two admin buttons as well?** The owner quoted only the CS step. (a) Full parity: "Send for
approval" -> "Change to pending approval", "Send back" -> "Reject"; (b) only the CS step. Recommendation: (a),
the owner asked for the same buttons and wording.

**Q5. Which routing rules does the notice read?** (a) The contact's existing **Purchase Request** rules (no admin
work, works on day one); (b) a new **Order Change Notice** rule set on the contact Routing page (admins must add
rules per contact before any notice is routed). Recommendation: (a); build (b) only if the owner wants a different
CS person for notices than for purchase requests.
