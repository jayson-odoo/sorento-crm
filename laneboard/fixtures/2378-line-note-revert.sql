-- Reverts 2378-line-note.sql: clears the two fixture line notes on ZZT-NC-Q2.
UPDATE projects.quotation_lines
   SET notes = NULL, updated_at = (now() AT TIME ZONE 'UTC')
 WHERE id IN ('f1c70000-0000-4000-8000-000000000114'::UUID,
              'f1c70000-0000-4000-8000-000000000115'::UUID);
