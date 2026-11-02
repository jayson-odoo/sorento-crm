# PLAN: the `mcp_tools` registry never syncs in the production image

Status: PR #2086 open, reviewer READY (one test fix + two comment nits applied in round 1),
waiting on CI and on the owner's run of the prod first-sync query (DEACTIVATE rows are an ask
before merge). Small fix track (no migration, no auth/RBAC/permission change, no new ingest
surface). #2085 merged as 56a48f0c02 and main is merged in.

Lane: MCP-REGISTRY-IMAGE. Base: main at 6c446ed8f6.

## Defect

`app/services/mcp_tool_registry_service.py:49-50` (`_load_specs`) imports
`sorento_crm_mcp.catalog` and `sorento_crm_mcp.module_loader`. The backend image is built with
`context: ./sorento_crm_backend` (`.github/workflows/deploy.yml:774`,
`sorento_crm/docker-compose.yml:31`), the Dockerfile copies only that context to `/app`, and
`requirements.txt` has never named the MCP package (`git log -S sorento_crm_mcp --
sorento_crm_backend/requirements.txt` is empty). The import fails, `app/main.py:450` logs
"Failed to sync MCP tool catalog at startup" and boot carries on. The module upload re-sync
(`app/services/module_upload_service.py:340-351`) fails the same way.

Since when: the boot sync landed 1 May 2026 (dac3ddf9b8); the build context has been
`./sorento_crm_backend` since 16 Jan 2026 (ea42a36a16). So the sync has never succeeded in any
deployed image. Whatever rows production holds did not come from the image (origin UNVERIFIED).

## What reads `mcp_tools` (and what users see)

Only two code paths read the table:

1. `GET /api/v1/system/mcp-tools` (`app/api/v1/system/mcp_tools.py:18-32`, active rows by
   default). Feeds System Management > MCP Tools
   (`sorento_crm_frontend/app/(protected)/system-management/mcp-tools/services/mcpAdminService.ts:18`)
   and the tool picker in the chatbot domain editor (`.../chatbot-domains/components/ChatbotDomainModal.tsx:99-102`).
   Stale table = the page and the picker show the wrong tool list: catalog tools added since the
   table was last written are missing, retired ones still listed.
2. Chatbot domain save validation (`app/api/v1/system/chatbot_config.py:188-199`, POST and PUT
   `/chatbot/domains`): every name in `tools` / `primary_tool` must have an `mcp_tools` row (any
   `is_active`), else 422 "Unknown MCP tool(s)". Stale table = an admin cannot save a domain that
   names a newer tool. Example on the dev copy `sorento_dev_1028` (prod-derived, 28 Oct; dev data,
   not prod): domains `order`, `sales` and `chat_analytics` name `crm_report_ask`, which has no row,
   so saving any of them returns 422.

Not readers (checked): the AI assistant settings tool list asks the live MCP server
(`ai_assistant_service.py:859`); the panel's tool pick ranks `ai_assistant_configs.enabled_tools`
(`ai_assistant_service.py:1537`); embeddings and capability docs load the code catalog
(`mcp_tool_capability_service.py:2035`); `restricted_fields` and `chatbot_domain` are written,
never read (`contact_field_reveal_service.py:17`, `McpTool.chatbot_domain` docstring). The boot
steps after the sync (`app/main.py:462-575`) do not read the table, so their writes do not change.

## What the first working sync writes on production

`sync_catalog` never deletes a row and never touches configs, embeddings or permissions. Per
catalog tool it inserts a row or overwrites `description`, `module_key`, `http_path`,
`http_method`, `restricted_fields`, `chatbot_domain`, `last_seen_at` and sets `is_active=true`;
then every active row whose name is not in the catalog is flipped to `is_active=false`
(`mcp_tool_registry_service.py:104-108`). A flipped row disappears from the MCP Tools page and the
domain picker; domain saves naming it still pass (validation ignores `is_active`).

Production's table is not visible to this lane. On the dev copy (already re-synced by local stacks,
last_seen 2 Nov, so it understates prod's drift): 164 rows, 47 active; a sync would add 8
(`crm_find`, `crm_procurement_grn_summary`, `crm_purchase_request_by_number`, `crm_report_ask`,
`crm_sales_analysis`, `crm_sales_opportunity_customer_options`, `crm_sales_opportunity_log`,
`crm_sales_target_progress`), update 47, deactivate 0, leave 117 inactive rows untouched.

The owner's exact answer for production: `mcp-registry-image-first-sync-prod.sql` beside this
plan, read-only, lists ADD / REACTIVATE / DEACTIVATE per tool against the catalog this PR ships.
Anything in DEACTIVATE is filed as an ask before merge.

## Fix

1. `_load_specs` reads `app.services.mcp_catalog_copy.CATALOG`, the backend's verbatim copy that
   #2085 added and pins byte-for-byte to the MCP file (`tests/test_mcp_catalog_in_image.py`). No
   second copy.
2. The `merged_catalog` overlay is dropped from the registry: no module ships
   `app/modules/<key>/mcp/tools.json` (`find sorento_crm_backend/app/modules -name tools.json` is
   empty), and the production MCP server, built from `./sorento_crm_mcp`, cannot see the backend's
   modules either (`module_loader._backend_modules_root` needs `CRM_BACKEND_MODULES_DIR`, set
   nowhere in compose or deploy.yml). So the registry then mirrors the catalog production's MCP
   server serves from. The module upload re-sync (`module_upload_service.py`) existed only for
   that overlay and is removed. Trigger to revisit: the first module that ships a `tools.json`, which needs a
   path into both images.
3. One `pg_advisory_xact_lock` at the top of `sync_catalog`. Production boots 4 gunicorn workers
   (`gunicorn.conf.py:54`) and each runs `startup_event` (`app/main.py:335`), so 4 syncs start at
   once; on the first deploy they all insert the same new names and all but one fail on the
   `tool_name` unique index (and concurrent syncs already deadlocked in CI, see the fixture note
   in `tests/test_mcp_tool_registry_service.py`). The lock makes them run one after another.
4. Stale comments: the `McpTool` `restricted_fields` and `chatbot_domain` docstrings,
   `chatbot_field_reveals.py` and `contact_field_reveal_service.py` (all said the sync never runs
   in the image).

## Tests (red first)

`tests/test_mcp_registry_in_image.py`:
- image layout (`sorento_crm_mcp` unimportable): `sync_catalog` on a blank schema writes one active
  row per catalog tool, `restricted_fields` included. Red today: ModuleNotFoundError.
- mechanism pin: the specs come from `mcp_catalog_copy.CATALOG`.
- two concurrent syncs on an empty table both succeed (second waits until the first commits).
  Red today: the second raises IntegrityError on `tool_name`.

Kill test: restore the old import, then drop the lock; the same tests go red.

## Not in scope

The 117 inactive rows on the dev copy stay (sync never deletes, by contract at
`mcp_tool_registry_service.py:9`). The never-read `chatbot_domain` column drop stays with the next
migration that touches `mcp_tools`.
