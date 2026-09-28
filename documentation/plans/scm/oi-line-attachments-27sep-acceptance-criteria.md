# UAC: order inquiry line attachments, sent with the OI handover email (#1312)

Plan: `PLAN-oi-line-attachments-27sep.md`. Issue: #1312. Created 27 Sep 2026.

## Journey

1. **Actor:** a sales admin or the planning lead (CS), on Project sales > Fulfilment planning,
   "Planning 1 sales orders together" for one SO (for example SO423136, 14 lines), list view,
   the "Every contributing line" grid. The system already knows every line (SO number, line
   number, item code); nothing about the line is asked again.
2. **First screen:** every row of the grid carries a paperclip icon next to the existing
   tick, cross and pencil. A line that already holds files shows the count on the icon.
3. **Step 1, one decision (which files):** CS clicks the paperclip on the line that needs a
   clarification. The existing lightbox opens, titled with the line ("SO423136 L3
   SRTWCY8605-PJ"), listing that line's files and a drop zone. CS drops the photos or the PDF
   and presses Upload. The files appear in the list and the count on the icon goes up.
   A wrong file is removed with its own x (deferred delete, 10s countdown, no confirm).
4. **Step 2, no new decision:** CS confirms the plan as today (tick, Confirm). The OI
   handover email that write sends to purchasing carries that line's files as real email
   attachments, and the line's row in the email reads "Attachments: name, name".
5. **Purchasing** opens the email: the photos and PDFs are attached to the mail itself, named
   after the SO and line they clarify. A file too large to fit the mail is named in the row
   with a link to the order inquiry line in the CRM, where it can be opened.
6. **The same icon** sits on the order inquiry's own Lines tab (Project sales > Order
   inquiries > the OI > Lines), same count, same lightbox, so purchasing and CS see the same
   files wherever they look at the line.

## Phase 1 and 2 ACs

### Storage and link (journey step 3)

- **AC-A1 [BE]** Given a user with `projects.projects.edit` and a core sales order line, when
  they POST one or more files to `/api/v1/project-sales/sales-order-lines/{line_id}/attachments`,
  then each file is stored through the existing attachment storage (an `attachments` row of
  type "Sales Order Line Attachment", `storage_provider` from `STORAGE_DEFAULT_PROVIDER`) and
  linked to the line through `entity_attachment_links` (`entity_type='sales_order_line'`,
  `entity_id` = the line id), in upload order, and the response is the line's full list.
- **AC-A2 [BE]** Given a user with only `projects.projects.view`, the upload and the delete
  answer 403; the lookup answers 200. A user without `projects.projects.view` gets 403 on the
  lookup.
- **AC-A3 [BE]** Given a file whose extension is not an image (jpg, jpeg, png, webp, gif),
  a PDF or an Excel file (xlsx, xls), the upload answers 400 naming the file; a file over 10 MB
  answers 400 naming the file.
