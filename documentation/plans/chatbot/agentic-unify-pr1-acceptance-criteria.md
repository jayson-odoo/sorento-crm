# UAC: AGENTIC-UNIFY PR 1, the AI panel reads as the staff member

Status: written 31 Oct 2026. Owner ruling: Q3 (a) on `CARD-agentic-unify-31oct.md`, fix now, whole panel, not behind the rollout
permission (`CARD-agentic-unify-v2-31oct.md`). Small on screen, security-critical underneath: security-reviewer required.

**The rule:** through the panel, a staff member reads what they could read on their own screens, in their active company, and never
more. Today every panel read runs as the shared API key's act-as user, across every company.

Names used below. **Staff** = the logged-in user the panel is answering. **Act-as** = the user the shared key acts as.
**Identity header** = `X-Staff-User: <user id>`, sent by the MCP server to the backend.

## Panel to MCP

- **AC-1** Every `MCPRuntimeClient` the panel builds is `staff=True` with the real staff id, including `list_mcp_tools` and
  `_render_record_answer`. Building `staff=True` without an id raises `ValueError`.

## MCP to backend

- **AC-2** While serving a staff-marked call to a read tool (GET, or `read_only` in the catalog), every CRM request the MCP server makes
  carries the identity header. That covers catalog tools and hand-written tools alike, however deep the client call. Excluded: the routing
  hint `system/mcp-routing` (separate client, no CRM data, no such backend route).
- **AC-3** A call that is not staff-marked never carries it, whatever headers it sent. A write tool never carries it.
- **AC-4** A staff-marked read of a company-scoped tool with no staff id is refused, with no backend request.

## Backend identity

- **AC-5** Shared key + identity header of an active user, on a GET or HEAD, or a POST to a catalog `read_only` path: the route's
  `current_user["id"]` is staff, `current_user["key_user_id"]` is act-as, and the integration fields and `auth_method` are unchanged.
- **AC-6** Fails closed, never falling back to act-as: a malformed, unknown, inactive or deleted id gets 403 with code
  `staff_identity_invalid`. So does the header with any key other than the shared `EXTERNAL_API_KEY`.
- **AC-7** On any other write, the header is ignored: act-as and today's company scope, so attribution cannot be forged.
- **AC-8** With no header, nothing changes: a key with no contact still reads all companies, a key with a contact pair still reads the
  contact's companies, a session is untouched.
- **AC-9** The audit actor on an identity read stays the integration and act-as.

## Permission

- **AC-10** `require_permission_with_api_key`: staff AND act-as must both hold the slug. Staff lacking it gets 403 even though act-as holds
  it. Act-as lacking it gets 403 even though staff holds it: the header can only narrow.
- **AC-11** `require_any_permission_with_api_key`: staff must hold at least one slug of the list AND act-as must hold at least one, not necessarily
  the same one; the module check runs per user. A superadmin staff does not get past an act-as who holds none of the slugs. The shared key's act-as is
  not an admin and lacks some `.view_own` slugs (crew, read-only check on the 28 Oct prod copy), so a `.view_own`-only staff member with an act-as holding
  only `.view` must pass: this role must not need `.view_own` granted to it.
- **AC-12** External routes: a real slug needs both users; an `integration.*` slug is checked on act-as only, since staff never hold those.
- **AC-13** These routes gate on a slug for an identity read only. A session and a plain key behave exactly as today.

| Tool | Route | Slug |
| --- | --- | --- |
| `crm_inventory_stock_balance_list` | `inventory/stock/balance` | `inventory.stock.view` |
| `crm_incoming_stock_by_product`, `_shipments`, `_list` | `incoming-stock/by-product`, `/shipments`, `/list` | `procurement.packing_lists.view` |
| `crm_procurement_po_placed_list`, `_po_last_cost_list` | `procurement/purchase-orders/placed`, `/last-cost` | `scm.purchase_orders.view` |
| `crm_procurement_spo_allocations_last_receipt_list` | `procurement/spo-allocations/last-receipt` | `procurement.spo_allocations.view` |
| `crm_procurement_grn_summary` | `procurement/grn/summary` | `procurement.grn.view` |
| `crm_master_product_attachments_list` | `master-data/product-attachments` | `master_data.product_attachments.view` |
| `crm_purchase_request_by_number` | `procurement/purchase-requests/by-number/{number}` | `procurement.purchase_requests.view` or `.view_own`, or `procurement.sponsorship_forms.view` or `.view_own` |
| `crm_sales_opportunity_customer_options` | `external/sales-opportunities/customer-options` | `sales.opportunities.view` or `.view_own` (the staff route's own rule; named by the AC-22 guard) |

- **AC-14** Stay open to any staff, as pickers (owner ruling L10, `dependencies.py:499-505`): products list, warehouses, `lookup/resolve`,
  tool capabilities, guides.

## Own scope and company

- **AC-15** A staff member limited to their own rows (`view_own`) gets through the panel the same rows as on their own session: complaints list,
  projects list and detail, purchase request by number. Asserted as parity, same user, session call against identity call.
- **AC-16** Company: an identity call's scope is the staff member's active company, resolved exactly as a session resolves it. Orders, stock balance
  and purchase orders return only that company's rows, in parity with the session. A superadmin is narrowed to their active company too.
- **AC-17** No grants or a bad id: zero rows, never all companies.
- **AC-18** Identity header plus contact pair: the intersection of the two scopes.

## Record context

- **AC-19** Panel record facts need a view permission for all four record kinds: stock inquiry, purchase request, sponsorship form, complaint
  (`.view` or `.view_own`). Same for `api/v1/assistant/record_context.py`. No permission: no facts, the turn still answers.
- **AC-20** A `view_own` user gets facts only for their own record, even when the record id in the page snapshot names someone else's. The id comes
  from the client and is not trusted.

## End to end and guard

- **AC-21** A panel turn whose tool is refused with 403 still answers: no 500, and the model receives the refusal as a failed tool result.
- **AC-22** Guard: every read tool in `sorento_crm_mcp/catalog.py` is either refused for a staff member holding nothing, or named in one explicit list
  with its reason (open picker, or contact-only). A new catalog read with neither fails the test.
- **AC-23** Not gated: no setting or rollout permission controls this.

## Unchanged, each pinned

- **AC-24** Panel writes still run as act-as after Confirm, with `_WRITE_TOOL_PERMISSIONS`. `crm_order_cancel` stays without an extra slug (the UI path is
  auth-only, `ai_assistant_service.py:1819-1821`).
- **AC-25** Chatbot lanes, the agent loop and n8n send no identity header and behave as today.

## Same as screens, deliberately not changed

- Complaint, purchase request, stock inquiry, SLA tracking and lookup tables have no company column, so company scope cannot apply to them on screens either.
- Orders, sales and stock have no user-keyed own-customer rule, for sessions either.
- `resolve_references` keeps its picker-level behaviour inside the active company.
- Contact-only routes (`report-ask`, `sales/target-progress`) keep refusing without a contact; PR 2 gives them a staff path.

## Hand test

A low-permission staff member and a two-company staff member each ask the panel about stock, orders and a record they should not see.
