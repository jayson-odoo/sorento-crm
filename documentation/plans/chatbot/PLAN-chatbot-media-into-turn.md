# PLAN: image and voice intake INSIDE the chatbot turn (n8n sub-media-intake retired)

Status: APPROVED 22 Sep 2026 (owner, plan page), in progress. Track: feature (`/feature`, Phase 1
FE mock first, Phase 2 tester-first, Phase 3 review once per lane). Branch
`feat/chatbot-media-into-turn` off main, one PR.
UAC: `chatbot-media-into-turn-acceptance-criteria.md` (AC-1800..1859).
Owner rulings 22 Sep: R1 fold into `/chat/turn`; R2 photo-only asks "what would you like me to
do with it?" unless a focus/domain already exists, then behave as if the codes were typed;
R3 entity cap stays operator-controlled (`media_max_entities`); R4 store the media bytes;
R5 traced (no missing photo-only message, see Evidence 3).
Plan-page rulings 22 Sep: Q1 the entities-only arm serves TYPED bare codes too (general fix);
Q2 the media prefix lists EVERY code read, never a count or "+N more" ("not transparent");
Q3 voice echoes the transcript; Q4 the 14:34 turn was served by the rearch engine, so S5
lands in `turn/compose.py` / `resolve_kinds`, not the old business lane.

## Journey

1. Dealer sends a photo of a stock list, no words. Bot: "I read M486-75-BL, M483-BL and
   MBF 9902 from that photo. Couldn't find MBF 9902. What would you like me to do with it?"
   Dealer: "check stock". Bot answers stock for the two placed codes (the photo's codes are
   in focus exactly as typed codes would be).
2. Dealer types "check stock" first (bot asks for a product), then sends the photo. Bot
   answers stock straight away; the reply opens with one line "I read M486-75-BL and
   M483-BL from that photo." so the dealer knows exactly what was recognised (every code,
   never a count).
3. Dealer sends the photo with caption "Check stock". Same as 2, one turn.
4. Dealer sends a voice note "stock for SRTWB1455". Bot answers as if typed; the reply
   opens with "I heard: stock for SRTWB1455".
5. Photo held more codes than the operator cap: the "I read" line ends with "There was
   more than I can handle in one go, so I have taken the first 10." (cap from
   `system_settings.media_max_entities`, already editable in Settings > Chatbot media).
6. Staff open Chat History: the incoming message shows the photo thumbnail (click =
   lightbox) or an audio player with the transcript under it, plus the "read N items" chip;
   the turn details show the extraction (entities, attributes, notes) as one more stage.
7. Denials (media not enabled for the number, monthly quota, burst, clip too long) and
   failures (unreadable, worker timeout) are normal turn replies with the existing wording,
   visible in the trace with a Retry button, never sent blind from n8n.

## Evidence (measured 22 Sep 2026)

1. n8n main `THfmMmYcGzDDXBu4` -> sub `sub-media-intake` (B3rBMtABou6FpY69): `detect-media`
   -> POST `/api/v1/external/media/process` -> `media-route` (continue | reply | poll |
   silent) -> `patch-transcript` rewrites the message to `type:"text"` with `rendered_text`.
   `chat-turn` body = `{envelope: {...message, media: <patched item>}}`. The engine reads
   `envelope.media` once (`engine.py:1523` -> `ctx["media"]`) and nothing consumes it.
2. Photo with no caption: `media_extract/service.py:265` forces `needs_clarification`,
   `:290` sets `rendered_text = None`; n8n takes the `reply` arm, sends "I read ... What
   would you like me to do with it?" itself, returns `handled:true`, NO `/chat/turn` runs,
   nothing reaches `session_vars.focus`. Next "check stock" starts empty. Root cause of the
   owner's amnesia report.
3. Owner's 14:34 image + caption (exec 17448465 / sub 17448466) took `continue`, answered
   stock for 8 of 10 codes. Two defects inside a "working" turn: the extractor truncated
   (`truncated: true`, "remaining handwritten items omitted") and the `confirmation_message`
   carrying that note is dropped on the `continue` arm; M496-GM and MBF 9902 were absent
   with no "Couldn't find" line (see Slice 5). No photo-only message from the owner exists
   in n8n between 04:00Z and 07:00Z; other contacts' photo-only turns did get the clarify
   reply (17444325).
