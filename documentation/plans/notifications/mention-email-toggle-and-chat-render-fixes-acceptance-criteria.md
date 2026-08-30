# UAC: mention email toggle + two chat render fixes

Status: VERIFIED 30 Aug 2026 - AC-A*, AC-B*, AC-C1..C6 all pass (unit + browser + DB outbox row)

## Slice A - quoted quick_reply excerpt

- AC-A1 A contact reply quoting a `quick_reply` message renders the quoted `title` in the
  "Replying to" block. Never the literal `[quick_reply]`.
- AC-A2 A quoted `quick_reply` with no title renders its option labels joined by ` | `.
- AC-A3 A quoted media message still renders its typed placeholder (`[image]`).
- AC-A4 The AI reply-draft transcript line for a `quick_reply` message is its title.

## Slice B - internal note mention row

- AC-B1 A CRM-authored note whose body already contains `@Name` for every mentioned user
  renders no mention header row (`chat-internal-note-mentions` absent).
- AC-B2 A note whose mentioned names are NOT in the body (Respond-mirrored) still renders
  the header row with those names.

## Slice C - mention email toggle

- AC-C1 `users.notify_email_on_mention` exists, boolean, not null, default true, added by
  migration `444_notify_email_on_mention` chained on `443_fulfilment_planning_flag`.
- AC-C2 With the flag on, an @-mention creates `in_app` + `email` deliveries for the
  mentioned user, and the email delivery produces an `email_outbox` row addressed to that
  user's email.
- AC-C3 With the flag off, only the `in_app` delivery is created.
- AC-C4 The flag is readable and writable through the same endpoints the other
  `notify_email_on_*` flags use, and reaches the FE (present in the /me payload).
- AC-C5 My Account > Notification channels shows a "Mentioned in a note" row with an
  email toggle, in the same matrix as the other events. The admin user edit dialog
  carries the same field.
- AC-C6 The author of the note never receives their own mention notification.
