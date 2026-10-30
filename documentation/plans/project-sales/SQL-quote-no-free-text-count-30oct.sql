-- QUOTE-NO-FREE-TEXT (30 Oct 2026): READ-ONLY counts of off-catalogue ("free text") project
-- quotation lines, for the OWNER to run on production. Crew lanes never read production.
-- No personal data: quote numbers, version numbers, outcome and dates only.
-- Run with: PGOPTIONS='-c default_transaction_read_only=on' psql "$PROD_URL" -f this-file

-- 1. Totals: every line vs lines with neither a product nor a product set.
select count(*) as total_lines,
       count(*) filter (where l.product_id is null and l.product_set_id is null) as free_text_lines,
       count(*) filter (where l.product_id is null and l.product_set_id is null
                        and l.product_code_snapshot is not null) as free_text_with_code_snapshot
from projects.quotation_lines l;

-- 2. Free-text lines by quotation outcome and month created.
select q.outcome, date_trunc('month', l.created_at)::date as month, count(*) as free_text_lines
from projects.quotation_lines l
join projects.quotation_versions v on v.id = l.version_id
join projects.quotations q on q.id = v.quotation_id
where l.product_id is null and l.product_set_id is null
group by 1, 2 order by 2, 1;

-- 3. Which quotes carry them (latest version only), and whether that version was issued.
select d.document_no, q.scope_label, v.version_no, q.outcome,
       (v.frozen_at is not null) as superseded,
       count(*) as free_text_lines
from projects.quotation_lines l
join projects.quotation_versions v on v.id = l.version_id
join projects.quotations q on q.id = v.quotation_id
left join projects.quotation_documents d on d.id = q.document_id
where l.product_id is null and l.product_set_id is null
group by 1, 2, 3, 4, 5 order by 1, 3;
