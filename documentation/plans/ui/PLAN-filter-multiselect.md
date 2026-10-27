# PLAN: every dropdown filter is multi-select (FILTER-MULTISELECT)

Status: Review. Scan done (27 Oct); owner answered the card (28 Oct, section 0). PR1 #1930
(Contacts Company filter + Companies column) merge-ready. PR2 #1928 (contacts, users, permissions,
onboarding, SLA, system logs / outboxes / chatbot / ideas: ~40 filters on 27 screens) built
red-first in 5 batches, reviewer READY with kill tests per batch, review round green at 3b3da207,
browser pass 7 of 8 screens (Ideas blocked by the copy's ideation 502; vitest covers it). PR3 #1937
(sales / orders / customers / complaints / tickets / marketing) building; PR4 and PR5 red tests
written. Track: full lane, stacked PRs (diff well over 300 lines; no migration, no auth change).

Owner standing rule (27 Oct 2026): "do a scan through the filter in our system, all dropdown
filter should be able to multi select". Same family as "every grid column sortable server-side".

## 0. Owner answers (28 Oct ~00:20 MYT)

- Q1 (a): the five broken filters (Stock batches Status, Customers Status, Permissions Role, Order
  statuses Final, Divergences "Any") are fixed in the PR that touches them.
- Q2 (b): the report Company filter stays single (one company per run).
- Q3 (a): two-value filters (Region on Contacts and Packing lists, Chat history Direction) become
  multi too.
- Q4 (a): the Advanced filter dialog gets real multi-select pick lists, as the lane's last PR (with
  the import-jobs / import-logs text boxes turned into dropdowns).
