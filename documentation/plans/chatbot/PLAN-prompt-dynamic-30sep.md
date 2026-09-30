# PLAN - parser prompt wired to its registries + prompt editor that shows it (PROMPT-DYNAMIC)

Status: Build. Track: full (migration, new admin table, new admin page). R5c shipped (7f004bf0);
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
D2 **Variables** (module `app/services/chatbot/prompt_registry_vars.py`, one entry each: name,
   label, source table, admin href, `render(db) -> str`, `rows(db)` for the panel):
   `domains` (names, sort_order, ` | ` joined), `domain_words` (switch words of every domain,
   then status trigger words, de-duplicated, `, ` joined), `domains_detail` (today's
   `domain_line` per row), `statuses` (the bullets, per domain, from the new status table),
   `status_values` (`a|b|c` of every status value), `entity_kinds` (`a|b|c`),
   `entity_kinds_detail` (today's kind lines), `specs` (`specification_lines`), `brands`
   (`Name (CODE), ...`, active brands), `teams` (`a|b|c`), `agents` (`a|b|c`), `access_levels`
   (JSON list of active `contact_access_types.name` by sort_order).
D3 **Teams and agents render from the tables, never from a new code list.** `teams` = distinct
   `agent_teams.code` of active agents, ordered by `ESCALATION_TEAMS` position then name;
   `agents` = active `access_agents.code`. Empty table (CI) falls back to the code constants so a
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
D7 **Wording migration (R1).** `prompt_dynamic_0001` reads the `production`-labelled template
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
