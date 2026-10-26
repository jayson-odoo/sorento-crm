# UAC: Outbox row attachments (OUTBOX-ATTACHMENT)

Plan: `documentation/plans/email/PLAN-outbox-attachment-26oct.md`

- AC-1: Opening an Email Outbox row that carries files shows an Attachments block listing every
  file the email sends (the row's own attachment, then each `extra_attachments` entry), by
  filename, in send order.
- AC-2: Each file has a Download button that saves the stored file under its filename.
- AC-3: An Excel or PDF file also has a Preview button that opens the existing attachment preview
  (sheet grid / PDF viewer) for that file.
- AC-4: A row with no files shows no Attachments block.
- AC-5: A file missing from storage gives a clear "not found" message instead of a broken
  download.
- AC-6: Only a user who can view the Email Outbox can download; the server serves only files the
  row itself lists (addressed by position, never by a storage key from the browser).
- AC-7: The dialog is usable at 1280px and 375px.
