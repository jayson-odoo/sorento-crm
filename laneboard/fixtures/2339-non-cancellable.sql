-- PR #2339 NON-CANCELLABLE-ITEMS: hand-test fixture for every step of laneboard/scripts/2339.md.
-- TEST COPY ONLY. Applied by crew (`crew migrate`); revert: laneboard/fixtures/2339-non-cancellable-revert.sql.
-- Needs the lane schema (nc_0001) first. Fake ZZT rows only, under company SRT, fixed ids, every
-- INSERT ON CONFLICT DO NOTHING and every UPDATE touching only fixture rows: re-running changes
-- nothing, and running it over the first version (applied 12 Nov) only adds part 2.
--
-- Part 1 (first version):
--   ZZT-NC-TUB-A  a bathtub product in category ZZT-NC-BATH
--   series "ZZT NC Fixture Series" listing that category, marked Non-cancellable, TUB-A priced
--   project ZZT-NC-PRJ "ZZT Non-cancellable fixture project", proposal ZZT-NC-Q1 (Draft),
--     scope "ZZT House Units", one line ZZT-NC-TUB-A qty 5 (is_non_cancellable = true)
--   project SO ZZT-NC-SO-1, published, line 1 qty 5 consuming that quotation line
-- Part 2 (crew pass R10):
--   ZZT-NC-TAP-B  a basin tap in category ZZT-NC-TAPS, added to the series, NOT marked (step 3)
--   core sales order ZZT-NC-CORE-1 (open, project demand) with one open line, TUB-A qty 5 in
--     warehouse ZZT-NC-WH, linked to ZZT-NC-SO-1 and its line, so the Fulfilment Planning board
--     takes ZZT-NC-SO-1 (Transfer to Cancel SO, step 16)
--   proposal ZZT-NC-Q2, signed (typed "ZZT Fixture Signer") and sent (R1): TUB-A x10 + TAP-B x10,
--     so Download PDF / Excel and the sign link work (step 11)
-- The rows are what the CRM's own services write for the same steps (captured from
-- register_project / create_document / add_scope / upsert_line / sign_as_sorento / issue on a
-- sandbox DB) with the ids fixed and the document numbers replaced by ZZT codes. The owner is an
-- INACTIVE ZZT user (cannot sign in). Prices are made up.
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


-- ---------------------------------------------------------------- part 2 (R10)

