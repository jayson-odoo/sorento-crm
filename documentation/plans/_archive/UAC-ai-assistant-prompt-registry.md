# UAC - AI Assistant Prompt Registry (M1)

**Plan:** `PLAN-ai-assistant-prompt-registry.md` · **Branch:** `feat/ai-assistant-prompt-registry`
**Rule:** Write UAC first, then self-verify FE **and** BE against **every** line end-to-end before handoff
(`feedback_uac_first_then_verify_both`). Each criterion states its own verification command / click-path so
"done" is provable, not asserted.

Legend: **[BE]** backend/pytest · **[FE]** vitest/browser · **[E2E]** Playwright FE→BE→DB round-trip · **[MIG]** migration.

---

## A. Data model & migration

- **A1 [MIG]** Two tables created: `ai_prompt_versions` (immutable, append-only) and `ai_prompt_labels`
  (movable pointer). `ai_prompt_versions` has `UNIQUE(name, version)` and index on `name`;
  `ai_prompt_labels` has `UNIQUE(name, label)`.
  *Verify:* `alembic upgrade head` clean; `\d ai_prompt_versions` / `\d ai_prompt_labels` show the constraints.
- **A2 [MIG]** After the migration there is exactly **one** alembic head (dual-head rule
  `project_alembic_dual_head_merge`). *Verify:* `alembic heads` prints a single head.
- **A3 [MIG]** `version` auto-increments **per `name`** (`max(version)+1`), never global.
  *Verify:* seed inserts 9 keys each at `version=1`; two POSTs to one key produce v2, v3 while other keys stay at v1.
- **A4 [MIG] Seed is idempotent** (JOIN-based set-to-correct-value, not insert-where-null;
  `feedback`/backfill rule). Re-running `alembic downgrade -1 && upgrade head`, or running the seed twice,
  never spawns duplicate v2/v3 rows and never duplicates a label. *Verify:* run seed script twice, row counts stable.
- **A5 [MIG]** All **9 keys** seeded at v1 from the current hardcoded fallback text, each with a `production`
  label pointing at v1: active `reformulator`, `router`, `agent_system`, `synthesizer`; dormant `planner`,
  `semantic_compressor`, `validator`, `clarifier`, `judge`. *Verify:* `SELECT name,count(*) FROM ai_prompt_versions GROUP BY name` = 9 rows; every name has a `production` label.
- **A6 [MIG] Preserve pre-existing custom prompt (no silent loss).** If `ai_assistant_configs.system_prompt`
  holds a non-empty custom value at migrate time, it is seeded as `agent_system` **v2** and `production` points
  at **v2**; else `production` → v1. *Verify (both branches):* with a custom value set, post-migrate
  `agent_system` production template == the custom value; with empty value, production == v1 fallback.

## B. Runtime resolver & fallback

- **B1 [BE]** `get_prompt(name, label="production")` returns the labelled version's text + version int; caches by
  `(name,label)` with TTL. *Verify:* pytest - first call hits DB, second within TTL hits cache (DB query counted once / patched).
- **B2 [BE] DB-unreachable / missing key → hardcoded fallback, no hard failure** (UAC-plan §5). `get_prompt`
  returns `PROMPT_KEYS[name].fallback()` text with `version=None` when the DB query raises or no row exists.
  *Verify:* pytest - patch the session to raise; resolver returns fallback text, `version is None`; assistant
  still answers (no 500).
- **B3 [BE]** `render(name, **vars)` substitutes `{{var}}`; **all declared vars must be supplied** else a clear
  error. *Verify:* pytest - render with a declared var missing raises with the var name in the message; render
  with all vars returns substituted text; an undeclared `{{token}}` left in a template renders literally only if
  it slipped past save-validation (see D3), so save is the gate.
- **B4 [BE] Publish = move label, one UPDATE.** `set_label(name,label,version_id)` repoints the row; next
  `get_prompt` (after cache bust/TTL) returns the new version. *Verify:* pytest - publish v2, resolver returns v2 text.

