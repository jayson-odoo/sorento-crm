-- WA-COMPLAINT-INTAKE: publish the committed candidate prompt as the next chatbot_semantic_parser version, UNLABELLED.
-- Run with psql from the repo root of a worktree at the PR head (psql reads the file client-side):
--   psql "$DATABASE_URL" -f documentation/plans/chatbot/sql/wa-issue-publish.sql
-- Type, variables and config come from the version holding the v72 text (md5 d29c1983), on prod and dev alike.
-- Inserts only when the file is the pinned candidate, and only once. Moves no label.
\set ON_ERROR_STOP 1
\set candidate_md5 'd7d8c83742e2c43f56fc44cf9f0b9c1d'
\set tpl `cat documentation/plans/chatbot/prompt-wa-issue-ideate.txt`
BEGIN;
INSERT INTO ai_prompt_versions (id, name, version, type, template, variables, config_json, commit_message, created_at)
SELECT gen_random_uuid(), v.name,
       (SELECT max(version) + 1 FROM ai_prompt_versions WHERE name = 'chatbot_semantic_parser'),
       v.type, :'tpl' || E'\n', v.variables,
       COALESCE(v.config_json, '{}'::jsonb) || '{"wa_0002_parser_issue_ideate": true}'::jsonb,
       'WA-COMPLAINT-INTAKE candidate (md5 ' || :'candidate_md5' || '). Unlabelled.', now()
FROM ai_prompt_versions v
WHERE v.id = (SELECT id FROM ai_prompt_versions WHERE name = 'chatbot_semantic_parser'
              AND md5(template) = 'd29c19830b22aa47403a88ddcb8e817d' ORDER BY version DESC LIMIT 1)
  AND md5(:'tpl' || E'\n') = :'candidate_md5'
  AND NOT EXISTS (SELECT 1 FROM ai_prompt_versions WHERE name = 'chatbot_semantic_parser'
                  AND md5(template) = :'candidate_md5');
SELECT version, md5(template) FROM ai_prompt_versions
WHERE name = 'chatbot_semantic_parser' AND md5(template) = :'candidate_md5';
COMMIT;
