# N8N-RETIRE-A: CRM sender vs the live n8n sender, row by row

Source: crew's read-only audit of the LIVE published `sorento-chatbot-sender` and its subs
(`sendmsg`, `send-attachments`) against PR #2356 head 910be7f7, 12 Nov 2026, plus the verbatim
node definitions crew read the same day. Requirement (owner, 12 Nov): the CRM sender behaves
exactly like n8n unless a row is an agreed difference.

Status: built and reviewed (12 Nov). Agreed differences ruled by crew 12 Nov, (a) on all five
asked (rows 6 labels, 18, 19, 24, 26) plus the presign-failure fallback (row 23); rows 6, 24 and 26
are told to the owner, who may overrule, so each sits behind one named function.

Paths: `crm_sender.py` = `sorento_crm_backend/app/services/chatbot/crm_sender.py`; tests are in
`sorento_crm_backend/tests/`: `parity` = `test_crm_sender_parity.py`, `sender` =
`test_crm_sender.py`, `wiring` = `test_crm_sender_wiring.py`. Line numbers as at head 20bf0634.

Splitter proof beyond the unit tests: the reviewer ran the live JS (node 22) and `split_text` on
6,052 inputs (random mixed text, emoji, CJK, lone surrogates, 13 hand edge cases): 0 mismatches.

