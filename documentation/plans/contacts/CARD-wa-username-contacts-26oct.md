# Behaviour card - WA-USERNAME-CONTACTS: a WhatsApp username-only contact proves its phone and joins the contact that holds its access

**Owner answers (26 Oct ~22:45, via crew):** Q3 (a) bot asks. Q4 (a) nothing before linking. Q5 wording:
"Hi there, please share your phone number with us" / "xxxx is your verification code, please paste your code here" /
"Wrong code, please try again" / "Phone number verified, you may start using the AI". Merge survivor = the contact
WITH the phone number (owner tested in Respond.io). Q1 leaning (c) ("the sorento number is verified"), Q2 asks
whether Respond.io has a merge API: both open pending research round 2 (section 8).

Lane WA-USERNAME-CONTACTS, size L, 26 Oct 2026. Card before any code. Researched on main `36f571df3b`, static
reading only: no DB, no Respond.io call, no n8n call. Backend paths under `sorento_crm_backend/`. People are
CONTACT A / B, phones +6010000000x (fake).

## 1. What happens today (verified)
- **Contact sync skips it, silently.** The scheduled pull `respond_contacts_sync` (`app/scheduler/task_scheduler.py:763`)
  drops a contact with no phone: `if not phone: failed += 1; continue` (`app/services/respond_sync_handler.py:213-215`),
  no log line, no integration log row. The n8n push route rejects it with 400 `"phone_number or phone is required."`
  (`app/api/v1/external/respond_contacts.py:48-53`). The table cannot hold it anyway: `respond_contacts.phone_number`
  is `unique=True, nullable=False` (`app/models/access.py:268`).
- **The chatbot denies it.** Chat turns resolve the contact by the Respond.io contact id, not the phone
  (`app/services/field_access.py:218`, `:278`). Access needs a CRM row with that id (`app/services/mcp_access_service.py:72`);
  none exists, so `deny_unknown_contact` -> `branch_kind = "access_denied"` (`app/services/chatbot/engine.py:6352-6353`)
  -> reply `"Sorry, you are not allowed to access {{team}}"` (`app/services/chatbot_reply_copy.py:104`). A dealer
  who switched to a username therefore reads "not allowed" with no way forward.
- **Access hangs off the CRM contact row** (`respond_contacts.id`): customer links, access types, agent grants,
  location policy, brands (`app/models/access.py:32`, `:92`, `:472`, `:895`). The phone is only the sync match key
  (`respond_sync_handler.py:241`) plus a copy on agent grants (`access.py:476`).
- **The CRM already follows a Respond.io id change by phone.** The sync finds the CRM row by phone and overwrites
  its `respond_io_id` with whatever Respond.io now reports for that phone (`respond_sync_handler.py:241-257`). So once
  the Respond.io contact the user writes from carries the phone, the CRM row re-points on the next sync run with no
  new code (sync interval is a DB setting, UNVERIFIED).
- No code anywhere handles BSUID, WhatsApp username or a Respond.io merge (grep `bsuid|whatsapp_username|merge`
  over the backend: none).

## 2. Respond.io and Meta (official docs where reachable)
- Meta: username users arrive with a BSUID (`user_id`); the phone is included only if, in the last 30 days, the
  business messaged/called that number, the user messaged/called the business, or the number is in the business's
  Meta contact book (developers.facebook.com/docs/whatsapp/business-scoped-user-ids).
- Respond.io: contacts created after Apr 2026 carry BSUID/username in the message webhook `channel` block; if the
  Meta contact book is OFF, Respond.io "will not be able to match" username users to existing contacts and makes a
  duplicate (respond.io/help/whatsapp/whatsapp-business-platform-api-channel-configuration).
- **Merging: CORRECTED in round 2 (section 8).** Round 1 said UI-only; wrong. The API has `POST /v2/contact/merge`.
  Merge *suggestions* are UI-only: Respond.io suggests a merge when two profiles share a phone or email
  (respond.io/blog/merge-contacts).
- Setting the phone: `PUT /v2/contact/{identifier}` takes `phone` (we already PUT custom fields there,
  `respond_sync_handler.py:311`). Behaviour when the phone is already on another contact (error vs merge
  suggestion): UNVERIFIED. The official API reference pages did not load from here.
- Meta's "request contact info" button exists (Jul 2026); Respond.io offers it only on Marketing/Utility templates.
  Whether the number it shares is the user's own, attested by WhatsApp: UNVERIFIED.

