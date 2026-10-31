-- Portal tokens whose space_id differs from their contact's workspace.
--
-- Evidence for an open decision (follow-up to #2028): an internal contact id
-- resolves whatever space_id the caller passes, and a token may carry a stale
-- space_id. Before that is tightened, count how many ACTIVE tokens would be
-- affected. Read-only and aggregate only (no ids, no names, no phone numbers).
--
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c 'BEGIN READ ONLY' \
--        -f scripts/portal_token_space_drift.sql
--
-- Buckets: matches | differs | contact_has_no_workspace | workspace_row_missing
-- | contact_missing. `differs` is the count that a stricter check would lock out.
SELECT
  CASE
    WHEN c.id IS NULL                 THEN 'contact_missing'
    WHEN c.workspace_id IS NULL       THEN 'contact_has_no_workspace'
    WHEN w.id IS NULL                 THEN 'workspace_row_missing'
    WHEN w.space_id = t.space_id      THEN 'matches'
    ELSE 'differs'
  END                              AS bucket,
  t.is_impersonation,
  (t.verified_at IS NOT NULL)      AS verified,
  count(*)                         AS tokens,
  count(DISTINCT t.contact_id)     AS contacts
FROM portal_tokens t
LEFT JOIN respond_contacts c   ON c.id = t.contact_id
LEFT JOIN respond_workspaces w ON w.id = c.workspace_id
WHERE t.revoked_at IS NULL
  AND t.expires_at > now() AT TIME ZONE 'UTC'
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
