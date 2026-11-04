-- OI-ONE-DELIVERY-DATE: read-only example pulls for the card (run on the dev prod copy).
-- Nothing here writes. Every query compares an OI row's own date with its SO line's date.

-- 1. The owner's example: OI-2609-0588, every row, its date vs its SO line's date.
SELECT oi.inquiry_no, r.item_code, r.qty, r.verb, r.state,
       r.delivery_date            AS oi_row_date,
       r.previous_delivery_date   AS oi_row_was,
       m.line_no, m.delivery_date AS mirror_line_date,
       c.required_date            AS core_line_date,
       so.so_number
FROM projects.order_inquiry_rows r
JOIN projects.order_inquiries oi ON oi.id = r.order_inquiry_id
LEFT JOIN projects.sales_order_lines m ON m.id = r.so_line_id
LEFT JOIN public.sales_order_lines c ON c.id = m.core_sales_order_line_id
LEFT JOIN public.sales_orders so ON so.id = c.sales_order_id
WHERE oi.inquiry_no = 'OI-2609-0588'
ORDER BY r.item_code, r.delivery_date;

-- 2. How big is the gap: live rows by (date agrees / differs / no SO line / SO line has no date).
SELECT CASE
         WHEN r.so_line_id IS NULL THEN 'no_so_line'
         WHEN c.required_date IS NULL AND m.delivery_date IS NULL THEN 'so_line_no_date'
         WHEN r.delivery_date IS NULL THEN 'oi_row_no_date'
         WHEN r.delivery_date = COALESCE(c.required_date, m.delivery_date) THEN 'same'
         ELSE 'differs'
       END AS bucket,
       r.state, count(*)
FROM projects.order_inquiry_rows r
LEFT JOIN projects.sales_order_lines m ON m.id = r.so_line_id
LEFT JOIN public.sales_order_lines c ON c.id = m.core_sales_order_line_id
WHERE r.state <> 'cancelled'
GROUP BY 1, 2 ORDER BY 1, 2;

-- 3. Mirror vs core drift (should be zero since PLAN-esb-change-row-refresh S2).
SELECT count(*) AS mirror_core_drift
FROM projects.sales_order_lines m
JOIN public.sales_order_lines c ON c.id = m.core_sales_order_line_id
WHERE m.delivery_date IS DISTINCT FROM c.required_date;

-- 4. Five real 'differs' rows, largest gap first (card examples).
SELECT oi.inquiry_no, so.so_number, m.line_no, r.item_code, r.qty,
       r.delivery_date AS oi_row_date, c.required_date AS so_line_date,
       (c.required_date - r.delivery_date) AS gap_days, r.state, r.verb
FROM projects.order_inquiry_rows r
JOIN projects.order_inquiries oi ON oi.id = r.order_inquiry_id
JOIN projects.sales_order_lines m ON m.id = r.so_line_id
JOIN public.sales_order_lines c ON c.id = m.core_sales_order_line_id
JOIN public.sales_orders so ON so.id = c.sales_order_id
WHERE r.state <> 'cancelled'
  AND r.delivery_date IS DISTINCT FROM c.required_date
ORDER BY abs(c.required_date - r.delivery_date) DESC NULLS LAST
LIMIT 5;

-- 5. Two or more live rows on one SO line with different dates (split / legacy duplicates).
SELECT so.so_number, m.line_no, r.item_code, count(*) AS rows,
       array_agg(r.delivery_date ORDER BY r.delivery_date) AS oi_dates,
       c.required_date AS so_line_date,
       bool_or(EXISTS (SELECT 1 FROM projects.so_line_splits s WHERE s.so_line_id = m.id)) AS has_split
FROM projects.order_inquiry_rows r
JOIN projects.sales_order_lines m ON m.id = r.so_line_id
JOIN public.sales_order_lines c ON c.id = m.core_sales_order_line_id
JOIN public.sales_orders so ON so.id = c.sales_order_id
WHERE r.state <> 'cancelled'
GROUP BY so.so_number, m.line_no, r.item_code, c.required_date
HAVING count(DISTINCT r.delivery_date) > 1
ORDER BY rows DESC LIMIT 10;

-- 6. Rows with no SO line at all (stock / manual / dealer rows): how many, by verb.
SELECT r.verb, r.state, count(*)
FROM projects.order_inquiry_rows r
WHERE r.so_line_id IS NULL AND r.state <> 'cancelled'
GROUP BY 1, 2 ORDER BY 3 DESC;