## 3. Proposed rules (step by step)
1. **Detect.** A chat turn whose Respond.io contact has no CRM row AND no phone in the turn's contact block (the
   n8n spine posts the whole Respond.io message, contact block included) takes a new `phone_needed` branch instead
   of `access_denied`. A contact with a CRM row is never asked.
2. **Ask.** The bot asks for the phone number (wording: owner). Any reply holding one phone number moves on;
   anything else repeats the ask, at most 3 times, then hands to staff (step 7).
3. **Prove ownership** (Q1). Recommended: a 6-digit code sent as a WhatsApp authentication template to the typed
   number. If the number really is the user's, it lands in the SAME WhatsApp app (one account); they type it back.
   Code valid 10 min, 3 tries; at most 3 codes per contact and per number per day.
4. **Fill the phone.** On a correct code, the CRM PUTs the phone onto the user's Respond.io contact.
5. **Find the merge candidate.** CRM looks up `respond_contacts` by that phone (unique, so 0 or 1 row).
   - 1 row (the contact with access) -> step 6.
   - 0 rows -> the next sync creates the CRM contact with that phone (no access, as for any new contact today);
     staff configures access as usual.
6. **Merge** (Q2). Respond.io now sees two profiles with one phone and suggests the merge. The bot leaves a comment
   on the conversation ("verified +60...; merge with CONTACT A") and assigns it to the contact's CS routing, using
   the spine's existing comment and assign actions. Staff clicks Merge in Respond.io. The CRM row follows the
   survivor's id by phone (section 1, no new code; or re-checked on the next turn so the user need not wait).
7. **Access works.** The next message resolves to the CRM row with access. Before that, the user gets only the ask
   / code / "a team member will help" lines (Q4).

## 4. Cases (realistic, fake identities)
| # | Case | Today | Proposed |
|---|------|-------|----------|
| 1 | CONTACT A, dealer with access, adopts a username after 30+ quiet days; Respond.io makes a phoneless twin | sync skips; bot: "not allowed to access stock enquiries" | ask -> code to +60100000001 -> typed back -> phone set -> staff merges -> stock answers |
| 2 | CONTACT B, new end user, username only, number not in CRM | same denial | ask -> code -> phone set -> sync creates CRM contact (no access) -> staff configures as today |
| 3 | CONTACT C types CONTACT A's number | n/a | code goes to CONTACT A's WhatsApp; C cannot answer; 3 wrong -> stop + staff note; A sees one unexpected code message ("do not share") |
| 4 | User ignores the ask or refuses | denial every time | ask x3, then assign to staff with a note; no access meanwhile |
| 5 | Dealer chats weekly (inside 30 days) or contact book ON | works | Meta includes the phone, Respond.io matches, the flow never triggers |

## 5. Edge cases
- Number already on another CRM contact: that is case 1 (merge). Two CRM rows with one phone cannot exist (`access.py:268`).
- Number with no CRM contact: case 2.
- Wrong number typed by mistake: code goes to a stranger; user retypes; daily caps stop spam and cost.
- Format: `0123...`, `+6012...`, `6012...` normalised to E.164 before lookup; non-MY numbers allowed.
- Group chats: the flow runs only for one-to-one contacts; whether our WhatsApp channel delivers groups at all is UNVERIFIED.
- History under the merged-away Respond.io id (chat turns, conversation frames, chat facts, chat histories,
  media usage; all loose strings, `chatbot_turn.py:84`, `conversation_frame.py:36`) stays under the old id; the
  conversation memory of the losing id is not carried over. Re-pointing it is optional (say if wanted).
- User later changes number: Meta regenerates the BSUID (third-party source, UNVERIFIED); the flow simply runs again.

## 6. Questions (at most 5)
**Q1 Ownership proof.**
(a) one-time code by WhatsApp authentication template to the typed number: strong and automatic; costs one Meta
authentication charge per code (MY rate UNVERIFIED), a one-time template approval, and a send path.
(b) staff approves (calls the number or asks the salesperson): no Meta cost, hours of delay, a judgement call.
(c) Meta "request contact info" button: no typing, cheapest, BUT Respond.io offers it only on Marketing/Utility
templates and whether the shared number is WhatsApp-attested is UNVERIFIED.
**Rec (a)**: the only option that proves ownership without a person's judgement; staff then merge mechanically.

