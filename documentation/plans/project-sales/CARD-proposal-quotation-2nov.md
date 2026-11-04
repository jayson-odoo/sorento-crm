# Behaviour card: PS-PROPOSAL-QUOTATION (proposal vs quotation, PO tallies with the quotation)

Source: owner rulings 2 Nov 2026 ~21:05 MYT, after the "Demo on Project Sales Module" meeting.
Plan: `PLAN-proposal-quotation-2nov.md` (same folder). Code read on origin/main 46de2f6d.

## What exists today (facts)

- A project "quotation" is a DOCUMENT (`projects.quotation_documents`, `models/projects.py:1075`) holding
  scopes (`quotations`, :1516), each scope a chain of versions (`quotation_versions`, :1574) with lines
  (:1618). Sending it creates an ISSUE R1, R2 ... (`quotation_issues`, :1225) that freezes which version of
  each scope went out (`quotation_issue_scopes`, :1473). A project can already hold several documents.
- Number: running-number rule doc_type `project_quotation`, seeded `PRJQ-{year}-` + 4 digits
  (`alembic/versions/327_quotation_document_layer.py:254-270`); printed `PRJQ-2026-0003-R1`
  (`project_quotation_document_service.py:122-128`). No A/B/C lettering anywhere.
- Recipient: `recipient_party_id` + snapshots on the document, defaulted from the project's developer
  (`project_quotation_document_service.py:156-178`). Party types: developer, architect, main contractor,
  trading house, consultant (`project_reference_service.py:26-32`). No tender party, no subcontractor.
- Customer counter-sign on the public page WINS every scope the issue carried
  (`project_quotation_document_service.py:1153-1275`); project outcome = won if any scope won (`project_quotation_service.py:1349`).
- Approval: only a line below its minimum price needs a manager (`project_quotation_approval_service.py:118-143`),
  gate at Issue, deciders hold `projects.quotations.approve` (:63).
- PO: bound to ONE scope version (`purchase_orders.quotation_version_id`); each line checked for model and
  price against it (`project_po_service.py:298-325`); quantity never compared (:301). Scanned POs auto-bind
  to the single best scope (`project_po_confirm.py:296-360`).
- "Management" for alerts = users holding `projects.projects.manage` (`project_notify_service.py:34-74`).

## Rules after this lane

1. **Proposal.** Every quotation document that exists today, and every new one made from the Quotation
   tab, is a PROPOSAL. The tab, the document page, the PDF, the sign page and the emails say "Proposal".
   Revisions continue as today (edit, issue, revise), labelled per Q1.
2. **Addressed to a party.** A proposal's "To" is picked from the project's parties: developer, architect,
   main contractor, the firms of the project's stakeholders, plus two new party types **Tender party** and
   **Subcontractor** next to Trading house and Main contractor. One proposal per party, each its own
   number, so the main con and the trading house can hold different prices.
3. **Price alert.** Issuing proposal revision 2+ compares every line with the previous revision of the SAME
   proposal (matched by product, set, or printed code). Any unit price that changed (up or down) sends
   management one in-app + email alert: project, proposal no., party, each product old -> new price.
   Not a gate: the revision still goes out. Added or removed lines alone do not alert.
4. **Convert to quotation.** Only when the project is Won. The salesperson opens a proposal, picks one issued
   revision (e.g. PRJQ-2026-0003-B) and presses "Make quotation". This creates a QUOTATION: a new document of
   kind quotation, own number (Q1), "From proposal PRJQ-2026-0003-B" link both ways, same party, letter,
   terms, payment terms, validity, scopes (lost scopes left out) and lines copied from that revision. It needs
   its own Sorento signature before Issue. One quotation per project; a wrong pick is deleted (deferred delete,
   as today) before it is issued and made again.
5. **Further discount.** On the quotation, a line priced BELOW the same product's price on the proposal
   revision it came from needs management approval before Issue (the same approve/reject flow and approvers
   as the minimum-price gate). Prices equal or higher, and quantity changes, need nothing. The minimum-price
   rule keeps applying on top.
