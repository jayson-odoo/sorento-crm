# PLAN - parser prompt wired to its registries + prompt editor that shows it (PROMPT-DYNAMIC)

Status: Build. Track: full (migration, new admin table, new admin page). Grill run late (see "Grill"). R5c shipped (7f004bf0);
backend S2-S4 under TDD; R5a/b wait on the mock
(`documentation/mockups/prompt-editor-dynamic.html`). Lane `crew-lane: PROMPT-DYNAMIC`, PR #1405.
UAC: `prompt-dynamic-30sep-acceptance-criteria.md`.

## Journey

The owner opens AI Assistant > Prompts > Chatbot semantic parser. He sees the wording he edits,
and every list the CRM owns (domains, their switch words, status words, entity kinds, specs,
brands, teams, agents, access levels) shows as a chip that names its source and row count.
He adds "sales analysis" as a status word on the Chatbot Status Words page, runs a test turn,
and the rendered prompt the model received carries it without a publish. He deletes a chip to
write the list in his own words; the chip does not come back on a later publish. In a diff he
steps change by change; in search, Enter takes him to the next match and he types right there.

## Facts measured (base b8cdbebe4, `sorento_crm_backend/app/services` unless noted)

- Runtime: `chatbot/head/parser.py:590` `render('chatbot_semantic_parser')` -> the version
  labelled `production`; `ai_prompt_registry.py:1408 render` substitutes `{{var}}` only for
  variables the caller passes; `:1323 get_prompt` caches the raw template 60s per (name, label).
- The code constant `chatbot_parser_prompt.SEMANTIC_PARSER_PROMPT` is 123,870 chars; its lists:
  `domain_hint = ONE of: ...` (INTENT & DOMAIN), the DOMAIN IN MESSAGE word list, the
  ORDER_STATUS FILTER bullets, the OUTPUT `order_status` / `status` / `suggested_team` /
  `suggested_agent` enums, the ENTITY OPERATIONS `hint` enum, the ACCESS LEVELS list.
- Policy blocks (`chatbot_parser_prompt.py:730 render_prompt_blocks`) are baked into a version at
  PUBLISH time between `<<<CHATBOT POLICY BLOCKS>>>` markers; a row edit only raises the stale
  banner (`app/api/v1/system/chatbot.py:750`).
