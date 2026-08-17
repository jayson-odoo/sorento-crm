# AUDIT - Project Sales vs the Sorento Process Flow spec

> **Table names in this document predate the schema move.** On 2026-08-15 the projects
> module's 47 tables moved into a dedicated `projects` Postgres schema and the 34 that
> carried a `project_` prefix dropped it: `project_leads` is now `projects.leads`,
> `project_quotation_lines` is `projects.quotation_lines`, and so on. The 13 unprefixed
> ones only changed schema. Nothing else in this document changes. See
> [ADR-0011](../adr/0011-project-sales-tables-live-in-the-projects-schema.md) and
> `documentation/plans/PLAN-projects-schema-move.md` for the full mapping.

**Date:** 2026-08-12. **Auditor:** Fable, at the client's request, after the main merge.
**Inputs:** `Sorento Project Management Process Flow.pdf` (6 pages, read in full),
`products template( sanitaryware).xlsx`, `Cabana Elmina- nadi cergas R2.xlsx`, the code on
`feat/project-lead-to-so` at 392a0bd3b, and the running app on :3010/:8010.

## 1. Requirements fulfilment (the PDF, stage by stage)

| Spec | Built | Where | Verdict |
|---|---|---|---|
| Single registration point, clash prevention | Trigram clash preview at typing time + block/surface thresholds in settings | `previewClashes`, `project_clash_*_threshold` | FULFILLED |
| Registration fields (developer parent + SPV, title, location, architect, contractor, est. value, brands multi-select, salesperson, launch date) | All present; architect/contractor are PARTIES (reused across projects, which is what makes architect intelligence possible) | `projects`, `project_parties`, `ProjectSalesProfile` | FULFILLED |
| Reassign a neglected project; system prompts for updates | Staleness ladder (0-3) on a scheduler sweep with notify, takeover requests with manager decision | `project_staleness_service.sweep`, `create_takeover_request` | FULFILLED |
| Multiple quotations per project (scopes), versioned, per-line image/desc/price/qty/unit type | Scopes on one document, versions frozen on revise, lines carry all five plus band/rate-only/tech-spec - matches the Cabana workbook column for column | quotation stack | FULFILLED |
| Non-standard SKU alert | Built AND (since 2026-08-12) judged on the spot. CAVEAT: dormant on real data until yesterday - no quotation had a series bound because the picker lived on an orphaned page. Fixed (Edit scope on the document screen). | `is_in_series`, line-verdict endpoint | FULFILLED, with a delivery lesson |
| Below-minimum price alert (warn salesperson + alert management) | Floor rules + series floor precedence; breach notifies management only | `resolve_floor`, `_notify_breaches` | FULFILLED |
| Sample tied to quotation VERSION; quotation is SoT | FK to version; new sample refused against a superseded version | `project_samples.quotation_version_id` | FULFILLED |
| Final negotiation critical status, management engaged | `is_critical` flag + filter; notify wiring exists | `set_critical` | FULFILLED (verify the notify fan-out in UAT) |
| Sponsorship: items, cost, date, per-project + per-year rollup, sponsorship-to-PO conversion | Panel + rollup endpoint | `SponsorshipsPanel`, `getSponsorshipRollup` | FULFILLED; conversion metric present in rollup, verify numbers in UAT |
| PO: source, number, date, amount, linked quotation version | All on `project_purchase_orders`; binding never silently moved | intake + `_bind_quotation_version` | FULFILLED |
| PO validation: model + unit price must match quotation, qty may differ, auto-flag | `model_mismatch` / `price_mismatch` per line, computed against the BOUND version, qty deliberately unchecked | `_apply_match_flags` | FULFILLED, exactly as specified |
| Dashboard: totals, pipeline value, conversion, loss reasons, delivery forecast (launch+lag), per-salesperson | All in `project_forecast_service` (pipeline/weighted/committed, year buckets, `by_salesperson`, `loss_reason_counts`, `conversion`) | `/reports/*` | FULFILLED |
| Brand intelligence: which brands win by location & budget band | NOT FOUND as a report. Brands are recorded per project; no location/budget-band cut exists. | - | **GAP** |
| Architect intelligence: which architects to prioritise | Party reuse + per-customer portfolio exist; no ranked architect report. | `customer_portfolio` | **PARTIAL** |

Verdict: the spec's six stages, both validation alerts, the PO match rules and ~90% of the
dashboard are built and traceable. Two intelligence reports (brand-by-location, architect
ranking) are the genuine unbuilt remainder.

## 2. Architecture and enterprise-grade assessment

**What is genuinely strong (keep, and hold as the bar):**

- **"AI proposes, arithmetic decides."** Nothing the vision model says about a number is
  believed until `qty x unit_price == amount` recomputes in Decimal. Validated on the real
  Buimaco PO to the cent (1,810,640.62; minus the pencilled cancellation = the quotation's
  1,805,907.02). This is the correct enterprise posture for AI-read financial documents.
