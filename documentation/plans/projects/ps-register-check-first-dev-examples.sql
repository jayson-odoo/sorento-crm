-- PS-REGISTER-CHECK-FIRST: read-only examples for the behaviour card (crew or the owner runs them on the crew
-- dev DB; the lane does not run SQL on a prod restore). Every statement is a SELECT. Output carries titles: mask
-- them (codes only) before pasting anywhere public.
BEGIN READ ONLY;

-- 1. Projects by stage, and how many have at least one project document.
SELECT s.key, s.label, count(*) AS projects,
       count(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM entity_attachment_links l JOIN attachments a ON a.id = l.attachment_id
           WHERE l.entity_type = 'project' AND l.entity_id = p.id::text AND NOT a.is_deleted
       )) AS with_any_document
FROM projects.projects p
LEFT JOIN statuses s ON s.id = p.status_id
WHERE p.approval_state IS NULL OR p.approval_state = 'approved'
GROUP BY s.key, s.label ORDER BY 3 DESC;

-- 2. Projects sitting in Registered: code, document count (the ones the new guard affects next).
SELECT p.project_code, count(a.id) AS documents
FROM projects.projects p
JOIN statuses s ON s.id = p.status_id AND s.key = 'registered'
LEFT JOIN entity_attachment_links l ON l.entity_type = 'project' AND l.entity_id = p.id::text
LEFT JOIN attachments a ON a.id = l.attachment_id AND NOT a.is_deleted
GROUP BY p.project_code ORDER BY 2, 1 LIMIT 20;

-- 3. Interests (takeover requests) by kind and state, and the projects that have more than one.
SELECT kind, status, count(*) FROM projects.takeover_requests GROUP BY 1, 2 ORDER BY 1, 2;
SELECT p.project_code, count(*) AS requests
FROM projects.takeover_requests t JOIN projects.projects p ON p.id = t.project_id
GROUP BY p.project_code HAVING count(*) > 1 ORDER BY 2 DESC LIMIT 10;

-- 4. Registrations waiting for approval (submitted by a salesperson) and drafts.
SELECT approval_state, count(*) FROM projects.projects GROUP BY 1 ORDER BY 1;

-- 5. Title pairs the Check would flag (same company, similarity >= 0.55 surface / 0.70 block), approved rows only.
SELECT a.project_code AS a_code, b.project_code AS b_code,
       round(greatest(similarity(lower(a.title), lower(b.title)),
                      strict_word_similarity(lower(a.title), lower(b.title)),
                      strict_word_similarity(lower(b.title), lower(a.title)))::numeric, 2) AS score
FROM projects.projects a
JOIN projects.projects b ON b.company_id = a.company_id AND b.id > a.id
WHERE (a.approval_state IS NULL OR a.approval_state = 'approved')
  AND (b.approval_state IS NULL OR b.approval_state = 'approved')
  AND similarity(lower(a.title), lower(b.title)) >= 0.4
ORDER BY score DESC LIMIT 15;

-- 6. Attachment types present (a "Requirements" row does not exist yet).
SELECT code, type_name FROM attachment_types ORDER BY code;

ROLLBACK;
