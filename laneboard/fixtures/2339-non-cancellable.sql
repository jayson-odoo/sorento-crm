-- PR #2339 NON-CANCELLABLE-ITEMS: hand-test fixture for the override block. TEST COPY ONLY.
-- Applied by crew (`crew migrate`); revert: laneboard/fixtures/2339-non-cancellable-revert.sql.
--
-- Builds, all ZZT-prefixed and under company SRT, with fixed ids so it is idempotent:
--   ZZT-NC-TUB-A  a bathtub product in category ZZT-NC-BATH
--   series "ZZT NC Fixture Series" listing that category, marked Non-cancellable, TUB-A priced
--   project ZZT-NC-PRJ "ZZT Non-cancellable fixture project", proposal ZZT-NC-Q1 (Draft),
--     scope "ZZT House Units", one line ZZT-NC-TUB-A qty 5 (is_non_cancellable = true)
--   project SO ZZT-NC-SO-1, published, line 1 qty 5 consuming that quotation line
-- The rows are what the CRM's own services write for the same steps (captured from
-- register_project / create_document / add_scope / upsert_line on a sandbox DB), minus the
-- document-number bump: the codes are fixed instead. Owner is an INACTIVE ZZT user (cannot sign in).
-- Every INSERT is ON CONFLICT DO NOTHING; re-running changes nothing.
BEGIN;

INSERT INTO users (id, email, name, status, is_trashed, is_protected, respond_synced,
                   daily_sla_summary_subscribed)
VALUES ('f1c70000-0000-4000-8000-000000000001', 'zzt-nc-fixture@sorento-sandbox.com',
        'ZZT Non-cancellable fixture', 'INACTIVE', false, false, 'pending', false)
ON CONFLICT DO NOTHING;

INSERT INTO units_of_measure (id, uom_code, uom_name, decimal_places, is_active, company_id)
VALUES ('f1c70000-0000-4000-8000-000000000002', 'ZZT-NC-UNIT', 'Unit', 0, true,
        (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO product_categories (id, category_code, category_name, is_active, display_order,
                                is_searchable, company_id)
VALUES ('f1c70000-0000-4000-8000-000000000003', 'ZZT-NC-BATH', 'ZZT NC Bathtubs', true, 0, true,
        (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO products (id, product_code, product_name, description, category_id, base_uom_id,
                      list_price, currency, variant_link_manual, alternatives_manual,
                      family_code_manual, has_serial_tracking, has_batch_tracking,
                      show_so_line_description, is_active, is_searchable, is_discontinued,
                      exclude_from_planning, company_id)
VALUES ('f1c70000-0000-4000-8000-000000000004', 'ZZT-NC-TUB-A', 'ZZT NC Freestanding bathtub',
        'Free standing bathtub (non-cancellable fixture)', 'f1c70000-0000-4000-8000-000000000003',
        'f1c70000-0000-4000-8000-000000000002', 1950.00, 'MYR', false, false, false, false, false,
        false, true, true, false, true, (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO projects.series (id, name, is_active, company_id)
VALUES ('f1c70000-0000-4000-8000-000000000005', 'ZZT NC Fixture Series', true,
        (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO projects.series_categories (series_id, category_id, non_cancellable)
VALUES ('f1c70000-0000-4000-8000-000000000005', 'f1c70000-0000-4000-8000-000000000003', true)
ON CONFLICT DO NOTHING;

INSERT INTO projects.series_products (series_id, product_id, selling_price, excluded)
VALUES ('f1c70000-0000-4000-8000-000000000005', 'f1c70000-0000-4000-8000-000000000004', 1950.00,
        false)
ON CONFLICT DO NOTHING;

INSERT INTO projects.projects (id, project_code, title, normalised_title, status_id, outcome,
                               owner_user_id, is_critical, stale_level, created_by, company_id)
VALUES ('f1c70000-0000-4000-8000-000000000006', 'ZZT-NC-PRJ',
        'ZZT Non-cancellable fixture project', 'zzt non-cancellable fixture project',
        (SELECT id FROM statuses WHERE entity_type = 'project' AND is_initial AND is_active
          ORDER BY scope_id NULLS FIRST, sort_order LIMIT 1),
        'open', 'f1c70000-0000-4000-8000-000000000001', false, 0,
        'f1c70000-0000-4000-8000-000000000001', (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO projects.quotation_documents (id, project_id, document_no, doc_date, subject_title,
                                          kind, created_by, company_id)
VALUES ('f1c70000-0000-4000-8000-000000000007', 'f1c70000-0000-4000-8000-000000000006',
        'ZZT-NC-Q1', '2026-11-12', 'ZZT Non-cancellable fixture project', 'proposal',
        'f1c70000-0000-4000-8000-000000000001', (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO projects.quotations (id, project_id, document_id, sort_order, scope_label, series_id,
                                 outcome, created_by, company_id)
VALUES ('f1c70000-0000-4000-8000-000000000008', 'f1c70000-0000-4000-8000-000000000006',
        'f1c70000-0000-4000-8000-000000000007', 0, 'ZZT House Units',
        'f1c70000-0000-4000-8000-000000000005', 'open', 'f1c70000-0000-4000-8000-000000000001',
        (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO projects.quotation_versions (id, quotation_id, version_no, issued_by, total_amount,
                                         company_id)
VALUES ('f1c70000-0000-4000-8000-000000000009', 'f1c70000-0000-4000-8000-000000000008', 1,
        'f1c70000-0000-4000-8000-000000000001', 9750.00,
        (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO projects.quotation_lines (id, version_id, product_id, product_code_snapshot,
                                      description_snapshot, list_price_snapshot, is_section,
                                      unit_price, quantity, uom, line_total, is_rate_only,
                                      is_non_standard, is_below_floor, is_discounted,
                                      is_non_cancellable, sort_order, company_id)
VALUES ('f1c70000-0000-4000-8000-00000000000a', 'f1c70000-0000-4000-8000-000000000009',
        'f1c70000-0000-4000-8000-000000000004', 'ZZT-NC-TUB-A',
        'Free standing bathtub (non-cancellable fixture)', 1950.00, false, 1950.00, 5,
        'ZZT-NC-UNIT', 9750.00, false, false, false, false, true, 0,
        (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO projects.sales_orders (id, project_id, provisional_ref, status, is_pre_order,
                                   is_sponsorship, published_by, published_at, company_id)
VALUES ('f1c70000-0000-4000-8000-00000000000b', 'f1c70000-0000-4000-8000-000000000006',
        'ZZT-NC-SO-1', 'published', false, false, 'f1c70000-0000-4000-8000-000000000001',
        '2026-11-12 09:00:00', (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO projects.sales_order_lines (id, project_sales_order_id, line_no, product_id,
                                        description, qty, uom, quotation_line_id, company_id)
VALUES ('f1c70000-0000-4000-8000-00000000000c', 'f1c70000-0000-4000-8000-00000000000b', 1,
        'f1c70000-0000-4000-8000-000000000004',
        'Free standing bathtub (non-cancellable fixture)', 5, 'ZZT-NC-UNIT',
        'f1c70000-0000-4000-8000-00000000000a', (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

COMMIT;
