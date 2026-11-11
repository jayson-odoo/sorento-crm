# PLAN: PO-EXTRACT-LIST-FIX (customer PO upload: "'list' object has no attribute 'get'")

Status: in progress (small fix track: < 300 lines, no migration, no auth/RBAC change, no new ingest surface)
Lane: crew/po-extract-list-fix. Size S.

## Journey

Project Sales > project > PO tab > "Upload a PO document" > "Upload a customer PO" with a real
customer PDF (22 pages). Result: "This document could not be read: 'list' object has no attribute
'get'". The user cannot act on that sentence and the document is not read at all.

## Cause (measured in code, confirmed by repro below)

- `document_extraction.extract_document` asks every page for `response_format={"type": "json_object"}`
  only (`sorento_crm_backend/app/services/document_extraction.py:424`). JSON mode guarantees JSON, not
  an object: Gemini's `responseMimeType: application/json` (`llm_provider.py:1812`) will return a
  top-level array. `_parse_json` (`document_extraction.py:224`) hands back whatever `json.loads` gives.
- `persist_pages` then calls `data.get("header")` on that list
  (`sorento_crm_backend/app/services/project_po_intake_lifecycle.py:644`). The raise is outside the
  `try` around `extract_document` (`project_po_intake_lifecycle.py:524-535`), so it escapes
  `run_extraction`; the RQ task's last-resort `_mark_failed` writes the raw `str(exc)` into
  `extraction_error` (`sorento_crm_backend/app/tasks/project_document_tasks.py:77-80,116`), and the FE
  shows it verbatim. One page in a list shape fails the WHOLE document, against the module's own rule
  "a page that fails does not fail the document".

## Fix

1. Structured output at the source: the PO reader sends the page shape as a JSON schema
   (`json_schema=`, already supported natively by OpenAI strict mode `llm_provider.py:510` and Gemini
   `responseSchema` `llm_provider.py:1806`), so the model is constrained to ONE object with `header`,
   `lines`, `annotations`. The schema mirrors the `po_extractor` prompt's own shape
   (`ai_prompt_registry.py:701`) plus the printed-total keys `persist_pages` reads.
2. Shape check at the boundary, for an answer that still is not an object (older model, provider
   without schema support, fenced answer): an array holding one page object is that object; an array
   of several page objects or anything else marks THAT PAGE failed with a plain sentence; the rest of
   the document is still read.
3. No Python message on screen: an unexpected error after the read gives a plain sentence the user can
   act on ("Read it again" / enter lines by hand), the exception goes to the log only.

## Tests (red first, synthetic fixture, no real customer data)

- page answer is a list of one page object -> lines persisted, version done.
- page answer is a list of several page objects -> that page failed with a plain reason, other pages read.
- page answer is a bare list of line objects / scalar -> page failed, plain reason, no crash.
- unexpected error in persist -> version failed, `extraction_error` has no Python text.
- the PO reader passes a JSON schema whose top level is an object with header/lines/annotations.

## Repro / confirm

Owner PDF lives outside git (`crew/state/files/PO-EXTRACT-LIST-FIX/owner-po.pdf`), never committed.
One in-process run against the dev Gemini key (ledger line before and after, cap USD 0.20), reporting
only page shapes, PO number present yes/no and line count.
