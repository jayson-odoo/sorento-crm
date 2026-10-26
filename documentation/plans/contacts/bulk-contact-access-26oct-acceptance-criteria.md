# UAC - BULK-CONTACT-ACCESS (upload the Respond dealer-contact sheet, set each contact's access)

Status: DRAFT - written against the card's recommended answers (Q1 a, Q2 a, Q3 a, Q4 a, Q5 a); rows marked
[Qn] change if the owner answers otherwise. Card: `CARD-bulk-contact-access-26oct.md`. Plan:
`PLAN-bulk-contact-access-26oct.md`.

Test data is fake (public repo): dealers like "ALPHA BATH SDN BHD", phones +60100000001.

## Parse
- U1 The upload takes the Respond contact export CSV (columns First Name, Phone Number, Tags; extra columns
  ignored). A file without a Phone Number or Tags column is refused with a message naming the missing column.
- U2 Tags parse: first token = dealer text; `Sorento Sdn Bhd` / `Mocha Sdn Bhd` = brand companies; the token after
  a brand company is that company's agent unless it is another brand company or a role word; `Business Owner` /
  `Employee` = role; any other token = alt dealer text. A row with no brand company or no role is a row error.
- U3 Phone matched to a CRM contact on digits only. Not found = "Not in CRM yet" [Q5]; two contacts with the same
  digits = "Ambiguous phone". Both are skipped, never created.

## Template (per contact, from its own row)
- U4 Access types: Business Owner gets `dealer` + `cabana_dealer` [Q2] for Sorento, `mocha_dealer` for Mocha,
  plus `end_user`; Employee gets `end_user` only.
- U5 Companies = the row's brand companies. Brands: Sorento SORENTO, WDI, CABANA, NO LOGO, ELLECI; Mocha MOCHA,
  IBORN [Q3]; both = union. Locations (stock visibility, mode availability, hide-zero off): Sorento BRW, MWH;
  Mocha HQ, MOCHA-WH; both = union.
- U6 Every contact: packing list OFF, ETA buffer ON, stock ON, AI ON, escalation OFF, segment retail, image
  media allowed, agent grants general / order / incoming stock enquiries (1 Jan - 31 Dec 2026).
- U7 [Q1] Add only: a type, company, brand, location, segment, grant the contact already holds is kept; nothing is
  removed. Switches (packing, ETA, stock, AI, escalation) are set to the template value. A contact holding MORE
  than its template (e.g. a dealer type on an Employee row, WH3) shows a warning "Holds more than the sheet".

## Customer accounts
- U8 Per dealer and brand company: every customer of that company whose normalised name equals the dealer text
  (or an alt text), merge survivor and not held, is an exact match. A dealer with an exact match for every
  brand company of its rows is "Exact".
- U9 Otherwise "Needs a pick" (ranked candidates, none ticked, plus a customer search) or "No match" (search
  only). Nothing is linked for a dealer the admin did not confirm, and that dealer's contacts are skipped whole
  ("Dealer not confirmed").
- U10 [Q4] Only accounts of the brand companies the row tags are proposed; exact accounts in an untagged brand
  company are listed unticked.
- U11 "Confirm all exact" ticks every Exact dealer; the admin can untick an account or a dealer before applying.
- U12 Each proposed account shows debtor code, name, active/inactive and its sales agent, next to the sheet's
  agent text. Inactive accounts are shown unticked. The sales agent is never written.

## Preview, apply, result
- U13 Preview writes nothing (dry run). Counts: rows, contacts found, not in CRM, ambiguous, row errors, dealers
  Exact / Needs a pick / No match, contacts already holding access.
- U14 Apply sends the same file + the confirmed account ids; the server re-plans and writes everything in ONE
  transaction. An error rolls back all of it and the admin sees the message; nothing is half-applied.
- U15 Result: applied contacts (with what changed) and skipped contacts with reason (not in CRM yet, ambiguous
  phone, dealer not confirmed, row error).
- U16 One audit row per changed contact (`contact.access_sheet`, before/after per facet, actor = the admin).
- U17 Uploading the same sheet with the same confirmations again changes nothing (0 applied, all "No change").

## Permission and scope
- U18 Needs `user_management.contacts.edit`. Facets the caller could not set directly are not written and are
  listed as "Not applied: needs permission" (companies = superadmin; locations = `inventory.stock.edit`; agent
  grants = `user_management.access_agents.edit`), exactly as the bulk copy.
- U19 Only customers inside the caller's company scope are proposed or linkable; a confirmed id outside it is
  refused (422) and nothing is written.

## Screen
- U20 Contacts list > Import access sheet opens a dialog: Upload > Preview > Result (steps as Copy access).
  Usable at 375 px and 1280 px; no UUIDs shown; dealer blocks collapsible; long names truncate with title.
