# UAC - New product application from a stock inquiry: ask, AI draft, match, reserve code (NPA-AI-ASSIST)

Plan: `PLAN-npa-ai-assist-04nov.md`. Builds on the merged NPA lane
(`PLAN-new-product-application-17oct.md`, `new-product-application-acceptance-criteria.md`); every rule there
still holds unless an AC below says otherwise.

## Journey

Actors: **purchasing** (staff), **sales rep** (portal contact via the WhatsApp link, or a staff user with
`procurement.new_product_applications.create`), the system.

1. Purchasing opens a stock inquiry at Pending purchasing (or Responded) and finds no product fits. In the
   **Edit purchasing response** dialog they tick **Ask for a new product application** and press
   **Update & Reply**. The rep receives the reply on WhatsApp with a link to start the application. The inquiry
   is Responded and shows a "New product application requested" marker.
2. The rep opens the inquiry (portal or CRM) and presses **Create new product application**. The form opens
   already filled: AI has written the remark (what the rep wants, in plain words) and the product lines
   (product type, dimension, material, thickness, packing, qty, brand) from the inquiry, purchasing's reply and
   the inquiry's images. Where the inquiry names an existing product the rep wanted "something like", that
   product is filled in as the line's **reference product**. The rep checks and edits anything, then submits.
3. On submit, every line that has a reference product shows the rep the products already in the list that
   match it (exact first, then up to 5 similar). For each such line the rep either **uses** an existing
   product (the line is done; no purchasing work for it) or says **none of these** (the line goes on as a new
   code request). Lines without a reference product skip this step. If every line was settled by the rep, the
   application completes on the spot.
4. Purchasing opens the submitted application. Each open line shows its matches (computed for every line) and,
   where the rep already said "none of these", which products the rep turned down. Purchasing either
   **links** an existing product (today's Link) or **reserves a new code** for the line.
5. Purchasing opens the reserved code in AutoCount as today. When the product arrives in the CRM (AutoCount
   pull, ESB ingest or manual create), the line links itself to it and the application completes when every
   line is done. Nobody has to come back and press Link.

What every other stakeholder is told: the rep gets the WhatsApp reply in step 1 (existing reply path) and the
existing NPA notifications at submit / approve / complete; nothing new is sent.

Out of scope, deferred with a named trigger: **system-suggested item codes** in "the new format". The owner
will define the format later (owner, 4 Nov 2026); until then purchasing types the reserved code and the system
only checks it is free. Backlog entry: BL-072 in `documentation/backlogs/backlog.md`.

## Phase 1 - FE against mocks

- **AC-NAI-01 [FE]** Given the Edit purchasing response dialog on an inquiry at Pending purchasing or
  Responded, then an **Ask for a new product application** checkbox shows under the response text, unticked.
- **AC-NAI-02 [FE]** Given an inquiry with the request marker set, then the detail header shows a
  "New product application requested" pill until a linked application exists, after which the existing
  "New product applications" row replaces it.
- **AC-NAI-03 [FE]** Given a Responded inquiry, the **Create new product application** action shows (staff ⋯
  menu and portal inquiry view) only when the request marker is set and the viewer may create applications.
- **AC-NAI-04 [FE]** Given the create form opened from an inquiry, then while the draft loads the sheet shows
  a skeleton (no spinner over a blank form), and on arrival every AI-filled field is editable in place. A
  one-line notice "Drafted from SI-xx-xxxx. Check before you submit." sits above the sheet (no explanation of
  how AI works).
- **AC-NAI-05 [FE]** Given the AI draft failed, then the form opens with today's plain copy and the notice
  reads "Copied from SI-xx-xxxx." - no error toast, nothing blocks the rep.
- **AC-NAI-06 [FE]** Each product line has a clearable **Reference product** `SearchableSelect` (product code -
  name, never an id).
- **AC-NAI-07 [FE]** Given the rep presses Submit and at least one line has a reference product, then a
  **Check matches** modal lists, per such line, the exact match (if any) then up to 5 similar products with
  code, name, brand and a **Use this** button, plus **None of these** per line. Submit in the modal stays
  disabled until every listed line has a choice.
- **AC-NAI-08 [FE]** Given the purchasing view of a submitted / approved application, each unresolved line
  shows a **Matches** cell: up to 5 products with **Link**, products the rep turned down struck through with
  "Rep: none of these", and a **Reserve new code** action.
- **AC-NAI-09 [FE]** Given Reserve new code, a modal takes one code input; an in-use code shows the inline
  error "Already used by <code - name>" (or "Reserved on NPA-xxxxxx line N").
- **AC-NAI-10 [FE]** A line with a reserved code shows "Reserved: <code> - waiting for AutoCount" in the
  Opened as column, with **Undo** for `open_code` holders.
- **AC-NAI-11 [UX]** All of the above usable and unclipped at 375 px and 1280 px; the matches modal stacks one
  line per card under 640 px. No new motion: no animation on match lists, pills or the notice.

## Phase 2 - BE (tests first)

### Ask (journey step 1)

- **AC-NAI-20 [BE]** Given `POST /stock-inquiries/{id}/update-and-reply` with `request_npa: true` at
  pending_purchasing or responded, then the inquiry stores `npa_requested_at` / `npa_requested_by`, the status
  becomes responded (existing rule), and the queued Respond.io message carries the NPA start link (portal NPA
  new-form URL with `stock_inquiry_id`).
- **AC-NAI-21 [BE]** `request_npa` omitted or false leaves `npa_requested_*` unchanged (never clears an
  earlier request).
- **AC-NAI-22 [BE]** The stock inquiry detail payload carries `npa_requested_at` and
  `npa_requested_by_name` (asserted through the `response_model`).
- **AC-NAI-23 [BE]** Staff `GET /new-product-applications/prefill` and portal
  `GET /new-product-application/prefill` answer 409 `npa_not_requested` for an inquiry without the marker;
  portal `GET /new-product-application/inquiries` lists only own responded inquiries with the marker.

### AI draft (journey step 2)

- **AC-NAI-30 [BE]** Given a marked inquiry, prefill returns the Write-shaped body with `remark` and `lines[]`
  (`description`, `dimension`, `material`, `thickness`, `packing`, `expected_qty`, `brand_id`,
  `reference_product_id`) drafted by the configured LLM provider from: the inquiry fields, the purchasing
  response, and the inquiry's image attachments; plus `drafted_by: "ai"`.
- **AC-NAI-31 [BE]** `brand_id` and `reference_product_id` are only ever ids that resolve in the caller's
  company (brand via `LookupResolverService`, product via exact code); an unresolvable value is dropped, never
  guessed.
- **AC-NAI-32 [BE]** Given the provider raises, times out (`npa_ai_timeout_seconds`, default 20) or returns
  invalid JSON, prefill returns today's plain copy with `drafted_by: "copy"` and status 200.
- **AC-NAI-33 [BE]** Each AI draft logs one `AIAssistantUsageLog` row tagged `feature=npa_draft`.
- **AC-NAI-34 [BE]** `reference_product_id` is a new nullable line column in the Write schema (staff and
  portal); an id of another company's product is 422.

### Matching (journey steps 3-4)

- **AC-NAI-40 [BE]** `GET /new-product-applications/{id}/lines/{line_id}/matches` (and the portal twin, own
  application only) returns `{exact: Product|null, similar: Product[<=5]}` for the line, company-scoped,
  active products only, never including `exact` again in `similar`.
- **AC-NAI-41 [BE]** Exact = a product whose code equals the line's `proposed_code`, or the reference
  product's code, compared case- and whitespace-insensitively. Similar = ranked by the existing resolver
  tiers over the line text (description + dimension + material + thickness + packing + brand + the reference
  product's name): trigram first, embedding fallback. Golden set: a fixture catalogue of 10 products and 6
  line texts with expected top-1 written as failing tests before the ranker is wired.
- **AC-NAI-42 [BE]** `POST /{id}/lines/{line_id}/use-match {product_id}` by the owner on an unlocked (draft or
  rejected) application's line that has a reference product sets `opened_product_id`, `resolved_by` = the rep (portal: the contact's act-as
  user), `resolved_at`; the product must be one of that line's matches (else 422).
- **AC-NAI-43 [BE]** `POST /{id}/lines/{line_id}/reject-matches` by the owner stores
  `rejected_match_product_ids` (the ids shown) and `matches_rejected_at` on the line.
- **AC-NAI-44 [BE]** Submit with any line that has a reference product and neither a resolution nor
  `matches_rejected_at` answers 422 "Product N: check the matches first."; lines without a reference product
  are never blocked.
- **AC-NAI-45 [BE]** When the rep's choices resolve every line, the application moves to completed (existing
  auto-complete) without passing through approved, and purchasing is not notified for approval.
