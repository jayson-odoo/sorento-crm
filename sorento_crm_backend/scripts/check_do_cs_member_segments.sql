-- MYTEAM-BY-SEGMENT: who in DO Customer Service is tagged with which segments / brands.
--
-- My Team now shows a teammate's task only when the task's contact segment and brand
-- are ones the viewer serves. A viewer's tags are the UNION over every team they are a
-- member of; no tag on any membership = serves everything. So an untagged project CS
-- still sees retail tasks until they are tagged. Run this, then fix tags in
-- Users & Access > Access > AI Agents > (agent) > team member row (market segments / brands).
--
-- Read-only:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c 'BEGIN READ ONLY' \
--        -f scripts/check_do_cs_member_segments.sql
--
-- Override the team name with:  -v team_name='Other Team'
\if :{?team_name}
\else
  \set team_name 'DO Customer Service'
\endif

-- 1) Every membership (in ANY team) of each DO Customer Service member, with its tags.
--    effective_* columns are what My Team filters on (the union across memberships).
WITH do_cs_users AS (
  SELECT DISTINCT tm.user_id
  FROM team_members tm
  JOIN teams t ON t.id = tm.team_id
  WHERE t.name = :'team_name'
),
membership AS (
  SELECT
    tm.user_id,
    t.name AS team_name,
    COALESCE(
      (SELECT string_agg(s.segment_code, ', ' ORDER BY s.segment_code)
         FROM team_member_market_segments s WHERE s.team_member_id = tm.id),
      '(all)') AS segments,
    COALESCE(
      (SELECT string_agg(lower(b.brand_code), ', ' ORDER BY lower(b.brand_code))
         FROM team_member_brands b WHERE b.team_member_id = tm.id),
      '(all)') AS brands
  FROM team_members tm
  JOIN teams t ON t.id = tm.team_id
  WHERE tm.user_id IN (SELECT user_id FROM do_cs_users)
)
SELECT
  COALESCE(NULLIF(trim(u.name), ''), u.email) AS member,
  m.team_name,
  m.segments,
  m.brands,
  COALESCE(
    (SELECT string_agg(DISTINCT s.segment_code, ', ')
       FROM team_members tm2
       JOIN team_member_market_segments s ON s.team_member_id = tm2.id
      WHERE tm2.user_id = m.user_id),
    '(all)') AS effective_segments,
  COALESCE(
    (SELECT string_agg(DISTINCT lower(b.brand_code), ', ')
       FROM team_members tm2
       JOIN team_member_brands b ON b.team_member_id = tm2.id
      WHERE tm2.user_id = m.user_id),
    '(all)') AS effective_brands
FROM membership m
JOIN users u ON u.id = m.user_id
ORDER BY member, m.team_name;

-- 2) Open tasks held by DO Customer Service members, by contact segment, so the owner can
--    see how many each tag change moves. '(none)' = contact with no segment (visible to all).
--    Approximate against My Team: it includes the viewer's own tasks (My Team excludes
--    them) and a contact with two segments counts once in each row.
SELECT
  COALESCE(seg.segment_code, '(none)') AS contact_segment,
  COUNT(DISTINCT c.id)                 AS open_tasks
FROM conversation_sla_tracking c
LEFT JOIN respond_contact_market_segments seg ON seg.contact_id = c.respond_contact_id
WHERE c.is_resolved IS FALSE
  AND c.voided_at IS NULL
  AND c.assigned_to_id IN (
    SELECT tm.user_id FROM team_members tm JOIN teams t ON t.id = tm.team_id
    WHERE t.name = :'team_name')
GROUP BY 1
ORDER BY 1;