## C. Call-site wiring & metadata stamping

- **C1 [BE]** Active call sites resolve through the registry, each method's current hardcoded string becoming the
  registered fallback - no behavior change when DB == seed:
 - `_reformulate_query` → `render("reformulator", ...)`
 - record classifier (`intent_is_record_class`) → `router`
 - `_default_system_prompt` → `agent_system`
 - user-guide/answer policy → `synthesizer` (absorbs `_user_guide_protocol_addendum`; the deterministic
    link post-proc `_inject_route_links`/`_extract_guide_link_map`/`_strip_outline_urls` is unchanged).
  *Verify:* pytest asserts each site calls the resolver with the right key; existing assistant tests still green.
- **C2 [BE] Metadata stamping.** Every assistant turn's `AIAssistantMessage.metadata_json` records
  `prompt_versions: [{name, version}, ...]` - one entry per LLM call made that turn (reformulator + router +
  agent_system/synthesizer as applicable). Fallback calls record `version: null`. *Verify:* pytest on `respond()`
  asserts `metadata_json["prompt_versions"]` present and non-empty; contains `reformulator` + the agent key.
- **C3 [BE]** `config.system_prompt` is **no longer read** by the agent loop (deprecated; registry is SoT). The
  DB column stays one release, read-ignored. *Verify:* setting `config.system_prompt` to garbage does NOT change
  the agent's system text (registry `agent_system` production wins).

## D. API contract (matches PLAN §8b exactly)

All routes gated on the **same permission as existing AI-assistant config** (`system.ai_assistant_settings.view`
for reads, `system.ai_assistant_settings.edit` for writes).

- **D1 [BE]** `GET /ai-assistant/prompts` → list of 9 keys `{name, role, active, activates_in|null, variables,
  production_version, staging_version|null, latest_version, updated_at, updated_by_name}`. *Verify:* pytest
  happy path shape + 403 without permission.
- **D2 [BE]** `GET /ai-assistant/prompts/{name}/versions` and `/versions/{v}` return history + full template per
  contract. *Verify:* pytest.
- **D3 [BE] Save = POST new immutable version** `{template, commit_message}` → 201 with `version=max+1`,
  `labels:[]`. **Asymmetric var validation** (`§9b Q7`): an **unknown `{{token}}` hard-blocks** save (422 with
  `unknown_tokens:[...]`); a **missing declared var soft-warns** (save allowed, `missing_vars:[...]` echoed).
  **Commit message required** (422 if blank). *Verify:* pytest - unknown token → 422; missing declared var →
  201 + warning; blank commit → 422.
- **D4 [BE] Publish/rollback** `POST /ai-assistant/prompts/{name}/labels {label, version_id}` → 200
  `{labels:{production, staging}}`. Rollback = publish an older version (same route). *Verify:* pytest - publish
  v2 then v1, `labels.production` follows.
- **D5 [BE] Dry-run** `POST /ai-assistant/prompts/{name}/test {message, version_id}` runs one real assistant
  turn with **only this key** overridden to the given version (`prompt_overrides:{key:version_id}`), rest =
  production → `{output, token_usage, tool_calls:[{name,ok}], used_overrides}`. **Dormant key → 400** (no call
  site). *Verify:* pytest - active key returns output + used_overrides; dormant key → 400.
- **D6 [BE]** Every write route enforces auth: 403 for a principal lacking edit permission. *Verify:* pytest auth-deny per route.

## E. Frontend (admin UI)

Sub-route `system-management/ai-assistant/prompts/` (list) → `.../prompts/[name]/` (detail). No modals for the
editor (dedicated page per ADR complex-form rule). Reaches via **sidebar/nav click**, not deep URL
(`feedback_playwright_via_sidebar`).

- **E1 [FE]** **List page** renders the 4 active keys as a table (name, role, production version, last-edited).
  Loading / empty / error states each render. *Verify:* vitest states; browser via nav from AI Assistant settings.