INSERT INTO product_categories (id, category_code, category_name, description, parent_category_id, is_active, display_order, class_label, brand_hint, is_searchable, chatbot_max_qty, chatbot_eta_offset_days, created_by, updated_at, company_id) VALUES ('f1c70000-0000-4000-8000-000000000101'::UUID, 'ZZT-NC-TAPS', 'ZZT NC Taps', NULL, NULL::UUID, true, 0, NULL, NULL, true, NULL, NULL, NULL::UUID, NULL, (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO products (id, product_code, product_name, description, remark, category_id, brand_id, item_type_id, item_class_id, variant_of_id, variant_link_manual, alternatives_manual, family_code, family_code_manual, base_uom_id, item_type, barcode, accessory_box_preset_id, price_tag_description, list_price, cost_price, invoice_price, currency, weight, dimensions_length, dimensions_width, dimensions_height, warranty_months, has_serial_tracking, has_batch_tracking, show_so_line_description, reorder_level, reorder_quantity, chatbot_max_qty, chatbot_eta_offset_days, is_active, is_searchable, is_discontinued, exclude_from_planning, discontinued_notified_at, discontinued_notify_batch_id, list_price_notified, list_price_notified_at, list_price_notify_batch_id, created_by, updated_by, updated_at, company_id) VALUES ('f1c70000-0000-4000-8000-000000000102'::UUID, 'ZZT-NC-TAP-B', 'ZZT NC Basin tap', 'Basin tap (fixture, cancellable)', NULL, 'f1c70000-0000-4000-8000-000000000101'::UUID, NULL::UUID, NULL::UUID, NULL::UUID, NULL::UUID, false, false, NULL, false, 'f1c70000-0000-4000-8000-000000000002'::UUID, NULL, NULL, NULL::UUID, NULL, 100.00, NULL, NULL, 'MYR', NULL, NULL, NULL, NULL, NULL, false, false, false, NULL, NULL, NULL, NULL, true, true, false, false, NULL, NULL::UUID, NULL, NULL, NULL::UUID, NULL::UUID, NULL::UUID, NULL, (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO projects.series_categories (series_id, category_id, non_cancellable) VALUES ('f1c70000-0000-4000-8000-000000000005'::UUID, 'f1c70000-0000-4000-8000-000000000101'::UUID, false)
ON CONFLICT DO NOTHING;

insert into projects.series_products (series_id, product_id, selling_price, excluded) values ('f1c70000-0000-4000-8000-000000000005','f1c70000-0000-4000-8000-000000000102',100.00,false)
ON CONFLICT DO NOTHING;

INSERT INTO warehouses (id, warehouse_code, warehouse_name, location, manager_id, is_active, counts_as_available, pool_warehouse_id, segment, fulfilment_planning, updated_at, company_id) VALUES ('f1c70000-0000-4000-8000-000000000103'::UUID, 'ZZT-NC-WH', 'ZZT NC Warehouse', NULL, NULL::UUID, true, true, NULL::UUID, NULL, false, NULL, (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO sales_orders (id, so_number, customer_id, debtor_code, debtor_name, sales_agent_id, order_date, requested_delivery_date, order_type, demand_class, demand_origin, priority, status, source_system, source_ref, source_doc_no, internal_note, project_label, project_label_source, is_transferable, po_ref, po_ref_key, ship_info, doc_type, company_id) VALUES ('f1c70000-0000-4000-8000-000000000104'::UUID, 'ZZT-NC-CORE-1', NULL::UUID, NULL, NULL, NULL::UUID, NULL, NULL, NULL, 'project', NULL, NULL, 'open', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'sales_order', (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, qty_ordered, qty_delivered, qty_cancelled, cancelled_by_cancel_doc, removed_unreferenced, qty_returned, unit_price, line_remark, section_heading, description, discount, line_total, priority, required_date, uom, qty_required, purchasing_status, line_status, cancelled_at, cancelled_by_id, cancel_reason, source_system, source_ref, line_no, company_id) VALUES ('f1c70000-0000-4000-8000-000000000105'::UUID, 'f1c70000-0000-4000-8000-000000000104'::UUID, 'f1c70000-0000-4000-8000-000000000004'::UUID, 'f1c70000-0000-4000-8000-000000000103'::UUID, 5, 0, 0, false, false, 0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-12-15'::date, NULL, NULL, 'not_reviewed', 'open', NULL, NULL, NULL, NULL, NULL, NULL, (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

UPDATE projects.sales_orders SET so_id='f1c70000-0000-4000-8000-000000000104'::UUID, area_group='ZZT TOWER', autocount_doc_no='ZZT-NC-CORE-1', updated_at=now() WHERE projects.sales_orders.id = 'f1c70000-0000-4000-8000-00000000000b'::UUID;

UPDATE projects.sales_order_lines SET core_sales_order_line_id='f1c70000-0000-4000-8000-000000000105'::UUID, unit_price=1950.00, delivery_date='2026-12-15'::date WHERE projects.sales_order_lines.id = 'f1c70000-0000-4000-8000-00000000000c'::UUID;

INSERT INTO projects.quotation_documents (id, project_id, document_no, your_ref, doc_date, recipient_party_id, recipient_name_snapshot, recipient_address_snapshot, recipient_phone_snapshot, recipient_fax_snapshot, recipient_email_snapshot, attn_name, quotation_purpose, payment_terms, validity, payment_term_id, validity_value, validity_unit, subject_title, cover_letter_html, cover_closing_html, terms_html, spec_sheet, signatory_name, signatory_phone, signatory_signature_id, approval_status_id, approval_rejected_reason, approver_user_id, kind, source_issue_id, copied_from_document_id, created_by, company_id) VALUES ('f1c70000-0000-4000-8000-000000000110'::UUID, 'f1c70000-0000-4000-8000-000000000006'::UUID, 'ZZT-NC-Q2', NULL, '2026-11-12'::date, NULL::UUID, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL::UUID, NULL, NULL, 'ZZT Non-cancellable fixture project', NULL, NULL, NULL, NULL::JSONB, NULL, NULL, NULL::UUID, NULL::UUID, NULL, NULL, 'proposal', NULL::UUID, NULL::UUID, 'f1c70000-0000-4000-8000-000000000001', (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

UPDATE projects.quotation_documents SET subject_title='ZZT Non-cancellable fixture project (sent)', updated_at=now() WHERE projects.quotation_documents.id = 'f1c70000-0000-4000-8000-000000000110'::UUID;

INSERT INTO projects.quotations (id, project_id, document_id, sort_order, scope_label, series_id, notes, outcome, loss_reason, decided_at, created_by, company_id) VALUES ('f1c70000-0000-4000-8000-000000000111'::UUID, 'f1c70000-0000-4000-8000-000000000006'::UUID, 'f1c70000-0000-4000-8000-000000000110'::UUID, 0, 'ZZT House Units', 'f1c70000-0000-4000-8000-000000000005'::UUID, NULL, 'open', NULL, NULL, 'f1c70000-0000-4000-8000-000000000001', (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO projects.quotation_versions (id, quotation_id, version_no, frozen_at, issued_by, issued_on, total_amount, matrix_columns, notes, company_id) VALUES ('f1c70000-0000-4000-8000-000000000112'::UUID, 'f1c70000-0000-4000-8000-000000000111'::UUID, 1, NULL, 'f1c70000-0000-4000-8000-000000000001', NULL, 0.00, NULL::JSONB, NULL, (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

INSERT INTO activity_events (id, entity_type, entity_id, kind, body_html, body_text, system_template, system_payload, actor_id) VALUES ('f1c70000-0000-4000-8000-000000000113'::UUID, 'project', 'f1c70000-0000-4000-8000-000000000006', 'system', NULL, NULL, 'quotation_created', '{"quotation_id": "f1c70000-0000-4000-8000-000000000111", "scope_label": "ZZT House Units"}'::JSONB, 'f1c70000-0000-4000-8000-000000000001'::UUID)
ON CONFLICT DO NOTHING;

INSERT INTO projects.quotation_lines (id, version_id, product_id, product_set_id, set_parts_snapshot, product_code_snapshot, description_snapshot, list_price_snapshot, image_attachment_id, drawing_attachment_id, item_label, brand_snapshot, technical_spec, complete_set, band_label, is_section, unit_price, quantity, qty_cells, uom, unit_type, line_total, is_rate_only, is_non_standard, floor_value_applied, floor_level_applied, is_below_floor, is_discounted, is_non_cancellable, sort_order, notes, company_id) VALUES ('f1c70000-0000-4000-8000-000000000114'::UUID, 'f1c70000-0000-4000-8000-000000000112'::UUID, 'f1c70000-0000-4000-8000-000000000004'::UUID, NULL::UUID, NULL::JSONB, 'ZZT-NC-TUB-A', 'Free standing bathtub (non-cancellable fixture)', 1950.00, NULL::UUID, NULL::UUID, NULL, NULL, NULL, NULL, NULL, false, 1950.00, 10, NULL::JSONB, NULL, NULL, 0, false, false, NULL, NULL, false, false, false, 1, NULL, (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

UPDATE projects.quotation_lines SET uom='ZZT-NC-UNIT', line_total=19500.00, updated_at=now() WHERE projects.quotation_lines.id = 'f1c70000-0000-4000-8000-000000000114'::UUID;

UPDATE projects.quotation_lines SET is_non_cancellable=true, updated_at=now() WHERE projects.quotation_lines.id = 'f1c70000-0000-4000-8000-000000000114'::UUID;

UPDATE projects.quotation_lines SET floor_value_applied=1950.00, floor_level_applied='series', updated_at=now() WHERE projects.quotation_lines.id = 'f1c70000-0000-4000-8000-000000000114'::UUID;

UPDATE projects.quotation_versions SET total_amount=19500.00, updated_at=now() WHERE projects.quotation_versions.id = 'f1c70000-0000-4000-8000-000000000112'::UUID;

INSERT INTO projects.quotation_lines (id, version_id, product_id, product_set_id, set_parts_snapshot, product_code_snapshot, description_snapshot, list_price_snapshot, image_attachment_id, drawing_attachment_id, item_label, brand_snapshot, technical_spec, complete_set, band_label, is_section, unit_price, quantity, qty_cells, uom, unit_type, line_total, is_rate_only, is_non_standard, floor_value_applied, floor_level_applied, is_below_floor, is_discounted, is_non_cancellable, sort_order, notes, company_id) VALUES ('f1c70000-0000-4000-8000-000000000115'::UUID, 'f1c70000-0000-4000-8000-000000000112'::UUID, 'f1c70000-0000-4000-8000-000000000102'::UUID, NULL::UUID, NULL::JSONB, 'ZZT-NC-TAP-B', 'Basin tap (fixture, cancellable)', 100.00, NULL::UUID, NULL::UUID, NULL, NULL, NULL, NULL, NULL, false, 100.00, 10, NULL::JSONB, NULL, NULL, 0, false, false, NULL, NULL, false, false, false, 2, NULL, (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

UPDATE projects.quotation_lines SET uom='ZZT-NC-UNIT', line_total=1000.00, updated_at=now() WHERE projects.quotation_lines.id = 'f1c70000-0000-4000-8000-000000000115'::UUID;

UPDATE projects.quotation_lines SET floor_value_applied=100.00, floor_level_applied='series', updated_at=now() WHERE projects.quotation_lines.id = 'f1c70000-0000-4000-8000-000000000115'::UUID;

UPDATE projects.quotation_versions SET total_amount=20500.00, updated_at=now() WHERE projects.quotation_versions.id = 'f1c70000-0000-4000-8000-000000000112'::UUID;

INSERT INTO projects.quotation_signatures (id, owner_kind, user_id, signer_name, mode, image_attachment_id, image_data_uri, signed_at, ip_address, user_agent, gps_lat, gps_lng, company_id) VALUES ('f1c70000-0000-4000-8000-000000000116'::UUID, 'user', 'f1c70000-0000-4000-8000-000000000001', 'ZZT Fixture Signer', 'type', NULL::UUID, 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=', '2026-11-12T06:06:00.633651'::timestamp, NULL, NULL, NULL, NULL, (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

UPDATE projects.quotation_documents SET signatory_signature_id='f1c70000-0000-4000-8000-000000000116'::UUID, updated_at=now() WHERE projects.quotation_documents.id = 'f1c70000-0000-4000-8000-000000000110'::UUID;

INSERT INTO projects.quotation_issues (id, document_id, issue_no, our_ref_text, revision_label, issued_at, issued_by, cover_letter_rendered, terms_rendered, cover_design, cover_closing_rendered, layout_version, payment_terms, validity, grand_total, pdf_attachment_id, xlsx_attachment_id, sorento_signature_id, customer_signature_id, accepted_at, changes_requested_at, changes_requested_note, changes_requested_by_name, signed_pdf_attachment_id, sign_token, sign_token_expires_at, company_id) VALUES ('f1c70000-0000-4000-8000-000000000117'::UUID, 'f1c70000-0000-4000-8000-000000000110'::UUID, 1, 'ZZT-NC-Q2-A', 'A', '2026-11-12T06:06:00.656842'::timestamp, 'f1c70000-0000-4000-8000-000000000001', NULL, NULL, '{"show_letterhead": true, "title": "QUOTATION", "closing_html": "", "sections": [{"style": "fields", "label": "", "columns": 1, "rows": [{"source": "document_no", "label": "Reference No.", "shown": true, "column": 0}, {"source": "date", "label": "Date", "shown": true, "column": 0}, {"source": "attn", "label": "Attn", "shown": true, "column": 0}, {"source": "to_name", "label": "Company", "shown": true, "column": 0}, {"source": "to_tel", "label": "Contact", "shown": true, "column": 0}, {"source": "to_address", "label": "Add", "shown": true, "column": 0}, {"source": "to_email", "label": "Email", "shown": true, "column": 0}, {"source": "terms", "label": "Terms & Conditions", "shown": true, "column": 0}, {"source": "payment_terms", "label": "Payment Terms", "shown": true, "column": 0}, {"source": "validity", "label": "Validity", "shown": true, "column": 0}, {"source": "prepared_by_name", "label": "Prepared By", "shown": true, "column": 0}]}, {"style": "title", "label": "Project Title:", "columns": 1, "rows": [{"source": "project_title", "label": "", "shown": true, "column": 0}]}]}'::JSONB, NULL, 4, NULL, NULL, 0.00, NULL::UUID, NULL::UUID, 'f1c70000-0000-4000-8000-000000000116'::UUID, NULL::UUID, NULL, NULL, NULL, NULL, NULL::UUID, NULL, NULL, (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

UPDATE projects.quotation_issues SET grand_total=20500.00, updated_at=now() WHERE projects.quotation_issues.id = 'f1c70000-0000-4000-8000-000000000117'::UUID;

INSERT INTO projects.quotation_issue_scopes (id, issue_id, quotation_id, version_id, sort_order, scope_total, company_id) VALUES ('f1c70000-0000-4000-8000-000000000118'::UUID, 'f1c70000-0000-4000-8000-000000000117'::UUID, 'f1c70000-0000-4000-8000-000000000111'::UUID, 'f1c70000-0000-4000-8000-000000000112'::UUID, 0, 20500.00, (SELECT id FROM companies WHERE code = 'SRT'))
ON CONFLICT DO NOTHING;

UPDATE projects.quotation_issues SET certificates='[]'::JSONB, updated_at=now() WHERE projects.quotation_issues.id = 'f1c70000-0000-4000-8000-000000000117'::UUID;

COMMIT;
