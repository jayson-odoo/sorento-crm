# PLAN: access-sheet preview shows full per-contact changes; account links follow each contact's own row (BULK-ACCESS-PREVIEW)

Status: Plan. Mockup + behaviour card pending owner approval before code. Track: M (LEAD pattern), no migration.
Parent: `PLAN-bulk-contact-access-26oct.md` (#1875). UAC: `bulk-access-preview-27oct-acceptance-criteria.md`.

## Owner rulings (27 Oct)
1. Linking rule: an account in a dealer card links only to contacts whose own sheet row (Tags) includes that
   account's company. Today links go per card to every contact.
2. No deletion of existing links: Apply stays add-only. The preview shows, per contact, linked accounts outside
   the contact's row companies as an info line, never removes them.
3. Visibility: per contact, a before -> after view per facet, one item per line, nothing truncated;
   "Holds more than the template" lists what is extra.

Detail filled in after reading the code (next commit).
