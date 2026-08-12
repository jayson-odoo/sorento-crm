# UAC - Response attachments, uploader attribution, portal navigation, form-level Reassign

Acceptance criteria for `PLAN-response-attachments-and-portal-nav.md` (decisions D1-D12 in its §2a).
Every line must pass with an automated test or a scripted check before manual eyeball. Regression lines
are hard blockers.

Legend: ☐ pending · ☑ passed.

## Journey

See the plan's §1. In one line: a purchasing / technical responder attaches photos **in the same popup
where they write the response**, the salesman gets a WhatsApp update that explicitly says an attachment
came with it, and opening the portal link shows a **View attachment(s) (N)** button at the top of the
reply banner that pages through purchasing's files **on the same screen**.

## A. Schema / migration

- A1 ☐ `attachments.uploaded_by_contact_id UUID NULL` FK → `respond_contacts(id) ON DELETE SET NULL`, indexed.
- A2 ☐ `attachments.uploader_kind VARCHAR(16) NULL` accepting `user` / `contact` / `system`.
- A3 ☐ `response_attachment` row exists in `attachment_types` with its own extensions / size / per-record cap.
- A4 ☐ Migration idempotent (re-run = no-op); `alembic heads` shows exactly ONE head after it lands.
- A5 ☐ `downgrade` removes the two columns cleanly and leaves `attachments.uploaded_by` untouched.
- A6 ☐ `uploaded_by_contact_id` + `uploader_kind` added to `Attachment.__audit_columns__`.

## B. Attribution

- B1 ☐ Portal upload stamps `uploader_kind='contact'` + `uploaded_by_contact_id = token.contact_id`.
- B2 ☐ Internal (JWT) upload stamps `uploader_kind='user'` and keeps writing `uploaded_by`.
- B3 ☐ Worker / system-created attachments stamp `uploader_kind='system'` (or NULL, never `contact`).
- B4 ☐ Every attachment serializer that a human sees returns `uploaded_by_name` + `uploaded_by_role`
  (`contact` | `staff`): CRM Linked Attachments panel AND portal attachment list. Names, never UUIDs.
- B5 ☐ Unknown uploader renders as an explicit em-free "Unknown" rather than a guessed name.
- B6 ☐ Backfill: form-entity rows with `uploaded_by IS NULL` infer `contact` + the parent row's
  `contact_id`; rows with `uploaded_by` set infer `user`; ambiguous rows left NULL and counted.
- B7 ☐ Backfill is idempotent JOIN-based set-where-mismatch, keyset-batched, `--dry-run` writes nothing.

## C. Staff upload inside the response popup

- C1 ☐ "Edit purchasing response" (stock inquiry) has an attachment dropzone accepting **multiple** files
  via drop / choose / paste-from-clipboard.
- C2 ☐ "Edit technical team response" (complaint) has the same dropzone.
- C3 ☐ Files staged in the popup are committed with the response; **Cancel leaves nothing orphaned**.
- C4 ☐ Uploads use the `response_attachment` type, so the contact's `portal_submission` per-record cap is
  never consumed by staff files (and vice versa).
- C5 ☐ Upload failure surfaces a toast and does NOT silently save the response text alone.
- C6 ☐ PR/SF approval comments are unchanged this slice (explicitly out of scope, D8).

## D. Notify (the message)

- D1 ☐ Sending a response with N>0 files emits ONE Respond.io message whose body contains the response
  text AND an explicit attachment sentence naming the count.
- D2 ☐ **The attachment sentence is composed at send time only.** `stock_inquiries.purchasing_response`
  and `complaints.technical_team_response` contain EXACTLY what the staff typed, byte-for-byte. Asserted
  by reading the row back after a send. **Hard blocker.**
- D3 ☐ N=0 → no attachment sentence at all (never "0 attachments").
- D4 ☐ Works on BOTH sides of the 24h window: in-window text and out-of-window template render the
  sentence, with no template edit and no new Meta approval (it rides inside the existing `response` var).
- D5 ☐ No image bytes are sent to WhatsApp (link only, D1 of the plan).
- D6 ☐ Every send writes an `integration_log` outbox row on success AND on failure, logging the payload
  actually attempted.

## E. Portal banner (top-of-screen access)

