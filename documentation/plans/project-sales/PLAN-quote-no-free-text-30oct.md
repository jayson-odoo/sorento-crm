# PLAN: QUOTE-NO-FREE-TEXT (every quotation line is a catalogue product or set)

Status: Build - card answered 30 Oct ~22:05 (Q1 no legacy handling, Q3 yes, Q5 (a) API + UI); Q2 / Q4 pending the
owner, each a separate small commit after his answer. Track: full (M, owner-visible rule on an existing screen); no
migration.

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
- Classes fixed together: every write path (card table) through the one check; the seed script skips unknown codes;
  product / set delete (Q2) waits for the owner.
- No legacy handling (Q1): prod is not live, so no stored product-less line exists that matters. Revise and
  amendment Apply need no code: they go through `_write_line` or copy only lines that already passed it.
- FE: `lineErrors` refuses a line with no product and no set; "Not a catalogue product" flag removed
  (`QuotationLineFlags.tsx:86`), "Non-standard" kept.

## UAC

`quote-no-free-text-acceptance-criteria.md` (same folder), AC-1..AC-12 built now, AC-Q2 / AC-Q4 after the owner.

## Tickets (draft, ordered)

1. tester: red pytest per write path (add, edit-to-null, save-all, form create, form edit) + red vitest for
   `lineErrors` and the flags; rewrite the existing tests that assert an off-catalogue line saves.
2. coder: service rule + schema text + FE draft/grid/flags; update the existing off-catalogue tests the card lists.
3. Q2 guard on product / set delete (after the owner's answer, own red + fix commits).
4. Seed script skips unknown codes.
5. reviewer + security-reviewer (write-path validation), browser pass 1280 + 375, hand test script.
