# LEAN-INDEX: the production data step (owner-run, never run by crew)

The same two DATA changes `explore-data.sql` makes on sorento_explore1020, for the owner to run on production
once the LEAN-INDEX measurements say so. The prompt version is NOT part of this step: a production version is
published by the owner through the Prompts screen or `scripts/publish_parser_template.py`, and no label moves here.

Run each READ first and check its output against the expectation under it. Run the WRITE only when the read
matches. Both writes are guarded, so running one twice changes nothing.

## 1. Photo alias words

What it does: puts "how does it look", "does it look", "how it looks", "look like", "show me" and "see it" on the
photo attachment type as alias words (lookup set `attachment_type_alias`, option value = the type's name). The
chatbot's index lists the photo file type when a message holds one of them (`head/closed_lists_index.file_lines`,
phrases of at most 3 words: "how does it look" is kept for the block-mode Words line, "does it look" is what the
index matches inside it).

READ:

```sql
SELECT code, type_name, description FROM attachment_types WHERE code = 'product_photos';
SELECT s.set_key, s.is_active, o.value, o.is_active AS option_active, k.keyword
FROM lookup_sets s
LEFT JOIN lookup_options o ON o.set_id = s.id
LEFT JOIN lookup_option_keywords k ON k.option_id = o.id
WHERE s.set_key = 'attachment_type_alias'
ORDER BY o.value, k.keyword;
```

Expect: one `product_photos` row (its `type_name` is the option value the write uses). The alias set may be
missing, or present with or without a photo option; the write handles each case. If the photo type has another
code on production, replace `'product_photos'` below with it.

WRITE:

```sql
BEGIN;
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
COMMIT;
```

The same words can be added by hand under System > Lookup Sets > Attachment Type Alias instead.

## 2. "Spec" out of the Technical Specifications description

What it does: removes the "Spec" part from `technical_specifications`' description, keeping the rest of the
text. A description part is a Words entry on the file type's line, and "Spec" there tells the parser that a bare
"spec" is the drawing file.

READ:

```sql
SELECT code, type_name, description,
       regexp_replace(description, '(^|\s*[,;/]\s*)Spec(?=\s*([,;/]|$))', '', 'gi') AS after_write
FROM attachment_types
WHERE code = 'technical_specifications';
```

Expect: `after_write` is the description without its "Spec" part (on the explore copy:
`Technical Specifications / Spec / Drawing by Marketing` -> `Technical Specifications / Drawing by Marketing`).
If `after_write` loses anything else, stop and edit the description by hand on the Attachment Types screen.

WRITE:

```sql
UPDATE attachment_types
SET description = regexp_replace(description, '(^|\s*[,;/]\s*)Spec(?=\s*([,;/]|$))', '', 'gi')
WHERE code = 'technical_specifications'
  AND description ~* '(^|[,;/])\s*Spec\s*([,;/]|$)';
```

## After

The chatbot's prompt variables cache holds for up to 30 seconds (`chatbot_prompt_vars.CACHE_TTL_SECONDS`); the
next turn after that reads the new words.
