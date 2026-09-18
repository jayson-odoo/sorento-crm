## PLAN: order inquiry worklist - SPO, Agent, Instruction columns sort

Status: in progress (Track: small fix)

### Bug

On `/project-sales/order-inquiries` (purchasing worklist, List view), clicking the
column header to sort on SPO, Agent or Instruction returns a 422 and the grid shows
"The order inquiry could not be loaded / sort: Input should be 'inquiry_no', 'so_date',
... 'location' or 'agent'".

### Cause

FE column ids in `orderInquiryWorklistColumns.tsx` are sent verbatim as `sort`
(`OrderInquiriesClient.tsx`: `sort: sorting[0]?.id ?? 'delivery_date'`). Three ids are
not in the server's `SORTABLE_FIELDS` / `WorklistSort` set:

- `spo_number` - the server has no SPO sort at all.
- `agent_code` - the column id; the server already sorts on `agent` (same underlying
  column, `SalesAgent.sales_agent`), but not under this name.
- `verb` - the "Instruction" column; the server has no verb sort.

### Rule

Every column that draws a sort arrow is a key the server accepts for `sort`. A grid
offering a sort the backend refuses is a screen lying about what it can do.

### Change

Backend only (`app/api/v1/projects/order_inquiries.py` `WorklistSort` Literal,
`app/services/order_inquiry_worklist_service.py` `SORTABLE_FIELDS` and
`_SORT_EXPRESSIONS`):

1. `agent_code` -> `SalesAgent.sales_agent`, the same expression `agent` already sorts
   by. `agent` is kept too - the Schedule matrix axis and any other caller may still
   name it.
2. `verb` -> `OrderInquiryRow.verb`.
3. `spo_number` -> the first SPO number the row's own SPO cell prints: a row's own
   link through `spo_allocations`, ordered the same way `OrderInquiryLink` rows are
   read elsewhere (`linked_at` then `id`, ascending - "first" is an order in time),
   falling back to the row's own `spo_ref` when it has no such link. Built as a
   correlated scalar subquery in the style of `_LINKED_PO_ID`, with an explicit
   `.correlate(OrderInquiryRow)` (mandatory - see the comment above `_LINKED_PO_ID`).
   The derived-SPO leg (a PO link whose PO has an open SPO allocation for the same
   product, `_SPO_LINKED_PO_ID`'s sibling reasoning) is deliberately NOT folded into
   the sort: own link then `spo_ref` is the rule for this key.

No frontend change: the FE column ids (`spo_number`, `agent_code`, `verb`) are sent
unchanged, so no saved column layout (personalisation is keyed by column id) is
orphaned.

### Tests

`sorento_crm_backend/tests/test_order_inquiry_worklist.py`, beside the existing sort
tests (~line 786-845):

- Parametrized over `("spo_number", "agent_code", "verb")` x `("asc", "desc")`: the
  list endpoint accepts the sort and returns 200.
- `spo_number` orders rows by their own linked SPO number first, then by `spo_ref` for
  a row with no link; a row with neither sorts last (nulls last, both directions - the
  generic `.nulls_last()` ordering already applied to every sort field).
- The two existing agreement tests
  (`test_the_route_and_the_service_agree_on_the_sortable_set`,
  `test_every_advertised_sort_column_answers`) stay green with the widened set.

Run only the touched file, on the shared dev DB from `.env` - never the full suite on
this track.

### Out of scope

- Renaming any FE column id (would orphan saved column layouts, personalisation is
  keyed by column id).
- Folding the derived-SPO leg (a PO's own open SPO allocation, `_SPO_LINKED_PO_ID`)
  into the `spo_number` sort - the rule stated above is own link then `spo_ref`, same
  as the SPO cell's first-priority read.
