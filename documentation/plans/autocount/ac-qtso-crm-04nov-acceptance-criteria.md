# UAC: AC-QTSO-CRM, quotation + sales order create / update / cancel in AutoCount from Project sales

Plan: `PLAN-ac-qtso-crm-04nov.md`. Mock: `ac-qtso-crm-04nov-mockup.html`. Rulings R1-R6 in the plan.

## Switch (R1)
- U1. `system_settings.project_autocount_write_enabled`, migration seeds it OFF; admin Settings shows "AutoCount quotations and sales orders from Project sales".
- U2. Off: no Create / Update / Cancel in AutoCount renders on any screen; every write route answers 403 "AutoCount quotations and sales orders from Project sales are switched off in Settings." and the Shared Service client is never called.
- U3. On: the actions render, gated by permission and by the SS capability feed.
- U4. The switch is in the settings GET dict, the update model and `/settings/app-config` (all three).

## Sales order create (R2)
- U5. Worksheet shows Create in AutoCount only when: switch on, order published or amended, `can_export` true, `autocount_doc_no` empty. Download CSV stays.
- U6. Body: header debtorCode = customer `customer_code`, docDate today, currencyCode MYR, currencyRate 1, yourPONo = customer PO no, ref = project title, displayTerm = Net N days, salesAgent, remark1 = provisional ref; lines itemCode, description, uom, qty, unitPrice, location, deliveryDate.
- U7. Missing debtor code or any line location: refused in the CRM before any SS call, naming the customer / line.
- U8. done: `autocount_doc_no` = answer docNo; result lists the read-back lines. A second press replays (same Idempotency-Key, same body).
- U9. refused / 403 WRITE_DISABLED, WRITE_NOT_ALLOWED / 202 pending / 502: plain wording per the plan; nothing written to the CRM except on done.

## Sales order update (R3)
- U10. Update in AutoCount only on a published amendment of an order already in AutoCount.
- U11. Qty change and date moves go as PATCH line edits; added lines as POST lines; remove line / balance cancel / repoint / model change show "Waiting for AutoCount" while the feed says delete_line / cancel_doc off.
- U12. PATCH always carries docDate and expectedLastModified; DOC_STALE shows "Changed in AutoCount since dd/mm/yyyy. Nothing was changed; check it in AutoCount, then press Update again." and stores the LastModified read back from AutoCount, so the next press sends it (B10).
- U13. QTY_BELOW_TRANSFERRED shows as AutoCount's refusal; nothing changes in the CRM.

## Cancel (R4)
- U14. Decide > Cancel in AutoCount (SO list ticks, quotation page) reads the capability feed; today greyed "Waiting for AutoCount". No hard-coded off.

## Quotation (R5, R6)
- U15. Create in AutoCount only on the project's `kind = quotation` document whose latest issued revision is accepted; greyed "The customer has not accepted this quotation yet" before; proposals never.
- U16. Rate-only lines are not sent; product sets go as components (part qty x set qty, driver at the set rate, others zero); the result note names each skipped line and each exploded set.
- U17. A later accepted revision of a quotation already in AutoCount shows Update in AutoCount.

## Security
- U18. New permission slug `projects.autocount.write` (granted to superadmin and admin by migration); without it no action renders and the routes answer 403.
- U19. companyCode and every docKey are resolved on the server from the CRM record, never taken from the request.
- U20. Writes reach only the book SS allows (db3 guard, WRITE_COMPANY_NOT_TEST shown as switched off).
