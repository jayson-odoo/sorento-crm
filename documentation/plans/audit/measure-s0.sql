-- Audit standard S0 (#1281): the measurement gate (plan "Measurement", review B3 at 7a56073f).
--
-- Read-only: temp tables only, nothing in the schema changes. Run with psql against the
-- production copy BEFORE the default-on flip merges:
--
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f documentation/plans/audit/measure-s0.sql
--
-- Section 1 is today's audit_logs volume. Sections 2 to 4 project the volume under
-- default-on: S0 moves the writers from 42 mapped tables (the old __audit_track__ set) to
-- 266 (every mapped table that does not declare __audit_skip__), both lists generated from
-- app.models at this commit. Two estimators, because neither is complete alone:
--   A. pg_stat_user_tables write counters since the last stats reset. Covers every table,
--      but a freshly restored copy has near-zero counters (check days_of_stats), and a
--      touch-only UPDATE (which S0 does not audit) still counts, so it is an upper bound.
--   B. created_at / updated_at over the last 30 days. Real business dates that survive a
--      restore, but only for tables that carry those columns, and a row updated several
--      times counts once, so it is a lower bound for updates.
-- The plan's rule: if the projected daily count exceeds 10x today's, narrow the loudest
-- table with __audit_columns__ or __audit_skip__ before merge; do not revert the default.

\echo '== 1. Today: audit_logs volume =='

SELECT date_trunc('day', changed_at)::date AS day, count(*) AS rows
FROM audit_logs
WHERE changed_at > now() - interval '30 days'
GROUP BY 1 ORDER BY 1;

SELECT count(*) AS total_rows,
       pg_size_pretty(pg_total_relation_size('audit_logs')) AS total_size,
       CASE WHEN count(*) > 0 THEN pg_total_relation_size('audit_logs') / count(*) END AS avg_bytes_per_row,
       round(count(*) FILTER (WHERE changed_at > now() - interval '30 days') / 30.0, 1) AS avg_rows_per_day_30d
FROM audit_logs;

SELECT entity_type, count(*) AS rows_7d, round(count(*) / 7.0, 1) AS rows_per_day
FROM audit_logs
WHERE changed_at > now() - interval '7 days'
GROUP BY 1 ORDER BY 2 DESC LIMIT 20;

\echo '== 2. The audited tables, before S0 (42) and under default-on (266) =='

CREATE TEMP TABLE s0_audited (table_name text PRIMARY KEY, audited_before boolean NOT NULL);
INSERT INTO s0_audited (table_name, audited_before) VALUES
    ('access_agents', false),
    ('agent_field_access', false),
    ('agent_teams', false),
    ('ai_assistant_configs', false),
    ('ai_prompt_labels', false),
    ('ai_prompt_versions', false),
    ('app_module_bundles', false),
    ('app_modules_catalog', false),
    ('approval_tokens', false),
    ('attachment_directories', false),
    ('attachment_field_links', false),
    ('attachment_types', false),
    ('attachments', true),
    ('automations', false),
    ('brands', false),
    ('campaign_types', false),
    ('certificate_products', false),
    ('certificate_revisions', true),
    ('certificates', true),
    ('chatbot_domains', true),
    ('chatbot_entity_kinds', true),
    ('companies', false),
    ('complaint_attachments', false),
    ('complaint_fulfilment_orders', false),
    ('complaint_manual_attachments', false),
    ('complaint_product_lines', false),
    ('complaint_resolutions', false),
    ('complaint_root_causes', false),
    ('complaints', true),
    ('contact_access_types', false),
    ('contact_agent_access', false),
    ('contact_attachment_types', false),
    ('contact_field_reveals', false),
    ('contact_impersonation_sessions', false),
    ('contact_media_limit', false),
    ('contact_portal_form_overrides', false),
    ('conversation_ticket_comments', false),
    ('countries', false),
    ('customer_contacts', false),
    ('customers', true),
    ('dealer_kit.asset', false),
    ('dealer_kit.bundle', false),
    ('dealer_kit.bundle_component', false),
    ('dealer_kit.collection', false),
    ('dealer_kit.edition', false),
    ('dealer_kit.page', false),
    ('dealer_kit.page_label', false),
    ('dealer_kit.page_version', false),
    ('dealer_kit.selection', false),
    ('dealer_kit.selection_line', false),
    ('dealer_kit.tag_size_preset', false),
    ('dealer_kit.tag_template', false),
    ('dealer_kit.tag_template_version', false),
    ('dealer_kit.tile_template', false),
    ('document_numbering_rules', false),
    ('email_event_configs', false),
    ('email_templates', false),
    ('entity_attachment_links', false),
    ('form_fields', false),
    ('form_sections', false),
    ('form_sla_configs', false),
    ('form_submissions', false),
    ('form_versions', false),
    ('forms', true),
    ('impersonation_sessions', false),
    ('import_field_alias', false),
    ('inbound_shipment_lines', false),
    ('inbound_shipments', true),
    ('integration_api_keys', false),
    ('integration_references', false),
    ('integrations', false),
    ('internal_notes', false),
    ('list_query_fields', false),
    ('list_query_resources', false),
    ('lookup_bindings', false),
    ('lookup_option_keywords', false),
    ('lookup_options', false),
    ('lookup_sets', false),
    ('market_segments', false),
    ('marketing_campaigns', false),
    ('mcp_tools', false),
    ('message_snippets', false),
    ('notification_subscriptions', false),
    ('onboarding_people', false),
    ('onboarding_requests', false),
    ('onboarding_templates', false),
    ('order_inquiry_conflicts', false),
    ('order_lines', false),
    ('order_statuses', false),
    ('orders', true),
    ('picking_headers', false),
    ('picking_lines', false),
    ('portal_form_revisions', false),
    ('portal_revision_configs', false),
    ('portal_revision_drafts', false),
    ('portal_tokens', false),
    ('price_tag_request_line_parts', false),
    ('price_tag_request_lines', false),
    ('price_tag_request_tags', false),
    ('price_tag_requests', false),
    ('price_tag_review_comments', false),
    ('product_attachments', false),
    ('product_categories', false),
    ('product_combo_parts', false),
    ('product_combos', true),
    ('product_companion_rule_hosts', false),
    ('product_companion_rules', true),
    ('product_flyer_text', false),
    ('product_set_members', false),
    ('product_set_proposal_batches', false),
    ('product_set_proposals', false),
    ('product_sets', true),
    ('product_spec_exceptions', false),
    ('product_spec_flyer_batches', false),
    ('product_spec_flyer_proposals', false),
    ('product_spec_registry', false),
    ('product_spec_search_policy', false),
    ('product_spec_verifications', false),
    ('product_specifications', false),
    ('product_suppliers', false),
    ('products', true),
    ('projects.allocation_claims', false),
    ('projects.brands', false),
    ('projects.collaborators', false),
    ('projects.customer_item_code_map', false),
    ('projects.delivery_phases', false),
    ('projects.delivery_schedule_cells', false),
    ('projects.delivery_schedule_versions', false),
    ('projects.delivery_schedules', false),
    ('projects.leads', true),
    ('projects.order_change_notices', true),
    ('projects.order_inquiries', false),
    ('projects.order_inquiry_links', false),
    ('projects.order_inquiry_reserve_request_rows', false),
    ('projects.order_inquiry_reserve_requests', false),
    ('projects.order_inquiry_rows', false),
    ('projects.order_inquiry_suggested_links', false),
    ('projects.parties', false),
    ('projects.planning_change_batches', false),
    ('projects.planning_change_rows', false),
    ('projects.po_annotations', false),
    ('projects.po_lines', false),
    ('projects.po_versions', false),
    ('projects.price_floor_rules', true),
    ('projects.projects', true),
    ('projects.purchase_order_lines', false),
    ('projects.purchase_orders', true),
    ('projects.quotation_documents', true),
    ('projects.quotation_issue_scopes', false),
    ('projects.quotation_issues', true),
    ('projects.quotation_lines', true),
    ('projects.quotation_signatures', true),
    ('projects.quotation_templates', true),
    ('projects.quotation_versions', true),
    ('projects.quotations', true),
    ('projects.sales_order_lines', false),
    ('projects.sales_orders', true),
    ('projects.sales_profile', false),
    ('projects.samples', true),
    ('projects.series', false),
    ('projects.series_categories', false),
    ('projects.series_products', false),
    ('projects.so_amendments', false),
    ('projects.so_divergence_lines', false),
    ('projects.so_divergences', false),
    ('projects.so_draft_findings', false),
    ('projects.so_line_allocations', false),
    ('projects.so_supply_decision_drafts', false),
    ('projects.so_supply_decisions', true),
    ('projects.stakeholders', false),
    ('projects.stock_transfers', true),
    ('projects.takeover_requests', false),
    ('projects.tasks', true),
    ('projects.template_roles', false),
    ('projects.template_tasks', false),
    ('projects.templates', false),
    ('projects.types', false),
    ('promotion_attachments', false),
    ('promotion_groups', false),
    ('promotion_products', false),
    ('promotion_types', true),
    ('promotions', true),
    ('public_holidays', false),
    ('purchase_order_lines', false),
    ('purchase_orders', false),
    ('purchase_request_lines', false),
    ('purchase_requests', true),
    ('push_subscriptions', false),
    ('respond_channels', false),
    ('respond_contact_companies', false),
    ('respond_contact_cs_routing', false),
    ('respond_contact_customers', false),
    ('respond_contacts', false),
    ('respond_message_templates', false),
    ('respond_template_defaults', false),
    ('respond_workspaces', false),
    ('sales.team_members', true),
    ('sales.teams', true),
    ('sales_agents', false),
    ('sales_order_lines', false),
    ('sales_orders', false),
    ('scheduled_tasks', false),
    ('scm.abc_xyz_policy', false),
    ('scm.cash_ranking_policy', false),
    ('scm.container_size', false),
    ('scm.currency_rate', false),
    ('scm.demand_nature_map', false),
    ('scm.loading_plan', false),
    ('scm.loading_plan_line', false),
    ('scm.market_research_topic', false),
    ('scm.order_link_claim', false),
    ('scm.override_reason', false),
    ('scm.plan_row_decision', false),
    ('scm.priority_policy', false),
    ('scm.proforma_invoice', false),
    ('scm.proforma_invoice_line', false),
    ('scm.proforma_invoice_packing_line', false),
    ('scm.proforma_invoice_shipment_link', false),
    ('scm.purchasing_budget', false),
    ('scm.reason_action_map', false),
    ('scm.recommendation_override', false),
    ('scm.reorder_level', false),
    ('scm.reorder_policy', false),
    ('scm.shipment_line_spo_link', false),
    ('scm.supplier_inventory', false),
    ('scm.supplier_product_code_alias', false),
    ('scm.supplier_scoring_policy', false),
    ('sla_policies', false),
    ('sla_policy_tiers', false),
    ('sla_takeover_requests', false),
    ('spec_visibility_policies', true),
    ('spo_allocations', false),
    ('status_transitions', false),
    ('statuses', false),
    ('stock', false),
    ('stock_batches', false),
    ('stock_inquiries', true),
    ('stock_visibility_policies', true),
    ('storage_zones', false),
    ('supplier_notice_lines', false),
    ('supplier_notices', false),
    ('suppliers', true),
    ('system_settings', false),
    ('team_members', false),
    ('teams', false),
    ('tenant_modules', false),
    ('ticket_respond_contact_links', false),
    ('ticket_watchers', false),
    ('tickets', true),
    ('transporters', false),
    ('units_of_measure', false),
    ('user_companies', false),
    ('user_permissions', false),
    ('user_product_discontinued_scopes', false),
    ('user_role_assignments', false),
    ('user_role_permissions', false),
    ('user_roles', false),
    ('users', true),
    ('view_tokens', false),
    ('warehouses', false),
    ('work_calendar_configs', false),
    ('workflow_form_definitions', false),
    ('workflow_form_versions', false),
    ('workflow_submission_lines', false),
    ('workflow_submission_transition_logs', false),
    ('workflow_submissions', false);

SELECT count(*) FILTER (WHERE audited_before) AS tables_before,
       count(*) AS tables_default_on,
       count(*) FILTER (WHERE to_regclass(table_name) IS NULL) AS missing_in_this_db
FROM s0_audited;

\echo '== 3A. Projection from pg_stat_user_tables (upper bound) =='

CREATE TEMP TABLE s0_stat AS
SELECT a.table_name,
       a.audited_before,
       coalesce(s.n_tup_ins, 0) AS ins,
       coalesce(s.n_tup_upd, 0) AS upd,
       coalesce(s.n_tup_del, 0) AS del,
       greatest(extract(epoch FROM now() - coalesce(
           (SELECT stats_reset FROM pg_stat_database WHERE datname = current_database()),
           pg_postmaster_start_time())) / 86400.0, 1.0 / 24) AS days_of_stats
FROM s0_audited a
LEFT JOIN pg_stat_user_tables s ON s.relid = to_regclass(a.table_name);

SELECT round(max(days_of_stats)::numeric, 2) AS days_of_stats,
       round(sum((ins + upd + del) / days_of_stats) FILTER (WHERE audited_before)::numeric, 1) AS writes_per_day_before,
       round(sum((ins + upd + del) / days_of_stats)::numeric, 1) AS writes_per_day_default_on,
       round((sum((ins + upd + del) / days_of_stats)
             / nullif(sum((ins + upd + del) / days_of_stats) FILTER (WHERE audited_before), 0))::numeric, 1) AS multiplier
FROM s0_stat;

SELECT table_name, audited_before, ins, upd, del,
       round(((ins + upd + del) / days_of_stats)::numeric, 1) AS writes_per_day
FROM s0_stat
ORDER BY (ins + upd + del) DESC LIMIT 25;

\echo '== 3B. Projection from created_at / updated_at, last 30 days (lower bound) =='

CREATE TEMP TABLE s0_dated (table_name text, audited_before boolean, created_30d bigint, updated_30d bigint);

DO $$
DECLARE
    r record;
    has_created boolean;
    has_updated boolean;
    c bigint;
    u bigint;
BEGIN
    FOR r IN SELECT table_name, audited_before FROM s0_audited WHERE to_regclass(table_name) IS NOT NULL LOOP
        SELECT coalesce(bool_or(attname = 'created_at'), false), coalesce(bool_or(attname = 'updated_at'), false)
          INTO has_created, has_updated
          FROM pg_attribute
         WHERE attrelid = to_regclass(r.table_name) AND attnum > 0 AND NOT attisdropped;
        c := NULL;
        u := NULL;
        IF has_created THEN
            EXECUTE format('SELECT count(*) FROM %s WHERE created_at > now() - interval ''30 days''', r.table_name) INTO c;
        END IF;
        IF has_updated AND has_created THEN
            EXECUTE format('SELECT count(*) FROM %s WHERE updated_at > now() - interval ''30 days'' '
                           'AND updated_at > created_at + interval ''1 second''', r.table_name) INTO u;
        ELSIF has_updated THEN
            EXECUTE format('SELECT count(*) FROM %s WHERE updated_at > now() - interval ''30 days''', r.table_name) INTO u;
        END IF;
        INSERT INTO s0_dated VALUES (r.table_name, r.audited_before, c, u);
    END LOOP;
END
$$;

SELECT count(*) FILTER (WHERE created_30d IS NOT NULL OR updated_30d IS NOT NULL) AS tables_with_dates,
       count(*) FILTER (WHERE created_30d IS NULL AND updated_30d IS NULL) AS tables_without_dates,
       round(sum(coalesce(created_30d, 0) + coalesce(updated_30d, 0)) FILTER (WHERE audited_before) / 30.0, 1) AS rows_per_day_before,
       round(sum(coalesce(created_30d, 0) + coalesce(updated_30d, 0)) / 30.0, 1) AS rows_per_day_default_on
FROM s0_dated;

SELECT table_name, audited_before, created_30d, updated_30d,
       round((coalesce(created_30d, 0) + coalesce(updated_30d, 0)) / 30.0, 1) AS rows_per_day
FROM s0_dated
ORDER BY coalesce(created_30d, 0) + coalesce(updated_30d, 0) DESC LIMIT 25;

\echo '== 4. The gate: projected daily rows against 10x today =='

WITH today AS (
    SELECT count(*) / 30.0 AS per_day FROM audit_logs WHERE changed_at > now() - interval '30 days'
), a AS (
    SELECT sum((ins + upd + del) / days_of_stats) AS all_on,
           sum((ins + upd + del) / days_of_stats) FILTER (WHERE audited_before) AS before
      FROM s0_stat
), b AS (
    SELECT sum(coalesce(created_30d, 0) + coalesce(updated_30d, 0)) / 30.0 AS all_on,
           sum(coalesce(created_30d, 0) + coalesce(updated_30d, 0)) FILTER (WHERE audited_before) / 30.0 AS before
      FROM s0_dated
)
SELECT round(today.per_day, 1) AS today_rows_per_day,
       -- today's rows scaled by the writer growth each estimator measures
       round((today.per_day * a.all_on / nullif(a.before, 0))::numeric, 1) AS projected_per_day_stat,
       round((today.per_day * b.all_on / nullif(b.before, 0))::numeric, 1) AS projected_per_day_dated,
       round((a.all_on / nullif(a.before, 0))::numeric, 1) AS multiplier_stat,
       round((b.all_on / nullif(b.before, 0))::numeric, 1) AS multiplier_dated,
       CASE WHEN greatest(a.all_on / nullif(a.before, 0), b.all_on / nullif(b.before, 0)) > 10
            THEN 'NARROW BEFORE MERGE' ELSE 'within 10x' END AS verdict
FROM today, a, b;
