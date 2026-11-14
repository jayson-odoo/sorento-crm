# PLAN: agent mode as a contact tag setting + bulk (AGENT-MODE-TAG)

Status: in progress (small fix track: no migration, no auth/RBAC change, under ~300 lines)

Owner 14 Nov: agent mode settable from a tag, and in bulk on the contacts list.

## What changes

1. Tag setting. `chatbot_agent_enabled` joins `CHATBOT_BOOLS` (`app/services/contact_tag_settings.py:58`).
   That one entry is what every other chatbot switch uses, so validation (`_v_chatbot`), merge
   (`_merge_kind`: TAG-UNION "or", same as AI replies), current value (`_Reader.current`), label and the
   apply writer (`contact_tag_apply._w_columns`) all handle it with no new code. Tag editor checkbox:
   `ContactTagSettings.tsx` `CHATBOT_BOOLS`.
2. Bulk. AI replies is set in bulk by the contacts list "Copy access from contact" action
   (`contact_access_copy_service.SWITCHES`, same snapshot/diff/write loop for one or many targets) and by
   "Apply tag settings". Agent mode joins `SWITCHES`, so both bulk actions carry it with the same
   function as the single contact. The access-sheet import loads only named columns, so the column is
   added to its `CONTACT_COLUMNS` (no lazy load per contact).
3. Chatbot tab. The "Agent mode (auto)" switch shows "From tag X" (or "Tags disagree: X, Y") from the
   contact's tag settings (`GET /contacts/{id}/tag-settings`, `decided_by` / `conflict_tags`), the same
   wording the AI model line uses (`LLM_SOURCE_LINE`).

## Not changed

Agent mode still needs AI replies on (`chatbot/agent/access.py`); a tag that sets agent mode does not
switch AI replies on.

## Tests

- pytest: tag validates/merges/applies agent mode; copy access diff + write carries agent mode.
- vitest: tag editor shows the Agent mode checkbox; Chatbot tab shows "From tag X" on agent mode.