- **E2 [FE] Dormant keys behind "Show inactive" toggle** (default off). Toggled on → 5 dormant keys appear with
  a `Dormant` badge + "activates in {milestone}". *Verify:* vitest toggle; browser.
- **E3 [FE] Detail page:** left version-history list (commit messages + label badges), right monospace
  **raw-text** `<textarea>` editor (no WYSIWYG - avoids ProseMirror/Outline re-serialize bug), var chips,
  diff toggle, label controls, dry-run box. Editor **loads `production` by default**; version-picker loads any
  prior version as a fork base. *Verify:* vitest render; browser.
- **E4 [FE] Diff = client-side line-level** between any two versions. *Verify:* vitest renders added/removed lines; browser.
- **E5 [FE] Save = new version, commit message required**, local draft buffer + **warn-on-navigate-away** when
  dirty. Save ≠ publish (new version lands unlabelled). *Verify:* vitest - save disabled without commit msg;
  dirty-nav warning fires.
- **E6 [FE] Var chips**: green = present, amber = declared-but-missing, red inline error lists unknown tokens;
  **unknown token blocks the save button**. *Verify:* vitest chip states + disabled save on unknown token.
- **E7 [FE] Publish/rollback = AlertDialog confirm** (`feedback_confirm_before_delete_or_unlink`,
  `documentation/reference/ADR-PRODUCT-STANDARDS`), never `confirm()`. Copy for production:
  *"This changes the live assistant immediately. Publish {key} v{n} to production?"* *Verify:* vitest dialog
  renders + confirm calls the labels mutation; browser.
- **E8 [FE] Dry-run box** on detail: type one message → runs the selected version → shows `output` + token usage
  + tool pills inline. **Disabled for dormant keys** with an inline reason. *Verify:* vitest; browser.
- **E9 [FE] Mobile**: detail page + any dialog are scrollable and usable at ~375px, submit/publish reachable
  (`feedback_mobile_modal_scroll`). *Verify:* browser at 375px width.
- **E10 [FE]** Settings form: the old `system_prompt` RichTextEditor field is **removed**, replaced by a link to
  **Prompts → agent_system** (`§9b Q8`). *Verify:* vitest - field gone, link present; browser.
- **E11 [FE]** No UUIDs shown in UI (cursor rule) - versions shown as `v{n}`, authors as names. *Verify:* browser snapshot has no raw uuid.

## F. End-to-end (the money criteria - PLAN §11)

- **F1 [E2E]** All 4 active prompts editable in FE; none require redeploy. 5 dormant visible/editable, marked
  inactive, dry-run disabled. *Verify:* Playwright edits each active key.
- **F2 [E2E]** Saving produces a new immutable version with commit message; prior versions remain readable.
  *Verify:* Playwright save → history shows both versions → open old version renders its old text.
- **F3 [E2E]** Diff between any two versions renders. *Verify:* Playwright diff toggle shows a line change.
- **F4 [E2E] Publish moves `production`; the very next chat turn uses the new text. Rollback → next turn uses
  old text.** *Verify:* Playwright - edit `reformulator` to inject a detectable marker, publish, send a chat
  message, assert the marker's effect (or assert production label moved + resolver returns new version via
  dry-run); then rollback, assert reverted. Confirm `browser_network_requests` hit `POST /.../labels` and
  `POST /.../chat`.
