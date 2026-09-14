# UAC - Price Tag Round 9: data gate, review pins, notifications, collection

Plan: `documentation/plans/dealer-kit/PLAN-price-tag-r9-review-loop.md`

Each AC is verified in a real browser (agent-browser on the lane dev server) unless marked
`pytest` / `vitest`. Portal = logged in as the linked portal contact; CRM = marketing user
with `dealer_kit.price_tag_requests.process`.

## Journey

Salesperson (portal contact) submits a price tag request and now picks who prints. Marketing
is assigned and designs; the moment a design exists the product data on it is pinned. When
marketing marks the design ready, the salesperson gets a WhatsApp with a link, opens the
request, sees the design first, and either approves or clicks straight on the tag to leave
pinned comments, then sends them. Marketing sees the pins on the detail page and in the
designer, fixes, ticks them Done, marks ready again. On approve: self print ends there and
the salesperson downloads the PDF; office print continues with the office pressing Mark
ready for collection, the salesperson getting a WhatsApp, and the request closing on Mark
collected or automatically after the configured days. Whenever master data changes under an
open request, marketing sees a label, reviews old vs new, and chooses Update (a version is
kept) or Keep. Every status change reaches the salesperson without anyone remembering to
tell them.

## S1 Preview payload + viewer

- AC-S1-1 Portal read view of a `proof_ready` request renders the design with its background
  artwork, product photo, badges and brand fonts (no grey placeholder boxes). `pytest`: the
  portal design payload carries `assets`, `images`, `fonts` keys equal to the print payload for
  the same request.
- AC-S1-2 The Design section is the first section after the status row on the portal read
  view from `proof_ready` onward, and the first block of the CRM detail Request tab from
  `designing` onward (draft). Before those statuses the section is absent (portal) or shows
  the empty state "No design yet" (CRM). `vitest`: section-order test updated.
- AC-S1-3 Inline card is fit-to-width, pages sheets when more than one, and has one `Open`
  button. No zoom dropdown in the card.
- AC-S1-4 Lightbox header shows doc number, `n / N`, `- % +`, Download PDF, close; same visual
  chrome as the attachment viewer (Resources). `vitest`: `AttachmentPreviewModal` still renders
  its header through the shared chrome.
- AC-S1-5 Ctrl/Cmd + wheel zooms around the cursor (0.25-5); plain wheel scrolls; dragging
  pans when the sheet exceeds the viewport; `+ - 0` keys work; the % menu offers Fit and
  presets. Pinch zoom on a touch device zooms.
- AC-S1-6 Download PDF is disabled with "PDF is being generated" while no completed export
  exists and downloads the newest export otherwise.
- AC-S1-7 Usable at 375px: card and lightbox fit the viewport; pins and header wrap, no
  horizontal page scroll.

## S2 Pinned change requests

- AC-S2-1 On a `proof_ready` request, a click on a tag (card or lightbox) drops a numbered pin
  and opens a comment popover; a drag draws a box with the pin at its corner. Escape or an
  empty comment discards it.
- AC-S2-2 There is no "Request changes" mode or button; the first placed pin turns on the
  footer rail and the `Send 1 change request` button. Rail lists pins with line code, text and
  Delete; an optional general note textarea sits under them.
- AC-S2-3 Send posts all pins in one call; status becomes `changes_requested`; the portal
  returns to the list with a toast. `pytest`: rows carry request_id, line_id, round, fractions
  in 0..1, author_contact_id; the request `notes` column is NOT modified.
- AC-S2-4 Pins are anchored to the tag: after zooming, paging sheets and re-arranging tags in
  Arrange, each pin sits on the same spot of its tag.
- AC-S2-5 CRM detail Design section shows the pins overlaid and a list with a Done toggle; Done
  greys the pin and records resolved_by/at. `pytest`: only a user with the process permission
  may toggle; the portal contact gets 403.
- AC-S2-6 Designer canvas shows numbered markers over the matching tag; `Comments` in the
  trailing toolbar hides/shows them; clicking a marker opens the comment and selects no
  layer. LINES rail shows an orange count on lines with open pins.
- AC-S2-7 With open pins, the primary CTA reads `Mark design ready (N open)` and still works
  (D2). The next round on the portal shows earlier pins grey and allows new pins; `round`
  increments. `pytest`: round equals the request's `review_round` counter, incremented on
  every entry into proof_ready (browser finding 14 Sep: the snapshot-count derivation skipped
  rounds when no draft existed).
- AC-S2-8 A request-changes call with only the legacy `note` field (no pins) still succeeds
  and creates one general comment row.

## S3 Print choice + collection

