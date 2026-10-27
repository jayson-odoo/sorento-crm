# CONTRACT: Sales unified (build contract for tests and code)

Plan: `PLAN-sales-unified-27oct.md` (round 2). UAC: `sales-unified-27oct-acceptance-criteria.md`.
Backend paths relative to `sorento_crm_backend/`.

## 1. Schema (one migration `sales_unified_0001`, down_revision `akc_0001_removed_unreferenced`)

- `customers.autocount_debtor_type` varchar(50) NULL. Model attr `Customer.autocount_debtor_type`.
- `companies.sales_agent_source` varchar(10) NOT NULL server_default `'document'`, CHECK
  `sales_agent_source IN ('document','customer')` named `ck_companies_sales_agent_source`.
  Model attr `Company.sales_agent_source`; constants in `app/services/sales/invoiced_sales.py`:
  `AGENT_FROM_DOCUMENT = "document"`, `AGENT_FROM_CUSTOMER = "customer"`.
- `sales.set_apart_customers` (model `app.models.sales.SetApartCustomer`, CompanyScopedMixin,
  audited): `id` uuid pk, `company_id`, `customer_id` FK customers ON DELETE CASCADE NOT NULL,
  `from_month` date NOT NULL (always the 1st), `to_month` date NULL (the 1st; inclusive month),
  `created_at`, `updated_at`; CHECK `to_month IS NULL OR to_month >= from_month`.
- Permission slug `sales.set_apart.edit` (module `sales`), granted to admin and superadmin.

## 2. `app/services/sales/invoiced_sales.py` (the one shared calculation)

SQL expression builders over `BillingDocument` (and, for lines, `BillingDocumentLine`):

- `posted()` -> condition: `status == 'posted'` and type in the four types.
- `signed_amount()` -> `local_net_total`, negated for `credit_note`.
- `signed_line_amount()` -> `net_amount * currency_rate`, negated for credit notes.
- `signed_line_quantity()` -> `quantity`, negated for credit notes.
- `agent_id()` -> the document's `sales_agent_id`, or the customer's `customers.sales_agent_id` when
  the document's company has `sales_agent_source = 'customer'` (correlated on the company row).
