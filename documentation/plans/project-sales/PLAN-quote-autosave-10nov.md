# PLAN: Proposal / quotation autosave with history (QUOTE-AUTOSAVE)

Status: Merge-ready pending CI (reviewer READY after 3 rounds, security review: no IDOR or bypass,
its should-fix done or answered; cloud browser pass done). Track: full (size L, migration). UAC: `quote-autosave-10nov-acceptance-criteria.md`.

## Owner answers (10 Nov 2026 ~15:10 MYT, via crew). These supersede the card where they differ.

- **Q1 (a)**: autosave writes a DRAFT; Save applies it (the tag designer split).
- **Q2 (b)**: a NEW proposal's draft is PRIVATE per person per project and numbered on its first
  Save, so an abandoned draft uses up no number.
- **Q3**: "follow price tag setting": History copies the tag designer's rule exactly. An entry per
  Save; Restore first keeps the state being left as "Before restore to version N" (the draft, else
  the latest Save, `price_tag_requests.py:941-997`), then the entry becomes the draft. Autosave
  writes no History.
- **Q4**: the OLDER tab / session becomes VIEW-ONLY ("I worry the user open 2 tabs at once"):
  banner "Opened in another tab / by <name> at <time>", fields locked, Reload; its unsent text
  goes to History.
- **Q5 (a)**: Cancel becomes "Discard draft" with a 5 s undo (the reversible pending action).

## As built

- `projects.quotation_document_drafts` (audit-skipped): one shared row per document, or a private
  row per person per project for a new proposal (`document_id` NULL, `owner_user_id`). Every open
  of the form claims it (`holder_token`); only the holder writes.
- `projects.quotation_document_snapshots` (insert-only, audit-skipped): kinds `saved`,
  `before_restore`, `conflict`. Numbered oldest = 1 at read time ("Version N").
- Routes (`api/v1/projects/quotation_documents.py`): `.../{id}/form-draft/open`, `.../holder`,
  `PUT .../form-draft`, `.../history`, `.../history/{entry}`, `.../history/{entry}/restore`;
  `.../new-draft/open`, `.../new-draft/holder`, `PUT .../new-draft`. Create / PATCH take
  `form_state` + `form_token`. Issue and Request approval refuse 409 `quotation_draft_pending`.
- Discard draft: record action `quotation_form_draft.discard` (`record_actions.py`, 5 s).
- FE: `useQuotationFormAutosave.ts` (the tag designer's `useAutosave` + `AutosaveIndicator`, flush
  on unmount and `pagehide`, retry on `online`, local mirror, holder check every 15 s and on
  focus), `QuotationFormClient.tsx` (opens on the draft, Save carries the state and claim, view-only
  banner and `inert` body, Discard draft countdown, History button), `QuotationHistorySheet.tsx`,
  the read page's draft hint (`QuotationDocumentClient.tsx`).

Owner ruling, 10 Nov 2026 ~14:15 MYT: "I think the quotation should be always saved instead of
needing me to click 'Save' otherwise if I click outside then all the data will be gone, should be
auto-saved with history just like our tag designer".

