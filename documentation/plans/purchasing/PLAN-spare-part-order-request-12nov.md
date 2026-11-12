# PLAN: Spare-part order request (stock replenishment, no SO)

Status: Build (mock v5 + card v4 approved 12 Nov 20:14). Track L. as crew-ask on PR #2381; waiting on owner answers. No product code yet. Track: L (migration, new flow, approval permissions; security-reviewer required).

Lane: SPARE-PART-ORDER-REQUEST.

## Goal

A stock-replenishment order request (first use: spare parts) raised without a sales order,
approved through a configurable chain (requester -> approver -> purchasing; the approver may set
or change quantities), then delivered to purchasing as an Order Inquiry with its own type so
purchasing works it in the same place as SO-driven inquiries.

## Discovery (reuse first, measured in code)

### 1. Order Inquiry (purchasing's inbox): extend, add a type

- Header `OrderInquiry`, table `projects.order_inquiries`: `sorento_crm_backend/app/models/project_so.py:816`.
  `project_sales_order_id` is **NOT NULL, CASCADE** (`project_so.py:839`); there is no type column.
  States raised / actioned / cancelled (`project_so.py:738-740`); number `OI-YYMM-NNNN` minted on insert.
- Rows `OrderInquiryRow` (`project_so.py:990`): `item_code`, `qty`, `delivery_date`, `verb` (`ORDER` fits,
  `project_so.py:784`), `ack_state` awaiting / acknowledged / changed / rejected. No unit price, no currency.
- Hand-off: `_hand_to_purchasing` (`app/services/project_order_inquiry_service.py:8384`) and
  `_notify_purchasing` (`:8467`), recipients = every active `purchasing%` role holder (`_purchasing_user_ids`, `:8524`).
- Purchasing acts on rows through `acknowledge_rows` (`:9605`), `reject_row` (`:9936`), `mark_rows` (`:9544`).
- API: `/order-inquiry-headers` list/detail (`app/api/v1/projects/order_inquiries.py:1979`, `:2058`),
  slugs `projects.order_inquiry.action`, `projects.order_inquiries.acknowledge` (`permission_registry.py:635-656`).
- FE: `sorento_crm_frontend/app/(protected)/project-sales/order-inquiries/` (`OrderInquiriesClient.tsx`,
  `[id]/components/OrderInquiryDetail.tsx`, `OrderInquiryLinesTab.tsx`), service
  `_shared/services/orderInquiryService.ts`, hooks `_shared/hooks/useOrderInquiry.ts`.

Decision: **extend** OrderInquiry with `inquiry_type` (`sales_order` default, `spare_part_request`) and make
`project_sales_order_id` nullable behind a CHECK (`inquiry_type <> 'sales_order' OR project_sales_order_id IS NOT NULL`).
Risk measured: 83 reads of `project_sales_order_id` in inquiry code across 27 files; every read that
dereferences the order must tolerate a typeless-SO header (tests list each surface the type reaches:
header list, detail, rows worklist, acknowledge, reject, history, purchasing notification).
Not reused: SO-only machinery (verbs other than ORDER, reserve requests, supply decisions, amendments,
suggested links) never runs for this type.

### 2. Approval: form-SLA stage chain (NPA pattern) + routed-approver check (quotation pattern)

- `FormSLAConfig` (`app/models/sla.py:222`): one row per stage keyed by `source_entity_type` + `stage_code`,
  chained by `next_config_id` / `advance_on_event`, assignee team via `team_set_code` -> `AgentTeam`
  (`app/models/access.py:688`). Admin screen `/sla-management/form-sla-config`, slug
  `sla_management.form_sla_config.manage`. Advanced by `FormSLAOrchestrator.emit_event` (`app/services/form_sla_service.py:378`).
  Type list `FORM_SLA_TYPES` (`form_sla_service.py:34`) gets `stock_order_request`.
- NPA already runs approval -> purchasing on these stages (`new_product_application_service.py:429` submit,
  `:479` approve, `:491` reject, `:540` revise). Same shape here.
