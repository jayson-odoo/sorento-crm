# N8N-RETIRE-A: CRM sender vs the live n8n sender, row by row

Source: crew's read-only audit of the LIVE published `sorento-chatbot-sender` and its subs
(`sendmsg`, `send-attachments`) against PR #2356 head 910be7f7, 12 Nov 2026. Requirement (owner,
12 Nov): the CRM sender behaves exactly like n8n unless a row is an agreed difference. The test
column names the parity test (`sorento_crm_backend/tests/test_crm_sender_parity.py` unless noted);
the CRM column is filled with file:line once built.

Status: building. Rows marked "keep (ask)" wait on the crew-ask of 12 Nov; placeholders marked
VERBATIM-PENDING are swapped for the live text when crew answers.

| # | n8n live behaviour | CRM must | Verdict target | CRM file:line | Test |
|---|---|---|---|---|---|
| 1 | webhook transport | in-process call | same (transport) | | wiring |
| 2 | throws without contact_id / turn_id | refuse (send nothing) without either | same | | parity |
| 3 | drops the WHOLE body when `is_test` or any action is `dry_run` | send nothing for the whole turn when any action is `dry_run` | same | | parity |
| 4 | actions strictly in order | in order, stop at first unconfirmed | same | | existing |
| 5 | unknown kind skipped | skipped | same | | existing |
| 6 | buttons: join, split ",", trim, max 10 | split, trim, at most 10 | same (leading space: keep (ask)) | | parity |
| 7 | assign with `respond_user_id`; an empty id errors in n8n | never call assign with an empty id (step skipped, logged) | same in effect | | parity |
| 8 | comment `{{@user.<id>}}` mentions, newline, text | same | same | | existing |
| 9 | `update_contact_fields` sends nothing | skip the action, send nothing (crew ruling; lane C owns the flag) | same | | parity |
| 10 | `is_test` records, no send | test turns never reach the sender | same | | n/a |
| 11 | limits 3900 plain / 1024 with buttons | same | same | | parity |
| 12 | cut at the last newline before the limit if past the floor (800 plain / 450 buttons), else last space, else hard cut; never split a surrogate pair; length in UTF-16 units | same | same | | parity |
| 13 | button message also capped at 1000 UTF-8 bytes | same | same | | parity |
| 14 | buttons on the last part only | same | same | | existing |
| 15 | plain part via SEND_MESSAGE, last-interacted channel | text message (respond.io default channel) | same | | existing |
| 16 | button body `{"message":{"type":"quick_reply","title":..,"replies":[..]}}` | same | same | | existing |
| 17 | empty text sends nothing | same | same | | existing |
| 18 | no retry; drain re-POSTs the whole body | per-part resume + look-up before resend | keep (ask) | | existing |
| 19 | Redis push to the chat-history consumer | `message.sent` webhook row, linked by message id | keep (owner Q5) | | wiring |
| 20 | template fallback / delivery check disabled | none | same | | n/a |
| 21 | `attachments_src` is a list OR `{attachments: [...]}` | accept both | same | | parity |
| 22 | remove duplicate urls | same | same | | parity |
| 23 | url containing `cdn-sorento` -> 1 h presigned URL; else as is | same, in-process presign | same | | parity |
| 24 | type by mime: image / video / else file | attachmentType, then mime | keep (ask) | | existing |
| 25 | sends the file name | same | same | | parity |
| 26 | file send retried 3 times, 1 s | drain retries from the failed step | keep (ask) | | existing |
| 27 | a file that still fails -> its link sent as a text message, run continues | same | same | | parity |
| 28 | text before files | same | same | | existing |
| 31 | engine failure: n8n sub-error-logger sentence | the same sentence (VERBATIM-PENDING) | same | | parity |