- **AC-NAI-46 [BE]** Detail payload lines carry `reference_product_code`, `reference_product_name`,
  `rejected_match_product_ids`, `matches_rejected_at`.

### Reserve code and auto-link (journey step 5)

- **AC-NAI-50 [BE]** `POST /{id}/lines/{line_id}/reserve-code {code}` (`open_code`, application approved)
  stores `reserved_code` (trimmed, uppercased), `reserved_by`, `reserved_at`. 409 when the code equals an
  existing product code in the company or another open line's `reserved_code` (normalized as AC-NAI-41).
- **AC-NAI-51 [BE]** When a product is inserted in the company (any path: AutoCount pull apply, ESB ingest,
  manual create) whose normalized code equals a line's `reserved_code`, the same transaction sets that line's
  `opened_product_id`, `resolved_at`, `resolved_by = NULL` (system), and the application auto-completes when
  every line is done.
- **AC-NAI-52 [BE]** `POST /{id}/lines/{line_id}/undo` also clears `reserved_*`; reserve on a line that is
  already linked or closed is 409.
- **AC-NAI-53 [BE]** Audit history shows reserve, auto-link, use-match and reject-matches on the application.

### Migration / permissions

- **AC-NAI-60 [T]** One migration (id <= 32 chars, single head): `stock_inquiries.npa_requested_at`,
  `npa_requested_by`; `new_product_application_lines.reference_product_id` (FK products SET NULL),
  `rejected_match_product_ids` JSONB, `matches_rejected_at`, `reserved_code`, `reserved_by`, `reserved_at`.
  Uniqueness of `reserved_code` is checked in the service (AC-NAI-50), not by an index.
- **AC-NAI-61 [T]** No new permission slug: ask rides Update & Reply; use-match / reject-matches ride owner
  rights; reserve-code rides `open_code`.

## Phase 3 - E2E

- **AC-NAI-70 [E2E]** agent-browser, sidebar clicks from `/`: purchasing asks on an inquiry -> rep (portal)
  creates from it, sees the AI draft, edits a field, sets a reference product, submits, rejects matches ->
  purchasing reserves a code -> a manual product create with that code -> the line shows the linked product and
  the application is Completed. Screens at 375 and 1280.
