# PLAN: LEAD-GOVERNS-REGISTER (29 Oct 2026)

Status: Review - slices 1 (BE + RBAC) and 2 (screens) built and green (PR #1966, red/kill proofs posted); main merged
25cafb9b0d; fix round in progress for the security review (own = owner only, own-only duplicate hints, E7-E9) and the
reviewer (draft-path lead customer fill, Edit customer wipe, leadMissing guard, wizard assignee). Browser Part A PASS at
1280/375 on d0c20bb090; C/D blocked on copy data. Track: M + RBAC. No migration.

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
