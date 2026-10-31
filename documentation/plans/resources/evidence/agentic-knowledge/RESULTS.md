# AGENTIC-KNOWLEDGE P1: browser and agent verification

Date: 31 Oct 2026. Branch claude/agentic-knowledge-doc-rag-mirs78. Tool: agent-browser, session "akn", headless, dev frontend on :3000, backend :8000, worker on the knowledge queue. Viewports 1280 and 375. No implementation code was changed and nothing was committed.

## Setup (seeded outside the repo)

- Team HR (company Sorento), attachment type "Employee Handbook" (pdf,docx), a second type "Plain Memo" left at Off.
- File (a) Leave Policy.pdf: produced by knowledge_service.read_attachment with fake fetch (4 page PDF: 3 text pages, 1 blank), fake OCR and fake 1536 float embed, so 4 real knowledge chunks exist. The row's display figures were then set to 42 pages, 3 OCR pages, cost 0.006 as briefed (a real read of that PDF gives 4 pages, 1 OCR page, 0.002).
- File (b) Dress Code.pdf: seeded Failed. Saving the type as Staff only queued it (correct: never read or failed files are queued), the worker ran it and it ended Failed with a readable S3 error, so (b) shows that error rather than the seeded text.
- File (c) Parking Memo.pdf: type Plain Memo (Off), status null.
- Environment fixes needed to browse at all (data only, not lane defects): the seeded browse admin has a .test email that the login endpoint rejects with 422, so I made a second superadmin with a valid email; tenant_modules was empty so the frontend sidebar hid every module, so I enabled the catalogue modules for the default tenant; my first HR team had no company so the Escalate to list was empty until I set it to Sorento.

## Results

| Step | Result | Evidence |
|---|---|---|
| 1a. Types list, edit opens | PASS | 01-types-list-1280.png, 02-type-edit-1280.png |
| 1b. "AI can read" offers Off, Staff only, Dealers, Everyone | PASS | 03-ai-can-read-options-1280.png |
| 1c. "Escalate to" offers HR and is clearable (Clear selection button once set) | PASS | 04-escalate-options-1280.png, 05-type-form-filled-1280.png |
| 1d. Save Staff only + HR (PUT 200), reopen: both persist | PASS | 06-type-saved-1280.png, 07-type-reopened-1280.png |
| 1e. 375px: modal not clipped, no horizontal overflow, dropdown fully visible | PASS | 08-type-modal-375.png, 09-type-ai-options-375.png |
| 2a. Files list (sidebar Resources > Files) opens a file in a modal | FAIL, see D1: the modal has no "Read by AI" row | 10-files-list-1280.png, 11-file-a-1280.png |
| 2b. File (a) detail page: "Done, 42 pages, 3 read by OCR (est. USD 0.006)" and Read again | PASS (page reached by URL, see D1) | 12-file-a-detail-page-1280.png, 16-file-a-375.png |
| 2c. Read again on a recent done row: POST ai-read returns 202, toast "Queued for reading", status Queued | PASS | 13-read-again-click1-1280.png |
| 2d. After the worker ran: Failed with S3 error, Read again returns (no S3 here, expected); the 4 knowledge chunks stayed intact | PASS | 14-after-worker-failed-1280.png |
| 2e. Read again while the row is freshly queued: 409, toast "This file is already being read." | PASS (row set to queued in the DB while the page still showed the button, i.e. a second tab; the UI hides the button while Queued, and the job finishes in under a second here, so there is no other way to hit it) | 15-read-again-409-1280.png |
| 3. File (b): Failed, readable error text, Read again; at 375 wraps without clipping | PASS | 18-file-b-failed-1280.png, 17-file-b-failed-375.png |
| 4. File (c): no "Read by AI" row | PASS | 18-file-c-off-1280.png (375 capture: 17-file-c-off-375.png) |
| 5. No UUIDs in visible text on the types page and the three detail pages (regex over page text, 0 matches each; ids appear only in the address bar) | PASS | scripted check |

Console and errors check: no page errors recorded in the session.

## Agent check (no LLM)

Script: tools.dispatch for crm_knowledge_search with a context for the superadmin, knowledge_service._default_embed patched to return the same fake vector, type set to Staff only, company scope stamped on the session as the agent does.

- Passages returned (status ok), best first, all similarity 1.0:
  - Leave Policy, page 1: "Annual leave: every employee gets 14 days of paid annual leave per year..."
  - Leave Policy, page 2: "Sick leave: 14 days paid sick leave with a medical certificate..."
  - Leave Policy, page 3: "Overtime: overtime is paid at one and a half times the hourly rate..."
  - Leave Policy, page 4 (the OCR page): "Probation: new hires serve a three month probation period..."
- handoff_teams: ["HR"].
- A user without resource.attachments.view, via knowledge_service.search: status "denied", no passages, no teams.
- Same dispatch with the type switched back to Off: status ok, 0 passages (audience is read live).
- Same dispatch on a session with no company scope: ok, 0 passages (fail closed, as designed).

## Defects and observations

