# PLAN - Quotation edit view, tabs, and a live place name

**Status:** written 2026-08-05, not started.
**Parent:** `PLAN-project-quotation-document.md` (S1-S8 shipped)
**Slug:** quotation-edit-view

## Why

Client review of the shipped screen, in their words: *"I don't know when can i edit and when i
cannot, and when i want to edit, idk why it can't edit ... every addition of line doesn't trigger a
save, cause now i delete each line, then you ask me to confirm, then when i add line, you also
trigger save, very annoying, we should have an edit view imo"*, and *"the cover letter, terms and
conditions, signatures should be their own tab, so I don't need to scroll down to see, see how we
do for users list"*.

Three separate faults behind one complaint:

1. **Every keystroke is a write.** The line table saves per row, so building a scope is a stream of
   individual saves and a confirmation dialog per deletion. The dialog is correct for a live
   quotation and wrong for one being drafted, because nothing is being destroyed yet.
2. **The freeze is explained but not navigable.** The screen already says "The customer holds this
   version, so its lines cannot be changed. Open a revision to re-price it." The client read that
   and still could not tell why, because the sentence describes a state rather than offering the
   way out. `Revise to v3` is on the far side of the panel and reads like a different feature.
3. **Everything is one long scroll.** Cover letter, terms and signatures sit below the lines, so
   the parts a salesperson checks before issuing are the parts hardest to reach.

## Decisions taken with the client, 2026-08-05

- **Edit on a frozen version offers a revision** (chosen over silently branching, and over leaving
  Edit disabled). Edit stays clickable; a dialog states that this version is with the customer and
  that editing opens the next one, leaving what was sent untouched. Confirm lands the user in edit
  mode on the new version. One click, and no revision appears without being asked for.
- **One Save covers the whole quotation**: lines, header fields, cover letter and terms stage
  together, and one Cancel discards all of it. Rejected: batching only the lines, which would leave
  two different saving behaviours on one screen and reintroduce the surprise the client objected to.

## Reconciling the staged delete with the confirm-before-delete rule

`feedback_confirm_before_delete_or_unlink` says every destructive action gets an `AlertDialog`. It
still holds, and this does not break it: inside edit mode a removed line is **staged**, reversible
by Cancel, and nothing has been destroyed. The commit point moves to Save, which is where the
confirmation belongs. So:

- Removing a line in edit mode: no dialog, and the row stays visible as struck-through until Save
  so the removal is undoable rather than invisible.
- Save, when the staged set deletes lines: ONE confirmation naming the count.
- Deleting the whole document or a scope: unchanged, still its own dialog.

## Slices

| # | Slice | Ships |
|---|---|---|
| **S10** | Bulk line write | `PUT /quotation-versions/{version_id}/lines` taking the FULL desired line set in order, diffing to insert / update / delete inside one transaction. One request per Save, so a save is atomic: today's per-row writes can half-land and leave a quotation nobody edited into that state. Refuses a frozen version with the existing `quotation_version_issued` 422. |
| **S11** | Edit view | View by default (clean, read-only, no inputs). `Edit` stages every change locally; `Save` writes the lines through S10 plus one document PATCH; `Cancel` discards. Frozen version: the revision dialog above. Unsaved changes must survive a tab switch and warn on navigate-away. |
| **S12** | Tabs | Route-driven tabs matching `user-management/users/[id]/layout.tsx`: Scopes, Cover letter, Terms, Signatures. URL-addressable so a link can point at the terms. |
| **S13** | Live place name | `GET /api/v1/public/geo/nearest-place?lat=&lng=` so the signature pad shows `near Kajang, Selangor` WHILE capturing, not only after saving. |

## S13, and why the pad shows bare coordinates today

The place lookup is backend-only on purpose (one table, so the screen and the PDF cannot disagree).
The consequence was accepted too quickly: during capture nothing is saved yet, so there is no
server answer, and the pad falls back to raw coordinates. The client read that as a missing
service they had to switch on.

The fix is NOT to ship the table to the browser, which is the drift this was avoiding. It is a
small public endpoint the pad calls once it has a fix. Public because the customer counter-signing
has no session, and it reveals nothing: it answers a place name for coordinates the caller already
supplied.

## Definition of done

1. Building a scope of ten lines performs ONE write, not ten.
2. No confirmation dialog while staging; one on Save when lines are being deleted; document and
   scope deletion dialogs unchanged.
3. Edit on a frozen version reaches an editable revision in one confirm, and the issued copy is
   byte-identical afterwards.
4. Cancel restores exactly what was on screen before Edit, including across tab switches.
5. The pad shows the place name during capture, from the same table the PDF uses.
6. Verified at 375px and 1280px on a prod build, against real data.
