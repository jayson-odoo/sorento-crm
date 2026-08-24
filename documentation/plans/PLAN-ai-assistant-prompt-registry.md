# PLAN - AI Assistant Prompt Registry (P1)

**Status:** BUILT + VERIFIED 2026-07-03 (branch `feat/ai-assistant-prompt-registry`). All 3 phases done; UAC A - G verified end-to-end (ledger in `UAC-ai-assistant-prompt-registry.md`). Pending: code-review findings + PR.
**Owner:** jayson
**Date:** 2026-07-03
**Scope:** Milestone **M1** of a multi-milestone AI-assistant re-architecture. This plan covers **prompt registry only**.

### Roadmap (milestones - do NOT confuse with the per-plan dev Phases in §12)
| Milestone | Delivers | New roles activated | Plan |
|---|---|---|---|
| **M1** (this plan) | prompt registry: all prompts DB-editable, versioned, labelled | codifies today's roles as keys; seeds dormant keys | this doc - GRILLED |
| **M2** | per-node trace/spans UI (n8n-style in/out), OTel `gen_ai.*` schema | - (observes existing) | `PLAN-ai-assistant-node-trace.md` - GRILLED |
| **M2.5** | split agent monolith → explicit `planner` + `synthesizer`; add `semantic_compressor` | planner, semantic_compressor | `PLAN-ai-assistant-node-trace.md` §6 - GRILLED |
| **M3a** | guardrails: write-tool confirm, `validator` (hedge/abstain), `clarifier` (ask-vs-guess) | validator, clarifier | `PLAN-ai-assistant-evals-guardrails.md` §9 - GRILLED |
| **M3b** | evals: feedback UI, golden datasets, `judge`, A/B compare + advisory promotion gate | judge | `PLAN-ai-assistant-evals-guardrails.md` §9 - GRILLED |

Each later milestone only **flips a dormant key's label + wires a call site** - no schema migration (that's the front-loaded option-B win). "Phase 1/2/3" in §12 is the CLAUDE.md dev loop (FE prototype → BE+tests → review) *within* M1, unrelated to milestones.

---

## 1. Problem

Today every prompt in the AI assistant is hardcoded in `app/services/ai_assistant_service.py`:

| Call site | Prompt | Editable today? |
|---|---|---|
| `_reformulate_query` (:831) | reformulator system prompt | **No** - hardcoded |
| `_run_agent_loop` (:1153) / record-context loop (:1776) | agent system prompt (`_default_system_prompt` :1473) | Partially - only as a single `config.system_prompt` override, no history |
| auto-appended (:1159 / :1778) | `_user_guide_protocol_addendum` (:1599) | **No** - hardcoded, silently appended even over a custom prompt |
| record-question classifier (:1690) | classifier system prompt | **No** - hardcoded |
| `_generate_suggestions` (:1993) | suggestions prompt | **No** - currently disabled |

Consequences:
- Admin can only edit ONE of ~4 real prompts, and even that has no versioning, no diff, no rollback. Tuning is blind and irreversible.
- The `config.system_prompt` lives on the `AIAssistantConfig` singleton - no history, no "publish vs draft", no way to compare a change against the prior text.
- No linkage between "which prompt text produced this answer" and the answer itself → cannot attribute a regression to a prompt change.

## 2. Goal (P1)

Move **all** assistant prompts into a DB-backed, FE-editable **prompt registry** with the industry-standard **immutable-versions + movable-labels** model, keyed by the target **role decomposition** (§5), so an admin can:
1. Edit any prompt (reformulator, agent system, user-guide protocol, classifier) in the UI.
2. Save a new immutable version with a commit message.
3. Diff any two versions.
4. Publish = move the `production` label to a version (no redeploy).
5. Roll back = move the label to a prior version.

## 3. Non-goals (explicitly deferred)

- **Per-node trace / spans UI (P2).** No `ai_assistant_spans` table here. BUT: we stamp `prompt_name` + `prompt_version` onto the existing `AIAssistantMessage.metadata_json` in P1 so P2 spans can link back.
- **Eval / golden-set / LLM-judge (P3).**
- **Model-tier abstraction (BASE/LARGE, Grafana pattern).** Nice, but out of scope; model stays on `AIAssistantConfig` for now. Note as future.
- **A/B traffic-split by percentage (PromptLayer pattern).** Labels support it later; not built now.
- **Prompt playground / re-run-node.** P3.

