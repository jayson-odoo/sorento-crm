-- MCP-REGISTRY-IMAGE: what the first working mcp_tools sync will do on production.
-- READ-ONLY. For the owner to run on production (or a fresh prod copy), e.g.:
--   PGOPTIONS='-c default_transaction_read_only=on' psql "$PROD_URL" -f mcp-registry-image-first-sync-prod.sql
-- The catalog list below is sorento_crm_mcp/sorento_crm_mcp/catalog.py CATALOG (55 tools) as this
-- PR ships it. sync_catalog never deletes rows; DEACTIVATE rows vanish from System Management >
-- MCP Tools and the chatbot domain tool picker, nothing else reads is_active.

-- 1. Per-tool effect.
WITH catalog(tool_name) AS (VALUES
  ('crm_certificates_list'),
  ('crm_complaint_analytics'),
  ('crm_complaint_close'),
  ('crm_complaints_list'),
  ('crm_find'),
  ('crm_forms_management_forms_list'),
  ('crm_ideation_turn'),
  ('crm_incoming_stock_by_product'),
  ('crm_incoming_stock_list'),
  ('crm_incoming_stock_shipments'),
  ('crm_inventory_stock_balance_list'),
  ('crm_inventory_warehouses_list'),
  ('crm_it_support_ticket_create'),
  ('crm_lookup_resolve'),
  ('crm_low_stock_report'),
  ('crm_marketing_promotion_attachments_list'),
  ('crm_marketing_promotion_products_list'),
  ('crm_marketing_promotions_list'),
  ('crm_master_brands_list'),
  ('crm_master_customers_list'),
  ('crm_master_product_attachments_list'),
  ('crm_master_product_categories_list'),
  ('crm_master_products_list'),
  ('crm_master_units_of_measure_list'),
  ('crm_order_analytics'),
  ('crm_order_cancel'),
  ('crm_order_management_orders_by_product_list'),
  ('crm_order_management_orders_list'),
  ('crm_outstanding_report'),
  ('crm_portal_link_get'),
  ('crm_procurement_grn_summary'),
  ('crm_procurement_po_last_cost_list'),
  ('crm_procurement_po_placed_list'),
  ('crm_procurement_spo_allocations_last_receipt_list'),
  ('crm_project_detail'),
  ('crm_project_forecast'),
  ('crm_project_quotations_list'),
  ('crm_projects_list'),
  ('crm_purchase_request_approve'),
  ('crm_purchase_request_by_number'),
  ('crm_purchase_request_reject'),
  ('crm_report_ask'),
  ('crm_resource_attachments_catalogue'),
  ('crm_resource_attachments_current_stock_list'),
  ('crm_resource_attachments_list'),
  ('crm_sales_analysis'),
  ('crm_sales_opportunity_customer_options'),
  ('crm_sales_opportunity_log'),
  ('crm_sales_report'),
  ('crm_sales_target_progress'),
  ('crm_sla_conversation_event_logs_list'),
  ('crm_sla_conversation_tracking_dashboard'),
  ('crm_sla_conversation_tracking_list'),
  ('crm_system_tool_capabilities_summary'),
  ('user_guides_read')
)
SELECT 'ADD' AS effect, c.tool_name FROM catalog c LEFT JOIN mcp_tools t USING (tool_name) WHERE t.id IS NULL
UNION ALL
SELECT 'REACTIVATE', t.tool_name FROM mcp_tools t JOIN catalog c USING (tool_name) WHERE NOT t.is_active
UNION ALL
SELECT 'DEACTIVATE', t.tool_name FROM mcp_tools t LEFT JOIN catalog c USING (tool_name) WHERE c.tool_name IS NULL AND t.is_active
ORDER BY 1, 2;

-- 2. Table as it stands (how stale, how big).
SELECT count(*) AS total_rows, count(*) FILTER (WHERE is_active) AS active_rows,
       min(created_at) AS first_created, max(last_seen_at) AS last_synced
FROM mcp_tools;