4. The media lane writes only `media_extraction_job` + `contact_media_usage`. Zero writes to
   `session_vars`, `chatbot.turns`, `chat_histories`. `chat_histories` has no modality / url /
   attachment column; the drawer's `TurnAttachments` reads OUTBOUND actions only. Bytes are
   fetched (`media_extract/service.py::fetch_media_bytes` :168) and dropped.
5. Already built, reusable: `console_service.py::_run_console_media_turn` (:585-739) does
   decide + meter + enqueue + poll + run turn in-process (console path);
   `_poll_media_job` (:560-583) is the sync twin of the async `_wait_for_worker`;
   `external/media.py::_decide_meter_record_and_enqueue` (:141-211) is plain sync and takes
   (db, `MediaProcessRequest`). Engine seam: `engine.py::_run_stages`, text read at :1213,
   no-session window :1241-1277 (where the parser LLM call already lives).
6. Carry already works for typed text: `turn/apply.py::_focus_rules` (:766-777,
   `replace_same_axis`) writes confident entities to focus on EVERY turn, ask or answer;
   `apply.py:1440` carries `focus.domains` onto a bare-entity message. Gap: bare codes with
   empty focus and no domain route to the `casual` lane (`apply.py:1136`) = LLM clarifier,
   no resolve, no "couldn't find".

## Simplest thing that works

No new table, no new n8n node, no new setting. One intake step in the engine, one
deterministic arm for "entities and nothing else", one `attachments` row per media message
linked through the existing `entity_attachment_links`, one `media` block on the turn
projection the drawer already fetches.

Rejected: a second "media focus" store (focus is the one scope, D-rulings 15 Sep); a callback
from the worker into a waiting turn (the sync poll the console uses is enough at 0.25 s);
keeping the n8n sub and only fixing the `reply` arm (still two deciders of meaning).

## Slices

### S1 FE mock (Phase 1)

`ChatTranscript.tsx` incoming-message media block from a mocked `turn.media`: image
thumbnail (fixed height, `object-cover`, click opens the existing lightbox primitive), audio
`<audio controls>` with the transcript in the same bubble, one chip "Read N items" (amber
when `truncated`), denial / failure state = the plain reply bubble only. `TurnPanel` gets one
more stage row "Read the photo / Heard the voice note" with entities, attributes, notes.
375 px and 1280 px. No explanation copy on screen.

### S2 Engine intake (Phase 2, tester-first)

`engine.py::_run_stages`:

- After `_insert_turn` and inside the :1241-1277 window: if
  `message.message.attachment.type` is image/audio (same predicate as n8n `detect-media`,
  incl. `mimeType` prefix; documents / video / sticker-without-url fall through as text) and
  the media is not already patched, run `media_intake(envelope, turn_id)`:
  `_decide_meter_record_and_enqueue(db, MediaProcessRequest(... turn_id=<chatbot.turns.id>,
  caption=text-or-description))` in its own short session, then `_poll_media_job` up to
  `media_sync_wait_seconds`. Stash `{modality, decision, status, result, notices, job_id}` on
  the turn trace as stage `media_intake`.
- Completed: the parser input becomes `rendered_text` (caption + entity raws, or the entity
  raws alone when there is no caption; `service.py:265/290` change: `rendered_text` is
  ALWAYS rendered, `needs_clarification` no longer nulls it). Voice: the transcript.
- Denied / failed / pending after the wait: the turn replies with the existing wording
  (`notices[].text`, `wording.nothing_read`, `voice_unclear`, a new one-liner for the
  timeout: "I could not read that photo in time. Please send it again or type the codes.")
  as branch_kind `media_denied` / status failed with Retry; no parser call, no LLM.
- Delete the `AUDIO_NOT_PATCHED_ERROR` block (:1173-1199); `build_latest_user_message`'s
  `attachment.description` fallback stays (it is the caption).
- Reply prefix, one line, media turns only: image answered -> "I read A, B, C and D from
  that photo." listing EVERY code read (`wording.confirmation` shape, Q2: never a count,
  never "+N more") + `truncated_note` when set; voice -> "I heard: <transcript>" (capped at
  160 chars). Prepended in `_finish_turn` where the reply is sealed (:2606-2612) so every
  arm gets it once.
- Console: `_run_console_media_turn` collapses to "upload bytes, build the same envelope
  with `attachment{type,url,mimeType,description}`, call `run_turn`". One path.

### S3 Entities-only arm (Phase 2, tester-first, general fix)

