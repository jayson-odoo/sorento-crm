# PLAN: AI assistant 500, backend reads the MCP catalog that is not in its image

Status: in progress (small fix track: no migration, no auth/RBAC change, no new ingest surface;
the diff is large only because of one verbatim file copy)

Lane: ASSISTANT-CATALOG-500. Base: main at 5ac2eb7fa6.

## Incident

Production, 2 Nov 08:48 and 08:51 MYT: `POST /api/v1/system/ai-assistant/chat` returned 500
"Failed to chat with AI assistant" with
`FileNotFoundError: '/sorento_crm_mcp/sorento_crm_mcp/catalog.py'`, raised by
`app/services/mcp_tool_capability_service.py:2041` (`_load_catalog_specs`, :2035) after
`ModuleNotFoundError: No module named 'sorento_crm_mcp'`.

The function climbs to `Path(__file__).parents[3] / "sorento_crm_mcp"`. The backend image is built
with `context: ./sorento_crm_backend` (`.github/workflows/deploy.yml:2084`,
`sorento_crm/docker-compose.yml:31`), the Dockerfile copies that context to `/app`, so
`parents[3]` is `/` and the file does not exist. `requirements.txt` has no `mcp` or
`sorento_crm_mcp`. Dev and tests run in the monorepo, where the file exists, which is why nothing
caught it.

## Findings

### 1. Callers of `_load_catalog_specs` on production paths

