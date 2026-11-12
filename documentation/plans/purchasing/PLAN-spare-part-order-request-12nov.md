# PLAN: Spare-part order request (stock replenishment, no SO)

Status: Plan, behaviour card filed as crew-ask on PR #2381; waiting on owner answers. No product code yet. Track: L (migration, new flow, approval permissions; security-reviewer required).

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

Decision: **extend** OrderInquiry with `inquiry_type` (`sales_order` default, `stock_replenishment`) and make
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
- Card questions 1-5: (pending)
