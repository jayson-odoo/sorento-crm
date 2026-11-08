# Behaviour card: AGENT-PANEL-COMPOSER (filed 8 Nov 2026)

Plan: `PLAN-agent-panel-composer-8nov.md`. Mock: `agent-panel-composer-8nov-mock.html`.

## Rules

1. **Typing.** The box grows from 1 line to 8, then scrolls. Enter sends, Shift+Enter starts a new line (Claude
   Code and ChatGPT do the same). While a Chinese/Malay IME is composing, Enter picks the word and never sends. On
   a phone, Enter is a new line and the send button sends. Pasted text keeps its line breaks and tabs, so a pasted
   table reaches the agent exactly as today.
2. **Attaching.** Paperclip, drag a file onto the panel, or paste a screenshot. Each file becomes a chip above the
   box: thumbnail (image) or icon (sheet, PDF), name, size, upload progress, and an X to remove. Up to 5 files per
   message. Send waits until every chip has finished uploading. Text plus files, or files alone, can be sent.
3. **What is accepted.** Images `.png .jpg .jpeg .webp`; sheets `.xlsx .xls .csv`; `.pdf`. 10 MB per file
   (Q2). Anything else is refused on the chip with the reason, before upload. `.xlsm` and an `.xlsx` that carries
   macros are refused ("macro workbooks are not read; save as .xlsx"). Macros never run: the sheet is read as
   values (a formula reads as the value Excel last saved).
4. **Sheets.** The file is read on the server. Several non-empty sheets: the chip gets a sheet picker, first
   non-empty sheet chosen. The header row is the first row (of the top 20) with 2 or more text cells; rows above it
   (a letterhead) are skipped; blank rows are dropped. The agent gets the rows as a table, the same shape as a
   paste, under one line it also shows in its reply when it cut rows: "contacts.xlsx, sheet Dealers: first 50 of
   212 rows". Rows past the cap are not read (Q3).
5. **Images and PDFs.** The model sees the picture or the PDF pages itself (Gemini reads them natively) on the turn
   they are sent. Later turns keep a one-line note (`[image: error.png]`), not the pixels; to ask about it again,
   attach it again.
6. **Voice.** Mic button: click to start, click again (or 60 s of silence) to stop. Words appear in the box as you
   speak; nothing is sent until you press Enter or Send, so you can fix a misheard word. EN / BM pick next to the
   mic, remembered. Mic hidden in browsers with no speech engine (Firefox).
7. **Same rules as today.** Only users with the AI assistant permission see the panel and can upload. A file is
   visible to its uploader (and admins through the existing trace view). Changes still need the Confirm card and
   each change's own permission. The upload and every link are recorded on the file's own row; the turn's trace
   lists the files it read.

## Examples

