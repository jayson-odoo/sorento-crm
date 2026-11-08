# UAC: AGENT-PANEL-COMPOSER (8 Nov 2026)

Plan: `PLAN-agent-panel-composer-8nov.md`. Card: `agent-panel-composer-8nov-behaviour-card.md`. Mock OK'd by the
owner 8 Nov 15:23; Q1a Q2a Q3a Q4a Q5a final (15:25).

## Contract

All routes under `/api/v1/system`, gate `system.ai_assistant_chat.use` (same as chat).

- `POST /ai-assistant/attachments` (multipart, field `file`, one file) -> 201
  `{id, filename, size, mime_type, kind: "image"|"sheet"|"pdf", thumb_url: str|null, sheets: [{name, rows}], pages: int|null}`.
  `sheets` = the NON-EMPTY sheets in workbook order with their data-row counts (sheet kind only, else `[]`). `rows`
  = data rows under the header (blank rows not counted). `pages` = PDF page count (pdf only).
- `DELETE /ai-assistant/attachments/{id}` -> 204. Only the caller's own UNSENT draft; anything else 404.
- `POST /ai-assistant/chat` gains `attachments: [{id: str, sheet: str|null}]` (default `[]`, max 5). `message` may be
  empty (or whitespace) only when `attachments` is non-empty; both empty -> 422.
- `GET /ai-assistant/greeting` gains `can_attach: bool` (= the user is on the brain, `panel_service.on_the_brain`).

Storage: one new attachment type, code `ai_assistant_attachment`, seeded by migration (idempotent):
`allowed_extensions = png,jpg,jpeg,webp,xlsx,xls,csv,pdf`, `max_file_size_mb = 10`, `max_count_per_entity = 5`.
Upload goes through the same steps as `entity_attachment_service.create_response_attachment` (quota check, storage
via `storage_router`, `store_thumbnail` renditions, `create_attachment_and_link`, `uploader_kind='user'`), with
the link `entity_type = "ai_assistant_draft"`, `entity_id = <user id>`. On send, the link moves to
`entity_type = "ai_assistant_conversation"`, `entity_id = <conversation id>`.

## Acceptance criteria

### Upload validation (server; the browser checks the same first, the server never trusts it)

- C1 Extension not in the type's list -> 422 with the allowed list. `.xlsm` -> 422 "Macro workbooks are not read; save
  as .xlsx". `.heic` -> 422 (not in the list).
- C2 Over 10 MB -> 422 "File exceeds 10 MB limit." The route reads at most limit+1 bytes off the wire.
- C3 Content must match the extension (magic bytes): png `\x89PNG`, jpg `\xff\xd8\xff`, webp `RIFF....WEBP`, pdf
  `%PDF-`, xlsx a ZIP holding `xl/workbook.xml`, xls OLE `\xd0\xcf\x11\xe0`, csv decodes as text with no NUL byte.
  Mismatch -> 422 "The file's content does not match its type."
- C4 An `.xlsx` carrying `xl/vbaProject.bin` or a macroEnabled content type -> 422 (macro message). A ZIP over 100 MB
  uncompressed or ratio over 100 -> 422. Same guard as `supplier_price_list_reader._inspect_zip` (move it to one
  shared helper; the supplier reader imports it; no behaviour change there).
- C5 Workbooks open values-only (`openpyxl.load_workbook(read_only=True, data_only=True)`, `keep_vba` never set;
  `.xls` via `xlrd`). No macro, formula or external link is ever executed or fetched.
- C6 Password-protected or corrupt workbook / PDF, or an image Pillow cannot open -> 422 "This file cannot be read."
- C7 PDF over 20 pages -> 422 "PDFs over 20 pages are not read."
- C8 A 6th unsent draft for the same user -> 422 (the type's count cap).
- C9 More than 20 uploads per user per minute -> 429 (rate_limit bucket `panel_upload`).
- C10 No `system.ai_assistant_chat.use` -> 403. Delete of another user's file, or a file already sent -> 404 (same
  answer, so ids cannot be probed).
- C11 Delete removes the storage object, its renditions (best effort), the link and the attachments row (hard).

### Sheet reading (`read_sheet` helper, used at upload for counts and at send for the chosen sheet)

- S1 Header row = first row among the top 20 with 2 or more non-empty TEXT cells (a number is not text). Rows above
  it are skipped. None found -> no header; columns named `Column 1..N` and the note says "no header row found".
- S2 Blank rows (every cell empty) are dropped and not counted. Trailing empty columns are trimmed.
- S3 Cells: None -> ""; a float with an integer value -> plain digits (`60123456789.0` -> `60123456789`, never
  `6.01E+10`); other floats as Python `repr` trimmed; date/datetime at midnight -> `YYYY-MM-DD`, else
  `YYYY-MM-DD HH:MM`; bool -> `TRUE`/`FALSE`; text stripped, newlines -> space, `|` -> `/`; cut at 200 chars.
