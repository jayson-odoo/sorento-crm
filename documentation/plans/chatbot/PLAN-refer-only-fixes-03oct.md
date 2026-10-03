# PLAN: refer-only reply fixes (REFER-ONLY-FIXES)

Status: Build. Track: small fix (expected diff under 300 lines, no migration, no auth/RBAC change, no new ingest surface).

Owner ask (3 Oct 2026, console, parser v43):

1. A contact who may NOT escalate gets "Please refer to your salesman." and must never see the
   CS escalation picker or any staff list after it. Example: an order ask for SRTWC8605-FT with
   no match printed "But no order matched these. Please refer to your salesman." followed by a
   numbered staff list, and the scope header "Customer: all customers / Product / Dates: all dates".
2. Dealer availability: "stock srtwc286-sh" -> "How many units?" -> "5" printed
   "SRTWC286-SH x 5: ❌ No incoming. Please refer to your salesman." With no stock AND no
   incoming the line must say "❌ No stock and no incoming."; with some (insufficient) stock
   and no incoming the existing wording stays.

Findings and the outcome -> wording table: filled in as the lane builds (see PR body).
