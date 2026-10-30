# PLAN: QUOTE-NO-FREE-TEXT (every quotation line is a catalogue product or set)

Status: Plan - behaviour card filed to crew (`--ask`), waiting on the owner's answers to Q1-Q5. Track: full (M,
owner-visible rule on an existing screen); no migration unless Q5(b).

Source: owner 30 Oct ~21:15, "Free text product shouldn't be allowed, simple as that."
Behaviour card (rules, every write path with file:line, real data, Q1-Q5): `CARD-quote-no-free-text-30oct.md`.
Owner-run prod count: `SQL-quote-no-free-text-count-30oct.sql`.

## Journey (one line)

A salesperson adding a line to a project quotation can only pick a catalogue product or product set; anything
not in the catalogue goes through a New Product Application first.

## Architecture

- Layer: backend service. One check in `_write_line` (`services/project_quotation_service.py:851`), the funnel for
  add / edit / save-all / quotation form create + edit / amendment apply; it replaces the description-only guard
  at :978-983. The schema descriptions (`schemas/projects.py:1278-1290`) say product or set is required.
- Frontend mirrors it in `quotationLineDraft.ts` `lineErrors` (:99-103) so the editor shows the error before the
  server does; the server stays the authority.
- Classes fixed together: every write path (card table), plus product / set delete (Q2) and the seed script.
- Final shape depends on Q1-Q5; this section is filled in once the answers land.

## UAC

To be written from the answered card (`quote-no-free-text-acceptance-criteria.md`, same folder).

## Tickets (draft, ordered)

1. tester: red pytest per write path (add, edit-to-null, save-all, form create, form edit, amendment apply on a
   legacy line, revise of a legacy line) + red vitest for `lineErrors` and the grid's Add-a-line.
2. coder: service rule + schema text + FE draft/grid/flags; update the existing off-catalogue tests the card lists.
3. Q2 guard on product / set delete (if (a)).
4. Seed script skips unknown codes.
5. reviewer + security-reviewer (write-path validation), browser pass 1280 + 375, hand test script.
