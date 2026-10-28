# PLAN: Audit Trail shows every resubmission (AUDIT-TRAIL-RESUBMITTED)

Status: Plan (small fix track: no migration, no auth/RBAC change)

Owner 28 Oct: the audit trail must read rejected -> resubmitted -> rejected -> resubmitted for a
complaint rejected twice and resubmitted by the customer each time, for old history and for new
portal resubmits (#1925), with the #1924 field diff under each.

Findings and design: filled in after the code read (see PR crew-note).
