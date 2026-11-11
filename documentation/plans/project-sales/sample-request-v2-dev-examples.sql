-- SAMPLE-REQUEST-V2 dev examples (read-only). crew-data-request for the behaviour card.
-- Aggregates and a handful of rows; names get replaced with fake-but-stable ones in the card.

-- 1. How many sample requests per project (does "many per project" already happen?).
SELECT n_requests, count(*) AS projects
  FROM (SELECT project_id, count(*) AS n_requests
          FROM projects.sample_requests WHERE project_id IS NOT NULL GROUP BY 1) t
 GROUP BY 1 ORDER BY 1;

-- 2. Registered vs unregistered, debtor vs typed customer.
SELECT (project_id IS NOT NULL) AS registered,
       (customer_id IS NOT NULL) AS debtor,
       count(*)
  FROM projects.sample_requests GROUP BY 1, 2 ORDER BY 1, 2;

-- 3. Today's free-text Ship To / For: does Ship To match a party of the project, or the customer?
SELECT sr.request_no,
       sr.ship_to_name,
       sr.scope_note,
       c.customer_name,
       EXISTS (
         SELECT 1 FROM projects.party_links pl JOIN projects.parties pa ON pa.id = pl.party_id
          WHERE pl.project_id = sr.project_id AND lower(pa.name) = lower(sr.ship_to_name)
       ) OR EXISTS (
         SELECT 1 FROM projects.projects p JOIN projects.parties pa ON pa.id = p.developer_party_id
          WHERE p.id = sr.project_id AND lower(pa.name) = lower(sr.ship_to_name)
       ) AS ship_to_is_a_project_party,
       lower(coalesce(c.customer_name, sr.customer_name, '')) = lower(coalesce(sr.ship_to_name, '')) AS ship_to_is_customer,
       (sr.site_contact_phone IS NOT NULL) AS has_phone,
       (sr.site_contact_note IS NOT NULL) AS has_note
  FROM projects.sample_requests sr
  LEFT JOIN customers c ON c.id = sr.customer_id
 ORDER BY sr.created_at DESC
 LIMIT 25;

-- 4. Projects with sample requests: how many parties (developer + links), how many have an
--    address, how many have contacts.
SELECT p.project_code,
       (SELECT count(*) FROM projects.party_links pl WHERE pl.project_id = p.id)
         + (p.developer_party_id IS NOT NULL)::int AS parties,
       (SELECT count(*) FROM projects.party_links pl JOIN projects.parties pa ON pa.id = pl.party_id
         WHERE pl.project_id = p.id AND coalesce(pa.address, '') <> '') AS parties_with_address,
       (SELECT count(*) FROM projects.party_links pl JOIN projects.party_contacts pc ON pc.party_id = pl.party_id
         WHERE pl.project_id = p.id AND pc.is_active) AS contacts
  FROM projects.projects p
 WHERE EXISTS (SELECT 1 FROM projects.sample_requests sr WHERE sr.project_id = p.id)
 ORDER BY p.created_at DESC
 LIMIT 15;

-- 5. Field fill rates on existing requests (scope_note = the "For" field the owner crossed out).
SELECT count(*) AS total,
       count(scope_note) AS has_for,
       count(ship_to_address) AS has_address,
       count(site_contact_name) AS has_contact,
       count(site_contact_phone) AS has_phone,
       count(site_contact_note) AS has_note
  FROM projects.sample_requests;
