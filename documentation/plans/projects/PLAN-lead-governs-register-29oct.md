# PLAN: LEAD-GOVERNS-REGISTER (29 Oct 2026)

Status: Plan - behaviour card filed, waiting on owner answers. Track: M (behaviour on two existing
screens: Create lead wizard + Register a project form). Branch `crew/lead-governs-register`.

## Owner ask (29 Oct ~09:3x, verbatim)

"back to project registration ya, i think our lead creation first step is need to link to the customer leh, not
sure why the buyer dropdown is empty, it is supposed to be customer isit? i think the lead and customer field should
be tgt at the bottom and when we choose the lead the customer should be prefilled with readonly, so we select lead
only, i want to select lead, i want to govern the project registration process with lead creation"

## Journey

1. Salesperson hears of a job through a dealer. Create lead: step 1 picks the CUSTOMER (the dealer, an existing
   AutoCount debtor), then the development, who told us, assign and confirm.
2. Registering the project: the user picks the LEAD (bottom section, beside Salesperson). The Customer is filled
   from the lead and read-only. No lead yet: the Lead picker's "Create lead" row opens the wizard, and the new lead
   (with its customer) is picked on return.

## Card

`documentation/plans/projects/CARD-lead-governs-register-29oct.md` (filed as `crew report --ask`).

## Slices

To be written once the card is answered (UAC first: `lead-governs-register-acceptance-criteria.md`).
