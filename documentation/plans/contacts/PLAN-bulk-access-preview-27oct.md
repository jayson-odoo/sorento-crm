# PLAN: access-sheet preview shows full per-contact changes; account links follow each contact's own row (BULK-ACCESS-PREVIEW)

Status: Review READY (round 2) and round-2 fixes in; sandbox browser pass PASS; P8 flipped to crew ruling (b); browser pass rerun on the new head; hand test re-filed. Mock v2 + card approved 27 Oct (preview as
its own paginated page). Track: M (LEAD pattern; diff over 300 lines, no migration, no auth change).
Parent: `PLAN-bulk-contact-access-26oct.md` (#1875). UAC: `bulk-access-preview-27oct-acceptance-criteria.md`.

## Owner rulings (27 Oct)
1. Linking rule: an account in a dealer card links only to contacts whose own sheet row (Tags) includes that
   account's company. Today links go per card to every contact.
2. No deletion of existing links: Apply stays add-only. The preview shows, per contact, linked accounts outside
   the contact's row companies as an info line, never removes them.
3. Visibility: per contact, a before -> after view per facet, one item per line, nothing truncated;
   "Holds more than the template" lists what is extra.

Mockup: `documentation/mockups/BULK-ACCESS-PREVIEW/index.html`. Card: `CARD-bulk-access-preview-27oct.md`.

## Changes
- BE `_plan` (svc:491-507): per contact, links = confirmed accounts whose company is on the row; add `links_to` per account, `outside_links` and `holds_more_items` per contact.
- FE `ContactsTable` (dlg:528-571) becomes per-contact panels with a before -> after grid; `AccountsTable` gets "Links to".
- FE `confirmAllExact` (lib:24-27): skip `rows_disagree` blocks if the owner agrees.
