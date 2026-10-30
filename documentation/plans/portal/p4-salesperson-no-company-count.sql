-- READ-ONLY. Salesperson contacts (is_salesperson: ACTIVE, untrashed, linked contact, roles within
-- {salesperson, portal_user} incl. salesperson) and how many have no respond_contact_companies row.
WITH sp AS (
  SELECT u.id AS user_id, u.respond_contact_id AS contact_id
  FROM users u
  WHERE u.status = 'ACTIVE' AND NOT u.is_trashed AND u.respond_contact_id IS NOT NULL
    AND EXISTS (SELECT 1 FROM user_role_assignments a JOIN user_roles r ON r.id = a.role_id
                WHERE a.user_id = u.id AND r.slug = 'salesperson')
    AND NOT EXISTS (SELECT 1 FROM user_role_assignments a JOIN user_roles r ON r.id = a.role_id
                    WHERE a.user_id = u.id AND r.slug NOT IN ('salesperson', 'portal_user'))
)
SELECT count(*) AS salesperson_contacts,
       count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM respond_contact_companies cc
                                          WHERE cc.respond_contact_id = sp.contact_id)) AS no_linked_company,
       count(*) FILTER (WHERE c.requires_registered_project) AS flagged_requires_registered_project
FROM sp JOIN respond_contacts c ON c.id = sp.contact_id;
