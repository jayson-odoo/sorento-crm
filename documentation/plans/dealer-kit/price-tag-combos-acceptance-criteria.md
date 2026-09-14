# UAC - Price tag combos: catalogue packages on the request, one line, many tags

Plan: `documentation/plans/dealer-kit/PLAN-price-tag-combos.md`

Each AC is verified in a real browser (agent-browser on the lane dev server) unless marked
`pytest` / `vitest`. Portal = logged in as the linked portal contact; CRM = marketing user
with `dealer_kit.price_tag_requests.process`; Master data = user with
`master_data.products.edit`.

## Journey

Marketing opens a cabinet's product page, reads the catalogue page beside it, and records
the package once: a combo named the way the catalogue names it ("3 in 1"), the parts that
always come with it, and the group of basins the customer picks one of. A cabinet printed
on two catalogue pages gets two combos. A salesperson on the portal asks for a price tag by
picking the cabinet they know; the package's parts appear under it without being asked for,
a basin they are unsure of stays open, and a cabinet with no package or with parts removed
submits anyway with a warning marketing will see. Marketing opens the request, sees one line
per product the salesperson asked for with its parts, and one tag under each line; on the
open basin they split the tag into one per candidate, or pick one. Every tag prints the
cabinet with its parts and one price. Nothing about this reaches the chatbot's stock
answers, which still answer for the cabinet alone.

## S1 Combos on the product

- AC-S1-1 Product detail page shows a "Combos" section (placement per plan) listing each
  combo by name with its parts; a product with none shows the empty state "No combos" and
  an "Add combo" button. `[FE]`
- AC-S1-2 Add combo asks for a name only; a combo is created empty and its parts table opens
  for editing. Names are unique per host product; a duplicate is refused inline. `[FE]` `[BE]`
  `pytest`: `POST /products/{id}/combos` twice with the same name returns 409.
- AC-S1-3 Add part opens the shared product search (server-searched, no capped dropdown);
  the host product itself and a product already in this combo are refused with an inline
  message. `[FE]` `[BE]` `pytest`: 422 on host-as-part and on duplicate part.
- AC-S1-4 Each part row has a clearable "Choice group" control (free text with the group
  names already used in this combo offered as options). Empty means fixed. Two or more parts
  sharing a label are rendered together under that label with "pick one" wording. `[FE]`
- AC-S1-5 Removing a part is a deferred action (countdown, Cancel), no confirm dialog.
  Removing a combo likewise removes its parts. `[FE]` `[BE]` `pytest`: delete combo cascades
  parts; a part referenced by a submitted request line is still deletable (the line keeps its
  own product references).
- AC-S1-6 A part's own product page shows a read-only "Sold with" list naming each host and
  combo ("SRTBF11834 · 3 in 1"), linking to the host. `[FE]` `[BE]` `pytest`: `GET
  /products/{part_id}/sold-with` lists hosts across combos.
- AC-S1-7 Combos are company scoped through the host product; a user scoped to another
  company gets 404 on the host's combos. `pytest`
- AC-S1-8 `product_sets`, the chatbot business gate and miss-suggest are untouched: a stock
  question for the host code resolves the host product only. `pytest`: resolver returns the
  cabinet with no combo parts attached.
- AC-S1-9 Usable at 375px and 1280px: parts table scrolls inside its own container, no page
  overflow. `[UX]`

## S2 Portal request: parts under the line, warn and allow

- AC-S2-1 Picking a product with exactly one combo fills its parts as child rows under the
  line immediately (fixed parts as product rows, each choice group as one open row showing
  the group label and candidate count). `[FE]`
- AC-S2-2 Picking a product with two or more combos shows a clearable "Package" select on the
  line listing the combo names; parts fill in when one is chosen and are replaced when the
  choice changes. With none chosen the line has no parts. `[FE]`
- AC-S2-3 An open row offers a clearable select of that group's candidates; choosing one turns
  the row into a product row; clearing reopens it. Copy on an open row: "Marketing will
  prepare one tag per option". `[FE]`
- AC-S2-4 Any part row can be removed (staged removal, no countdown, no confirm, per the
  staged-removals rule) and a part can be added by hand through the shared product search,
  on any line, combo or not. `[FE]`
- AC-S2-5 Submit is never refused for package reasons. A line whose product is in a guarded
  class and has no combo, or has fewer parts than its chosen combo, shows a row warning
  before submit and submits with `package_warning` set to "No package defined" or "Missing:
  <part codes>". `[FE]` `[BE]` `pytest`: both texts; a clean line stores NULL.
- AC-S2-6 Guarded classes are read from System Settings `price_tag_guarded_classes`
  (default Bathroom Furniture, Kitchen Sink), shown and editable on the settings page as a
  multi-select over the distinct `class_label` values. `[FE]` `[BE]` `pytest`: settings
  round-trip; the manual settings dict includes the key.
