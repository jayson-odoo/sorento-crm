# UAC - DEALER-ACCESS-PORTAL (draft on the card's (a) answers; final once the owner answers Q1-Q5)

Card: `CARD-dealer-access-portal-09nov.md`. Mock: `dealer-access-portal-mock.html`. Plan: `PLAN-dealer-access-portal-09nov.md`.

## Who and what they see

U1. A user with `user_management.contacts.edit_own` and at least one active sales agent linked to their contact
    (`users.respond_contact_id` = `sales_agents.contact_id`) sees MY WORK > "Dealer access". A user without the
    permission does not see the item, and every endpoint below answers 403.
U2. The company tabs show only companies the user is granted. Each tab lists, for every active customer of that
    company whose `sales_agent_id` is one of the user's agents, each linked contact (one row per contact per
    account): name, phone, account code + name, level (Business Owner when the contact holds an owner type of that
    company, else Employee), WhatsApp (Linked when `respond_io_id` is set, else Waiting), who added the link and when.
U3. A customer of another salesperson's agent never appears, not in the list, the account picker, or any message.
U4. Empty tab: heading "No dealer people yet", hint "People you add to your customers appear here.", no button.

## Grant

U5. "Add people" opens the modal for the active tab's company. Accounts lists only the user's own active accounts
    of that company, none pre-ticked; at least one is required.
U6. 1..20 person rows, each Name (required, max 255), Phone (required), Access (Business Owner / Employee, required).
U7. Phone is normalised to `+601XXXXXXXX`; a stored `01...` or `+60...` with the same digits is the same person.
    A non-Malaysian-mobile phone is refused on its row: "<as typed>" is not a Malaysian mobile number.
U8. Refused on its row: a phone held by two contacts; the user's own phone; a phone that is any CRM user's contact
    or any sales agent's contact ("This number belongs to a staff member."); the same phone twice in one form.
U9. Submit with any row refused writes nothing and shows each row's reason; otherwise every row applies in ONE
    transaction.
U10. A row applies the 26 Oct template for the company and level through `contact_setup_engine` (access types,
    company, brands, stock, segment, image media, 3 enquiry agents, switches), the WHOLE template, regardless of
    which of those facets the user could set by hand, add-only; and links the contact to every picked account
    (`source = 'portal'`, `linked_by` = user). A new phone creates the contact (default workspace, default agents).
U11. One audit row per person (`contact.dealer_access_grant`, entity `respond_contacts`, actor the user, before and
    after per facet, "Contact: created" when new).
U12. A person already linked to an account the user does not own shows "Also has access through another account." and
    still applies; the other account is not named anywhere in the response.
U13. Re-submitting the same people for the same accounts changes nothing and says so per row ("Already has this
    access.").

## Respond.io

U14. After commit a job on the `respond_io` queue looks the phone up in Respond.io; found: stores `respond_io_id`;
    not found: creates the Respond contact (phone, first name) and stores its id; then writes `backend_id` as the sync
    does. No message is sent. Failure retries; the row stays "Waiting".
U15. With no Respond.io API key configured (dev, tests, CI) the job is a logged no-op; no test calls Respond.io.

## Remove and change level

U16. Remove on a row unlinks the contact from THAT account after the 5 s deferred window (Cancel restores); when it
    was the contact's last customer link, `chatbot_allowed` becomes false. Audit row.
U17. Change level Employee -> Business Owner adds that company's owner types. Business Owner -> Employee removes that
    company's owner types, refused when the contact is linked to an account of that company outside the user's own
    ("Ask the office: this person is also an owner for another account."). Audit row.
U18. Remove and change are refused (403) for a contact not linked to any of the user's accounts.

## Not changed

U19. The admin access sheet upload and the WhatsApp agent `crm_contact_grant` behave exactly as before.
U20. Usable and not clipped at 375px and 1280px.