- E1 ☐ The green "Comment / reply by purchasing" block shows `N attachment(s) from purchasing` with the
  count derived, never typed.
- E2 ☐ A **View attachment(s) (N)** button sits in that banner; clicking it opens the preview
  **on the same screen** (no new tab, no navigation).
- E3 ☐ The preview pages through all staff files with prev/next (carousel), scoped to staff uploads only -
  the contact's own files are not mixed in.
- E4 ☐ Banner height is identical for 1 file and for 9 (no thumbnail strip growth).
- E5 ☐ Renders only when the staff attachment count > 0; the banner otherwise looks exactly as today.
- E6 ☐ Banner credits the team ("from purchasing"), never an individual staff member's name.
- E7 ☐ Non-image files (pdf/xlsx) open in the same preview with a file-type fallback, still no new tab.
- E8 ☐ Download inside the portal preview works under token auth (or the button is hidden there) - the
  JWT-only `apiFetch` path must not 401 silently.
- E9 ☐ Works at ~375px: button reachable, preview scrollable and dismissible.

## F. Unlink permissions

- F1 ☐ Portal shows NO unlink control on a `user`-uploaded attachment.
- F2 ☐ Portal DELETE of a `user`-uploaded attachment is **rejected server-side (403)** even when called
  directly with a valid token. FE gating alone does not satisfy this line. **Hard blocker.**
- F3 ☐ Portal DELETE of the contact's own (`contact`) upload still works.
- F4 ☐ Staff CAN unlink a staff-uploaded attachment from the CRM panel, behind the standard
  AlertDialog confirm ("Confirm delete" / "This action cannot be undone").

## G. Portal record navigation

- G1 ☐ Token-scoped neighbours endpoint returns `{prev_id, next_id, position, total}` over the
  contact's own submissions of the SAME kind, newest-first (mirrors `list_submissions`).
- G2 ☐ Ownership is enforced by the token, never by the requested id: a token holder cannot page into
  another contact's submissions. **Hard blocker.**
- G3 ☐ Subtle edge chevrons render left AND right on the portal detail; hidden on the side with no neighbour.
- G4 ☐ `position / total` is visible next to the record number.
- G5 ☐ `←` / `→` keys navigate on desktop; ignored while a dialog/input has focus.
- G6 ☐ At 375px the chevrons do not overlap the banner button or form controls.
- G7 ☐ Internal detail pages are UNTOUCHED - the existing top-right `< 19 / 38 >` still works (D7).

## H. Reassign at form level

- H1 ☐ Complaint / PR / SF / stock inquiry detail pages expose a **Reassign** action in the gear menu.
- H2 ☐ It acts on the **open form-SLA tracker** for that form (the same `activeTracker` the Escalate /
  Extend items use); hidden when there is no open tracker.
- H3 ☐ It reuses the existing `ReassignDialog`; no new endpoint.
- H4 ☐ After reassigning, BOTH tracker queries refetch (`form-sla-trackers` AND `form-sla-tracking`) so
  neither the SLA banner nor the handling-lock banner goes stale. Verified via network requests.
- H5 ☐ Permission-gated the same way the SLA screens gate it.
- H6 ☐ A voided form does not offer Reassign.

## I. Tests

- I1 ☐ pytest: attribution stamping per path, portal 403 (F2), neighbours ownership (G2), note-not-persisted
  (D2), notify on both window states, backfill matcher table. Postgres only, real FK targets seeded.
- I2 ☐ vitest: response popup with dropzone (staged / upload error / cancel), banner button states
  (0 / 1 / many), portal picker, attribution label rendering.
- I3 ☐ playwright: portal round-trip - staff responds with 2 files → contact opens portal → banner button
  → carousel pages both → no new tab opened.
- I4 ☐ Full backend suite green with ZERO errors on a clean exclusive-DB run.

## J. No-regression

- J1 ☐ Existing portal upload / delete of contact files unchanged in behaviour and shape.
- J2 ☐ Existing complaint Update & Reply and stock-inquiry purchasing response still work with no files.
- J3 ☐ Attachment quota, extension and size checks still enforced for portal uploads.
- J4 ☐ Files page / attachment browser still render rows whose `uploader_kind` is NULL (legacy).
