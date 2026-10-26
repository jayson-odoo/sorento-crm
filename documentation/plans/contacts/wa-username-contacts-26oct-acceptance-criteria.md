# UAC - WA-USERNAME-CONTACTS (a WhatsApp username-only contact taps Share Contact Info and joins the contact that holds its access)

Status: APPROVED rules. Owner rulings 27 Oct ~00:55 on `CARD-wa-username-contacts-26oct.md` section 9: Q1 button
only (no code path; typed numbers never accepted), Q2 auto-merge by API, Q3 template text "Hi there, please share
your phone number with us" through the CRM's template-default mapping (no hard-coded template), Q4 no bot reply to a
card from a linked contact, Q5 prod direct ingress mode is `all` (no ingress change). Rule 3 confirmed on two live
payloads (tap and hand-shared card, crew 27 Oct). Plan + contract: `PLAN-wa-username-contacts-26oct.md`.

Test data is fake (public repo): Respond.io ids like 900000001, phones +60100000001, names CONTACT A. Respond.io is
a stub in every test; no test calls Respond.io or sends WhatsApp.

## Words
- **Card**: an inbound message whose Respond.io body has `message.message.type == 'contact'`.
- **Linked**: a CRM contact (`respond_contacts`) has `respond_io_id` = the turn's Respond.io contact id (the
  query the AI-allowed gate uses, whatever its `chatbot_allowed` value).
- **Unknown phoneless**: not linked, AND the turn envelope's contact block has no phone.
- **Accepted card** (STRICT, crew ruling 27 Oct + security review): a card that arrived through the CRM's own
  HMAC-signed Respond.io webhook (`envelope.ingress == DIRECT_INGRESS`, set only by `direct_ingress.envelope_for`
  after `skip_reason` required `hmac_signed`), with `message.message.contact.origin == 'contact_request'`, a
  non-empty `message.message.contact.phone`, AND a present `channel.meta.wa_id` with `normalize_msisdn(wa_id) ==
  normalize_msisdn(contact.phone)`. A missing wa_id is NOT accepted.

## Gate (before the parser)
- WU1 A card never reaches the parser or any business answer, whoever sends it (linked or not). The turn is
  recorded with one of the branch kinds `phone_ask`, `phone_linked`, `phone_ignored`, `phone_handoff`.
- WU2 [Q4] A card from a linked contact (accepted or not): no reply, no Respond.io call, no CRM write.
- WU3 Any message (card or not) from an unknown phoneless contact never reaches the parser or a business answer.
  The turn is recorded with one of the four phone branch kinds (WU1).
