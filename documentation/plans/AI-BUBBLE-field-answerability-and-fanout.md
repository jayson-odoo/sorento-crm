# AI Bubble - Field Answerability + Fan-out (what users can ask)

**Status:** Validated 2026-06-28 (live LLM). Companion to `PLAN-bubble-record-context-and-guides.md`.

## The model (two data sources, both reach the answer)

The bubble can answer about a record the user is viewing from **two** sources, merged in the render path:

| Source | Carries | Reaches answer via |
|--------|---------|--------------------|
| `page_snapshot.visible_text` (≤6000 chars, DOM of the current screen) | **Every on-screen field** - purpose, dates, line items, addresses, remarks, prices, status pill, … | Injected into the agent loop **and** the record-context render path. Universal - works on ANY detail page. |
| Record-context **assembler** (`record_context_service.py`) | **Off-screen structured data** - SLA tab (tier/due/breach/lead-time), audit log/history, approval decision, who/when/lead-time | The deterministic pre-route, for the 4 form-SLA entities only. |

**Key consequence:** a detail page whose data is all on-screen needs **no assembler and no entity registration** - `visible_text` already answers it through the agent loop. Assemblers exist only to surface data the user would have to switch tabs / lacks permission to see.

## What users can ask (the taxonomy - drives test cases)

Per record, validated grounded for the 4 forms:
1. **Any visible field** - "what is the purpose / expected delivery date / customer / product code / defect / line items / price". → `visible_text`.
2. **Status** - "what's the status" → the single combined display status (PR/SF combine lifecycle + approval to match the pill).
3. **Decision** - "who approved/rejected this and why" → assembler `approval` / on-row reject cols.
4. **Lead-time** - "how long to decide / respond" → assembler lead-times.
5. **SLA** - "what's the SLA status / which tier / is it breached / who's it assigned to" → assembler `sla` (the SLA Tracking tab).
6. **Audit** - "show the history / who changed it last" → assembler `audit_trail`.
7. **Response** (stock inquiry) - "who responded / what did purchasing say" → assembler `response`.
8. **Next step / process** - "what should I do now / process flow for this" → guide-grounded by current status.

Anti-overfit: these are **categories of intent**, validated by paraphrase robustness, not memorized sentences. The classifier is a general semantic judgment; `visible_text` answering is inherently field-agnostic.

## Validation (live, service-level e2e)

- `tests/test_field_answerability_eval.py` (gated `RUN_LLM_EVALS=1`) - all 4 forms: real visible fields + SLA + audit, asserts the **real value** appears (grounded, never hardcoded); plus the no-assembler visible_text path, an honesty/absent-field guard, and a **real-data fan-out** test.
- **Fan-out validated on real data** across all 9 named non-form entities through the agent loop, NO entity, NO assembler: product (code), GRN/PickingHeader (picking number + status), SPO/SPOAllocation (number + receipt status), stock/Stock (on-hand), promotion (title), form (name + type), attachment (filename), **orders/Order** (number + debtor + type - "delivery orders"), **inbound_shipment/InboundShipment** (shipment number + status - "packing list").
- Manual battery: 15/15 field+SLA+audit across PR/SI/complaint.

## Fan-out classification

| Entity | Detail page | Off-screen data? | Action |
|--------|-------------|------------------|--------|
| complaint, stock_inquiry, purchase_request, sponsorship_form | yes | **yes** (SLA tab, audit, approval) | ✅ assembler adapters (done) |
| products | yes (tabs incl. Audit) | audit is a tab the user can open | `visible_text` covers main fields; audit via the tab. No assembler needed. |
| packing_list | yes (flat) | no | `visible_text` - already covered |
| attachments | yes (Linkages tab) | no (linkages visible) | `visible_text` - already covered |
| spo_allocation (SPO) | yes | no | `visible_text` - already covered |
| grn (GRN) | yes | no | `visible_text` - already covered |
| stock | yes (`[productId]/[warehouseId]`, ledger inline) | no | `visible_text` - already covered |
| promotion | yes | no | `visible_text` + `crm_marketing_promotions_list` |
| forms | yes | no | `visible_text` + `crm_forms_management_forms_list` |
| **orders** ("delivery orders") | yes | no | `visible_text` - validated (number/debtor/type); has `crm_order_management_orders_list` but the prefer-visible nudge keeps field Qs on the page |
| **inbound_shipment** ("packing list") | yes | no | `visible_text` - validated (shipment number/status) |

**Conclusion:** the fan-out needs **no new per-entity backend code**. `visible_text` (shipped) makes every detail page's fields answerable; existing MCP catalog tools cover list/cross-record questions. Optional polish (not required): register `RecordEntityRegistrar` on the non-form detail pages only if we later add off-screen data worth an assembler - otherwise it just costs a wasted assemble attempt per turn.

## Generic audit assembler - investigated, NOT justified

Considered a generic audit-trail assembler keyed by `audit_logs.(entity_type, entity_id)` so "who changed this / show history" works for ANY auditable entity, not just the 4 forms. Checked the real data:

- Auditable entities (`__audit_entity_type__`): complaint, stock_inquiry, purchase_request, product, ticket.
- `audit_logs` row counts: product **47,164**, complaint 2,668, purchase_request 1,931, stock_inquiry 1,726 - others (promotion, GRN, SPO, stock, forms) are **not audited at all**.
- BUT product audit rows are **bulk-import noise**: mostly duplicated `CREATE` actions, empty `description`, null actor. Not workflow-meaningful (unlike the forms' real status transitions with users).

**Decision: do not build it.** It would surface low-quality CREATE noise for products and nothing for the rest. Audit is meaningful only for the 4 forms (already covered by the assembler). For products, the on-page Audit tab + `visible_text` covers it on demand. Revisit only if product audit gains real field-change descriptions + actors.

## Open
- (resolved) delivery_orders = Orders, packing_list = InboundShipment - both validated + in the fan-out eval.
- Optional: if the agent loop ever mis-routes a clearly on-page question to a catalog tool, add a nudge to prefer `visible_text` for "this record" questions. Not observed for plain field questions.
- Optional FE polish: register `RecordEntityRegistrar` on the non-form detail pages - adds nothing today (no assembler), so deferred; one-liner per page if/when an assembler is added.
