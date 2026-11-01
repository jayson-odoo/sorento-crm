# UAC: Dealer sales orders plannable on Fulfilment Planning

Plan: `PLAN-dealer-planning-1nov.md`.

## PR 1

- **AC-1** A sales order line at an active, flagged-off, dealer-segment bin (BRW) is plannable: not unplannable on the board, no `unplannable_reason` from the supply service.
- **AC-2** A bin with no segment set behaves as dealer (`pool_predicate.is_site_pool`).
- **AC-3** A line at an active, flagged-off, project-segment bin still reads "Outside fulfilment planning" and confirm still refuses it.
- **AC-4** An inactive bin keeps the verdict it has today.
- **AC-5** A consignment line at its own flagged-off bin behaves exactly as today: never the verdict, proposal is a borrow at its own bin, no Buy, no purchasing row.
- **AC-6** BRW stays flagged off and out of planning reads: no project line's proposal, netting or Stock Debt figure changes because of this PR.
- **AC-7** A BRW line goes through decide, confirm and OI preview without a refusal.
- **AC-7a** A line at its own pool does not net its own demand against that pool, and every other line's demand there stays netted. 10 on hand and 10 ordered is Reserve 5 + Buy 5 at the 50% default, never Buy 10. The answer is the same on the line's sheet, on the board alone, and on the board with other lines of the product.
- **AC-7b** What goes back is what the pool's book counted: a closed, non-transferable or covered line, or a line at a retired pool, adds nothing. Another line never reads this line's add-back.
- **AC-8** A line still unplannable shows its real reason: flagged-off bin reads "Outside fulfilment planning", no location reads "Needs a location". Same in the Verdict pill, the Suggested column, its sort text and the row's disabled-checkbox reason.

## Retail orders, only if crew decides to widen (not in PR 1)

- **AC-9** A retail order with a line at a dealer-segment bin is listed, opens on the board, adopts, confirms and raises its OI.
- **AC-10** A retail order with lines only at project-segment bins (MOCHA-WH) stays out, as today.
- **AC-11** A confirmed retail line is not counted twice as purchasing demand.

## PR 2

To be written from the answered behaviour card.
