# UAC: chatbot incoming answer carries ETA delay silently

Plan: `PLAN-chatbot-eta-delay-always-kept-24sep.md`
All ACs are pytest against `fetch.output_structurer` (pure function, no DB), in
`sorento_crm_backend/tests/chatbot/test_s6b_fetch_lane.py`.

Envelope shape for every AC: `result_type: "incoming_stock"`, `has_result: True`, one item
whose fields carry `product_code` (identity), `estimated_arrival_date`, and (per AC) an
`eta_delay_date` field; `field_vocabulary` may be present.

- **AC-1 delay rides with the bare ETA ask.** `requested_attributes: []`, no shipment named
  in ctx, row carries `eta_delay_date: "2026-10-02"`. Output fields contain
  `estimated_arrival_date` AND `eta_delay_date`. No "not recorded yet" field, no "can't share"
  text in `response`.
- **AC-2 delay rides with an explicit ETA ask.** `requested_attributes:
  ["estimated_arrival_date"]`, row carries `eta_delay_date`. Output keeps both. No note text.
- **AC-3 denied delay is silent when not asked by name.** `requested_attributes:
  ["estimated_arrival_date"]`, row has NO `eta_delay_date` field (the backend stripped it),
  `field_access.denied` = `[{"field": "eta_delay_date", "label": "ETA Delay"}]`. `response`
  contains NO "can't share", NO "eta delay", NO "not recorded yet". ETA line still present.
- **AC-4 explicit delay ask still refuses when denied.** `requested_attributes:
  ["eta_delay_date"]`, same denied envelope as AC-3. `response` DOES contain the denial note
  (existing behaviour, guards against over-suppression). The existing test at ~line 548
  already covers this; keep it green, do not duplicate.
- **AC-5 blank delay is silent when not asked by name.** `requested_attributes:
  ["estimated_arrival_date"]`, row has no `eta_delay_date`, no `field_access`. Output fields
  do NOT contain a synthetic `eta_delay_date` "not recorded yet" entry.
- **AC-6 non-checkpoint ask keeps the delay.** `test_non_checkpoint_ask_does_not_expand`
  updated: a `liner_code` ask keeps `liner_code`, `product_code`, `estimated_arrival_date`
  AND `eta_delay_date`; every other checkpoint still dropped.
- **AC-7 existing suite green.** `pytest tests/chatbot/test_s6b_fetch_lane.py -q` passes
  in full.