1. **Contact sheet -> access grant.** The owner drops `Dealer contacts Nov.xlsx` (one sheet, columns Phone, Name,
   Role, Access, Company, Customer; 12 rows) and types "grant access to these". The agent gets the 12 rows as a
   table and answers with the same Confirm card as a paste (#2241): Ready / Needs your choice / Not changed.
   Masked rows (real file pending the crew data request):

   | Phone | Name | Role | Access | Company | Customer |
   | --- | --- | --- | --- | --- | --- |
   | PHONE-1 | Person A | owner | stock + price | SRT | Dealer F |
   | PHONE-2 | Person B | employee | stock | MCH | Dealer H |
   | PHONE-3 | Person C | owner | stock | SRT | No Such Shop Sdn Bhd |

   Row 1 waits for an account pick (6 accounts carry "Dealer F"), row 3 is Not changed (no customer). Same as paste.
2. **Follow-up on the same file.** Next message "tag them as Q4 promo". The rows are in the earlier turn's text, so
   the agent still has them without a re-attach (until the conversation summary folds that turn away, 6 turns on).
3. **Big sheet.** `All dealers.xlsx`, 212 data rows. The agent gets rows 1-50 and says "I read the first 50 of 212
   rows of All dealers.xlsx (sheet Dealers). Send the rest as a second file." The Confirm card holds at most 50
   rows today (`batch.py:20`).
4. **Screenshot.** The owner pastes a screenshot of a red error toast on the quotation page and asks "kenapa ni?".
   The agent reads the image plus the page context it already gets and answers.
5. **Supplier PDF.** A 3-page price list PDF and "which of these codes do we not have in products?". The agent reads
   the pages natively, then looks the codes up with its existing read tools.
6. **Dictation.** BM picked; the owner says "berapa stok SRT102 dekat Penang". The text appears in the box, the
   owner presses Enter.

## Edge cases

- Workbook with 3 sheets, two empty: no picker, the one non-empty sheet is read.
- Header not in the top 20 rows, or only one column: no header row; rows are sent as-is with "no header row found".
- Merged cells: the value sits in the top-left cell only; others read empty (openpyxl), so a merged "Company" block
  reads on its first row only. Agent sees it as written; the batch tool already refuses an empty company.
- Phone numbers stored as numbers lose a leading 0 or show as `6.01E+10`: the reader writes integers as plain
  digits (`60123456789`), never scientific notation.
- Dates come out as `2026-11-08`.
- CSV encodings: UTF-8 (with or without BOM), then cp1252 fallback; delimiter sniffed (comma, semicolon, tab).
- A ZIP bomb or a renamed macro workbook: refused before parsing (the supplier price list reader's guard).
- Password-protected xlsx or a corrupt file: chip shows "cannot be read", nothing sent.
- Scanned PDF (no text layer): fine on Gemini (reads the image). Over 20 pages: refused on the chip.
- HEIC from an iPhone: refused for now (renditions cannot make it); iPhone Safari converts to JPEG on paste and on
  most picks anyway.
- Excel copy-paste puts BOTH text and a picture on the clipboard: the text is pasted, no picture chip.
- User removes a chip after upload: the draft file is hard-deleted.
- Files attached but never sent: deleted after 24 h (Q5).
- User not yet on the brain (rollout slug off): the paperclip is hidden; the old path reads text only.
- Upload with no network / server 413: chip turns red with the reason and a retry; Send stays disabled until the
  chip is removed or retried.
- Speech: no microphone permission -> the mic shows the blocked state and a toast "Allow the microphone for this
  site". Mixed Malay-English in one sentence is weak on the browser engine (one language per session); see Q4.
- Rate: uploads count against a per-user limit (20 per minute), same idea as the panel message limit.

## Questions (each with a recommendation)

- **Q1 Send key.** (a) Enter sends, Shift+Enter new line; on a phone Enter is a new line. (b) Enter is a new line,
  Ctrl/Cmd+Enter sends. **Recommend (a)**: it is what you asked for ("like Claude Code"), it keeps today's
  one-line habit, and pasting a multi-line table does not send it (paste never presses Enter).
- **Q2 File types and size.** (a) Images png/jpg/webp, xlsx/xls/csv, pdf; 10 MB per file; 5 files per message.
  (b) Same, 25 MB per file (the supplier price list reader's cap). **Recommend (a)**: every model call carries the
  file inline and Gemini's inline request tops out near 20 MB; a contact sheet is far under 1 MB. The cap lives on
  the new attachment type, so an admin can raise it on Attachment Types without a release.
- **Q3 Sheet row cap.** (a) 50 rows, the Confirm card's own cap, with "first 50 of 212 rows" said. (b) 200 rows read
  (good for "which of these are not in the CRM?"), but a write still proposes at most 50 per card, so the agent
  has to page the card ("rows 51-100 next"), which is new card behaviour. **Recommend (a)**: one number for read and
  write, nothing new in the card, and the file never holds rows the agent silently cannot act on; raise it later
  when a real 200-row ask shows up.
- **Q4 Voice engine.** (a) Browser Web Speech API now: free, no backend, works in Chrome, Edge and Safari (Mac,
  iPhone); audio goes to Google (Chrome) or Apple (Safari) for recognition; one language per session, so mixed
  BM-English is weak. (b) Record in the browser and transcribe on our server with Gemini: works in every browser and
  handles mixed BM-English, audio stays with the vendor that already sees the text; costs a Gemini call per clip,
  needs an upload route and ~2 s wait. NO OpenAI either way. **Recommend (a) now, (b) as a follow-up only if mixed
  speech misfires in real use**: it is the simplest thing that works and you can try it today.
- **Q5 Where files live and for how long.** (a) In the normal storage (S3/R2 via the attachments table), linked to
  the conversation, kept as long as the conversation; unsent draft files deleted after 24 h. (b) Same, but every
  file deleted 30 days after upload (contact sheets carry phones and names). **Recommend (a)**: it matches every
  other upload in the app, and the same phones already sit in the chat text forever; (b) needs a purge job and
  leaves old threads with dead chips.
