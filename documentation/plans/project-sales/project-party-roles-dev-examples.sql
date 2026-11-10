-- PROJECT-PARTY-ROLES dev examples (read-only). crew-data-request for the behaviour card.

-- 1. PPF2611003: developer, architect, main contractor columns and every party_links row.
SELECT 'developer' AS role, pa.name, pa.party_type
  FROM projects.projects p JOIN projects.parties pa ON pa.id = p.developer_party_id
 WHERE p.project_code = 'PPF2611003'
UNION ALL
SELECT 'architect (column)', pa.name, pa.party_type
  FROM projects.projects p JOIN projects.sales_profile sp ON sp.project_id = p.id
  JOIN projects.parties pa ON pa.id = sp.architect_party_id
 WHERE p.project_code = 'PPF2611003'
UNION ALL
SELECT 'main_contractor (column)', pa.name, pa.party_type
  FROM projects.projects p JOIN projects.sales_profile sp ON sp.project_id = p.id
  JOIN projects.parties pa ON pa.id = sp.main_contractor_party_id
 WHERE p.project_code = 'PPF2611003'
UNION ALL
SELECT pl.role, pa.name, pa.party_type
  FROM projects.projects p JOIN projects.party_links pl ON pl.project_id = p.id
  JOIN projects.parties pa ON pa.id = pl.party_id
 WHERE p.project_code = 'PPF2611003';

-- 2. Parties per type, active / inactive.
SELECT party_type, is_active, count(*) FROM projects.parties GROUP BY 1, 2 ORDER BY 1, 2;

-- 3. Backfill size, and column parties whose type differs from the column's role.
SELECT count(*) FILTER (WHERE architect_party_id IS NOT NULL) AS architect_set,
       count(*) FILTER (WHERE main_contractor_party_id IS NOT NULL) AS main_con_set
  FROM projects.sales_profile;
SELECT 'architect' AS col, pa.party_type, count(*)
  FROM projects.sales_profile sp JOIN projects.parties pa ON pa.id = sp.architect_party_id
 WHERE pa.party_type <> 'architect' GROUP BY 1, 2
UNION ALL
SELECT 'main_contractor', pa.party_type, count(*)
  FROM projects.sales_profile sp JOIN projects.parties pa ON pa.id = sp.main_contractor_party_id
 WHERE pa.party_type <> 'main_contractor' GROUP BY 1, 2;

-- 4. Proposals: recipient vs the project's developer.
SELECT d.kind,
       count(*) AS docs,
       count(*) FILTER (WHERE d.recipient_party_id IS NULL) AS no_recipient,
       count(*) FILTER (WHERE d.recipient_party_id IS DISTINCT FROM p.developer_party_id) AS not_developer
  FROM projects.quotation_documents d JOIN projects.projects p ON p.id = d.project_id
 GROUP BY 1;

-- 5. Role / type values outside the eight seeded keys.
SELECT 'party_type' AS src, party_type AS v, count(*) FROM projects.parties
 WHERE party_type NOT IN ('developer','architect','main_contractor','trading_house','consultant',
                          'subcontractor','interior_designer','tender_party') GROUP BY 1, 2
UNION ALL
SELECT 'link_role', role, count(*) FROM projects.party_links
 WHERE role NOT IN ('developer','architect','main_contractor','trading_house','consultant',
                    'subcontractor','interior_designer','tender_party') GROUP BY 1, 2;

-- 6. Three more real projects with the most parties, for the mock.
SELECT p.project_code, p.title, count(pl.*) AS links
  FROM projects.projects p LEFT JOIN projects.party_links pl ON pl.project_id = p.id
 GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 3;
