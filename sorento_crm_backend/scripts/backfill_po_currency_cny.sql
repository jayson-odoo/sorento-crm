-- Purchase orders and their lines that state NO currency are CNY (captain, 28 Aug 2026:
-- "change all to CNY"). Rows that state a currency (USD / MYR / EUR from the history book)
-- are facts from the file and are left alone. Idempotent.
BEGIN;
UPDATE purchase_orders SET currency = 'CNY' WHERE currency IS NULL OR btrim(currency) = '';
UPDATE purchase_order_lines SET currency = 'CNY' WHERE currency IS NULL OR btrim(currency) = '';
COMMIT;
