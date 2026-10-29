-- LEAD-GOVERNS-REGISTER: read-only counts for the behaviour card (crew or owner runs; the lane cannot:
-- auto-mode blocks SQL on sorento_prod_1020). Every statement is a SELECT.
BEGIN READ ONLY;

-- 1. Leads, and how many have no customer (the "Buyer" was optional since D6).
SELECT count(*) AS leads,
       count(*) FILTER (WHERE customer_id IS NULL) AS leads_without_customer,
       count(*) FILTER (WHERE outcome = 'open') AS open_leads
FROM projects.leads;

-- 2. Projects, how many have no lead, and how many have no customer of their own.
SELECT count(*) AS projects,
       count(*) FILTER (WHERE p.lead_id IS NULL) AS projects_without_lead,
       count(*) FILTER (WHERE sp.customer_id IS NULL) AS projects_without_own_customer
FROM projects.projects p
LEFT JOIN projects.sales_profile sp ON sp.project_id = p.id;

-- 3. Projects whose own customer differs from their lead's customer (possible today, no sync).
SELECT p.project_code, l.lead_code, sp.customer_id AS project_customer, l.customer_id AS lead_customer
FROM projects.projects p
JOIN projects.leads l ON l.id = p.lead_id
LEFT JOIN projects.sales_profile sp ON sp.project_id = p.id
WHERE sp.customer_id IS NOT NULL AND l.customer_id IS NOT NULL AND sp.customer_id <> l.customer_id;

-- 4. Leads linked to more than one project (only Qualify can do that).
SELECT l.lead_code, count(*) AS projects
FROM projects.projects p JOIN projects.leads l ON l.id = p.lead_id
GROUP BY l.lead_code HAVING count(*) > 1;

-- 5. Customers the lead wizard created (select_or_create_customer, source = 'project_lead').
SELECT count(*) AS customers_created_by_lead_wizard FROM customers WHERE source = 'project_lead';

ROLLBACK;