| # | n8n live behaviour | CRM | Verdict | CRM file:line | Test |
|---|---|---|---|---|---|
| 1 | webhook `chatbot-sender`, header key | in-process call when the turn is on the CRM path | same (transport) | `direct_ingress.py:382`, `:465` | wiring `test_switch_covering_contact_uses_crm_sender_and_never_posts` |
| 2 | throws without contact_id / turn_id | nothing sent, non-OK, a failed log row (contact) | same | `crm_sender.py:686-688` | parity `test_row02_*`, `test_n3_*` |
| 3 | whole body dropped when `is_test` or any action is `dry_run` | nothing sent for the whole turn | same | `crm_sender.py:699` | parity `test_row03_*` |
| 4 | actions strictly in order | in order, stop at the first unconfirmed | same | `crm_sender.py:224`, `:710` | sender `test_send_runs_all_five_kinds_in_order` |
| 5 | unknown kind skipped | skipped | same | `crm_sender.py:272` | sender `test_dry_run_and_unknown_kinds_are_skipped` |
| 6 | buttons: list joined with ",", split ",", trim, drop empty, first 10; buttons 2..n keep a leading space | same, labels trimmed | same, except AGREED DIFFERENCE: labels trimmed (a quirk; respond.io shows the label as given). One function: `_button_labels` | `crm_sender.py:99` | parity `test_row06_*`, `test_n1_*` |
| 7 | assign with `respond_user_id`; an empty id errors | empty id: no call, one skipped row, the run goes on | same in effect | `crm_sender.py:259-263` | parity `test_row07_*`, `test_n2_*` |
| 8 | comment `{{@user.<id>}}` mentions, newline, text | same | same | `crm_sender.py:264-270` | sender `test_comment_with_mentions_is_prefixed_on_its_own_line` |
| 9 | `update_contact_fields` sends nothing | skipped, nothing sent (crew ruling; lane C owns the flag) | same | `crm_sender.py:272` | parity `test_row09_*` |
| 10 | `is_test` records, no send | test turns never reach the sender | same | n/a | n/a |
| 11 | limits 3900 plain / 1024 with buttons, UTF-16 units | same | same | `crm_sender.py:29-30`, `:68` | parity `test_row11_*` |
| 12 | trim; cut at the last newline at or before the window if at or past the floor (800 / 450), else the last space, else hard; step back off a surrogate pair; trim parts | line-for-line port | same | `crm_sender.py:68-97` | parity `test_row12_*` (incl. `matches_the_live_chunker_part_for_part`) |
| 13 | with buttons the window shrinks (x0.9, floored) until its prefix is at most 1000 UTF-8 bytes | same | same | `crm_sender.py:68-97` | parity `test_row13_*` |
| 14 | buttons on the last part only | same | same | `crm_sender.py:240-247` | parity `test_row13_buttons_ride_the_last_part_only` |
| 15 | plain part via SEND_MESSAGE, last-interacted channel | text message, respond.io default channel | same (inferred) | `integration_service.py:465` | sender `test_send_long_text_goes_out_as_parts_in_order` |
| 16 | button body `{"message":{"type":"quick_reply","title","replies"}}` | same | same | `integration_service.py:470` | `test_respond_outbound_switch.py` `test_send_quick_reply_*` |
| 17 | empty text sends nothing | same | same | `crm_sender.py:68` | sender `test_split_text_empty_or_blank_is_no_parts` |
| 18 | no retry; the drain re-POSTs the whole body | per-part resume, look-up before any resend | AGREED DIFFERENCE (owner rule 11 Nov: a confirmed part is never resent; n8n sends part 1 twice) | `crm_sender.py:577`, `:528` | sender `test_resume_skips_confirmed_steps`, `test_unknown_text_found_in_conversation_counts_as_sent` |
| 19 | Redis push to the chat-history consumer | `message.sent` webhook writes the row, linked by message id | AGREED DIFFERENCE (owner Q5 (a), 12 Nov) | `crm_sender.py:498`, `respond_webhook.py:152` | wiring `test_confirmed_step_links_the_respond_message_id_to_the_turn` |
| 20 | template fallback / delivery check disabled | none | same | n/a | n/a |
| 21 | `attachments_src` a list or `{attachments: [...]}` | both | same | `crm_sender.py:112` | parity `test_row21_*` |
| 22 | duplicate urls removed | same | same | `crm_sender.py:112` | parity `test_row22_*` |
| 23 | url containing `cdn-sorento` (case-sensitive) -> 1 h presign through the route (attachment-row guard); else as is. A presign failure drops the file | same, in process, same guard; a presign failure sends the original url | same, except AGREED DIFFERENCE on a presign failure (the customer still gets the file) | `crm_sender.py:126-170` | parity `test_row23_*`, `test_p2_*`, `test_p3_*` |
| 24 | type by mime only: image / video / else file | `attachmentType`, then mime; audio as audio | AGREED DIFFERENCE (live entries carry no mimeType, backlog H47, so n8n sends photos as documents). One function: `_attachment_type` | `crm_sender.py:172` | sender `test_attachments_one_call_each_with_type_and_caption` |
| 25 | body `attachment.{type,url,fileName}`; video with the ORIGINAL url, image / file with the presigned one | same | same | `crm_sender.py:248-258`, `integration_service.py:476-498` | parity `test_row25_*`, `test_row23_a_video_*` |
| 26 | each file send tried 3 times, 1 s apart, in place | a 4xx goes to the link at once; a 5xx not found in the conversation is retried by the drain, the link after 3 failed tries; a connection error is retried, never a link | AGREED DIFFERENCE (same count; the drain does the retrying). One place: `MAX_SEND_ATTEMPTS` (`inbox_queue.py:73`) and the 3-try count in `_run_step` | `crm_sender.py:577-671` | parity `test_p5_*`, `test_row27_a_connection_failure_*` |
| 27 | a failing file -> a plain text that is just the bare url (presigned when presigned); the loop goes on | same; the link is its own logged step, looked up as text, never sent twice | same | `crm_sender.py:567-575`, `:722` | parity `test_row27_*`, `test_p4_*` |
| 28 | text before files | same order | same | `crm_sender.py:224` | sender `test_send_runs_all_five_kinds_in_order` |
| 31 | engine failure: sub-error-logger sends one plain text: "Sorry, I couldn't process that just now, something went wrong on our side. Please try again in a moment." (the live text has U+2014 where this table shows a comma) | the same sentence byte for byte, on the CRM path only; the n8n path is unchanged | same | `crm_sender.py:106`, `inbox_queue.py:756-766`, `:1069` | parity `test_row31_*`, `test_n4_*` |

Not in n8n's sender (CRM only, unchanged from the earlier review): the per-contact outbound switch on
every customer send, one `integration_log` row per step, Try again on CRM-sent turns, and the
"Bot replies sent by" switch.

No-send replay of past n8n runs (owner, 12 Nov): `scripts/crm_sender_replay.py`, spec
`n8n-retire-a-no-send-replay.md`, tests `test_crm_sender_replay.py`.
