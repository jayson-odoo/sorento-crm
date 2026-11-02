-- PS-REGISTRATION-V3: read-only queries for the behaviour card examples (crew runs on the dev copy and masks
-- names; the cloud lane cannot reach it). Every statement is a SELECT.
BEGIN READ ONLY;

-- 1. How lead sources are spread (Q4).
SELECT source, count(*) FROM projects.leads GROUP BY source ORDER BY 2 DESC;
SELECT informant_source, count(*) FROM projects.leads GROUP BY informant_source ORDER BY 2 DESC;

-- 2. Projects with and without a customer, architect, main contractor (rule 9, rule 3).
SELECT count(*) AS projects,
       count(*) FILTER (WHERE sp.customer_id IS NULL) AS no_customer,
       count(*) FILTER (WHERE sp.architect_party_id IS NOT NULL) AS with_architect,
       count(*) FILTER (WHERE sp.main_contractor_party_id IS NOT NULL) AS with_main_con
FROM projects.projects p LEFT JOIN projects.sales_profile sp ON sp.project_id = p.id;

-- 3. Distinct Area (mukim) values per state (Q3).
SELECT state, count(DISTINCT lower(trim(mukim))) AS distinct_areas, count(*) AS rows
FROM projects.sales_profile WHERE mukim IS NOT NULL GROUP BY state ORDER BY 3 DESC;

-- 4. Parties per type, and how many carry a phone / email (Q1).
SELECT party_type, count(*), count(phone) AS with_phone, count(email) AS with_email
FROM projects.parties GROUP BY party_type;

-- 5. Stakeholders: how many name a party, how many have a phone (rule 6, Q1).
SELECT count(*), count(party_id) AS with_party, count(phone) AS with_phone, count(email) AS with_email
FROM projects.stakeholders;

-- 6. Three recent approved projects with architect + main con set (masked by crew).
SELECT p.project_code, p.title, sp.state, sp.mukim, sp.customer_id IS NOT NULL AS has_customer
FROM projects.projects p JOIN projects.sales_profile sp ON sp.project_id = p.id
WHERE sp.architect_party_id IS NOT NULL AND sp.main_contractor_party_id IS NOT NULL
ORDER BY p.created_at DESC LIMIT 3;

ROLLBACK;
