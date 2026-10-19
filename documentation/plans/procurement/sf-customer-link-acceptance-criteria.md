# UAC: SF-CUSTOMER-LINK

Plan: `PLAN-sf-customer-link-19oct.md`.

- CL1 Dry run (no `--apply`) writes nothing to the database and writes a CSV with one row per
  Sponsorship Form (never a Purchase Request).
- CL2 Status LINK: exactly one active customer of the chosen company has the SF's typed customer
  name, compared after trimming, collapsing runs of whitespace to one space, and ignoring case.
- CL3 Status AMBIGUOUS: two or more such customers. Nothing is picked.
- CL4 Status NO MATCH: none, including a blank typed name. A name that only matches after removing
  a word, a bracket, a suffix or a typo is NO MATCH.
- CL5 Status ALREADY LINKED: the SF already has a customer link. Never changed.
- CL6 An inactive customer is never matched. Another company's customer is never matched.
- CL7 `--apply --from-csv FILE` links only rows marked LINK in that file; a row the owner deleted is
  not linked. A row whose match changed since the dry run is skipped and counted.
- CL8 A linked SF gets the customer's id and the customer's own name (as the staff form stores it).
  An existing customer link is never overwritten.
- CL9 A second `--apply` with the same file links nothing.
- CL10 All links commit together or not at all; the output prints the counts and tells the operator
  to run `scripts/backfill_sf_sales_type.py` next.