- S4 CSV: UTF-8 (BOM stripped) then cp1252; delimiter sniffed among `,` `;` tab, default `,`.
- S5 Row cap 50 (`batch.MAX_ROWS`, imported, not copied). Rendered block, appended to the agent's turn text:
  ```
  Attached file "Dealer contacts Nov.xlsx", sheet "Dealers": 12 rows.
  | Phone | Name | Role |
  | --- | --- | --- |
  | 60123456789 | Person A | owner |
  ```
  Cut: `Attached file "All dealers.xlsx", sheet "Dealers": first 50 of 212 rows.` CSV has no sheet part.
- S6 `sheet` on send names the sheet; null or unknown -> the first non-empty sheet.

### Send

- T1 Every id must be an attachment linked as `ai_assistant_draft` to the caller (uploaded_by = caller). Any other
  -> 404 "File not found", nothing saved, no turn run.
- T2 Over 5 attachments -> 422.
- T3 Files with a user NOT on the brain -> 422 "Files cannot be read here yet." (the old path is text only).
- T4 The panel user message keeps `content` = the typed text only, and `metadata_json.files` =
  `[{id, filename, size, mime_type, kind, sheet, rows_read, rows_total, pages}]` (null where not applicable).
- T5 Links move to `ai_assistant_conversation/<conv id>`; after send the files no longer count as drafts.
- T6 The agent's input text = typed text, then one block per file in order, separated by a blank line: sheets as
  S5; image `[image: name.png]`; pdf `[pdf: name.pdf, 3 pages]`. This text is what `envelope.text` stores, so later
  turns (history) still have the rows.
- T7 A turn with files always runs the AGENT side, route reason `attachment`, whatever `decide_route` said, EXCEPT
  a `not_eligible:*` decision, which replies the fixed line "I can't read files for you here." (route chat, status
  refused, nothing run).
- T8 Images reach the model natively: `run_agent_turn(..., images=[ImagePart])`; `_run` passes `images=` to every
  model call of the turn except the compaction call. The image sent is the `medium` rendition (1024 px JPEG,
  `image/jpeg`); when it is missing, the original downscaled with `image_thumbnailer.downscale(raw, 1024)`.
- T9 PDF: when the agent's provider is `gemini`, an `ImagePart(mime="application/pdf", data_b64=...)`; otherwise
  the PDF's text (PyMuPDF, first 20 pages, 20,000 chars max) is appended under `[pdf: name.pdf, 3 pages]`.
- T10 The agent turn's envelope records `files: [{id, filename, kind}]` (audit of what the turn read). Writes still
  go through the Confirm card and each write's own slug (unchanged).
- T11 Reading the thread (`GET .../messages` and the chat response) adds fresh presigned `url` and, for images,
  `thumb_url` to each file in `metadata_json.files`; URLs are never stored.
- T12 Later turns never resend image or PDF bytes (history is text only).

### Purge

- P1 A scheduler job (hourly) hard-deletes draft files (`ai_assistant_draft` links) uploaded more than 24 h ago:
  storage object, renditions, link, row. Sent files and newer drafts stay.

### Frontend composer (`components/chatbot/AssistantComposer.tsx`, replaces `AIAssistantBubble.tsx:960-981`)

- F1 Textarea grows 1 -> 8 lines then scrolls. Enter sends; Shift+Enter, Enter while `isComposing` (or keyCode 229),
  and Enter on a coarse pointer (`matchMedia('(pointer: coarse)')`) do NOT send.
- F2 Paste: when the clipboard has non-empty `text/plain`, the text pastes as normal (no chip), even if an image
  is also there. Otherwise image files on the clipboard become chips.
- F3 Paperclip opens a file input (`accept` = the 8 extensions, multiple); dropping files on the panel shows the
  "Drop to attach" overlay and adds chips. Client-side refusal (chip red with reason, no upload): bad type, `.xlsm`
  (macro message), over 10 MB, 6th file ("At most 5 files per message").
- F4 A chip uploads at once: name (truncate + title), size, indeterminate progress while uploading, X to remove
  (calls DELETE when it had uploaded). Server errors turn the chip red with the server's message (`extractApiError`).
- F5 Sheet chip shows a `SearchableSelect` sheet picker only when `sheets.length > 1`, default the first; row count
  of the picked sheet shown.
- F6 Send is disabled while any chip is uploading or red, or when there is neither text nor an uploaded chip.
- F7 After send, the user's bubble shows its files (image thumbnail opens `url` in a new tab; sheet/pdf chip opens
  `url`).
- F8 `can_attach` false -> no paperclip, no drop overlay, no image paste.
- F9 Mic (`hooks/useDictation.ts`): hidden when neither `SpeechRecognition` nor `webkitSpeechRecognition` exists.
  Click starts (`continuous`, `interimResults`), click again stops, 60 s with no result stops. Final words are
  inserted into the text; nothing is sent. Language EN (`en-US`) / BM (`ms-MY`) toggle, remembered in `localStore`.
  `not-allowed` error -> toast "Allow the microphone for this site".
- F10 Usable at 375 px and 1280 px; every icon button has an aria-label; no UUIDs shown.
