# UAC - DEALER-ACCESS-PORTAL v2 (owner answers 9 Nov ~00:50: Q1 b tags, Q2-Q5 a; agent path first)

Card: `CARD-dealer-access-portal-09nov.md` section 0. Plan: `PLAN-dealer-access-portal-09nov.md`.
"Own scope" = the acting user holds `user_management.contacts.edit_own` and NOT `user_management.contacts.edit`.
"Own accounts" = active customers whose `sales_agent_id` is one of the user's own active sales agents
(`writes._own_agent_ids`), in the user's granted companies.

## A. Grant (agent tool `crm_contact_grant`, single row and through `crm_batch_propose`)

A1. An edit_own holder (no `.edit`) can propose and confirm `crm_contact_grant`. A user with neither slug cannot
    (the tool is not offered and a direct propose is refused).
A2. Own scope, customer codes: a code of an own account resolves; a code of an account that exists but is not own is
    refused with exactly the same text as a code that does not exist: `No customer with the code "<code>" in your
    accounts.` (no oracle).
A3. Own scope, customer names: an exact name of exactly one own account resolves; a name fitting several own accounts
    (phrase match) waits for the pick, and the candidates are own accounts only, even when other salespeople's
    accounts carry the same name. Never linked on a name alone when more than one fits.
A4. Word fallback (own scope only): a written name that none of the user's own accounts contains as a phrase offers,
    as a pick, the user's own active accounts of the row's company whose name contains the FIRST significant word of
    the written name as a whole word (3+ letters; company suffix words like sdn, bhd, berhad, enterprise, trading, co, company, plt
    ignored), ordered by the number of shared significant words then code, at most 10 (+ "more"). Never linked
    without the pick. With no such account: `No customer named "<name>" in your accounts.` Broad scope (`.edit`)
    keeps today's matching (a generic word such as "hardware" would otherwise offer hundreds of accounts).
A5. The whole 26 Oct template is written on confirm (Q2 a) whatever the confirming user could set by hand: a user
    holding only edit_own (no superadmin, no `inventory.stock.edit`, no `user_management.access_agents.edit`) grants a
    new phone and the contact ends with the company, the stock policy (availability, the template locations), the
    three enquiry agents, `end_user`, the retail segment, image media, AI replies on.
A6. Owner via tag: role owner adds the tag "Sorento Business Owner" (SRT) / "Mocha Business Owner" (MCH) to the
    contact; after confirm the contact holds the tag and the tag's access types (`dealer`, `cabana_dealer` for SRT;
    `mocha_dealer` for MCH). Employee: no owner tag, access types `end_user` only (plus whatever it held). The
    preview names the level ("Business owner (Sorento)").
A7. A missing or inactive owner tag refuses an owner row: `The "Sorento Business Owner" tag is missing; ask the
    office.` An employee row still applies.
A8. Re-granting the same person, level and accounts: `Already has this access; nothing to change.`
A9. Staff phone refused (every scope): a phone that is any user's `respond_contact_id` contact or any
    `sales_agents.contact_id` contact: `This number belongs to a staff member.`
A10. Own scope, a phone already linked to an account that is not own: the row applies (add-only, link added, other
    link untouched), the preview carries the line `also has access through another account`, and no other account's
    code or name appears in the preview, the confirm result, the action record or the audit row.