## 4. Industry grounding (from research)

Universal convergent pattern across LangSmith Prompt Hub, Langfuse, PromptLayer:
- **Version** = immutable snapshot (auto-increment int per name). Never edited in place.
- **Label** = movable pointer (`production`, `staging`) → one version. Publish = re-point. Rollback = move back. No redeploy.
- Runtime fetch by `(name, label)` with **in-process TTL cache** + **hardcoded env fallback** if DB unreachable (Langfuse's fallback-prompt pattern). Our current hardcoded strings become that fallback - we never delete them.
- **Stamp `prompt_name` + `prompt_version` on every generation** so diagnosis/regression is attributable. (This is the bridge to P2.)
- Model config can travel WITH a version (Langfuse `config` blob). We keep model on `AIAssistantConfig` for P1 (single provider/model today); leave a `config_json` column on the version for future.

## 5. Data model

Two tables. Immutable versions + movable labels.

### `ai_prompt_versions` (immutable, append-only)
```
id              uuid pk
name            text        -- stable key from PROMPT_KEYS (see role table below):
                            -- active: reformulator | router | agent_system | synthesizer
                            -- dormant: planner | semantic_compressor | validator | clarifier | judge
version         int         -- auto-increment PER name (max(version)+1 on insert)
type            text        -- 'text' | 'chat' (all current = 'text')
template        text        -- the prompt body, {{mustache}} placeholders
variables       jsonb       -- extracted declared vars, e.g. ["current_date","standalone_query"] (UI + validation)
config_json     jsonb null  -- reserved: per-version model/params override (unused P1)
commit_message  text null
created_by      uuid null   -- users.id
created_at      timestamptz default now()

UNIQUE (name, version)
INDEX (name)
```

### `ai_prompt_labels` (movable pointer, one row per (name,label))
```
id              uuid pk
name            text
label           text        -- 'production' | 'staging'
version_id      uuid fk -> ai_prompt_versions.id
updated_by      uuid null
updated_at      timestamptz default now()

UNIQUE (name, label)
```

Publish = `UPDATE ai_prompt_labels SET version_id=? WHERE name=? AND label='production'`. That's the whole publish operation.

**Registry of prompt keys** (a code-level constant `PROMPT_KEYS`, not a table) - the canonical list of editable prompts + their declared variables + their hardcoded fallback function. Keeps the seed migration and the resolver in sync.

### Prompt keys = role decomposition (front-loaded, option B)

Keys are defined against the **target role decomposition**, not just today's call sites, so later phases only flip a label + wire a call site - never a migration. Each key = one LLM role = one future trace node (P2). Deterministic stages (retriever, tool-executor, RBAC, link injection, entity resolution, short-circuits) are NOT prompts and get no key.

**Active in P1 (map to existing call sites):**
| key | role | current source |
|---|---|---|
| `reformulator` | rewrite turn → standalone query | `_reformulate_query` :831 |
| `router` | intent/routing - is-record-Q? is-how-to? handoff? (generalizes today's record-classifier) | record classifier :1690 |
| `agent_system` | thinker/executor ReAct core | `_default_system_prompt` :1473 |
| `synthesizer` | answer policy - cite, preserve links, format steps, anti-invent | absorbs `_user_guide_protocol_addendum` :1599 |

**Registered but INACTIVE in P1 (seed the key + fallback, no call site yet):**
| key | role | activates in |
|---|---|---|
| `planner` | decompose task, order tool steps (split from `agent_system`) | P2.5 |
| `semantic_compressor` | raw tool JSON → token-tight sentences (Grafana 4x pattern) | P2.5 |
| `validator` | confidence-gate answer before send (Intercom/Shopify) | P3 |
| `clarifier` | ask-vs-guess when query underspecified | P3 |
| `judge` | offline/online quality eval (LLM-as-judge) | P3 |

**`user_guide_protocol` is deliberately NOT a key.** It was a mislabeled generic retrieval-answer policy named after its first source. Its content redistributes: "when to retrieve" → `router`; tool call-once quirk → the `user_guides_read` **tool description** (Shopify Just-in-Time tool-instruction pattern - per-tool rules ride on the tool, not the global prompt); "how to answer from retrieved content (cite, preserve links, format, don't invent)" → `synthesizer` (source-agnostic). The markdown-link preservation is additionally guaranteed by the existing **deterministic** post-processing (`_inject_route_links` / `_extract_guide_link_map` / `_strip_outline_urls`) - the prompt instruction is belt, the post-proc is suspenders.

## 6. Runtime resolver

New module `app/services/ai_prompt_registry.py`:

```
get_prompt(name, label="production") -> RenderedPrompt
  1. in-process TTL cache (e.g. 60s) keyed by (name,label) -> version row
  2. miss: SELECT version via label join; cache it
  3. DB unreachable / no row: fall back to PROMPT_KEYS[name].fallback() (current hardcoded text)
  4. return {text, name, version}  (version = None when fallback used)

render(name, **vars) -> str
 - fetch, then substitute {{var}} from vars; validate all declared vars supplied
```

Call-site edits in `ai_assistant_service.py` (mechanical, one per site):
- `_reformulate_query` :831 → `render("reformulator", current_date=...)`
- `_default_system_prompt` :1473 → resolver `agent_system` (this method BECOMES the fallback)
- record classifier :1690 → resolver `router` (becomes fallback)
- `_user_guide_protocol_addendum` :1599 → **dissolved** (see role table §5): generic answer policy moves into the `synthesizer` fallback text; the tool call-once quirk moves to the `user_guides_read` tool description. The runtime composition at :1159/:1778 that appends the addendum to `agent_system` is replaced by appending the `synthesizer` policy (or merging into `agent_system` - decide at impl). Deterministic link post-proc unchanged.
- `config.system_prompt` override at :1153/:1776: **decision** - either (a) deprecate it in favor of the `agent_system` registry entry (single source of truth), or (b) keep it as a higher-priority override above the registry. See open questions.
- Every `provider.chat` result → attach `{prompt_name, prompt_version}` to that turn's `metadata_json` (bridge to P2).

## 7. Migration + seed

- Alembic migration: create both tables. Watch the dual-head rule (single head after - see `[[project_alembic_dual_head_merge]]`).
- Seed migration: for each key in `PROMPT_KEYS` (4 active + 5 dormant), insert version 1 = current hardcoded fallback text, then insert a `production` label pointing at it. Dormant keys get a placeholder/best-first-draft body but no call site reads them yet. Idempotent (JOIN-based upsert per the backfill rule - set-to-correct-value, not insert-where-null; guard against re-running spawning v2/v3).
- `system_settings` / `AIAssistantConfig.system_prompt`: if a non-empty custom value exists, seed it as `agent_system` version 2 and point `production` at it (preserve what the admin already set). Otherwise `production` → version 1.

## 8. API (backend routes, under existing `app/api/v1/system/ai_assistant.py`)

```
GET    /ai-assistant/prompts                      -> list keys + current production version summary
GET    /ai-assistant/prompts/{name}/versions      -> version history (id, version, commit_message, created_by, created_at)
GET    /ai-assistant/prompts/{name}/versions/{v}  -> full template body
POST   /ai-assistant/prompts/{name}/versions      -> create new version {template, commit_message}
POST   /ai-assistant/prompts/{name}/labels        -> move label {label:'production', version_id}  (publish/rollback)
GET    /ai-assistant/prompts/{name}/diff?a=&b=     -> (optional server-side diff, or diff client-side)
```
RBAC: gate on the same admin permission as the existing AI-assistant config routes.

## 9. Frontend (admin UI)

Extend `app/(protected)/system-management/ai-assistant/`:
- New **Prompts** tab/section. List the ~4 prompt keys with their live production version number + last-edited.
- Click a key → editor: current production template (read), **version history list** (with commit messages), **diff view** between any two versions (client-side diff lib or `<pre>` side-by-side), an **edit → save-as-new-version** flow (textarea + commit message), and a **Publish** button per version (moves `production` label) + confirm dialog.
- Reuse existing `AIAssistantSettingsForm` patterns + `useAIAssistantAdmin` hooks; add `useAIAssistantPrompts`.
- Show declared `{{variables}}` for each prompt so the admin knows what's substituted (prevents editing out a required placeholder). Validate on save that declared vars still present.
- Follow CRUD UX standard: publish + rollback are state changes → AlertDialog confirm (`[[feedback_confirm_before_delete_or_unlink]]`). Mobile-scrollable modal (`[[feedback_mobile_modal_scroll]]`).

## 9b. Phase-1 UX decisions (resolved via grill 2026-07-03)

| # | Decision |
|---|---|
| Q1 | **Editor** = plain monospace `<textarea>`, raw text stored **verbatim** (no HTML/WYSIWYG transform). Markdown is a *recommended authoring convention* (LLM-friendly), NOT enforced and NOT a rich editor - avoids the ProseMirror/Outline re-serialization class of bug. Optional read-only render-preview tab; source-of-truth = raw text. Kills templating-collision + diff-noise at source. |
| Q2 | **Diff** = client-side, **line-level** (word-level later if coarse). No diff endpoint. Raw-text storage makes it accurate. |
| Q3 | **IA** = new sub-route `system-management/ai-assistant/prompts/` (mirrors `usage/`) + nav link from settings. **List page** (table of 9 keys) → **detail page** (dedicated, per ADR complex-form rule). No modals. Detail = left version-history list, right monospace editor + var-chips + diff toggle + label controls + dry-run box. |
| Q4 | **Save** = always POST a **new immutable version** (`max+1`), never edit-in-place. **Commit message required.** Editor **loads `production` by default**; version-picker can load any prior version as a fork base. Local draft buffer + warn-on-navigate-away. **Save ≠ publish** (new version lands unlabelled/`latest`). |
| Q5 | **Staging test** = **(b) single-message dry-run**. Detail-page "Test this version" box: type one message → runs through the real assistant with THIS key swapped to the selected version (`prompt_overrides:{key:version_id}`), rest = production → shows output inline. No dataset/scoring (that's M3). |
| Q6 | **Dormant keys** = shown behind a **"Show inactive" toggle (default off)**; `Dormant` badge + "activates in {milestone}". **Editable** (draft ahead - the option-B win) with an *"Inactive - saved but not used at runtime yet"* banner. **Dry-run disabled** for dormant (no call site). |
| Q7 | **Var validation** = asymmetric. Declared vars are a property of the KEY (fixed in `PROMPT_KEYS`, not free-form). **Unknown `{{token}}` → hard-block save** (would leak literally). **Missing declared var → soft warn**, save allowed. Chip row: green=present, amber=declared-but-missing, red inline error lists unknown tokens. |
| Q8 | **`config.system_prompt` deprecated.** Remove the RichTextEditor field from settings form; replace with a link to **Prompts → agent_system**. Migration copies existing value into `agent_system` (→ production). **Every key's default text is seeded to DB as v1** - nothing stays code-only; the hardcoded strings become a DB-unreachable *fallback only*. Keep the column one release (read-ignored), drop later. |
| Q9 | **Publish/rollback** = one model: "Publish v{n} to {label}" moves the label; rollback = publish an older version. Inline label badges (`● production` green, `staging` amber) on history rows. **AlertDialog confirm** for production: *"This changes the live assistant immediately. Publish {key} v{n} to production?"* **Same permission as edit** (no tighter gate in M1). |
| Q10 | **Contract** = see §8b below. `role` supplied by backend as display string. Dry-run response returns `output` + `token_usage` + `tool_calls:[{name,ok}]` (free taste of M2). Diff client-side. |

## 8b. FE↔BE data contract (Phase-1 mock target, Phase-2 BE must match)

```
GET  /ai-assistant/prompts
  [{ name, role, active, activates_in|null, variables:[...],
     production_version, staging_version|null, latest_version,
     updated_at, updated_by_name }]

GET  /ai-assistant/prompts/{name}/versions
  { name, role, active, activates_in|null, variables:[...],
    labels:{ production:int, staging:int|null },
    versions:[{ id, version, commit_message, created_by_name,
                created_at, labels:[...] }] }        // version desc

GET  /ai-assistant/prompts/{name}/versions/{v}
  { id, name, version, template, variables:[...], commit_message,
    created_by_name, created_at, labels:[...] }

POST /ai-assistant/prompts/{name}/versions           # save
  req { template, commit_message }
  201 <version object, version=max+1, labels:[]>
  422 { error, unknown_tokens:[...], missing_vars:[...] }   # unknown=block, missing=warn

POST /ai-assistant/prompts/{name}/labels             # publish/rollback
  req { label:"production"|"staging", version_id }
  200 { labels:{ production, staging } }

POST /ai-assistant/prompts/{name}/test               # single-message dry-run
  req { message, version_id }                          # override THIS key only
  200 { output, token_usage, tool_calls:[{name,ok}], used_overrides }
  400 dormant key not testable
```

## 10. Tests (Phase 2 - land here, not deferred)

- **pytest:** resolver (cache hit/miss/fallback), version auto-increment per name, label-move = publish, seed idempotency, render var-substitution + missing-var error, each route happy/auth-deny/validation.
- **vitest:** Prompts tab - list/empty/error/loading, diff render, save-new-version, publish confirm dialog.
- **playwright:** admin edits reformulator → save version → publish → send a chat message → assert the new prompt took effect (or at least that production label moved). Verify via sidebar per `[[feedback_playwright_via_sidebar]]`.

## 11. Acceptance criteria (UAC - write/verify both sides)

1. All four ACTIVE prompts (reformulator, router, agent_system, synthesizer) are editable in the FE; none require a redeploy to change. The 5 dormant keys are visible/editable but marked inactive (not yet wired to a call site).
2. Saving produces a new immutable version with a commit message; prior versions remain readable.
3. Diff between any two versions renders.
4. Publish moves the `production` label; the very next chat turn uses the new text. Rollback moves it back; next turn uses old text.
5. DB unreachable or key missing → assistant still answers using the hardcoded fallback (no hard failure).
6. Every assistant message's `metadata_json` records `prompt_name`+`prompt_version` for each LLM call in that turn.
7. Seed preserves any pre-existing custom `system_prompt` (no silent loss on migrate).
8. Editing out a required `{{variable}}` is rejected at save with a clear error.

## 12. Three-phase breakdown (per CLAUDE.md methodology)

- **Phase 1 (FE prototype):** Prompts tab against mock versions/labels. Nail the version-list + diff + publish-confirm UX. Document the API contract at top of the new service file.
- **Phase 2 (BE + wire + tests):** tables, migration+seed, resolver, routes, swap call sites, stamp metadata, wire FE off mocks. All three test suites land.
- **Phase 3 (review):** `/code-review`, then PR with prototype screenshot + contract confirmation.

## 13. Open questions (for grill)

1. ~~**`config.system_prompt` fate**~~ - RESOLVED: **deprecate hardcoding**. Registry is sole SoT. Migrate any existing custom value into `agent_system` as a version + point `production` at it, then stop reading the column (leave column for one release as safety, remove later).
2. ~~**Labels beyond `production`**~~ - RESOLVED: ship **`staging` + `production`**. Edit → save version → optionally test on `staging` → publish = move `production`.
3. ~~**Who can edit**~~ - RESOLVED: **same permission as existing AI-assistant config routes**.
4. **Diff** client-side vs server-side. Recommend client-side (no BE dep, simpler).
5. ~~**`user_guide_protocol` composition**~~ - RESOLVED: dissolved into `router` + `synthesizer` + tool description (see §5 role table). Not a key.
6. **Cache TTL / invalidation** - 60s TTL is simplest; a publish could also bust the cache immediately via an in-process signal. Recommend TTL only for P1 (60s lag on publish acceptable), immediate-bust as a nicety.
7. **`suggestions` prompt** - currently disabled. Register it now (inactive) or omit until re-enabled? Recommend omit; add when feature returns.

---

## Forward hooks for P2/P3 (designed, not built)
- `prompt_name`+`prompt_version` on `metadata_json` → P2 spans `gen_ai` attributes link to the exact prompt variant (OTel `gen_ai.request.*` + a `prompt.name`/`prompt.version` pair).
- `config_json` column on versions → P2/P3 model-tier + per-prompt param overrides.
- Immutable versions → P3 evals pin "experiment = prompt version X over golden dataset".
