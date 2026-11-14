# UAC: DEALER-ACCESS-NAMES (14 Nov 2026)

Plan: `PLAN-dealer-access-names-14nov.md`. Owner answers 14 Nov 16:45 / 16:53: Q1 (a), Q2 "show already has access and
give the link to the contact to amend", Q3 (a), Q4 (a), Q5 (a). All examples are invented (public repo).

World used below: salesperson S1 (holds `user_management.contacts.edit_own` only) owns Sorento customers
"Kedai Test Satu" (300-A004) and "Kedai Test Dua" (300-A005) and Mocha customer "Kedai Test Satu" (300-M001).
Salesperson S2 owns Sorento "Kedai Lain" (300-B001). Contact Ali Test is linked to 300-A004 and 300-B001. Contact Chong
Test is linked to 300-B001 only. Contact Dan Test exists with no customer link at all.

## N1 Chips show customer names

- N1.1 A people row's chips are the customer NAMES of that row's company, not codes; the code is the chip's hover title.
- N1.2 Two chips of one row with the same name read "Name (code)"; a unique name reads just "Name".
- N1.3 Chips stay one line, cut with "...", with "+N" for the overflow (existing `PillOverflow`).
- N1.4 The Add people / edit "My accounts" options read "<name> (<code>)" and match a typed name or code.

## N2 The list: all dealer contacts of my companies, "My customers" on by default

- N2.1 `GET /people` without `mine` (default `mine=true`) returns today's set: contacts linked to one of MY active
  accounts, one row per (contact, company).
- N2.2 `mine=false` returns every contact linked to an ACTIVE customer of a company I am granted, mine or not
  (S1 sees Ali Test AND Chong Test in Sorento). Never a company I am not granted.
- N2.3 Each row's `accounts` lists every active linked customer of that company (S1's Ali Test row: 300-A004 and
  300-B001), each with `mine: true|false`. The `link_id` is sent only for `mine: true` accounts.
- N2.4 Each row carries `editable` = `writes.contact_in_scope` for the user. Chong Test for S1: `editable: false`.
  `PUT /people/{id}` and the unlink action keep refusing a non-editable contact (404, unchanged).
- N2.5 A non-editable row has no Edit and no Unlink action; clicking it opens the same dialog read-only (fields shown,
  no Save).
- N2.6 `other_account` is gone from the API, the grid and the cards; no "also another account" text anywhere.
- N2.7 The Filters popover has a "My customers" switch, ON by default, kept in the address bar (`mine=0` when off);
  "Clear all" turns it back ON.
- N2.8 Unlink offers only my own accounts (`mine: true`).

## N3 Customer filter and search

- N3.1 `GET /customers?query=&mine=&company[]=` returns at most 50 `{id, code, name, company}` of the customers the
  list can show (mine with `mine=true`; every active customer of my granted companies with `mine=false`), matched
  case-insensitively on name OR code, sorted by name.
- N3.2 `GET /people?customer=<id>&customer=<id>` keeps rows linked to EITHER customer; it combines with company,
  access and query (all apply). An id outside what the user may see returns no rows (not an error).
- N3.3 The Filters popover has a Customer `SearchableMultiSelect` that asks the server as the user types.
- N3.4 Search matches a person's name, phone digits, or any of the row's customer codes OR names.

## N4 Add people: several companies, no silent add

- N4.1 `POST /grant` takes `companies: [codes]` (1-2) with `account_ids` across them; each account must be my own of
  one picked company, every picked company must get at least one account (else "Pick one of your accounts.").
  The legacy single `company` field is still accepted.
- N4.2 Each person's one access level applies to every picked company; the SAME grant service
  (`contact_grant.plan` / `_execute`) runs once per (person, company). Every plan runs before any execute: one refusal
  writes nothing.
- N4.3 A phone whose contact already has ANY customer link (anywhere) is refused for that row, nothing written for
  any row, with `{index, error, contact: {id, name, company, editable}}`:
  - visible on my list (linked to an active customer of a company I am granted): error "<Name> already has access.";
    `contact` filled; the dialog shows "Edit <Name>" (editable) or "Show <Name>" (not editable) which opens that
    person's dialog (edit or read-only) for that company.
  - linked only outside my companies: error "This number already has access in another company."; `contact` null; no
    link, no name.
- N4.4 A phone whose contact exists with NO customer link is linked (never a second contact), as today.
- N4.5 Duplicate phones within one form, staff phones and the other existing refusals keep their texts.
- N4.6 The agent's pasted-table grant (`contact_grant`) behaviour is unchanged (its tests stay green).

## N5 Respond.io, in the request, logged, retryable

- N5.1 After a person's grant commits, the screen finds the person in Respond.io by phone and creates them on a 404,
  inside the same request, through ONE shared function that the worker task `ensure_respond_contact` also calls.
  An existing Respond.io contact is linked (its id stored), never created twice. The screen path does not also
  enqueue the worker job.
- N5.2 Every Respond.io call this makes (lookup, create, backend_id update) writes one `integration_logs` row
  (channel `respond_io`, business_table `respond_contacts`, the contact id) on success AND failure, via
  `integration_service.log_respond_send`.
- N5.3 Respond.io fails (HTTP error, timeout, no API key): the access stays saved; that row's result carries
  `respond: "failed"` and a plain `respond_error`; the dialog says "Access given. Not yet in Respond.io: <reason>."
  with Try again; no failure is silent.
- N5.4 People rows carry `in_respond` (contact has a Respond.io id). A row with `in_respond: false` shows "Not in
  Respond.io yet" and, when editable, a "Try again in Respond.io" action.
- N5.5 `POST /people/{contact_id}/respond` runs the same shared function for an editable contact (404 otherwise) and
  returns `{respond: "ok"|"failed", respond_error}`.
- N5.6 Tests use fakes; nothing calls the real Respond.io.
