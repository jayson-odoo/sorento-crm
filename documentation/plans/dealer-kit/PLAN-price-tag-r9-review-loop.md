# PLAN - Price Tag Round 9: data gate, review pins, notifications, collection

Status: Implemented 14 Sep 2026, browser-verified, PR open (awaiting owner test on :3082 and merge go). Reconciled onto the combos model 15 Sep 2026: `origin/main` merged PR #913 (PLAN-price-tag-combos.md) FIRST, so a line now prints many tags and this lane adapts to it. Everything r9 does per LINE is done per TAG - the pin and its ack, the review comment anchor, the diff, the rail badges, the versions' `pinned_line_data` map. `ptag_0007` / `ptag_0008` are re-parented onto `ptag_0009_combos_tags` and CREATE the tag-keyed shapes directly, so `ptag_0009`'s `_remap_r9_pins` stays the documented no-op it was written to be. Single head `ptag_0008_pins_versions`; D4, D6, D16-D19 below carry the change.
UAC: `documentation/plans/dealer-kit/price-tag-r9-review-loop-acceptance-criteria.md`
Predecessor: `documentation/plans/dealer-kit/PLAN-price-tag-r7-request-ux.md` (merged #758), portal r8 (#861)
Grill artifact: `.lavish/ptag-r9/price-tag-r9-plan.html`
Lane: one lane, one PR (F1). Branch `feat/price-tag-r9-review-loop`, worktree `.claude/worktrees/price-tag-r9`.

Owner walked PT-202609-0001 on live 14 Sep 2026 and asked for five things: product data must
not flow into a finished design without a person deciding; every status change reaches the
salesperson; the portal preview must render properly, sit first, and zoom like the attachment
viewer; change requests are pinned on the design, not typed in a box; office print needs a
collection hand-over with an auto-collect timer.

All line refs are `origin/main` at ae0831776.

## What exists (measured, two Opus explorers 14 Sep)

- Tag data resolves LIVE on every render, ADR 0008. Single resolver
  `resolve_request_line_data` (`app/services/dealer_kit/tag_data_service.py:450-516`) feeds the
  CRM designer (`price_tag_requests.py:447-475`), the portal preview (`portal_price_tag.py:210-219`)
  and the PDF payload (`tag_sheet_export_service.py:300-380`). Live fields: code, name,
  dimensions, spec_lines, specs, dealer images, list_price, offer_price, promotion_id, barcode;
  set lines the same via `product_set_tag_data`. Stored on the line: marketing override,
  quantity, remarks, show_promo_price. Frozen in the doc: `slot_binding`, `text_override` only.
  No change detection anywhere. r4 S2 added a silent refresh-on-focus
  (`RequestTagDesigner.tsx:277-301`).
- Versions: `page_versions(page_id, version, doc, commit_message, created_by, created_at)`
  written by `_snapshot_draft` on manual Save and on proof_ready
  (`price_tag_requests.py:328-357, 205-210`). No list, view or restore for requests. Templates
  have all three (`TemplateVersionsSheet.tsx:36-140`, restore route `tag_templates.py:338`).
- Status graph `price_tag_request_service.py:29-71`: new, designing, proof_ready,
  changes_requested, approved, ready, rejected, void. `ready` terminal; export flips
  approved -> ready (`tag_sheet_export_service.py:196`); `approved` auto-queues the export
  (`:500-512`). `TransitionPayload.note` exists (`schemas/price_tag.py:264`) and the route
  drops it (`price_tag_requests.py:187-212`).
- Change request: `portal_price_tag.py:482-488` appends `"\n[Changes requested]: ..."` to
  `notes`. Portal UI `PriceTagRequestForm.tsx:1409-1462` (AlertDialog + Textarea).
- Salesperson notifications: none. Purchase request path to copy:
  `_send_purchase_request_contact_message` (`procurement_service.py:7094-7180`) ->
  `respond_messaging_service.send_text_or_template` (`:545`), `build_context_vars` (`:690`),
  `PortalService.submission_link` (`portal_service.py:459`), IntegrationLog row, outbound webhook.
  Marketing: only form-SLA "submit"; `price_tag_request` missing from `_ENTITY_NUMBER_SOURCE`
  (`form_sla_service.py:118-124`) so the notification shows a uuid prefix. Dev DB (prod copy)
  has no `form_sla_configs` row for `price_tag_request` (3 requests sit in `new`).
- Portal preview: `ProofPreviewSection` (`PriceTagRequestForm.tsx:2149-2218`) ->
  `PriceTagProofViewer` (`:48`) -> `TagSheetRenderer`. Viewer passes only `doc`,
  `resolvedData`, `preview`, `previewScale` (`PriceTagProofViewer.tsx:183-188`); `assets`,
  `images`, `fonts` never reach the renderer, so image layers paint `#f5f5f5`
  (`TagSheetRenderer.tsx:305`) and photo slots `#f0f0f0` + code (`:680-700`). Print page passes
  all three from `_resolved_payload` (`print/tag-sheet/[downloadId]/page.tsx:190-195`,
  `tag_sheet_export_service.py:329-382`). Not CORS (`useHtmlImage.ts:18-30`). Zoom = dropdown
  `[0.25..2]` + Fit, no wheel/pinch/pan (`:35-138`). Section order: Customer, Sales Order &
  Lines, Price, Additional Information, Design Preview, PO cross-check, Design Review,
  Revisions (`:1213-1600`, asserted in `PriceTagRequestForm.sectionOrder.test.tsx:100-110`).
- Attachment lightbox `components/common/AttachmentPreviewModal.tsx`: title, `n / N`,
  ZoomOut / % input / ZoomIn (image only), Open, Download, Delete; zoom 0.25-5, keys
  ArrowLeft/Right + - =, Ctrl/Cmd+wheel zoom, plain wheel scrolls, no drag-pan; content by
  filename kind, no node slot (`:112-125, 143-196, 378-385`).
- CRM detail `PriceTagRequestDetail.tsx`: PageHeader + record card (pager, gear, one primary
  CTA from `priceTagRequestActions.ts`), tabs Request / Lines / Sales Order. No design view
  since r7 D10.
- Annotations: no pin or coordinate comment model anywhere (BE or FE). Nearest geometry code:
  `RoomPlan.tsx:207-235` (SVG screen->user), `TagCanvasEditor.tsx:2527-2542` (wheel zoom),
  `TagSheetRenderer.tsx:929-1010` (absolute mm divs in a scaled wrapper).
- Print / collection: no field, status, setting or job. Scheduler = 10 s heartbeat over
  `scheduled_tasks` rows with handlers registered in `task_scheduler.py:526-554`; precedent
  for "flip after N configured days" = `project_staleness_sweep`
  (`project_staleness_service.py:198-301`). System settings = one wide row
  (`models/user.py:274+`, `deferred_action_seconds` at 377; API `settings.py:81, 275`; FE
  `settings/layout.tsx:81`, `settings/page.tsx:344`).
- Audit: `products` audited with field diffs (`product.py:159-162`); `product_specifications`,
  `product_flyer_text`, `product_attachments` NOT audited. Not needed: the diff is computed
  from live vs pin, not from audit rows.

## Rulings (owner, 14 Sep, lavish round 1 -> 2)

- A1 Pin starts at `designing`. r4 refresh-on-focus retired. Terminal requests never diff.
- A2 Change label computed on open only. No listener, no queue, no bell for data changes.
- B1 EVERY status change goes to the salesperson by WhatsApp, including confirmations of
  their own actions, plus "PDF ready" when the self-print export completes.
- C1 Lightbox: Ctrl/Cmd + wheel zooms at cursor, plain wheel scrolls, drag pans past fit.
- D  No "Request changes" mode: click or drag on the tag creates the pin and opens the
  comment; Send appears once a comment exists.
- D1 Pins render inside the Konva designer canvas.
- D2 Mark design ready stays allowed with open pins; the button shows the open count.
- E1 Printing has no default; submit blocked until chosen. Auto-collect default 7 days, 0 off.
- E2 Status `ready` retired. Self print ends at `approved`. Office print: approved ->
  ready_for_collection -> collected.
- F1 One lane, one PR.

## Decisions

### S1 Preview payload + shared viewer

- D1 Portal design endpoint `GET /public/portal/submissions/price_tag_request/{id}/design`
  returns the print payload: reuse `resolve_tag_sheet_print_payload` (doc, resolved lines,
  `assets`, `images`, `fonts`) with `prefer="version"`. `PortalTagSheetDesignResponse` gains
  `assets: dict[str, str]`, `fonts: list[...]` matching the print payload schema. Owner and
  status gates unchanged (`ready` leaves the set, `ready_for_collection` + `collected` join).
  The CRM `GET /dealer-kit/price-tag-requests/{id}/design` returns the SAME shape
  (`prefer="draft"`, with `lines` + `assets` + `images` + `fonts`) so the CRM Design section
  makes one call and never falls back to the `dealer_kit.library.manage`-gated asset library
  (Phase 1 finding, 14 Sep). Shared FE contract: `lib/dealer-kit/design-payload.ts`.
- D2 New `components/dealer-kit/DesignViewer.tsx` (shared by portal and CRM): inline card =
  fit-to-width `TagSheetRenderer` with media maps + `ensureFontsLoaded`, sheet pager when
  `sheetCount > 1`, one button Open. Lightbox `DesignLightbox.tsx` = same header chrome as
  `AttachmentPreviewModal` (extract `PreviewModalChrome` for title, counter, zoom cluster,
  actions, close; the attachment modal adopts it, its `<img>` slide untouched). Zoom 0.25-5 with
  Fit; Ctrl/Cmd+wheel zooms at cursor; plain wheel scrolls; pointer drag pans when the sheet
  is larger than the viewport; keys `+ - 0`; presets in the % menu. Download PDF = the existing
  portal download route (disabled with "PDF is being generated" while no completed export).
  `PriceTagProofViewer.tsx` is deleted.
- D3 Order. Portal read view: Design section first after the status row whenever the design
  is visible (`proof_ready` onward), then Customer, Sales Order & Lines, Price, Additional
  Information, PO cross-check, Design Review (until S2 D5 folds Approve into the Design
  header), Revisions. CRM detail: new Design section at the top of the
  Request tab, same viewer, visible from `designing` (draft, `prefer="draft"`). Section-order
  test updated.

### S2 Pinned change requests

- D4 Table `price_tag_review_comments`: id, request_id FK, **`tag_id` FK
  `price_tag_request_tags` CASCADE, nullable (null = general)** (combos reconciliation,
  15 Sep: a line prints one tag per open option and two of them show different products,
  so a pin is about the one that was clicked), round int, x/y/w/h numeric(6,4) nullable (fractions of the tag box), body text,
  author_contact_id nullable, author_user_id nullable, created_at, resolved_at, resolved_by_id
  nullable, company_id (CompanyScopedMixin). `round` = `price_tag_requests.review_round`, a
  counter incremented on every entry into `proof_ready` and stored on the comment at send time
  (R1, 14 Sep). It was derived from the `Marked proof ready` snapshots, and that snapshot is
  only written when a draft exists - the designer's own CTA saves first - so the send skipped
  it and every round came back as 1. A row whose counter is still 0 is read the old way.
- D5 Portal: in the inline card AND the lightbox, a click on a tag places a point pin
  (w=h=0), a drag places a box; either opens a popover Textarea; Escape or empty = discard.
  Pins are local state until Send. A footer rail lists them with Delete; an optional general
  Textarea; `Send N change requests` appears when N >= 1. Send = one
  `POST .../request-changes` with `{comments: [...], note?}` -> creates rows, transitions to
  `changes_requested`, notifies (S4). The Notes append is removed; the old text `note` field
  stays accepted for one release as a general comment. Portal Approve stays a button in the
  Design section header (no separate Design Review card).
- D6 Pins after Send: read-only for the salesperson; new rounds show earlier rounds grey
  (resolved or not). Marketing: CRM detail Design section shows the same overlay plus a
  list with a Done toggle per pin (`PATCH .../review-comments/{id}` resolved). Designer:
  markers as a DOM overlay in the editor's existing pan/zoom coordinate space (the same
  space as the inline text editor and the whole-tag eye; a Konva node would sit inside stage
  hit-testing, which D6 then has to fight) using the same fractions, drawn on every copy of
  THAT TAG on the sheet, toggled by a `Comments` trailing toolbar button (default on while open pins
  exist); clicking a marker opens the comment popover, never selects a layer. LINES rail:
  orange count badge on the TAG rows with open pins.
  (Combos reconciliation, 15 Sep: the never-deployed `placed_tag_id` column is dropped.
  It existed so a pin would not spread across copies that differ; the thing that differs
  is a different TAG now, and every copy of one tag draws the same artwork, so the anchor
  answers it without a copy id.) `Mark design ready` label becomes
  `Mark design ready (2 open)` while pins are open; not blocked (D2).