- Gap in the NPA pattern: approve checks only the slug. Quotation approval checks the actor against the routed
  approver (`may_decide`, `app/services/project_quotation_approval_service.py:500`). This lane adds that check: only a member of the current
  stage's team (or admin) may approve/reject, never the requester.
- Rejected alternatives: price tag (designer/salesperson proof, one stage, `price_tag_request_service.py:1825`);
  purchase request (customer-facing approver per send, `purchase_requests.py:526`); workflow forms
  (role-only, no resubmit/revise, no purchasing link); a new amount-threshold table (no case today; trigger
  named below).

### 3. Photos: fulfilment planning's attachment pipeline, generalised by entity type

- Upload/link service `app/services/so_line_attachments.py` (`upload` `:181`, `ENTITY_TYPE="sales_order_line"`),
  join table `entity_attachment_links` (`app/models/entity_attachment.py:10`), `storage_router`, thumbnails via
  `image_thumbnailer.store_thumbnail` (`so_line_attachments.py:245`).
- Decision: make that service take `entity_type` (one function; SO line stays its first caller), add
  `stock_order_request_line`. No second upload path.
- FE: thumbnails `components/common/AttachmentImage.tsx:19`, lightbox `components/common/AttachmentPreviewModal.tsx:197`,
  thumbnail-strip precedent `procurement-management/packing-lists/components/ShipmentLinePhotosCell.tsx`
  (to be lifted to a shared photo cell taking an entity, not copied).

### 4. Form, product picker, money, history

- Form layout template: `app/(auth)/portal/components/PriceTagRequestForm.tsx` (sections, `openSectionOnce` `:525`).
- Line table: `components/common/SampleRequestLines.tsx:35` (shared, product by `codeWithName`), picker
  `components/common/SearchableSelect.tsx:173`.
- Currency list `lib/currencies.ts`; money `formatMoneyExact` (`project-sales/_shared/lib/money.ts:128`).
- History tab `components/audit/AuditTrail.tsx:100` over `/audit-logs/` (`app/api/v1/audit/audit_logs.py:298`).

## Behaviour card (crew-ask; same text as the PR comment)

See the crew-ask comment on PR #2381. Answers are recorded here once relayed.

## Named triggers (not built now)

- Amount-based approval levels: build when the owner names a threshold that routes to a different approver.
- Approval per requester team: the stage's team already scopes who approves; a per-requester rule waits for a
  second requester team with a different approver.

## Owner answers

