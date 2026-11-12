-- CHATBOT-CODE-MATCH AC-18: active products whose class has a size key, with no value stored under
-- any of that class's size keys. READ ONLY: one SELECT, it edits nothing.
--
-- The class and its size keys are read the way the chatbot reads them
-- (`chatbot/lanes/business/code_sizes._product_facts`, `chatbot/head/bare_size.size_key_applies`):
-- the class is the product's stored spec class, else its category's class; a key scoped to
-- classes (`applies_when.class`) is that class's only, an unscoped key flagged
-- `matches_bare_size` is every class's. Keys are active numeric registry keys with a unit. The
-- chatbot never assumes a size, so each row here is a code its did-you-mean shows as
-- "<label>: not recorded" until a value is stored.
--
-- Run: psql "$DATABASE_URL" -f scripts/chatbot_products_without_size.sql

WITH size_keys AS (
    SELECT r.spec_key,
           coalesce(r.applies_when -> 'class', '[]'::jsonb) AS scope,
           r.matches_bare_size
    FROM product_spec_registry r
    WHERE r.is_active IS TRUE
      AND lower(r.data_type) = 'numeric'
      AND coalesce(r.unit, '') <> ''
),
product_class AS (
    SELECT p.id AS product_id,
           p.product_code,
           c.category_name,
           s."values" AS spec_values,
           lower(coalesce(s."values" -> 'class' ->> 'value', c.class_label)) AS class
    FROM products p
    LEFT JOIN product_categories c ON c.id = p.category_id
    LEFT JOIN product_specifications s ON s.product_id = p.id
    WHERE p.is_active IS TRUE
),
applying AS (
    SELECT pc.product_id, k.spec_key
    FROM product_class pc
    JOIN size_keys k
      ON (jsonb_array_length(k.scope) = 0 AND k.matches_bare_size IS TRUE)
      OR EXISTS (
          SELECT 1 FROM jsonb_array_elements_text(k.scope) AS scoped(value)
          WHERE lower(scoped.value) = pc.class
      )
)
SELECT pc.product_code, pc.category_name
FROM product_class pc
WHERE EXISTS (SELECT 1 FROM applying a WHERE a.product_id = pc.product_id)
  AND NOT EXISTS (
      SELECT 1 FROM applying a
      WHERE a.product_id = pc.product_id
        AND jsonb_typeof(pc.spec_values -> a.spec_key -> 'value') = 'number'
  )
ORDER BY pc.category_name, pc.product_code;
