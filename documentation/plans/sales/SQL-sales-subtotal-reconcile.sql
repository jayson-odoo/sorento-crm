-- SALES-SUBTOTAL-LINES reconciliation (read-only). Plan:
-- documentation/plans/sales/PLAN-sales-subtotal-lines-07nov.md
--
-- Per company-month of 2026: the header sales sum (signed local_net_total) against the line
-- sum (signed net_amount x currency_rate) BEFORE the fix (every line) and AFTER it (subtotal
-- lines skipped). The subtotal verdict is computed here by the same walk as
-- app/services/finance/billing_subtotal_lines.py, so the query runs on a database that does not
-- have the is_subtotal column yet. SELECT only; safe on the dev copy.
--
-- Query 1: the company-month table. Query 2: the documents still off after the fix, with the
-- likely reason (no lines; footer charge or rounding = header-only money, REF gotcha 5).
WITH RECURSIVE ordered AS (
    SELECT l.id, l.document_id, l.net_amount,
           (l.net_amount IS NOT NULL
            AND NULLIF(BTRIM(l.item_code), '') IS NULL AND l.product_id IS NULL
            AND NULLIF(BTRIM(l.uom), '') IS NULL AND l.quantity IS NULL AND l.unit_price IS NULL
            AND NULLIF(BTRIM(l.from_doc_type), '') IS NULL
            AND NULLIF(BTRIM(l.from_doc_no), '') IS NULL
            AND NULLIF(BTRIM(l.from_line_ref), '') IS NULL
            AND l.sales_order_line_id IS NULL) AS shape,
           ROW_NUMBER() OVER (
               PARTITION BY l.document_id
               ORDER BY l.line_no NULLS LAST, l.source_ref COLLATE "C"
           ) AS rn
    FROM finance.billing_document_lines l
    WHERE l.document_id IN (SELECT d.id FROM finance.billing_documents d
                        WHERE d.doc_date >= DATE '2026-01-01' AND d.doc_date < DATE '2027-01-01')
),
walk AS (
    SELECT o.id, o.document_id, o.rn, FALSE AS is_subtotal,
           COALESCE(o.net_amount, 0) AS since_start,
           COALESCE(o.net_amount, 0) AS since_previous,
           1 AS counted
    FROM ordered o
    WHERE o.rn = 1
    UNION ALL
    SELECT o.id, o.document_id, o.rn, v.is_subtotal,
           CASE WHEN v.is_subtotal THEN w.since_start
                ELSE w.since_start + COALESCE(o.net_amount, 0) END,
           CASE WHEN v.is_subtotal THEN 0
                ELSE w.since_previous + COALESCE(o.net_amount, 0) END,
           w.counted + CASE WHEN v.is_subtotal THEN 0 ELSE 1 END
    FROM walk w
    JOIN ordered o ON o.document_id = w.document_id AND o.rn = w.rn + 1
    CROSS JOIN LATERAL (
        SELECT (w.counted > 0 AND o.shape
                AND o.net_amount IN (w.since_start, w.since_previous)) AS is_subtotal
    ) v
)
,
verdict AS (SELECT id, is_subtotal FROM walk),
docs AS (
    SELECT d.id, c.code AS company, to_char(d.doc_date, 'YYYY-MM') AS month, d.doc_no,
           d.document_type,
           CASE WHEN d.document_type = 'credit_note' THEN -1 ELSE 1 END AS sign,
           d.local_net_total, d.currency_rate
    FROM finance.billing_documents d
    JOIN companies c ON c.id = d.company_id
    WHERE d.status = 'posted'
      AND d.document_type IN ('invoice', 'cash_sale', 'credit_note', 'debit_note')
      AND d.doc_date >= DATE '2026-01-01' AND d.doc_date < DATE '2027-01-01'
),
per_doc AS (
    SELECT d.id, d.company, d.month, d.doc_no, d.document_type,
           d.sign * d.local_net_total AS header,
           COALESCE(SUM(d.sign * l.net_amount * d.currency_rate), 0) AS lines_before,
           COALESCE(SUM(d.sign * l.net_amount * d.currency_rate)
                    FILTER (WHERE NOT COALESCE(v.is_subtotal, FALSE)), 0) AS lines_after,
           COUNT(l.id) AS line_count,
           COUNT(l.id) FILTER (WHERE v.is_subtotal) AS subtotal_lines
    FROM docs d
    LEFT JOIN finance.billing_document_lines l ON l.document_id = d.id
    LEFT JOIN verdict v ON v.id = l.id
    GROUP BY d.id, d.company, d.month, d.doc_no, d.document_type, d.sign, d.local_net_total
)
-- Query 1
SELECT company, month,
       ROUND(SUM(header), 2) AS header_sum,
       ROUND(SUM(lines_before), 2) AS line_sum_before,
       ROUND(SUM(lines_before) - SUM(header), 2) AS overstatement_before,
       ROUND(SUM(lines_after), 2) AS line_sum_after,
       ROUND(SUM(lines_after) - SUM(header), 2) AS diff_after,
       SUM(subtotal_lines) AS subtotal_lines,
       COUNT(*) FILTER (WHERE subtotal_lines > 0) AS docs_with_subtotal
FROM per_doc
GROUP BY company, month
ORDER BY company, month;

-- Query 2: run it with the same WITH block as Query 1 (copy everything above `-- Query 1`),
-- replacing the final SELECT with:
--
-- SELECT company, month, doc_no, document_type, header, ROUND(lines_after, 2) AS lines_after,
--        ROUND(lines_after - header, 2) AS diff, line_count, subtotal_lines,
--        CASE WHEN line_count = 0 THEN 'no lines (header-only document)'
--             WHEN ABS(lines_after - header) <= 0.05 THEN 'rounding'
--             ELSE 'header-only money (footer charge) or a line the rule does not see' END
--          AS reason
-- FROM per_doc
-- WHERE ROUND(lines_after, 2) <> ROUND(header, 2)
-- ORDER BY company, month, ABS(lines_after - header) DESC;
