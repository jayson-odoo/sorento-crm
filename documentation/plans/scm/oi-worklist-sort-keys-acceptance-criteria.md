## UAC: order inquiry worklist - SPO, Agent, Instruction columns sort

- AC-1 Sorting the order inquiry worklist by SPO (`spo_number`), Agent (`agent_code`)
  or Instruction (`verb`) returns 200, both ascending and descending.
- AC-2 The SPO sort orders rows by the row's own first linked SPO number (own link,
  earliest `linked_at` then `id`); a row with no own link but a `spo_ref` sorts by
  that ref instead; a row with neither sorts last in both directions.
- AC-3 The route's `WorklistSort` Literal and the service's `SORTABLE_FIELDS` still
  agree, and every advertised key answers 200.
- AC-4 No frontend column id changes - existing saved column layouts (keyed by column
  id) are unaffected.
