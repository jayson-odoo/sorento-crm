# PLAN: price tag AI extract matches through the entity resolver; Add part only on a product with a combo

Status: BUILDING 15 Sep 2026 (owner go, chat 15 Sep)
Domain: dealer-kit
UAC: price-tag-ai-extract-resolver-acceptance-criteria.md
Branch: fix/price-tag-ai-extract-resolver  (lane stack :3080 / :8080)

## Why

Owner screenshot 15 Sep: an AI Extract of a 13-line sales order on the portal price tag form
reads "Not found" on 11 rows. Nine of those codes exist as active products. The extract path
has its own matcher, twice, and neither normalises separators:

- BE `app/services/ai_extract/extract_service.py` `_canonical_product_code`: `product_code ILIKE raw`
  with no `%` and no dash/whitespace stripping. `Srt6536 DIY` never meets `SRT6536-DIY`.
- FE `PriceTagRequestForm.tsx` `handleAIExtracted`: one `lookupTagItems(code)` call per row, then
  `i.code.trim().toLowerCase() === code` exact equality. Same failure.

`/api/v1/system/references/resolve` already answers this correctly through
`app/services/entity_resolver.py` (`_probe_product`, `_probe_product_set`): both sides
whitespace-and-dash stripped, casefolded, exact match, company-scoped, sets included.

Owner's rule (15 Sep): **one matcher.** Every entity match in the product goes through
`resolve_references`, so a change to the resolver reaches every consumer. The price tag AI
extract is the consumer fixed here; the FE keeps no matcher of its own.

Second finding, same screenshot: every product line shows an "Add part" search, including a
product that has no combo. Owner: if the product has no combo, there is nothing to add a part
to. The combos lookup already answers "this product has no combo"; the form ignores it. Also
enforce it on save, so the portal cannot post parts onto a no-combo product.

Third finding (owner screenshot 15 Sep, request PT-202609-0004 detail page, Lines tab): a
product with no combo still renders as two rows, the line row with empty price columns and a
"1a" tag row carrying the price, tag status and Design action. Owner: with no combo, just one
row per product; no 1a / 2a.

Fourth finding (owner screenshot 15 Sep, the tag designer's Lines rail): the same split, a
line block ("P SRTWT8203, Qty 1 / Shower") with a "1a" tag row under it carrying the price,
the check and the actions. Owner: a line with no parts is one row on the rail too.

Fifth finding (owner screenshot 15 Sep, designer rail): the Tag Size panel (preset select, W,
H, Apply to all lines) is always open and takes the rail space the lines need. Owner: make it
collapsible; it is not needed most of the time.

Sixth finding (owner, live 15 Sep 3:29 pm, PT-202609-0004 "design is ready"): the Respond send
failed with `24h window closed and template send skipped for use case 'price_tag_update': no
default template configured`, and the WhatsApp Templates settings page has no row for that
use case, so it cannot be configured. `price_tag_notify.USE_CASE = "price_tag_update"` is
absent from `TEMPLATE_DEFAULT_USE_CASES` (BE) and from `USE_CASES` in
`services/whatsappTemplateService.ts` (FE), and `build_context_vars` has no branch for it, so
even a configured template would have no entity number or portal link to fill.

Seventh finding (same outbox): the Contact column reads "-" on the list and a UUID in the
modal. `price_tag_notify._send` passes `request.contact_id` (a `respond_contacts.id` UUID)
straight through as the send identifier and logs it as `external_reference`; the outbox
resolves name and phone by `respond_io_id`, so the UUID never resolves. The OTP path already
does it right: `contact.respond_io_id or contact.id`.

Eighth finding (owner screenshot 15 Sep, designer rail): the orange open-pins count on a tag
row sits under the Use template button. `TagRailRow` puts the count inside the row button
with `ml-auto` and `pr-8`, while the actions are `absolute right-1` and two icons wide.

Ninth finding (owner question 15 Sep): "how do I dismiss the comment" on the design page. The
canvas pin popover only closes; Done lives on the request detail page's Design section
(`RequestDesignSection`, AC-S2-5 of r9). The designer is where the fix is made, so the
decision belongs there too.

## Decisions

- D1 `_canonical_product_code` is deleted. `_extract_products` calls `resolve_references(db,
  codes, allowed_entity_types={"product", "product_set"}, enable_prefix_fallback=False,
  enable_embedding_fallback=False, max_candidates=len(codes))` ONCE for the whole list, inside
  the portal token's `company_scope` (the same scope the sibling lookups in
  `portal_price_tag.py` use). Exact tier only, because a prefix or semantic guess prints a tag
  for a product the sheet did not name. Both flags are parameters, not code, so widening later
  is a one-line change.
