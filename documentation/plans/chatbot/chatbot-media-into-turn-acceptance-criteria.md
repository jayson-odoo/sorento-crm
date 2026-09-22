# UAC: image and voice intake inside the chatbot turn

Plan: `PLAN-chatbot-media-into-turn.md`. Status: DRAFT 22 Sep 2026, awaiting owner markup.
Every AC is a red test first (pytest unless marked vitest / browser). "Photo" = WhatsApp
image attachment envelope as Respond.io delivers it (`message.message.attachment{type,url,
mimeType,description,size}`); "voice" = `attachment.type audio`.

## A. Intake runs inside `/chat/turn` (S2)

- AC-1800 A photo envelope posted to `/chat/turn` (no `media` key, no n8n patch) produces a
  turn whose trace has stage `media_intake` with `modality: image`, `decision: accepted`,
  `status: completed`, the job id, and `elapsed_ms`.
- AC-1801 The same for a voice envelope (`modality: voice`, `duration_ms` forwarded).
- AC-1802 `MediaProcessRequest.turn_id` equals the `chatbot.turns.id` of that turn and
  `context.source == "chat-turn"`; `contact_media_usage.turn_id` holds the same id.
- AC-1803 The intake call happens with no DB session open (assert via the session-factory
  spy the parser tests already use); the wait is bounded by `media_sync_wait_seconds`.
- AC-1804 A document / video / sticker-without-url attachment is NOT intake (no
  `media_intake` stage); the turn runs on the caption text as today.
- AC-1805 An envelope that already carries n8n's patched `type:"text"` + `_media` (transition
  window) is not intaked twice: one `contact_media_usage` row per (contact, message_id,
  modality, ordinal).
- AC-1806 The `AUDIO_NOT_PATCHED_ERROR` path is gone: a voice envelope never fails with
  "media intake did not transcribe this voice note".
- AC-1807 Completed image with caption "Check stock": the parser receives
  `"Check stock: <raw1>, <raw2>, ..."` (the `rendered_text` shape), never the url.
- AC-1808 Completed image with NO caption: `rendered_text` is the raws joined
  (`service.py` no longer nulls it); `needs_clarification` is still reported true in the
  result for the trace.
- AC-1809 Completed voice: the parser receives the transcript verbatim.
- AC-1810 `decision: denied_gate` -> reply text = the `not_enabled` notice wording, branch_kind
  `media_denied`, no parser call (LLM spy = 0 calls), turn status `answered`.
- AC-1811 `denied_quota`, `denied_duration` -> same shape with their notice text.
- AC-1812 `denied_burst` when the burst notice was already shown this window -> turn answered
  with an EMPTY reply and zero actions (the n8n `silent` arm, now a recorded turn).
- AC-1813 Extraction `status: failed` -> reply = `wording.nothing_read()` (image) /
  `voice_unclear()` (voice), turn status `failed`, Retry available.
- AC-1814 Job still `queued/running` after the wait -> reply "I could not read that photo in
  time. Please send it again or type the codes." (voice: "...that voice note..."), turn status
  `failed`, Retry available; the job keeps running and its later completion does not send
  anything.
- AC-1815 Quota warn notice (`append: true`) is appended to the reply of an answered media
  turn, once.
- AC-1816 Console (`/system/chatbot/console` media turn) builds the same envelope shape and
  calls `run_turn`; `_run_console_media_turn`'s private poll+turn code is deleted; console
  and WhatsApp traces for the same bytes have identical `media_intake` keys.

## B. Reply prefix (S2)

- AC-1817 An answered image turn's reply starts with "I read A, B, C and D from that photo."
  on its own line, naming EVERY entity kept in the order read; never a count, never "+N
  more" (Q2).
- AC-1818 When `truncated` is true the prefix continues with `truncated_note(max_entities)`
  ("There was more than I can handle in one go, so I have taken the first N.").
- AC-1819 An answered voice turn's reply starts with "I heard: <transcript>" capped at 160
  chars with an ellipsis.
- AC-1820 The prefix appears exactly once whichever arm answered (fetch, ask, roster,
  escalation offer); a text turn never gets it.
- AC-1821 `media_max_entities` from `system_settings` is the cap (set 3 -> three codes in
  the prefix and the note names 3).

## C. Entities-only arm (S3)

- AC-1822 Typed "M486-75-BL, M483-BL" with empty focus and no domain routes to lane
  `entities_only`, not `casual`; LLM clarifier spy = 0 calls.
- AC-1823 The arm resolves the tokens: placed rows land on `focus.products` with uuids
  (trace rule `focus_settles_product`); unplaced tokens do not.
- AC-1824 Reply for a photo source: "I read A, B and C from that photo. Couldn't find D.
  What would you like me to do with it?" (no "Couldn't find" sentence when all placed).
- AC-1825 Reply for a typed source: "I have A, B and C. Couldn't find D. What would you like
  me to know?"
- AC-1826 `session_vars.open_question` stays null after the arm; `focus.domains` stays empty.
- AC-1827 Journey J1: photo-only turn, then "check stock" -> second turn answers stock for
  the placed codes only, `domains == ["inventory"]`, no re-ask for a product.
