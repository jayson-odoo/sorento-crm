# UAC - BULK-CONTACT-ACCESS (upload the Respond dealer-contact sheet, set each contact's access)

Status: APPROVED rules. Owner rulings 26 Oct ~15:10: Q1 (a) add only, Q2 (a) cabana_dealer for Sorento owners,
Q3 brands by the brand's dealer group (15:20: Sorento group / Mocha group / project), Q4 (b) link EVERY exact account, ticked,
Q5 (a) skip phones not in the CRM. Mock v1 approved 15:03. Card: `CARD-bulk-contact-access-26oct.md`. Plan +
API contract: `PLAN-bulk-contact-access-26oct.md`.

Test data is fake (public repo): dealers like "ALPHA BATH SDN BHD", phones +60100000001.

## Parse
- U1 The upload takes the Respond contact export CSV (columns First Name, Phone Number, Tags; extra columns
  ignored; UTF-8 with or without BOM). A file without a Phone Number or Tags column is refused (422) naming the
  missing column. Over 2 MB or over 2000 data rows is refused (422).
- U2 Tags parse (comma list, tokens trimmed): first token = dealer text; `Sorento Sdn Bhd` -> SRT, `Mocha Sdn Bhd`
  -> MCH (case-insensitive); the token right after a brand company is that company's agent unless it is another
  brand company or a role word; `Business Owner` -> owner, `Employee` -> employee; any other token = alt dealer
  text. A row with no brand company, no role, or no phone is a row error (listed, not applied).
- U3 Phone matched to a CRM contact on digits only (`+60 12-345 6789` = `60123456789`). Not found = skipped
  "not_in_crm" [Q5]; two contacts with the same digits = skipped "ambiguous_phone". Never created.

## Template (per contact, from its own row)
- U4 Access types: owner gets `dealer` + `cabana_dealer` for SRT, `mocha_dealer` for MCH, plus `end_user`;
  employee gets `end_user` only.
- U5 Companies = the row's companies. Brands [Q3, owner 15:20] = every ACTIVE brand whose `dealer_company_id` is
  one of the row's companies (Sorento only -> SORENTO, CABANA, ELLECI, WDI, NO LOGO; Mocha only -> MOCHA, IBORN;
  both -> union; project brands BRAVAT, INFINITY, JOHNSON SUISSE, TP ENTERPRISE, OTHERS have none and are never
  given). Contact brands NULL -> set to that list; already a list -> union (never remove); a brand outside it ->
  warning `holds_more`. Locations (stock visibility, mode `availability`, hide-zero off, no exclusions): SRT ->
  warehouses BRW, MWH of company SRT; MCH -> HQ, MOCHA-WH of company MCH; both = union.
- U6 Every contact: packing list OFF, ETA buffer ON, stock ON, AI replies ON, escalation OFF, segment `retail`,
  image media allowed, agent grants `general_enquiries`, `order_enquiries`, `incoming_stock_enquiries` allowed
  1 Jan 2026 00:00 - 31 Dec 2026 00:00.
- U7 [Q1] Add only: a type, company, brand, location, segment, grant the contact already holds is kept; nothing is
  removed. Switches (packing, ETA, stock, AI, escalation) are set to the template value. A contact holding more
  than its template (types, companies or locations outside it) gets warning `holds_more`.

## Customer accounts
- U8 Dealer block key = `normalise_name(dealer text)` (`scripts/contact_bulk_setup.py:563`); rows whose dealer
  texts normalise equal share one block. Exact account = a customer of ANY company whose normalised name equals the
  block's dealer text or an alt text, merge survivor and not held (`_merge_flags`, line 582).
- U9 Block status: `exact` when every company the block's rows tag has at least one exact account; otherwise
  `pick` with up to 5 ranked candidates per tagged company (similarity score, not ticked) when any exist, else
  `none`. Rows of one block that tag different companies get warning `rows_disagree`.
- U10 [Q4] Every exact account is proposed and ticked by default, including accounts of a company the rows do
  not tag; inactive exact accounts are listed but not ticked.
- U11 Nothing is linked for a block the admin did not confirm; its contacts are skipped "dealer_not_confirmed".
  "Confirm all exact" confirms every `exact` block with its ticked accounts. A confirmed block links EVERY
  confirmed account to EVERY found contact of the block.
- U12 Each account shows debtor code, name, company, active flag and its sales agent; the sheet's agent text for
  that company sits beside it. The sales agent is never written.

## Preview, apply, result
- U13 Preview (`dry_run` true) writes nothing.
- U14 Apply (`dry_run` false) sends the same file + the confirmed account ids per block; the server re-plans and
  writes everything in ONE transaction. Any error rolls all of it back; nothing is half-applied.
- U15 Result per contact: `applied` (with its changes), `no_change`, or `skipped` with reason (`not_in_crm`,
  `ambiguous_phone`, `dealer_not_confirmed`, `row_error`).
- U16 One audit row per changed contact (event `contact.access_sheet`, before/after per facet, actor = the
  admin). No audit row for an unchanged contact.
- U17 The same sheet with the same confirmations again: 0 applied, every found contact `no_change`.

## Permission and scope
- U18 Needs `user_management.contacts.edit` (403 otherwise). Facets the caller could not set directly are not
  written and are listed per contact in `not_applied` (companies = superadmin; locations =
  `inventory.stock.edit`; agent grants = `user_management.access_agents.edit`), via
  `contact_access_copy_service.facets_to_skip`.
- U19 Only customers inside the caller's company scope are proposed; a confirmed id that is unknown or outside
  the caller's scope is refused (422) and nothing is written.

## Brand dealer group (owner 15:20)
- U21 `brands.dealer_company_id` (nullable, FK companies): the company whose dealers get the brand. Migration seeds
  SORENTO, CABANA, ELLECI, WDI, NO LOGO -> Sorento Sdn Bhd; MOCHA, IBORN -> Mocha Sdn Bhd; the rest NULL. Brand
  create / edit (master data) has a clearable "Dealer group" select of companies; the brand API accepts and returns
  `dealer_company_id` + `dealer_company_name`; an unknown company id is refused (422).

## Screen
- U20 Contacts list > Actions > Import access sheet (shown with `user_management.contacts.edit`) opens a dialog:
  Upload > Preview > Result, as mock v1 (`documentation/mockups/BULK-CONTACT-ACCESS/index.html`). Usable at
  375 px and 1280 px; no UUIDs shown; dealer blocks collapsible; long names truncate with title. Result has
  "Download result" (CSV built in the browser; cells starting with = + - @ are prefixed with ').
