# UAC: chat-send-order (answer by send time, earlier photo first)

Plan: `PLAN-chat-send-order.md`.

- AC-1 A photo sent before a text, stored by the CRM webhook before the text's turn runs, but not
  yet at `/chat/turn` and not yet in n8n's media intake, is answered first, on its own turn row;
  its reply is the first action of the text's response.
- AC-2 The text's turn then answers about the photo's product (the focus the photo turn left),
  not the product held from before.
- AC-3 The photo's own later delivery is `duplicate: true`, is not parsed again, and its media is
  read and charged once.
- AC-4 Voice, document and sticker stored-only messages are found and rebuilt with their own
  attachment type; a stored text row, a later-sent row, a row with a turn row, a row with a media
  ledger row, a row older than 120 s before the text, a row sent before the contact's latest
  answered turn, a test (dry run) turn, and another contact's row are never answered ahead.
- AC-5 Same second: a photo and a text whose `timestamp` share one second are ordered by message
  id microseconds, for queued rows and stored rows alike.
- AC-6 No timer: the text never waits for the photo to arrive; nothing new holds the ticket.