- WU4 A not-linked contact WITH a phone in the envelope is not this flow: today's behaviour is unchanged.
- WU5 A test / console (dry-run) turn takes the same decisions but makes no Respond.io call.
- WU20 Only WhatsApp turns take the phone flow: the envelope's `channel.source` (or `channel.type`) read through
  `chat_history_ingest_service.normalise_channel` must be `whatsapp` (an empty source counts as WhatsApp, as there).
  An unknown phoneless contact on any other channel (e.g. WeChat, Messenger) is unchanged (today's silent close).

## Ask
- WU6 [Q3] An unknown phoneless contact whose message is not an accepted card gets the ask: the Respond.io
  template mapped to use case `wa_phone_share` in the CRM's template-default mapping (Settings), sent to that
  Respond.io contact. The template text lives in Respond.io / the mapping, never in code.
- WU7 At most 3 asks per contact in any rolling 24 h. The message that would be the 4th ask instead hands the
  chat to staff (WU13); after that, no further ask or hand-off for that contact until the 24 h window frees a slot.
- WU8 No template mapped for `wa_phone_share`: no ask is sent; the chat is handed to staff (WU13), at most once
  per contact per 24 h.
- WU9 [Q1] A phone number typed as text is never accepted; it is an ordinary message from an unknown phoneless
  contact (WU6).

## Accept
- WU10 A card from an unknown phoneless contact that is NOT an accepted card (`origin` is `other` or missing,
  phone empty, or `wa_id` present and different) links nothing, merges nothing, writes nothing to Respond.io or
  the CRM, and is answered by the ask (WU6, within WU7).
- WU11 An accepted card from an unknown phoneless contact runs the link (WU12-WU14) with the card's phone,
  normalised to E.164.

## Link
- WU12 Merge: if Respond.io has a contact for that phone (lookup by phone) and it is not the turn's contact, the
  CRM calls `POST /v2/contact/merge` with `contactIds` [phone contact id, turn contact id]. Respond.io keeps the
  OLDER contact whatever the order, so the survivor is read, never assumed: the merge response's `contactId`; if
  the response carries none, a fresh lookup by phone; if that fails too, WU16 (no CRM write; the scheduled sync
  re-points by phone later, `respond_sync_handler.py:241-257`). A CRM row with that phone keeps its row and access
  and its `respond_io_id` becomes the survivor id; with no CRM row for that phone, one is created with the phone,
  the survivor id and the default workspace, and the default agents (as any new contact). The verified line goes
  to the survivor.
- WU13 Staff hand-off = one internal comment on the Respond.io conversation (posted by the CRM through `RespondClient.create_comment`) naming the
  reason (the phone shown only to staff). No assignment (an unknown contact has no routing) and no customer-facing
  line (no approved wording).
- WU14 No merge needed: if Respond.io has no contact for that phone, the CRM sets the phone on the turn's
  Respond.io contact (`PUT /v2/contact/id:<id>` with the E.164 phone), then makes the CRM row for that phone point
  at the turn's contact id: an existing row keeps its access and gets `respond_io_id` = the turn's id; with no row,
  one is created (phone, id, default workspace, default agents).
- WU15 After a successful link, when the linked CRM row has `chatbot_allowed = true`, the contact receives "Phone
  number verified, you may start using the AI" (owner Q5), sent to the surviving Respond.io contact, and the next
  message resolves to that row and its access. When `chatbot_allowed = false` (every new contact, owner ruling
  5 Oct), the customer gets nothing and staff get a comment that the phone is verified and the AI is off.
- WU16 Any failure (a Respond.io lookup/merge/update error or timeout, more than one CRM row for the phone, the
  phone's CRM row on a non-default workspace, or a CRM row that names a workspace while no default workspace exists): no CRM write, no verified line, staff hand-off (WU13). The CRM never
  writes before the Respond.io step succeeds, so nothing is half-linked.
- WU17 A repeat of the same webhook (same message id) does not merge or write twice. A second accepted card after
  linking is WU2.
- WU21 An accepted card always attempts the link, even inside a 24 h window that already holds a hand-off (a
  Respond.io error must not lock the user out for a day). Only the hand-off comment stays once per 24 h: a second
  failed link inside the window writes no second comment.

## Safety
- WU18 Logs never carry a full phone number (masked as the phone sign-in does); the staff comment may.
- WU19 Every Respond.io call in this flow (ask, lookup, merge, phone update, verified line, staff comment) goes
  through `RespondClient` for the default workspace, called by the CRM itself; the turn hands the sender no actions
  (after a merge the turn's contact id no longer exists). Tests stub the client.

- WU22 `POST /api/v1/external/chat/turn` refuses (422) an envelope whose `ingress` is `respond_webhook`: that
  value is the CRM's own signed-webhook marker and no caller may claim it. A card that arrives with any other
  ingress (n8n, poller, retry, console) is never accepted; from an unknown phoneless contact it is answered by the
  ask (WU10).

- WU23 Chat History (System Management > Chat History, turn timeline) names the four phone kinds in words: lane
  `phone_ask` "Asked for a phone number", `phone_linked` "Phone linked", `phone_ignored` "Phone card ignored",
  `phone_handoff` "Phone handed to staff"; status word `phone_ask` "Asked", `phone_linked` "Linked",
  `phone_ignored` "No reply", `phone_handoff` "Handed to staff" (never "Answered"). FE `BranchKind` carries them.

## Not in scope
Typed numbers or one-time codes (Q1); re-pointing chat history rows of the merged-away Respond.io id; n8n; any UI.
