# UAC - Packing list region (REGION-PACKING-LIST)

Draft on the card recommendations (Q1-Q5 = (a)); revised when the owner answers.

## Packing list
- AC-RPL-1 A new packing list from any path (upload, Create, proforma convert, external API) is West Malaysia unless East is chosen.
- AC-RPL-2 The Upload dialog shows a required Region select only for the Packing List type, West preselected; the region picked reaches the packing list n8n creates from that file.
- AC-RPL-3 External create: an explicit `region` in the payload wins, else the attachment's region, else West.
- AC-RPL-4 Region is shown and editable on Create Packing List and on the detail page (same layout, edit in place); any value other than West / East is refused (422).
- AC-RPL-5 The packing list list has a Region column and a Region filter.
- AC-RPL-6 Backfill: every existing packing list reads West after the migration.

## Contact
- AC-RPL-7 Every contact holds one or more regions, default West; the Chatbot settings card shows a Regions multi-select; saving an empty set is refused (422); GET returns `regions`.
- AC-RPL-8 Backfill: every existing contact holds West only.

## What a contact is told
- AC-RPL-9 A contact holding East sees East and West packing lists on `/incoming-stock/list`, `/by-product`, `/shipments`, `/shipments/{id}/products`, `/shipments/{id}/attachment`.
- AC-RPL-10 A West-only contact sees no East packing list on any of those routes: no row, no line, no ETA, no file; totals and paging count only what they see.
- AC-RPL-11 An unresolved contact is treated as West only, including a respond_io_id that matches several contact rows (never the union of their regions).
- AC-RPL-12 No contact in play (staff session, bare API key) sees every packing list, as today.
- AC-RPL-13 Stock ask: a West-only contact's ETA and packing-list file come from the earliest West packing list; an East-only container gives them no ETA.
- AC-RPL-14 Chatbot "has incoming" stamps and did-you-mean / cross-domain probes follow AC-RPL-9..11 (they call `/incoming-stock/list` with the contact).
- AC-RPL-15 A packing list's region change applies on the next ask.
