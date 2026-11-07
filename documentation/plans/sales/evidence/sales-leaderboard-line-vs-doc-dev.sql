-- SALES-LEADERBOARD: why line sum != doc sum for ERIC NG (Oct 2026) and JENNIFER (Sep 2026).
-- Read-only, dev copy only (BEGIN READ ONLY ... ROLLBACK). No customer names or phones selected.
-- Doc sum  = signed local_net_total            (achievement_service.py:657-658, invoiced_sales.py:91-93)
-- Line sum = signed sum(net_amount * currency_rate) (billing_document_lines.py:66, invoiced_sales.py:96-99)
BEGIN READ ONLY;

-- Q1. Every posted document of the two agents/months whose lines do not add up to its header.
WITH docs AS (
  SELECT d.*, a.sales_agent AS agent
  FROM finance.billing_documents d
  JOIN companies c ON c.id = d.company_id
  LEFT JOIN customers cu ON cu.id = d.customer_id
  LEFT JOIN sales_agents a ON a.id = CASE WHEN c.sales_agent_source = 'customer'
                                          THEN cu.sales_agent_id ELSE d.sales_agent_id END
  WHERE d.status = 'posted'
    AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
    AND ((a.sales_agent = 'ERIC NG'  AND d.doc_date >= '2026-10-01' AND d.doc_date < '2026-11-01')
      OR (a.sales_agent = 'JENNIFER' AND d.doc_date >= '2026-09-01' AND d.doc_date < '2026-10-01'))
)
SELECT d.agent, d.doc_no, d.document_type, d.doc_date, d.currency_code, d.currency_rate,
       d.net_total, d.local_net_total, d.tax_total, d.total,
       count(l.id)                                   AS lines,
       sum(l.net_amount)                             AS sum_line_net_doc_ccy,
       round(sum(l.net_amount * d.currency_rate), 2) AS sum_line_net_rm,
       sum(l.line_total)                             AS sum_line_total,
       sum(l.tax_amount)                             AS sum_line_tax,
       count(*) FILTER (WHERE l.net_amount IS NULL)  AS lines_null_net,
       count(l.line_no) - count(DISTINCT l.line_no)  AS repeated_line_no,
       count(DISTINCT l.item_code) FILTER (WHERE l.item_code IS NOT NULL) AS items,
       round(sum(l.net_amount * d.currency_rate) - d.local_net_total, 2)  AS gap_rm,
       d.source_modified_at, d.last_synced_at, d.created_at
FROM docs d
LEFT JOIN finance.billing_document_lines l ON l.document_id = d.id
GROUP BY d.agent, d.id, d.doc_no, d.document_type, d.doc_date, d.currency_code, d.currency_rate,
         d.net_total, d.local_net_total, d.tax_total, d.total,
         d.source_modified_at, d.last_synced_at, d.created_at
HAVING abs(coalesce(sum(l.net_amount * d.currency_rate), 0) - d.local_net_total) > 0.01
ORDER BY abs(coalesce(sum(l.net_amount * d.currency_rate), 0) - d.local_net_total) DESC;

-- Q2. The lines of those documents (product codes only; no customer data).
WITH bad AS (
  SELECT d.id
  FROM finance.billing_documents d
  JOIN companies c ON c.id = d.company_id
  LEFT JOIN customers cu ON cu.id = d.customer_id
  LEFT JOIN sales_agents a ON a.id = CASE WHEN c.sales_agent_source = 'customer'
                                          THEN cu.sales_agent_id ELSE d.sales_agent_id END
  JOIN finance.billing_document_lines l ON l.document_id = d.id
  WHERE d.status = 'posted'
    AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
    AND ((a.sales_agent = 'ERIC NG'  AND d.doc_date >= '2026-10-01' AND d.doc_date < '2026-11-01')
      OR (a.sales_agent = 'JENNIFER' AND d.doc_date >= '2026-09-01' AND d.doc_date < '2026-10-01'))
  GROUP BY d.id, d.local_net_total
  HAVING abs(sum(l.net_amount * d.currency_rate) - d.local_net_total) > 0.01
)
SELECT d.doc_no, l.line_no, l.item_code, l.uom, l.quantity, l.unit_price, l.discount_amount,
       l.net_amount, l.tax_amount, l.line_total, l.from_doc_type, l.from_doc_no,
       l.source_ref AS dtl_key, l.created_at, l.updated_at
FROM bad
JOIN finance.billing_documents d ON d.id = bad.id
JOIN finance.billing_document_lines l ON l.document_id = d.id
ORDER BY d.doc_no, l.line_no, l.source_ref;

-- Q3. How widespread: every posted 2026 document whose lines do not add up, per company/month.
SELECT c.code AS company, to_char(date_trunc('month', d.doc_date), 'YYYY-MM') AS month,
       count(*) AS docs_off,
       round(sum(s.line_rm - d.local_net_total), 2) AS gap_rm
FROM finance.billing_documents d
JOIN companies c ON c.id = d.company_id
JOIN LATERAL (SELECT coalesce(sum(l.net_amount * d.currency_rate), 0) AS line_rm
              FROM finance.billing_document_lines l WHERE l.document_id = d.id) s ON true
WHERE d.status = 'posted'
  AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
  AND d.doc_date >= '2026-01-01'
  AND abs(s.line_rm - d.local_net_total) > 0.01
GROUP BY 1, 2 ORDER BY 1, 2;
ROLLBACK;
