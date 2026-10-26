# Behaviour card - WA-USERNAME-CONTACTS: a WhatsApp username-only contact proves its phone and joins the contact that holds its access

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
- **Merging is UI-only.** No merge or merge-suggestion endpoint is documented; Respond.io suggests a merge when two
  profiles share a phone or email; agents merge from the Messages > Channels tab, only Owners/Managers unmerge
  (respond.io/blog/merge-contacts). Which contact id survives a merge: UNVERIFIED.
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

**Q2 Merge.** Respond.io has no merge API (none documented).
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
