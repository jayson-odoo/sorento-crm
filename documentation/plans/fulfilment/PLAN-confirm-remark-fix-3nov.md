# PLAN: CONFIRM-REMARK-FIX

Status: in progress (Plan). Track: small fix track (no migration, no auth/RBAC change). Follow-up
to merged #2091 (`PLAN-confirm-preview-stale-2nov.md`, UAC
`confirm-preview-stale-2nov-acceptance-criteria.md`).

## Items

- F1 (prod bug): the SO Remark typed in the Confirm popup is blank in the queued purchasing email.
- F2: a planner's own line remark shows in the popup but the email / attachment print the generated
  words. Popup = email = attachment.
- F3: two dry runs per change (save, then board re-read). Make it one.
- Speed: at most one Confirm-guide dry run in flight, dry-run only the order on screen, 5 s lock
  timeout on the preview (like Simulate).