### S3 Print choice + collection

- D7 `price_tag_requests.print_by VARCHAR(8) NULL`, values `office | self`. Portal form
  Additional Information: segmented control "Printing" - `Office prints` / `I print myself`,
  first field, required at submit (`validate_submittable` 422 `PRINT_BY_REQUIRED`), no
  default. CRM Request tab shows it and the office can change it via the gear "Edit request"
  while not terminal. Existing rows stay NULL; the CRM card shows "Printing: not set" and the
  Mark ready for collection CTA is hidden until set.
- D8 Status graph: remove `ready`; `approved -> {ready_for_collection, rejected, void}`
  allowed only when `print_by == 'office'`; `ready_for_collection -> {collected}`;
  terminal = `collected, rejected, void` plus `approved` when `print_by == 'self'`
  (`is_terminal(request)` becomes request-aware). `request_tag_sheet_export` no longer
  transitions; it accepts `approved | ready_for_collection | collected`. Migration
  `ptag_0007_print_collection`: add columns, `UPDATE ... SET status='approved' WHERE
  status='ready'`. FE label map drops `ready`, adds `ready_for_collection: Ready for
  collection`, `collected: Collected`; `priceTagRequestActions.ts` primary CTA at `approved`
  + office = `Mark ready for collection`, at `ready_for_collection` = `Mark collected`;
  portal primary at `ready_for_collection` = `Mark collected` (`POST .../collect`).
