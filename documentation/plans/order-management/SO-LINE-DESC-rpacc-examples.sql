-- SO-LINE-DESC: read-only lookup of real RPACC sales order lines for the behaviour card.
-- Crew / owner runs this on the shared dev DB (sorento_prod_1020); the lane worker cannot
-- (auto-mode classifier blocks row reads on prod restores). No writes.
-- Paste the output into the crew ask; do not paste customer names or phones into the PR.
BEGIN READ ONLY;

-- 1. How many SO lines per RP* product code, how many already carry a line remark.
SELECT p.product_code,
       count(*)              AS so_lines,
       count(l.line_remark)  AS with_line_remark,
       max(so.order_date)    AS latest_order
FROM sales_order_lines l
JOIN products p      ON p.id = l.product_id
JOIN sales_orders so ON so.id = l.sales_order_id
WHERE p.product_code ILIKE 'RP%'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 15;

-- 2. Five most recent RPACC lines (no customer columns selected).
SELECT so.so_number,
       l.line_no,
       p.product_code,
       left(p.product_name, 60)   AS product_name,
       l.qty_ordered,
       l.uom,
       left(l.line_remark, 120)   AS line_remark,
       l.purchasing_status,
       so.order_date
FROM sales_order_lines l
JOIN products p      ON p.id = l.product_id
JOIN sales_orders so ON so.id = l.sales_order_id
WHERE p.product_code = 'RPACC'
ORDER BY so.order_date DESC NULLS LAST, l.line_no
LIMIT 5;

-- 3. The owner's screenshot SO.
SELECT so.so_number, l.line_no, p.product_code, left(l.line_remark, 120) AS line_remark
FROM sales_order_lines l
JOIN products p      ON p.id = l.product_id
JOIN sales_orders so ON so.id = l.sales_order_id
WHERE so.so_number = 'SO428498'
ORDER BY l.line_no;

ROLLBACK;
