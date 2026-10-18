# PLAN: Flexible multi-level Group by on the stock status table (STOCK-GROUPBY)

Status: Plan. Behaviour card being drafted (Phase 1, before any code). Lane STOCK-GROUPBY, size M, standard track
(new behaviour + UI on an existing screen; no migration expected). Base: #1752's branch
`claude/stock-status-embed-sxgykp` at 67e87c24d; rebase onto main once #1752 merges.

## Owner request (18 Oct, verbatim)

"In 1752 how do i view the total by different dimensions like customer project?" then, after crew said it is not
possible: "by location is still needed, i think we can try to support flexible group by and multiple layers of group by
la, Odoo style".

## Target (to be confirmed by the behaviour card)

A "Group by" menu on the stock status table. The user picks one or more dimensions in order (for example
Location > Customer > Project); each level is a collapsible group header showing its row count and summed quantity
columns; levels can be removed and reordered. Location stays available and is the default first level, so today's view
is unchanged by default. One reusable capability, applied first to the four stock status screens (Fulfilment Planning
cell dialog Stock tab, OI line expand, project quotation stock popover, stand-alone Stock status page).

## 1. Discovery

(filled in from the code map; every claim cites file:line)

## 2. Behaviour card

(posted as one crew-ask; answers recorded here)

## 3. Mock

`documentation/mockups/STOCK-GROUPBY/index.html` (masked dev-data case).

## 4. Slices

(after the owner OKs the mock)
