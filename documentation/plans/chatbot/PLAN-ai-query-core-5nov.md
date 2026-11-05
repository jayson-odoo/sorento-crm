# PLAN: AI-QUERY-CORE (phase 1 of the AI tools standard)

Status: in progress 5 Nov 2026 (Build). Track: full (multi-company reads, RBAC). Lane AI-QUERY-CORE.

Parent plan: `PLAN-ai-tools-standard-5nov.md` section 4 "QUERY-CORE" (branch `claude/ai-tools-scout-mcp-vea9ka`,
PR #2185). UAC: `ai-tools-standard-acceptance-criteria.md` AC-1, AC-2, AC-3, AC-6, AC-9.

## Scope

- `app/services/assistant_registry/` (core, no import of `app/services/chatbot`): `FieldDef`, `EntityDef`, the query
  compiler and runner, pilot entities `order`, `product`, `purchase_order`, `complaint`.
- `crm_query` and `crm_describe` agent tools (`app/services/chatbot/agent/query_tools.py`), run in process under
  `run_as_user`; offered to staff principals on the panel and to linked-user WhatsApp turns, never to a contact
  principal.
- Caps: 50 rows, 200 groups, `SET LOCAL statement_timeout = 5000`.
- The 12 tests of the parent plan's QUERY-CORE section.

Out: actions, `tools_search`, CI gate. No change to who holds the agent slug; `chatbot_agent_enabled` default unchanged.
