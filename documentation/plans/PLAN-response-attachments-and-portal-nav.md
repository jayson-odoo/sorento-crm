# PLAN - Response attachments (with uploader attribution) + portal record navigation

**Status:** decisions D1-D12 locked with the user 2026-07-27. Implementation IN PROGRESS 2026-07-28:
migration + models + schemas landed by the orchestrator (incl. the `response_attachment` type); S1-S3 plus
form-level Reassign built in parallel. Gate before handoff: FE pass + BE pass + orchestrator code review +
whole plan implemented, THEN one prod build.

## 1. Journey (Phase 0 - governing)

**Actors:** *purchasing / technical responder* (a CRM **user**) and the *salesman* (a respond
**contact**) who submitted the form.

Today a responder can only reply in words. "SCREW OF HANDLE ONLY" needs a photo of the screw, and the
photo has nowhere to go except a separate WhatsApp message that is disconnected from the form.

New journey:

1. Responder opens the stock inquiry (or PR / SF), clicks **Edit purchasing response**, writes the
   text, and drops one or more images into the same modal - the dialog already accepts drop / choose /
   paste-from-clipboard, so no new upload UX is invented.
2. On submit, the images are stored as **form attachments on that record** and the salesman gets a
   WhatsApp update: the response text plus the portal link. The images travel with the record, not as
   loose chat media.
3. Salesman opens the portal link. At the top, above the form, a banner says
   *"Comment / reply by purchasing"* - with a new line: *"2 images attached below by purchasing"*.
4. Scrolling to Attachments, each row says who put it there: **by Tera (salesman)** vs
   **by Josephine Ng (purchasing)** - so nobody has to guess whose photo is whose.
5. From that same portal screen the salesman can page to their previous / next submission with subtle
   chevrons at the left and right edges, without going back to the list.

Derived, not asked: uploader identity and role come from the upload path (portal token = contact,
JWT = user); the banner count is computed, never typed.

## 2. Why attribution needs a schema change

`attachments.uploaded_by UUID NULL` is the only uploader field. The portal upload path
(`app/api/v1/public/portal.py::portal_upload_attachment`) calls
`create_attachment_and_link(..., created_by=None)`, so **contact uploads land with `uploaded_by` NULL
and no record of which contact uploaded**. "By contact" vs "by user" is therefore not derivable today -
NULL currently means both "a contact uploaded it" and "we don't know".

## 2a. Decisions (locked with the user 2026-07-27, second pass)

| # | Decision |
|---|---|
| D1 | **Link only** - the image is never pushed as WhatsApp media. |
| D2 | The WhatsApp message must make the attachment findable: it says there is an **attachment response**, then the portal link. Recipient must never have to guess. |
| D3 | Viewing in the portal happens **in place - no new tab**, same experience as the in-system form attachment preview. |
| D4 | Multiple attachments must not clog the banner: the banner previews them with a **scroll-through** (carousel), not a stacked list. |
| D5 | Staff upload happens in the **same popup as "Edit purchasing response"**, and accepts **multiple** files. |
| D6 | A contact **cannot** unlink a staff-uploaded attachment. Staff **can** unlink it from the system view. |
| D7 | Edge chevrons are **portal only**. Internal detail pages keep the existing top-right `19 / 38` counter - that is enough there. |
| D8 | Surfaces: **stock inquiry purchasing response + complaint technical team response**. PR/SF approval comments are a later, separate journey (internal decision, different audience). |
| D9 | Staff replies get their **own attachment type** (`response_attachment`) with its own cap, so staff and contact can never starve each other's quota. |
| D10 | The attachment sentence rides in the existing `response` context var - **no template edit**. Composed at SEND TIME only; the stored `purchasing_response` / `technical_team_response` column keeps exactly what staff typed, never the generated line. |
| D11 | Portal paging is **within the same kind, newest first** - mirrors `list_submissions(kind=...)`, which is already per-kind `created_at DESC`. Not a free choice. |
| D12 | Staff attachments surface **at the TOP, in the reply banner**, behind a `View attachment(s) (N)` button that opens the carousel preview on the same screen. Not a thumbnail strip, and not only in the Attachments section below. |

### Why D9 exists

`_check_quota` (portal.py) counts EVERY `EntityAttachmentLink` on the entity against
`portal_submission.max_count_per_entity`, currently **10** (100 MB per file, extension whitelist). With
one shared pool a chatty contact could leave purchasing with zero slots for the photo this whole feature
exists to deliver. A second type keeps the two budgets independent and gives the banner a cheap second
signal for "staff file" alongside `uploader_kind`.

### Why D10 is phrased so carefully

