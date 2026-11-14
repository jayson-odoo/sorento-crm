# PLAN OI-PO-LINK B: Link PO popup reads only the CRM copies; every ticked line is a row

Status: building (small fix track: no migration, no auth/RBAC change, no new ingest surface).
Follow-up to #2350 (merged as is, owner 14 Nov ~15:52). UAC: `oi-po-link-b-14nov-acceptance-criteria.md`.

## Why (owner, 14 Nov ~15:50, db3 hand test round 2)
"I tried to select multiple line and click the Link PO, I noticed only 1 line show up and I notice abit of
lag when the popup opens, is it because we got do some autocount pulling when the popup opens? cause I
thought we can just pull from the purchase order and sales order that we have as a copy in our system".

## Cause (at 5e78e211e)
- Lag: `PoLinkService.options()` (`app/services/scm/po_link_service.py:356`) calls `capabilities()`, which
  calls the Shared Service `GET /api/v1/autocount/write-capabilities` (`:275`) on every popup open. Both
  screens (Order Inquiry, Stock Debt Decide) use it.
- One row: `scope_for_oi_rows` (`:208`) leaves out a ticked line whose sales order line is not in AutoCount
  and names it only under the grid; the popup (`PoLinkDialog.tsx` ManageDialog, `:809-826`) draws rows only
  for the lines it gets.

## Change
1. `options()` sends nothing to the Shared Service. `capabilities` stays in the answer (same shape) with
   every action enabled; what AutoCount cannot do is answered at Save with its plain reason (existing
   wording: VENDOR_UNSUPPORTED "AutoCount cannot do this yet. Nothing was changed.", WRITE_DISABLED /
   WRITE_NOT_ALLOWED "Changes to AutoCount are switched off here.") and Try again. Supersedes the 4 Nov
   capability-feed ruling (PLAN-ac-link-crm-ui-04nov.md rule 2) for this popup; newest owner ruling wins.
2. Every ticked line is a row. A line not in AutoCount is a row of its own: sales order, location, delivery
   date, outstanding from the CRM copy where it has one, "Not in AutoCount yet" in the PO cell, no tick, no
   picker, no qty. OI lines on the same sales order line stay one row (the link is per sales order line).

## Not in this lane
Q1-Q3 of the behaviour card (PO line picker popup with sort/filter, SO-location placement by SS, pool
ordering): a later lane, mock first.
