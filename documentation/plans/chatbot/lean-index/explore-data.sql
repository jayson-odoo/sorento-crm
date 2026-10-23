-- LEAN-INDEX data step for sorento_explore1020 ONLY (never production: see PROD-OWNER-STEP.md).
--
-- Run from the repo root (the lead runs it; crew agents never write the DB):
--   psql "$EXPLORE_DATABASE_URL" -v ON_ERROR_STOP=1 \
--     -v lean_file=documentation/plans/chatbot/lean-index/parser-lean.txt \
--     -f documentation/plans/chatbot/lean-index/explore-data.sql
--
-- Idempotent: every write is guarded, so a rerun changes nothing.
--   1. The photo attachment type's ALIAS words (lookup set `attachment_type_alias`, option value = the type's
--      name, keywords = the words): what `chatbot_prompt_vars._alias_words` reads and
--      `head/closed_lists_index.file_lines` matches. The index matches a message phrase of at most 3 words
--      (`candidates.MAX_PHRASE_WORDS`), so "how does it look" itself never matches; "does it look" (inside it)
--      and "how it looks" do.
--   2. "Spec" leaves technical_specifications' description (a description part is a Words entry).
--   3. The candidate as a NEW UNLABELLED `chatbot_semantic_parser` version: next free version number, every
--      other column copied from v88 except the commit message. `ai_prompt_labels` is never touched.

\set ON_ERROR_STOP on

\if :{?lean_file}
\else
  \echo 'refused: pass -v lean_file=<path to parser-lean.txt>'
  \quit
\endif

SELECT current_database() = 'sorento_explore1020' AS on_explore \gset
\if :on_explore
\else
  \echo 'refused: this file runs on sorento_explore1020 only'
  \quit
\endif

-- The file is the template plus one trailing newline; psql's backquote strips exactly that newline.
\set lean_template `cat :'lean_file'`

SELECT length(:'lean_template') > 60000 AND position('{{attachment_types}}' IN :'lean_template') > 0 AS lean_ok \gset
\if :lean_ok
\else
  \echo 'refused: lean_file is not the parser candidate'
  \quit
\endif

BEGIN;

-- 1. Photo alias words ------------------------------------------------------------------------------------------
INSERT INTO lookup_sets (id, set_key, name, is_active)
SELECT gen_random_uuid(), 'attachment_type_alias', 'Attachment Type Alias', true
WHERE NOT EXISTS (SELECT 1 FROM lookup_sets WHERE set_key = 'attachment_type_alias');

INSERT INTO lookup_options (id, set_id, value, label, sort_order, is_active)
SELECT gen_random_uuid(), s.id, t.type_name, t.type_name, 0, true
FROM lookup_sets s
JOIN attachment_types t ON t.code = 'product_photos'
WHERE s.set_key = 'attachment_type_alias'
  AND NOT EXISTS (
    SELECT 1 FROM lookup_options o
    WHERE o.set_id = s.id AND lower(o.value) IN (lower(t.type_name), lower(t.code))
  );

INSERT INTO lookup_option_keywords (id, option_id, keyword, locale)
SELECT gen_random_uuid(), o.id, k.keyword, NULL
FROM lookup_sets s
JOIN attachment_types t ON t.code = 'product_photos'
JOIN lookup_options o ON o.set_id = s.id AND lower(o.value) IN (lower(t.type_name), lower(t.code))
CROSS JOIN (VALUES ('how does it look'), ('does it look'), ('how it looks'), ('look like'), ('show me'), ('see it'))
  AS k(keyword)
WHERE s.set_key = 'attachment_type_alias'
  AND NOT EXISTS (
    SELECT 1 FROM lookup_option_keywords x WHERE x.option_id = o.id AND lower(x.keyword) = lower(k.keyword)
  );

-- 2. "Spec" out of technical_specifications' description (the part between separators, the rest kept) ----------
UPDATE attachment_types
SET description = regexp_replace(description, '(^|\s*[,;/]\s*)Spec(?=\s*([,;/]|$))', '', 'gi')
WHERE code = 'technical_specifications'
  AND description ~* '(^|[,;/])\s*Spec\s*([,;/]|$)';

-- 3. The candidate as a new unlabelled parser version ----------------------------------------------------------
INSERT INTO ai_prompt_versions (id, name, version, type, template, variables, config_json, commit_message, created_by)
SELECT gen_random_uuid(), v.name,
       (SELECT max(x.version) + 1 FROM ai_prompt_versions x WHERE x.name = v.name),
       v.type, :'lean_template', v.variables, v.config_json,
       'LEAN-INDEX: v88 with three text edits (documentation/plans/chatbot/lean-index/lean-changelog.md)',
       v.created_by
FROM ai_prompt_versions v
WHERE v.id = '4646e9a2-696e-4461-955e-5722b916b763'
  AND v.name = 'chatbot_semantic_parser'
  AND NOT EXISTS (
    SELECT 1 FROM ai_prompt_versions x WHERE x.name = v.name AND md5(x.template) = md5(:'lean_template')
  );

COMMIT;

-- What the run left (read only).
SELECT o.value AS alias_of, string_agg(k.keyword, ', ' ORDER BY k.keyword) AS alias_words
FROM lookup_sets s
JOIN lookup_options o ON o.set_id = s.id
JOIN lookup_option_keywords k ON k.option_id = o.id
WHERE s.set_key = 'attachment_type_alias'
GROUP BY o.value;

SELECT code, description FROM attachment_types WHERE code = 'technical_specifications';

SELECT v.id, v.version, length(v.template) AS chars,
       EXISTS (SELECT 1 FROM ai_prompt_labels l WHERE l.version_id = v.id) AS labelled
FROM ai_prompt_versions v
WHERE v.name = 'chatbot_semantic_parser' AND md5(v.template) = md5(:'lean_template');