| Path | Chain | Live on prod? | Fails now? |
|---|---|---|---|
| Assistant panel, old path (`respond()`), route `agent` without `skip_rag` (intents data_query, record_action, form_submit, definition, unknown) | `ai_assistant_service.py:1205` `_rag_select_tools` -> `:1549` `tool_keyword_rank.rank_tools` -> `tool_keyword_rank.py:50` `build_capability_documents` -> `mcp_tool_capability_service.py:2252` | yes, every panel user without `system.ai_assistant_chat.agent` (granted to nobody, #2060) | **yes, 500**: `_rag_select_tools` has no guard |
| Assistant panel, capability intent | `ai_assistant_service.py:1586` `_build_capability_answer` -> `:2196` `build_novice_capability_overview` -> `mcp_tool_capability_service.py:2525` -> `:2314` | yes | degraded, not 500: `:2195-2203` catches and returns a fixed sentence |
| MCP tool `crm_system_tool_capabilities_summary` and `/overview` | `app/api/v1/system/tool_capabilities.py:31,46` -> `:2314` | yes (X-API-Key, MCP catalog `catalog.py:1239`) | yes, 500 |
| Embedding backfill, source `mcp_tool` | `embedding_backfill_service.py:269` -> `:2252` | admin/task only | yes, raises |
| WhatsApp chatbot | none: `app/services/chatbot` never calls these (grep of `rank_tools`, `build_capability_documents`, `build_live_capability_summary`, `_rag_select_tools` returns no hit); its tool list is the frozen `CHATBOT_READ_ONLY_TOOLS` (`chatbot/lanes/business/fetch.py:1440-1475`) | yes | **not affected** |
| Panel new path (agent permission, `run_panel_turn`) | runs on the chatbot engine, same as above | granted to nobody | not affected |
| Startup | the four `*_bootstrap.py` only mention `_rag_select_tools` in comments | n/a | not affected |

### 2. Since when

Not today's release. `_rag_select_tools` used embedding search (`EmbeddingReadService.search_tool_candidates`)
until #1967 (`e86b459281`, LOOKUP-EMBED-CENTRAL, committed 30 Oct 02:27 MYT) switched it to
`tool_keyword_rank.rank_tools`, which reads the catalog. First production release carrying it:
`b07e71d5bf`, deploy run of 29 Oct 19:53 UTC (30 Oct 03:53 MYT); every later release, including
the previous production sha `7896f3ae75`, has it. In the range `7896f3ae75..5ac2eb7fa6` the only
change to `ai_assistant_service.py` is #2060 (`TOOLS_NEEDING_A_CONTACT`, `ensure_enabled`), which
does not touch tool selection. So every panel data question has returned 500 for about three days.
The capability summary endpoint has failed for as long as it has read the catalog this way.

### 3. Other runtime reads outside the backend

- `app/services/mcp_tool_registry_service.py:49-50` `_load_specs` imports `sorento_crm_mcp.catalog`
  and `sorento_crm_mcp.module_loader.merged_catalog`; called on every boot (`app/main.py:437-451`)
  and after a module upload (`module_upload_service.py:340-353`). Both callers log and continue, so
  no crash, but the `mcp_tools` table never syncs in production. **Not fixed here**: making it sync
  changes production data on the next boot (new rows, deactivations, `restricted_fields`), which is
  owner-visible behaviour, and it also needs `module_loader`. Follow-up lane recommended.
- `module_upload_service.py:53-55`, `module_export_service.py:34-36` `_frontend_root()` climbs to
  `sorento_crm_frontend`; returns `None` when absent, so upload/export skip frontend files in prod.
  Degrades by design; not fixed here.
- `alembic/versions/108_...py:25-31` reads a repo-root `docs/workflow-seeds/...json` (moved to
  `documentation/`); only on a fresh DB without the row. Out of scope, reported.

Everything else that climbs paths stays inside `sorento_crm_backend/` and is in the image.

## Architecture

- Layer: backend service (`app/services`). The MCP package stays the single source of truth for the
  catalog.
- Mechanism: the backend carries a **verbatim copy** of `sorento_crm_mcp/sorento_crm_mcp/catalog.py`
  at `app/services/mcp_catalog_copy.py` (the file imports only `dataclasses`). `_load_catalog_specs`
  returns the copy's `CATALOG`; no `sys.path` edit, no file read outside the image. This is the
  pattern `chatbot/lanes/business/fetch.py:1440-1460` set for the chatbot allow-list (a backend-side
  literal, pinned to the catalog by a CI test), applied to the whole file so nothing is projected
  or regenerated.
- Drift guard: a backend test asserts the copy is byte-identical to the MCP file (skips only where
  the MCP tree is absent, i.e. inside the image). The failure message prints the one `cp` command.
  The pre-push hook gets the same `cmp` when either file is in the push, because the catalog changes
  about 30 times a month and PR CI only selects backend tests for backend code changes, so a
  catalog-only PR would otherwise first meet the guard at release.
- Degrade: `_rag_select_tools` catches any exception from ranking, logs it with the stack, and
  returns no tools, so the turn answers without tools instead of a 500.
- Classes fixed: every runtime caller of `_load_catalog_specs` (panel ranking, capability summary,
  overview, embedding backfill, the seed and eval scripts), not only the panel turn.
- Not done: no change to the MCP package or its image, no new dependency, no migration, no change to
  `mcp_tool_registry_service` (see finding 3).

## Tests (red first)

New `sorento_crm_backend/tests/test_mcp_catalog_in_image.py`:
1. Image layout: block `sorento_crm_mcp` imports (`sys.modules[...] = None`) and relocate the
   service module's `__file__` to `/app/app/services/...` (the image path). `build_capability_documents`,
   `build_live_capability_summary` and `rank_tools` must work. Red today with
   `FileNotFoundError: ... '/sorento_crm_mcp/sorento_crm_mcp/catalog.py'`.
2. Copy equals the MCP catalog byte for byte (red today: copy missing).
3. `_rag_select_tools` with a ranking that raises returns `([], [])` and logs (red today: raises).
4. In-image guard: `tests/test_lessons_learnt_regressions.py` (run inside the built image by the
   build job's executing gate, `deploy.yml` "Pytest regression guards") gets a case that builds the
   capability documents with no patching, so an image without the catalog fails CI.

Also run: panel tests (`tests/chatbot/test_panel_*.py`), `tests/chatbot/test_import_boundary.py`,
`tests/chatbot/test_tool_pool_is_read_only.py`. Docker build of the backend context and an import
inside it if the Mac's Docker runs (it was not running at plan time: no `/var/run/docker.sock`).

## Guide

guide: n/a (no user-visible change beyond the 500 going away).
