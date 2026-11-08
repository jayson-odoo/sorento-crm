# CARD - DEALER-ACCESS-PORTAL: salespeople grant dealer users access themselves, instantly

Status: v2, answered 9 Nov ~00:50 (Q1 b tags, Q2 a, Q3 a, Q4 a, Q5 a; agent path FIRST, screen second). Lane
DEALER-ACCESS-PORTAL, size L. Read of `origin/main` d8a74efc. Section 0 supersedes the v1 sections where they differ.

## 0. v2: owner answers and the agent-first design

Owner (9 Nov ~00:50): Business Owner vs Employee is only the dealer promotions, and it should be a TAG ("don't
reinvent the wheel"). Q2 a, Q3 a, Q4 a (the salesperson can unlink), Q5 a. MAIN CHANNEL: the salesperson sends the
same message they send the owner today (names, phones, Owner/Employee, which dealer) to the AI agent (WhatsApp or the
agent panel); the agent proposes, the salesperson confirms, and access is granted or removed. Fused with the existing
WhatsApp agent tools. The screen follows (one portal list page, company as a filter, portal add/edit design; mock v2
then, on tags and a real masked case).

Rules v2 (replace R1-R10 where they differ):
- V1. The agent tools `crm_contact_grant` (pasted table / message, through `crm_batch_propose`), `crm_contacts_find`
  and `crm_contact_access_update` serve `user_management.contacts.edit_own` holders; the `salesperson` role gets
  that permission (migration). `.edit` holders keep every behaviour they have.
- V2. A salesperson (edit_own, no `.edit`) only ever resolves to THEIR OWN accounts: a code, an exact name, and every
  "which account?" pick list come from active customers whose sales agent is one of theirs, in the row's company.
  Another salesperson's account is never named, offered or linked. A written name that fits several of their accounts
  (a dealer usually has 3 to 9: A/C I, III, CERAMIC...) waits for the pick ("codes, or all"); nothing links on a name
  alone. When the written name matches no account as a phrase, accounts sharing a significant word are offered as the
  pick (still never linked without the pick).
- V3. Level = tag. "Sorento Business Owner" (sets access types dealer + cabana_dealer) and "Mocha Business Owner"
  (mocha_dealer), seeded by migration when absent, editable on the Tags screen. Employee = the template base only, no
  tag. Granting an owner adds the company's tag (TAG-UNION live recompute); demoting removes the tag and the owner
  types it granted.
- V4. The whole template is written for every grant (Q2 a): companies, stock, enquiry agents included, whatever the
  confirming user could set by hand. The template plus the two tags is the limit; the user only picks people, level
  and their own accounts.
- V5. Staff phones refused: a phone that is a CRM user's contact or a sales agent's contact is never granted.
- V6. A person already linked to an account that is not the salesperson's: allowed, add-only, with the line "also has
  access through another account"; the other account never named (Q5 a).
- V7. Remove: unlink from the salesperson's own account(s) (the existing tool); when it was the person's last link
  anywhere, AI replies go off in the same change. Demote Owner -> Employee is refused when the person is linked to an
  account outside the salesperson's own ("ask the office").
- V8. Instant: after a grant commits, a `respond_io` worker job looks the phone up in Respond.io and creates the
  contact there when missing (no message sent), stores `respond_io_id`, writes `backend_id`. No key (dev, CI): no-op.
- V9. Audit: the existing agent action log + one audit row per contact (event `contact.access_agent`), actor the
  salesperson.

Dev data (sorento_prod_1104, crew-data-response 9 Nov): 29 salesperson users reach customers through their agent rows,
up to ~500 accounts each (SRT median 60 among those with any); every `sales_agents` row is shared (company NULL), so
company comes from the customer; 117 linked contacts sit in both companies, 95 of them with DIFFERENT salespeople per
company (V2, V6 are the common case, not an edge); every one of 546 contacts has a `respond_io_id` today (V8 is new);
4 contacts are non-MY numbers (still refused by the grant, office handles them). Example: dealer CHO*** has Sorento
300-N034..N036 (salesperson WT***) and Mocha 300-N026..N043, 9 accounts (salesperson JIM***): each salesperson grants
on their side only, and the access adds up.

Backend paths under `sorento_crm_backend/`, frontend under `sorento_crm_frontend/`. No names or phones in this
file: dealer names are masked as the first 3 letters + `***`.

## 1. The owner's job, today vs wanted

Today: Google Form -> owner retypes into Excel -> Respond.io contact import -> the 15 min syncer pulls the contacts
into the CRM -> owner tags them -> owner uploads the Respond access sheet, which links them to customers by name.
Wanted: the salesperson picks one of their own customers, adds 1..n people (name, phone, Business Owner or
Employee), submits, and the bot answers those people at once with the right scope.

## 2. What exists already (measured)

The hard part is built. Three things already grant a dealer's access through ONE engine:

| Piece | Where | What it does |
| --- | --- | --- |
| Access template (26 Oct, owner-approved) | `app/services/contact_access_sheet_service.py:42-57` | The definition of Business Owner vs Employee per company (table in section 3) |
| Engine (plan + apply, add-only) | `app/services/contact_setup_engine.py:121-256` (`_plan_contact`), `:258-314` (`_apply_contact`) | Writes access types, companies, stock, brands, segment, media, agent grants, switches |
| Respond sheet upload (admin) | `contact_access_sheet_service.py:623-664`, FE `app/(protected)/user-management/contacts/access-sheet/` | Bulk; links customers by exact normalised name, admin confirms |
| WhatsApp agent tool `crm_contact_grant` | `app/services/chatbot/agent/contact_grant.py:179-275` (plan), `:318-379` (execute) | One person per row, customers by CODE only, CREATES the CRM contact when the phone is new, one audit row |
| "Dealer contacts of my own agents" rule | `app/services/chatbot/agent/writes.py:948-970` (`contact_in_scope`) | Salesperson may touch only contacts linked to customers of their own sales agents, never their own contact |
| Permission for that rule | `user_management.contacts.edit_own`, `app/rbac/permission_registry.py:1133-1139`, seeded by `agp3_0002`, granted to NO role today | |

The other links:

| Link | Store | Writer / reader |
| --- | --- | --- |
| Contact <-> customer (many, per company) | `respond_contact_customers` (`app/models/access.py:11-64`) | `link_customer` idempotent (`app/services/contact_customer_service.py:70-129`), unlink `:132` |
| Salesperson (CRM user) -> their customers | `users.respond_contact_id` (`app/models/user.py:74`) -> `sales_agents.contact_id` (`app/models/sales_agent.py:92-96`) -> `customers.sales_agent_id` (`app/models/order.py:173-179`) | `agents_for_contact` (`app/services/sales/portal_agent.py:24-33`) |
| Per company | `customers` is company-scoped (`CompanyScopedMixin`); a Sorento debtor and a Mocha debtor are two rows, each with its OWN `sales_agent_id` | So "my customers, per company" is exact and needs no new column |
| Contact <-> company | `respond_contact_companies` (`app/models/company.py:69-90`), fail-closed company scope for the bot (`company_scope_resolver.py:338-358`) | Written by the template; by hand superadmin-only (`contacts.py:658-690`) |
| Contact tags | `contact_tags.settings`, union + live recompute since TAG-UNION #2254 (`contact_tag_union.py`) | The template does NOT write tags; tags are optional extras |

Respond.io side:

| Fact | Where |
| --- | --- |
| Syncer = scheduled task `respond_contacts_sync`, every 15 min, pulls Respond contacts without `backend_id`, matches CRM rows on the EXACT phone string, backfills `respond_io_id` + names, writes `backend_id` back | `app/services/respond_sync_handler.py:111-283`, seed `alembic/versions/072_seed_scheduled_tasks.py:27-38` |
| Second pass every run: a CRM row with no `respond_io_id` gets one `GET /v2/contact/phone:{phone}` | `respond_sync_handler.py:383-398`, `contact_service.py:1156-1162` |
| The bot's on/off gate keys on `respond_io_id`: no row with that id = silent | `app/services/chatbot_allowed_service.py:28-36` |
| No code CREATES a contact in Respond.io; the client has get-by-phone, list, update, merge, sends | `app/services/integration_service.py:251-805` |
| Every send passes `outbound_enabled` at one choke point | `integration_service.py:398-403` |

So today a CRM-created contact (the agent tool's path) stays silent until the dealer writes once AND the next sync
run fills `respond_io_id`: up to 15 minutes of unanswered first messages. That is the one gap to "instant" (Q3).

## 3. Definition of each access level (what the code does today)

What the template writes (`contact_access_sheet_service.py:42-57`, engine `:139-239`):

| | Business Owner / Director | Employee |
| --- | --- | --- |
| Access types, Sorento | `dealer`, `cabana_dealer`, `end_user` | `end_user` |
| Access types, Mocha | `mocha_dealer`, `end_user` | `end_user` |
| Companies | the company (or both) | same |
| Brands | every brand of that company (Mocha: every brand) | same |
| Stock | availability mode, Sorento BRW + MWH, Mocha HQ + MOCHA-WH | same |
| Enquiry agents | general, order, incoming stock (valid to 31 Dec 2026) | same |
| Switches | AI replies ON, stock replies ON, ETA offset ON, hand-over OFF, packing list OFF, retail segment, image replies | same |
| Customer links | the accounts picked | same |

What each one can then see and ask (read from the code):

| Can see / ask | Owner | Employee | Decided by |
| --- | --- | --- | --- |
| Talk to the bot at all | yes | yes | `chatbot_allowed` + `respond_io_id` (`chatbot_allowed_service.py:28-36`) |
| Product info, list price, stock availability at the template locations, incoming ETA | yes | yes | agent grants (`mcp_access_service.py:41-99`), stock policy (`stock_visibility.py:229-253`) |
| End-user promotions and end-user offer prices | yes | yes | `end_user` code vs `promotions.access_levels` (`marketing_service.py:525-535`) |
| **Dealer promotions, dealer offer prices, dealer-only documents** | **yes** | **no** | dealer codes (`dealer_kit/pricing.py:145-179`, `chatbot/lanes/business/tier_gate.py:46-124`, `knowledge_service.py:113-124`) |
| Their own delivery orders (DO fields) | yes | yes | customer link (`contact_customer_scope.py:52-54`, `contact_asker.py:163-172`) |
| Purchase cost | no | no | field reveal `purchase_orders.cost`, off by default (`contact_field_reveal_service.py:66-93`) |
| Outstanding, sales orders, sales report | no | no | field reveals `sales_orders.outstanding` / `.sales_report`, off by default (`chatbot/lanes/business/__init__.py:992-995, 1580-1588`) |
| Invoice price | no | no | staff only (`dealer_kit/viewer.py:43-51`) |

So the Form's "Contain Cost Related Information" means DEALER PRICES in the code today, not purchase cost and not
outstanding. Neither role sees cost or outstanding unless someone ticks a field reveal by hand. The screen will
label the levels "Business Owner (sees dealer prices)" and "Employee (end-user prices only)".

## 4. Rules (proposed)

R1. Who: a CRM user with `user_management.contacts.edit_own` (granted to the `salesperson` role by this lane, Q2).
    Their customers = active customers whose `sales_agent_id` is one of the user's own active sales agents
    (`agents_for_contact` of `users.respond_contact_id`), in the user's granted companies. A user with no linked
    sales agent sees an empty list ("No customers are assigned to you yet.").
R2. Screen (salesperson sidebar, MY WORK > "Dealer access"): a list of the user's customers per company (Sorento /
    Mocha tabs or a company column), each with the people who hold access through it. "Add people" opens a modal:
    pick the customer account(s) (SearchableMultiSelect, ONLY the user's own accounts of ONE company, nothing
    pre-ticked: explicit picks only), then 1..n rows of Name, Phone (PhoneInput, MY), Access (Business Owner /
    Employee). Submit.
R3. Submit runs the existing `crm_contact_grant` plan per row (same template, same engine, same audit shape), in one
    transaction for the whole modal: a row that cannot apply (bad phone, staff phone, duplicate phone in the form)
    blocks Submit with the reason on that row; nothing is half-written.
R4. Phone: normalised to `+601XXXXXXXX` (`contact_setup_engine.normalise_phone`); matched on digits so a stored
    `01...` and `+601...` are the same person; a non-Malaysian mobile is refused ("Ask the office to add a
    non-Malaysian number."). A phone held by two contacts is refused (existing rule, `contact_grant.py:159-176`).
R5. Never a staff or salesperson phone: a phone that is a CRM user's contact or a `sales_agents.contact_id` is
    refused ("This number belongs to a staff member.").
R6. Instant: after commit, the grant looks the phone up in Respond.io and creates the Respond contact when there is
    none (Q3), stores `respond_io_id` and `backend_id`. No message is ever sent. Runs on the `respond_io` worker
    queue with retries; the row shows "WhatsApp: linked" / "WhatsApp: waiting" until it lands.
R7. Add-only, like the sheet and the agent: a person who already holds access keeps everything they hold; the grant
    adds what the template lacks and the new link.
R8. Remove (Q4): "Remove" on a person under a customer unlinks them from THAT customer (deferred action, 5 s, Cancel).
    When it was their last customer link, AI replies turn off for them. Role change Owner -> Employee removes that
    company's dealer codes, only when the person has no other link in that company outside the user's own customers.
R9. Audit: one row per person per submit (`contact.dealer_access_grant`, actor = the salesperson, before/after per
    facet, as `contact_grant._execute` writes today); removal and role change too. The admin sees it on the contact's
    History; the salesperson's list shows "Added by <name>, <date>" per person.
R10. The salesperson never sees another salesperson's customer: a person already linked to another dealer shows
    "Also has access through another account" with no name (Q5).

## 5. Examples (real, masked, from the 20 Oct prod backup measured for the 26 Oct card; fresh dev rows asked for with crew-data-request on the PR)

1. ABA*** SDN BHD, Sorento + Mocha. Sorento accounts 300-A091..A093 (A/C I, III, IV) are the Sorento salesperson's;
   Mocha 300-A025..A027 (A/C I, CERAMIC, IBORN) the Mocha one's. The Sorento salesperson adds the owner as Business
   Owner on A091..A093: gets `dealer`, `cabana_dealer`, `end_user`, Sorento. Later the Mocha salesperson adds the same
   phone on A025..A027: union, now also `mocha_dealer`, Mocha brands and locations. Neither sees the other's accounts.
2. KBO*** LOGISTIC & SUPPLY: the Form says "KBO*** LOGISTIC & SUPPLY", AutoCount says "KBO*** LOGISTICS". Today that
   needed a manual pick; on the new screen the salesperson picks K124/K126/K139 from their own list. No name match.
3. YOO*** LIVING HOUSE, 4 people: one owner S+M, two owners Sorento only, one employee. Each row gets its own level;
   the employee sees end-user prices only.
4. A shop assistant added as Employee whose phone is already the Business Owner of another dealer (R10): add-only,
   they keep owner codes from the other dealer; the screen says "Also has access through another account".
5. HEN*** SENG SPG HARDWARE vs HEN*** SENG TSM (two branches, near-identical names): the salesperson picks the branch
   account; the old fuzzy hit (0.91) to the wrong branch cannot happen.

## 6. Edge cases

| Case | Behaviour |
| --- | --- |
| Phone already a contact of another customer | Add-only; link added; other links untouched; neutral notice (R10, Q5) |
| Same person for 2 dealers | Two links; the bot scopes per link as today |
| Phone formats `012...`, `6012...`, `+60 12-...` | One person (R4) |
| Customer served by 2 agents (Sorento vs Mocha) | Two customer rows, two agents; each salesperson sees and grants only their own company's row; grants add up (ex. 1) |
| Same company, one dealer, accounts split across 2 salespeople | Each sees only their accounts; a person can be linked by both |
| Revoke / remove | R8 |
| Salesperson leaves | Grants stay (they hang on the customer link, not the person). The customer's new agent sees them at once, since the list derives from `customers.sales_agent_id`. Audit keeps who granted |
| Who sees / undoes a grant | Salesperson: own customers' people, Remove. Admin (`contacts.edit`): contact page, History, unlink as today |
| Dealer under both companies | Ex. 1; the modal grants one company at a time (its accounts), the second company adds up |
| Staff phone | Refused (R5) |
| The salesperson's own phone | Refused (existing rule, `writes.py:953`) |
| Respond.io down / no key (dev, CI) | Grant commits; the Respond step retries on the worker and the row shows "WhatsApp: waiting". Tests mock the client; dev never calls Respond |
| Permission edits by hand on the contact afterwards | Kept (add-only; TAG-UNION keeps own changes) |

## 7. Questions (owner)

Q1. Where the access levels are defined: (a) keep the 26 Oct template in code (section 3; already shared by the sheet
    upload and the WhatsApp agent, one engine); (b) four admin-editable contact tags ("Sorento Business Owner",
    "Sorento Employee", "Mocha Business Owner", "Mocha Employee") and the grant adds the tag. Recommend (a): it is
    built, tested and approved, and three surfaces then agree; (b) can come later if you want to tune a level without
    a release (trigger: the first time you want to change what a level gets).
Q2. Authorisation: (a) give the `salesperson` role `user_management.contacts.edit_own`, and a portal grant writes the
    WHOLE template, including companies, stock and enquiry agents that a salesperson cannot set by hand: the template
    is the limit, the salesperson picks only account, person and level; (b) write only what the salesperson could set
    by hand (today that skips companies, stock and agents, so the bot would not answer them). Recommend (a): (b)
    does not meet the goal, and (a) gives no free choice of any setting.
Q3. Respond.io side: (a) at grant time, look the phone up in Respond and create the contact there if missing (an API
    create, no message sent), so the first WhatsApp is answered; (b) wait for the dealer's first message and the 15
    min sync (first messages go unanswered). Recommend (a): it is the "instant" in the goal; dev and tests never call
    Respond.
Q4. Remove: (a) as R8: unlink from this customer, AI off when it was the last link, role change Owner -> Employee
    allowed; (b) salespeople can only add, removal stays with the office. Recommend (a): a dealer's staff turnover is
    the salesperson's knowledge, and it is the same deferred undo as everywhere else.
Q5. A phone that already has access through ANOTHER salesperson's dealer: (a) allowed, add-only, neutral notice, the
    other account never named; (b) refused, office only. Recommend (a): real people do work for two shops, and add-only
    cannot take anything away from the other dealer.

Not a question, a note: if you want Business Owners to also see outstanding or cost, that is a field reveal added to
the Owner level (one line in the template); say so and it goes in.

## 8. One-off import of the existing Google Form rows

Recommend a reviewed one-off, never auto-matching: a crew script turns the Form export into a dry-run CSV (one row per
person: normalised phone, name, level, company, salesperson, the Form's SSM name as written, and an EMPTY
customer-codes column). The owner (or each salesperson) fills the customer codes; the apply step links by code only,
through the same engine, and prints a report. Rows with no code are skipped and listed. The Form's data never enters
the repo.
