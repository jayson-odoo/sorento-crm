-- Cost price Lane A, S1 pre-flight queries (PLAN-cost-price-supplier-26sep.md section 3.8).
--
-- Run on the prod copy, read-only: psql "$DATABASE_URL" -f preflight-s1.sql
-- Every statement is a SELECT. Nothing here writes.
-- Queries 3 and 4 need the codes from the owner's TAIYANG file: paste them into the
-- file_codes VALUES list (one row per 型号 cell, verbatim). The two codes quoted in #1288
-- are there already so the queries run as they stand.

\echo '== 1. Product-supplier links per currency'
SELECT coalesce(currency, '(null)') AS currency,
       count(*)                     AS links,
       count(unit_cost)             AS links_with_unit_cost
FROM product_suppliers
GROUP BY 1
ORDER BY 2 DESC;

\echo '== 2. TAIYANG links: count, currencies, priced links, most common lead time'
WITH taiyang AS (
    SELECT id, supplier_code, supplier_name, company_id
    FROM suppliers
    WHERE supplier_name ILIKE '%TAIYANG%' OR supplier_code ILIKE '%TAIYANG%'
)
SELECT t.supplier_code,
       t.supplier_name,
       t.company_id,
       count(ps.id)                                             AS links,
       string_agg(DISTINCT coalesce(ps.currency, '(null)'), ', ') AS currencies,
       count(ps.unit_cost)                                      AS links_with_unit_cost,
       mode() WITHIN GROUP (ORDER BY ps.standard_lead_time_days) AS most_common_lead_time_days
FROM taiyang t
LEFT JOIN product_suppliers ps ON ps.supplier_id = t.id
GROUP BY t.supplier_code, t.supplier_name, t.company_id;

\echo '== 3. The file''s codes: exact product match, recorded alias, or neither'
-- The ladder rungs 2 to 4 (separator, token set, trap size) are Python; this query answers
-- the exact and alias rungs and lists what is left for them. The lane's reader runs the
-- full engine with remember=False on the file itself.
WITH file_codes(raw) AS (
    VALUES ('SRTWT1900-BL-DIY'), ('CB2500SS-BL（彩盒）')
),
cleaned AS (
    -- NFKC folds the full-width brackets; one trailing bracket group is the note.
    SELECT raw,
           btrim(regexp_replace(normalize(raw, NFKC), '\s*\([^()]*\)\s*$', '')) AS code
    FROM file_codes
),
taiyang AS (
    SELECT id, company_id FROM suppliers
    WHERE supplier_name ILIKE '%TAIYANG%' OR supplier_code ILIKE '%TAIYANG%'
)
SELECT c.raw,
       c.code,
       (SELECT string_agg(p.product_code, ', ')
          FROM products p
         WHERE upper(p.product_code) = upper(c.code)
           AND p.company_id IN (SELECT company_id FROM taiyang))      AS exact_product,
       (SELECT string_agg(coalesce(p.product_code, '(dismissed)'), ', ')
          FROM scm.supplier_product_code_alias a
          LEFT JOIN products p ON p.id = a.product_id
         WHERE a.supplier_id IN (SELECT id FROM taiyang)
           AND upper(btrim(a.supplier_code)) = upper(c.code))         AS alias_product,
       (SELECT string_agg(p.product_code, ', ')
          FROM products p
         WHERE upper(regexp_replace(p.product_code, '[-\s]+', '', 'g'))
               = upper(regexp_replace(c.code, '[-\s]+', '', 'g'))
           AND p.company_id IN (SELECT company_id FROM taiyang))      AS separator_match
FROM cleaned c
ORDER BY c.code;

\echo '== 3b. Does SRTWT1900-BL-DIY exist, or only SRTWT1900-DIY?'
SELECT product_code, description, company_id
FROM products
WHERE upper(product_code) IN ('SRTWT1900-BL-DIY', 'SRTWT1900-DIY')
ORDER BY product_code;

\echo '== 4. Cleaned codes that appear more than once in the file (the duplicate-code check)'
WITH file_codes(raw) AS (
    VALUES ('SRTWT1900-BL-DIY'), ('CB2500SS-BL（彩盒）')
)
SELECT upper(btrim(regexp_replace(normalize(raw, NFKC), '\s*\([^()]*\)\s*$', ''))) AS code,
       count(*) AS times
FROM file_codes
GROUP BY 1
HAVING count(*) > 1
ORDER BY 2 DESC, 1;

\echo '== 5. Roles and the product-supplier write slugs they hold today (for the AC-S2-14 sweep)'
-- The CRUD routes need only a login today, so every role that uses the Product-Suppliers
-- screen can write. The lane grants add/edit/delete to every role holding .view; this lists
-- who holds what now, so the sweep can be checked before and after.
SELECT r.slug AS role,
       bool_or(p.slug = 'procurement.product_suppliers.view')   AS has_view,
       bool_or(p.slug = 'procurement.product_suppliers.add')    AS has_add,
       bool_or(p.slug = 'procurement.product_suppliers.edit')   AS has_edit,
       bool_or(p.slug = 'procurement.product_suppliers.delete') AS has_delete,
       bool_or(p.slug = 'scm.proforma_invoice.upload')          AS purchasing_role
FROM user_roles r
LEFT JOIN user_role_permissions rp ON rp.role_id = r.id
LEFT JOIN user_permissions p ON p.id = rp.permission_id
GROUP BY r.slug
ORDER BY purchasing_role DESC, r.slug;

\echo '== 5b. Who changed a product_suppliers price recently (audit rows, if any)'
SELECT count(*) AS audit_rows_for_product_suppliers
FROM audit_logs
WHERE entity_type = 'product_suppliers';