- D2 `ExtractedProductLine` gains `match: Literal["product", "product_set"] | None`,
  `product_id: str | None`, `product_set_id: str | None`. Exactly one match: `product_code` and
  `product_name` become the canonical row values, `match` and the id are set. No match, or an
  ambiguous token (more than one scoped hit): `match` is `None`, the ids are `None`, and
  `product_code` keeps the raw extracted text so the dialog can show what was read.
- D3 The FE drops the per-code `lookupTagItems` call and the equality check. `handleAIExtracted`
  reads `match` / `product_id` / `product_set_id` off the payload and builds the same
  `{kind, id, code, name}` record `aiMatchesRef` already holds, so Apply is untouched. Status
  `'loading'` disappears: the answer arrives with the extract.
- D4 `showParts` in `LineRow` becomes `!isSet && !!line.product_id && line.combos_loaded &&
  line.combos.length > 0`. Existing part rows (a reopened draft) still render with their
  Remove; only the "Add part" search is hidden. Supersedes AC-S2-4 of the combos plan ("on any
  line, combo or not").
- D5 Server: `PriceTagRequestService._add_line_parts` (and so `replace_lines` and create) raises
  the existing validation error shape (422, naming the line index) when `parts` is non-empty and
  the line's product has zero `ProductCombo` rows. A `product_set` line is already skipped.
- D7 Detail page Lines tab (`PriceTagRequestDetail.tsx`, the `request.lines.map` table): a
  line with exactly ONE tag and NO parts renders as a single row. That row is the line row with
  the tag's cells folded in: List Price, Sell Price (+ override), Tag status
  (Designed / No tag / Changed) and the Actions cell (Review / Design) come from the one tag;
  the `1a` label is not shown; `aria-label`s keep the tag label so the existing tests' selectors
  still resolve. A line with parts, or two or more tags, keeps today's shape (line row, part
  rows, `1a` / `1b` tag rows). The line-level "Changed" roll-up is redundant on a folded row, so
  it is not shown there (the tag's own Changed pill is on the same row).
- D8 Designer rail (`RequestTagDesigner.tsx`, `LinesRail`): a line with exactly ONE tag, NO
  parts and NO open group renders as ONE block: the line block becomes the selectable button
  (`onSelect(tag.id)`, `selected` highlight, `Check` when designed, the open-pins count, the
  Changed / Review affordance, the Use template button) and the Qty line carries the tag's
  price text (`Qty 1 / Shower / LP RM 300`, same `formatTagPrice` rules, override included).
  No `1a` text, no `TagRailRow` under it. The Remove button is not shown (it is already hidden
  when a line has one tag). A line with two or more tags, any parts, or an open group keeps
  today's shape. `aria-label`s keep the tag label.
- D9 `TagSizeControl` (shared by the designer rail and the template page) becomes a
  `Collapsible` (`components/ui/collapsible.tsx`): the "Tag Size" heading is the trigger, with
  a chevron and, when collapsed, the current size inline (`95 x 44.5 mm`, the same
  `sizeKey`/label the select shows) so the value stays readable without opening it. Collapsed
  by default. The open/closed state is remembered per browser in `localStorage` under one key
  (`dealer-kit.tag-size.open`), read and written inside try/catch, so a viewer who opens it
  keeps it open on the next request. No server preference, no prop: one component, one key.
  The "Select a line to set its tag size" placeholder in the rail keeps its heading as is.
- D10 `price_tag_update` joins `TEMPLATE_DEFAULT_USE_CASES` (after `ticket_resolved`, with a
  comment in the same voice as its neighbours) and the FE `USE_CASES` list as
  "Price Tag Request - Update" in the update group, described as: "Sent to the salesperson
  when their price tag request moves (received, design ready, changes requested, approved,
  PDF ready, ready for collection, collected, rejected) and their 24h window is closed. Map
  params to Full update message at minimum; add Entity number and Portal URL when the template
  carries them." `build_context_vars` gains an `elif entity_use_case == "price_tag_update"`
  branch that loads `PriceTagRequest` by `business_id` and sets `entity_number`
  (`doc_number`), `status`, and `portal_url` (the same `_portal_link`). `message` is already
  defaulted to the text by `send_text_or_template`.
- D11 `price_tag_notify._send` resolves the identifier once at the top:
  `resolve_respond_io_id(db, request.contact_id) or request.contact_id`
  (`app/services/respond_identifier.py`), and uses that value for the window check, the send,
  the webhook, and BOTH log rows' `external_reference` and endpoint. The outbox list and modal
  then show the contact's name and phone, the way stock inquiry / purchase request rows do.
- D12 `TagRailRow` (and the folded line block of D8): the open-pins count moves OUT of the row
  button into the absolute action group, first in the group (`[pins][changed dot][Use
  template][Remove]`), and the row button's right padding clears the whole group (`pr-20`).
  Nothing overlaps at any count.
- D13 The canvas pin popover in `TagCanvasEditor` gains a Done / Reopen button (same copy and
  icons as `RequestDesignSection`: `Check` "Done", `Undo2` "Reopen") through one optional
  prop `onReviewPinResolve?: (pinId: string, resolved: boolean) => void | Promise<void>`. The
  button renders only when the prop is given. `RequestTagDesigner` passes it: call
  `setReviewCommentResolved(request.id, pinId, resolved)`, then `listReviewComments` and
  `setReviewComments`, so the marker greys, the rail count drops and the CTA's `(N open)`
  updates; a failure toasts "Could not update the change request" (same text as the detail
  page). No new endpoint: PATCH review-comments already does it.
- D6 No new endpoint, no registry, no flag. One resolver call, one boolean in the FE, one guard
  in the service.

## Files

BE
- `app/services/ai_extract/extract_service.py`: D1, D2.
- `app/api/v1/public/ai_extract.py`: scope the extract in `company_scope` for the token's
  company if `extract()` is not already scoped there (check first; sibling
  `portal_lookup_product_combos` shows the pattern).
- `app/services/price_tag_request_service.py`: D5.
- `app/models/respond_template.py`, `app/services/respond_messaging_service.py`
  (`build_context_vars`), `app/services/price_tag_notify.py`: D10, D11.
- `sorento_crm_frontend/services/whatsappTemplateService.ts` `USE_CASES`: D10.
- tests: `tests/test_ai_extract_resolver_match.py`, `tests/test_price_tag_parts_need_combo.py`,
  `tests/test_price_tag_notifications.py` (extend: identifier + context vars + use case listed).

FE
- `app/(auth)/portal/lib/portal-client.ts`: `AIExtractedProductLine` gains the three fields.
- `app/(auth)/portal/components/PriceTagRequestForm.tsx`: D3, D4.
- `app/(protected)/dealer-kit/price-tag-requests/components/PriceTagRequestDetail.tsx`: D7.
- `app/(protected)/dealer-kit/price-tag-requests/[id]/design/components/RequestTagDesigner.tsx`: D8.
- `app/(protected)/dealer-kit/components/TagSizeControl.tsx`: D9.
- `app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor.tsx`: D13 (popover).
- `RequestTagDesigner.tsx`: D12 (rail), D13 (wiring).
- tests: `RequestTagDesigner.review.test.tsx` (Done from the popover), `RequestTagDesigner.tags.test.tsx`
  (pins count outside the row button), `TagSizeControl.test.tsx` (collapsed by default with the size inline; click opens;
  state read from localStorage), `RequestTagDesigner.tags.test.tsx` (one tag + no parts = one selectable block, no "1a";
  two tags = tag rows), `PriceTagRequestDetail.test.tsx` (one tag + no parts = one row; two tags = sub-rows),
  `PriceTagRequestForm.aiExtractApply.test.tsx` (update the mocks: no `lookupTagItems`
  call, statuses from payload), `PriceTagRequestForm.parts.test.tsx` (Add part hidden when
  combos empty, shown when one or more).

## Out of scope

Other AI extract consumers (`SubmissionForm` product codes for stock inquiry / purchase
request) keep receiving `product_code`; they gain the canonical code for free through D2 and
are not otherwise touched.
