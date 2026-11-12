# PLAN: remove the "Below default price" line pill and filter option (QUOTE-BELOW-DEFAULT-OFF)

Status: in progress (small fix track: FE only, no migration, no auth change)

## Why

Owner, 12 Nov 2026: "we ady got the minimum selling price indicator at the price column, i don't
think this is needed". The pill came from PROJECT-QUOTE-LINE-TOOLS
(`PLAN-project-quote-line-tools-11nov.md`, AC-5/6/8/9/10).

## Scope

- Remove the grey "Below default price" pill from the Product cell
  (`QuotationLineFlags.tsx` `LineFlags`). Non-standard stays.
- Remove the "Below default price" option from the lines Flags filter
  (`QuotationVersionEditor.tsx` `LINE_FLAG_FILTERS`). Non-standard and Below minimum price stay.
- The approval banner's "N lines are priced below the default price" clause keeps its words; its
  count stops being a link (the filter it opened is gone). Other clauses stay links.
- Below minimum price in the Rate cell: unchanged.
- Not changed: pricing, approval rules, `is_discounted`, banner wording, backend.
- No portal copy exists (grep: only `project-sales/[projectId]` renders `LineFlags`).

## Tests (red first)

- Editor: a discounted saved line shows no "Below default price"; the Flags filter offers only
  Non-standard and Below minimum price; a below-floor line still shows "Below minimum price".
- Banner: the default-price clause renders as text, not a button.

## Standing rules that apply

Filters (multi-select, unchanged), Wording (no extra text), Lists one-line rows.
