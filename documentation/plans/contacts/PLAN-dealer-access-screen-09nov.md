# PLAN: Dealer access screen (portal screen on the #2268 grant service)

Status: Plan. Mock v2 in progress; build waits for the owner's go on the mock. Track: full (security-sensitive
grant surface). Lane: DEALER-ACCESS-SCREEN. Follow-up of DEALER-ACCESS-PORTAL (#2268, merged 918f3d4d).

## Journey

A salesperson opens Dealer access from the sidebar, sees the people who hold access through THEIR OWN customers
(company as a filter), adds people to one or more of their own accounts (name, phone, Business Owner or Employee),
changes a level or unlinks a person, and the change applies at once through the same service the AI agent uses.

## Inputs

Card `CARD-dealer-access-portal-09nov.md` section 0 (rules V1-V9), UAC `dealer-access-portal-09nov-acceptance-criteria.md`,
mock v1 `dealer-access-portal-mock.html`. Owner rulings 9 Nov carried over unchanged (own customers only, levels are tags,
full template, add-only for phones under another dealer, one write path, owner controls rollout).

## Steps

1. Mock v2 (`dealer-access-screen-mock-v2.html`) in the app's design system with a component reuse map. Owner review.
2. Red-first fix: a re-sent new-request row after `all` must not ask "Say which company..." when the customer is
   already resolved.
3. Build (after the owner's go): tests first, coder, reviewer, security review, browser pass, hand-test script.
