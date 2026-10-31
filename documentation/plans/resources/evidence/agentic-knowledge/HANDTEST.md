crew-handtest: AGENTIC-KNOWLEDGE P1 (staff ask the AI about documents uploaded in Resources)

## URL
crew test copy

## Setup
- Apply the `crew-migration` SQL from the PR (alembic `akn_0001_knowledge`): adds `attachment_types.ai_audience` / `ai_escalate_team_id` and `attachments.ai_read_*`.
- Restart the Worker after checkout: there is a new `knowledge` queue (in `worker.py` QUEUES, so the default worker drains it).
- The test copy needs a working Gemini key on System > AI Assistant (embeddings use `gemini-embedding-001`; scanned pages use the document reader model) and working file storage (S3 or R2).
- Have a short text PDF ready, e.g. a 3 page "Leave Policy.pdf" whose page 2 says "Staff with 3 to 5 years of service get 16 days of annual leave." (no real HR content needed), and optionally a scanned (image only) 1 page PDF.
- Sign in as an admin. A core team named "HR" exists (User Management > Teams); create one if not.

## Steps
1. Sidebar: Resources > Attachment Types. Open "Employee Handbook" (create it with extensions `pdf,docx` if missing).
2. Set "AI can read" = Staff only and "Escalate to" = HR. Save.
3. Reopen the type and check both values stayed.
4. Sidebar: Resources > Files. Upload "Leave Policy.pdf" with type Employee Handbook.
5. Click the uploaded file in the list. Watch the "Read by AI" row in the file panel for up to 30 seconds without reloading.
6. Check the file panel: no Read again button on a Done file.
7. Upload the scanned PDF with the same type and open it (optional).
8. Open the in-app AI assistant side panel and ask: "How many days of annual leave do I get after 3 years?"
9. In the side panel ask: "What is the company policy on crypto investments?"
10. In the side panel ask: "How do I upload a packing list?"
11. Open the Chatbot Console (sidebar, System Management > Chatbot Console) for a contact linked to your own staff user, agent switch on, and ask the question from step 8.
12. Back in Attachment Types, set Employee Handbook "AI can read" = Off and save. Ask the step 8 question again in the side panel.
13. Sign in as a staff user WITHOUT Resources access (no `resource.attachments.view`) and ask the step 8 question in the side panel.

## Expected
1. The type form shows "AI can read" (Off, Staff only, Dealers, Everyone) and "Escalate to" (team list, clearable).
2. Save succeeds with a success toast.
3. "Staff only" and "HR" are shown on reopen.
4. Upload succeeds.
5. The row goes Queued -> Processing -> "Done, 3 pages" on its own (no reload).
6. No Read again button is shown (it appears only for Failed files).
7. Row ends "Done, 1 page, 1 read by OCR (est. USD 0.002)".
8. The answer says 16 days and cites the document and page, e.g. "(Leave Policy, p.2)".
9. The reply says this is not in the documents and to ask HR. No invented policy.
10. The reply gives the user guide steps (from the Outline guide), not a document passage.
11. Same answer as step 8, with the citation.
12. The reply says it is not in the documents (the file is no longer readable). No passage is quoted.
13. The tool is not offered: the reply does not quote the handbook.
