# 6.6-Project Sales Admin — Purchase request & sponsorship form lifecycle & what to do at each stage

Purchase requests and sponsorship forms share the same approval lifecycle. This is the map of how one moves from draft to finished, and **what you should do next at every status**. Open it when you're on a request/form and aren't sure what's next. Step guides are linked inline.

## Where

Open [**Procurement Management → Purchase Requests**](/procurement-management/purchase-requests) (or [**Sponsorship Forms**](/procurement-management/sponsorship-forms)) → click a record. The status pill shows the current stage; the action bar shows the buttons for that stage.

## The lifecycle (process flow)

```
Draft ──Change to pending approval──▶ Pending approval ┌─Approve─▶ Approved ──Processed by CS──▶ Processed by CS
   │                                                   └─Reject (reason)─▶ Rejected              └─Close─▶ Closed
   └─Reject (reason)──────────────────────────────────────────────────▶ Rejected
```

Plain English:

1. A request/form starts as **Draft**.
2. It moves to **Pending approval**.
3. The approver decides **in the system** — clicking **Approve** or **Reject** (with a reason) in the top action bar.
4. An **Approved** request is finished by customer service: **Processed by CS**, or **Closed**.

## Status labels

| Status | What it means |
|--------|----------------|
| **Draft** | Created, not yet sent for approval. |
| **Pending approval** | Awaiting the approver's decision — they **Approve** or **Reject** it in the system. |
| **Approved** | Approver accepted it; awaiting CS to finish. |
| **Rejected** | Turned down, with a reason. |
| **Processed by CS** | Customer service handled it. End state. |
| **Closed** | Closed out. End state. |

## What should I do now — by status

**Draft**
Move it forward with **[Change to pending approval](#guide_target=procurement.approvals.change-to-pending-approval-button)** — this sets the status to **Pending approval** so the approver can act on it. You can also **Reject** it here with a reason if it shouldn't proceed. Full steps: [Review a purchase request](review-purchase-request.md) / [Review a sponsorship form](review-sponsorship-form.md).

**Pending approval**
The approver decides **in the system**: click **[Approve](#guide_target=procurement.purchase-requests.approve-button)** to accept it, or **[Reject](#guide_target=procurement.purchase-requests.reject-button)** (a reason is required) to turn it down — the buttons are in the top action bar of the record. The status then becomes **Approved** or **Rejected**.

> The older emailed approval-link flow ("Copy approval link") is being phased out — approve and reject directly in the system.

**Approved**
Customer service finishes it: **Processed by CS** when handled, or **Close** if it's being closed out. Both notify the contact.

**Rejected**
Review the rejection reason (shown on the record) and the approver's comments. The request is turned down; raise a new one if the need stands.

**Processed by CS / Closed**
End states — no further action.

## Notes

* Approve and reject happen **in the system** (the buttons on the record). The emailed approval-link flow is being retired.
* The same component drives both purchase requests and sponsorship forms; the flow and buttons are identical — only the menu entry differs.
* Buttons are gated by status and permission — if one is missing, check the status pill and your role.
* The approver's decision and any rejection reason are recorded in the audit history.
