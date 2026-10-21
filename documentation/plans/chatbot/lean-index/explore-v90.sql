-- LEAN v90: the v90 candidate as the next UNLABELLED chatbot_semantic_parser version, sorento_explore1020 ONLY.
-- No data change here (the photo alias words and the "Spec" description change are explore-data.sql's).
--
-- Run from the repo root (the lead runs it; crew agents never write the DB):
--   psql "$EXPLORE_DATABASE_URL" -v ON_ERROR_STOP=1 \
--     -v v90_file=documentation/plans/chatbot/lean-index/parser-v90.txt \
--     -f documentation/plans/chatbot/lean-index/explore-v90.sql
--
-- Idempotent: skipped when a parser version with the same template (md5) exists. Every other column is copied
-- from v88 (id 4646e9a2-696e-4461-955e-5722b916b763) except the commit message. `ai_prompt_labels` is never
-- touched.

\set ON_ERROR_STOP on

\if :{?v90_file}
\else
  \echo 'refused: pass -v v90_file=<path to parser-v90.txt>'
  \quit
\endif

SELECT current_database() = 'sorento_explore1020' AS on_explore \gset
\if :on_explore
\else
  \echo 'refused: this file runs on sorento_explore1020 only'
  \quit
\endif

-- The file is the template plus one trailing newline; psql's backquote strips exactly that newline.
\set v90_template `cat :'v90_file'`

SELECT length(:'v90_template') > 60000
       AND position('{{attachment_types}}' IN :'v90_template') > 0
       AND position('`continuation` true when the message only asks for more' IN :'v90_template') > 0 AS v90_ok \gset
\if :v90_ok
\else
  \echo 'refused: v90_file is not the v90 candidate'
  \quit
\endif

BEGIN;

INSERT INTO ai_prompt_versions (id, name, version, type, template, variables, config_json, commit_message, created_by)
SELECT gen_random_uuid(), v.name,
       (SELECT max(x.version) + 1 FROM ai_prompt_versions x WHERE x.name = v.name),
       v.type, :'v90_template', v.variables, v.config_json,
       'LEAN v90: v89 plus four reading rules and the continuation field '
       '(documentation/plans/chatbot/lean-index/lean-changelog.md)',
       v.created_by
FROM ai_prompt_versions v
WHERE v.id = '4646e9a2-696e-4461-955e-5722b916b763'
  AND v.name = 'chatbot_semantic_parser'
  AND NOT EXISTS (
    SELECT 1 FROM ai_prompt_versions x WHERE x.name = v.name AND md5(x.template) = md5(:'v90_template')
  );

COMMIT;

-- What the run left (read only).
SELECT v.id, v.version, length(v.template) AS chars,
       EXISTS (SELECT 1 FROM ai_prompt_labels l WHERE l.version_id = v.id) AS labelled
FROM ai_prompt_versions v
WHERE v.name = 'chatbot_semantic_parser' AND md5(v.template) = md5(:'v90_template');
