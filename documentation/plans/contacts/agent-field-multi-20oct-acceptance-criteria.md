# UAC: Agent field access as a multi-select (AGENT-FIELD-MULTI)

Plan: `PLAN-agent-field-multi-20oct.md`.

- AC-1 In Edit, with "Set on this tag" on, Agent field access shows two multi-selects, "Allow" and "Deny".
  Each option reads "<agent name>: <readable field label>", e.g. "Incoming Stock Enquiries: ETA delay".
  No raw key such as `eta_delay_date` shows anywhere in the section.
- AC-2 The tag's current entries show as chips in the list matching their Allow / Deny value.
- AC-3 Each chip has an x; clicking it removes the field, and after Save the field is gone from the tag.
- AC-4 A field can be picked once only: once chosen it shows ticked in its own list (picking it again un-picks
  it), and a field in Allow is not offered in Deny (and the other way round).
- AC-5 A tag whose stored list already holds the same field twice shows it once (view and edit), and Save
  stores it once.
- AC-6 The server refuses a save that lists the same field twice (422, "listed twice").
- AC-7 View mode shows "Allow" and "Deny" pills with readable labels, each list only when non-empty.
- AC-8 "Set on this tag" off still removes the whole section; on with no fields picked still saves an empty list
  (today's behaviour).
- AC-9 Usable and unclipped at 375px and 1280px.