`send_text_or_template` renders BOTH the in-window text and the out-of-window template from the SAME
configured per-use_case body plus `context_vars` (the uniformity guarantee, respond_messaging_service.py
:515). A sentence appended in code would be silently dropped on both paths, and an empty new template
slot would be rejected by WhatsApp on approved templates. Passing it inside `response` sidesteps both
without any template or Meta approval work - provided it is composed for the send only and never
written back to the record.

Reuse, not rebuild: `components/common/AttachmentPreviewModal.tsx` already does exactly what D3 + D4
describe - a Dialog wrapping a `Carousel` (prev/next across items) with zoom and download. The portal
gets the same component. One gap to close: its `downloadItem` uses `apiFetch` (JWT, same-origin), so
the portal needs a token-authenticated download route for the Download button; the `url` used for
`<img>` rendering is already a CDN/presigned URL and needs nothing.

## 3. Slices

### S1 - Uploader attribution (foundation)

- Migration: `attachments.uploaded_by_contact_id UUID NULL` FK → `respond_contacts(id) ON DELETE SET
  NULL`, plus `attachments.uploader_kind VARCHAR(16) NULL` (`user` | `contact` | `system`), indexed on
  `uploaded_by_contact_id`.
- Portal upload path stamps `uploaded_by_contact_id = token.contact_id`, `uploader_kind='contact'`.
  Internal paths stamp `uploader_kind='user'` alongside the existing `uploaded_by`.
- Backfill: existing rows with `entity_type` in the form types and `uploaded_by IS NULL` → infer
  `uploader_kind='contact'` and `uploaded_by_contact_id` from the parent row's `contact_id`; rows with
  `uploaded_by` set → `'user'`; everything else stays NULL (`'system'` only where a worker created it).
  Idempotent JOIN-based set-where-mismatch.
- Serializers add `uploaded_by_name` + `uploaded_by_role` (`contact` / `staff`) to every attachment
  list: CRM Linked Attachments panel, portal attachment list. **Names, never UUIDs.**
- Add `uploaded_by_contact_id` / `uploader_kind` to `__audit_columns__`.

### S2 - Responder attachments + WhatsApp update + portal banner

**Upload (D5).** The existing "Edit purchasing response" modal gains the shared attachment dropzone
(drop / choose / paste-from-clipboard, `multiple`), below the response textarea. Files upload against
the same `EntityAttachmentService` entity as the form's own attachments - one list, attribution
distinguishes them; no second table, no "response attachments" silo. Rows added in the modal are
staged and committed with the response so a cancelled edit leaves nothing orphaned.

**Notify (D1, D2, D10).** Sending the response emits ONE Respond.io message. The `response` context var
passed to `send_text_or_template` is composed at send time as `<stored response text>` +
`"\n📎 Attachment response: 2 image(s) attached - open the link below to view them."`, so the existing
template body renders it on BOTH the in-window and out-of-window path with no template change:

```
Purchasing has responded to SI26-0116.
<response text>
📎 Attachment response: 2 image(s) attached - open the link below to view them.
<portal link>
```

The attachment sentence is omitted entirely when the response carries no files (never "0 attachments"),
and is NEVER persisted to `purchasing_response` / `technical_team_response` - those columns keep exactly
what staff typed. Media itself is not sent. Every send writes an `integration_log` outbox row on success AND failure per
the standing rule; the logged payload is the one actually attempted (text vs template).

**Portal banner (D3, D4, D12).** The staff attachments live **at the top, inside the existing green
"Comment / reply by purchasing" block** - that is the first thing the salesman reads, so the photo must
be reachable from there, not only from the Attachments section far below.

- Derived line *"N attachment(s) from purchasing"* (count computed, never typed).
- Next to it, a **button** - `View attachment(s) (2)` - not a thumbnail strip. Clicking it opens
  `AttachmentPreviewModal` **on the same screen**, which is already a Dialog wrapping a `Carousel`, so
  the salesman scrolls through all of purchasing's files in place with the carousel's own prev/next.
  No new tab, and the banner's height never grows with the file count (1 file or 9 look identical).
- The modal opens scoped to the **staff-uploaded set only** - the contact's own uploads stay in the
  Attachments section below and don't pad the carousel.
- Renders only when the staff attachment count > 0; the banner keeps rendering as today otherwise.
- The external-link icon on portal attachment rows is replaced by the same in-place preview, so nothing
  in the portal opens a new tab any more.

**Permissions (D6).** Portal delete is gated on the attachment's `uploader_kind`: a `contact`-uploaded
row keeps its unlink control, a `user`-uploaded row renders without one and the portal DELETE endpoint
**rejects** it server-side (403) - FE gating alone is not a control on a token surface. Staff keep
unlink in the CRM Linked Attachments panel, with the standard confirm dialog (unlink is destructive per
the standing rule).

