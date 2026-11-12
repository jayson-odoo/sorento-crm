-- CHATBOT-CODE-MATCH AC-18: active products in a category whose class has a size key, with no
-- value stored under any of that class's size keys. READ ONLY: one SELECT, it edits nothing.
--
-- A class's size keys follow the chatbot's own rule (`chatbot/head/bare_size.size_key_rows`):
-- active numeric registry keys with a unit that the class scopes (`applies_when.class`), plus
-- the keys flagged `matches_bare_size`. The chatbot never assumes a size, so each row here is a
-- code whose did-you-mean shows "<label>: not recorded" until a value is stored.
--
-- Run: psql "$DATABASE_URL" -f scripts/chatbot_products_without_size.sql

WITH size_keys AS (
    SELECT r.spec_key, r.applies_when, r.matches_bare_size
    FROM product_spec_registry r
    WHERE r.is_active IS TRUE
      AND lower(r.data_type) = 'numeric'
      AND coalesce(r.unit, '') <> ''
),
class_keys AS (
    SELECT c.id AS category_id, k.spec_key
    FROM product_categories c
    JOIN size_keys k
      ON k.matches_bare_size IS TRUE
      OR (
          c.class_label IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM jsonb_array_elements_text(coalesce(k.applies_when -> 'class', '[]'::jsonb)) AS scoped(value)
              WHERE lower(scoped.value) = lower(c.class_label)
          )
      )
)
SELECT p.product_code, c.category_name
FROM products p
JOIN product_categories c ON c.id = p.category_id
WHERE p.is_active IS TRUE
  AND EXISTS (SELECT 1 FROM class_keys ck WHERE ck.category_id = c.id)
  AND NOT EXISTS (
      SELECT 1
      FROM class_keys ck
      JOIN product_specifications s ON s.product_id = p.id
      WHERE ck.category_id = c.id
        AND jsonb_typeof(s."values" -> ck.spec_key -> 'value') = 'number'
  )
ORDER BY c.category_name, p.product_code;
