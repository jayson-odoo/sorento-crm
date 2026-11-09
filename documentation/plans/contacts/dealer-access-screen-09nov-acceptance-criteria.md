# UAC - DEALER-ACCESS-SCREEN (owner approved mock v3, 9 Nov 23:31, option (a), no admin view)

Mock: `dealer-access-screen-mock-v3.html`. Plan: `PLAN-dealer-access-screen-09nov.md`. Rules carried from
`dealer-access-portal-09nov-acceptance-criteria.md` (#2268) unchanged; the texts quoted here are that service's own.
"Own accounts" = active customers whose `sales_agent_id` is one of the user's own active sales agents
(`writes._own_agent_ids`), in the user's granted companies. "Me" = the acting user (holds
`user_management.contacts.edit_own`).

## S. Screen backend (`/api/v1/sales/dealer-access/*`)

S1. Every route requires `user_management.contacts.edit_own` (403 without it). The routes sit under the `sales`
    module guard like the other `/sales` routes.
S2. `GET /accounts?company=SRT|MCH`: my own accounts of that company only (`{id, code, name}`, by code). Another
    salesperson's account of the same dealer never appears. A company I am not granted: 403 (`not one of your
    companies`). A user with no linked sales agent: `[]`.
S3. `GET /people` (DataGrid params `page`, `limit`, `query`; filters `company` (SRT/MCH, repeatable) and `access`
    (owner/employee)): one row per (contact, company) for every contact linked to at least one of my own accounts
    of that company. Row: `contact_id`, `name`, `phone`, `company` (code), `company_name`, `accounts` (my own linked
    accounts of that company only: `{id, code, name, link_id}`), `access` (`owner` when the contact holds that
    company's owner tag (`contact_tag_service.owner_tag`), else `employee`), `owner_tag` (the tag name or null),
    `other_account` (true when the contact has any link that is not my own, `writes._not_own_links`). No field ever
    carries another salesperson's account id, code or name, nor a count of them beyond the boolean. My own
    contact never appears. `query` matches name, phone digits or one of MY account codes (never another account's
    code). Ordered by name then phone; `total` counts rows.
S4. `POST /grant` `{company, account_ids[1..10], people[1..20]: {name, phone, role}}`: every account id must be one
    of my own accounts of `company`, else 422 `Pick one of your accounts.` and nothing is written. Each person is
    checked with the #2268 grant plan (`contact_grant.plan`, args `phone`, `name`, `role`, `companies=[company]`,
    `customer_codes` = the picked accounts' codes) BEFORE anything is written; a duplicate phone in the form (same
    normalised phone) is refused on the later row `Same as row <n>.`. Any refused row: 422 with
    `rows: [{index, error}]` (the plan's own refusal text, e.g. `This number belongs to a staff member.`,
    `This person also has access through another account; ask the office to change their level.`,
    `Already has this access; nothing to change.`), and nothing is written. Otherwise each person is executed with
    the #2268 grant execute (`contact_grant._execute`): same template, owner tag, add-only on a shared contact, one
    audit row per contact (event `contact.access_agent`, actor me), Respond job enqueued for a contact without a
    `respond_io_id`. Response: `rows: [{index, contact_id, created, notes}]` where `notes` carries
    `also has access through another account` when the plan said so.
S5. `PUT /people/{contact_id}` `{company, role, account_ids}`: the contact must be one I may change
    (`writes.contact_in_scope`), else 404 (no oracle). `account_ids` must all be my own accounts of `company`
    (else 422 `Pick one of your accounts.`). The change goes through the #2268 access update
    (`writes._contact_execute`) with `link_customer_ids` = picked accounts not yet linked, `unlink_customer_ids` =
    my own accounts of that company linked now but not picked, and `role` only when it differs from the row's
    current access. Its refusals come back as 422 with the service's own text (C3/A14 `ask the office`, C4 AI
    replies off when the last link goes). An empty `account_ids` is refused `Pick one of your accounts.` (unlink is
    the row action).
S6. Unlink is the server-deferred record action `dealer_access.unlink` (entity type `dealer_access_link`, entity id =
    the `respond_contact_customers` row id, window reversible), permission `user_management.contacts.edit_own`.
    At park time and at commit the link must be one of MY own accounts' links of a contact I may change, else 404.
    The commit runs the #2268 access update with `unlink_customer_ids=[customer_id]` as the requester (audit actor
    the requester), so C4 (last link turns AI replies off) applies. No confirm dialog.
S7. One write path: the routes call only `contact_grant.plan` / `contact_grant._execute` and
    `writes._contact_plan` / `writes._contact_execute` for writes; no route writes a contact, link, tag or access
    type itself.

## F. Screen frontend (`/sales/dealer-access`)

F1. Sidebar MY WORK > "Dealer access", `audience: 'salesperson'`, permission `user_management.contacts.edit_own`.
F2. Portal list layout per mock v3 state 1: PageHeader (title only), ListSearchInput (portal size), LandingToolbar
    with a Filter popover holding Company (my companies) and Access (Business Owner / Employee), clearable; primary
    "Add people" on the right. DataGrid columns Person, Phone, Company, My accounts (PillOverflow), Access (owner tag
    pill, or "Employee"; "also another account" when `other_account`), row menu. Fixed layout, resizable,
    explicit sizes, truncate + title. At 375px the portal card list.
F3. Row menu: Edit, then "Unlink from" one item per own account, red, last. Unlink parks `dealer_access.unlink`
    with the deferred row countdown (no dialog, Cancel).
F4. Add people modal (portal form look): Company (SearchableSelect, my companies, hidden when I have one), My
    accounts (SearchableMultiSelect of `GET /accounts`, clearable, nothing pre-ticked), People rows (name,
    PhoneInput MY, Access select Business Owner / Employee, trash), "+ Add person". Save posts `/grant`; a 422
    `rows` shows each reason under its row and keeps the form; success closes, toasts, refreshes the list.
F5. Edit modal (row click or Edit): same form for one person: Company and Phone read-only, My accounts and Access
    editable; Save puts `/people/{id}`; a refusal shows under the field, the form stays.
F6. Empty state: heading "No people have access yet" + hint, no button. Load error: LoadErrorState with Retry.
F7. No UUID shown anywhere.

## M. #2268 minor (agent)

M1. A grant row READY on the immediately preceding (undecided) card, re-sent by the model on an `all` answer, keeps
    that card's verified company and typed name (A17/A18 hold for every row of the last table, waiting or not): no
    `Say which company...` when the customer is resolved and the company was typed one message earlier.