- AC-S3-1 Portal form Additional Information starts with the required segmented control
  `Printing`: `Office prints` / `I print myself`, no default. Submit with neither selected
  names the gap inline and the server returns 422 `PRINT_BY_REQUIRED` (`pytest`).
- AC-S3-2 Portal read view and CRM Request tab show Printing; the office can change it from
  the gear `Edit request` while the request is not terminal. Existing rows show "Printing:
  not set" in CRM.
- AC-S3-3 Status `ready` no longer exists: label map, list filter, portal and CRM pills
  never show "Ready". `pytest`: migration maps every `ready` row to `approved`;
  `request_tag_sheet_export` leaves the status unchanged and accepts approved /
  ready_for_collection / collected.
- AC-S3-4 Self print: after the salesperson approves, the request stays `approved`, is
  terminal (Export PDF is the only action left and renders as the primary button, no gear,
  no Void), and the PDF appears under Download PDF once exported.
- AC-S3-5 Office print: at `approved` the CRM primary CTA is `Mark ready for collection`;
  pressing it sets `ready_for_collection` and `ready_for_collection_at`. The CTA is hidden when
  Printing is not set.
- AC-S3-6 At `ready_for_collection` the portal primary CTA is `Mark collected`; the CRM
  card offers `Mark collected` as its primary button. Either sets `collected`,
  `collected_at`, and the acting user or contact. `collected` is terminal.
- AC-S3-7 System Settings > General shows "Auto-mark price tags collected after" days,
  default 7, accepts 0..90, saves and reloads (`vitest` mapping, `pytest` bounds).
- AC-S3-8 `pytest`: the `price_tag_auto_collect` handler flips only `ready_for_collection`
  rows older than the configured days, sets `collected_auto = true`, does nothing when
  days = 0, and is seeded in `scheduled_tasks` by the migration. CRM card subline reads
  "since <date> · auto-collects <date>" when days > 0.

## S4 Notifications

- AC-S4-1 `pytest`: every status transition (new -> designing, designing -> proof_ready,
  proof_ready -> changes_requested / approved, approved -> ready_for_collection,
  ready_for_collection -> collected incl. auto, any -> rejected / void) calls the salesperson
  notifier exactly once with the event name and a portal link; a notifier exception is logged
  and the transition still commits.
- AC-S4-2 `pytest`: completion of a self-print export sends "PDF is ready to download" with
  the portal link; an office-print export sends nothing.
- AC-S4-3 On the lane stack (Respond disabled) each transition writes an outbox /
  IntegrationLog row with `business_table = price_tag_requests` and the rendered text matching
  the copy table in the plan.
- AC-S4-4 `pytest`: `changes_requested` and `approved` create one in-app notification for the
  assignee with the CRM detail link; a repeated call for the same request + status + round
  does not duplicate.
- AC-S4-5 Form-SLA notifications for a price tag request show `PT-YYYYMM-NNNN` and link to
  `/dealer-kit/price-tag-requests/{id}` (`pytest`).
- AC-S4-6 A CRM rejection with a note stores the note as a general review comment by the user
  and the salesperson text contains it (`pytest`).

## S5 Product data pin + versions

- AC-S5-1 `pytest`: the transition to `designing` pins `LineTagData` on every line
  (`pinned_tag_data`, `pinned_at`); a line added while designing is pinned on save; the
  migration backfills pins for all lines of non-terminal requests.
- AC-S5-2 Editing the product's list price, barcode, spec value, or dealer image after the pin
  changes nothing on the CRM designer canvas, the portal preview or the PDF payload
  (`pytest` on the payload; browser on the canvas). Focusing the window no longer refreshes
  the data.
- AC-S5-3 After such an edit, the CRM detail card shows `Product data changed · N`, the Lines
  tab row shows `Changed` + `Review`, and the designer LINES rail shows a red dot on that line.
  Terminal requests never show the label (`pytest`: no live resolve for terminal).
- AC-S5-4 Review dialog lists each changed field with old and new values (image thumbnails for
  images, "promotion ended" when the offer disappears) and offers `Keep current` and
  `Update tag`; `Update all` appears on the card when N > 1.
- AC-S5-5 `Update tag` creates a version titled "Before product update: <fields>" carrying
  `pinned_line_data`, replaces the pin, and the canvas, preview and PDF payload now show the
  new values (`pytest` + browser). `Keep current` clears the label until the product changes
  again (`pytest`: ack hash).
- AC-S5-6 `History` (CRM Design section and designer toolbar) opens the request Versions
  sheet: newest first, View opens the read-only version, Restore writes the version's doc and
  pins back, creates "Restored v<n>", and the canvas reflects it (`pytest` on the routes).
- AC-S5-7 Marketing price override still wins over the pinned offer price (`pytest`).
