# Behaviour card - BULK-CONTACT-ACCESS: upload the Respond dealer-contact sheet, set each contact's access

**Owner answers (26 Oct ~15:10):** Q1 (a) add only. Q2 (a) cabana_dealer too. Q3 brands = every brand of the
contact's companies, from the data (`brands.company_id`, `app/models/product.py:99`), no list in code. Q4 (b) link
every exact account, shown ticked. Q5 (a) skip. Mock v1 approved ("ok", 15:03).
Data note on Q3 (20 Oct backup): all 12 brand rows belong to Sorento Sdn Bhd (MOCHA and IBORN included); Mocha Sdn
Bhd has none and its 3481 products carry no brand. So Sorento only and S+M both get the 12; Mocha only stays NULL,
which the per-company brand rule (`app/services/contact_brand_scope.py:1-9`) plus the contact's company scope
(`app/services/company_scope_resolver.py:221`) turns into every Mocha product. Follow-up filed to the owner.

Lane BULK-CONTACT-ACCESS, size L, 26 Oct 2026. Card before any code. Researched on main `f287cbe703`; data from
`sorento_prod_1020` (20 Oct prod backup, read-only). Backend paths under `sorento_crm_backend/`. Dealer names
masked as first 3 letters + `***`; no person names or phones.

## 1. The owner's job
313 dealer contacts (114 dealers) are in Respond.io and synced to the CRM but not yet configured. The owner uploads
the Respond export (First Name, Phone Number, Tags) and every contact gets its dealer access and its customer
accounts in one pass. Tags shape: `<dealer text>, Sorento Sdn Bhd, <agent>, [Mocha Sdn Bhd, <agent>], [<alt text>],
<Business Owner|Employee>`. Sheet: Business Owner 186 / Employee 127; Sorento+Mocha 82, Sorento only 206, Mocha
only 25 (25 rows have no Sorento agent: `Sorento Sdn Bhd,Mocha Sdn Bhd` back to back; 1 row has no Mocha agent).

