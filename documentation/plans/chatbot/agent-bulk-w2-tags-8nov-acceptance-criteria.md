# UAC: agent bulk wave 2, contact tags from a pasted table (AGENT-BULK-W2-TAGS)

Plan: `PLAN-agent-bulk-w2-tags-8nov.md`. Test numbers in brackets are the pytest names in
`sorento_crm_backend/tests/chatbot/agent/test_agent_bulk_w2_tags.py`.

- T1 (01) `crm_contact_tags` is a batchable WriteDef, slug `user_management.contacts.edit`; `crm_batch_propose`
  offers it next to `crm_contact_grant`; without the slug neither is offered and a call is denied.
- T2 (02) A row = phone + tags to add and / or remove. The contact is found by phone in either stored form; the
  preview row shows phone, name, and "Will change": `add tag X`, `remove tag Y`, the settings that change.
- T3 (03) Tag by exact name, case and spaces aside. An exact name wins even when longer tag names contain it
  ("Mocha Dealer" -> Mocha Dealer, never Mocha Dealer Tag).
- T4 (04) A name that is not exact but is contained in active tag names: the row waits under Needs your choice
  with those tags (max 10, by name), nothing is picked on its own, even one candidate. The pick is a chat reply;
  a re-proposal with a tag that was neither listed for that row, nor already exact in the row, nor typed by the
  user this turn is Not changed.
- T5 (05) Not changed, every reason of the row listed: no phone "Give the phone"; a phone no contact holds; two
  contacts hold it; "No tag named X"; "Tag X is inactive"; the same tag added and removed; no tag named at all;
  "Already tagged; nothing to change".
- T6 (06) Add applies the added tags' settings, as the bulk-tag dialog's default: the preview lists the
  changed settings; a section the acting user (and the console operator) may not write is listed as
  "not applied (needs more access)" and is not written; a conflict between tags is listed and not written.
  Remove changes membership only.
- T7 (07) Confirm writes each row in its own transaction: memberships, settings, the screen's audit rows
  ("Tag added: X" / "Tag removed: X") and one `contact.tags_agent` row per contact. A row whose tags or settings
  changed since the preview fails alone; the other rows still apply. A second confirm changes nothing.
- T8 (08) The reply carries the code-built tables (Ready / Needs your choice / Not changed); the waiting table's
  pick column says "Tag" and the closing line asks for the tag name(s); the grant wording stays unchanged.
- T9 (09) A Not changed "No tag named X" backs the reply's "no tag named X" wording (no repair round).
