-- QUOTE-MULTI-RECIPIENT dev examples (read-only). crew-data-request for the behaviour card v2.

-- 1. Documents per kind: with / without a recipient, issued at least once.
SELECT d.kind,
       count(*) AS docs,
       count(*) FILTER (WHERE d.recipient_party_id IS NULL AND d.recipient_name_snapshot IS NULL) AS no_recipient,
       count(DISTINCT i.document_id) AS issued_docs,
       count(i.id) AS issues
  FROM projects.quotation_documents d
  LEFT JOIN projects.quotation_issues i ON i.document_id = d.id
 GROUP BY 1;

-- 2. Projects with 2+ parties (developer + links) that already have a proposal: the multi-recipient candidates.
SELECT p.project_code, p.title, count(DISTINCT pl.party_id) + (p.developer_party_id IS NOT NULL)::int AS parties,
       count(DISTINCT d.id) AS documents
  FROM projects.projects p
  JOIN projects.quotation_documents d ON d.project_id = p.id
  LEFT JOIN projects.party_links pl ON pl.project_id = p.id
 GROUP BY p.id, 1, 2 ORDER BY 3 DESC LIMIT 5;

-- 3. Same project, several documents with near-identical totals (today's workaround: one proposal per party).
SELECT p.project_code, d.document_no, d.recipient_name_snapshot, max(i.grand_total) AS latest_total
  FROM projects.quotation_documents d JOIN projects.projects p ON p.id = d.project_id
  LEFT JOIN projects.quotation_issues i ON i.document_id = d.id
 GROUP BY 1, 2, 3 ORDER BY 1, 4;

-- 4. Letters that name the recipient (Q2 size).
SELECT count(*) FILTER (WHERE cover_letter_html ILIKE '%' || recipient_name_snapshot || '%') AS letter_names_recipient,
       count(*) AS with_recipient
  FROM projects.quotation_documents WHERE recipient_name_snapshot IS NOT NULL;
