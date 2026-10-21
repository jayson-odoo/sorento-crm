-- LEAN: one parser candidate file as the next UNLABELLED chatbot_semantic_parser version, sorento_explore1020 ONLY.
-- No data change here (the photo alias words and the "Spec" description change are explore-data.sql's).
--
-- Run from the repo root (the lead runs it; crew agents never write the DB), once per candidate:
--   psql "$EXPLORE_DATABASE_URL" -v ON_ERROR_STOP=1 \
--     -v candidate_file=documentation/plans/chatbot/lean-index/parser-v91.txt \
--     -v commit_message='LEAN v91: v90 plus R1 code-not-label and R3 names-nothing-new (lean-changelog.md item 6)' \
--     -f documentation/plans/chatbot/lean-index/explore-version.sql
--
-- Idempotent: skipped when a parser version with the same template (md5) exists. Every other column is copied
-- from v88 (id 4646e9a2-696e-4461-955e-5722b916b763) except the commit message. `ai_prompt_labels` is never
-- touched.

\set ON_ERROR_STOP on

\if :{?candidate_file}
\else
  \echo 'refused: pass -v candidate_file=<path to parser-vNN.txt>'
  \quit
\endif
\if :{?commit_message}
\else
  \echo 'refused: pass -v commit_message=<what this candidate changes>'
  \quit
\endif

SELECT current_database() = 'sorento_explore1020' AS on_explore \gset
\if :on_explore
\else
  \echo 'refused: this file runs on sorento_explore1020 only'
  \quit
\endif

-- The file is the template plus one trailing newline; psql's backquote strips exactly that newline.
\set candidate_template `cat :'candidate_file'`

SELECT length(:'candidate_template') > 60000
       AND position('== PARSER TEMPLATE ==' IN :'candidate_template') > 0
       AND position('{{attachment_types}}' IN :'candidate_template') > 0 AS candidate_ok \gset
\if :candidate_ok
\else
  \echo 'refused: candidate_file is not a parser template candidate'
  \quit
\endif

BEGIN;

INSERT INTO ai_prompt_versions (id, name, version, type, template, variables, config_json, commit_message, created_by)
SELECT gen_random_uuid(), v.name,
       (SELECT max(x.version) + 1 FROM ai_prompt_versions x WHERE x.name = v.name),
       v.type, :'candidate_template', v.variables, v.config_json,
       :'commit_message',
       v.created_by
FROM ai_prompt_versions v
WHERE v.id = '4646e9a2-696e-4461-955e-5722b916b763'
  AND v.name = 'chatbot_semantic_parser'
  AND NOT EXISTS (
    SELECT 1 FROM ai_prompt_versions x WHERE x.name = v.name AND md5(x.template) = md5(:'candidate_template')
  );

COMMIT;

-- What the run left (read only).
SELECT v.id, v.version, length(v.template) AS chars,
       EXISTS (SELECT 1 FROM ai_prompt_labels l WHERE l.version_id = v.id) AS labelled
FROM ai_prompt_versions v
WHERE v.name = 'chatbot_semantic_parser' AND md5(v.template) = md5(:'candidate_template');
