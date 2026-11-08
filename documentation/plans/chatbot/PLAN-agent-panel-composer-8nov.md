# PLAN: AI assistant side panel composer (multiline, attachments, voice)

Status: Review done (full track): reviewer READY, security-reviewer READY, cloud browser pass done; waiting on the owner hand test (crew test copy) and live agent checks on the Mac. Mock OK 8 Nov 15:23; Q1a-Q5a final 15:25.
Track: full (size L: new upload surface, file parsing, a data migration seeding one attachment type).
Lane: AGENT-PANEL-COMPOSER. Owner ask 8 Nov 2026 ~15:10 MYT.

Mock: `agent-panel-composer-8nov-mock.html`. Behaviour card: `agent-panel-composer-8nov-behaviour-card.md`.
UAC: `agent-panel-composer-8nov-acceptance-criteria.md`.

## Owner journey

"For our AI assistant side panel, can make it more like Claude Code? Now it is one liner, cannot be multiline, and
cannot attach image, files, like I can't provide Excel file of the contact and it go and process, voice etc."

The owner opens the panel, drops in the dealer contact sheet, types "grant access to these", and gets the same
Confirm card a pasted table gets today (#2226, #2241). Or pastes a screenshot and asks "what is this error", or
dictates a question in Malay.

## Map of today (file:line, read on main f21b67fc)

### Frontend

| What | Where |
| --- | --- |
| The panel (one component, 990 lines) | `sorento_crm_frontend/app/components/common/AIAssistantBubble.tsx` |
| Gate: panel renders only with `system.ai_assistant_chat.use` | `AIAssistantBubble.tsx:149` |
| Default panel size 384 x 600, user-resizable | `AIAssistantBubble.tsx:51-75` |
| The composer: a single-line `Input` + icon `Button` | `AIAssistantBubble.tsx:960-981` |
| `canSend` = non-empty text and not sending | `AIAssistantBubble.tsx:186` |
| Submit -> `sendText(input)` | `AIAssistantBubble.tsx:400`, `:473-477` |
| Files on an assistant reply (OUTBOUND: what the bot sends) | `AIAssistantBubble.tsx:116-119` -> `components/chatbot/TurnAttachments.tsx` |
| Chat client: JSON body `{message, conversation_id, page_snapshot, confirm_action}` | `lib/aiAssistantChatApi.ts:92-112` |
| Reusable pieces | `components/ui/textarea.tsx`, `components/common/FileDropzone.tsx` (type/size reject callbacks), `components/ui/progress.tsx`, `components/ui/badge.tsx`, `components/common/SearchableSelect` |
| Speech-to-text anywhere in the FE | none (`grep SpeechRecognition` = 0 hits) |

### Backend

| What | Where |
| --- | --- |
| Chat route, gate `system.ai_assistant_chat.use` | `sorento_crm_backend/app/api/v1/system/ai_assistant.py:312-344` |
| Request schema: `message: str` (min 1), no files | `app/schemas/ai_assistant.py:73-80` |
| Brain path: user message saved, `run_panel_turn`, assistant message saved | `ai_assistant.py:322-329` |
| Panel turn: rate limit, page context, route decision with `has_media=False` | `app/services/chatbot/panel_service.py:104-150` |
| Router: any media sends the turn to the bot (`chat`), never the agent | `app/services/chatbot/router.py:78-79` |
| Agent side: `run_agent_turn(text=..., context_before/after)`, text only | `panel_service.py:201-232`, `app/services/chatbot/agent/loop.py:1238-1268` |
| Agent model: Gemini `gemini-3.5-flash` by default via the prompt registry | `agent/loop.py:59-60`, `:1039-1055` |
| Provider already takes images: `ImagePart(mime, data_b64)`, Gemini puts them as `inlineData` on the last user turn | `app/services/llm_provider.py:69-82`, `:1468-1496`, `:1730-1756` |
| Agent wrapper passes `**kwargs` through to the provider (so `images=` reaches it) | `agent/loop.py:1065-1070`, `app/services/chatbot/llm_call.py:176` |
| Agent history = each turn's `envelope.text` + reply; older turns folded into a summary, last 6 kept verbatim | `agent/memory.py:123-136`, `:163-206` |
| Pasted-table bulk: the MODEL reads the table text; `crm_batch_propose`, 50 rows max | `agent/batch.py:20`, `:54-69` |
| A closed row comes back only when the user's latest TEXT names it (phone or name) | `agent/batch.py:110-123` |

### Upload pipeline (the ONE we reuse)

| What | Where |
| --- | --- |
| Staff thread files: `create_response_attachment` = quota check, storage upload via `storage_router`, renditions, `attachments` row + `entity_attachment_links` row, `uploader_kind='user'` | `app/services/entity_attachment_service.py:621-702` |
| Quota per attachment TYPE: `allowed_extensions`, `max_file_size_mb`, `max_count_per_entity` (admin-editable on Attachment Types) | `entity_attachment_service.py:96-140` |
| Precedent with its own type and limits: form comments (5 files), response attachments (100 MB, 10 per record) | `app/services/form_comment_service.py:53`, `:366-403`; seed in the `response_attachment` migration |
| Image renditions: `thumb` 320 px, `medium` 1024 px | `app/services/image_thumbnailer.py:39`, `:226-249` (`store_thumbnail = store_renditions`) |
| CMYK -> RGB normaliser (Meta rejects CMYK) | `app/api/v1/resources/attachments.py:905-906`, `app/services/image_normalizer.py` |
| Spreadsheet safety precedent: 25 MB cap, ZIP bomb check (100 MB uncompressed, ratio 100), `xl/vbaProject.bin` / macroEnabled refused before openpyxl opens it | `app/services/procurement/supplier_price_list_reader.py:27-53`, `:201-248` |
| Libraries already installed: `openpyxl`, `xlrd` (.xls), `PyMuPDF` | `sorento_crm_backend/requirements.txt` |
| Body limit at the edge: nginx `client_max_body_size 50m` | `sorento_crm_frontend/nginx.conf:29`, `:62` |
| The generic `POST /api/v1/attachments/` needs `resource.attachments.upload` + an attachment type, has NO size cap | `attachments.py:832-870`; not used here (panel users need not hold that slug) |

## Design (recommendations; the card's questions can change them)

1. **Composer** (FE only). `Textarea` that grows from 1 to 8 lines then scrolls. Enter sends, Shift+Enter adds a
   line; while an IME is composing Enter never sends; on a touch device Enter adds a line and the send button sends.
   Paste keeps line breaks (a textarea does natively). Paperclip button, drag-drop onto the whole panel, and pasting
   an image from the clipboard all add chips. A clipboard holding both text and an image (Excel cells copy as both)
   pastes the TEXT, as today. Mic button for dictation.
2. **Upload on attach.** `POST /api/v1/system/ai-assistant/attachments` (multipart, one file), gate
   `system.ai_assistant_chat.use`, rate-limited. It calls a sibling of `create_response_attachment` with a new
   attachment type `ai_assistant_attachment` (seeded by migration: extensions, MB cap, count cap, all editable on
   Attachment Types). Link `entity_type = ai_assistant_draft`, `entity_id = <user id>` until sent. Returns
   `{attachment_id, filename, size, kind: image|sheet|pdf, thumb_url, sheets: [{name, rows, header_row}]}`.
   Chip remove = `DELETE .../attachments/{id}` (own draft only, hard delete; a draft chip is not a record).
3. **Send.** `POST /chat` gains `attachments: [{id, sheet?}]` (max 5) and `message` may be empty when files are
   attached. The server checks every id is the caller's own draft, re-links it to
   `ai_assistant_conversation/<conv id>`, and writes `metadata_json.files` on the user message so history renders
   the chips. A turn with files always goes to the agent (new route reason `attachment`), never the bot.
4. **What the model gets.**
   - Image: the `medium` rendition (1024 px JPEG) as `ImagePart` on THIS turn only; history keeps the line
     `[image: name.png]`.
   - Sheet: the chosen sheet parsed server-side (values only, macros never run, formulas read as cached values),
     header row = first row with 2+ non-empty text cells in the first 20 rows, blank rows dropped, cut at the row
     cap. Appended to the turn text as a pipe table under `Attached file contacts.xlsx, sheet "Dealers": first 50 of
     212 rows.` Same shape as a paste, so `crm_batch_propose` and `_asked_again` (`batch.py:110`) work unchanged,
     and it is in `envelope.text`, so the next turn ("now tag these") still sees it.
   - PDF: native on Gemini (`inlineData application/pdf`) on THIS turn, page cap 20; history keeps
     `[pdf: name.pdf, 3 pages]`. If the agent's model is not Gemini, PyMuPDF text instead.
5. **Voice.** Browser Web Speech API, click to start/stop, interim words appear in the textarea at the caret, EN /
   BM language pick remembered per user (localStorage). Mic hidden where the browser has no engine (Firefox).
6. **Permissions and audit.** Same gate as chat; a file is readable only by its uploader (and trace viewers through
   the existing trace slug); presigned URLs only. Upload and link are `attachments` rows (existing audit
   listeners); the agent turn's trace records the attachment ids it read. Writes still go through the Confirm card
   and each write's own slug, unchanged.

Out of scope: server speech-to-text (unless Q4 picks it), other file types (Word, PowerPoint, zip), images in the bot
(chat) route, the old non-brain path (attach button hidden there).

## Slices (after the owner OKs)

1. FE mock: composer, chips, drop overlay, sheet picker, mic (against a mocked service). Browser pass at 375 / 1280.
2. Tester-first BE: attachment type migration, upload + delete routes, sheet reader (bomb, macro, xls, csv
   encodings, header detection, cap note), chat payload + re-link + route reason, ImagePart / PDF on the agent call.
3. Wire FE to BE, vitest for the composer keys and paste rules.
4. Reviewer + security-reviewer + cloud browser pass. Live agent checks by crew on the Mac (no Gemini key here).

## Review decisions (round 1, 8 Nov)

Fixed in round 1: UAC R1-R10 (files hidden from other staff, bounded sheet reads, file content as quoted data with no
confirm on a file turn, daily cap kept on file turns, no upload-activity rows, hard ceilings, no links for archived
files, chip removed mid-upload deletes the file).

Not changed, with the reason:
- Sheet rows stay in the turn's stored history (`envelope.file_text`), visible to trace viewers
  (`system.ai_assistant_settings.view`) like a pasted table today. The follow-up "now tag these" needs them, and the
  owner accepted chat-text retention in Q5.
- Files go to whichever agent model an admin configures (Gemini by default). The owner's "no OpenAI" ruling was on the
  voice engine (Q4); refusing files on another provider is a new policy for the owner to ask for, not this lane.
- No per-user stored-bytes cap and a deleted thumbnail may live up to a day in the CDN edge cache (signed URLs only).

Round 2 and 3 (8 Nov): security re-check READY at a82780a859 after R2b (rows read at most 100 columns, 10k rows per
sheet, 20k per workbook), R1b (private-file rule on every bulk route and the external link routes), R3b (the server
refuses confirm_action on a file turn). Round 3 should-fix closed: `link_existing_attachment` refuses another user's
panel file (covers link-packing-list, complaint, stock inquiry, purchase request and NPA links).

Not changed, with the reason: a few staff routes that take an `attachment_id` in a request body (certificates, product,
marketing, price tag, dealer kit, accessory, procurement, complaints) look it up without the private-type rule. Using
them needs the file's random id, which only admins can see (audit log); the turn envelope that holds it is not returned
by any API. The reviewer's suggested global SQLAlchemy loader rule on `Attachment` is a new app-wide layer for that
case; per "Simplest thing that works" it is deferred until an id is shown to a non-admin (trigger: any API or screen
that returns `envelope.files` or a panel file id to a user other than the uploader).

## DoD lines 6 to 8 (assistant coverage)

- 6: n/a, no new list screen or paged list route (`scripts/ci_ai_coverage.py`: ok, 0 new paged list routes).
- 7: n/a, no new record-changing button: attach, remove a chip and dictate act on the user's own unsent message,
  never on a CRM record. Writes the agent makes from a file reuse the existing ActionDefs (bulk grant, tags).
- 8: n/a, the feature is the panel's input surface, not something the assistant is asked about; an eval row is text
  only (`scripts/chatbot_eval/cases.py`) and cannot carry a file. The file path into the agent is covered by
  `tests/chatbot/test_panel_send_files.py` (real loop, scripted model), and the live agent check is crew's on the Mac.

Reviewer round 2 (at 5838b5e4): its blocker (confirm dispatch on a file turn) was already closed by R3b; its 6
surviving mutants got guard tests (N03, N10, N15, N20, N21 now killed). N09 (`PUT /{id}` route-level check) is an
equivalent mutant: the service re-reads without a viewer and answers 404 itself. Side effect, accepted: the uploader
cannot edit their own panel file through the generic `PUT /resources/attachments/{id}` (panel files are not managed
in Files). `cancel_action` stays offered on a file turn: a file could at worst cancel a waiting change, which the user
can ask for again; no write can happen from it.
