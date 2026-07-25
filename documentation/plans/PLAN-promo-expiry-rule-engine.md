# PLAN — Promotion expiry rule engine + compiled-PDF batch

**Status:** In progress — Phase 2. BACKEND LANDED (rule engine port, `/rule-facts`, conditions_json + validation, `_execute` filter + batch stamp, `PromotionsPdfService` + `generate_promotions_pdf` task + `POST /promotions/export/pdf`, `expiry_notify_batch_id` list filter; migration `301_promo_expiry_rule_engine`). FE + tests still pending. Branch `feat/promo-expiry-rule-engine` (off `origin/main`).
> Backend note: the promotions compile-PDF route lives at the existing backend mount `/api/v1/marketing/promotions/export/pdf` (FE `marketing-management` → `marketing` rewrite), not `/marketing-management/...` literally. Local-only: the dev DB's `alembic_version` held the pre-rename id `300_polymorphic_source_entity_id_uuid`; reconciled in place to `300_poly_source_entity_id_uuid` before applying 301 (no schema change, prod unaffected).
**Owner:** autonomous build (user grilled the design, then handed off).
**Grill outcome:** decisions locked below (§Decisions).

---

## Problem

The "Promotion expiry reminder" automation (`days_before_promotion_end` trigger, template `tpl-e7abadd8`) sends **every** expiring promotion to **every** recipient, ignoring each promotion's access level / brand. Marketing wants brand-segmented routing:

- promos with access level `sorento_*` **or** name containing "Sorento" → the Sorento owner(s);
- promos with access level `cabana_*` **or** name containing "Cabana" → the Cabana owner(s);
- generalized/configurable, not hardcoded to two brands.

Second ask: a "compile expiring promotions into one PDF" flow. Each promo links to attachment files (flyers). User lands on the promotions page (deep-linked from the reminder email to a *batch*), selects promos, Actions → "Compile PDF", gets one merged PDF to print (printer does N-up).

---

## Decisions (from grill)

