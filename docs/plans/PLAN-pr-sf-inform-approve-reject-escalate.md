# PLAN — PR/SF in-form Approve/Reject + Escalate SLA buttons

Status: **Done** (BE + FE shipped; pytest green; buttons verified in browser on a pending-approval PR)

## Goal
On the Purchase Request / Sponsorship Form detail header, add:
1. **Escalate SLA** button — same as the SLA Tracking tab's escalate, but reachable
   directly on the form (parity with how staff escalate elsewhere).
2. **Approve / Reject** buttons (when the request is pending approval) — the approver
   can decide in-system instead of only via the emailed approval link. MUST behave
   identically to the public approval form (same state transition, notifications,
   SLA event, automation).

## Key facts
- Public approval = `POST /api/v1/public/approval/submit?token=…` → `ProcurementService.submit_approval(token, action, approved_by, comments)`. It validates a one-time `ApprovalToken`, sets `header.status`/`approval_status = action`, notifies requester+contact (Respond), emits form-SLA event `approved`/`approval_rejected`, dispatches approval automation.
- PR + SF share `purchase_requests` router/service; `request_type` discriminates.
- Active form-SLA tracker for an entity: `GET /api/v1/sla-management/conversation-sla-tracking/by-source?source_entity_type=&source_entity_id=` (FE `getFormSLATrackers`). Escalate: `POST …/{tracking_id}/escalate` (FE `escalateFormTracking`).
- PR detail header lives in `PurchaseRequestDetail.tsx`. It already has Send-for-approval, a *reject-submitted* (pre-approval) dialog, Edit, Delete, DetailActionsMenu.

## BE
1. Extract `_apply_approval_decision(header, action, approved_by, comments)` from `submit_approval` (everything after token validation: status set, notifications, SLA emit, automation). `submit_approval` validates+consumes the token, then calls it — behavior unchanged.
2. New authenticated endpoint `POST /api/v1/procurement/purchase-requests/{request_id}/approval-decision` body `{action: approved|rejected, comments?}`. Permission-gated (same perm as send-for-approval). Loads header, guards `status == pending_approval`/`submitted` per current rules, `approved_by` = current user's name, calls `_apply_approval_decision`. No token. Works for PR + SF.
3. pytest: approve transitions status→approved + emits SLA `approved`; reject requires reason + emits `approval_rejected`; auth denial.

## FE
4. `purchaseRequestService`: `submitApprovalDecision(requestId, action, comments?)`.
5. `PurchaseRequestDetail` header:
   - **Escalate** button → load active tracker via `getFormSLATrackers`, open reason dialog → `escalateFormTracking`. Hidden when no active/unresolved tracker.
   - **Approve** / **Reject** buttons shown when pending approval → `submitApprovalDecision`. Reject requires a reason (AlertDialog), matching the public form.
6. vitest: buttons render only in the right state; reject requires reason.

## Verify
Playwright: PR detail (pending approval) → Approve → status flips, SLA resolves; Reject w/ reason; Escalate bumps tier. Confirm SF detail mirrors.
