-- SALES-LEADERBOARD: read-only, dev copy only. Nothing is written (BEGIN READ ONLY ... ROLLBACK).
-- October 2026 vs September 2026, invoiced net (IV + CS + DN - CN, posted only, by doc_date),
-- per agent code and person_label, the rules of app/services/sales/invoiced_sales.py:79-131.
-- Paste the output on PR #2227. No customer names or phones are selected.
BEGIN READ ONLY;
WITH docs AS (
  SELECT d.id, d.company_id, d.doc_date, d.customer_id,
         CASE WHEN c.sales_agent_source = 'customer' THEN cu.sales_agent_id ELSE d.sales_agent_id END AS agent_id,
         d.agent_code,
         CASE WHEN d.document_type = 'credit_note' THEN -d.local_net_total ELSE d.local_net_total END AS doc_amount
  FROM finance.billing_documents d
  JOIN companies c ON c.id = d.company_id
  LEFT JOIN customers cu ON cu.id = d.customer_id
  WHERE d.status = 'posted'
    AND d.document_type IN ('invoice','cash_sale','credit_note','debit_note')
    AND d.doc_date >= '2026-09-01' AND d.doc_date < '2026-11-01'
),
lines AS (
  SELECT l.document_id,
         sum(CASE WHEN bd.document_type = 'credit_note' THEN -1 ELSE 1 END * l.net_amount * bd.currency_rate) AS line_amount
  FROM finance.billing_document_lines l
  JOIN finance.billing_documents bd ON bd.id = l.document_id
  WHERE l.document_id IN (SELECT id FROM docs)
  GROUP BY l.document_id
)
SELECT co.code                                         AS company,
       coalesce(a.sales_agent, d.agent_code, '(no agent)') AS agent_code,
       a.person_label,
       to_char(date_trunc('month', d.doc_date), 'YYYY-MM') AS month,
       round(sum(coalesce(ln.line_amount, 0)), 2)      AS line_sum_rm,
       round(sum(d.doc_amount), 2)                      AS doc_sum_rm,
       count(DISTINCT d.customer_id)                    AS customers,
       count(*)                                         AS documents
FROM docs d
JOIN companies co ON co.id = d.company_id
LEFT JOIN sales_agents a ON a.id = d.agent_id
LEFT JOIN lines ln ON ln.document_id = d.id
GROUP BY 1, 2, 3, 4
ORDER BY 4 DESC, 5 DESC;
-- Agent targets that cover October 2026 (for the target % column); figures come from the Targets screen.
SELECT t.target_no, t.subject_kind, a.sales_agent AS agent_code, t.metric, t.basis, t.start_date, t.end_date
FROM sales.targets t
LEFT JOIN sales_agents a ON a.id = t.sales_agent_id
WHERE t.subject_kind = 'agent' AND t.start_date <= '2026-10-31' AND t.end_date >= '2026-10-01'
ORDER BY t.target_no;
ROLLBACK;
