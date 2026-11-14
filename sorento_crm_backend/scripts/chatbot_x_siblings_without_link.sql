-- CHATBOT-CODE-MATCH: read-only list of the products the chatbot reaches ONLY through the "X" family rule
-- (`app/services/product_code_family._family_rows`). Edits nothing.
--
-- An X sibling is an active product whose family_code is letters + X + digits (e.g. CWCX1009) while the same
-- family without that X exists (CWC1009). The chatbot already links an X sibling to its base from catalogue data
-- when a registered product set holds both, or when its family_code was set by hand to the base family. The rows
-- below have neither link; linking them (set Family code on the product, or register a set holding both) is the
-- data that lets the X rule be removed (crew ruling 12 Nov: keep the X rule until then).
--
-- Run: psql "$DATABASE_URL" -f scripts/chatbot_x_siblings_without_link.sql
-- (the regex also catches a family whose letters end in X when the X-less family exists; check by eye)
BEGIN READ ONLY;

WITH fam AS (
    SELECT id, product_code, upper(family_code) AS fc, family_code_manual AS m, is_active
    FROM products
    WHERE family_code IS NOT NULL
),
xs AS (
    SELECT x.id, x.product_code, x.fc AS xfc, x.m, x.is_active,
           regexp_replace(x.fc, '^([A-Z]*)X([0-9].*)$', '\1\2') AS base
    FROM fam x
    WHERE x.fc ~ '^[A-Z]*X[0-9]'
      AND EXISTS (
          SELECT 1 FROM fam b
          WHERE b.fc = regexp_replace(x.fc, '^([A-Z]*)X([0-9].*)$', '\1\2') AND b.fc <> x.fc
      )
),
setboth AS (
    SELECT DISTINCT s.id
    FROM xs s
    JOIN product_set_members mx ON mx.product_id = s.id
    JOIN product_set_members mb ON mb.product_set_id = mx.product_set_id
    JOIN fam b ON b.id = mb.product_id AND b.fc = s.base
)
SELECT xs.product_code, xs.xfc AS x_family, xs.base AS base_family
FROM xs
WHERE xs.is_active
  AND NOT (xs.m AND xs.xfc = xs.base)
  AND xs.id NOT IN (SELECT id FROM setboth)
ORDER BY xs.base, xs.product_code;

ROLLBACK;
