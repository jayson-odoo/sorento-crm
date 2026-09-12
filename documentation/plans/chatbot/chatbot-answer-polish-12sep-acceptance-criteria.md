# UAC: Chatbot answer polish, 12 Sep 2026

Plan: `PLAN-chatbot-answer-polish-12sep.md`.

- AC-1 No spec cap. A product item with 12 populated spec keys and no requested attribute
  renders a `Specs` field naming all 12 as `Label: value` pairs, comma-separated, in
  registry order, and the value never contains "more". An item with 8 or fewer keys is
  byte-identical to today.
- AC-2 Miss-line code cap unchanged. The per-word "not recorded for A, B, C (+N more)"
  line still caps at `_MISS_CODES_CAP` codes (existing test keeps passing).
- AC-3 No phantom attachment sentence. `crossdomain_render` output never contains
  "I have attached the file(s) below.", including when the probe envelope carries a
  non-empty `attachments` list and rows render. The rest of the block (lead, rows,
  silent-company note, only-other note, nothing note) is byte-identical to today.
- AC-4 Bold rung labels. `_crossdomain_rung_text` renders, for a full row, exactly:
  `*Product Code:* SRTWC191-G3\n*Ordered:* 30\n*Outstanding:* 30\n*PO date:* 2026-08-10\n*Location:* BRW`.
- AC-5 Rung omission and separation unchanged. A null/empty `ordered_qty`, `po_date` or
  `location` omits its line entirely (never a placeholder); `*Product Code:*` and
  `*Outstanding:*` always print; two rows are separated by exactly one blank line.
- AC-6 Typed prefix is requested. `crossdomain_zeroset` with `resolved = {"tokens":
  ["SRTWT6236"], "intersection": [<product canonical_code "SRTWT6236-GY", uuid U>]}`,
  `domain_hint = "incoming"`, `message_type = "business_query"`, and a validator item with
  no returned rows yields `_xd.active == True`, `_xd.requested == ["SRTWT6236-GY"]`,
  `_xd.missing[0].uuid == U`, and one probe entity for U. The same with the exact token
  "SRTWT6236-GY" is byte-identical to today.
- AC-7 Prefix guard. A typed token shorter than 4 characters ("SRT") requests NO product by
  prefix: `_xd.active` is False when the intersection holds only prefix matches for it.
  An exact-equal token of any length still requests as today.
- AC-8 End to end (unit, mocked probes): an incoming-origin turn for typed "SRTWT6236"
  whose incoming lookup is empty, whose stock probe returns no rows, and whose PO rung
  returns one PO row renders "No incoming and no stock for SRTWT6236-GY, but PO is
  placed:" followed by the bold-label block, and the block's `team` is `purchasing`.
- AC-9 Detailed hide-zero keeps an all-zero product. With a contact policy `mode =
  "detailed"`, `hide_zero_locations = true`, no warehouse lists: a product whose only
  visible rows read 0 at two warehouses returns BOTH rows (quantity 0) from
  `get_stock_balance` (the endpoint behind `crm_inventory_stock_balance_list`), and the
  pagination total counts them.
- AC-10 Detailed hide-zero still drops zero beside stock. Same policy: a product with 5 at
  BRW and 0 at BRW-BB returns only the BRW row; total is 1.
- AC-11 Negative rows stay. Same policy: a product with -2 at BRW and 0 at BRW-BB returns
  the BRW row (existing rule) and, because the product is not zero everywhere, drops the
  BRW-BB row.
- AC-12 Scope inside the predicate. The all-zero test in AC-9 seeds a THIRD row for the same
  product in a warehouse EXCLUDED by the policy (`excluded_warehouse_ids`) holding 7: the
  product still counts as zero-everywhere for this contact (both 0 rows return). A row in
  another company never makes a product "has stock somewhere" (seed one and assert the two
  0 rows still return).
- AC-13 Compact mode unchanged. The compact-mode hide-zero test set in
  `tests/test_stock_visibility_policy.py` keeps passing byte-identical.
- AC-14 Live turns (console check, lane stack, recorded as evidence): "ETA SRTWT6236"
  carries the bold PO block; "SRT6550-DIY ETA" in detailed mode with the contact's prod
  policy (hide-zero on) prints the BRW row at 0 and "stock is 0 at every location ... but
  PO is placed"; a SRTKT71SS ask lists every spec; a CWCX7605-S-ECO stock ask carries no
  "attached the file(s)" sentence.
