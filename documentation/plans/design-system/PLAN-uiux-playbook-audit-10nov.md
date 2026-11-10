# PLAN: UI/UX playbook gap audit (UIUX-PLAYBOOK-AUDIT)

Status: audit written, draft PR open, waiting on the owner's answers to Q1-Q5 (small fix track: docs only, no code, no migration).

## Journey

Owner + management meeting 9 Nov 2026 aligned on applying the Foundryx UI/UX playbook
(`foundryxkay/playbook-UIUX`, skill `foundryx-playbook-uiux`) to the CRM. Before any rule is applied,
the playbook's "First time on a system" steps 2-3 need a gap audit of the existing frontend.

## Scope

- Read-only. No app code, no mock, no root `playbook-uiux.md` (that file means "playbook applied"
  and waits for the owner's answers).
- Step 2: one-line verdict (existing system) with evidence.
- Step 3: list the CRM's UI patterns; sort each playbook rule as conforms / missing / CRM does it
  better / conflicts with an owner rule.
- Checklist pass on 6 real screens with `file:line`: Order Inquiry list (DataGrid), Order Inquiry
  detail header, quotation editor (money form), one confirm dialog, price tag request, 375 px layout.

## Output

`documentation/uiux/playbook-uiux-audit.md`:
1. Summary table: rule -> status -> evidence.
2. Top 10 quick wins that fit owner rules.
3. Agreed-difference candidates (each conflict, recommendation keep-ours / adopt).
4. Rules the CRM does better (proposals back to Kay, report only).

## Architecture

Docs only. Layer: none (no FE/BE change). Evidence gathered by read-only Explore subagents over
`sorento_crm_frontend/` and the repo's own design contract (`PRINCIPLES.md`,
`documentation/reference/DESIGN-LANGUAGE.md`, `ADR-PRODUCT-STANDARDS.md`).

## Steps

1. Read playbook SKILL.md, knowledge/decisions.md, skim reference/clarity-draft.html. Done.
2. Gather CRM evidence per playbook section (subagents, max 15-line conclusions each). Done.
3. Write the audit doc, draft PR with only the doc (+ this plan). Done.
4. One `crew report --ask` with at most 5 agreed-difference questions, each with a recommendation.
5. Final report + `crew report --done`.

## DoD (small fix track, docs only)

- No red test / kill test: no code changes, nothing to test (stated in PR body).
- No browser pass: no screen changed.
- guide: n/a (no user-visible change).
