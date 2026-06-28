# AI Bubble — Field Answerability + Fan-out (what users can ask)

**Status:** Validated 2026-06-28 (live LLM). Companion to `PLAN-bubble-record-context-and-guides.md`.

## The model (two data sources, both reach the answer)

The bubble can answer about a record the user is viewing from **two** sources, merged in the render path:

| Source | Carries | Reaches answer via |
|--------|---------|--------------------|
| `page_snapshot.visible_text` (≤6000 chars, DOM of the current screen) | **Every on-screen field** — purpose, dates, line items, addresses, remarks, prices, status pill, … | Injected into the agent loop **and** the record-context render path. Universal — works on ANY detail page. |
| Record-context **assembler** (`record_context_service.py`) | **Off-screen structured data** — SLA tab (tier/due/breach/lead-time), audit log/history, approval decision, who/when/lead-time | The deterministic pre-route, for the 4 form-SLA entities only. |

**Key consequence:** a detail page whose data is all on-screen needs **no assembler and no entity registration** — `visible_text` already answers it through the agent loop. Assemblers exist only to surface data the user would have to switch tabs / lacks permission to see.

## What users can ask (the taxonomy — drives test cases)

Per record, validated grounded for the 4 forms:
1. **Any visible field** — "what is the purpose / expected delivery date / customer / product code / defect / line items / price". → `visible_text`.
2. **Status** — "what's the status" → the single combined display status (PR/SF combine lifecycle + approval to match the pill).
3. **Decision** — "who approved/rejected this and why" → assembler `approval` / on-row reject cols.
4. **Lead-time** — "how long to decide / respond" → assembler lead-times.
5. **SLA** — "what's the SLA status / which tier / is it breached / who's it assigned to" → assembler `sla` (the SLA Tracking tab).
6. **Audit** — "show the history / who changed it last" → assembler `audit_trail`.
7. **Response** (stock inquiry) — "who responded / what did purchasing say" → assembler `response`.
8. **Next step / process** — "what should I do now / process flow for this" → guide-grounded by current status.

Anti-overfit: these are **categories of intent**, validated by paraphrase robustness, not memorized sentences. The classifier is a general semantic judgment; `visible_text` answering is inherently field-agnostic.

## Validation (live, service-level e2e)

- `tests/test_field_answerability_eval.py` (gated `RUN_LLM_EVALS=1`) — for PR / stock_inquiry / complaint: real visible fields + SLA + audit, asserts the **real value** appears (grounded, never hardcoded). 3/3 live.
- Manual battery (scratchpad): 15/15 field+SLA+audit across PR/SI/complaint; agent-loop-only visible-field answering proven on a product page (price/brand/category/status) with **no entity, no assembler**.

## Fan-out classification

| Entity | Detail page | Off-screen data? | Action |
|--------|-------------|------------------|--------|
| complaint, stock_inquiry, purchase_request, sponsorship_form | yes | **yes** (SLA tab, audit, approval) | ✅ assembler adapters (done) |
| products | yes (tabs incl. Audit) | audit is a tab the user can open | `visible_text` covers main fields; audit via the tab. No assembler needed. |
| packing_list | yes (flat) | no | `visible_text` — already covered |
| attachments | yes (Linkages tab) | no (linkages visible) | `visible_text` — already covered |
| spo_allocation (SPO) | yes | no | `visible_text` — already covered |
| grn (GRN) | yes | no | `visible_text` — already covered |
| stock | yes (`[productId]/[warehouseId]`, ledger inline) | no | `visible_text` — already covered |
| promotion | yes | no | `visible_text` + `crm_marketing_promotions_list` |
| forms | yes | no | `visible_text` + `crm_forms_management_forms_list` |
| **delivery_orders** | — | — | **does not exist** as an entity — clarify (Orders? incoming shipments?) |

**Conclusion:** the fan-out needs **no new per-entity backend code**. `visible_text` (shipped) makes every detail page's fields answerable; existing MCP catalog tools cover list/cross-record questions. Optional polish (not required): register `RecordEntityRegistrar` on the non-form detail pages only if we later add off-screen data worth an assembler — otherwise it just costs a wasted assemble attempt per turn.

## Open
- `delivery_orders` entity identity — confirm what the user means.
- Optional: if the agent loop ever mis-routes a clearly on-page question to a catalog tool, add a nudge to prefer `visible_text` for "this record" questions. Not observed for plain field questions.
