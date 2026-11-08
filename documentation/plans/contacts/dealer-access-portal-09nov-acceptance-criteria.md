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
A4. Word fallback (both scopes): a written name that no account contains as a phrase offers, as a pick, the active
    accounts (own accounts in own scope) of the row's company whose name shares at least one significant word (3+
    letters, company suffix words like sdn, bhd, berhad, enterprise, trading, co, company, plt ignored), ordered by
    the number of shared words then code, at most 10 (+ "more"). With no such account: `No customer named "<name>"
    in your accounts.` (own scope) / today's text (broad).
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
A11. One audit row per contact (event `contact.access_agent`, actor the confirming user); a created contact says so.

## B. Respond.io (V8)

B1. Confirming a grant whose contact has no `respond_io_id` enqueues `ensure_respond_contact(contact_id)` on the
    `respond_io` queue, after the commit. A contact that has one enqueues nothing.
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

## D. Permission

D1. Migration grants `user_management.contacts.edit_own` to role `salesperson` (idempotent) and seeds the two owner
    tags when no tag of that name (case-insensitive) exists; an existing tag of that name is left untouched.

## E. Not changed

E1. `.edit` holders: grant, find and update behave as before except A4 (word fallback, offered picks only) and A5
    (no facet is skipped any more) and A9.
E2. The admin access sheet upload (`contact_access_sheet_service`) is unchanged.