- Sources: domains `chatbot_domains` (14 rows seeded); entity kinds `chatbot_entity_kinds` (13);
  specs `product_spec_registry`; brands `brands` (already sent per turn on the user block's
  "Known brands:" line, `chatbot/head/parser.py:670-763`); access levels `contact_access_types`
  (`app/models/access.py:67`, name + sort_order + is_active); teams: `agent_teams.code`
  (`app/models/access.py:614`), code constant `lanes/escalation.py:62 ESCALATION_TEAMS` (8);
  agents: `access_agents.code` (`app/models/access.py:381`), code constant
  `contracts.py:172 SUGGESTED_AGENTS` (6; the prompt's enum lists 5, `ideation` missing);
  statuses: code constants only (`contracts.py:388 SALES_FIGURE_STATUSES`, the prompt bullets).
- Sales today is `order` + `order_status in {sales_report, sales_analysis, top_selling}`. Every
  site that special-cases it: see "S5 (R7)" below.

## Decisions

D1 **Two layers, one template.** The wording layer IS the version's template text, and it holds
   `{{name}}` registry variables where the lists sit. The generated layer is the render of those
   variables. A publish saves the owner's text as-is: nothing in any publish or migration path
   rebuilds a version from the code constant again (the `<<<CHATBOT POLICY BLOCKS>>>` bake is
   retired for this key; the blocks become `{{domains_detail}}`, `{{entity_kinds_detail}}`,
   `{{specs}}`). Deleting a chip = deleting the token; no code path re-inserts it.
D2 **Variables** (module `app/services/chatbot_prompt_vars.py`, one entry each: name,
   label, source table, admin href, `render(db) -> str`, `rows(db)` for the panel):
   `domains` (names, sort_order, ` | ` joined), `domain_words` (switch words of every domain,
   then status trigger words, de-duplicated, `, ` joined), `domains_detail` (today's
   `domain_line` per row), `statuses` (the bullets, per domain, from the new status table),
   `status_values` (`a|b|c` of every status value), `entity_kinds` (`a|b|c`),
   `entity_kinds_detail` (today's kind lines), `specs` (`specification_lines`), `brands`
   (`Name (CODE), ...`, active brands), `teams` (`a|b|c`), `agents` (`a|b|c`), `access_levels`
   (JSON list of active `contact_access_types.name` by sort_order).
D3 **Teams = the escalation lane's `ESCALATION_TEAMS` (grill 2, owner 30 Sep 2026), agents =
   active `access_agents.code`.** The lane matches the parser's team word only against
   `ESCALATION_TEAMS` (`lanes/escalation.py:1234-1261`); `suggested_agent` goes out as the round
   robin's `agent_code` (`escalation.py:1547`). Empty table (CI) falls back to the code constants so a
   fresh DB still renders a complete prompt. Equivalence against production data is proven by
   `scripts/prompt_dynamic_render_diff.py`, run by crew on the prod-copy dev DB.
D4 **Brands.** Stay on the per-turn user block (no behaviour change). `{{brands}}` exists in the
   picker and the wired panel; the migration does not insert it into the wording.
D5 **Freshness.** `render()` substitutes registry variables at request time from a process cache
   (TTL 30s) that an SQLAlchemy `after_commit` hook clears when a registry model row was written
   in that session. Other processes (worker) converge within the TTL. The template cache
   (`get_prompt`) is unchanged; the label moves only through the owner's label route.
D6 **Status words registry (R2).** New table `chatbot_status_words` (id, domain -> 
   `chatbot_domains.name`, value, label, trigger_words text[], sort_order, timestamps),
   seeded from the prompt bullets + the sales statuses (`sales_report`, `sales_analysis`,
   `top_selling`) with the owner's words ("sales", "sales report", "top selling",
   "sales analysis", "best selling"). Admin page = the Chatbot Domains page pattern
   (`app/api/v1/system/chatbot_config.py:340-403`, list + modal, deferred hard delete).
D7 **Wording migration (R1).** `pdyn_0002_wording_layer` reads the `production`-labelled template
   of `chatbot_semantic_parser` (v42 on prod, owner edits included), replaces each duplicated
   list by exact-substring match with its token, strips the baked policy blocks for
   `{{domains_detail}}` etc., and inserts the result as a NEW UNLABELLED version. A list the
   owner had reworded (no exact match) is left verbatim and logged. Labels untouched.
D8 **Drift test (R4).** `tests/chatbot/test_prompt_dynamic_drift.py`: the rendered prompt's
   lists equal their registries; the wording layer (latest version + code fallback) contains no
   literal copy of any registry list (e.g. `master_products | product_attachment`, the team
   enum, the access level JSON).
D9 **R7 sales domain.** Its own row `sales` in `chatbot_domains` (migration + `policy_rows`
   seed + `bootstrap_env` replay): switch words sales, sales report, top selling, sales
   analysis, best selling; tools `crm_sales_report`, `crm_sales_analysis`,
   `crm_top_selling_report`; reveal key `sales_orders.sales_report`; escalation
   `customer_service`. Routing moves the three statuses from `order` to `sales` at every
   special-case site (list in S5). Coordinate with PR #1401 (rebase if it lands first).

## Slices

S1 R5c search fix - DONE 7f004bf0 (tests `components/common/find-in-text`).
S2 Registry variables + render-time substitution + cache/invalidation + drift test (D1-D5, D8).
S3 Status words table, seed, admin API + page (D6); `statuses`/`status_values` read it.
S4 Wording migration + render-diff script (D7), before/after diff attached to the PR.
S5 R7 sales domain (D9): contracts `DOMAIN_HINTS` from the live table, `select_tool` /
   allow-list, `turn_runtime._report_status_means_order_domain`, business lane overrides
   (`lanes/business/__init__.py:1558-1702`), `gate.ALLOWED`, `answer.DOMAIN_LABELS`,
   `mcp_tool_domains`, `apply._is_report_hop`, `pending.py:142`, the sales addenda wording.
S6 R5a/b editor (after mock OK): chips, wired panel, preview toggle, variable picker, diff
   next/prev + counter + shortcuts + changes-only.

## Triggers deliberately not built

- Variables for other prompt keys: only `chatbot_semantic_parser` reads registries today.
- Per-variable formatting options: one format each until a second format is asked for.

## Grill (feature skill step 2, run LATE on 30 Sep 2026 after the owner's process audit)

The grill was not run before the build. It was run after the audit: every decision the lane
had taken alone went to the owner as one `crew-ask` on PR #1405 (comment 5914198889), each with
a recommendation. Answers are recorded here as they arrive. Until then, each recommendation stands. Every premise was re-checked against the code after the owner's rule of 30 Sep 2026 ("every statement grounded in file:line"); the two wrong ones (2, 7) are marked CORRECTED.

| # | Decision | Recommendation | Owner answer |
|---|---|---|---|
| 1 | Wording layer published unlabelled; the owner promotes (`pdyn_0002_wording_layer.apply`, no label row) | keep unlabelled (R3) | no answer: recommendation stands |
| 2 | CORRECTED. Teams: the lane matches `suggested_team` only against `ESCALATION_TEAMS` (`lanes/escalation.py:61-70`, `:1234-1261`), so `{{teams}}` from `agent_teams` could name codes the lane cannot route. Agents: `suggested_agent` goes out as `agent_code` to the round robin (`escalation.py:1547`, `:1579`), so `{{agents}}` from `access_agents` is right | teams = `ESCALATION_TEAMS` via `lane_vocabulary`; agents = `access_agents` | re-asked (comment 5914415234) |
| 3 | Access levels from `contact_access_types.name`, swapped only when they cover the 7 tier names. UNVERIFIED on prod: CI table empty | keep the guard | as recommended |
| 4 | Domain words = union of switch words and status words; measured +2,712 chars on the CI DB | union | no answer: recommendation stands |
| 5 | OUTPUT status enums list all 8 statuses; the mapping to `sales` is PENDING R7 | accept | no answer: recommendation stands |
| 6 | Sales addenda keep `domain_hint "order"` (constant; UNVERIFIED on prod v42) | code mapping only | owner: do NOT change his wording |
| 7 | CORRECTED. The plan-level reveal gate never runs (`turn_runtime.py:420`, `:451` grants None; `apply.py:2135`). The sales refusal is the business lane (`lanes/business/__init__.py:1558-1566`), unchanged. The `sales` row's `reveal_key` has no runtime effect today | nothing to decide | as recommended |
| 8 | `order` row keeps the 3 sales tools | remove in a follow-up | as recommended |
| 9 | Worker turns (`app/tasks/chat_turns.py:12`) converge within the 30s TTL; the API process clears at commit | 30s | as recommended |
| 10 | Code-constant publishers stand down. INCOMPLETE at first: `sales_s1_reports_module.py:121-149` was unguarded; guarded in the review round | accept | as recommended |
| 11 | Stale banner silenced for a wording-layer production | accept | as recommended |
| 12 | Brands not inserted. The per-turn line carries the contact's own companies' brands (`turn/context.py:100-116`, `head/parser.py:754`) | accept | as recommended |
| 13 | Wired panel and preview need `system.ai_assistant_settings.view`; the brand list is system-wide (raw SQL `_brands`) | accept | as recommended |
| 14 | Status Words page built without its own mock (clone of Chatbot Domains) | accept | as recommended |

## Process deviations and how each was closed (owner audit, 30 Sep 2026)

- **Red-first commit order.** S1 (R5c), S2, S3, S4 and the Status Words page were committed
  with their tests IN the same commit, so the commit order does not show red first. History
  is not rewritten (no force-push). Red was proven after the fact instead: each slice's test
  file was run against the code as it stood just before that slice:
  - R5c (7f004bf0): 3 of the 4 new tests fail on the old `SearchableTextarea`. The typing test
    reproduces the owner's bug as `'w a   b ne c'`.
  - S2 (427b309c) test file on 7e4affa3: collection error `cannot import name
    'ChatbotStatusWord'` (the model did not exist).
  - S3 (ef271758) test file on 427b309c: 11 failed, all `404 == 200/201/409/422/403` (the
    routes did not exist).
  - S4 (888f4ae3) test file on ef271758: 10 failed with `AttributeError`, because
    `wording_layer`, `is_wording_layer` and `publish_wording_edit` did not exist, and the
    migration published no version (`assert 5 == 4`).
  - Status Words page (b3a940d5): both vitest files fail when the service and the list are
    removed.
  R7 and R5a/b are committed red-test-first (`test(prompt-dynamic): red tests for ...`, then
  `feat(...)`).
- **Kill test** (captain's own, before the reviewer's independent one), each restored after:
  - AC-PD-1: the `after_commit` cache clear disabled. 4 tests go red (the committed-domain
    render, the cache test, and the API create and update/delete renders).
  - AC-PD-3/R3: the s4/s12 wording-layer guards disabled. The stand-down test goes red
    (`assert 5 == 4`).
  - AC-PD-7: the `{{statuses}}` substitution disabled. 3 drift tests go red.
  - AC-PD-10: the old `SearchableTextarea` effect restored. 3 find tests go red.

## Next lane (owner, 30 Sep 2026)

- Move `ESCALATION_TEAMS` (`app/services/chatbot/lanes/escalation.py:61-70`) into the
  `agent_teams` registry so teams become admin-editable end to end; `{{teams}}` then renders
  from that registry instead of the code list.
- Remove the three sales tools from the `order` row once `sales` has run a week (grill 8).
- The Prompts detail page overflows at 375px (document 1357px wide), measured identical on
  main b8cdbebe with this lane's files swapped out, so not this lane's defect: logged in
  `documentation/backlogs/backlog.md`.

## Browser evidence run (agent-browser 0.27.0, session `pdyn`, 30 Sep 2026)

Stack: the lane's sandbox, not the crew test copy (a cloud worker cannot reach it). Backend is
uvicorn :8000 on the private `sorento_ci` DB, bootstrapped by `scripts.bootstrap_env` with every
module installed; the frontend is `npm run dev` :3000. Login is a local superadmin
(`E2E_EMAIL`/`E2E_PASSWORD` in the gitignored `sorento_crm_frontend/.env.local`). Navigation
was by sidebar clicks from `/`.

1. 1280x800, `/`, then System > Messaging > **Status Words**. The URL is
   `/system-management/chatbot-status-words`, and the grid shows the 8 seeded rows with real data.
2. Row `sales_report`, then the modal: added the customer word "jualan bulan ini", then Save.
   The backend logged `PUT /api/v1/system/chatbot/status-words/<id>` 200, and the row's
   Customer words cell shows the new word.
3. Without a publish, `POST /ai-assistant/prompts/chatbot_semantic_parser/render-preview`
   on the v4 wording-layer template returns the word in `{{domain_words}}` and in the
   `sales_report` bullet, with 0 literal `{{` left. The version list is unchanged: v4 has no
   label and v3 is production.
4. AI Assistant > Prompts > chatbot_semantic_parser, then Ctrl+F on the editor, query
   "outstanding":
   - The count reads 1/107, the selection is [2739, 2750] = "outstanding", and scrollTop is 830.
   - Enter x3 gives 4/107. Shift+Enter gives 3/107, with the selection on [5483, 5494].
   - The active `<mark>` offsetTop is 2109, inside the visible range 1950-2268.
5. Caret at 5500, which is between match 3 (5483-5494) and match 4 (5524), then typed "ZZ ".
   The text reads `outstanding DO foZZ r 7445`, the caret moved to 5503, the find bar stayed
   open, and the count stayed 3/107. The owner's bug does not reproduce.
6. 375x812, same page: Enter moves to 4/107 and the active match is visible. The page itself
   is 1357px wide at 375. That overflow is identical with main b8cdbebe's files, so it is
   pre-existing: BL-068.

Screenshots (under 200 KB each): `documentation/plans/evidence/prompt-dynamic-status-words-1280.png`
and `documentation/plans/evidence/prompt-dynamic-search-375.png`.
