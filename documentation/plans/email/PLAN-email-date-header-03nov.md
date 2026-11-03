# PLAN: outbound emails carry Date + Message-ID (EMAIL-DATE-HEADER)

Status: implemented (small fix track: under 300 lines, no migration, no auth/RBAC, no new ingest)

## Problem

Owner, 3 Nov 2026: CRM emails (e.g. "OI: BRW-BB @ SO423361" from ai@sorento.com.my) show "None"
where Outlook shows the sent date/time. Outlook takes the sent time from the RFC 5322 `Date`
header. None of the three SMTP builders in `sorento_crm_backend/app/services/notification_email.py`
set `Date` or `Message-ID` (`send_mime_email`, `send_notification_email_multi`,
`send_notification_email`), and `smtplib.SMTP.sendmail` adds neither.

## Outbound paths (all of them)

- `send_mime_email`: the only live sender. Called by `app/tasks/email_outbox_tasks.py`
  `_attempt_send`, which drains `email_outbox` for every event (OI / order-inquiry emails,
  reserve requests, notifications, password reset).
- `send_notification_email_multi`, `send_notification_email`: no callers in `app/` today; kept
  and fixed so neither can be revived without the headers.
- `test_smtp_connection`: connects only, sends no message.
- Frontend `services/send-email.ts` (nodemailer): no importer; nodemailer adds both headers itself.
- No provider API (Graph, SES, SendGrid) path exists.

## Fix

One helper `_stamp_date_and_message_id(msg, from_addr)` called by all three builders right
before SMTP: `Date` = Malaysia time (+08:00) via `email.utils.format_datetime`; `Message-ID` =
`email.utils.make_msgid(domain=<sender domain>)`, default domain when the sender has none. Never
overwrites a header already present. Body, subject, recipients and attachments untouched.

## Tests

`sorento_crm_backend/tests/test_email_date_message_id_headers.py` (no DB): captures the bytes each
sender hands to smtplib and asserts one Date (+08:00, within the send window), one Message-ID
(`@<sender domain>`, unique per send), and unchanged Subject/From/To/Cc/attachment.

Evidence: `documentation/plans/email/evidence/email-date-header-sample.eml` (rendered by the real
builder, no customer data).
