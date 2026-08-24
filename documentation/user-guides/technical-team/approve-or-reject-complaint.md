# 7.3-Technical Team - Approve or reject a complaint

After the technical team has sent a response (status = **Responded**), the complaint needs to be closed out - either **Approved** (we accept the outcome) or **Rejected** (we don't accept the outcome and the complaint goes back to open). Both actions notify the customer via Respond.io.

## Prerequisites

* The complaint is in status **Responded**. If it's still **Open**, finish [Respond to a complaint](respond-to-complaint.md) first.
* You have the permission for the action you want to take:
  * `complaint_management.complaints.approve` - to approve.
  * `complaint_management.complaints.reject` - to reject.

The **Approve** and **Reject** buttons are only rendered when both conditions are true. If you don't see them, double-check the status and your role permissions.

## Where

Open [**Complaint Management → Complaints**](/complaint-management/complaints) → click the responded complaint → the top action bar shows the buttons.

## Approve

Click **[Approve](#guide_target=complaint-management.complaints.tech-team.approve)**.

* A confirmation dialog asks you to acknowledge that the customer will be notified.
* On confirm: status → **Approved**, a closing message is sent to the customer's Respond.io thread, and the complaint is closed.

Use this when:

* The customer has accepted the technical team's response, or
* The complaint is resolved and you want to record it as closed.

## Reject

Click **[Reject](#guide_target=complaint-management.complaints.tech-team.reject)**.

* A dialog asks for a **Rejection reason** (required).
* On confirm: status → **Rejected**, the rejection reason is posted to the customer's Respond.io thread, and the complaint reverts to an open state so the salesperson can pick it up again.

Use this when:

* The technical team's response is insufficient and the case needs more work, or
* The complaint should not have been escalated to the technical team and should go back to the salesperson.

## What changes after either action

* The complaint row in the list updates with the new status badge.
* The audit trail records who approved / rejected and when.
* The customer's Respond.io thread receives a templated message.

## See also

* [Respond to a complaint](respond-to-complaint.md)
* [Set Root Cause & Resolution and notify salesperson](set-root-cause-and-resolution.md)