- D1 (UI reachability, blocks AC-K11 as a user journey): the "Read by AI" row and the Read again button exist only in the standalone detail page, sorento_crm_frontend/app/(protected)/resource-management/attachments/components/AttachmentDetail.tsx:449-470 (page /resource-management/attachments/<id>). That page has no sidebar entry (the Resources group lists Files, Trash and Attachment Types) and the Files drive, the primary place staff open a file, uses AttachmentDetailModal.tsx, which has no ai_read handling at all (grep finds none). A user clicking through the sidebar never sees the row. The only in-app links to the detail page are AttachmentBrowser.tsx:433 (its own page, also not in the menu) and StockBalanceGrid.tsx:398. I reached the page by URL, which departs from the sidebar-only rule, and I say so here. Fix options for the coder: add the row to AttachmentDetailModal, or point the Files drive rows at the detail page.
- D2 (minor, wording): a failed read shows the raw backend configuration message "S3 configuration incomplete: set the following in the backend environment: AWS_S3_BUCKET_NAME" to any staff viewer. It is readable and expected without S3 here, but it names a server environment variable; knowledge_service._readable_error (knowledge_service.py:259) only redacts key fragments. Consider a fixed sentence for storage configuration errors.
- D3 (observation, not lane code): the Read by AI row does not poll, so a page opened as Queued keeps saying Queued after the worker finishes until reloaded. Matches the design as built; noted because the job here finishes in 0.2 s.
- Note: the open-modal "Escalate to" list shows only the HR option with no explicit "No team" entry; clearing is through the clear button, which works.
- Note: upload-activity returned a 500 once while the browse admin had a non-UUID user id (an artifact of the seed style); it returned 200 after I recreated the admin with a normal id. Not related to this lane.

## Verdict

Step 1: PASS. Step 2: PASS on the detail page, FAIL on reachability (D1). Steps 3, 4, 5: PASS. Agent check: PASS.

## Re-check (31 Oct 2026, HEAD 53233cec, session "akn2")

Same stack, sidebar navigation only (Resources > Files, Resources > Attachment Types), 1280 and 375, no implementation code changed, nothing committed. Console and page errors: none recorded. The session was closed by name.

### Environment finding (not a lane defect)

The uvicorn on :8000 had been started at 08:20 without `--reload`, before commit dec498d1 (08:39) added the "file unchanged" rule to `knowledge_service.read_block_reason`. Against that stale process Read again on file (a) returned 202 instead of 409, and a read run by the old code stored a text-hash in `source_hash` instead of `file_hash`. I restarted uvicorn with the same command and env file (SORENTO_ENV_FILE=.env.dev-browse, 127.0.0.1:8000, log /tmp/akn2_uvicorn.log) and re-aligned file (a)'s stored hash with a data-only script (/tmp/scripts/akn2_reset_a.py). All results below are against HEAD code. The worker (started 08:50) is after dec498d1 and was not touched.

### Results

| Step | Result | Evidence |
|---|---|---|
| D1. Files (sidebar), modal for (a) Leave Policy.pdf: "Read by AI" row "Done, 42 pages, 3 read by OCR (est. USD 0.006)" and Read again | PASS | 30-file-a-modal-1280.png |
| D1. Modal for (b) Dress Code.pdf: "Failed" with the error text and Read again | PASS | 32-file-b-failed-1280.png |
| D1. Modal for (c) Parking Memo.pdf (type Off): no "Read by AI" row and no Read again | PASS | 37-file-c-off-1280.png |
| D1 at 375: rows wrap, no horizontal overflow (document and dialog scrollWidth equal clientWidth) for (a), (b), (c) | PASS | 38-file-a-375.png, 39-file-b-375.png, 40-file-c-375.png |
| D2. Read again on (b): POST ai-read 202, worker runs, error now reads "The file could not be downloaded from storage." with no AWS or S3 config text | PASS | 33-file-b-read-again-1280.png, 34-file-b-new-error-1280.png |
| D3. Row Processing in the open modal, flipped to failed in the DB, modal showed Failed on its own with no reload (first read after 2 s, limit 10 s) | PASS, with the caveat below | 35-file-b-processing-before-1280.png, 36-file-b-failed-after-1280.png |
| 4. Read again on (a) (done, file hash unchanged): POST ai-read 409, error toast "This file is already read and has not changed.", row stays Done | PASS (after the restart above) | 31-file-a-read-again-409-1280.png |
| 5a. Non-admin viewer@example.com, role "AKN Types Viewer" with only resource.attachment_types.view: sidebar shows only Resources > Attachment Types, list loads (GET 200), Add, Edit and Delete controls count 0 | PASS | 41-types-viewer-view-only-1280.png |
| 5b. Same role plus resource.attachment_types.edit (after a reload): Edit pencil on both rows, Delete and Add still absent | PASS | 42-types-viewer-edit-1280.png |
| 6. No UUIDs in visible text (regex over innerText): the three file modals, the page behind them, and the viewer's types page, 0 matches each | PASS | scripted check |

D3 caveat: the real job finishes in about 0.2 s, so Processing could not be held long enough for the worker itself to flip it while the modal was open. I set the row to Processing, reopened the modal (it showed Processing), then set it to failed from a script. That proves the modal polls and redraws on its own; it does not prove a worker-driven flip. The poll lives in AttachmentDetailModal.tsx:858-859 (5000 ms while in flight).

### Seeding for step 5

Via /tmp/scripts/akn2_viewer.py: a `user_roles` row (slug akn-types-viewer), a `users` row (viewer@example.com, ACTIVE, bcrypt password in /tmp/akn_viewer.env), a `user_role_assignments` row, and `user_role_permissions` rows pointing at the existing `user_permissions` slugs. Nothing else was needed for the sidebar: the Attachment Types leaf is gated only by `resource.attachment_types.view` (menu.config.tsx:876) and the Resources group by the `resources` module, which the earlier pass had enabled. No `user_companies` grant was required. Permission changes show after a page reload with no new sign-in.

### Defects

None new in lane code. The earlier D1, D2 and D3 are closed as described above. One thing to be aware of: a dev backend started without `--reload` serves stale code after a fix commit, which produced a false FAIL on step 4 until restarted.

### Data left behind

Files: (a) Done with its original display figures and hash aligned; (b) Failed with the storage-download sentence; (c) untouched. Added: the viewer role and user above, with view and edit permissions.
