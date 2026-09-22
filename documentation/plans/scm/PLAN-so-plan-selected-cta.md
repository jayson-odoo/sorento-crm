# PLAN: Plan selected is the sales-orders list's one CTA, not a Start menu

Status: Small fix track - implemented
Domain: scm / sales orders list
Branch: `fix/so-plan-selected-cta` (worktree `sorento_crm-so-plan-cta`)
UAC: `so-plan-selected-cta-acceptance-criteria.md`
Supersedes: A1 and A3 of the archived `documentation/plans/_archive/scm/scm-planning-inline-decisions-acceptance-criteria.md`, which put Plan selected behind a primary **Start** dropdown alongside Upload sales orders.

## Owner ruling (22 Sep 2026, screenshot of the Sales orders list)

"I need this button to be Plan selected, we don't need Start anymore, Plan selected should be
the CTA, then Upload sales orders can go in the Actions dropdown."

## The change

1. The toolbar's primary button is now `Plan selected (N)` itself, not a `Start` dropdown that
   opened to reveal it. `buildPlanActions` (`../lib/planActions.ts`) still owns the label,
   disabled state and reason - the toolbar renders its single result as a plain `Button`, or
   nothing at all when the caller lacks `PLAN_PERMISSION`.
2. The disabled reason (nothing ticked, or over the board's 50-order bound) travels in a Radix
   `Tooltip` on a focusable wrapper `<span data-testid="plan-selected-trigger">`, the same
   pattern `BoardLineDecisionPanel` uses for its own disabled Save/Reject - a `title` on a
   disabled `Button` never reaches a real browser's hover.
3. "Upload sales orders" moves into the `Actions` dropdown as its first item, still hidden while
   the grid is pinned to one sales agent's record. Actions now reads, in order: Upload sales
   orders, Add sales order, Reset planning (N), Refresh.
4. The `DropdownMenu`/"Start" trigger and its menu items are removed outright; nothing else in
   the toolbar (bulk strip, Export, Clear) changes.

No backend change, no migration.

## Tests

- `SalesOrdersGrid.test.tsx` - Actions membership and order (now 4 items: Upload, Add, Reset,
  Refresh), Plan selected disabled at 0 and above 50 with the tooltip reason, no `Start` button
  left, `pinnedToAgent` hides Upload from Actions but keeps Plan selected as the CTA.
- `SalesOrdersList.planning.test.tsx` - every "open Start, click the menu item" case rewritten
  onto `getByRole('button', { name: /^Plan selected \(N\)$/ })`; disabled-reason assertions
  focus `plan-selected-trigger` and read the Radix tooltip; a new case pins that no `Start`
  button remains.
- `SalesOrdersList.upload.test.tsx` - both cases that opened `Start` now open `Actions` and
  click the `Upload sales orders` menu item.