Scope: the Project Sales proposal AND quotation form (new + edit,
`quotation-documents/components/QuotationFormClient.tsx`). Save path, state layer and page
actions only. Collapsible sections (PROPOSAL-FORM-COLLAPSE #2302) and the "To" party picker
(PROJECT-PARTY-ROLES #2300) are other lanes.

## Scout (file:line)

### The tag designer's autosave (the pattern to reuse)

- `sorento_crm_frontend/hooks/useAutosave.ts`: the one debounce. 1 s after the last committed
  change, saves serialised (never two PUTs racing), `flush()` for moments that cannot wait,
  `retry()` resends the failed value, status `idle | saving | saved | error`.
- `sorento_crm_frontend/app/(protected)/dealer-kit/components/AutosaveIndicator.tsx`: "Saving..." /
  "Saved 2:14 PM" / "Save failed Retry", next to the manual Save.
- Request designer, `price-tag-requests/[id]/design/components/RequestTagDesigner.tsx:1064-1153`:
  value-compare guard so the load is not an edit (:1084-1104), flush on unmount and `pagehide`
  with `keepalive` (:1110-1136), manual Save = `flush()` then the deliberate save (:1150).
- Backend split, `sorento_crm_backend/app/api/v1/dealer_kit/price_tag_requests.py`:
  - `PUT /{id}/design/draft` (:1359) overwrites `page.draft_doc` in place, never a version.
  - `PUT /{id}/design` (:1395) is the deliberate Save: `_snapshot_draft` (:1284) writes the next
    immutable `PageVersion` and clears the draft.
  - `GET /{id}/design` (:1336) opens draft-first, else the latest version.
  - Column: `app/models/dealer_kit.py:132` `draft_doc = Column(JSONB(none_as_null=True))`.
- History: `components/dealer-kit/RequestVersionsSheet.tsx` (newest first, who + when + note,
  View, Restore; Restore runs at once with no confirm and ADDS an entry, it never destroys one).
- Conflict handling: none in the request designer (last write wins). The template editor has
  `StaleTemplateError` for its linked accessory boxes only.

### The proposal / quotation save path today

- The form holds everything in the browser until Save (`QuotationFormClient.tsx:280-291` warns on
  `beforeunload` only). An in-app click away (sidebar, crumb, Cancel) loses it with no warning.
- Create: `POST /projects/{pid}/quotation-documents` (`api/v1/projects/quotation_documents.py:136`)
  writes header + scopes + lines in one commit; the number is assigned here
  (`services/project_quotation_document_service.py:257`, `_next_document_no` :185). The FE shows
  "Numbered on save" until then (`QuotationFormClient.tsx:826-832`).
- Edit: `PATCH .../{did}` (`quotation_documents.py:228`): header, `remove_scope_ids`, `scopes[]`
  whose `lines` REPLACE the scope's current version's set (`project_quotation_service.py:1092`).
  No optimistic concurrency anywhere (no updated_at / If-Match check).
- Every create / PATCH fires, per line, the floor-breach alert to management
  (`_notify_breaches`, `api/v1/projects/quotations.py:91`, called at `quotation_documents.py:159`
  and `:282`), re-runs guardrails and writes audit rows for every re-written line. Autosaving
  through this PATCH would alert management once per intermediate price typed and churn line ids.
- Revisions: customer revisions A, B... (proposal) / R1, R2... (quotation) are `quotation_issues`
  rows, written only by `issue()` (`project_quotation_document_service.py:647`). Per-scope versions
  (`ProjectQuotationVersion`) freeze on issue; an issued version refuses edits with 422
  `quotation_version_issued` (`project_quotation_service.py:208-227`).
- PRICE revision alert (owner 2 Nov): fired ONLY on issue (`service:755-759`, deferred job at
  `quotation_documents.py:450-463`, `alert_price_changes` `service:830`). Not on save.
- Discount approvals: a manual press, `POST .../approval-status` (`quotation_documents.py:545`).
  Locked states `pending_approval`, `resubmitted`, `approved` refuse edits with 422
  `quotation_locked_for_approval` (`project_quotation_approval_service.py:82`, `:543`).
- No per-document snapshot / history table exists. STANDARD-HISTORY (#2298, not merged) is an
  audit-event History TAB (DataGrid of audit rows); there is no `RecordHistory` component yet.

## Behaviour card

### Rules (recommended answers to Q1-Q5 assumed)

1. **Every edit autosaves, like the tag designer.** 1 s after the last change the form's whole
   state (header, cover letter, terms, scopes, every staged line, scopes removed) is written to
   the document's DRAFT: one JSONB column on `quotation_documents`, overwritten in place. Same
   `useAutosave` hook, same `AutosaveIndicator` ("Saving...", "Saved 2:14 PM", "Save failed Retry")
   in the page header beside the Save button.
2. **Leaving never loses anything.** In-app navigation (sidebar, crumb, Back) flushes on unmount;
   refresh / tab close flushes on `pagehide` with `keepalive`; the `beforeunload` prompt goes.
   A failed save (offline) is retried on its own when the browser comes back online, and the
   unsent state is also mirrored to this browser's local storage so a tab closed while offline
   still comes back on the next open.
3. **Reopening opens the draft.** Edit opens on the draft when one exists, else the saved record.
   The read page shows a strip under the header: "Unsaved draft, last edited 2:14 PM by Aina"
   with "Continue editing".
4. **Save is the deliberate act, unchanged in what it fires.** "Save proposal" / "Save quotation"
   flushes the autosave, then runs today's POST/PATCH from the draft, so floor-breach alerts,
   guardrails and audit fire exactly as today, once per Save, never per autosave. It then writes
   a History entry and clears the draft.
5. **History.** A History button (lucide History icon, like the designer's rail) opens a sheet:
   every Save, newest first, who, when, total. View shows that state read-only; Restore loads it
   into the draft (no confirm; the draft before the restore becomes its own entry "Before
   restore", so Restore never destroys anything). The record changes only on the next Save.
6. **Locked stays locked.** Autosave writes nothing while the document is approval-locked
   (pending / resubmitted / approved) and never touches an issued scope version (the editor
   already shows those lines read-only). PRICE revision alerts (issue) and discount approvals
   (the approval press) are untouched: they never fire from an autosave.
7. **Issue and Request approval need the draft saved first**: refused with "Save or discard the
   draft first" (409 `quotation_draft_pending`), so a customer never receives a revision missing
   edits that are sitting in a draft.

### Examples

- New proposal: Aina opens Project > Proposals > New proposal, types the Subject. One second
  later the proposal exists as Q-2026-0142 (draft), the header says "Saved 2:14 PM". She clicks
  Inventory in the sidebar. Next morning she opens Q-2026-0142 from the project's list: the read
  page says "Unsaved draft, last edited 2:14 PM by Aina"; Continue editing shows her Subject.
- Price typed below floor: on an existing proposal Aina types 120.00, then 1200.00 on a line whose
  floor is 900. Autosave writes both to the draft; management gets nothing. She presses Save:
  1200.00 is above floor, no alert. (Today, two Saves would have alerted once.)
- Network blip: Wi-Fi drops while she edits the terms. The header shows "Save failed Retry"; she
  keeps typing; Wi-Fi returns and the indicator goes "Saving...", "Saved 2:21 PM" on its own.
- Restore: Ben opens History on QT-2026-0031, Views the 9 Nov 16:02 entry (total RM 48,200.00),
  presses Restore. The form now shows the 9 Nov lines with "Saved" in the indicator; History now
  starts with "Before restore, 10 Nov 14:40". Nothing reaches the record until he presses Save.
- Issued revision: proposal Q-2026-0120 has revision A sent. Its scope's lines show read-only in
  the form as today; editing them needs Revise (today's flow). The header and a new scope still
  autosave.

### Edge cases

- Two tabs or two users on one draft: each autosave carries the draft revision it last read; a
  stale one is refused (409), that tab stops autosaving and shows "Edited in another tab or by
  Ben at 2:30 PM, Reload"; its unsent state is kept as a History entry "Not saved, edited
  elsewhere" so nothing typed is lost (Q4).
- Someone Saves or issues from another tab while a draft exists: the draft records the record's
  version it was built on; a draft older than the record still opens, and Save re-checks on the
  server exactly as today (issued lines still 422).
- An untouched new form (nothing typed): no record, no number, nothing written (the load and
  template defaults are not edits, same value-compare guard as the designer).
- A draft that fails validation (a line without a product, a non-number price): autosave keeps
  it (a draft may be unfinished); only Save refuses, with today's messages.
- Payload size: the teardown flush is `keepalive`, capped at 64 KB by the browser; a larger
  draft relies on the local-storage mirror and the in-app unmount flush (no keepalive needed).

### Questions (each with a recommendation)

1. **What autosave writes.** (a) the tag designer split: autosave writes a DRAFT on the document,
   Save applies it (alerts and audit exactly as today); (b) autosave PATCHes the real record every
   second, the Save button goes, and the floor-breach alert moves to issue. **Recommend (a)**: it
   is literally the tag designer, management is never alerted mid-typing, and approvals, alerts
   and revision locking stay untouched. The cost: the record and the PDF change only on Save
   (the draft strip makes that visible).
2. **When a new proposal becomes a record.** (a) the first real edit creates it, with its number,
   in the project's list as a draft; (b) a per-user draft with no record and no number until the
   first Save. **Recommend (a)**: a colleague can find it, and today's Delete removes an abandoned
   one. Cost: an abandoned new proposal uses up a number.
3. **What History records.** (a) one entry per Save plus the automatic "Before restore" / "Not
   saved, edited elsewhere" entries (the tag designer's rule: autosave never writes history);
   (b) also an automatic entry every 10 minutes of editing. **Recommend (a)**: the designer's
   rule, and a 10-minute trail buries the Saves the owner will want to go back to.
4. **Two tabs / two users on one draft.** (a) the stale writer is stopped with Reload and its
   unsent state goes to History; (b) last write wins (the designer today). **Recommend (a)**:
   (b) silently loses one person's typing, which is the bug this lane exists to fix.
5. **What Cancel becomes.** (a) Cancel goes; the page header gets "Discard draft", shown only
   while a draft exists, which puts the form back to the last Save and keeps the discarded draft
   as a History entry (so it destroys nothing and needs no countdown, the History sheet's own rule
   for Restore); leaving by any route keeps the draft; (b) Cancel stays and discards. **Recommend
   (a)**: a Cancel that throws work away is the click-outside loss the owner is reporting, under a
   friendlier name.

### Mock

None needed: the form keeps its layout; the only new UI is the designer's own
`AutosaveIndicator`, a History button + sheet lifted from `RequestVersionsSheet`, and a one-line
draft strip on the read page.

## Slices (after the owner answers)

1. BE: migration (`quotation_documents.form_draft JSONB`, `form_draft_rev INT`,
   `form_draft_at`, `form_draft_by`; table `quotation_document_snapshots`), `PUT .../draft`
   (lock + rev check, no side effects), `DELETE .../draft`, snapshot list / get / restore, Save
   writes a snapshot and clears the draft, issue / approval refuse while a draft exists. Tests
   first.
2. FE: `useAutosave` wired into `QuotationFormClient` (draft seed on open, first-edit create,
   flush on unmount / pagehide / online, local mirror, 409 handling), History sheet, draft strip,
   Discard draft. Vitest first, kill tests for the lost-edit scenarios.
3. Review, security review, browser pass, hand-test script.

## Review rounds (10 Nov)

- Round 1 (reviewer NOT READY): Restore left stale line ids on the same version (B1); History
  entries held only changed scopes (B2: entries now carry every scope's stored lines,
  `record_lines`, and a Save's entry is rebuilt from the record); a Discard kill-test gap (B3);
  typing during a Save; local copies reviving a discarded draft, shared between tabs, or reopened
  unreconciled; refused Save/Restore not locking. All fixed with tests.
- Round 2: restored lines of an issued scope were re-sent (N1, fixed: an issued version is never
  staged); three local-copy loss cases (fixed; `pickLocalCopy` is a tested pure function).
- Security: one conflict entry per lost claim (updated in place), History list without the JSON,
  holder token in a header, History view reads stored JSON defensively. Not done, with reason:
  a pre-parse body cap for these routes; nginx already caps every request at 50 MB
  (`sorento_crm_frontend/nginx.conf:29`), the bound every existing JSON route relies on.

## Browser pass (cloud sandbox, seeded empty DB, 10 Nov)

Sidebar from `/`: Project Sales > Projects > project > Proposals > Add a proposal. Typed Your Ref
and Subject: "Saved 6:54 AM", Discard draft, no Cancel, "Numbered on save". Typed and clicked
Projects in the sidebar within the debounce: the private draft held the value; reopening Add a
proposal showed it. Save numbered it BP/Q/0001 (History Version 1). Second user opened the same
edit page: the first tab locked ("Opened in another tab / by Ben Test at ..."), Save off, Reload;
the reverse direction kept the locked tab's text as History Version 2 ("Not saved: opened in
another tab"). The read page showed "Unsaved draft, last edited ... by Aina Test." with Continue
editing. The second user's edit page was opened by URL (a second tab of the same link).
