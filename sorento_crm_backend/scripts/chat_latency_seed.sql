-- Synthetic volume for the CHAT-LATENCY-SCOUT timing run. No real data.
-- 1 company (SRT, pre-seeded), 40 warehouses, 6 brands, 60 categories, 8000 products,
-- ~64k stock rows (8 warehouses per product), ~640k ledger rows, 40k open SO lines, 15k PO lines.
\set ON_ERROR_STOP on
BEGIN;
INSERT INTO units_of_measure (id, uom_code, uom_name)
SELECT gen_random_uuid(), 'PCS', 'Pieces' WHERE NOT EXISTS (SELECT 1 FROM units_of_measure);

INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, counts_as_available, company_id)
SELECT gen_random_uuid(), 'WH' || lpad(g::text, 3, '0'), 'Warehouse ' || g, g <= 36, true,
       '00000000-0000-0000-0000-000000000001'
FROM generate_series(1, 40) g;

INSERT INTO brands (id, brand_code, brand_name, is_active, company_id)
SELECT gen_random_uuid(), b, initcap(lower(b)), true, '00000000-0000-0000-0000-000000000001'
FROM unnest(ARRAY['SORENTO','MOCHA','AQUA','VELA','TERRA','NOVA']) b;

INSERT INTO product_categories (id, category_code, category_name, is_active, company_id)
SELECT gen_random_uuid(), 'CAT' || g,
       (ARRAY['Basin Mixer','Shower Set','Kitchen Sink','Water Closet','Basin','Bath Tub','Floor Trap','Towel Rack','Mirror','Cabinet'])[1 + g % 10] || ' ' || g,
       true, '00000000-0000-0000-0000-000000000001'
FROM generate_series(1, 60) g;

WITH cats AS (SELECT id, row_number() OVER () rn FROM product_categories),
     brs AS (SELECT id, row_number() OVER () rn FROM brands),
     uom AS (SELECT id FROM units_of_measure LIMIT 1)
INSERT INTO products (id, product_code, product_name, category_id, brand_id, base_uom_id, list_price,
                      reorder_level, is_active, is_searchable, is_discontinued, company_id)
SELECT gen_random_uuid(),
       (ARRAY['SRT','MWT','AQT','VLA'])[1 + g % 4] || (1000 + g)::text || (ARRAY['-CR','-BK','-SS','-WH',''])[1 + g % 5],
       (ARRAY['Basin Mixer','Shower Set','Kitchen Sink','Water Closet','Basin','Bath Tub','Floor Trap','Towel Rack','Mirror','Cabinet'])[1 + g % 10]
         || ' ' || (ARRAY['Chrome','Black','Stainless','White','Gold'])[1 + g % 5] || ' ' || g,
       (SELECT id FROM cats WHERE rn = 1 + g % 60),
       (SELECT id FROM brs WHERE rn = 1 + g % 6),
       (SELECT id FROM uom), 100 + g % 900, 10, true, true, g % 50 = 0,
       '00000000-0000-0000-0000-000000000001'
FROM generate_series(1, 8000) g;

WITH p AS (SELECT id, row_number() OVER (ORDER BY product_code) rn FROM products),
     w AS (SELECT id, row_number() OVER (ORDER BY warehouse_code) rn FROM warehouses)
INSERT INTO stock (id, product_id, warehouse_id, quantity_on_hand, quantity_reserved,
                   synced_to_excel, company_id, updated_at)
SELECT gen_random_uuid(), p.id, w.id, q, 0, false, '00000000-0000-0000-0000-000000000001', now() - (k || ' hours')::interval
FROM p CROSS JOIN generate_series(0, 7) k
JOIN w ON w.rn = 1 + (p.rn * 7 + k * 5) % 40
CROSS JOIN LATERAL (SELECT CASE WHEN (p.rn + k) % 6 = 0 THEN 0 ELSE ((p.rn * 13 + k * 31) % 400) END q) qq;

INSERT INTO stock_ledger (id, product_id, warehouse_id, transaction_type, quantity_change, previous_quantity,
                          new_quantity, created_at, company_id)
SELECT gen_random_uuid(), s.product_id, s.warehouse_id,
       CASE WHEN n = 10 AND s.quantity_on_hand = 0 AND random() < 0.3 THEN 'SYSTEM_ADJUSTMENT' ELSE 'IMPORT' END,
       1, 0, s.quantity_on_hand, now() - ((10 - n) || ' days')::interval, s.company_id
FROM stock s CROSS JOIN generate_series(1, 10) n;

INSERT INTO sales_orders (id, so_number, debtor_code, debtor_name, order_date, status, doc_type, company_id)
SELECT gen_random_uuid(), 'SO-' || g, 'D' || (g % 500), 'Dealer ' || (g % 500), current_date - (g % 120), 'open',
       'sales_order', '00000000-0000-0000-0000-000000000001'
FROM generate_series(1, 10000) g;

WITH so AS (SELECT id, row_number() OVER () rn FROM sales_orders),
     s AS (SELECT product_id, warehouse_id, row_number() OVER () rn FROM stock)
INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, qty_ordered, qty_delivered,
                               line_status, company_id)
SELECT gen_random_uuid(), so.id, s.product_id, s.warehouse_id, 5 + g % 20, g % 3, CASE WHEN g % 4 = 0 THEN 'closed' ELSE 'open' END,
       '00000000-0000-0000-0000-000000000001'
FROM generate_series(1, 40000) g
JOIN so ON so.rn = 1 + g % 10000
JOIN s ON s.rn = 1 + (g * 7) % 64000;

INSERT INTO purchase_orders (id, po_number, issue_date, expected_date, status, company_id)
SELECT gen_random_uuid(), 'PO-' || g, current_date - 30, current_date + (g % 60), 'open', '00000000-0000-0000-0000-000000000001'
FROM generate_series(1, 3000) g;

WITH po AS (SELECT id, row_number() OVER () rn FROM purchase_orders),
     p AS (SELECT id, row_number() OVER () rn FROM products)
INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, qty_ordered, qty_received, line_status,
                                  expected_date, company_id)
SELECT gen_random_uuid(), po.id, p.id, 50, 0, 'open', current_date + (g % 60), '00000000-0000-0000-0000-000000000001'
FROM generate_series(1, 15000) g
JOIN po ON po.rn = 1 + g % 3000
JOIN p ON p.rn = 1 + (g * 3) % 8000;
COMMIT;
ANALYZE;