- AC-1828 Journey J2: "check stock" (needs-scope reply), then photo-only -> the photo turn
  answers stock directly (`focus.domains` carry), prefix "I read A and B from that photo."
- AC-1829 Journey J3: photo with caption "Check stock" -> one turn, stock answered.
- AC-1830 Journey J4: voice "stock for SRTWB1455" -> stock answered, prefix "I heard: ...".
- AC-1831 A photo with a promotion focus already set behaves the same way: the codes are
  applied to the current domain, not to stock.
- AC-1832 Bare entities with a non-empty focus but a NEW domain word in the caption follow
  the caption's domain (parser decides, unchanged).

## D. Stored media (S4)

- AC-1833 After a completed image job an `attachments` row exists: `uploader_kind
  'contact'`, `uploaded_by_contact_id` = the contact, `mime_type`, `file_size_bytes`,
  `storage_provider` = default provider, attachment type code `chatbot_media`.
- AC-1834 One `entity_attachment_links` row `entity_type 'chatbot_turn'`, `entity_id` = the
  turn id, `attachment_id` = that row.
- AC-1835 Voice bytes stored the same way with the audio mime type.
- AC-1836 Storage upload failure: the extraction still completes, the trace carries
  `attachment_error`, no attachment row, no link row.
- AC-1837 A denied job (no bytes fetched) creates no attachment.
- AC-1838 Migration seeds `attachment_types` code `chatbot_media` exactly once (idempotent on
  re-run); single alembic head.
- AC-1839 `GET /system/chatbot/turns/{id}` returns `media: {modality, mime_type,
  attachment_id, url, transcript_or_rendered_text, entities, attributes, notes, truncated,
  decision}`; `url` is a signed url valid 15 minutes; `media` is null on a text turn.
- AC-1840 `GET /system/chatbot/turns` (list) carries the same `media` block per row (assert
  field presence: `response_model` must declare it).
- AC-1841 The signed url is company-scoped like other attachment reads (a user without
  `system.chat_history.view` gets 403 on the turn, never a url).

## E. Chat History drawer (S1 mock, S4 wire) - vitest + browser

- AC-1842 vitest: an incoming message whose turn has `media.modality == 'image'` renders a
  thumbnail (`img` with `alt` = caption or "Photo") inside the bubble, above the caption.
- AC-1843 vitest: clicking the thumbnail opens the lightbox with the same url.
- AC-1844 vitest: `modality == 'voice'` renders `<audio controls src=url>` and the transcript
  text under it.
- AC-1845 vitest: chip "Read N items" renders for image turns (staff-facing count is fine;
  the customer reply lists the codes); amber tone when `truncated`.
- AC-1846 vitest: a `media_denied` turn renders the plain reply bubble, no thumbnail, no
  chip.
- AC-1847 vitest: `TurnPanel` shows a stage "Read the photo" / "Heard the voice note" with
  entities, attributes, notes and the decision; absent on text turns.
- AC-1848 browser (agent-browser, via sidebar): drawer at 375 px and 1280 px, thumbnail not
  clipped, audio player fits the bubble, lightbox closes on Escape.
- AC-1849 No explanatory copy about the feature on screen (chip label + stage title only).

## F. Partial-hit "Couldn't find" (S5)

- AC-1850 (rearch engine, Q4) "Check stock: A, B, X, Y" where A, B place and X, Y have
  ZERO fuzzy neighbours -> reply lists stock for A, B and ends with a "Couldn't find: X, Y."
  line; replay of the 14:34 envelope with its recorded verdict names M496-GM and MBF 9902.
- AC-1851 Same with one unplaced token that HAS a did-you-mean neighbour -> the existing
  suggest / roster behaviour is unchanged (no duplicate mention of that token).
- AC-1852 The line names the tokens as typed (space and dash preserved: "MBF 9902").
- AC-1853 Kill test: removing the new branch makes AC-1850 fail (tester records the
  mutation).

## G. n8n cut-over (S6, owner promotes)

- AC-1854 Clone main workflow: photo-only, caption, voice and denied-number messages each
  reach `/chat/turn` with the raw attachment envelope (no `media` key) and the reply arrives
  via `sendmsg-action`.
- AC-1855 `sub-media-intake` receives zero executions after the promote (search_executions,
  24 h window); it is then archived.
- AC-1856 `chat_histories.message` for an attachment message = the caption ("" when none);
  the drawer still renders the media from the turn join.
- AC-1857 Turn p95 for media messages on the first prod day is under
  `chatbot_turn_wait_seconds` (60 s); recorded in the plan.

## H. Hygiene

- AC-1858 No new setting, no new table beyond the `attachment_types` seed; `PRINCIPLES.md`
  layering intact (FE reads `turn.media` through `chatbotTurnService`, no new fetch path).
- AC-1859 Journey-runner file for J1..J4 committed under `tests/chatbot/journeys/` and green
  before any browser verdict.