- **AC-A4 [BE]** Given an unknown line id (or one outside the caller's company scope), the
  upload answers 404.
- **AC-A5 [BE]** POST `/api/v1/project-sales/sales-order-lines/attachments/lookup` with
  `{line_ids: [...]}` returns `{<line_id>: [ {id, attachment_id, filename, size_bytes,
  content_type, url, thumbnail_url} ]}` for exactly the lines that hold files; lines outside
  the caller's scope are omitted; more than 1000 ids answers 422.
- **AC-A6 [BE]** The delete removes the link, the attachment row and the stored object; it is
  scoped to the line (a link id under another line answers 404). The deferred action
  `sales_order_line_attachment.delete` (10s destructive window, permission
  `projects.projects.edit`) calls the same delete.
- **AC-A7 [BE]** Audit: each upload writes one `audit_logs` row `entity_type='sales_order_line'`,
  `entity_id` = the line id, `action='UPDATE'`, `new_values={"attachment_added": <filename>}`,
  `user_id` = the actor; each delete writes one with `old_values={"attachment_removed":
  <filename>}`. The `attachments` row keeps its own INSERT/DELETE audit (declarative, already
  on the model).

### The icon and the lightbox (journey steps 2, 3, 6)

- **AC-U1 [FE]** Every row of the board's "Every contributing line" grid that carries a core
  line id renders a paperclip button (`aria-label` "Attachments for SO423136 L3 <item>"),
  in the Verdict cell next to the tick, cross and pencil, same ghost icon-button size.
  A row with no core line id renders no paperclip.
- **AC-U2 [FE]** The paperclip shows the line's file count as a small badge when the count is
  above 0, and no badge at 0. The count comes from ONE lookup call per grid (all visible line
  ids), not one call per row.
- **AC-U3 [FE]** Clicking the paperclip opens the lightbox (the shared `Dialog`) scoped to that
  line: the title names the SO, line number and item code, the body lists that line's files
  (name, size, open in the shared `AttachmentPreviewModal`) and, for a user with
  `projects.projects.edit`, a `FileDropzone` and an Upload button that posts to that line
  only. A user without edit sees the list with no drop zone and no x.
- **AC-U4 [FE]** After an upload or a completed delete, the list and the count on the icon
  refresh without a page reload.
- **AC-U5 [FE]** The x on a file runs the deferred delete (`useDeferredRowAction`, toast
  countdown), never a confirm dialog.
- **AC-U6 [FE]** The order inquiry Lines tab renders the same component on every line that
  carries a core line id, in the State cell next to the existing icons.
- **AC-U7 [UX]** The lightbox is usable at 375px and 1280px (scrollable body, Upload reachable);
  the icon adds no animation (tens of uses a day: none, per the frequency gate); the lightbox
  uses the shared Dialog spring, nothing new.

### The handover email (journey steps 4, 5)

- **AC-E1 [BE]** Given a line holding files, when a CS write sends the OI handover email and
  that write includes the line, then the dispatch context's line carries `attachments`
  (in upload order) and the context carries `email_attachments` =
  `[{filename, storage_provider, storage_key}]`, filename `"<SO no>-L<line no>-<original>"`.
- **AC-E2 [BE]** The outbox row that email produces carries those files in
  `metadata_json.extra_attachments`, and the drainer sends them as MIME parts (png/jpg as
  `image/*`, pdf as `application/pdf`, xlsx as its own type).
- **AC-E3 [BE]** The rendered email's line row reads `Attachments: <name>, <name>` under the
  remark (HTML and text body); a line with no files prints nothing extra.
- **AC-E4 [BE]** Size cap: files are attached in line order then upload order while the running
  total stays at or under 15 MB (`HANDOVER_ATTACHMENT_CAP_BYTES`); every file that would push
  it over is NOT attached and its name is printed in the row as a link to the order inquiry
  line (`<OI link>?row=<row id>`) followed by "(not attached, too large for email)".
- **AC-E5 [BE]** A write whose lines hold no files sends exactly today's email (no
  `extra_attachments` key, no "Attachments:" text).
- **AC-E6 [BE]** A file deleted between the email being queued and the outbox draining does not
  block the email: the drainer skips a missing handover attachment (logged) and sends the rest.
- **AC-E7 [BE]** Migration: seeds the "Sales Order Line Attachment" attachment type once
  (idempotent) and adds the Attachments print to the handover template in place (idempotent,
  downgrade removes it). `alembic heads` shows exactly one head before and after.

## Test list (red first)

| AC | Test | Assertion in words |
| --- | --- | --- |
| A1 | `test_upload_links_files_to_core_line` | two files -> two links on the line, response lists both in order, attachment type code `so_line_attachment` |
| A2 | `test_upload_needs_edit_permission` / `test_lookup_needs_view` | 403 for view-only on upload and delete, 200 lookup |
| A3 | `test_upload_rejects_bad_type_and_size` | `.exe` -> 400 naming the file; 11 MB png -> 400 |
| A4 | `test_upload_unknown_line_404` | random uuid -> 404 |
| A5 | `test_lookup_groups_by_line` | 3 ids, 2 with files -> 2 keys, counts right; 1001 ids -> 422 |
| A6 | `test_delete_scoped_to_line` / `test_deferred_delete_registered` | wrong line -> 404; action key registered with destructive window and edit permission |
| A7 | `test_upload_and_delete_audit_on_line` | audit rows with the named values |
| E1 | `test_handover_context_carries_line_attachments` | builder output as stated |
| E2 | `test_handover_outbox_row_carries_extra_attachments` / `test_drainer_image_mime` | metadata and MIME types |
| E3 | `test_handover_template_prints_attachments` | rendered html and text contain "Attachments: SO...-L3-a.png" |
| E4 | `test_handover_size_cap_links_overflow` | 10 MB + 10 MB: first attached, second linked with the row link |
| E5 | `test_handover_without_files_unchanged` | no key, no text |
| E6 | `test_drainer_skips_missing_optional_attachment` | download raises for the optional extra -> email still sent with the others |
| E7 | `test_migration_idempotent_single_head` | upgrade twice, one type row, template marker once; one head |
| U1-U5 | `SoLineAttachmentsButton.test.tsx` | icon + badge count, lightbox title scoped, upload posts to that line id, no dropzone without edit, x calls deferred delete |
| U1/U2 | `FulfilmentBoardListView.attachments.test.tsx` | paperclip per row with a line id, one lookup call for all rows |
| U6 | `orderInquiryHeaderLinesColumns.test.tsx` addition | paperclip in the State cell |
