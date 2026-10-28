# PLAN: STOCKDEBT-NO-PLAN-REACH - a board plan never widens what a Stock Debt line may draw

Status: Plan (findings in progress). Track: full (size M). Base: main f64f4db1 (carries #1919 + #1935).

## Journey

Owner, 28 Oct ~09:00 MYT, on CB4702 Dec 26 (Project book view): "I don't want to take from BRW even if the
plan says 'Reserve from BRW'" and "the one that it can draw should be faithful to what's mentioned in the
Supply tab, be it PO, SPO or on hand". A Stock Debt line draws only from what the view shows as its supply.
A board plan (Reserve / Borrow from another location, group or BRW) never widens that reach.

Owner condition (kept from #1919): deciding and confirming on the Fulfilment Planning board work exactly as
today. Kept: OI links to PO/SPO keep holding; supply (incoming) Borrows unchanged.

## Count SQL (dev clone, read-only)

Upper bound on Stock Debt view lines whose reach changes. A line flips only if its plan
or hand link was what covered it.

```sql
-- A. open lines with a live confirmed board plan at a bin OUTSIDE their own group (or a site pool)
SELECT count(DISTINCT sol.id) AS plan_reach_lines, sum(a.qty) AS plan_reach_qty
FROM projects.so_line_allocations a
JOIN projects.sales_order_lines psl ON psl.id = a.so_line_id
JOIN public.sales_order_lines sol ON sol.id = psl.core_sales_order_line_id
JOIN public.sales_orders so ON so.id = sol.sales_order_id AND so.status = 'open'
JOIN public.warehouses wa ON wa.id = a.warehouse_id
JOIN public.warehouses wl ON wl.id = sol.warehouse_id
LEFT JOIN projects.so_supply_decisions d ON d.id = a.decision_id
WHERE a.confirmed_at IS NOT NULL AND a.source_type <> 'order'
  AND (d.id IS NULL OR d.state = 'active')
  AND (substring(wa.warehouse_code from '-([^-]+)$') IS DISTINCT FROM
       substring(wl.warehouse_code from '-([^-]+)$')
       OR EXISTS (SELECT 1 FROM public.warehouses c WHERE c.pool_warehouse_id = wa.id));

-- B. hand-made (auto = false) OI links on a PO line or an SPO allocation, live rows
SELECT (l.spo_allocation_id IS NOT NULL) AS on_spo, count(*) AS links,
       count(DISTINCT r.so_line_id) AS lines
FROM projects.order_inquiry_links l
JOIN projects.order_inquiry_rows r ON r.id = l.row_id
WHERE NOT l.auto AND r.state <> 'cancelled'
  AND (l.po_line_id IS NOT NULL OR l.spo_allocation_id IS NOT NULL)
GROUP BY 1;
```