- Mock v1 note 1 (12 Nov 18:48): location per line like AutoCount; header default optional. Reuse: `sorento_crm_backend/app/services/scm/location_stock_service.py:35` (`location_stock_for_product`, behind `GET /scm/reorder-runs/location-stock`, `app/api/v1/scm/reorder_runs.py:511`); OI row's existing `stock_location` (`app/models/project_so.py:1018`). Mock v2 filed.
- Mock v1 note 2: reuse list posted as a crew-note on PR #2381.
- Mock v1 note 3: request detail laid out like the Sales Order screen (`sorento_crm_frontend/app/(protected)/scm/sales-orders/[id]/components/SalesOrderDetail.tsx`: header card `:1745`, tabs `:1881`, General cards `:1921`/`:2156`/`:2196`; local `Field` `:256` lifted to a shared component). Mock v2.
- Mock v1 note 4: request type Spare part / Consignment; OI `inquiry_type` values `sales_order` | `spare_part_request` | `consignment_request`; consignment reuses `ConsignmentBadge` (`app/(protected)/scm/lib/docType.ts`). Differences asked as card v2 Q5.
- Mock notes 5-7 (12 Nov 18:54): stock per line = `sorento_crm_frontend/app/(protected)/project-sales/_shared/components/OrderInquiryStockGrid.tsx` as is (wired at `order-inquiries/[id]/components/orderInquiryHeaderLinesColumns.tsx:471-510`); attachments = `_shared/components/SoLineAttachmentsButton.tsx` (mock v2's thumbnail strip was NOT it; switched); the request opens on the existing OI page `order-inquiries/[id]/components/OrderInquiryDetail.tsx` (header `:771`, tabs `:1001-1019`), fields in `OrderInquiryGeneralTab.tsx`, lines in `OrderInquiryLinesTab.tsx`. The SO-style layout of mock v2 is dropped. Consequence: card question 1 flips to ONE record (the request is an OI of type spare_part_request / consignment_request with draft and pending_approval states before purchasing sees it). Mock v4 + card v3 filed.
- Mock note 8 (12 Nov 20:00): no Consignment type (supersedes note 4). `inquiry_type` values: `sales_order` | `spare_part_request`.
- Mock note 9: the approver edits qty, unit price and photos per line before approving; requested values kept on the row (`requested_qty`, `requested_unit_price`) and shown as "was ..."; each change audited (OI History). Photos via `SoLineAttachmentsButton` `canEdit`. Mock v5 + card v4 filed.
- Card v4 + mock v5 APPROVED (owner 12 Nov 20:14: "Ok go, make sure reuse"): all five recommendations stand. Q1 one record (the request IS an OI of type spare_part_request); Q2 Form SLA stages, one chain, server-side team check; Q3 catalogue products only; Q4 Revise until purchasing acknowledges; Q5 approver edits qty / unit price / photos on existing lines only.

## Build contract (approved design, 12 Nov 20:14; the tester and coder work from this)

### Impact check (measured, 12 Nov)
- `order_inquiries` / `order_inquiry_rows` carry no CHECK constraints; header `state` String(16) (`project_so.py:845`), row `state` default `raised` (`:1067`), row `so_line_id` already nullable (`:1011`); rows have no `product_id` / `unit_price`.
- `scm.committed_v` FORM leg (`app/services/scm/demand.py:589-644`) counts rows with verb ORDER/ORDER_BACK and state raised/partly_linked, by `item_code` + `stock_location`, no header join. A spare-part row must never be counted: draft rows use row state `draft`, and approved rows use a NEW verb `REPLENISH` (crew-ask on PR #2381, recommendation (a)), which committed_v and every `IN ('raised','partly_linked')` reader already ignore. No view change.
- `_refresh_inquiry_states` (`project_order_inquiry_service.py:10340-10363`) rewrites a header's state from its rows: must skip pre-approval headers.
- `mark_rows` (`:9548`), `acknowledge_rows` (`:9605`), `reject_row` (`:9936`) accept rows by id: must refuse `draft` rows (409).
- `live_row_clause` (`app/services/oi_row_visibility.py:33`) treats any non-cancelled row as live: must also exclude `draft`.
- Header list/detail (`order_inquiry_header_service.py:169-172`) and worklist `_base` (`order_inquiry_worklist_service.py:1439-1443`) INNER JOIN the sales order: must become OUTER, so a spare-part inquiry is listed and opens. Worklist `product_id` (`:915`, `:1460`) must fall back to the row's own `product_id`.
- Schemas `OrderInquiryHeaderOut.project_sales_order_id` (`app/schemas/project_order_inquiry.py:1508`) and `OrderInquiryDetail.project_sales_order_id` (`:390`) become Optional.
- Purchasing handover email `_record_handover` (`:4747`) and notification `_notify_purchasing` (`:8467`) run at raise; for this type they run once, at final approval, never before.
- `_LINKABLE_VERBS` (`:404`) gains `REPLENISH` so purchasing links POs to these rows as to ORDER rows.

### Data (one additive migration, re-parented onto main's head)
- `projects.order_inquiries`: `inquiry_type` varchar(32) NOT NULL DEFAULT 'sales_order' with CHECK IN ('sales_order','spare_part_request'); `project_sales_order_id` DROP NOT NULL with CHECK (`inquiry_type <> 'sales_order' OR project_sales_order_id IS NOT NULL`) (add CHECKs `NOT VALID` then `VALIDATE`); `currency` varchar(3), `requested_by` FK users, `needed_by` date, `default_location` varchar(80), `reason` text, `submitted_at`, `approved_at` timestamp, `approved_by` FK users, `reject_reason` text. All nullable.
- `projects.order_inquiry_rows`: `product_id` uuid FK products, `description` text, `unit_price` numeric(15,4), `requested_qty` numeric(15,4), `requested_unit_price` numeric(15,4). All nullable.
- New constants: header states `draft`, `pending_approval`, `rejected` (spare_part_request only); row state `draft`; verb `REPLENISH`; type constants `INQUIRY_TYPE_SALES_ORDER`, `INQUIRY_TYPE_SPARE_PART`.

### Lifecycle (spare_part_request)
- Create: header `draft`, rows `draft` (verb REPLENISH, ack awaiting), number from the existing `_stamp_inquiry_no` listener (same OI series). Requester = actor.
- Edit (requester; draft or rejected): replace lines; currency, needed_by, default_location, reason; each line product (catalogue `product_id`, item_code + description from the product), stock_location (defaults to header default_location), qty, unit_price.
- Submit (requester; draft or rejected): validate (currency set, >= 1 line, each line qty > 0, unit_price >= 0, location set); refuse 422 with a plain message when no active `form_sla_configs` row exists for `spare_part_request`; copy qty/unit_price into requested_qty/requested_unit_price; header `pending_approval`, `submitted_at`; `FormSLAOrchestrator.emit_event('spare_part_request', id, 'submitted', company_id=...)`.
- Can decide = admin/superadmin, OR (actor is a member of the current stage's team: the active tracker from `active_trackers_for_source` (`form_sla_service.py:515`), its config's `agent_code` + `team_set_code`, membership by `UserService.get_user_tier_in_team_set` (`user_service.py:3162`)) AND actor is not the requester. Everyone else 403.
- Approver edit (can decide; pending_approval): per line qty (>= 0) and unit_price (>= 0); requested_* never change; each change `log_audit` (old -> new). Photos: add / delete through the row attachment endpoints.
- Approve (can decide): refuse 422 if every line qty is 0; emit 'approved'; if a further stage is now active, stay `pending_approval` (next team notified by the SLA machinery); if none, FINAL: header `raised`, `approved_at/by`, rows with qty > 0 -> state `raised`, rows with qty 0 -> `cancelled`, then purchasing notification (reuse `_purchasing_user_ids` + the existing order-inquiry notification queue) once, audit row.
- Reject (can decide; reason required): header `rejected`, `reject_reason`, emit 'rejected'; requester edits and resubmits (back to level 1).
- Revise (requester; header raised and NO row acknowledged and no links): header back to `draft`, rows back to `draft`, approval fields cleared, void SLA trackers (`void_active_for_source`), audit.

### Visibility and permissions
- New slug `procurement.spare_part_requests.create` (permission registry) for Create / own drafts.
- A pre-approval header (draft, pending_approval, rejected) is visible only to its requester, to users who can decide on it, and to admins; never in purchasing's lists, counts, exports or notifications.
- Approved spare-part inquiries are visible like any OI (`projects.projects.view`). Header list / detail / lines also open to a requester holding the create slug for their own spare-part inquiries.
- Row attachment endpoints: write = requester while draft/rejected, can-decide while pending_approval; read = whoever can see the inquiry.

### Reuse (no second copy)
- OI page, header card, tabs: `OrderInquiryDetail.tsx`, `OrderInquiryGeneralTab.tsx`, `OrderInquiryLinesTab.tsx` + `orderInquiryHeaderLinesColumns.tsx`, `OrderInquiryHistory.tsx`; list `OrderInquiryHeadersList.tsx` (+ Type column / multi-select filter).
- Stock per line: `OrderInquiryStockGrid` as is (needs `product_id`).
- Attachments: `so_line_attachments.py` takes the entity type + its scope model as parameters (SO line stays the first caller); `SoLineAttachmentsButton.tsx` takes the target (SO line or OI row) instead of a hard-wired SO-line service.
- Approval: Form SLA stages + `emit_event`; membership `get_user_tier_in_team_set`; `FORM_SLA_TYPES` gains `spare_part_request` with label + link to the OI page.
- Form: `FormSection` + `openSectionOnce` pattern (`PriceTagRequestForm.tsx:525`), product picker by code and name, `lib/currencies.ts`, `formatMoneyExact` (`money.ts:128`), shared number input, location picker fed by `location_stock_service` / the existing warehouse select.
- History: `log_audit` on `project_order_inquiries` entity type (same as OI history today).