6. **PO tallies with the quotation.** Once a project has a quotation, a PO is checked against the quotation
   (auto-bind picks it; binding a NEW PO to a proposal is refused with "This project has a quotation, check
   the PO against it"). Model and price per line as today. NEW: the total quantity per product over all live
   POs of the project is compared with the quoted quantity; above it, Save / Confirm asks the salesperson for a
   reason (soft stop: with a reason it saves, it never blocks). The reason shows on the PO with a "Qty over
   quote" badge and management gets one alert.
7. **Existing data** (Q2): nothing is rewritten. Old documents read as proposals with their numbers, issues,
   signatures and won scopes untouched; old POs keep the version they are bound to.
8. **PDF** (cover page #2088 merged; designer #2094 open): one render path for both kinds; only the words
   change: "Proposal No." / "PROPOSAL" vs "Quotation No." / "QUOTATION", file `proposal-<no>.pdf` /
   `quotation-<no>.pdf`. The cover page and, once merged, the designer apply to both.
9. **Reports and bot.** Forecast pipeline sums OPEN scopes only (`project_forecast_service.py:106-141`); the
   quotation's scopes are created Won, so nothing counts twice. Conversion rate reads project outcome:
   unchanged. MCP `crm_project_quotations_list` (`catalog.py:1737`) gains `document_kind`
   (proposal / quotation) and the document number, so the bot can say which one it reads.

## Examples (dev data shape; real rows requested with crew-data-request, cloud has no prod copy)

- A. PRJQ-2026-0003, one scope "Townhouse", 32MM TAIL PIECE COUPLING 1 EA x RM 300.00 + BRAC73080604-0001
  1 EA x RM 500.00 = RM 800.00, to CUSTOMER A. Revision B drops the coupling to RM 280.00 -> management alert
  "PRJQ-2026-0003-B: 32MM TAIL PIECE COUPLING RM 300.00 -> RM 280.00". Revision C changes qty only -> no alert.
- B. Project won. Salesperson picks PRJQ-2026-0003-B -> quotation QT-2026-0001 (lines RM 280.00 / RM 500.00).
  Bracket set to RM 480.00 -> "Needs approval" before Issue. Bracket set to RM 520.00 -> issues freely.
- C. PO 1 for 1 EA coupling at RM 280.00: OK. PO 2 for 1 more EA: total 2 > quoted 1 -> "Quantity over the
  quotation: 32MM TAIL PIECE COUPLING ordered 2, quoted 1. Reason?" -> salesperson types "Variation order
  VO-3" -> saved, badge + management alert.
- D. Same project, second proposal to the trading house (PRJQ-2026-0004, RM 290.00 per coupling): a separate
  proposal; its prices never alert against PRJQ-2026-0003 (alerts compare within one proposal).
- E. An old document PRJQ-2026-0002 issued R1 and signed in October: now titled Proposal PRJQ-2026-0002-R1,
  still signed, its scopes still won, its PO still checked against the version it was bound to.

## Edge cases

- Project not won: "Make quotation" hidden; the API answers 409 `project_not_won`.
- Revision picked that is not the latest: allowed (the customer may have accepted an older one).
- Quotation line for a product not on the source proposal: no discount comparison, minimum price only.
- PO with no product on a line (printed code only): qty summed per printed code.
- PO lines on a cancelled or superseded PO do not count toward the total.
- Quotation revised after a PO: the check uses the quotation's current revision quantities.
- A quotation is signable on the same sign page; signing records acceptance (its scopes are already won).

## Touches shared with parallel lanes

- PS-QUOTE-RULES (#2096): both add a reason to `requires_approval` (`project_quotation_approval_service.py:139`);
  whoever merges second folds both reasons in. "Discount request -> Final Negotiation" stays theirs.
- PS-REGISTRATION-V3 (#2099): party master data. This lane only adds the two party TYPES (one tuple); if #2099
  adds them first, this lane drops that line.
- QUOTE-COVER-DESIGN (#2094): PDF title words only; no layout change here.

## Questions (each with a recommendation)

Q1. Revision labels and numbers. (a) Proposals issued from now print letters: PRJQ-2026-0005-A, -B, -C; a
proposal that already has an R1 keeps counting R2, R3 so nothing already sent changes its name. Quotation gets
its own rule doc_type `project_sales_quotation`, seeded `QT-{year}-` + 4 digits (editable in Settings >
Numbering), revisions -R1, -R2. (b) Keep R numbers for proposals too. Rec (a): it is what was asked, and
storing the label per issue keeps old paper and screen identical.

Q2. Existing documents. (a) All become proposals as they stand; no quotation is created by the migration; a
won project converts when the salesperson next needs one. (b) Migration auto-converts each SIGNED issue into
a quotation. Rec (a): a migration that writes customer documents nobody chose is hard to undo, and old POs
already have their comparison.

Q3. Sign page. (a) Proposals AND quotations can be signed on the same page, words follow the kind; signing a
proposal still marks its scopes Won (as today), which is what unlocks "Make quotation". (b) Proposals become
view + suggest changes only, only a quotation is signed; Won is set by the salesperson. Rec (a): no change to
how customers win a project today, and the quotation still gets its own signature.

Q4. "Further discount" on the quotation. (a) Any line below the same product's price on the source proposal
revision -> management approval (rule 5). (b) Any price change at all on the quotation -> approval. Rec (a):
an increase is not a discount, and (b) would send every typo fix to a manager.

Q5. PO quantity reason. (a) One reason per PO save, covering every product over (rule 6), asked again only if
the PO has no reason yet. (b) One reason per product line. Rec (a): a PO is entered in one sitting, one
reason ("VO-3") usually explains the whole overage, and management sees it on the PO.
