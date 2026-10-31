# UAC: AGENTIC-KNOWLEDGE P1 - staff ask the AI about documents uploaded in Resources

Plan: `PLAN-agentic-knowledge-31oct.md`. Owner answers 31 Oct ~14:55: K1 (a) audience per attachment TYPE,
K3 (a) hand-off team per type, K4 gemini only, K5 (a) OCR scans with cost per page shown, K6 two tools.
P1 scope: staff callers only (Console agent and the in-app side panel). Dealer / end-user callers are P2.

## Journey

HR opens Resources > Attachment Types, edits "Employee Handbook", sets "AI can read" = Staff only and
"Escalate to" = HR team, saves. HR uploads `Employee Handbook 2026.pdf` with that type. A few seconds later the
file's detail page shows "Read by AI: Done, 42 pages, 3 read by OCR (est. USD 0.01)". A staff member asks the
Console agent or the side panel "how many days of annual leave after 3 years?" and gets the answer with
"(Employee Handbook 2026, p.14)". Asked something the handbook does not cover, it says so and names HR.

## Acceptance criteria

### Type settings
- AC-K1 `attachment_types` gains `ai_audience` (text, NOT NULL, default `off`, one of off / staff / dealer / public)
  and `ai_escalate_team_id` (nullable FK to core `teams.id`, ON DELETE SET NULL). Every existing type reads `off`.
- AC-K2 The attachment type API returns both fields plus `ai_escalate_team_name`, and create / update accept them;
  any other `ai_audience` value is a 422.
- AC-K3 The Attachment Type form shows "AI can read" (SearchableSelect: Off, Staff only, Dealers, Everyone; default
  Off) and "Escalate to" (SearchableSelect over teams, clearable). Saved values reload on edit. 375px and 1280px.

### Reading a file
- AC-K4 `attachments` gains `ai_read_status` (null / queued / processing / done / failed / unsupported),
  `ai_read_pages`, `ai_read_ocr_pages`, `ai_read_cost_usd` (numeric), `ai_read_error`, `ai_read_at`.
- AC-K5 An upload (single and bulk) whose type's `ai_audience` is not `off` sets `ai_read_status = queued` and
  enqueues one read job on the worker's `media` queue. A type with `off` enqueues nothing and the status stays null.
- AC-K6 Changing a type's `ai_audience` from `off` to anything else queues every file of that type whose status is
  null or failed (at most 500 per save). Changing it to `off` queues nothing; those files stop being searchable
  at once (AC-K12), with no re-embed.
- AC-K7 PDF: each page's text layer is read. A page with fewer than 40 characters of text is sent to the existing
  vision reader as an image and transcribed (OCR); it counts in `ai_read_ocr_pages`, and
  `ai_read_cost_usd = ocr_pages x OCR_COST_PER_PAGE_USD` (a named estimate, shown as "est.").
- AC-K8 DOCX: paragraphs are read in order, with no new dependency; each Heading 1 / Heading 2 starts a new
  section, and the section number is the "page" and the heading is kept. Any other extension -> `unsupported`.
- AC-K9 Chunks are about 900 characters with 120 overlap, never cross a page, and carry
  `{attachment_id, page, heading}`. They are written as source_type `knowledge` with model `gemini-embedding-001`
  only (1536 dims). Re-reading a file replaces its previous knowledge chunks. Status `done` with pages / OCR count /
  cost, or `failed` with a readable error (no key fragments) and nothing half-written.
- AC-K10 `knowledge` is NOT in `RECORD_KEEP_SET`: `/external/rag/search` and every records reader never return a
  knowledge chunk, with or without a `source_type`.
- AC-K11 The attachment API returns the `ai_read_*` fields. The attachment detail page shows a "Read by AI" row only
  when the status is set: status, pages, OCR pages, est. cost, and the error when failed. Failed and done files
  show "Read again" (POST `/api/v1/resources/attachments/{id}/ai-read`, upload permission), which queues it again.

### Asking
- AC-K12 `knowledge_service.search(db, user_id, query, top_k=5)` returns passages
  `{document, page, heading, text, similarity}` only from files that: are of a type whose CURRENT `ai_audience`
  is staff / dealer / public (staff see all three in P1), still exist, and are inside the session's company
  scope (`_embedding_company_filter`). A caller without `resource.attachments.view` gets a refusal and no passages.
  Passages below `KNOWLEDGE_SIMILARITY_FLOOR` are dropped.
- AC-K13 The result carries `handoff_teams`: the distinct "Escalate to" team names of the readable types.
- AC-K14 Console agent: `crm_knowledge_search(query)` is in the agent `REGISTRY` (slug `resource.attachments.view`)
  and runs in process with the turn's linked user id (no MCP hop). Its schema is local, like `crm_products_find`.
- AC-K15 Console agent: `user_guides_read(query)` is in the agent `REGISTRY` and passes the permission check
  for any linked user (every agent caller is an active CRM user, `agent/access.py:47-76`). Its MCP call carries only
  `query`: no `contact_id` / `space_id` injected.
- AC-K16 Side panel: `crm_knowledge_search` is bound for a user holding `resource.attachments.view` and runs in
  process with the panel's staff user id (the MCP path cannot see the user: `X-MCP-Staff-User` is log-only).
- AC-K17 Both prompts (agent and panel) carry a KNOWLEDGE PROTOCOL paragraph, appended at runtime and idempotent
  on its header like USER GUIDE PROTOCOL: company policy / product document questions go to `crm_knowledge_search`,
  how-to-use-the-CRM questions go to `user_guides_read`, answer only from returned passages with
  "(document, p.N)", and with no passage say it is not in the documents and name the hand-off team.
  The agent also gets the USER GUIDE PROTOCOL.
- AC-K18 P1 hand-off is a named referral in the reply ("please ask HR"), not a ticket: the agent has no escalation
  route today and the panel never had one. A real hand-off arrives with AGENTIC-UNIFY / P2.

### Safety
- AC-K19 No HR passage reaches: an n8n `/external/rag/search` caller, an agent or panel user without
  `resource.attachments.view`, a user scoped to another company, or a file whose type is `off`.
- AC-K20 No UUID in the UI: team shown by name, attachment by file name.

## Out of scope (P2 or later)
Dealer / end-user callers on WhatsApp, real escalation ticket, website sync of the warranty policy, the MCP tool for
n8n, the eval scorer and gold files (they need HR's real handbook; P1's tests use a synthetic document).