- D9 Columns: `ready_for_collection_at`, `collected_at`, `collected_by_user_id`,
  `collected_by_contact_id`, `collected_auto bool default false`. Card subline at
  ready_for_collection: "since <date> · auto-collects <date>" when the setting is > 0.
- D10 System Settings > General: "Auto-mark price tags collected after" integer days, 0 = off,
  default 7. Column `system_settings.price_tag_auto_collect_days INT NOT NULL DEFAULT 7`,
  bounds 0..90, added to `GET /settings/`, `PUT /settings/general`, `SystemSettingUpdate`,
  AND the narrow `GET /settings/app-config` projection (the CRM detail card reads it and
  marketing does not hold `user_management.settings.view`), FE `layout.tsx` mapping +
  `page.tsx` field (both manual dict builders, per LESSONS). Collection steps use the
  existing CRM transition route; the portal gets `POST .../collect`; the office fixes
  `print_by` through `PATCH /dealer-kit/price-tag-requests/{id}`.
- D11 Scheduled task `price_tag_auto_collect` (handler in `task_scheduler.py`, service in
  `price_tag_request_service.py`): every hour, for each request `ready_for_collection` with
  `ready_for_collection_at < now - days` and days > 0, transition to `collected` with
  `collected_auto = true`, actor None, then S4 notification. Seed row in the migration
  (enabled, interval 1 hour), same shape as `promotion_active_window`.

