# PLAN: PO upload matching (PO-UPLOAD-MATCHING)

Status: behaviour card filed, waiting on owner answers (size M, LEAD pattern). No code yet.

## Problem (owner, 14 Nov, 134-line customer PO)

1. Products do not need a quotation, and matching never looks at one
   (`api/v1/projects/po_intake.py:112-160`, `services/project_po_intake_lifecycle.py:321-392`).
   Quotation is only used at Confirm for mismatch flags
   (`project_po_confirm.py:234`, `project_po_service.py:556-579`).
2. Matching is string rules only (`project_po_intake_lifecycle.py:917-1095`): exact code, a
   code-shaped token in the description, punctuation dropped, tokens reordered, truncated code
   completed. Brand words and customer prefixes defeat it ("SORENTO BBTSRTWC8518 -SH" vs
   `SRTWC8518-SH`). The description-token rule matched "40MM" (wrong).
3. Qty/UOM can come back empty; Confirm silently saves qty 1 (`project_po_confirm.py:264`).
4. "Document total" is the sum of the amounts read (no printed total is asked for:
   `project_po_reading.py:146-163`, lifecycle `recompute_totals` ~1217), but the banner says
   "the total printed on the document" (`POIntakeConfirmClient.tsx:405`).

## Behaviour card (filed as crew-ask)

See PR comment `crew-ask: behaviour card`. Copy kept here once answered.

## Reuse map (discovery)

| Need | Existing function | Verdict |
| --- | --- | --- |
| Exact code match | `ProjectPOIntakeLifecycle._resolve_product` lifecycle:917 | keep first tier (exact code) |
| Customer-remembered codes | `CustomerItemCodeMap` model `models/project_so.py:384`; `_remembered_codes` / `_remember_code` `project_schedule_service.py:1238, 2060` | lift into ONE shared helper used by schedule + PO |
| Catalogue shortlist (did-you-mean) | `entity_resolver.resolve_references(... alternatives)` `entity_resolver.py:5475`, as used by `ai_extract/extract_service.py:1261` | reuse as is for the shortlist |
| Quotation lines of the project | `project_po_service._quoted_line_for` / `_bind_quotation_version` (`project_po_confirm.py:290`) | reuse to pick the quotation version; read its lines |
| LLM structured call | `llm_provider` + prompt registry (`ai_prompt_registry.py`, `po_extractor` pattern, json_schema) | new prompt key `po_line_matcher`, same call path |
| Manual product pick on a line | lifecycle:1281-1294 (`set line product`) | extend: also writes the customer code map |
| Qty x price arithmetic | `arithmetic_ok`, `_computed_amount` `project_po_reading.py:283-305` | reuse |

## UAC / tickets

Written after the owner answers the card.
