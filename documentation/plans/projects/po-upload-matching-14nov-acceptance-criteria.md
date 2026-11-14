# UAC: PO upload matching (PO-UPLOAD-MATCHING)

Draft against the behaviour card's recommended answers (Q1 b, Q2 a, Q3 a, Q4 a, Q5 a).
Re-checked once the owner answers. Product codes below are catalogue shapes, no customer data.

## M - matching

- **AC-M1 exact code first.** A line whose stock code equals a catalogue code (case-insensitive,
  PO company only) resolves to it with `resolution_source = "code"`, no model call, no pill.
- **AC-M2 remembered code next.** A customer code found in `projects.customer_item_code_map` for
  the PO's customer (and company) resolves with `resolution_source = "map"`, no model call, no
  pill. A map hit wins over any model suggestion.
- **AC-M3 model suggestion.** Every other line goes to the `po_line_matcher` prompt in batches
  (at most 40 lines per call), with candidates: the bound quotation version's lines, the
  customer's remembered codes, and the catalogue shortlist from `resolve_references`
  alternatives for that line's code/description tokens. The model answer per line is
  `{line_no, product_code | null, confidence: high|medium|low, options: [code, ...]}`.
  - A picked code that is NOT in that line's candidate list is discarded (no invented products).
  - A pick sets `resolved_product_id` and `resolution_source = "suggested"`; confidence and the
    options are kept on the version (`extracted_json.line_matches[line_no]`).
  - No pick with 2+ options: line stays unmatched, options kept (picker shows them first).
- **AC-M4 the description-token rule and the loose string tiers are gone.** A description
  holding "40MM" never resolves to product `40MM` by itself.
- **AC-M5 failure is quiet.** Model unavailable, timeout or bad JSON for a batch: those lines stay
  unmatched; the read still finishes `done`; other batches keep their suggestions.
- **AC-M6 examples.** With catalogue `SRTWC8518-SH`, `CKS903`, `TPE-9201-300`, `SRT73-CR`,
  `CB310-CR-L`, `CB310-CR-PJ` and a stubbed model: `SORENTO BBTSRTWC8518 -SH`,
  `CABANA BBTCKS903`, `BBTTPE-9201-300`, `SORENTO BBTSRT73-CR **` come back suggested to those
  codes; `CABANA CB310-CR` comes back unmatched with options `CB310-CR-L`, `CB310-CR-PJ`.

## A - accepting and remembering

- **AC-A1 accept one.** Accepting a suggested line sets `resolution_source = "accepted"` and
  writes/overwrites the map row (customer, customer code -> product, confirmed_by = actor).
- **AC-A2 accept all.** One call accepts every suggested product AND every suggested qty on the
  version; each line goes through the same function as AC-A1 (one shared function).
- **AC-A3 manual pick remembers.** Picking a product by hand (`resolution_source = "manual"`)
  also writes the map row. Clearing a product does not delete a map row.
- **AC-A4 one shared map helper.** Delivery-schedule matching and PO matching read/write the map
  through the same helper (no second copy).
- **AC-A5 next upload.** A second PO for the same customer with the same customer code resolves
  via the map (AC-M2).

## Q - quantity

- **AC-Q1 no silent qty 1.** Confirm never writes quantity 1 for a line whose qty is empty.
- **AC-Q2 suggested qty.** At read time, qty empty + unit price + amount read and
  amount / unit price is a whole number > 0: qty is set to it and flagged suggested
  (`extracted_json.line_matches[line_no].qty_suggested = true`). Not whole: qty stays empty.
- **AC-Q3 Confirm gate.** Confirm answers 422 `po_version_lines_need_attention` naming the line
  numbers while any live (not cancelled) line has an empty qty, a suggested product not yet
  accepted, or a suggested qty not yet accepted. Editing the qty by hand clears the suggested flag.

## T - totals

- **AC-T1 printed total read.** The page schema carries a nullable `printed_total`; the
  extraction keeps the last non-null page value as `extracted_json.printed_total`, which
  `recompute_totals` already prefers.
- **AC-T2 banner wording.** With a printed total: "Document total X" and "above/below the total
  printed on the document" as today. Without one: the label reads "Sum of lines read" and the
  above/below sentence is not shown. The API says which (`totals.printed_total_read: bool`).

## UI (existing PO intake screen, no new screen)

- **AC-U1** a suggested line shows a `Badge` "Suggested" in the Flag column; the product cell
  shows the suggested product as today. A suggested qty shows the same pill.
- **AC-U2** one secondary button "Accept all suggestions (N)" on the lines toolbar while N > 0;
  right-click a suggested line -> "Accept suggestion". Confirm stays the one main button.
- **AC-U3** a line with options and no pick: the product picker lists the options first.
- **AC-U4** usable at 375 px and 1280 px.