- **Handwriting is never auto-applied.** Pencil becomes a proposed card; a person accepts;
  the acceptance is idempotent across re-scans (`dedup_key` = date + lines + text hash).
- **Version immutability + terminal states.** Confirmed versions never change; every
  extraction exit path writes a state and a sentence; a killed worker gets a verdict from
  the recovery service instead of a forever-spinner.
- **Shared extraction layer.** `document_extraction.extract_document` serves BOTH the PO
  reader and the schedule reader, prompts resolve through the versioned registry, usage is
  logged per call. This is real reuse, not copy-paste.
- **Isolation discipline.** All 24 project tables carry the company mixin or a documented
  inheritance reason; permissions registered in the one registry; every list uses the
  shared DataGrid contract; uploads use FileDropzone; previews use AttachmentPreviewModal.

**Where it falls short of enterprise grade:**

1. **`project_po_extraction_service.py` is a 2,391-line god-service.** Upload, storage,
   extraction lifecycle, fragment heuristics, annotation NLP, successor-PO linking, and the
   confirm write-through in one class. Each piece is well-commented, but the unit of change
   is the whole file. Split: intake lifecycle / annotation classification / confirm.
2. **Keyword NLP where the model should answer.** `classify_annotation` decides what a
   pencil note MEANS by English keyword lists (`_CANCEL_WORDS`, `"code" in blob`) and
   "last code-shaped token" regexes - stacked ON TOP of a vision model that already
   returns a `meaning` field. This violates the repo's own no-overfit-NLP rule. The
   classification belongs in the `po_extractor` prompt as schema-forced output (the
   semantic-parser doctrine), with the regexes kept only as recorded fallbacks. Kills
   ~200 lines and every future "the client wrote it differently" bug.
3. **Mock scenarios ship in the production bundle.** `POIntakeMocks.tsx` (673 lines) is
   compiled into the live page and activated by `?po_mock=` in the URL - on a screen that
   shows purchase-order money. Phase-1 leftover. Tests may keep it; the live page must not:
   gate the import out of production builds.
4. **Two editable-table paradigms in one module.** Quotation lines edit through the shared
   `InlineLineTable`; PO lines edit through a bespoke `CellInput`-inside-DataGrid hybrid
   that nothing else uses. This - plus chatty headings ("What the top of the document
   says", "What we read it as") against the system's terse label vocabulary, plus a
   "Version 2" pill where quotations use v1/v2 chips - is the "out of place" feel. The
   grids themselves DO follow the DataGrid contract; it is the vocabulary and the editing
   paradigm that drift.
5. **Money formatting exists three times** (`POIntakeMoney`, `SalesOrderMoney`,
   `QuotationsPanel.formatMyr`). One drifted implementation away from a cent disagreement
   on screen.
6. **SaaS scalability notes:** in-process TTL caches (signed-URL cache) are per-replica -
   fine today, revisit before horizontal scaling; multi-tenancy is stubbed repo-wide
   (`DEFAULT_TENANT_ID`) - a known platform gap, not a module one; page-per-LLM-call
   extraction is worker-side and fits the queue model.

## 3. The PO-reading fix list (ordered) - ALL FIVE SHIPPED 2026-08-12

1. Strip `POIntakeMocks` from the production bundle (URL-triggered mock data on a
   financial screen).
2. Move annotation classification into the extractor prompt (schema-forced), demote the
   keyword heuristics to fallback. One implementation of "what does this pencil note mean".
3. Converge the vocabulary: terse headings (Header / Lines / Handwriting), the quotation's
   version-chip strip, one shared money formatter.
4. Split the god-service into three modules along its own section comments.
5. Decide ONE editable-table paradigm for line editing (InlineLineTable is the system's),
   or explicitly document why PO lines are different (cell-commit-per-blur against an
   extraction that a person is reconciling IS a defensible reason - but it is currently
   undocumented).

Done: 1 (mocks deleted, isMock off the contract), 2 (the model classifies its own
handwriting; keywords are the fallback, pinned both ways), 3 (Header/Lines/Handwriting,
v1/v2 chips, one money renderer in _shared/lib/money with SalesOrderMoney the documented
arbitrary-precision exception), 4 (three mixins + a facade, name unchanged, 53 intake
tests green including the golden real-scan run), 5 (ADR-0008, authoring vs reconciling).

## 4. Delivery lesson worth keeping

The non-standard alert was "built and tested" for weeks while being OPERATIONALLY DEAD:
no quotation could bind a series because the only picker lived on a page nothing linked
to. Tests passed; the feature did nothing. The check that catches this class is the one
added yesterday - a test that STARTS where the user starts (sidebar in, not deep URL) -
and a periodic "is the feature's key column ever non-NULL in real data" probe.
