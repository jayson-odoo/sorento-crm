# PLAN: Order inquiry emails routed by sales order class (DEALER-PLANNING PR 3)

**Status:** Plan. Track M (no migration expected, no auth change). Branch `claude/dealer-oi-route-nepe9z` (crew lane DEALER-OI-ROUTE).

Parent plan: `PLAN-dealer-planning-1nov.md` (on `crew/dealer-planning-retail`, #2068), section "PR 3" and card Q4 (a).

## Journey

Dealer CS confirms a retail order's lines on Fulfilment Planning. The order inquiry handover email goes To dealer purchasing, Cc project purchasing and the person who raised it. A project order's email goes exactly where it goes today. An undo follows the same rule. The owner edits To and Cc in System Management > Automation and creates the retail row himself; nothing is seeded.

## Build (detail follows once the code read is done)

1. The handover and undo triggers expose the sales order class (`retail`, `project`; `other` reads as retail) as a condition fact.
2. Explicit To and Cc in the recipient picker.
3. Tests first, reviewer, security-reviewer, guide page.