- AC-S2-7 The old hard refusal `SET_GUARD_VIOLATION` no longer fires for product lines. WC
  product-set lines keep their existing path unchanged. `pytest`: the two former 422 cases
  now return 201 with `package_warning`.
- AC-S2-8 Submit payload per line: `{line_type, product_id, combo_id?, quantity, remarks,
  parts: [{product_id?, role?, candidates?}]}` (`show_promo_price` stays derived from the
  header `price_mode`, r7 D5; `alternatives` is gone); the API stores
  parts in order; the portal read view shows the parts under each line and the warning pill.
  `pytest`: parts persisted in order with roles and candidates. `[BE]`
- AC-S2-9 Draft save and reload keeps parts, package choice and open rows. `[E2E]`
- AC-S2-10 Same product twice on one request is still refused (`DUPLICATE_LINE`). `pytest`
- AC-S2-11 375px: line and part rows stack readably, package select and open-row select are
  full width, no horizontal page scroll. `[UX]`

## S3 One line, many tags

- AC-S3-1 Submitting a request creates exactly one tag per line (`price_tag_request_tags`)
  carrying the line's quantity; `show_promo_price`, `quantity` and `remarks` stay on the line
  as the salesperson's ask. The migration creates one tag for every existing line, moves
  marketing override and reason onto it, and rewrites every saved tag sheet doc's
  `request_line_id` to the new `request_tag_id`. `pytest`: migration test over a seeded
  request with a saved doc; create request -> one tag per line. `[BE]`
- AC-S3-2 CRM detail Lines tab shows each line with its parts under it and its tags under
  that (one by default), with the tag's resolved choices and price; the warning pill from
  AC-S2-5 shows on the line. `[FE]`
- AC-S3-3 In the designer the rail lists lines with their tags nested; selecting a tag edits
  that tag; the doc keys tag geometry and bindings by `tag_id`. `vitest`: designer maps doc
  tags by tag id; `?tag=` deep param replaces `?line=`. `[FE]`
- AC-S3-4 A tag whose line has an open part shows "Open: <group>" with two actions: "Split
  into N tags" resolves the existing tag to the first candidate (it keeps its geometry and
  pins) and creates N-1 sibling tags after it, each resolved to one of the remaining
  candidates with the geometry copied; "Pick one" resolves the group on the existing tag.
  `pytest`: split yields N tags with `choices` set, the original id survives, sort order
  1..N. `[FE]` `[BE]`
- AC-S3-5 Marketing price override and reason are edited per tag (route
  `PATCH /price-tag-requests/{id}/tags/{tag_id}`); the line-level override route is gone.
  `pytest`: old route 404/410, new route round-trips. `[BE]`
- AC-S3-6 A tag can be removed (deferred action) as long as its line keeps at least one tag.
  `pytest`: removing the last tag returns 422. `[BE]`
- AC-S3-7 Review pins (r9) anchor to a tag; if r9 has merged, the migration remaps existing
  pins to the line's first tag. `pytest` (only when r9 is on main at merge time).
- AC-S3-8 Export and the print sheet lay out one tile per tag times its quantity; the sheet
  for a split line prints N tiles. `pytest`: payload row count = sum of tag quantities. `[BE]`

## S4 What prints

- AC-S4-1 A product tag lists its parts in the `set_members` slot text as `+ <code> <name>
  <dimensions>` lines in part order; an unresolved open group prints `<group>: <code> / <code>
  / ...`. `pytest`: text for a resolved and an open tag. `[BE]`
- AC-S4-2 List price on the tag = host list price + sum of resolved parts' list prices;
  selling price = the promotion engine's offer over the same products; the marketing override
  on the tag wins when set. `pytest`: three cases. `[BE]`
- AC-S4-3 Portal read view and preview render the parts text and price; existing templates
  need no change (the slot already exists). `[E2E]`
- AC-S4-4 The PDF for a split line prints one tag per candidate with the candidate's code in
  the parts text. `[E2E]` (recorded agent-browser evidence, no new Playwright spec)

## Cross-cutting

- AC-X-1 Every new select is `SearchableSelect`/`SearchableMultiSelect`, clearable when
  optional; product pickers use the shared product search. `[UX]`
- AC-X-2 No UUID visible anywhere; combos, parts and tags are shown by product code, combo
  name and tag ordinal (1a, 1b). `[UX]`
- AC-X-3 No explanatory copy in the UI beyond the one open-row line in AC-S2-3; the user
  guide carries the rest. `[UX]`
- AC-X-4 New motion: none. Row add/remove uses the existing list transition preset only.
  `[UX]`
- AC-X-5 New permission: none. Combos use `master_data.products.edit` / `.view`; request
  tags use the existing price tag permissions. `[BE]`