A12. Own scope: a row that resolves to none of the user's own accounts is refused: `Name one of your accounts for
    this person (code or name).` (review round 1, H1: no grant without an own link).
A13. Own scope, an existing contact linked to any account that is not own: only the additive facets apply (the own
    link, the company, `end_user`, missing enquiry agents, the retail segment). Its switches (AI replies, stock
    replies, ETA offset, hand-over, packing list), stock mode and locations, brands and image media are left exactly
    as they are (another salesperson's or the office's settings are never rewritten).
A14. Own scope, role owner for a contact linked to any account that is not own: refused with the C3 text, in the grant
    and in the update tool (promotion is as restricted as demotion).
A15. The owner tag counts only when its settings are exactly the template's owner types for its company
    (`{"access_types": ["dealer", "cabana_dealer"]}` / `{"access_types": ["mocha_dealer"]}`, order aside); a tag of
    that name with any other settings is treated as missing (A7 text), so a renamed or edited tag can never grant
    more than the template.
A16. Staff phones (A9) also cover a phone equal (by digits) to any user's `contact_number`, and are checked for new
    phones as well as existing contacts.
A17. Every scope: a customer name in a grant row (table or single row) must be what the user typed in this turn's
    message (case and spacing aside, as a whole phrase), or the row's own "You wrote" from the waiting table an "all"
    or pick follow-up re-sends. Otherwise the row is skipped: `"<name>" is not in your message; write the dealer name
    as you typed it.` The waiting table's "You wrote" is the user's text (crew live x3, 9 Nov: a re-searched name was
    shown as written). Every row of the last table counts, ready, not changed and waiting alike: a follow-up that
    re-sends a row with the name it verified then is not refused for it (live x3 round 2: a not-changed row got this
    text instead of its own reason). Names are compared word for word with curly quotes folded to straight,
    punctuation dropped and company suffix words (sdn, bhd, berhad, enterprise, trading, co, company, plt...) ignored
    on both sides ("Ah Huat Motor" typed, "Ah Huat Motor Sdn Bhd" sent; "S’pore" and "S'pore"); the kept "You wrote"
    is the user's own span.
A18. Every scope: each company of a grant row must be named in this turn's message by the first word of its name
    ("Sorento", "Mocha"; case aside, a whole word), or verified for that row by the last table. Otherwise the row is
    skipped: `Say which company this person is for: Sorento or Mocha.` (live x3 round 2: a Mocha row re-sent as
    Sorento).
A19. A row whose customer codes all resolve to the user's accounts in the row's companies is decided by those codes;
    a customer name beside them is only the row's typed label and is not searched again (live x3 structural round: a
    pick answer that re-sent the codes and the typed name raised the pick again).
A11. One audit row per contact (event `contact.access_agent`, actor the confirming user); a created contact says so.

## B. Respond.io (V8)

B1. Confirming a grant whose contact has no `respond_io_id` enqueues `ensure_respond_contact(contact_id)` on the
    `respond_io` queue, after the commit. A contact that has one enqueues nothing.
B3. The job normalises the phone (`normalise_phone`, skips when it is None) and URL-quotes it in the path. A retry
    for a contact that already has its `respond_io_id` still writes `backend_id` (only the lookup/create is skipped).
    A stored action never carries another salesperson's account ids (own scope: own link ids plus a count of others).
B2. The job: no Respond API key resolvable -> returns without any HTTP call. Found by phone -> stores `respond_io_id`.
    Not found (404) -> creates the contact in Respond.io (POST, phone + first name), stores the returned id. Then
    writes the `backend_id` custom field. It never calls a message-send endpoint. An HTTP error other than 404 raises
    (RQ retries).

## C. Change and remove (agent tool `crm_contact_access_update`)

C1. Role owner on a contact of an own account adds the company's owner tag (and so its access types); a missing tag
    refuses as A7.
C2. Role employee removes the owner tags of the contact's template companies and the owner access types; the contact
    keeps `end_user`.
C3. Own scope: demote is refused when the contact is linked to any account that is not own: `This person also has
    access through another account; ask the office to change their level.`
C4. Unlinking the contact's LAST customer link (counted across every company, not only the user's) also turns AI
    replies off in the same change (preview line `AI replies on -> off`). Unlinking one of several links leaves AI
    replies as they are.

C5. Own scope, no leak in the update tool either: the preview, the stored action steps (`shown.link_codes` and every
    other field), the confirm result and the audit row never carry the code or name of an account that is not own;
    such a link reads `another account`.

C6. Own scope, a contact another account also reaches: every settings change in the update tool is refused, not only
    the level (crew live x3, 9 Nov): an AI replies change gets `This person also has access through another account;
    ask the office to change their settings.` The salesperson can still unlink their OWN accounts from that person.
    Tool contract: the dealer name is passed exactly as the user typed it (the pick table echoes it), every row goes
    through the tool (staff phones included), and refusals and skipped reasons are the tool's own words.
C7. Settings the update tool does not change (stock replies, hand-over, packing list, notify salesman, or any other
    setting the user names) are arguments of the tool and are refused by code, the whole call with them, nothing
    changed: `<what> is set by the office; ask the office.` (edit_own) / `<what> is changed on the contact's Access
    tab, not here.` (`.edit`), `<what>` being "Stock replies", "Hand-over", "Packing list", "Notify salesman" or the
    user's own words in quotes. This refusal comes before every other check.

## D. Permission

D1. Migration grants `user_management.contacts.edit_own` to role `salesperson` (idempotent) and seeds the two owner
    tags when no tag of that name (case-insensitive) exists; an existing tag of that name is left untouched.

D2. No migration or seed grants the AI assistant or agent to salespeople (owner 9 Nov ~10:45: "dealer access this one
    you let me control"): the owner switches it on per salesperson (`system.ai_assistant_chat.use` / `.agent`, the
    contact's agent switch). An edit_own salesperson without it gets the normal refusal (`switch_off` on WhatsApp, the
    old panel path in the CRM), no crash.

## E. Not changed

E1. `.edit` holders: grant, find and update behave as before except A5 (no facet is skipped any more), A6/C1/C2 (the
    owner level is the tag) and A9.
E2. The admin access sheet upload (`contact_access_sheet_service`) is unchanged.

## F. Agent replies

F1. No false completion, on dealer-access turns only (F2; a read answer elsewhere is never rewritten): a final reply
    that says a change was made (has or have been granted, given, added, removed,
    linked, unlinked, or turned on or off; I have or I've completed, granted, and so on; all or
    your requested operations, changes or requests are or have been done or completed; access is or has been granted)
    on a turn that proposed no change and decided no waiting one is replaced by: `Nothing was changed: I did not
    propose any change in this turn. Tell me again what to change and I will show it for you to confirm.` A reply that
    asks, lists a proposal, or follows a real confirm or cancel is left as it is. A bare "Done." is not a claim (a read
    turn closes with it too), and neither is "has been updated / changed / set" (an answer about an ETA or an order
    says that). In the F2 flow the model's text is never shown: with no dealer-access tool run, a claim gets the
    fixed reply above and anything else `I need to check that first.`; a tool that ran but proposed and refused
    nothing gets `Tell me the person's phone, Business Owner or Employee, the company (Sorento or Mocha) and the
    dealer, and I will show the change for you to confirm.`; a proposal shows only its card or table; otherwise the
    last refusal of the grant, access change or batch tool, in its own words. A yes or no to a waiting card can still
    confirm or cancel it in the flow.
F2. The dealer-access flow: when the acting user holds a contacts slug, one side call before the first model round
    judges whether the message (with the previous reply, when that was a dealer access table) asks to give, change,
    remove or pick dealer contact access; a judgement of the message, never a word list, and a plain yes or no to a
    waiting change is not one. When it is: that turn's rounds are offered only the dealer-access tools (the batch
    tool for the grant only, the grant, the phone lookup, the access change, and the answer tool to end), a tool call
    required. Its reply is built from the turn's tool results only: the tables, each refusal in the tool's own
    words, what the phone lookup could not use, the confirm card; never the model's own text (so nothing in it is
    marked "not verified"). A turn with no dealer-access tool result is asked once more for the call and then
    answers `I need to check that first.` A user without a contacts slug never gets the side call; a message it does
    not recognise runs as before.
F3. A pick answers only the table of the IMMEDIATELY preceding agent turn, and only when that turn ended with rows
    waiting for a pick: any newer request in between expires it. A code listed only by an expired pick and not typed
    now is refused: `"<code>" is from an earlier list that is closed now; write the dealer name again to see its
    accounts.` The confirm card after a valid pick repeats, for each picked row, `you wrote "<name>"` beside the
    accounts it links. A failed turn in between does not expire the pick (a retried answer still answers it); every
    older table with waiting rows is expired, and a table with no waiting rows is never the pick. A single grant row
    that waits for a pick is a pick too. This immediacy is the grant's only: the tag and customer-agent tables keep
    answering the newest earlier table.
F4. Rows of this message only (grant). When this turn's message names at least one person (a phone in any format,
    012-345 6789, +60 12..., 6012..., or a person's name), the card holds only the rows it names, plus the rows of
    the last table when the turn answers that table's pick (a row with codes the table listed for it, or the user
    typed). When the message names no person, it is a follow-up about the immediately preceding card, decided or
    waiting, so that card's rows may be re-sent ("give them Mocha too", "do the same two with Mocha instead"). A row
    of a decided card keeps its own reason, and codes of an expired pick get the F3 refusal. Any other row the model
    re-sends is left out of the card, the preview and the not-changed list, and returned to the model as `left_out`
    with `Not in this message; ask again with this person's phone to include them.` (live x3: an earlier waiting
    person re-sent into a new request was linked to the older pick).
