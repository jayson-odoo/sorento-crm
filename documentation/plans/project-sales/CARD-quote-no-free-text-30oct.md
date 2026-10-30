# Behaviour card: QUOTE-NO-FREE-TEXT (every quotation line is a catalogue product or set)

Source: owner 30 Oct ~21:15, verbatim: "Free text product shouldn't be allowed, simple as that."
Base: origin/main 38e718714e. Paths below are under `sorento_crm_backend/app/` unless they start with `sorento_crm_frontend/`.

## Rule

1. A quotation line saves only when it names a catalogue product OR a catalogue product set. No product and no
   set = refused (422), on every write path, whatever the description says.
2. The description stays editable on a catalogue line (it is the printed text, `QuotationLinesGrid.tsx` DescriptionCell).
   Only the "no product at all" line goes.
3. Issued (frozen) versions are never re-saved, so already-sent PDFs and sign pages do not change.

## Today on main

- Model: `product_id` nullable, comment "an off-catalog line is legitimate" (`models/projects.py:1625-1629`), FK
  ON DELETE SET NULL; set FK SET NULL too (:1634-1636); only CHECK = not both (:1690-1693).
- API: `product_id` "Null for an off-catalog line", description "Required when there is no product or set"
  (`schemas/projects.py:1278-1290`). Only guard: no product + no set + no description -> 422
  `quotation_line_description_required` (`services/project_quotation_service.py:978-983`). Product-less line is
  stored `is_non_standard` (:699).
- UI: new line starts `product_id: ''` (`quotationLineDraft.ts:63`), needs only a description (:99-103), sends
  `product_id: null` (:131-132); picker clearable (`QuotationLinesGrid.tsx:476`), clearing keeps the description
  (:1289-1298); flag "Not a catalogue product" (`QuotationLineFlags.tsx:86`).

## Every path that writes a line (all funnel through `_write_line`, svc:851, except the seed script)

| Path | Where | Free text today | After |
|---|---|---|---|
| Add one line | POST version lines `api/v1/projects/quotations.py:501-527` -> `upsert_line` svc:999 | yes | 422 |
| Save all lines (editor) | PUT version lines `quotations.py:532-567` -> `replace_lines` svc:1021-1100 | yes | 422, whole save rolls back |
| Edit one line | PUT `.../lines/{id}` `quotations.py:578-597` | yes (send `product_id: null`) | 422 |
| New quotation form | POST quotation-documents `quotation_documents.py:124-150` -> `replace_lines` | yes | 422 |
| Edit quotation form | PATCH document `quotation_documents.py:193-243` -> `apply_form_scopes` | yes | 422 |
| New revision | `revise` svc:371-455 copies lines as-is (:403-433) | carries old ones | copies; see Q1 |
| Customer amendment apply (#1984) | `quotation_amendment_service.py:581-673`, qty/price via `upsert_line` | re-saves old ones | see Q1 |
| Customer amendment submit, sign page | `public/quotation_sign.py:150-167`; schema has line_id/qty/price/remove only (`schemas/projects.py:2191-2200`) | no | no change |
| Seed demo script | `scripts/seed_project_cs_demo.py:267-282`, `product_id=None` for unknown code (:270) | yes | skip unknown codes |
| Portal, AI extract / project register, imports, external API, chatbot, MCP (`crm_project_quotations_list` GET only, `sorento_crm_mcp/catalog.py:1738-1757`) | read only | no | no change |

No customer-portal quotation form exists (portal routes are price-tag requests), so there is no portal form to match.

## Real data

- Crew dev copy (`sorento_prod_1020`, read-only aggregate, 30 Oct): 10 quotation lines in total, 0 with no product
  and no set, 0 of those rate-only. Example of the real shape (dev copy, from CARD-quote-sign-page-29oct.md):
  PRJQ-2026-0003 "Townhouse": 32MM TAIL PIECE COUPLING 1 EA x RM 300.00 and BRAC73080604-0001 1 EA x RM 500.00,
  both catalogue lines. A further per-line read was refused by the agent's production-read guard (the dev copy is a
  prod restore), so no more examples were pulled.
- Production count: UNVERIFIED (crew lanes never read prod). Owner-run read-only SQL:
  `documentation/plans/project-sales/SQL-quote-no-free-text-count-30oct.sql` (totals, by outcome/month, by quote no).

## Edge cases and questions (each with a recommendation)

Q1. Existing free-text lines on old quotes. (a) Issued versions untouched; a DRAFT version that holds one (old
draft, or a new revision copied from an issued one, svc:403-433) shows the row in red "Pick a catalogue product",
and Save / Issue / amendment Apply are refused until that row gets a product or is removed. (b) Grandfather: an
unchanged existing free-text line may be re-saved, only new ones are blocked (needs per-line identity tracking
through `replace_lines`, which rewrites lines). (c) A data fix converting them. Rec (a): one rule, no tracking,
dev has 0 such lines; run the SQL above first to size it.

Q2. Product or set deleted while on a quotation. Today both deletes are HARD (`services/product_service.py:1287-1299`,
`services/product_set_service.py:312-316`) and the quotation line silently becomes a free-text line (FK SET NULL).
(a) Refuse the delete with a 409 naming the quotation, the same guard shape as the new-product-application check
(`product_service.py:1301`); (b) leave it, the line falls under Q1; (c) migration to FK RESTRICT. Rec (a): no
migration; a sales-order line already blocks a product delete the same way (RESTRICT, `models/project_so.py:360`).

Q3. Flags. (a) Drop "Not a catalogue product" (`QuotationLineFlags.tsx:86`); a leftover legacy line shows the Q1
red "Pick a catalogue product" instead; keep "Non-standard" (:90), which still means "product outside the
project's series" (svc:699). (b) Keep both labels as they are. Rec (a).

Q4. Bespoke item (not in the catalogue yet). (a) No inline create: staff file a New Product Application (existing
flow, `procurement.new_product_applications.create`), purchasing opens the code (`...open_code`), then it is quoted
like any product. (b) A "create product" shortcut inside the quote editor. Rec (a): existing flow, no new screen,
purchasing keeps control of the catalogue.

Q5. Where the rule lives. (a) API + UI now: one check in `_write_line` (every path above goes through it), schema
text updated, no migration. A DB CHECK (product or set NOT NULL) waits until the SQL shows 0 legacy lines in prod,
and would also need Q2(a) or RESTRICT, since a SET NULL delete would break it. (b) DB CHECK now (migration, held for
owner approval as destructive). Rec (a).

## Screen change

Only the free-text path goes: no description-only "Add a line"; a line without a product shows the red error and
blocks Save; the picker is no longer clearable on a saved line (clearing = remove the line). No new screen, so no
mock (brief: mock only if the screen changes beyond removing the free-text path).
