# UAC - Packing list region (REGION-PACKING-LIST)

Draft on the card recommendations (Q1-Q5 = (a)); revised when the owner answers.

## Packing list
- AC-RPL-1 A packing list carries one or more regions (West, East, or both). A new one from any path (upload, Create, proforma convert, external API) is West only unless other regions are chosen.
- AC-RPL-2 The Upload dialog shows a required Regions multi-select only for the Packing List type, West preselected; the regions picked reach the packing list n8n creates from that file.
- AC-RPL-3 External create: explicit `regions` in the payload win, else the attachment's regions, else West only.
- AC-RPL-4 Regions are shown and editable on Create Packing List and on the detail page (same layout, edit in place); an empty set or any value other than West / East is refused (422).
- AC-RPL-5 The packing list list has a Regions column and a Region filter (a row matches when any of its regions matches).
- AC-RPL-6 Backfill: every existing packing list reads West only after the migration.

## Contact
- AC-RPL-7 Every contact holds one or more regions, default West; the Chatbot settings card shows a Regions multi-select; saving an empty set is refused (422); GET returns `regions`.
- AC-RPL-8 Backfill: every existing contact holds West only.

## What a contact is told
- AC-RPL-9 A packing list is visible to a contact when any of its regions is one the contact sees; a contact holding East sees East and West, i.e. every packing list, on `/incoming-stock/list`, `/by-product`, `/shipments`, `/shipments/{id}/products`, `/shipments/{id}/attachment`.
- AC-RPL-10 A West-only contact sees packing lists tagged West or West + East, and no East-only packing list on any of those routes: no row, no line, no ETA, no file; totals and paging count only what they see.
- AC-RPL-11 An unresolved contact is treated as West only, including a respond_io_id that matches several contact rows (never the union of their regions).
- AC-RPL-12 No contact in play (staff session, bare API key) sees every packing list, as today.
- AC-RPL-13 Stock ask: a West-only contact's ETA and packing-list file come from the earliest West packing list; an East-only container gives them no ETA; a West + East container counts.
- AC-RPL-14 Chatbot "has incoming" stamps and did-you-mean / cross-domain probes follow AC-RPL-9..11 (they call `/incoming-stock/list` with the contact).
- AC-RPL-15 A packing list's regions change applies on the next ask.
