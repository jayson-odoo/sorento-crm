-- WA-COMPLAINT-INTAKE round 12: publish the committed candidate as the next chatbot_semantic_parser version, UNLABELLED.
-- Run from the repo root of the copy's worktree at the PR head (psql reads the file client-side).
\set ON_ERROR_STOP 1
\set tpl `cat documentation/plans/chatbot/prompt-wa-issue-ideate.txt`
BEGIN;
INSERT INTO ai_prompt_versions (id, name, version, type, template, variables, config_json, commit_message, created_at)
SELECT gen_random_uuid(), v.name,
       (SELECT max(version) + 1 FROM ai_prompt_versions WHERE name = 'chatbot_semantic_parser'),
       v.type, :'tpl' || E'\n', v.variables,
       COALESCE(v.config_json, '{}'::jsonb) || '{"wa_0002_parser_issue_ideate": true}'::jsonb,
       'WA-COMPLAINT-INTAKE round 12 candidate (md5 46e16236). Unlabelled.', now()
FROM ai_prompt_versions v
JOIN ai_prompt_labels l ON l.version_id = v.id AND l.name = 'chatbot_semantic_parser' AND l.label = 'production'
WHERE v.name = 'chatbot_semantic_parser'
  AND md5(v.template) = 'd29c19830b22aa47403a88ddcb8e817d'          -- production holds the v72 text
  AND md5(:'tpl' || E'\n') = '46e16236f8906644ef35d68f87ce5187'     -- the file is the round 12 candidate
  AND NOT EXISTS (SELECT 1 FROM ai_prompt_versions WHERE name = 'chatbot_semantic_parser'
                  AND md5(template) = '46e16236f8906644ef35d68f87ce5187');
SELECT version, md5(template) FROM ai_prompt_versions
WHERE name = 'chatbot_semantic_parser' AND md5(template) = '46e16236f8906644ef35d68f87ce5187';
COMMIT;