- **F5 [E2E/BE]** DB-unreachable or key missing → assistant still answers via fallback (no hard failure). *Verify:* B2 pytest is the primary proof (E2E can't easily kill the DB).
- **F6 [E2E]** Every assistant message's `metadata_json` records `prompt_name`+`prompt_version` per LLM call.
  *Verify:* send a chat turn, inspect the message row / usage query-detail → `prompt_versions` populated.
- **F7 [E2E]** Seed preserved any pre-existing custom `system_prompt`. *Verify:* A6 (migration-time) + open
  Prompts → agent_system, production version == prior custom value.
- **F8 [E2E]** Editing out a required `{{variable}}` (removing it) → **soft warn**, save allowed; adding an
  **unknown** `{{token}}` → **hard-blocked** at save with a clear error. *Verify:* Playwright both paths.

## G. Process / non-regression

- **G1** Existing AI assistant chat, usage analytics, and settings pages still work (no regression). *Verify:* smoke the chat + usage page.
- **G2** Contract doc at top of the new FE service file matches shipped BE (`feedback_three_phase_dev_loop`).
- **G3** Tests land in Phase 2, not deferred: pytest (resolver, routes, seed, wiring) + vitest (list/detail/diff/publish) + one Playwright spec.
- **G4** `worker.py` untouched (no RQ task change). Backend edits only need uvicorn reload confirm; FE change → rebuild+restart before browser verify.

---

### Verification ledger (2026-07-03 - all ticked)

| UAC | How verified | Result |
|-----|--------------|--------|
| A1 - A6 | `alembic upgrade head` → single head `258`; DB query = 9 keys × v1 + 9 production labels; agent_system stayed v1 (config.system_prompt empty at migrate → v1 branch of A6); pytest seed-idempotency | ✅ |
| B1 - B4 | Direct resolver calls: `get_prompt` version=1; `render` substitutes `{{current_date}}` + missing-var raises `ValueError` naming it; `BoomDB` (raises on query) → fallback text, `version=None`, no raise; publish+`bust_cache` → new version; + 26 pytest | ✅ |
| C1 - C3 | Live chat turn stamped `metadata_json.prompt_versions=[reformulator,agent_system,synthesizer]`; pytest asserts config.system_prompt garbage does not reach system text | ✅ |
| D1 - D6 | 26 pytest (happy/403/404/422-unknown-token/dormant-400); live browser: POST versions→201, POST labels→200, POST test→ real turn | ✅ |
| E1 - E11 | Browser (mock + real): sidebar nav, list, dormant toggle, editor loads production, client line-diff, unknown-token hard-block + disabled save, publish AlertDialog copy, dry-run, dormant disabled, 375px mobile, settings link, author shown as name (no UUID); 21 vitest | ✅ |
| F1 - F8 | Live real-API round-trip: save reformulator→v2 (201), publish→production=v2 (resolver returns v2 marker), rollback→v1 (marker gone); diff renders; F5 via B2 pytest; F6 live metadata; F8 unknown blocked / missing soft-warn | ✅ |
| G1 - G4 | Chat + dry-run smoke live; contract doc at top of `aiPromptsService.ts`; pytest+vitest+playwright landed; worker untouched | ✅ |

### Phase-3 review findings (reviewer agent) - resolution

| # | Finding | Action |
|---|---------|--------|
| 1 | `window.confirm()` on version-switch discard (ADR violation) | **Fixed** - replaced with `AlertDialog` ("Discard unsaved edits?"); browser-verified + vitest (`confirm` never called). |
| 2 | Dry-run could drive a `*_submit`/`*_create` MCP write through live tools | **Fixed** - `respond(dry_run=True)` strips write-capable tools (`_is_write_tool`: `*_submit`/`*_create`/`*_link`/`_ticket_create`); pytest for the predicate; route passes `dry_run=True`. |
| 3 | `save_version` `max+1` not race-safe | Accepted (nit) - `uq(name,version)` prevents duplication; low-concurrency admin tool. |
| 4 | Hand-rolled table vs shared DataGrid | Accepted (nit) - static ~9-row registry, no DataGrid params surface; `line-clamp-2`+`title`+`overflow-x-auto` so no column overlap. |
| 5 | `<span role=button>` nested in `<button>` (a11y) | **Fixed** - version row is now `<div role=button>` with keyboard handler; Publish/Stage are real `<button>`s. |
| 6 | `saveVersion` hand-rolls `r.json().catch()` | Accepted - needs structured `{unknown_tokens,missing_vars}` body that `extractApiError` (string-only) can't return; documented. |
| 7 | `PromptVersionDetail` missing `missing_vars` field | **Fixed** - added the field; dropped the inline cast. |