- `agent_label()` -> that agent's `sales_agents.sales_agent`; else the document's `agent_code` (as
  sent) on the `document` setting; else NULL (the engine's `(blank)`, labelled `(no agent)`).
- `debtor_type()` -> the customer's `autocount_debtor_type` (NULL when none).
- `SALES_TYPES` = ordered `(value, label)`:
  `("dealer","Dealer"), ("project","Project team"), ("set_apart","Set apart"),
  ("mixed","Mixed sales order types"), ("type_not_set","Sales order type not set"),
  ("no_sales_order","No sales order")`.
- `sales_type()` -> one of the values above, first match wins:
  1. `set_apart` when a `sales.set_apart_customers` row of the document's company and customer has
     `from_month <= date_trunc('month', doc_date) AND (to_month IS NULL OR to_month >= that month)`;
  2. the traced sales orders (section 3): all `retail` -> `dealer`; all `project` -> `project`;
     both present -> `mixed`; traced but every type NULL -> `type_not_set`
     (some NULL plus one known type: the known type);
  3. nothing traced -> `no_sales_order`.
  It NEVER reads `billing_documents.demand_class`, `sales_agents.demand_class` or market segments.
- `sales_type_filter(values)` -> condition; unknown value raises 422 `REPORT_INVALID_PARAMS`.

## 3. The SO chain (DOC-RELATIONS rules, set-based)

A billing document traces to sales order S (same company) when one of its lines:
- has `sales_order_line_id` on a line of S; or
- has `from_doc_type = 'SO'` and `from_doc_no = S.so_number`; or
- has `from_doc_type = 'DO'` and `from_doc_no` = the `order_number` of a live DO (`orders`,
  `deleted_at IS NULL`, `is_cancelled = false`) that delivers S (a DO line with
  `sales_order_line_id` on S, a DO line with `from_doc_no = S.so_number` and `from_doc_type` 'SO'
  or NULL, or the DO header `sales_order_id = S.id`).
A credit or debit note none of whose lines trace inherits the sales orders of its
`against_document_id`.

## 4. Reports (engine definitions, `sales.reports.view`, module `sales`)

- Dataset `billing_documents` gains dimension columns `sales_agent` (label "Sales agent",
  `agent_label()`), `debtor_type` ("Debtor type"), and `channel` now = `SALES_TYPES` label of
  `sales_type()`. Its `channel_condition` = `sales_type_filter`.
- New dataset `billing_document_lines` (key `billing_document_lines`, scope company): dimensions
  `item` (see below), `item_code` (product code, else line item_code), `brand`, `channel`,
  `sales_agent`, `debtor_type`, `year`, `month_of_year`, `year_month`; measures `quantity`
  (`signed_line_quantity`), `sales_value` (`signed_line_amount`), `documents` (count_distinct of
  document id).
- Definition `sales_by_debtor_type` (title "Sales by debtor type"): params `company` (single),
  `channel` (multi, options `SALES_TYPES`, default all six; the blocks: `WorkbookSpec.sheet_per =
  "channel"`), `agent` (multi), `debtor_type` (multi), `period` (default this month); default view
  pivot `rows=sales_agent`, `cols=debtor_type`, `measures=["sales_value"]`; opens on summary;
  `WorkbookSpec(month_sheets=True, report_title="WEEKLY SALES BY DEBTOR TYPE BY SALES AGENT")`.
- Definition `top_selling_items` (title "Top selling items") on `billing_document_lines`: params
  `company`, `channel`, `agent`, `brand`, `debtor_type`, `period` (default year to date), and
  hidden params `customer`, `category` (not in report meta; API callers only); default view pivot
  `rows=item` (dimension "Item" = `item_code || ' - ' || description`, the code alone when no
  description), `cols=year`, measures `quantity`, `sales_value`, `documents`; pivot sort default
  `{"key": "__total__", "dir": "desc"}` (ranked by RM).
- `sales_yearly`: param `basis` default `invoiced`; `channel` options = `SALES_TYPES` (on the order
  bases `dealer`/`project` keep their demand-class meaning, `type_not_set` = demand class NULL,
  the other three match nothing), default all six.

## 5. Sorting (engine extension; every report column sorts server-side)

- `ReportViewDetailConfig.sort: Optional[{"key": str, "dir": "asc"|"desc"}]` orders the detail by
  that catalogue column (then the definition's own order); unknown key -> 422.
- `ReportViewPivotConfig.sort: Optional[{"key": str, "dir": ...}]` orders pivot rows (each block
  separately): `key="__row__"` by the row label, `key="__total__"` by the row total of the first
  measure, any column value (e.g. `"BRAVAT"`) by that cell of the first measure; blank sorts last
  either way; unknown key -> 422.

## 6. Routes

- `GET|POST /api/v1/sales/set-apart-customers`, `PATCH|DELETE /api/v1/sales/set-apart-customers/{id}`:
  read `sales.reports.view`, write `sales.set_apart.edit`; list params `page`, `limit`, `sort`
  (`debtor_code|customer_name|from_month|to_month`), `dir`, `query`; body
  `{customer_id, from_month: "YYYY-MM", to_month: "YYYY-MM"|null}`; response rows
  `{id, customer_id, debtor_code, customer_name, from_month: "YYYY-MM", to_month}`; overlap with
  another row of the same customer -> 422 `set_apart_overlap`; `to_month < from_month` -> 422.
- `GET /api/v1/sales/analysis` (MCP `crm_sales_analysis`): `basis` absent = `invoiced`; `rows` /
  `cols` also accept `agent` (-> `sales_agent`) and `debtor_type` on invoiced only (else 422
  `axis_needs_invoiced`); `channel` accepts the six `SALES_TYPES` values. On invoiced with an axis
  `agent` or `debtor_type` it runs `sales_by_debtor_type`, otherwise `sales_yearly`.
- `GET /api/v1/order-management/top-selling` (MCP `crm_top_selling_report`): `basis` absent =
  `invoiced`; on invoiced the rows come from `engine.run` of `top_selling_items` (rows `item`)
  with `customer_ids`, `category_ids`, `sales_agent_ids`, `brand_ids`, `channel`, `date_from`,
  `date_to` mapped onto its params; `group=category` on invoiced -> 422 `group_needs_order_basis`.
- `PATCH /api/v1/companies/{id}` accepts `sales_agent_source`.
- Customers push: `market_segment_code` also writes `autocount_debtor_type` (upper, trimmed).

## 7. The chatbot's report ask (`crm_report_ask`, `GET /api/v1/order-management/report-ask`)

- New basis `invoiced` in `app.services.reports.ask.CATALOGUE["sales"]`, label `"invoiced sales"`,
  definition `sales_invoiced_ask` built in `app/services/reports/datasets/billing_document_lines.py`
  on the SAME dataset expressions as `top_selling_items` (one copy): dimension keys `customer`,
  `product` (product code, else the line's item code), `brand`, `category`, `sales_agent`
  (`agent_label()`, `(no agent)`), `channel` (sales type label), `month` (`YYYY-MM` of doc_date),
  `all`; measures `amount` (`signed_line_amount`), `qty` (`signed_line_quantity`), `customers`,
  `orders` (distinct billing documents), `products` (count_distinct). Filters `customer`,
  `product`, `brand`, `category`, `sales_agent` (the attributed agent; `none` = no agent),
  `customer_agent`, `channel` (accepts `retail`/`dealer`, `project`, and the six sales type
  values). `location` on invoiced: 422 `location_needs_order_basis`.
- The route's `DEFAULT_BASIS` becomes `invoiced` (a direct API caller naming none).
- Tally: the report-ask invoiced amount for group_by `product` equals the `top_selling_items`
  report's `sales_value` per item for the same company, period and channel (AC-30).
