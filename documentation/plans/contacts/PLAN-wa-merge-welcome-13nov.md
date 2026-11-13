# PLAN: WA-MERGE-WELCOME (tell the user they can use the AI after the contact merge)

Status: Review (re-sized S by crew after the owner's Integration Logs evidence; small fix track: no migration, no RBAC change, no new ingest surface)

## Owner ask (13 Nov ~18:05)
After the share-contact merge, nothing tells the WhatsApp user they are verified and can start
using the AI assistant.

## What the code already does (discovery)
The step exists in the CRM, not in n8n:
- `sorento_crm_backend/app/services/chatbot/engine.py:4294-4325` (`_phone_unknown_decision`): an accepted
  contact card runs `wa_phone_link.link_phone` (Respond.io merge, `wa_phone_link.py:260-338`), then
  `wa_phone_link.send_verified` to the survivor: `VERIFIED_LINE` when the CRM row has
  `chatbot_allowed`, else `NO_ACCESS_LINE` + staff comment.
- `VERIFIED_LINE = "Phone number verified, you may start using the AI"` (`wa_phone_link.py:39`),
  `NO_ACCESS_LINE` (`wa_phone_link.py:42`).
- `send_verified` (`wa_phone_link.py:211-227`) sends a free-form text through
  `RespondClient.send_message` (`integration_service.py:490`), which goes through the single
  `_post_contact_message` gate (`integration_service.py:402-437`) that applies the per-contact
  `outbound_enabled` switch (`respond_outbound_service.py:46`), and writes one `integration_logs`
  outbox row on success and failure (`wa_phone_link._outbox`, `:132-168`).
- Once per contact: the gate only runs for an unknown phoneless contact; after the link the contact
  resolves to its CRM row, so later chats and the AI-allowed gate never reach it again.

So rules 3a (AI access decides the line), 3b (once), 3c (free-form in the open window),
3d (outbound switch) and 3e (logged) are already met by the shipped code. The owner still saw no
message on prod, so either the send failed (the outbox row says why) or the wording did not read
as "you can start". Next step is the prod outbox row for that turn (crew data request).

## Plain-text phone loop (report only)
A number typed as text is not a contact card (`engine.py:4286-4287`, refusal `not_a_card`), so the
contact gets the share template again, at most `PHONE_ASK_CAP` times per 24 h, then one staff
hand-off. That is the "asked twice" the owner saw; it is capped, not an endless loop. Not changed here.

## Crew asks (resolved)
1. Wording: unchanged, the owner saw no issue with it.
2. Prod outbox row: read by the owner in Integration Logs (below).

## Root cause (owner evidence, prod Integration Logs 13 Nov ~17:58)
The verified line WAS sent, to the contact Respond.io had merged away: `404 Not Found` on
`/v2/contact/id:<merged-away>/message`. Respond.io keeps the OLDER contact; `link_phone` trusted the id
the merge response (or the lookup right after it) named (`wa_phone_link.py`, `_merge_survivor`), so the
line, and the CRM row's `respond_io_id`, pointed at a deleted contact. Wording unchanged (owner).

## Fix
- `wa_phone_link._still_there`: after the merge, GET the named survivor; a 404 means the other merged id
  survived (that one gets the phone written, as before); neither found = failure, no CRM write; any other
  error propagates to the existing Respond.io-failure hand-off.
- `wa_phone_link.send_verified(..., phone=)`: a 404 (nothing delivered) resends ONCE to the contact
  holding the phone (`_holder_of`); never a third try, never to the same id; one outbox row per attempt.
- Engine passes the shared phone to both the verified and the no-access line.

## Tests
`tests/test_wa_phone_link.py` test_mw1..mw9, mw12; `tests/chatbot/test_wa_phone_link_gate.py` test_mw10
(owner case) and test_mw11 (late 404).

## Known, not fixed here
- Prod CRM rows linked before this fix may hold the merged-away `respond_io_id`; a contact whose row
  does is not recognised by the AI gate until the row points at the survivor.
- After a resend to a different holder, the AI-off staff comment still targets the first survivor
  (best effort, logged on failure).