### S4 Notifications

- D12 `price_tag_notify.py` (new service): `notify_salesperson(db, request, event, **ctx)`
  mirrors `_send_purchase_request_contact_message`: resolve identifier from the contact,
  `send_text_or_template(...)` with `build_context_vars(use_case="price_tag_update")`,
  portal link from `PortalService.submission_link(contact_id, "price_tag_request", id)`,
  IntegrationLog row `business_table="price_tag_requests"`, outbound webhook enqueue. Called
  from `transition_status` after commit for EVERY transition (B1) and from the export job on
  completion when `print_by == 'self'` (PDF ready). Copy per event as in the artifact table;
  self-triggered events read as confirmations. Failure logs, never blocks the transition.
- D13 Assignee bell: `NotificationService.create_in_app_only` on `changes_requested`
  ("<contact> requested N changes on PT-…", link to CRM detail) and `approved`
  ("PT-… approved. Office print: print and mark ready for collection." / "PT-… approved.
  PDF export queued."). `event_type` `price_tag_changes_requested` / `price_tag_approved`,
  dedup key per request+status+round.
- D14 `_ENTITY_NUMBER_SOURCE` gains `price_tag_request -> doc_number`; `_form_detail_link`
  points at `/dealer-kit/price-tag-requests/{id}`. CRM transition route persists
  `TransitionPayload.note` as a `price_tag_review_comments` general row by the user (author
  user) so rejection reasons exist and reach the salesperson text.
- D15 Prod has no `form_sla_configs` row for `price_tag_request` (r7 D13 shipped the admin
  option). Owner action after deploy, listed in the PR body; not code.

### Salesperson message copy (D12, one line each, `{n}` = doc number, `{link}` = portal link)

| Event | Text |
|---|---|
| submitted | `{n} received. We will start designing shortly. {link}` |
| designing | `{n} is being designed by {assignee}. {link}` |
| proof_ready | `{n} design is ready for your review. {link}` |
| changes_requested | `You sent {count} change requests on {n}. {link}` |
| approved (self) | `You approved {n}. The PDF is being prepared. {link}` |
| approved (office) | `You approved {n}. The office will print and tell you when it is ready. {link}` |
| pdf_ready (self) | `{n} PDF is ready to download. {link}` |
| ready_for_collection | `{n} tags are ready for collection at the office. {link}` |
| collected | `{n} marked collected. {link}` |
| collected (auto) | `{n} marked collected automatically after {days} days. {link}` |
| rejected / void | `{n} was rejected: {reason} {link}` (reason from the persisted transition note, else omitted) |

### Migration test contract (tester, 14 Sep)

`blank_session` builds the schema from `Base.metadata`, so migration data steps are tested by
importing the revision file by glob and calling a named function (precedent
`487_chatbot_warehouse_cue`). Required names, each called from its own `upgrade()`:
`ptag_0007_print_collection.py`: `map_ready_rows_to_approved(bind) -> int`,
`seed_auto_collect_task(bind)`; `ptag_0008_pins_versions.py`: `backfill_pins(bind) -> int` (pinning every TAG of an
in-flight request since the combos reconciliation).

### S5 Product data pin + versions

- D16 `price_tag_request_tags.pinned_tag_data JSONB NULL`, `pinned_at timestamptz NULL`,
  `data_change_ack_hash VARCHAR(64) NULL` (combos reconciliation, 15 Sep: per TAG, not per
  line - two tags split off one line resolve different products, so they are drawn from
  different data and a Keep on one must not silence the other; answering a tag's open
  choice drops its pin, because the tag now prints something else). Pin content = the `LineTagData` the resolver
  returns (images as `{attachment_id, is_primary}`; URLs re-signed at read). Pinned when the
  request transitions to `designing` (claim, auto-assign, or changes_requested -> designing
  only if the tag has no pin yet) and when a line is added to a request already in designing.
  Migration backfills pins for every TAG of every non-terminal request at upgrade.
- D17 Read path: `resolve_request_line_data` returns pinned data when present; the live
  resolve runs alongside for non-terminal requests and each TAG gets
  `data_changes: [{field, label, old, new}]` (fields: name, dimensions, spec_lines, specs by
  key, images by attachment id, list_price, offer_price with "promotion ended" wording when
  offer goes null, barcode; set members and set price for sets). Change = live hash differs
  from pin hash AND from `data_change_ack_hash`. Terminal requests skip the live resolve.
  Marketing override still wins over the pinned offer.
- D18 CRM: record card pill `Product data changed · N` while N > 0 (N counts TAGS); Lines
  tab TAG row pill `Changed` + `Review`, with a rolled-up `Changed` pill on the line above it;
  Review dialog = table old / new per field with image thumbnails, naming the tag beside the
  code, footer `Keep current` / `Update tag`; header `Update all` when N > 1.
  `POST .../tags/{tagId}/pin`
  with `{action: update | keep}`: update = `_snapshot_draft(commit_message="Before product
  update: <fields>")` then overwrite pin, clear ack; keep = set ack hash. Designer LINES rail:
  red dot on the changed TAG row opening the same dialog; refresh-on-focus removed.
- D19 `page_versions.pinned_line_data JSONB NULL` (snapshot of all pins at write, keyed by
  TAG id since the combos reconciliation - which is what the document keys its placements on,
  so a Restore puts each pin back under the tag that was drawn from it. The column keeps its
  cut name, which is what `ptag_0009` re-keys in place on a database that already had it). Every
  `_snapshot_draft` call fills it. Request Versions: `GET .../versions`, `GET .../versions/{n}`,
  `POST .../versions/{n}/restore` (writes draft_doc + pins from the version, then snapshots
  "Restored v<n>"). UI = `RequestVersionsSheet` lifted from `TemplateVersionsSheet` (newest
  first, View opens the version's own doc + pins in the shared `DesignLightbox` since a
  request version is a whole `TagSheetDoc`, Restore adds a version and asks nothing), opened from the CRM Design section
  `History` button and the designer trailing toolbar `History` entry.

## Slices (one lane, one PR, commit per slice, S1 -> S5)

| # | Slice | Layer | Files |
|---|---|---|---|
| S1 | Preview payload + DesignViewer/DesignLightbox + order (D1-D3) | FE mock -> BE | `portal_price_tag.py`, `price_tag_requests.py` (CRM design route, same payload), `schemas/price_tag.py`, `tag_sheet_export_service.py` (payload reuse), `components/dealer-kit/DesignViewer.tsx`, `DesignLightbox.tsx`, `components/common/PreviewModalChrome.tsx`, `AttachmentPreviewModal.tsx`, `PriceTagRequestForm.tsx`, `PriceTagRequestDetail.tsx`, `sectionOrder.test.tsx` |
| S2 | Review comments table + pins UI + designer markers (D4-D6) | FE mock -> BE | migration `ptag_0007` (shared with S3), `models/price_tag.py`, `price_tag_review_service.py`, routes portal + CRM, `DesignViewer` pin layer, `RequestTagDesigner.tsx`, `TagCanvasEditor.tsx` (marker group), LinesRail, `priceTagRequestActions.ts` |
| S3 | print_by, retire ready, collection statuses, setting, scheduled task (D7-D11) | FE mock -> BE | migration `ptag_0007`, `price_tag_request_service.py`, `tag_sheet_export_service.py`, `settings.py`, `models/user.py`, `task_scheduler.py`, `lib/price-tag-status.ts`, portal form + read view, CRM detail + list, settings page |
| S4 | Salesperson WhatsApp + assignee bell + SLA number + note persistence (D12-D15) | BE | `price_tag_notify.py`, `price_tag_request_service.py`, `form_sla_service.py`, `price_tag_requests.py`, export task |
| S5 | Pin, diff, Review dialog, versions sheet (D16-D19) | FE mock -> BE | migration `ptag_0008_pins_versions`, `tag_data_service.py`, `price_tag_request_service.py`, routes, `PriceTagRequestDetail.tsx`, `ProductDataReviewDialog.tsx`, `RequestVersionsSheet.tsx`, `RequestTagDesigner.tsx`, LinesRail |

## Test list (tester writes red first, Phase 2)

pytest: portal design payload carries assets/images/fonts and hides drafts; request-changes
creates rows + round + transition, old note field still accepted; Done toggle permission
(assignee or processor only); print_by required at submit; approved terminal for self,
ready_for_collection reachable only for office; export no longer transitions; migration maps
ready -> approved; auto-collect handler respects days=0 and the threshold; every transition
calls the notifier once (mock Respond), failure does not roll back; assignee bell on
changes_requested/approved with dedup; SLA number shows PT number; pin written at designing,
backfill migration; diff fields incl. promotion ended, ack hash silences; update writes a
version with pinned_line_data then new pin; restore writes draft + pins + new version;
terminal requests skip live resolve; PDF payload uses pins.

vitest: DesignViewer renders image layers with media maps; lightbox zoom/keys/ctrl-wheel;
pin placement click vs drag, Send visibility, Escape discard; section order; status label
map; actions matrix by status x print_by; settings field mapping; Review dialog old/new
render; versions sheet list/restore calls.

Browser (agent-browser, lane stack): full journey portal submit (office) -> claim -> design
-> Mark design ready -> portal pins + Send -> CRM Done + designer markers -> design ready ->
approve -> Mark ready for collection -> portal Mark collected; self-print journey ends at
approved with Download PDF; product edit -> label -> Update -> version -> Restore.

## Captain's test list (one line per AC id, tester writes these red before the coder's Phase 2)

Contracts: `lib/dealer-kit/design-payload.ts`, `lib/dealer-kit/review-comments.ts`,
`lib/dealer-kit/print-collection.ts` (+ S5's file), the service files they sit beside, and the
portal service `app/(auth)/portal/lib/price-tag-request-service.ts`. Backend tests on the
private DB `sorento_ptag9_ci` (never the shared dev DB), Postgres only: the lane `.env` reads
`DATABASE_URL=${PTAG9_DB_URL:-<shared dev url>}`, so run
`PTAG9_DB_URL=postgresql://sorento_crm:<pw>@localhost:5432/sorento_ptag9_ci venv/bin/pytest ...`
and the running :8080 stack (no var) stays on the shared DB.

S1
- AC-S1-1 `pytest test_portal_design_payload_media`: portal GET design for a proof_ready request returns `assets` (every asset id referenced by the doc), `images` (every attachment id on the lines), `fonts`, and they equal the print payload for the same page; draft-only page or `designing` status returns 404.
- AC-S1-1b `pytest test_crm_design_payload_media`: CRM GET design returns the same keys (draft-first) for a processor; no page = 404.
- AC-S1-2 `vitest PriceTagRequestForm.sectionOrder`: Design first after status at proof_ready; absent at new; CRM detail Request tab renders `RequestDesignSection` first, empty state at new.
- AC-S1-3 `vitest DesignViewer`: image layers render `<img src>` from the media maps; pager only when sheetCount > 1; one Open button.
- AC-S1-4 `vitest AttachmentPreviewModal` + `PreviewModalChrome`: header title/counter/zoom/actions render for both consumers.
- AC-S1-5 `vitest DesignLightbox`: ctrl+wheel changes zoom and keeps the cursor point; plain wheel does not; `+ - 0` keys; drag moves scroll.
- AC-S1-6 `vitest DesignViewer`: Download PDF disabled with "PDF is being generated" when `has_completed_export` false.

S2
- AC-S2-1/2 `vitest DesignPinLayer`: click adds a point draft (w=h=0) and opens the box; drag adds a rect within 0..1; Escape/empty discards; Send button hidden at 0 drafts, `Send 1 change request` at 1.
- AC-S2-3 `pytest test_request_changes_creates_comments`: POST with comments[] + note creates N+1 rows (fractions, line_id, round, author_contact_id), transitions to changes_requested, `notes` unchanged; non-owner 404; wrong status 409.
- AC-S2-4 `vitest review-comments.tagRectsForSheet/canvasPinsForLine`: fractions map to the same mm point at two scales.
- AC-S2-5 `pytest test_review_comment_resolve_permission`: PATCH resolved by processor sets resolved_by/at; portal contact 403; GET list on both surfaces returns the rows.
- AC-S2-6 `vitest RequestTagDesigner` + `TagCanvasEditor`: markers for the selected line, Comments toggle hides them, rail badge count; clicking a marker does not change selection.
- AC-S2-7 `pytest test_round_increments`: round = number of proof_ready snapshots at send; `vitest priceTagActions`: `Mark design ready (2 open)` label, action still enabled.
- AC-S2-8 `pytest test_request_changes_legacy_note`: body `{note}` only creates one general row.

S3
- AC-S3-1 `pytest test_submit_requires_print_by`: submit without print_by = 422 PRINT_BY_REQUIRED; with = ok; `vitest PriceTagRequestForm.validation`: inline gap text.
- AC-S3-2 `pytest test_patch_print_by`: processor PATCH sets print_by while not terminal; terminal 409; response carries it.
- AC-S3-3 `pytest test_migration_ready_to_approved` + `test_export_does_not_transition`: export accepts approved/ready_for_collection/collected and leaves status; `vitest price-tag-status`: no `ready` key, labels for the two new ones.
- AC-S3-4/5/6 `pytest test_collection_transitions`: approved+self -> ready_for_collection 409; approved+office -> ready_for_collection sets timestamp; -> collected sets collected_at + actor (user via CRM, contact via portal collect); collected terminal. `vitest priceTagActions` matrix by status x print_by.
- AC-S3-7 `pytest test_setting_bounds`: 0..90 accepted, 91 rejected, default 7, present on GET settings AND app-config; `vitest settings mapping`.
- AC-S3-8 `pytest test_auto_collect_handler`: flips only ready_for_collection older than N days, sets collected_auto, no-op at 0, seeded scheduled_tasks row.

S4
- AC-S4-1 `pytest test_notify_on_every_transition`: parametrised over every edge; notifier mock called once with event + link; notifier raising does not roll back.
- AC-S4-2 `pytest test_pdf_ready_notification`: self-print export completion notifies; office does not.
- AC-S4-3 `pytest test_notify_writes_integration_log`: IntegrationLog row business_table price_tag_requests with rendered text.
- AC-S4-4 `pytest test_assignee_bell`: notifications rows for changes_requested and approved with CRM link; dedup on repeat.
- AC-S4-5 `pytest test_sla_number_source`: form-SLA notification title carries PT-number and link path.
- AC-S4-6 `pytest test_transition_note_persisted`: CRM reject with note creates a general review comment authored by the user.

S5
- AC-S5-1 `pytest test_pin_on_designing` + `test_pin_backfill_migration`: pins written at designing / line add; backfill covers non-terminal requests only.
- AC-S5-2 `pytest test_render_uses_pin`: after a product edit, CRM design, portal design and print payload still show the pinned values.
- AC-S5-3 `pytest test_data_changes_diff`: data_changes lists changed fields (price, barcode, spec, image, promotion ended); terminal request performs no live resolve (assert resolver not called).
- AC-S5-4 `vitest ProductDataReviewDialog`: old/new rows, thumbnails, promotion-ended copy, Keep / Update buttons; `Update all` at N > 1.
- AC-S5-5 `pytest test_pin_update_and_keep`: update writes a page_version with pinned_line_data and commit message prefix, replaces the pin, clears ack; keep sets ack hash and silences the diff.
- AC-S5-6 `pytest test_request_versions_routes`: list newest first, get one, restore writes draft + pins and a new "Restored v<n>" version; `vitest RequestVersionsSheet`.
- AC-S5-7 `pytest test_override_beats_pin`: marketing override wins over pinned offer.

## Risks

- Pinned images: URLs re-signed from attachment ids at read; a deleted attachment shows as
  "image removed" in the diff and keeps rendering blank until Update.
- Promotion window: pin keeps the offer after the promotion ends until Update; the diff says
  "promotion ended".
- Backfill on deploy pins live data, so nothing changes visually on day one.
- Pins anchor to the tag box, not layers; a moved layer does not move the pin.
- Respond sends disabled on lane stacks; verified through the outbox / IntegrationLog rows.
- Auto-collect needs `ENABLE_SCHEDULER=true` on prod (already true for staleness sweep).
- `ready` removal touches `PriceTagRequestsList` filters and two portal tests that name it.
