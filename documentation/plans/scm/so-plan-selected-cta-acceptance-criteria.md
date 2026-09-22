# UAC: Plan selected is the sales-orders list's one CTA

Plan: `PLAN-so-plan-selected-cta.md`

## Frontend (vitest)

- AC-1. There is no `Start` button on the sales-orders list. With nothing ticked, the toolbar's
  primary button reads `Plan selected (0)` and is disabled, and focusing its wrapper shows a
  tooltip naming the reason ("Tick the sales orders to plan first.").
- AC-2. With N orders ticked (1 to 50), `Plan selected (N)` is enabled; clicking it navigates to
  `/project-sales/fulfilment-planning?orders=<the N document numbers>`.
- AC-3. With more than 50 orders ticked, `Plan selected (N)` is disabled and its tooltip names
  the board's own bound ("up to 50").
- AC-4. The `Actions` dropdown lists, in order: Upload sales orders, Add sales order, Reset
  planning (N), Refresh. Upload sales orders opens the same, unforked `OutstandingUploadDialog`
  scoped to `kind="sales-orders"` that Reorder Planning uses.
- AC-5. On the sales-agent record's pinned grid (`salesAgentId` set), `Plan selected` still
  shows as the toolbar's CTA; `Upload sales orders` and `Add sales order` are both absent from
  `Actions`. Usable and non-clipped at 375px.

## Definition of done

Touched vitest green (`SalesOrdersGrid.test.tsx`, `SalesOrdersList.planning.test.tsx`,
`SalesOrdersList.upload.test.tsx`), reviewer clean, one PR against main, owner go before merge.
