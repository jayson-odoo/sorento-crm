# Contract: `POST /order-inquiries/acknowledge` with `filter` (PLAN-oi-confirm-per-so)

Status: FE built against this contract (Phase 1). Backend unchanged in this slice - the
route already exists (`api/v1/projects/order_inquiries.py:521-548`, service
`acknowledge_rows` `project_order_inquiry_service.py:2686-2706`) and already accepts
`row_ids` + `link_up_to`/`link_horizon`. Phase 2 adds the `filter` branch below.

## Request body

Exactly one of `row_ids` or `filter` is present. Both present, or neither, is a 422.

```jsonc
{
  // EITHER this...
  "row_ids": ["<order_inquiry_row id>", ...],

  // ...OR this - the SAME shape `GET /order-inquiries` (the worklist list) takes,
  // minus page/limit/sort/dir. Every key optional; an absent key means "not filtered
  // on that axis", exactly as the list read it.
  "filter": {
    "query": "string | undefined",           // free-text search (SO number, item, PO/SPO, customer, agent)
    "delivery_month": "YYYY-MM | undefined",
    "raised_date": "YYYY-MM-DD | undefined",
    "state": "string | undefined",           // raised | partly_linked | placed | actioned | cancelled
    "project_id": "string | undefined",
    "supplier_id": "string | undefined",
    "raised_by": "string | undefined",       // user id
    "linked": "'po' | 'spo' | 'none' | undefined",
    "kind": "'buy' | 'po' | 'spo' | undefined",
    "ack": "'awaiting' | 'acknowledged' | 'changed' | 'rejected' | 'to_confirm' | undefined",
    "location": "string | undefined",
    "agent": "string | undefined",           // sales agent id
    "so_month": "YYYY-MM | undefined",
    "po_number": "string | undefined",       // prefix, case-insensitive
    "spo_number": "string | undefined",      // prefix, case-insensitive
    "delivery_from": "YYYY-MM-DD | undefined",
    "delivery_to": "YYYY-MM-DD | undefined",
    "axis": "'product' | 'sales_order' | 'customer' | 'agent' | undefined",
    "axis_key": "string | undefined"
  },

  // Both branches: the same link-horizon fragment every handshake press already sends
  // (`linkHorizonRequest`, unchanged by this lane).
  "link_up_to": "YYYY-MM-DD | undefined",
  "link_horizon": "'none' | undefined"
}
```

FE callers (`app/(protected)/project-sales/_shared/services/orderInquiryService.ts`):
- `acknowledgeOrderInquiryRows(rowIds, horizon)` - unchanged, sends `row_ids`.
- `acknowledgeOrderInquiryRowsByFilter(filter, horizon)` - new, sends `filter`. `filter` is
  built from the SAME `listFilters` memo the worklist's own list/summary/matrix queries
  already read (`OrderInquiriesClient.tsx`), so "Select all N matching" always confirms
  exactly the scope the buyer is looking at, never a stale or hand-rebuilt copy of it.

Both routed through `useOrderInquiryHandshake().acknowledge` (`useOrderInquiry.ts`), which
now takes `{ rowIds?, filter?, horizon? }` and picks the branch by which of `rowIds`/`filter`
is present.

## Expected result shape

Reuses `AcknowledgeResult` (`orderInquiry.types.ts`), extended with one field:

```ts
interface AcknowledgeResult {
  acknowledged: number;      // rows this press confirmed
  linked_rows: number;
  links: number;
  after_horizon?: number;    // taken on but due after the link horizon - left Not linked
  link_up_to?: string | null;
  link_horizon?: 'date' | 'none';
  skipped?: number;          // NEW - rejected/cancelled rows in row_ids or matching filter,
                              // left alone (AC-CF-8). Optional so an older backend answer
                              // still reads; the FE treats `undefined` as 0.
}
```

`by filter`: the server resolves `filter` the same way the list endpoint does (`_base` in
`order_inquiry_worklist_service.py`), then confirms every row in that result set whose
`ack_state` is `awaiting` or `changed` and whose `state` is not `cancelled`; everything else
matching the filter (rejected, already-confirmed/`acknowledged`, cancelled) is counted in
`skipped`, not `acknowledged`.

## List default (FE-side only, unchanged backend)

- Absent `?ack=` on the worklist reads as `to_confirm` on the FE; the FE then sends
  `ack: 'to_confirm'` to `GET /order-inquiries` (a value the endpoint has accepted since the
  original handshake plan - `order_inquiry_worklist_service.py:110-118`). No backend change.
- `?ack=all` sends no `ack` filter at all (every row, regardless of confirm state).
- Every other `ack` value (`awaiting`, `acknowledged`, `changed`, `rejected`) is unchanged.

## Permission

`projects.order_inquiries.acknowledge`, same as `row_ids` today (AC-CF-9). A principal
without it gets no Confirm button/menu item on the FE and a 403 from the endpoint either way
- unchanged by the `filter` branch.
