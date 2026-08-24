# 7.5-Technical Team - Complaint lifecycle & what to do at each stage

This is the map of how a complaint moves from raised to finished, and **what you should do next at every status**. Use it when you open a complaint and aren't sure what the next step is. For the detailed how-to of each action, the step guides are linked inline.

## Where

Open [**Complaint Management → Complaints**](/complaint-management/complaints) → click a complaint. The status pill near the top shows the current stage; the top action bar shows the buttons available for that stage.

## The lifecycle (process flow)

```
New / Submitted / Updated   →  Responded  ┌─→ Approved ─→ Processed by CS
   (a complaint comes in)       (team        │              └─→ Closed
                                 replied)    └─→ Rejected ─→ (back to open, re-worked)
```

Plain English:

1. A complaint arrives and sits as **New** (or **Submitted** / **Updated** if it came through the portal or was edited).
2. The technical team sends a reply → status becomes **Responded**.
3. From **Responded**, the complaint is decided: **Approved** (we accept the outcome) or **Rejected** (sent back for more work).
4. An **Approved** complaint is finished by customer service: **Processed by CS** (handled) or **Closed** (can't be resolved).
5. **Processed by CS** and **Closed** are the end states.

## Status labels

| Status | What it means |
|--------|----------------|
| **New** | Just raised, no response yet. |
| **Submitted** | Came in via the customer portal. |
| **Updated** | Details were edited after submission. |
| **Responded** | The technical team has sent a reply; awaiting a decision. |
| **Approved** | Outcome accepted; waiting on customer service to finish. |
| **Rejected** | Not accepted; back to open for re-work. |
| **Processed by CS** | Customer service handled it. End state. |
| **Closed** | Couldn't be resolved; closed out. End state. |

## What should I do now - by status

**New / Submitted / Updated**
The complaint needs a technical response. Write it with **Edit technical team response**, then send it with **[Update & Reply](#guide_target=complaint-management.complaints.tech-team.update-reply)** - this notifies the customer and moves the status to **Responded**. Full steps: [Respond to a complaint](respond-to-complaint.md). (Needs a linked Respond.io thread.)

**Responded**
Decide the outcome. Either:
- **[Approve](#guide_target=complaint-management.complaints.tech-team.approve)** - the response is accepted; the customer is notified and the complaint moves to **Approved**.
- **[Reject](#guide_target=complaint-management.complaints.tech-team.reject)** - a **Rejection reason** is required; the customer is notified with the reason and the complaint goes back to open for re-work.

Full steps: [Approve or reject a complaint](approve-or-reject-complaint.md). You'll only see these two buttons when the status is **Responded** and you hold `complaint_management.complaints.approve` / `.reject`.

**Approved**
Customer service finishes it. Either:
- **Processed by CS** - the complaint was handled. Sets status to **Processed by CS** and closes the customer-service SLA stage. Optional message to the contact. (Needs `complaint_management.complaints.resolve`.)
- **Mark as closed** - use when it can't be resolved. Sets status to **Closed** and closes the SLA stage. Optional message to the contact. (Needs `complaint_management.complaints.close`.)

Both actions cannot be undone and notify the customer. This is also the stage to record the outcome - see [Set root cause and resolution](set-root-cause-and-resolution.md).

**Rejected**
The complaint is back open. Review the rejection reason, do the extra work needed, then re-respond (**Edit technical team response** → **[Update & Reply](#guide_target=complaint-management.complaints.tech-team.update-reply)**) to put it back to **Responded** for another decision. A portal customer may also resubmit.

**Processed by CS / Closed**
End states - no further action. Editing a response here still messages the customer but does **not** change the status. You can still **Download PDF** for records.

## Notes

* The **Approve** / **Reject** buttons only exist at **Responded**; **Processed by CS** / **Mark as closed** only at **Approved**. If a button is missing, check the status pill and your permissions.
* Every decision sends a Respond.io message to the customer, so the thread is always in sync with the status.
* Moving a **Rejected** complaint back to **Approved** clears the stored rejection reason (the change stays in the audit history).
