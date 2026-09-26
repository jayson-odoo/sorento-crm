-- Pre-flight queries for S0 of the unified identity plan (#1280).
-- Plan: documentation/plans/identity/PLAN-unified-identity-26sep.md section 9.1.
--
-- Run on the prod copy BEFORE the S0 migration is applied:
--   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -f documentation/plans/identity/preflight-s0.sql
-- Every query is read-only. Paste the full output into the S0 PR.
--
-- Stop rule (plan 9.1): a non-empty result for Q1 or Q2 stops S0 and goes to the owner as a
-- list of names; nothing is merged or unlinked automatically. The S0 migration enforces the
-- same rule itself: it raises before any DDL if Q1 or Q2 would return a row.
--
-- Phone numbers: users.contact_number and respond_contacts.phone_number are both stored as
-- E.164 digits without '+' (app/services/phone_utils.normalize_msisdn); the equality joins
-- below rely on that stored form, exactly as respond_link_service does at runtime.

\pset pager off
\echo '== Q1. Case-duplicate emails (must be empty) =='
SELECT lower(u.email) AS email_lower,
       count(*) AS users,
       string_agg(coalesce(nullif(trim(u.name), ''), u.email), ' | ' ORDER BY u.created_at) AS names
FROM users u
WHERE u.email IS NOT NULL
GROUP BY lower(u.email)
HAVING count(*) > 1
ORDER BY 1;

\echo '== Q2. Contacts claimed by more than one user (must be empty) =='
SELECT u.respond_contact_id,
       coalesce(nullif(trim(rc.name), ''), rc.phone_number) AS contact,
       count(*) AS users,
       string_agg(coalesce(nullif(trim(u.name), ''), u.email), ' | ' ORDER BY u.created_at) AS user_names
FROM users u
LEFT JOIN respond_contacts rc ON rc.id = u.respond_contact_id
WHERE u.respond_contact_id IS NOT NULL
GROUP BY u.respond_contact_id, rc.name, rc.phone_number
HAVING count(*) > 1
ORDER BY 1;

\echo '== Q3. Link backfill set (AC-04): unlinked users whose phone matches exactly one contact that no other user claims =='
\echo '   Every row here is a link the S0 migration WILL write. Listed by name for the owner.'
WITH candidates AS (
    SELECT u.id AS user_id, u.name AS user_name, u.email, u.contact_number
    FROM users u
    WHERE u.respond_contact_id IS NULL
      AND u.contact_number IS NOT NULL
      AND u.is_trashed = false
      AND coalesce(u.is_integration, false) = false
),
matches AS (
    SELECT c.user_id, rc.id AS contact_id, rc.name AS contact_name, rc.phone_number,
           count(*) OVER (PARTITION BY c.user_id) AS contacts_for_phone
    FROM candidates c
    JOIN respond_contacts rc ON rc.phone_number = c.contact_number
)
SELECT c.user_name, c.email, m.phone_number,
       coalesce(nullif(trim(m.contact_name), ''), m.phone_number) AS contact_name
FROM candidates c
JOIN matches m ON m.user_id = c.user_id
WHERE m.contacts_for_phone = 1
  AND NOT EXISTS (SELECT 1 FROM users o WHERE o.respond_contact_id = m.contact_id)
ORDER BY c.user_name NULLS LAST, c.email;

\echo '== Q3b. Left unlinked by the backfill (ambiguous phone, or contact already claimed) =='
WITH candidates AS (
    SELECT u.id AS user_id, u.name AS user_name, u.email, u.contact_number
    FROM users u
    WHERE u.respond_contact_id IS NULL
      AND u.contact_number IS NOT NULL
      AND u.is_trashed = false
      AND coalesce(u.is_integration, false) = false
)
SELECT c.user_name, c.email, c.contact_number,
       count(rc.id) AS matching_contacts,
       bool_or(EXISTS (SELECT 1 FROM users o WHERE o.respond_contact_id = rc.id)) AS a_match_is_claimed
FROM candidates c
JOIN respond_contacts rc ON rc.phone_number = c.contact_number
GROUP BY c.user_id, c.user_name, c.email, c.contact_number
HAVING count(rc.id) > 1
    OR bool_or(EXISTS (SELECT 1 FROM users o WHERE o.respond_contact_id = rc.id))
ORDER BY c.user_name NULLS LAST;

\echo '== Q4. Salesperson contacts by rule (plan 6.1), by set-up state (counts only; nothing is created) =='
WITH salesperson_contacts AS (
    SELECT rcms.contact_id
    FROM respond_contact_market_segments rcms
    JOIN market_segments ms ON ms.code = rcms.segment_code
    WHERE ms.is_requestor_selectable = true
    UNION
    SELECT sa.contact_id FROM sales_agents sa WHERE sa.contact_id IS NOT NULL
),
classified AS (
    SELECT sc.contact_id,
           CASE
               WHEN EXISTS (SELECT 1 FROM users u WHERE u.respond_contact_id = sc.contact_id)
                   THEN '1 already linked to a user'
               WHEN EXISTS (SELECT 1 FROM users u
                            WHERE u.contact_number = rc.phone_number AND u.respond_contact_id IS NULL)
                   THEN '2 phone matches one unlinked user'
               WHEN EXISTS (SELECT 1 FROM users u
                            WHERE u.contact_number = rc.phone_number AND u.respond_contact_id IS NOT NULL)
                   THEN '3 phone matches a user linked elsewhere'
               ELSE '4 no user match'
           END AS state
    FROM salesperson_contacts sc
    JOIN respond_contacts rc ON rc.id = sc.contact_id
)
SELECT state, count(*) AS contacts FROM classified GROUP BY state ORDER BY state;

\echo '== Q5. Contacts whose portal tokens span more than one space_id (S2 space-derivation risk) =='
SELECT pt.contact_id,
       coalesce(nullif(trim(rc.name), ''), rc.phone_number) AS contact,
       count(DISTINCT pt.space_id) AS spaces,
       string_agg(DISTINCT pt.space_id, ', ') AS space_ids
FROM portal_tokens pt
LEFT JOIN respond_contacts rc ON rc.id = pt.contact_id
GROUP BY pt.contact_id, rc.name, rc.phone_number
HAVING count(DISTINCT pt.space_id) > 1
ORDER BY spaces DESC, contact;

\echo '== Q5b. Row counts the S0 migration touches (sizing the expand step) =='
SELECT (SELECT count(*) FROM users) AS users,
       (SELECT count(*) FROM users WHERE email IS NULL) AS users_null_email,
       (SELECT count(*) FROM users WHERE contact_number IS NULL AND email IS NULL) AS users_no_email_no_phone,
       (SELECT count(*) FROM user_sessions) AS user_sessions,
       (SELECT count(*) FROM audit_logs) AS audit_logs;

-- Q6 (every reader of users.email that would fail on NULL) is a code grep, not SQL; its result
-- is listed in the S0 PR body.