1. **Segmentation lives in the backend** as a **general, reusable rule engine**, ported from `foundryx-shared-service/service_backend/app/rule_engine` (pure condition-tree evaluator + fact registry + validator + prose). Chosen over a promo-specific hack (user: "B — general engine").
2. **A "rule" is a `conditions_json` filter hosted ON the automation row** (faithful to FoundryX "rule = property of the consumer entity"). NOT a separate rules-with-recipients table.
3. **Recipients stay on the automation** (existing `recipient_config`, unchanged). Segmentation = **multiple automations**, each with its own `conditions_json` filter + its own recipients. "Sorento" automation filters Sorento promos → Sorento people; "Cabana" automation filters Cabana promos → Cabana people.
4. **Empty `conditions_json` = match all** → the existing single automation is unchanged until an admin splits it. Backward compatible.
5. **Rule engine wired to the promotion-expiry trigger only** in v1; engine stays generic so more triggers are additive.
6. **Match semantics = union** — a promo matching multiple automations is emailed by each (dedup by email is already per-automation in `_send_grouped`).
7. **Days stays on the automation** (`trigger_config.days_before`), **exact-day match** (`end_date == today + X`). Exact-day = natural anti-spam; NO `<= X`, no window, no daily repeat. Days is NOT a rule fact used for filtering (though exposed as a fact for completeness).
8. **Batch**: add `expiry_notified_at` + `expiry_notify_batch_id` to `promotions`. One batch per automation-run (stamp-first, mirrors product-discontinued). Reminder email deep-links to `?expiry_notify_batch_id=<id>`. Re-running an automation re-stamps a **fresh** batch (failure-recovery resend; prior failed email's link is moot).
9. **Compile PDF**: checkbox-select promos on the promotions page → async job via the existing **`user_downloads`** ("My Downloads") loop → RQ `generate_promotions_pdf` on the `imports` queue → **PyMuPDF (`fitz`)** merges **ALL** linked attachments per promo (PDF → append pages, image → full page, other types → skip + report) in **frontend grid display order**, attachment `sort_order` within a promo → `exports/promotions-pdf/{download_id}/…` → appears in My Downloads drawer.
10. **Rule builder UI = the full nested AND/OR `RuleBuilder`** ported from FoundryX (user: "A"), embedded in the Automation edit modal, shown only for triggers that expose a fact source.

### Known limitations (documented, accepted for v1)

- A promo matching two automations gets its `expiry_notify_batch_id` overwritten by whichever runs last; the earlier automation's email deep-link then may not include that promo. Brand filters shouldn't overlap. Single-column batch mirrors product-discontinued deliberately.
- Client-side rule-eval parity mirror (`lib/rule-eval.ts`) is NOT ported — there's no live-form conditional-visibility use case here; save-time validation is server-authoritative.

---

## Architecture

```
Automation (row)
├─ trigger_type = days_before_promotion_end
├─ trigger_config = { days_before: 7 }
├─ conditions_json = { kind:group, combinator:or, rules:[ …access_levels/name conditions… ] }  ← NEW (nullable)
├─ recipient_config = { user_ids, role_ids, include_promotion_owner, extra_emails }  ← unchanged
└─ email_template_id

evaluate_due / run_now
  └─ _execute(automation)
       ├─ matches = trigger.fire()  → [TriggerMatch(context, fact_sources={"promotion": <Promotion ORM>})]
       ├─ FILTER: keep match where evaluate(conditions_json, resolve_facts(db, match.fact_sources)) is True
       │          (empty conditions_json → keep all; trigger with no fact_sources → keep all)
       ├─ BATCH: mint batch_id; stamp kept promos (expiry_notified_at, expiry_notify_batch_id); commit; build batch_link
       └─ _send_grouped(..., batch_id, batch_link)  → ctx adds batch_link + expiry_notify_batch_id
```

```
Promotions page  ── deep link ?expiry_notify_batch_id=<id> ──▶ list filtered to batch + banner
  checkbox select rows → Actions ▸ Compile PDF
     POST /marketing-management/promotions/export/pdf { promotion_ids:[…ordered as displayed…] }
        DownloadService.create(kind="promotions_pdf") + enqueue_job(generate_promotions_pdf, imports queue)
           worker: PromotionsPdfService.render_pdf(ids) → PyMuPDF merge → upload → mark_ready
              My Downloads drawer → click → signed URL → PDF
```

---

## Contracts

### `conditions_json` tree (identical wire shape to FoundryX)

```jsonc
{
  "kind": "group",
  "combinator": "or",            // "and" | "or"
  "rules": [
    { "kind":"condition", "fact":"promotion.accessLevels", "operator":"contains_any",
      "valueKind":"literal", "value":["sorento_dealer","sorento_office"] },
    { "kind":"condition", "fact":"promotion.name", "operator":"contains",
      "valueKind":"literal", "value":"Sorento" }
  ]
}
```
Nested groups to depth 5. Save-time `validate_tree` → 422 `{ "detail": [problems…] }` on invalid.

### Promotion fact source (`GET /api/v1/rule-facts?sources=promotion`)

Returns `[{ key, label, type, operators, source, sourceLabel, options? }]`. Facts:

| key | label | type | operators | options |
|---|---|---|---|---|
| `promotion.name` | Promotion name | string | eq,neq,contains,in,not_in | — |
| `promotion.accessLevels` | Access levels | list | contains_any,contains_all,not_contains | ContactAccessType catalog (dynamic) |
| `promotion.isActive` | Active | boolean | is_true,is_false | — |
| `promotion.startDate` | Start date | date | before,after,between | — |
| `promotion.endDate` | End date | date | before,after,between | — |
| `promotion.startDate.daysUntil` / `.daysSince` | Days until/since start | number | eq,neq,gt,gte,lt,lte,between | — |
| `promotion.endDate.daysUntil` / `.daysSince` | Days until/since end | number | (as above) | — |

`promotion.name` resolves from `Promotion.description` (there is no `name` column). Label says "Promotion name".

### Trigger spec exposes `fact_sources`

`TriggerSpec` gains `fact_sources: tuple[str,...]` (default `()`). `days_before_promotion_end` → `("promotion",)`. The triggers-list API (`GET /api/v1/system/automation/triggers` or wherever specs are surfaced) includes `fact_sources` so the FE knows whether to render the RuleBuilder and which facts to fetch.

### Compile-PDF endpoint

`POST /api/v1/marketing-management/promotions/export/pdf`
body: `{ "promotion_ids": ["<uuid>", …] }` (order preserved = FE grid order)
→ `202 { "download_id": "<uuid>" }`. Validates ≥1 id, all exist. Creates `UserDownload(kind="promotions_pdf", source_entity_type="promotion_batch", source_entity_id=null)`, enqueues `generate_promotions_pdf(download_id, promotion_ids, user_id)` on `imports`. Redis-down → `mark_failed` so the drawer shows it.

### Promotions list filter

`GET /api/v1/marketing-management/promotions` gains optional `expiry_notify_batch_id` param → filters to promos with that batch id. FE reads `?expiry_notify_batch_id=` from URL, passes through `buildDataGridParams` extra, shows a dismissable banner ("Showing promotions from a recent expiry-reminder batch. [Clear]").

### Email template context (new variables)

Grouped context gains `batch_link` (`{frontend_base}/marketing-management/promotions?expiry_notify_batch_id={id}`) and `expiry_notify_batch_id`. Added to `TEMPLATE_VARIABLE_CATALOG` + `sample_context()`. A script patches the live `tpl-e7abadd8` body to add a "View all expiring promotions" button using `{{ batch_link }}` (idempotent).

---

## Backend port map (`sorento_crm_backend/app/rule_engine/`)

Port from `foundryx-shared-service/service_backend/app/rule_engine/`, with these adaptations:

- **`evaluator.py`** — copy verbatim EXCEPT replace `from app.services.filter_translator import MAX_GROUP_DEPTH as _MAX_DEPTH` with a local `_MAX_DEPTH = 5` (sorento has no `filter_translator`). Keep `evaluate`, `failed_conditions`, `collect_fact_keys`, `CROSS_FACT_OPERATORS`, all coercion helpers.
- **`schemas.py`** — copy verbatim (`OPERATORS_BY_TYPE`, `validate_tree`). Import `_MAX_DEPTH` + `CROSS_FACT_OPERATORS` from local evaluator.
- **`prose.py`** — copy verbatim (`condition_text`, `tree_text`, `_PHRASES`).
- **`registry.py`** — copy the `FactDef`/`FactSource`/`register_fact_source`/`get_facts`/`fact_map`/`resolve_facts`/`infer_facts`/`_day_count_facts` machinery. Replace:
  - `from app.lazy_registry import lazy_once` → local `_lazy_once` helper (a one-shot wrapper).
  - `from app.clock import today` → sorento Malaysia-today: `datetime.now(MALAYSIA_TZ).date()` (import `MALAYSIA_TZ` from `app.services.sla_service`).
  - `_register_core()` → register ONLY the `promotion` source (drop foundryx actor/tenant). Access-levels options resolver queries `ContactAccessType` (`app/models/access.py`) active rows → `[{value: code, label: name}]`.
- **`aggregates.py`, `sites.py`** — NOT ported (no COUNT/SUM facts, no observability list in v1).
- **New `app/api/v1/.../rule_facts.py`** — `GET /rule-facts?sources=promotion` materializing dynamic options; mount in `app/api/v1/__init__.py`. Schema `RuleFactItem`.

## Backend wiring

- **`app/models/automation.py`** — add `conditions_json = Column(JSONB, nullable=True)`.
- **`app/models/marketing.py`** — add `expiry_notified_at = Column(DateTime, nullable=True)`, `expiry_notify_batch_id = Column(UUID(as_uuid=False), nullable=True, index=True)` to `Promotion`.
- **Migration** (one revision, chained off current committed `alembic heads`): add the 3 columns + index on `promotions.expiry_notify_batch_id`. Idempotent (`IF NOT EXISTS` guards where practical). Verify single head after.
- **`app/schemas/automation*.py`** — `conditions_json: Optional[dict]` on create/update/response.
- **`AutomationService.create/update`** — accept `conditions_json`; when non-empty, call `validate_tree(tree, fact_sources_for(trigger_type))` → raise 422 (top-level `{detail: problems}`, matching FoundryX; FE reads array) on problems.
- **`automation_triggers.py`** — `TriggerSpec.fact_sources`; `TriggerMatch.fact_sources: dict|None`; promotion trigger attaches `{"promotion": promo}` (the ORM object) to each match. Add `fact_sources_for(trigger_type)` helper.
- **`AutomationService._execute`** — after building `matches`:
  1. If `automation.conditions_json` and matches carry `fact_sources`: `keys = collect_fact_keys(tree)`; keep `m` where `evaluate(tree, resolve_facts(db, m.fact_sources, only_keys=keys))`. Empty tree or no fact_sources → keep all.
  2. Promotion trigger only: mint `batch_id`; stamp kept promos (`expiry_notified_at=utcnow`, `expiry_notify_batch_id=batch_id`); `db.commit()` (stamp-first); compute `batch_link`.
  3. Pass `batch_id`/`batch_link` into `_send_grouped`; add to each grouped `ctx`.
- **`_send_grouped`** — accept `batch_id`/`batch_link`; add `ctx["batch_link"]`, `ctx["expiry_notify_batch_id"]`.
- **`email_template_service.py`** — catalog + `sample_context()` add `batch_link`, `expiry_notify_batch_id`.
- **Compile PDF**:
  - `app/services/promotions_pdf_service.py` — `PromotionsPdfService.render_pdf(promotion_ids) -> (bytes, filename, skipped: list)`. Load promos preserving input order; per promo load `promotion_attachments` ordered by `sort_order` NULLS LAST, `created_at`; download each via `storage_router` dispatch on the attachment's `storage_provider`; PDF → `fitz` `insert_pdf`; image (jpeg/png/webp/gif) → new page + `insert_image`; else skip+record. Empty output → raise. Filename `promotions-expiring-{DD-MM-YYYY}.pdf`.
  - `app/tasks/export_tasks.py` — `generate_promotions_pdf(download_id, promotion_ids, user_id)` mirroring `generate_complaint_pdf` (mark_processing → render → upload `exports/promotions-pdf/{download_id}/{filename}` → mark_ready; except → mark_failed).
  - `app/api/v1/marketing/promotions.py` — `POST /export/pdf` (see contract) + `expiry_notify_batch_id` query param on the list route + list-query service filter.

## Frontend

- **`components/platform/rule-builder/`** (new dir) — port `RuleBuilder` + `types/rules.ts` (`RULE_OPERATORS`, `CROSS_FACT_OPERATORS`, `RULE_MAX_DEPTH`, wire types) + `services/ruleEngineService.ts` (`getFacts(sources)` → `GET /rule-facts`). Adapt imports/design tokens to sorento's shadcn/ReUI components (searchable dropdowns per repo standard — NO `ui/select`). Keep operator tables in lockstep with BE `OPERATORS_BY_TYPE`.
- **Automation form** (`app/(protected)/system-management/automation/…AutomationForm`) — fetch trigger specs; if selected trigger has `fact_sources`, render `<RuleBuilder sources={fact_sources} value={conditions_json} onChange=… />` under the trigger block; include `conditions_json` in the create/update payload.
- **Promotions list** (`app/(protected)/marketing-management/promotions/…`):
  - read `?expiry_notify_batch_id=` → pass through list query (`buildDataGridParams` extra) + dismissable banner (mirror `ProductsList` discontinued banner).
  - DataGrid row selection (checkbox) + "Compile PDF" toolbar/Actions button → `useCompilePromotionsPdf()` mutation → `POST …/export/pdf` with selected ids in display order → toast "Preparing PDF… it will appear in My Downloads" → invalidate `['my-downloads']`.
- **`components/my-downloads/DownloadRow.tsx`** — `KIND_LABEL['promotions_pdf'] = "Promotions PDF"`.

## Tests (Phase 2, not deferred)

- **pytest**: evaluator truth table (each operator, fail-closed on missing/garbage, OR/AND, depth guard); `validate_tree` (unknown fact, bad operator, between-arity, cross-fact type mismatch); promotion fact resolution (name←description, access_levels list, days facts); `_execute` filter integration (Sorento vs Cabana routing, empty tree = all, no-fact-source trigger = all); batch stamp-first + batch_link; `PromotionsPdfService` merge (pdf+image fixtures, skip non-printable, empty→fail); compile endpoint (202, validation, auth denial); list filter by batch id.
- **vitest**: `RuleBuilder` (add/remove condition, nested group, operator list per fact type, cross-fact toggle, emits valid tree, depth cap); AutomationForm shows builder only for promotion trigger; promotions selection + Compile action fires mutation; batch banner renders + clears.
- **playwright**: create two automations with Sorento/Cabana filters → run_now → assert correct grouped emails (network); deep-link batch → promotions filtered + banner → select → Compile PDF → My Downloads row appears. Real attachment fixtures (pdf + jpg) in `e2e/fixtures/`.

## Verification

Playwright MCP against prod build: sidebar → System Management → Automation → edit → RuleBuilder renders for promotion trigger, save Sorento filter; Marketing → Promotions → batch deep link banner + filter + select + Compile PDF → My Downloads drawer shows "Promotions PDF" → download opens merged PDF. Check console + network each step.

## Rollout notes

- Existing "Promo expiry reminder" automation keeps working (null `conditions_json` = match all). Admin manually clones it into per-brand automations with filters.
- Requires `ContactAccessType` catalog rows for `sorento_*` / `cabana_*` (admin data, already live).
- Worker restart required (new `app/tasks/export_tasks.py` producer). New migration → `alembic upgrade head` on deploy.
</content>
</invoke>