## 2. What exists already (measured)
- `scripts/contact_bulk_setup.py` (PR #1483, merged): the 4 Oct crew-run CLI over a dealer Excel. `RULES`
  (line 99) is an access template; `run()` (line 421) plans + applies ADD-only per contact; `auto_links()` (line
  739) links EVERY customer of the brand company whose `normalise_name` (line 563) equals the dealer text, merge
  survivor and not held (`_merge_flags`, line 582); the rest go to a review sheet.
- `app/services/contact_access_copy_service.py` (PR #1463 / #1732): snapshot, diff, per-contact savepoint, one
  audit row per contact (lines 1010-1092); skips facets the caller may not set (`facets_to_skip`, lines 129-147).
- Not there: an in-app upload, a parser for the Respond `Tags` column, and the 26 Oct template differences below.

Where each setting lives:
| Setting | Store | Writer |
|---|---|---|
| Brand companies | `respond_contact_companies` (`app/models/company.py:65`) | `PUT /contacts/{id}/companies`, superadmin only (`app/api/v1/user_management/contacts.py:602`) |
| Customer accounts (many) | `respond_contact_customers` (`app/models/access.py:11`) | `link_customer`, idempotent (`app/services/contact_customer_service.py:67`) |
| Access types = promotion visibility | `respond_contact_access_types` (`access.py:67`) | `set_contact_access_codes` (`app/services/contact_access_type_service.py:270`); a promotion shows when its `access_levels` share a code (`app/services/marketing_service.py:484`) |
| Brands allowed | `respond_contacts.brand_ids`, NULL = every brand (`access.py:293`) | `set_contact_brands` (`app/services/contact_brand_scope.py:257`) |
| Locations allowed | `stock_visibility_policies` (`access.py:866`) | `PUT /inventory/stock-visibility/contacts/{id}`, `inventory.stock.edit` |
| Packing list / ETA buffer / stock / AI / escalation | `respond_contacts` columns (`access.py:311-337`) | `PUT /contacts/{id}/chatbot` |
| Agent grants, media, segment | `contact_agent_access`, `contact_media_limit`, `respond_contact_market_segments` | per-section endpoints |
| Sales agent | NOT on the contact: read from each linked customer's `sales_agent_id` (`contact_customer_service.py:293-307`) | - |
| Business Owner / Employee | NOT stored; only the access types differ | - |

No access field is pushed back to Respond.io (`access.py:353-356`).

## 3. Today's configured dealers (20 Oct backup)
125 configured dealer contacts (customer link + a dealer type). 5 distinct type/company combos:
| Group | Contacts | Access types (Business Owner) | Brands | Locations |
|---|---|---|---|---|
| Sorento only | 64 | dealer + cabana_dealer + end_user | SORENTO, WDI, CABANA, NO LOGO, ELLECI | BRW, MWH |
| Sorento + Mocha | 43 | dealer + cabana_dealer + mocha_dealer + end_user | the 5 + MOCHA, IBORN | BRW, MWH, HQ, MOCHA-WH |
| Mocha only | 17 | mocha_dealer + end_user | NULL (= every brand) | HQ, MOCHA-WH |
| 1-offs | 2 | dealer+end_user / cabana_dealer+end_user+sorento_office | - | - |
Employees (93 linked contacts): `end_user` only, same brands/locations as their dealer's owners. Every linked
contact (219): packing list OFF, ETA buffer ON, stock ON, AI ON, escalation OFF, regions west, segment retail,
stock mode availability, the 3 agent grants (general / order / incoming stock enquiries). Exceptions: 6 S+M
contacts also hold WH3; 1 Sorento dealer has regions west+east. The owner's claims all hold in the data.

Template the upload writes (per contact, from ITS row's tags):
| | Business Owner | Employee |
|---|---|---|
| Sorento | dealer, cabana_dealer (Q2), end_user | end_user |
| Mocha | mocha_dealer, end_user | end_user |
| S+M | dealer, cabana_dealer (Q2), mocha_dealer, end_user | end_user |
Companies, brands (Q3) and locations by brand company as in the table above, same for both roles. Common to all:
packing list OFF, ETA buffer ON, stock ON, AI ON, escalation OFF, segment retail, stock mode availability, image
media, the 3 agent grants (valid 1 Jan - 31 Dec 2026, as today's rows).

## 4. Proposed flow
1. Contacts list > Import access sheet > choose the Respond CSV. Server parses and plans; nothing is written.
2. Preview, one block per dealer (114): dealer text, brand companies, match status, the accounts it would link
   (debtor code, name, that account's sales agent next to the sheet's agent), then its contacts: name, phone, in
   CRM yes/no, role, template, what changes, warnings.
3. Admin confirms: "Confirm all exact" ticks every exact dealer; a dealer needing a pick shows ranked candidates
   (none ticked) plus a customer search. An unconfirmed dealer's contacts are skipped whole.
4. Apply: the browser sends the same file + the confirmed account ids; the server re-plans and writes in ONE
   transaction; result report (applied / skipped, with reason); one audit row per changed contact. Re-upload of
   the same sheet = 0 changes.
Engine: the `contact_bulk_setup.py` core moves into a service the script and the endpoint both call (one copy).
Gate: `user_management.contacts.edit`; facets the caller may not set are reported "not applied" exactly as the
bulk copy does (`facets_to_skip`). Synchronous request (313 contacts; bulk copy already does 500).

Customer match (the 4 Oct `auto_links` rule, measured on this sheet): 140 dealer x brand-company blocks; 124
exact (each links 3-9 accounts: A/C I-IV, CERAMIC, IBORN), 16 none (13 dealers need a pick). The alt company
texts add 0 matches. No fuzzy auto-link: the best fuzzy hit can be a different branch (example 3).
Sales agent: not written (it lives on the customer). Shown side by side as a check only; the sheet uses first
names ("Samantha", "William") while `sales_agents` uses codes ("SMT - I", "WT I"), so no auto-compare.

## 5. Examples (real, masked)
1. ABA*** SDN BHD, S+M, exact: Sorento 300-A091..A093 [A/C I, III, IV] + Mocha 300-A025..A027 [A/C I, CERAMIC,
   IBORN] = 6 accounts, pre-ticked by "Confirm all exact".
2. KBO*** LOGISTIC & SUPPLY, S+M, none: accounts are spelled "KBO*** LOGISTICS" (score 0.96); admin ticks
   300-K124/K126/K139 + 300-K163..K165.
3. HEN*** SENG SPG HARDWARE, Sorento, none: best candidate is HEN*** SENG TSM (0.91), a different branch; admin
   picks or leaves it unconfirmed.
4. AIK*** HUAT HARDWARE and AIK*** HUAT HARDWARE TRADING SDN BHD (two spellings): both exact to the same 3
   accounts (`trading` is a stripped suffix).
5. YOO*** LIVING HOUSE: 4 contacts whose rows disagree (one owner S+M, two owners Sorento only, one employee
   S+M): each contact gets the template of its own row; the block shows "rows disagree on brands".

## 6. Edge cases
- 85 of 313 phones are not in the 20 Oct backup (Q5). Phones compared on digits; two contacts with the same
  digits = row error.
- 205 of the 228 found contacts already hold access (204 types, 205 links) (Q1).
- 46 dealer x company pairs have exact accounts in a brand company the sheet does NOT tag (Q4).
- 12 dealers' rows disagree on brands or agent (example 5). 6 matched dealers include an inactive account
  (shown, unticked).
- Agent grants expire 31 Dec 2026 (copied from today's rows; same as the 4 Oct script).
- Empty Respond columns (is_allowed_stock, is_allowed_ai, ...) are ignored; the template sets those switches.

## 7. Questions (owner)
Q1. A contact that already has access (205 of 228 found): (a) add only: add what the template lacks, never remove
  (4 Oct precedent; keeps WH3 / extra types); (b) replace: contact ends exactly the template; (c) skip configured
  contacts. Recommend (a): no manual setting is lost and re-runs are 0 changes; extras show as a warning.
Q2. Sorento Business Owners: today all 105 hold `cabana_dealer` (Cabana dealer promotions), the 4 Oct script does
  not write it (`RULES` line 101). (a) include it; (b) dealer only. Recommend (a): matches today's data.
Q3. Mocha-only contacts' brands: today NULL = every brand, Sorento's 5 included (`access.py:293`). (a) MOCHA +
  IBORN; (b) every brand, as today. Recommend (a): S+M contacts carry MOCHA + IBORN explicitly.
Q4. "Link to all accounts": (a) every exact account of the brand companies the row tags (the 46 untagged-company
  matches shown as unticked suggestions); (b) also link the 46. Recommend (a): a Sorento-only contact linked to a
  Mocha account would see Mocha orders without Mocha access.
Q5. Phones not in the CRM: (a) skip as "not in CRM yet" (a later re-upload picks them up); (b) create the contact
  from the sheet. Recommend (a): Respond sync owns contact creation (`app/services/respond_sync_handler.py:274`).
