# UAC: Brand font management (rename + delete)

Plan: `PLAN-brand-font-manage.md`. Journey: a designer removes or renames a
brand font from the price tag editor's Font Family list.

## Manage dialog

- AC-1 In the tag editor, selecting a text layer shows a `Manage fonts` button
  beside the Font Family label (replaces `Upload font`).
- AC-2 The dialog lists every brand font (`kind='font'` asset) with its name
  rendered in its own typeface. Static fonts (DM Sans, Inter, Bebas Neue, Jost,
  Arial, Georgia) are not listed.
- AC-3 With no brand fonts the list shows `No brand fonts yet`; the upload form
  below still works exactly as before.

## Rename

- AC-4 Pencil on a row turns the name into an inline input. Enter or Save
  submits; Escape or Cancel restores the old name. Empty names cannot be saved.
- AC-5 After a successful rename the Font Family dropdown shows the new name,
  and every text layer in the OPEN document that used the old name now shows
  the new name (without a reload).
- AC-6 After a rename, every saved tag template, published tag template
  version, tag sheet page version and page draft - the four documents that can
  name a family - that used the old family now carries the new one, so
  reopening or Restoring any of them still shows the brand font (not a
  fallback). Scoped to the renamed font's own company: an identically-named
  font in another company is untouched.
- AC-7 Renaming to a name another brand font already has is refused with a
  toast that says the name is taken; nothing changes.

## Delete

- AC-8 Trash on a row turns into a countdown with Cancel (D7 deferred delete; never `confirm()`, never `ConfirmDeleteDialog`). Cancel
  leaves the font in place.
- AC-9 Letting the countdown lapse on a font no document uses removes it from the list, the
  dropdown, the database (asset + attachment rows) and object storage (file and
  thumbnail objects).
- AC-10 Letting the countdown lapse on a font still used by any of the four
  documents (a template, a published template version, a tag sheet page
  version, or a draft) is refused; the toast names the template(s) that use
  it, and the row stays. Scoped to the font's own company: a template in
  another company naming the same family does not block the delete.

## Guarding

- AC-11 Both routes require `dealer_kit.library.manage`; a user without it gets 403.
- AC-12 Renaming or deleting a non-font asset follows the same routes: rename
  changes only the row (documents hold the id), delete is refused with
  `ASSET_IN_USE` while anything references the id.
- AC-13 No new permission, table or migration. Layout usable at 375px and 1280px.