- Portal attachment rows show the same `by <name> (<role>)` label as the CRM side.

### S3 - Portal record navigation

- Internal detail pages already have prev/next (`StockInquiryNavigation`, `PurchaseRequestNavigation`,
  `ComplaintNavigation`, GRN, suppliers, packing lists) via `useRecordNeighbours`. The **portal** has
  only "Back".
- Add token-scoped neighbours: `GET .../portal/submissions/{kind}/{id}/neighbours` returning
  `{prev_id, next_id, position, total}` over the contact's own submission list in the same order the
  portal list uses. Ownership enforced by the token, identical to `get_submission`.
- FE (**portal only**, D7): subtle edge-anchored chevrons (left + right, `fixed`-positioned, ghost,
  `opacity-60` → `opacity-100` on hover), plus `position / total` next to the record number. Hidden when
  there is no neighbour on that side. Keyboard `←` / `→` bound on desktop.
- Mobile: edge chevrons shrink to 32px hit targets inset from the safe area; they must not overlap the
  form's own controls or the banner carousel at 375px.
- Internal detail pages are **untouched** - the existing top-right `< 19 / 38 >` stays as-is.

## 4. Risks

- **Attribution backfill is inference.** A form attachment uploaded by staff *before* `uploaded_by` was
  populated could be mislabelled "by contact". Mitigation: only infer for rows whose parent form has a
  `contact_id` AND whose `uploaded_by` is NULL; log the count, and label uncertain rows as unknown
  rather than guessing a name.
- **Portal is an unauthenticated-ish surface.** The neighbours endpoint must scope by token, never by
  the requested id, or a token holder could walk other contacts' submissions.
- **Non-image attachments in the banner carousel.** A PDF or xlsx has no thumbnail; the strip shows a
  file-type tile instead. `AttachmentPreviewModal` already handles non-previewable types
  (`FileQuestion` + Download), so the modal is safe - only the strip needs the fallback tile.
- **Portal download button.** `AttachmentPreviewModal.downloadItem` goes through `apiFetch` (JWT). On
  the portal that 401s, so a token-scoped download route is required or the Download button must be
  hidden there. Decided in S2; called out because it is easy to miss until a contact taps Download.

## 5. Resolved on the second pass

Q1 → D1 (link only). Q3 → D6 (contact cannot unlink staff rows; staff can, from the system view).
Q6 → banner says the **team** ("from purchasing"), not the individual staff name - no staff identity
disclosed to an external contact; the CRM-side row keeps the person's name for internal audit.

## 5a. Still open (my defaults, override if wrong)

1. **Which response surfaces beyond stock inquiry?** D5 pins the *stock inquiry purchasing response*
   modal. Default: ship that one, then apply the identical pattern to PR/SF approval comments and the
   complaint technical-team response as a follow-up (that one already has Update & Reply, so it is the
   cheapest second surface).
2. **Portal navigation ordering.** Default: page **within the same kind** (a stock inquiry pages to
   stock inquiries), newest-first - mixing kinds makes "next" unpredictable.
3. **`uploader_kind` enum vs deriving from the two id columns.** Default: keep both. The enum makes
   `system`/worker rows unambiguous and keeps the portal 403 check a single-column test.

## 5b. Prerequisite shipped 2026-07-28 - the per-record cap is now configurable

D9 needs a cap on the new `response_attachment` type, and `attachment_types.max_count_per_entity` was a
**DB-only column**: absent from `AttachmentTypeBase/Update/Response`, absent from every API payload, and
absent from the admin dialog (which already exposed `allowed_extensions` and `max_file_size_mb`).
Changing the portal's limit of 10 required raw SQL.

Now editable end-to-end: schema fields added (the service already fans out via `**model_dump()` /
`setattr`, so no service change), a **Max attachments per record** input in the attachment-type dialog
(blank = unlimited, blank explicitly maps to NULL rather than being coerced to 0, which would read as
"no uploads allowed"), and a **Max Files / Record** column in the list rendering `Unlimited` when NULL.
Round-trip verified through the UI: 10 → 20 persisted, then blank → NULL persisted; restored to 10.

## 6. Already fixed this session (mobile, not part of the grill)

- **Header overflow with the company switcher.** `CompanySwitcher` now renders icon + code only below
  `sm` (name and chevron hidden, CSS-only so there is no hydration flip) and the topbar gap tightens
  to `gap-1.5` on phones. The bell and avatar stay on screen at 375px.
- **My downloads / Upload activity unreachable on mobile.** Both topbar icons are desktop-only and the
  comment claiming they were "reachable from the sidebar / menus" was wrong - there was no other entry
  point. Both are now items in the user dropdown (with their badge counts), which is present at every
  width; the drawers are already mounted at the layout level and open through their contexts.