**Q2 Merge.** (Round 1 text; superseded by section 8: the merge API exists.)
(a) staff merges in Respond.io on the bot's comment + assignment; the CRM follows by phone with no new data model.
(b) no Respond.io merge: the CRM contact carries a second Respond.io id (new column or table, history re-point, two
inboxes stay split in Respond.io).
**Rec (a)**: Respond.io suggests the merge itself once both profiles share the phone; (b) adds a data model and leaves Respond.io split.

**Q3 Who asks.** (a) the bot, as above. (b) staff ask by hand; the bot only replaces "not allowed" with a "team
will contact you" line and assigns the chat. **Rec (a)**: the owner asked for a process the user can finish alone, except the merge click.

**Q4 Before linking.** (a) nothing but the ask / code / hand-off lines. (b) also answers open to everyone (e.g. End
User promotions). **Rec (a)**: an unproven user gets nothing; (b) needs a per-agent "public" rule that does not exist.

**Q5 Wording (owner writes).** Five lines: ask for the number; code sent; code wrong / expired; verified, waiting for
the team; handed to the team. Plus the authentication template text (Meta's fixed format: code + "do not share").

## 7. Owner checks (facts only Respond.io shows, not decisions)
- Respond.io > Settings > Channels > WhatsApp: is the Meta contact book ON? If OFF, every quiet dealer who adopts a
  username becomes a phoneless twin; ON cuts case 1 sharply.
- One test merge on a Respond.io test pair: which contact id survives? (Rule 6 works either way; the answer decides
  whether the CRM row's id changes.)

## 8. Research round 2 (26 Oct ~23:00, after the owner's answers)
Sources: Meta BSUID page (P1) https://developers.facebook.com/documentation/business-messaging/whatsapp/business-scoped-user-ids;
Meta auth templates (P2) https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/authentication-templates/authentication-templates;
Respond.io help/changelog pages named below. developers.respond.io is a script-rendered site: its API facts come
from search snippets of the official pages, not a full page read (marked "snippet").

**Share Contact Info button (Q1 option c).**
- P1: "If a user taps this button, their WhatsApp phone number will be shared in the message thread", i.e. the
  number of the WhatsApp account that taps, not a number the user types or picks. A contact card the user shares by
  hand is a different message: P1 changelog 4 May 2026, "vCard is only included when a user shares a contact
  directly, not when tapping the `REQUEST_CONTACT_INFO` button"; the webhook marks the two with `origin`
  (`contact_request` vs `other`; field name from a page summary, exact text UNVERIFIED).
- Security rule that follows: accept a number ONLY from a button tap, never from a hand-shared contact card (a user
  could share a dealer's card).
- Verified business: P1 does not tie the button or the phone reveal to business verification; "verified name"
  appears only in the display-name rules. Being verified changes nothing here.
- Respond.io: "available in Marketing and Utility message templates" (https://roadmap.respond.io/changelog/whatsapp-usernames-and-business-scoped-user-ids-bsuids-are-here);
  label fixed "Share Contact Info" (https://respond.io/help/whatsapp/whatsapp-message-templates). Meta also allows
  it as an interactive message (P1), but Respond.io documents only the template route.
- UNVERIFIED: what Respond.io hands on after a tap: does it fill the contact's phone itself, and does the `origin`
  marker reach the message webhook / our chat turn? This decides whether (c) is safe to automate (owner test below).
- Cost: one Utility template per ask. Meta's price for a Utility template inside an open service window: UNVERIFIED this round.

**Authentication template (Q1 option a, Q5 line 2).** P2: body is "Fixed, non-customizable preset text":
"<VERIFICATION_CODE> is your verification code." + optional "For your security, do not share this code." + optional
footer "This code expires in <NUM_MINUTES> minutes." "please paste your code here" CANNOT go in the template; it
would be a separate bot message right after it. Auth templates must go to a phone number, not a BSUID (P1; Respond.io
help snippet "Authentication templates must be sent using a phone number").

**Merge API (Q2).** `POST /v2/contact/merge`, body `contactIds` (two ids) plus optional name/phone/email/language;
"older contact becomes primary" (snippet, https://developers.respond.io/docs/api/3c34d8547c5c9-merge-two-contacts).
Matches the owner's test (the contact with the phone survives). The Respond.io n8n node also lists "Merge Contact"
(https://respond.io/help/integrations/n8n). No merge-suggestion endpoint. Also `GET /v2/contact/{identifier}/channels`
(snippet, https://developers.respond.io/docs/api/a17bccb520d2e-list-contact-channels).
Consequence: survivor = the phone contact, so the CRM row keeps its `respond_io_id` and access works on the next
message with no CRM re-point.

**Meta contact book (owner check).** Meta-side, not Respond.io: Meta Business Suite > Business settings > Business
info > "Contact book for WhatsApp" (https://business.facebook.com/latest/settings/business_info). Respond.io: "It is
enabled by default." / "If this feature is turned off, respond.io will not be able to match Contacts who use WhatsApp
usernames" (https://respond.io/help/whatsapp/whatsapp-business-platform-api-channel-configuration, Best practices).
P1: turning it off deletes what it stored. If ON, anyone who ever messaged us keeps their phone visible, so the flow
mostly meets genuinely new people.

**Updated recommendations.**
- Q1: (c) Share Contact Info button, IF a 5-minute owner test shows the tap is distinguishable from a hand-shared
  card (Respond.io fills the phone only on a tap, or the `origin` marker reaches the message webhook). Then the flow
  is: template "Hi there, please share your phone number with us" + [Share Contact Info] -> tap -> merge -> "Phone
  number verified, you may start using the AI". No code, nothing to type, no wrong-code loop. If the test shows the
  two look the same: (a) code, with "please paste your code here" as a separate message.
- Q2: merge by API right after the proof, no staff click; staff only when the merge call fails (comment + assign).

## 9. FINAL flow (27 Oct ~00:40; supersedes sections 3 and 6)
**Owner test (27 Oct ~00:20):** Utility template + [Share Contact Info] sent from Respond.io, owner tapped it. Chat
shows an inbound contact card; Respond.io did NOT fill the contact's phone. **Crew read the live payload** (n8n
sender exec 21883768, read-only): `message.message = {type: 'contact', contact: {cId, phone: '<number>',
origin: 'contact_request', payload: null, firstName}}`; envelope `contact.phone` = null; `channel.meta` carries
`wa_id: '<same number>'` and `user_id: 'MY.<...>'` (the BSUID). It reached the CRM by direct ingress, not n8n (the
n8n Respond.io Trigger takes text/attachment only). Side bug seen: the bot read the card as a business question and
resent a stale answer. Pending: owner's hand-shared-card test (expected `origin: 'other'` + vCard `payload`).

**Where the event enters the CRM (verified).** `POST /api/v1/public/respond/webhook`
(`app/api/v1/public/respond_webhook.py:335`) -> HMAC check -> `map_webhook_message` (`:152`) stores the row ->
`chat_turns.enqueue_direct_turn` (`:322`; `app/tasks/chat_turns.py:113`) -> `direct_ingress.skip_reason`
(`app/services/chatbot/direct_ingress.py:145`; in queue mode non-text types pass, `:193`) -> `envelope_for`
(`:297`) hands the engine the Respond.io body verbatim, so `message.message.contact.origin` is readable in the turn.

**Rules.**
1. **Gate before the parser.** Every turn first checks: is `message.message.type == 'contact'`? Then it is handled
   by the phone-link step below and never parsed or answered as a business question (fixes the side bug, for
   every contact, linked or not). The access check runs only after the parser (`app/services/chatbot/engine.py:3981`),
   so the gate must sit ahead of it.
2. **Detect.** The contact has no CRM row (`field_access.resolve_contact_with_null_workspace_fallback`,
   `app/services/field_access.py:278`) and the envelope's `contact.phone` is empty -> no parser, no business
   answer; the CRM sends the Utility template with [Share Contact Info] (Q3 below) through the existing template
   send (`RespondClient.send_template_message`, `app/services/integration_service.py:682`; template picked by a
   template-default use case, `app/services/respond_template_service.py:444`, so the owner maps it in Settings).
   At most 3 asks per contact per 24 h (counted from `chatbot.turns.branch_kind`, `app/models/chatbot_turn.py:99`);
   after the 3rd, comment + assign to staff (existing `create_comment` `:472`, `set_conversation_assignee` `:583`).
3. **Accept a number ONLY when** `message.message.type == 'contact'` AND `contact.origin == 'contact_request'`
   AND `contact.phone` is non-empty AND (when `channel.meta.wa_id` is present) `wa_id == contact.phone` after
   `normalize_msisdn` (`app/services/phone_utils.py:22`). Anything else (hand-shared card `origin: 'other'`,
   typed number, mismatch) is never accepted: the bot repeats the ask (counts toward the 3).
4. **Find the match.** CRM row by phone (`respond_contacts.phone_number`, unique, `app/models/access.py:268`) and
   the live Respond.io contact for that phone (`RespondClient.get_contact_by_phone`, `integration_service.py:384`).
5. **Merge (Q2, auto).** If a Respond.io contact with that phone exists and is not this one:
   `POST /v2/contact/merge` `{contactIds: [<phone contact id>, <username contact id>]}` (new `RespondClient.merge_contacts`;
   older = primary = the phone contact, as the owner tested). The CRM row keeps its `respond_io_id`; no CRM re-point.
   The reply after the merge goes to the survivor id.
6. **No match.** No Respond.io contact with that phone: `PUT /v2/contact/id:<username id>` `{phone}`
   (`RespondClient.update_contact`, `integration_service.py:738`), then create the CRM row now, not at the next sync
   (`ContactService.create_contact`, `app/services/contact_service.py:397`, which assigns the default agents, `:428`).
7. **Reply** "Phone number verified, you may start using the AI" (owner Q5 line 4). The next message resolves to the
   CRM row with its access.
8. **Failure** (merge/PUT error, phone already on a CRM row in another workspace): comment + assign to staff; the
   user gets the hand-off line; nothing half-linked (the CRM writes only after Respond.io succeeds).

**Security.** The number comes from WhatsApp, not the user: only a tap yields `origin: 'contact_request'`; a user
can type text or hand-share any card, never forge `origin` (Meta sets it; the CRM accepts it only from an HMAC-signed
webhook, `direct_ingress.py:174-178`). The wa_id cross-check adds a second Meta field. No reply reveals whether a
number is known (same line either way). Merge is the irreversible step (only Respond.io Owners/Managers unmerge),
so it runs only after rule 3 passes. security-reviewer runs on the PR.

**Cases (fake identities).**
| # | Case | Result |
|---|------|--------|
| 1 | CONTACT A (dealer, access) on a username, taps the button | origin ok -> merge into A's phone contact -> verified line -> stock answers |
| 2 | CONTACT B, new person, taps | no match -> PUT phone, CRM row created with default agents -> verified line |
| 3 | CONTACT C hand-shares CONTACT A's card | origin 'other' -> refused, ask again; after 3 asks -> staff |
| 4 | CONTACT A (already linked) shares a colleague's card | gate catches it; no business answer, no link (Q4) |
| 5 | CONTACT D ignores the ask, keeps typing questions | ask x3 in 24 h, then staff; no access meanwhile |

**Questions (final).**
- **Q1 (proof):** (c) button with rule 3, no code path in v1 (owner lines 2-3 unused); a typed number is never
  accepted, the bot re-asks. Alternative: also build (a) code for typed numbers (reuses the portal OTP machinery,
  `app/services/portal_service.py:553`, `phone_signin_service.py`: hashed codes, 10 min, cooldown, 5-try lock).
  **Rec (c) only**, pending the hand-shared-card test; (a) only if a real user cannot tap (UNVERIFIED that any
  WhatsApp client lacks the button).
- **Q2 (merge):** auto-merge by API after rule 3. **Rec yes.**
- **Q3 (template text):** the approved Utility template body: owner's test text "Hi, please share you contact info
  to access the system." or Q5 line 1 "Hi there, please share your phone number with us"? Owner creates/names it in
  Respond.io (Meta approval) and maps it. **Rec** Q5 line 1 (typo-free).
- **Q4 (card from a linked contact):** (a) no bot reply, staff see it in Respond.io; (b) a short "noted" line.
  **Rec (a).**
- **Q5 (ingress prerequisite):** the tap only reaches the turn by direct ingress, which covers a contact only when
  `chatbot_direct_ingress_mode` is `all` or the contact is listed (`direct_ingress.py:139-142`, `:170-173`); a new
  username user is never listed. Prod mode UNVERIFIED (crew can read it). (a) mode `all` already: nothing to do;
  (b) a narrow code exception: a `type: 'contact'` message from an HMAC-signed webhook starts a turn whatever the
  mode; (c) add `contact` to the n8n Trigger (owner publishes). **Rec (a) if already `all`, else (b)** (no n8n change).
