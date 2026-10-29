# PLAN: LEAD-GOVERNS-REGISTER (29 Oct 2026)

Status: Build - card answered 29 Oct (Q1 a, Q2 a, Q3 a, Q4 b, Q5 a); slice 1 (BE + RBAC) red tests in progress;
screens wait for the mock v2 (owner notes: no debtor code; Firm question filed). Track: M + RBAC (Q4 b adds own-lead
access for the submit-only salesperson, so security-reviewer runs). No migration. Branch `crew/lead-governs-register`.

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

## UAC

`lead-governs-register-acceptance-criteria.md` (LGR-A..H).

## Slices

1. **BE + RBAC** (UAC B, E, F, G, H): lead create requires an existing customer (no `new_customer`); register
   requires a lead and takes the customer from it (fill-only write to an empty lead customer); PUT re-derives on a lead
   change; Qualify copies the customer; own leads (`owner_user_id` or `created_by`) for `projects.projects.view_own`
   readers on GET /leads and /leads/{id}; `projects.registrations.submit` may create own leads; submit-only
   `crm_register` / `crm_submit` take a required lead on submit. Keys off slugs PORTAL-P4 (#1953) grants; no new slug.
2. **Screens** (UAC A, C, D) after mock v2 approval: wizard 4 steps with Customer first (server search, name only);
   "Buyer" -> "Customer"; register form bottom section Lead / Customer (read-only) / Salesperson; submit-only form shows
   Lead; wizard without Assign for submit-only.
3. Phase 3: reviewer + security-reviewer + agent-browser 1280/375 on the crew test copy.

## Coordination

PORTAL-P4 (#1953) defines and grants `projects.registrations.submit` + `projects.projects.view_own` to `salesperson`;
crew-note posted on #1953. Merge main after #1953 lands.
