# PLAN: AGENTIC-KNOWLEDGE - ask the agent about documents uploaded in Resources (HR handbook, product knowledge)

Status: CARD v1 filed for the owner (31 Oct 2026). No code. Track: L (migration, new access rule, new agent tool).
UAC (`agentic-knowledge-acceptance-criteria.md`) is written after the owner answers K1-K5.

Owner, 31 Oct ~13:10: "what's next for our agentic? I want to upload some Sorento HR policy for users to ask, or
some product knowledge... we don't have RAG on documents, right?"

Short answer: right. We have the vector store and the search, but no document's CONTENT is ever read into it.
Attachments are embedded as a label card (file name, description, folder, linked entity), never their pages.

## What exists today (verified on 938a7fac)

| Piece | Where | State |
| --- | --- | --- |
| Vector store | `EmbeddingDocument` / `EmbeddingChunk` (`app/models/embeddings.py:71`, `:108`), `Vector(1536)` `:126` | Works. One chunk row per model (`model_name`). |
| Embedded sources | `RECORD_KEEP_SET` (`app/services/embedding_settings.py:38`): attachment, promotion, certificate, form, product_spec, project | No document content source. |
| Chunking | `embedding_chunk_size` 900 / overlap 120 chars (`app/config.py:316-317`) | Character chunks, no page number. |
| Attachment embed | `embedding_worker.py:208-233` | Name, description, path, entity, fixed intent keywords. Never the file. Stamped `visibility_scope: "customer"` (`:230`). |
| Text extraction | `document_extraction.py` (PyMuPDF `:169`, page render + vision reader `:356`) | Only for PO / delivery intake. No DOCX. |
| Upload | `api/v1/resources/attachments.py:800` (single), `:1307` (bulk) | Stores to S3/R2, optionally calls the n8n webhook (`AttachmentType.triggers_n8n_webhook`). |
| Search | `EmbeddingReadService.search_current` (`embedding_service.py:250`) | Company-scoped (`_embedding_company_filter` `:54-79`, applied `:290-294`); filters neither attachment type nor audience. |
| Consumers | n8n `/external/rag/search` (`api/v1/external/rag.py:45`), fuzzy resolver, project registration | None is the agent. |
| Agent tools | `chatbot/agent/tools.py:61-74` (report, stock, incoming, PO, orders, resolve, products) | No document tool. |
| Embedder | `DEFAULT_EMBEDDER = ("openai", "text-embedding-3-small")` (`embedding_settings.py:11`); Gemini path exists (`provider_for_model` `:43`, `gemini-embedding-001` truncated to 1536, `llm_provider.py:1097-1103`) | LOOKUP-EMBED-CENTRAL (merged, PR #1967) made the embedder ONE setting with a dual-write + 100% guard switch to gemini. |

The gap that matters for HR: every embedded record is `customer` visibility and the search does not filter by type
or audience. Putting a handbook into today's store would make it findable by the dealer bot. That is the first thing
this lane closes.

## The flow, end to end

```
Resources upload (type = "HR Policy" / "Product Knowledge", flagged "AI can read")
  -> worker job on the existing `media` queue: extract text per page
       PDF with a text layer: PyMuPDF page text (free, instant)
       scanned PDF page (no text layer): the existing vision reader (document_extraction.py) - OCR via Gemini
       DOCX: python-docx paragraphs; page = heading section (DOCX has no fixed pages)
  -> page-aware chunks: ~900 chars, never across a page break, each chunk carries {file, page, heading}
  -> new embed source `knowledge` in the keep set, embedded with the Embeddings setting's model (gemini)
     audience stamped from the attachment TYPE: staff | dealer | end_user (not the hard-coded "customer")
  -> agent tool `crm_knowledge_search(question)`: top passages the CALLER may see, each with
     {document title, page, passage, similarity}; nothing below the similarity floor
  -> agent answers ONLY from returned passages, cites "(Employee Handbook p.12)"
  -> nothing relevant / unclear / policy exception -> "I don't know this one, I'm passing it to HR"
     via the existing escalation route (the hand-off the bot already does; barred contacts get the
     existing barred reply, escalation_control.py)
```

Owner direction "empower the model with more tools instead of hard coding": this is one more tool in the same
registry, not a new lane or router branch. The model decides when to call it; the tool decides what the caller may see.

## Who may see what

Access is decided by the attachment TYPE (one new column `ai_audience` on `attachment_types`, values below), then
narrowed by what already exists. The tool applies it inside the query, so a passage the caller may not see never
reaches the model at all.

| Audience on the type | Staff Console agent | Dealer on WhatsApp | End user on WhatsApp | Example types |
| --- | --- | --- | --- | --- |
| `off` (default, every existing type) | no | no | no | Delivery Orders, POs, everything today |
| `staff` | yes, if the user holds `resource.attachments.view` | no | no | HR Policy, Employee Handbook, SOPs |
| `dealer` | yes | yes, if the contact's grant includes the type (`contact_attachment_access.py:125` `visible_type_ids`) and the file's `access_levels` has `dealer` | no | Product Knowledge, Installation Guide, Dealer Warranty Terms |
| `public` | yes | yes (same file-level check) | yes, if `access_levels` has `end_user` | Warranty Policy (BRD #12) |

Plus, always: company scope (`_embedding_company_filter`); `is_shared` types are visible to every company as today.
Default `off` means nothing already uploaded becomes readable by the AI until an admin ticks it on a type.

## Example Q&As (illustrative wording; no real Sorento content is in this public repo)

1. Staff, Console, type "Employee Handbook" (`staff`):
   - Q: "How many days of annual leave do I get after 3 years?"
   - A: "From year 3 to year 5 you get 16 days of annual leave (Employee Handbook, p.14, Leave Entitlement)."
   - Q: "Can I carry forward 10 days to next year?" (handbook says max 5, with HOD approval for more)
   - A: "The handbook allows up to 5 days carried forward (p.15). More than that needs HOD approval, which the
     handbook does not detail, so I'm passing this to HR." -> escalation to HR.
2. Dealer, WhatsApp, type "Product Knowledge" (`dealer`):
   - Q: "Can the Sorento XYZ basin mixer work with a solar water heater?"
   - A: "Yes, rated up to 85 C inlet (XYZ Product Guide, p.3)." If the guide is silent:
     "I couldn't find that in our product guide, I'm passing it to your salesperson / marketing."
3. Refusal, Console: Q "What's the company policy on crypto investments?" -> no passage above the floor ->
   "That isn't covered in the documents I can read. Want me to pass it to HR?" No invented answer.

## Gemini and the existing OpenAI vectors

LOOKUP-EMBED-CENTRAL already settled this: the embedder is ONE setting (System Settings > Embeddings), records
dual-write during the switch and search moves to the new model only at 100%, old rows are kept (owner N2-N5, 29 Oct).
`knowledge` joins that keep set, so it follows the same setting. Two vectors from different models are never compared:
every chunk row carries `model_name` and `search_current` filters on it (`embedding_service.py:276-281`).
New content is written with the setting's model (gemini-embedding-001, 1536 dims, same column, no schema change);
during a live switch it is also written with the current search model, exactly like the other sources (see K4).

## Phases

- **P1 - staff-only HR handbook in the Console agent.** `ai_audience` column + type form checkbox/select (Resources
  type settings, no new screen), extraction job (PDF text + vision OCR fallback + DOCX), page chunks, `knowledge`
  source with audience filter in `search_current`, `crm_knowledge_search` tool for staff, answer-only-from-source
  rule + HR hand-off, per-document status ("Read by AI: 42 pages, 3 OCR'd" / "failed: page 7") on the attachment
  detail and the existing Embeddings admin. Gold eval set for the handbook.
- **P2 - product knowledge for dealers on WhatsApp.** Same tool exposed to the chatbot agent for contacts, with the
  contact grant + `access_levels` check; hand-off goes to the salesperson / marketing; `public` audience for the
  Warranty Policy (BRD #12). Gold set per product document.
- Later, named not built: website sync of the Warranty Policy (BRD #12 "reflected within 24 h") and SLA suggestion
  grounding (BRD #30) both reuse the same tool; build when those lanes start.

## Cost (prices UNVERIFIED, check the Google price page before quoting)

- Embedding: gemini-embedding-001 ~USD 0.15 per 1M input tokens. A 60-page handbook is ~30k tokens -> under
  USD 0.01 per full re-read. 100 product documents of 20 pages -> ~USD 0.15 once.
- OCR for scanned pages: one vision call per page on the reader model (Gemini Flash class) ~USD 0.001-0.003 per page.
  Only pages with no text layer pay this.
- Per answer: one query embedding (negligible) + ~5 passages (~1.5k tokens) added to the agent's turn ->
  ~USD 0.0005-0.002 extra per question on a Flash-class model.
- Storage: ~1 chunk per 900 chars -> a 60-page handbook ~150 chunks, a few MB of vectors.

## Eval plan

- Per document: a gold file of 20-30 Q&As written by the document owner (HR / marketing), each with the expected
  page. ~1/3 are NOT in the document (must refuse + hand off), a few are near-misses (carry-forward above).
- Scored automatically with the existing agent eval harness pattern (`PLAN-ai-assistant-evals-guardrails.md`):
  retrieval hit (expected page in top 5), answer correct (LLM judge against the gold answer), citation present and
  correct, refusal on out-of-document questions, zero leakage (a dealer-context run over the HR gold set must return
  nothing, a hard fail).
- Bar to ship P1: retrieval hit >= 90%, correct-or-refused >= 95%, 0 hallucinated policy answers, 0 leaks.
- Gold files live outside the public repo (crew eval state), like the EEM gold set; only the scorer is committed.

## Questions for the owner (K1-K5)

- **K1 - Who decides what the AI can read?** (a) a setting per attachment TYPE (`ai_audience`: off / staff / dealer /
  public), (b) a tick per uploaded file. Recommendation: (a), because HR uploads a new handbook version without
  having to remember a tick, and the type already carries every other rule (shared, direct access, n8n).
- **K2 - Where does staff ask in P1?** (a) the Console agent only, (b) also the in-app AI bubble on every page.
  Recommendation: (a) first, because it is where the tools live today; the bubble reuses the same tool later.
- **K3 - Who gets the hand-off when the handbook doesn't answer?** (a) a named HR person/group set on the type
  ("Escalate to"), (b) the existing escalation queue with a "HR" label. Recommendation: (a), one column next to
  `ai_audience`, so marketing questions go to marketing and HR to HR without a routing table.
- **K4 - During the gemini switch, write knowledge chunks with both models like the other sources, or gemini only?**
  (a) same as the keep set (both until 100%), (b) gemini only and search knowledge with gemini even before the
  records switch completes. Recommendation: (a) if prod has not finished the switch, because one rule for every
  source is simpler and the extra OpenAI cost is cents; moot if prod already searches gemini.
- **K5 - Scanned PDFs:** (a) OCR them with the vision reader (cost per page, shown on the file), (b) refuse and ask
  for a text PDF. Recommendation: (a), because HR handbooks are often scanned signed copies, and the reader exists.

No new screen is needed: the type setting lives on the existing Resources attachment-type form, document status on
the attachment detail and the existing Embeddings admin. So no mock in this card.