`turn/apply.py::_lane` (:1136): `business_query` with entities, no domain, no
`focus.domains`, no open question -> new lane `entities_only` (not `casual`). The arm runs
the product resolver over the entities (same `resolve_kinds` the fetch would use), writes the
placed rows to `focus.products` (`focus_settles_product`), and replies deterministically:
"I read A, B and C from that photo. Couldn't find D. What would you like me to do with it?"
(typed source: "I have A, B and C. Couldn't find D. What would you like me to know?").
`session_vars.open_question` stays null (R2: the next message carries the domain, apply.py
:1440 already does the rest). Unplaced tokens are named, never dropped.

### S4 Store the media (Phase 2, tester-first)

Worker task `process_media_extraction`: after `fetch_media_bytes`, upload to the default
provider under `chatbot-media/<respond_io_id>/<message_id>-<ordinal>.<ext>`
(`storage_router.get_backend(p).upload_file`), create an `attachments` row
(`uploader_kind='contact'`, `uploaded_by_contact_id`, `mime_type`, `file_size_bytes`,
`storage_provider`, `attachment_type_code='chatbot_media'`, one seed row = migration) and
link it `entity_attachment_links(entity_type='chatbot_turn', entity_id=<turn id>)`. Upload
failure never fails the extraction (trace note only). `GET /system/chatbot/turns` and
`/turns/{id}` projections gain `media: {modality, mime_type, attachment_id, url (signed,
15 min), transcript_or_rendered_text, entities, attributes, notes, truncated, decision}`
built from the turn trace + link. Retention = same as other attachments (none special).

### S5 Partial-hit "Couldn't find" line (Phase 2, tester-first)

The rearch engine served the 14:34 turn (owner, Q4). Its rule "a token nobody could place is
named, never dropped" (`turn/compose.py:328-344`) did not fire for a `result` reply with two
unplaced product tokens. Diagnose along `resolve_kinds` (`turn_runtime.py:663-682`,
`unplaced_tokens`) -> `envelope_of.unresolved` (`:2359-2364`) -> compose, on a replay of the
14:34 envelope with the recorded parser verdict (key-free replay, the rearch gate tooling);
fix at the seam that drops them. Kill test: 10 codes, 2 unplaceable with zero fuzzy
neighbours -> "Couldn't find: M496-GM, MBF 9902." present.

### S6 n8n (owner promotes)

Main workflow `THfmMmYcGzDDXBu4`: delete `media-intake` + `media-gate`, wire
`redis-pop-main-message-list` -> `tf-message`; `chat-turn` body = `{envelope: <message>}`
(drop the `media` key); delete `if-message-is-audio` (both outputs go to `chat-turn` +
save-message). `sub-respond-save-message-redis`: for an attachment message store the caption
as `message` (empty string when none). Draft on the clone, smoke with one photo-only, one
caption, one voice, one denied number; owner promotes; archive `sub-media-intake`.
`chat-turn` HTTP timeout 90 s stays (intake wait 30 s + turn budget 60 s fit).

## Contract shapes

- Turn trace stage `media_intake`: `{modality, decision, status, job_id, tier, quota,
  notices[], result{entities[], attributes[], truncated, notes, rendered_text | transcript},
  attachment_id?, elapsed_ms}`.
- `turn.media` on `/system/chatbot/turns[/{id}]`: see S4.
- `branch_kind` new value `media_denied`; lane new value `entities_only`.
- `MediaProcessRequest.turn_id` now carries `chatbot.turns.id` (string). `context.source =
  "chat-turn"`.

## Tests (tester writes red first)

pytest, extractor + storage mocked, Postgres fixture: AC-1800..1859 map one-to-one; journey
chain tests for J1..J4 (photo-only then "check stock"; "check stock" then photo; caption;
voice), cap note, each denial kind, timeout, console path equality (console envelope ==
WhatsApp envelope shape), storage link row, projection `media` block, S5 kill test.
vitest: transcript media block (image, audio, chip, truncated amber, denial plain), TurnPanel
stage. No new Playwright spec; agent-browser evidence run on the drawer.

## Out of scope

Documents / PDF / video intake; media in the customer-facing portal; per-contact media
retention policy; n8n `chat_histories` ingest moving into `/chat/turn`.

## Follow-ups named, not built

- If turn p95 with intake exceeds `chatbot_turn_wait_seconds` (60 s) on prod, move the
  intake wait onto the worker offload flag (`CHATBOT_TURN_ON_WORKER`), measured first.