- Q5 (a): stacked PRs by area, shared parts first (#1930 first).

## 1. The rule (behaviour card)

- Every **enum or lookup dropdown filter** on a list, grid, board or report takes several values.
  Values are **OR-ed within a filter** and **AND-ed across filters** (Status: Draft, Submitted AND
  Agent: A = rows that are (Draft or Submitted) and belong to A).
- **Does not change:** free-text search, date / date-range / period pickers, numeric ranges and
  thresholds, Group-by and "Count by" view pickers, and scope selectors that pick WHICH set to read
  rather than filtering values (Stock claims Direction, Stock debt Book, SPO / Order-inquiry
  Outstanding / Completed / All toggles, the advanced dialog's Match all / any).
- **Yes / no filters stay single** (Yes / No / Any). Ticking both Yes and No is the same as no
  filter, so a multi-select adds a click and nothing else. Mutually exclusive enums stay single too
  (Contacts Tag settings Matches / Differs, Saved / All).
- **Chip with several values:** one chip per filter, first two names then a count:
  `Status: Draft, Submitted +2`. Clearing the chip clears the whole filter. The Filters badge counts
  filters, not values.
- **Pseudo-values combine like any other value:** `Assigned to: Unassigned, A` = unassigned OR A.
- **URL / saved views stay backward compatible:** the value rides one param comma-joined
  (`status=draft,submitted`); the backend reads comma-joined, repeated and single values alike
  (`app/utils/multi_value.py`). An old link or saved view holding one value reads as a one-value
  filter, so no saved-view version bump and no data migration.
- **Options always come from a list**, never typed text (import-jobs / import-logs Type and Status
  and the workflow submission State code are text boxes today; they become dropdowns).

## 2. Shared parts (built once, PR1)

- BE: `sorento_crm_backend/app/utils/multi_value.py` `multi_values(raw)` / `multi_uuids(raw, label)`.
  Declare the param `Optional[list[str]] = Query(None)` and pass it through; replaces the ~30
  hand-rolled `split(",")` parsers in `app/api/v1/**` as each screen is wired.
- FE: `sorento_crm_frontend/lib/list-filters/multiValue.ts` `splitMulti` / `joinMulti` /
  `multiValueSummary` / `multiChipLabel`. Controls are `SearchableMultiSelect`
  (`components/common/SearchableMultiSelect.tsx`), already the house multi control.
- `buildDataGridParams` (`lib/api-client.ts:216`) already passes a comma-joined string through; no
  change needed there.

## 3. Inventory (scan of 27 Oct)

Counts: **211 dropdown filters** (yes/no excluded) on about 120 screens. **36 already multi.**
**175 to change**: about 35 FE-only (backend already takes a list and filters with IN, or the filter
is client-side), about 140 FE+BE.

Found while scanning, broken today regardless of multi-select (fix in the PR that touches them):
- Stock batches Status: FE sends `status`, `api/v1/inventory/stock_batches.py:16-27` ignores it.
- Customers Status: `api/v1/order_management/customers.py:24-31` has no `status` param.
- Permissions Role: `api/v1/user_management/permissions.py:31-41` has no `roleId` param.
- Order statuses Final: filters the loaded page only (`OrderStatusesList.tsx:55-60`).
- Divergences "Any": backend defaults `status="open"` (`api/v1/projects/divergences.py:153`).
- Promotions: an advanced filter drops `attachment_state` (`usePromotions.ts:68-80`).
- Escalation logs Assigned to (found in PR2 review, 28 Oct): the screen sent Respond ids as
  `assigned_to`, a column that stores a display name (`sla_service.py:642-668`), so it matched
  nothing; PR2 sends `users.id` as `assigned_to_id`.
- Advanced filter dialog: enum / uuid values are free text, ids typed by hand
  (`ListQueryFilterDialog.tsx:329`); `option_source` always None (`api/v1/list_query.py:161-164`).

Legend: Today S = single, M = multi, C = client-side only. Change: FE, BE, FE+BE, none.
FE paths under `sorento_crm_frontend/app/(protected)/`, BE under `sorento_crm_backend/app/`.
"URL" = written into the row link and restored on Back by `useListStateFromUrl`; "view" = per-user
listing preferences or saved view.

### 3.1 Contacts, users, SLA, system

| Screen | Filter | Today | FE control | Param -> BE (type, SQL) | Persisted | Change |
|---|---|---|---|---|---|---|
| Contacts | Access type | S | contacts/components/ContactAccessFilters.tsx:109 | `access_type` -> api/v1/user_management/contacts.py:103 str; contact_service EXISTS `==` | URL | FE+BE |
| Contacts | Tier | S | ContactAccessFilters.tsx:119 | `tier` -> contacts.py:104 Literal; `==` | URL | FE+BE |
| Contacts | Customer | S | ContactAccessFilters.tsx:189 | `customer_id` -> contacts.py:111 UUID; EXISTS `==` | URL | FE+BE |
| Contacts | Company (new, PR1) | M | ContactFiltersPopover.tsx | `company` -> contacts.py list; EXISTS `IN` | URL | done |
| Contacts | Tag | M | ContactTagFilters.tsx:25 | `tag` repeated -> contacts.py:113 list[UUID]; `IN` | URL | none |
| Contacts | Region (west/east) | S | ContactAccessFilters.tsx:179 | `region` -> contacts.py:110 Literal; contains | URL | FE+BE (two values) |
| Contacts | Cost / AI replies / Escalation / Packing list / Stock checks | yes/no | ContactAccessFilters.tsx:129-169 | `cost` `ai` `escalation` `packing_list` `stock` | URL | none |
| Contacts | Tag settings, Access differs from | S | ContactTagFilters.tsx:35, ContactAccessFilters.tsx:202 | exclusive / one source contact | URL | none |
| Users | Role | S (extra rows: last wins) | user-management/users/components/user-list.tsx:254 | `roleId` -> api/v1/user_management/users.py:62; `==` | URL | FE+BE |
| Users | Status | S | user-list.tsx:268 | `status` -> users.py:61; `==` | URL | FE+BE |
| Permissions | Role | S, no-op | permissions/components/permission-list.tsx:375 | `roleId` -> permissions.py:31-41 not declared | none | FE+BE (build filter) |
| Onboarding requests | Status | S | onboarding-requests/components/OnboardingRequestList.tsx:327 | `status_key` -> onboarding.py:141; `==` | URL | FE+BE |
| Conversation SLA | Assignee | S | conversation-sla-tracking/components/ConversationSLATrackingList.tsx:587 | `assigned_to` -> sla/sla_tracking.py:865; `==` | URL | FE+BE |
| Conversation SLA detail | Event type, Assigned to | S | EventLogTable.tsx:359, :402 | `event_type`, `assigned_to_id` -> sla_tracking.py:2196-2198; `==` | none | FE+BE |
| Escalation logs | Event type, Assigned to | S | escalation-logs/components/EventLogList.tsx:174, :187 | same route; `==` | none | FE+BE |
| Team pending | Assignee, Team | S | team-pending/components/TeamPendingList.tsx:294, :309 | `assignee`, `team` -> sla_tracking.py:494-495 | none | FE+BE |
| Audit logs | Entity type, Action, User | S | system-management/audit-logs/components/AuditLogsList.tsx:361, :374, :391 | audit/audit_logs.py:258-261; `==` | none | FE+BE |
| Activity | Entity type | M | ActivityTimeline.tsx:215 | repeated -> audit/activity.py:22; `IN` | none | none |
| Activity | Action, User | S | ActivityTimeline.tsx:236, :249 | activity.py:28, :31 | none | FE+BE |
| Chat history | Direction (2 values) | S | system-management/chat-history/page.tsx:342 | `direction` -> system/chat_history.py:50 | none | FE+BE (two values) |
| Chatbot domains | Team | C | chatbot-domains/components/ChatbotDomainsList.tsx:250 | client-side | none | FE |
| Chatbot status words | Domain | C | ChatbotStatusWordsList.tsx:164 | client-side | none | FE |
| Email outbox | Status | S | email-outbox/components/EmailOutboxList.tsx:316 | system/email_outbox.py:67; `==` | none | FE+BE |
| Outgoing mails | Status | S | OutgoingMailsList.tsx:244 | system/outgoing_mails.py:23; `==` | none | FE+BE |
| Respond outbox | Status | S | RespondOutboxList.tsx:232 | system/respond_outbox.py:92; `==` | none | FE+BE |
| Import jobs | Type, Status | text box | import-jobs/components/ImportJobsList.tsx:325, :330 | system/jobs.py:27-28; `==` | none | FE+BE (dropdown first) |
| Import job rows | Outcome, Code | S | ImportJobRowsCard.tsx:277, :295 | jobs.py:236-237; `==` | none | FE+BE |
| Import logs | Entity type | text box | ImportLogsList.tsx:218 | system/import_logs.py:19; `==` | none | FE+BE (dropdown first) |
| Integration logs | Status, Channel, Table | S | integration-logs/components/IntegrationLogsList.tsx:373, :386, :401 | integrations/logs.py:24-26; `==` | URL | FE+BE |
| Smart linkage | Status, Channel | S | resource-management/smart-linkage/components/SmartLinkageList.tsx:218, :234 | integrations/logs.py:24-25; `==` | none | FE+BE |
| WhatsApp templates | Status | S | whatsapp-templates/components/TemplatesGrid.tsx:211 | integrations/respond_templates.py:25; `==` | none | FE+BE |
| AI usage | Feature | S | ai-assistant/usage/page.tsx:213 | system/ai_assistant.py:623; `==` | none | FE+BE |
| API call logs | Source, Outcome | S | api-call-logs/page.tsx:232, :242 | system/api_call_logs.py:58-59; `==` | none | FE+BE |
| Topic audit | Subject | S | TopicAuditScreen.tsx:457 | system/chatbot.py:981; `==` | none | FE+BE |
| Translations | Language | S | TranslationsList.tsx:296 | system/translations.py:34; `==` | none | FE+BE |
| Ideas | Status, Submitter, Channel | C | components/ideas/IdeasListView.tsx:467, :502, :514 | client-side | none | FE |

### 3.2 Sales, orders, customers, finance, reports

| Screen | Filter | Today | FE control | Param -> BE (type, SQL) | Persisted | Change |
|---|---|---|---|---|---|---|
| Sales orders | Status, Priority, Source, Type, Customer, Agent | S | scm/sales-orders/components/SalesOrdersGrid.tsx:1146, :1158, :1170, :1121, :1077, :1093 | `status` `priority` `source` `demand_class` `customer_code` `sales_agent_id` -> scm/sales_orders.py:83-105; `==` (source: IN per system) | view (FILTERS_VERSION 2) | FE+BE |
| Delivery orders | Status | S | order-management/orders/components/OrdersList.tsx:446 | `order_status_id` -> order_management/orders.py:370 str; resolve then `IN` | URL | FE+BE |
| Customers | Group | S | order-management/customers/components/CustomersList.tsx:310 | `customer_group_id` -> customers.py:31; `==` | URL | FE+BE |
| Customers | Status | S, no-op | CustomersList.tsx:293 | `status` not declared (customers.py:24-31) | URL | yes/no; BE build |
| Branches | Book | S | order-management/branches/components/BranchesList.tsx:211 | `book` -> branches.py:30; `==` | none | FE+BE |
| Order statuses | Final | page-only | OrderStatusesList.tsx:184 | client-side, current page | none | yes/no; fix to whole list |
| Opportunities | Stage, Agent, Customer | S | sales/opportunities/SalesOpportunitiesView.tsx:284, :294, :304 | sales/opportunities.py:135-137; `==` (service takes agent list) | none | FE+BE |
| Sales targets | Team | S | sales/targets/components/SalesTargetsView.tsx:444 | `sales_team_id` -> sales/targets.py:75 | URL | FE+BE |
| Billing documents | Type | M | finance/billing-documents/components/BillingDocumentsView.tsx:337 | comma -> finance/billing_documents.py:45; `IN` | none | none |
| Billing documents | Status, Customer, Agent | S | BillingDocumentsView.tsx:345, :357, :369 | billing_documents.py:46-48; `==` | none | FE+BE |
| Complaints | Status, Assigned to | S | complaint-management/complaints/components/ComplaintsList.tsx:458, :439 | complaints/complaints.py:247-248; `==` | URL | FE+BE |
| Complaints | Root cause, Resolution | M | ComplaintsList.tsx:476, :491 | comma -> `IN` | URL | none |
| Tickets | Status, Priority, Category, Source | S | ticket-management/tickets/TicketsList.tsx:280, :294, :307, :321 | tickets/tickets.py:45-50; `==` | none | FE+BE |
| Campaigns | Status | S | marketing-management/campaigns/components/CampaignsList.tsx:231 | marketing/campaigns.py:20; `==` | URL | FE+BE |
| Promotions | Access level, Attachment state | S | marketing-management/promotions/components/PromotionsList.tsx:442, :459 | marketing/promotions.py:98, :137 | URL | FE+BE |
| Price tag requests | Status | S | dealer-kit/price-tag-requests/components/PriceTagRequestsList.tsx:433 | dealer_kit/price_tag_requests.py:160; `==` | none | FE+BE |
| Brochure images | Promotion | S | dealer-kit/brochure-images/components/BrochureImagePicker.tsx:317 | master_data/product_attachments.py:52 | none | FE+BE |
| Report: Sales by debtor type | Company | S (not clearable) | components/reports/ReportFilterBar.tsx:324 | reports engine `company` -> datasets `==values[0]` | report view | see Q2 |
| Report: Sales by debtor type | Sales type, Agent, Debtor type | M | ReportFilterBar.tsx:305 | engine `_as_list` -> `IN` | report view | none |
| Report: Top selling items | Company | S | ReportFilterBar.tsx:324 | `==` | report view | see Q2 |
| Report: Top selling items | Sales type, Agent, Brand, Debtor type | M | ReportFilterBar.tsx:305 | `IN` | report view | none |
| Report: Yearly comparison | Company | S; Channel M | ReportFilterBar.tsx | `==` / `IN` | report view | see Q2 |
| Report: Sponsorship forms | Sales agent, Status | M | ReportFilterBar.tsx:305 | `IN` | report view | none |
| Reports: Chat overview / Top asks / Bot failures | Contact type, Outcome, Subject | M | ReportFilterBar.tsx:305 | `IN` | report view | none |
| Reports: Top asks | Products (role) | S | ReportFilterBar.tsx:324 | chat_top_asks.py:103 | report view | FE+BE |
| Advanced filter dialog (Suppliers, Promotions, Orders, Workflow definitions / submissions) | any enum / uuid field | free text; `in` = comma text | components/list/ListQueryFilterDialog.tsx:329 | POST list-query/search; `in` compiles to `IN` (filter_compiler_adapters.py:71-74) | URL `advFilter` | FE+BE (option_source + multi picker) |
| Workflow submissions | State code | text box | workflow-forms-management/components/WorkflowSubmissionsList.tsx:293 | `workflow_submission_state_code`; `==` | none | FE+BE |

### 3.3 Inventory, products, procurement, SCM

| Screen | Filter | Today | FE control | Param -> BE (type, SQL) | Persisted | Change |
|---|---|---|---|---|---|---|
| Stock balance | Warehouse | S | inventory-management/stock/components/StockBalanceGrid.tsx:302 | `warehouse_id`; BE also takes `warehouse_ids` list (inventory/stock.py:259) `IN` | none | FE |
| Stock balance | Status (critical / low / normal / overstock) | S | StockBalanceGrid.tsx:315 | stock.py:269; if/elif buckets | none | FE+BE (OR the buckets) |
| Stock batches | Status | S, no-op | stock-batches/components/BatchesList.tsx:196 | not declared (stock_batches.py:16-27) | none | FE+BE (build filter) |
| Stock ledger | Transaction type | S | stock-ledger/components/StockLedgerList.tsx:191 | inventory/stock_ledger.py:24; `==` | none | FE+BE |
| Stock transfers | State | S | inventory-management/stock-transfers/StockTransfersPanel.tsx:501 | comma -> stock_transfers.py:116; `IN` | URL | FE |
| Stock transfers | Source, From, To, Item | S | StockTransfersPanel.tsx:512, :523, :534, :545 | stock_transfers.py:86-89; `==` | URL | FE+BE |
| Products | Category | S | master-data-management/products/components/ProductsList.tsx:918 | `category_id` -> products.py:127; resolve one then `IN` | URL | FE+BE |
| Products | Brand | S | ProductsList.tsx:932 | `brand_id` -> products.py:128; comma already split, `IN` | URL | FE |
| Certificates | Validity | S | certificates/components/CertificatesList.tsx:402 | comma -> certificates.py:70; OR of states | URL | FE |
| Certificates | Scheme, Status | S | CertificatesList.tsx:422, :432 | certificates.py:68-69; `==` | URL | FE+BE |
| Spec verification | State, Class | S | spec-verification/components/SpecVerificationList.tsx:900, :914 | product_specifications.py:720-721; `==` (summary assumes one) | URL (live) | FE+BE |
| Spec "Seen in products" tab | Value, Class, Source | S | product-specifications/components/record/SeenInProductsTab.tsx:226, :236, :246 | master_data/spec_registry.py:586-591; `==` | none | FE+BE |
| GRN | Status | S | procurement-management/grn/components/GRNList.tsx:247 | `picking_status` -> procurement/grn.py:44; `==` | URL | FE+BE |
| New product applications | Status | S | new-product-applications/components/NewProductApplicationsList.tsx:338 | comma -> new_product_applications.py:113; `IN` | URL | FE |
| New product applications | Applicant | S | NewProductApplicationsList.tsx:348 | new_product_applications.py:105; `==` | URL | FE+BE |
| Packing lists | Region | S | packing-lists/components/PackingListsList.tsx:459 | procurement/packing_lists.py:231; contains | URL | FE+BE (two values) |
| Purchase requests | Type, Status, Assigned to | S | purchase-requests/components/PurchaseRequestsList.tsx:496, :511, :524 | procurement/purchase_requests.py:59-61; `==` | URL | FE+BE |
| SPO allocations | Product, Warehouse | S | spo-allocations/components/SPOAllocationsList.tsx:504, :517 | procurement/spo_allocations.py:210-211; `==` | URL | FE+BE |
| Stock inquiries | Status | M | stock-inquiries/components/StockInquiriesList.tsx:497 | comma -> `IN` | view | none |
| Cost price uploads | Status | M | CostPriceUploadsList.tsx:207 | comma -> `IN` | none | none |
| Cost price uploads | Supplier | S | CostPriceUploadsList.tsx:214 | procurement/cost_price_changes.py:77; `==` | none | FE+BE |
| Supplier prices tab | Status, Packaging | M | suppliers/[id]/components/SupplierPricesTab.tsx:239-240 | comma | none | none |
| Purchase orders | Status | S | scm/purchase-orders/components/PurchaseOrdersList.tsx:596 | scm/purchase_orders.py:57; `==` | URL | FE+BE |
| Proforma invoices | Supplier, Packing list placement | S | scm/proforma-invoices/components/ProformaInvoicesView.tsx:630, :643 | scm/proforma_invoices.py:316-317 | URL | FE+BE |
| Loading plans | Status | S | scm/loading-plan/components/LoadingPlansGrid.tsx:333 | scm/fulfilment.py:617; `==` / IN for active | none | FE+BE |
| SCM dashboard | Warehouses | M | scm/components/ScmFilterBar.tsx:128 | comma -> `ANY` | none | none |
| SCM dashboard | Category, Supplier, Value (ABC), Demand (XYZ) | S | ScmFilterBar.tsx:137, :148, :157, :166 | scm/dashboard.py:94-99 | none | FE+BE |
| Low stock report | Suppliers, Categories | M | LowStockReportView.tsx:211, :220 | repeated -> set | none | none |
| Reorder results | Type | S | scm/reorder/components/ReorderResultsGrid.tsx:566 | scm/reorder_runs.py:1174; `==` | none | FE+BE (component looks unused) |
| Reorder plan lines | Rec type, Decision | M (`in`) | PlanLinesGrid.tsx:1281 | client-side | view | none |
| Reorder plan exceptions / PO worklist | Status | C | PlanExceptionsView.tsx:362, PoWorklistView.tsx:569 | client-side | none | FE |
| SCM plan row pickers | PO, Supplier, Sales order, Customer, Location | C, one per condition | scm/components/PlanRowDialog.tsx:1301 | client-side | none | FE |
| Stock debt | Supplier, Location | M | project-sales/stock-debt/components/StockDebtClient.tsx:613, :627 | repeated | view | none |
| Stock debt snapshot | Decision | S | stock-debt/components/SnapshotClient.tsx:308 | projects/stock_debt_snapshots.py:102 | none | FE+BE |

### 3.4 Project sales, resources

| Screen | Filter | Today | FE control | Param -> BE (type, SQL) | Persisted | Change |
|---|---|---|---|---|---|---|
| Project order inquiries | Instruction, State | S | project-sales/[projectId]/order-inquiries/components/OrderInquiryClient.tsx:518, :528 | BE already `List[str]` `IN` (order_inquiries.py:1115-1116) | none | FE |
| Order inquiry lines | Location, Agent, Linked, Confirmed, State, Dead document, Reserve, Supplier, Project, Raised by | S | order-inquiries/components/OrderInquiriesClient.tsx:1505-1672 | projects/order_inquiries.py:287-407; `==` / Literal | URL + view | FE+BE |
| Order inquiry documents | Reserve, Raised by, Agent, Project | S | OrderInquiryHeadersList.tsx:640, :656, :671, :684 | order_inquiries.py:1941-1953; `==` | URL | FE+BE |
| Allocation panel | State | C | sales-orders/[psoId]/components/AllocationPanel.tsx:321 | client-side | none | FE |
| Divergences | State | S | project-sales/divergences/components/DivergenceListClient.tsx:277 | projects/divergences.py:153 default "open"; `==` | none | FE+BE (+ fix "Any") |
| Fulfilment planning | Review state | S | fulfilment-planning/components/FulfilmentPlanningClient.tsx:794 | fulfilment_planning.py:161-165 Literal | none | FE+BE |
| Fulfilment board | Status | M | FulfilmentBoardListView.tsx:1058 | client-side | none | none |
| Lead acceptance | Assigned to | S | lead-acceptance/components/AwaitingAcceptanceClient.tsx:324 | BE `List[str]` `IN` (leads.py:149) | none | FE |
| Leads | Outcome, Source | S | leads/components/LeadsClient.tsx:198, :208 | BE `List[str]` `IN` (leads.py:84, :88) | URL | FE |
| Parties | Type | S | parties/components/PartiesClient.tsx:311 | projects/parties.py:30; `==` | none | FE+BE |
| Pipeline | Developer, Type, Approval | S | pipeline/components/PipelineClient.tsx:233, :249, :265 | BE `List[str]` `IN` (projects.py:142-171) | URL | FE |
| Plans | State | S (required) | plans/components/PlansClient.tsx:359 | fulfilment_planning.py:235 Literal | none | FE+BE |
| Sample requests | Status | S | sample-requests/components/SampleRequestsList.tsx:293 | comma -> `IN` | URL | FE |
| Sample requests | Salesperson | S | SampleRequestsList.tsx:303 | sample_requests.py:111; `==` | URL | FE+BE |
| Stock claims | Outcome | S | stock-claims/components/StockClaimsClient.tsx:325 | BE `List[str]` `IN` (allocations.py:106) | none | FE |
| Folder attachments | Attachment type | S | attachment-directories/components/AttachmentsInFolderPanel.tsx:1157 | drive route single; service has list path | none | FE+BE |
| Folder attachments | Storage status, Company, Uploaded by | S | AttachmentsInFolderPanel.tsx:1193, :1211, :1228 | resources/attachments.py:436-444; `==` | none | FE+BE |
| Folder attachments | Access levels | M | AttachmentsInFolderPanel.tsx:1306 | repeated | none | none |
| Attachments | Folder, Company | S | resource-management/attachments/components/AttachmentBrowser.tsx:453, :508 | resources/attachments.py:262, :302; `==` | URL | FE+BE |
| Attachments | Attachment type | S | AttachmentBrowser.tsx:472 | BE has `attachment_type_ids` list (:265) | URL | FE |
| Customer asks portal landing | Customer, Contact, Product, Answer, State | C | (auth)/portal/components/LandingToolbar.tsx:225 | client-side | none | FE |

## 4. Rollout (stacked PRs, shared first)

1. PR1 #1930: shared parsers + Contacts Company filter + Companies column (owner ask).
2. PR2: Contacts (Access type, Tier, Customer, Region), Users, Permissions (+ build Role), SLA, system
   logs and outboxes.
3. PR3: Sales orders, delivery orders, customers (+ build Status), complaints, tickets, billing,
   opportunities, campaigns, promotions, price tags.
4. PR4: Inventory, products, certificates, spec screens, procurement.
5. PR5: SCM screens.
6. PR6: Project sales and resources.
7. PR7: Advanced filter dialog option pickers (`option_source`) and the text-box filters turned into
   dropdowns; reports Company (per the owner's answer).

Each PR: red tests first (vitest per screen filter control + URL round trip; pytest per backend param
via `multi_values`), kill tests, reviewer, browser pass on 5+ screens, hand-test script.
Every PR also covers the screen's export / summary / board paths with the same multi values (PR3
review lesson, 28 Oct: two list-query exports broke on a second value while the lists worked).

### 4.1 PR7 design (advanced filter dialog pick lists; owner Q4 (a))

Facts (28 Oct scan): the dialog (`components/list/ListQueryFilterDialog.tsx`) opens on Orders,
Products, Suppliers, Promotions and the two workflow lists; its value input is free text for every
non-boolean, non-number field (:329-334); `list_query_fields` rows are seeded by migrations and the
metadata route hard-codes `option_source: None` (`api/v1/list_query.py:161`); no column involved is a
DB enum. Pick-list fields today: Orders `order_status_id`, `customer_id`, `line_product_id`,
`line_warehouse_id`, `order_type`, `agent`; Products `category_id`, `brand_id`, `base_uom_id`,
`item_type`; Suppliers `country`; Workflow submissions `definition_id`, `current_state_code`.
Promotions has none left; `published_version_id` stays text (a version id is not a choice users make).

Design (one mechanism, no registry table):
- BE: one endpoint `GET /api/v1/list-query/{resource}/fields/{field_key}/options?query=&page=`
  returning `{data: [{value, label}], pagination}`: the DISTINCT values of that field over the
  resource's own base query (so company scope and the resource's view permission apply exactly as
  the list does), labelled through the field's relation (`order_status_id` -> `status_name`, etc.).
  The label compile key per field lives in a small dict next to `_infer_filter_ui_type`; a field
  absent from the dict gets no options (text box as today). The metadata route sets
  `option_source: {"kind": "distinct"}` for the dict's fields.
- FE: when a field has `option_source`, the value input for `in` / `not_in` is a
  `SearchableMultiSelect` (paginated loader from the endpoint) and for `eq` / `neq` a
  `SearchableSelect`; the stored value stays the array the URL already carries (`advFilter` keeps
  arrays, `lib/listNavQuery.ts:93-123`), so saved links keep working.
- Text boxes turned into dropdowns (multi): Import jobs Type / Status (`ImportJobsList.tsx:325,:330`,
  `system/jobs.py:27-28`), Import logs Entity type (`ImportLogsList.tsx:218`, `system/import_logs.py:19`),
  Workflow submissions State code (`WorkflowSubmissionsList.tsx:293`; options from the definition's
  schema `states`). Options from the code's own constants where they exist, else the distinct values.
- Reports: Company stays single (owner Q2 (b)); no change.
- security-reviewer runs on PR7 (a new read endpoint over scoped data).
Trigger to revisit: a field whose distinct values are too many to list (then it needs a search-only
lookup), or a third consumer of the label dict (then the labels move onto `list_query_fields`).
