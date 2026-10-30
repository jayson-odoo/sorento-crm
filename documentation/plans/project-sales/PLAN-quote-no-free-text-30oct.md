# PLAN: QUOTE-NO-FREE-TEXT (every quotation line is a catalogue product or set)

Status: Merge-ready pending the owner's hand test (PR #2020) - built red-first in three rounds, reviewer READY,
security S1 fixed and re-checked, browser pass 1280 + 375 PASS at 2a018ead9d. Owner answers: Q1 no legacy, Q2 refuse a
quoted product / set delete, Q3 drop "Not a catalogue product", Q4 New Product Application (no code), Q5 API + UI.
Track: full (M); no migration.

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
  product / set delete refused while quoted (Q2), in the service delete methods like the NPA guard
  (`product_service.py:1301`), so the direct route and the deferred `record_actions` delete share it; an
  execute-time refusal already toasts `error_text` (`lib/pending-entity-store.ts:275-276`). Out of scope: part
  products frozen inside a set line's `set_parts_snapshot` (JSON, no FK) are not checked.
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
3. Q2 guard on product / set delete: own test(red) + fix commits (AC-13..AC-15).
4. Seed script skips unknown codes.
5. reviewer + security-reviewer (write-path validation), browser pass 1280 + 375, hand test script.
