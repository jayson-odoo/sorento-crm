# MCP Tool Catalog + AccessAgent Tool Ownership + Per-Call Guard - Design

**Status:** Draft for review
**Date:** 2026-05-01
**Owner:** jayson
**Related:** `documentation/superpowers/specs/2026-04-30-lookup-sets-design.md`,
`sorento_crm_mcp/sorento_crm_mcp/server.py`,
`sorento_crm_backend/app/models/access.py`

---

## 1. Problem

The MCP server (`sorento_crm_mcp`) exposes ~150 read-only tools that mirror
backend GET endpoints. Today the server only checks a single shared
`X-API-Key` header - it has no concept of *which user is calling* or *which
tools that user should be allowed to invoke*. There is no DB table that lists
the registered MCP tools, and no link between MCP tools and the existing
`access_agents` model (which already groups contacts via
`contact_agent_access` and orchestrates multi-tier escalation via
`agent_teams`).

Result: any caller with the API key can invoke any tool. As tools become
write-capable or surface privileged data (financial, customer-PII), the lack
of per-contact authorisation is a hard blocker.

We need:

1. A persisted catalog of MCP tools that mirrors the code catalog and stays
   in sync as modules are uploaded / removed.
2. An ownership link between `access_agents` and tools - **each tool belongs
   to at most one agent** (N:1). Surfaced on the AccessAgent edit form as a
   multi-select; selecting a tool already owned by another agent reassigns
   it (with explicit warning in the picker label).
3. A runtime guard at the MCP server that requires `contact_id` + `space_id`
   on every tool call, validates `(tool, contact, space)` against the
   agent ownership, and refuses with a deterministic verbatim message when
   denied.

## 2. Goals

- Single source of truth: code catalog (`catalog.py:CATALOG` + per-module
  `mcp/tools.json`) is authoritative; the DB table is a materialised view.
- Zero manual sync - auto-runs on backend startup and after every module
  upload (which is when `tools.json` slices change).
- Mandatory `contact_id` + `space_id` on every MCP tool call. Backend
  performs the actual access decision; MCP server just enforces presence and
  caches the answer briefly.
- Deny replies use the user-supplied verbatim phrasing so calling LLMs
  surface the correct message back to end users.
- Audit trail of every allow/deny decision for debugging and compliance.

## 3. Non-goals

- Replacing the shared `X-API-Key` between MCP server and backend. The
  X-API-Key still authenticates server-to-server; the new check authorises
  the *end contact* on top.
- Per-tool RBAC roles independent of access agents. Agents are the unit of
  authorisation in this design.
- Any change to `EXTERNAL_API_KEY_ACT_AS_USER_ID` semantics for routes
  unrelated to MCP.
- Soft delete of tools or agents. Hard delete via existing CASCADE rules.

## 4. High-level architecture

```
┌──────────────────────────────┐         ┌──────────────────────────────┐
│ MCP server (sorento_crm_mcp) │         │ Backend (sorento_crm_backend)│
│ ─────────────────────────────│         │ ─────────────────────────────│
│ _compile_tool() injects      │ HTTPS   │ POST /system/mcp-access/    │
│   contact_id, space_id args  ├────────►│   check                      │
│ Calls /mcp-access/check      │         │   { tool_name, contact_id,  │
│   before forwarding tool req │◄────────┤     space_id }              │
│ TTL 60s in-memory cache      │ allow/  │   → { allowed, agent_name, │
│                              │  deny   │       decision }            │
└──────────────────────────────┘         │                              │
                                         │ Catalog sync (startup +     │
                                         │   module upload)             │
                                         │   reads code catalog +      │
                                         │   per-module tools.json     │
                                         │   → upserts mcp_tools rows  │
                                         │                              │
                                         │ Tables: mcp_tools            │
                                         │   (with owner agent_id FK), │
                                         │   mcp_access_log             │
                                         └──────────────────────────────┘
```

Key resolution chain (N:1 ownership):

```
caller → contact_id (= respond_io_id), space_id (= respond_workspace_id)
       → respond_contacts.id (lookup by respond_io_id + respond_workspace_id)
       → contact_agent_access.agent_id (set of agents this contact may use)
mcp_tools.agent_id  (single owner; NULL if unassigned)
       → allow iff mcp_tools.agent_id ∈ contact's agent set
```

## 5. Data model

Two new tables. All live in the platform `base` module (matches where
`access_agents` already lives in `app/models/access.py`).

```sql
CREATE TABLE mcp_tools (
  id UUID PRIMARY KEY,
  tool_name TEXT UNIQUE NOT NULL,            -- e.g. "crm_master_products_list"
  description TEXT,
  module_key TEXT,                           -- empty for legacy / unbound tools
  http_path TEXT NOT NULL,
  http_method TEXT NOT NULL DEFAULT 'GET',
  agent_id UUID NULL REFERENCES access_agents(id) ON DELETE SET NULL,
                                              -- single owner agent; NULL = unassigned
  is_active BOOLEAN NOT NULL DEFAULT true,   -- false → tool removed from code catalog
  last_seen_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX ix_mcp_tools_module_key ON mcp_tools(module_key);
CREATE INDEX ix_mcp_tools_is_active ON mcp_tools(is_active);
CREATE INDEX ix_mcp_tools_agent_id ON mcp_tools(agent_id);
```

(No separate link table - ownership is a single FK column on `mcp_tools`.)

```sql
CREATE TABLE mcp_access_log (
  id UUID PRIMARY KEY,
  tool_name TEXT NOT NULL,
  contact_external_id TEXT,                  -- respond_io_id as supplied
  respond_contact_id TEXT,                   -- resolved id, NULL on miss
  respond_workspace_id UUID,
  decision TEXT NOT NULL,                    -- 'allow' | 'deny_no_access'
                                             -- | 'deny_tool_unlinked'
                                             -- | 'deny_unknown_tool'
                                             -- | 'deny_unknown_contact'
  matched_agent_id UUID,                     -- on allow
  ts TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX ix_mcp_access_log_ts ON mcp_access_log(ts);
CREATE INDEX ix_mcp_access_log_tool_name ON mcp_access_log(tool_name);
```

SQLAlchemy models added to `app/models/access.py`:
`McpTool` (with `agent = relationship("AccessAgent", back_populates="mcp_tools")`)
and `McpAccessLog`. `AccessAgent` grows
`mcp_tools = relationship("McpTool", back_populates="agent")` (no cascade - 
deleting an agent sets its tools' `agent_id` to NULL via the FK rule).

## 6. Catalog sync

New service `app/services/mcp_tool_registry_service.py` exporting
`sync_catalog(db: Session) -> SyncReport`.

Algorithm:

1. `sync_started_at = utcnow()`.
2. Import the live code catalog:
   ```python
   from sorento_crm_mcp.catalog import CATALOG
   from sorento_crm_mcp.module_loader import merged_catalog
   specs = merged_catalog(CATALOG)   # already overlays per-module tools.json
   ```
3. For each `ToolSpec`: upsert by `tool_name` (Postgres
   `ON CONFLICT (tool_name) DO UPDATE`). Fields touched on update:
   `description`, `module_key` (defaults to `""`), `http_path`,
   `http_method`, `is_active=true`, `last_seen_at=sync_started_at`.
   **Do NOT touch `agent_id` on update** - admin-set ownership must
   survive every catalog sync.
4. After the upsert pass, mark stragglers:
   `UPDATE mcp_tools SET is_active=false WHERE last_seen_at < :sync_started_at`.
5. Return counts (`added`, `updated`, `deactivated`) for logging.

Triggers:

- `app/main.py` startup event calls `sync_catalog()` once.
- `app/services/module_upload_service.py::install_uploaded_zip()` calls
  `sync_catalog()` after `_run_alembic_upgrade()` (newly-extracted module's
  `mcp/tools.json` is now on disk and `merged_catalog` picks it up).

The MCP server itself never writes the table - its in-memory `CATALOG +
merged_catalog` is the source.

## 7. MCP server guard

Modify `sorento_crm_mcp/server.py::_compile_tool`:

- Inject `contact_id: str` and `space_id: str` as the first two parameters
  of every generated `_impl_*` function (always required, no defaults).
- Add a precheck before the existing `_required` validation:
  ```python
  decision = await _check_access(client, _spec.name, contact_id, space_id)
  if not decision["allowed"]:
      return json.dumps(_deny_payload(decision))
  ```
- `_check_access` lives in a new `sorento_crm_mcp/access_guard.py`. It posts
  to `POST /api/v1/system/mcp-access/check` (with the existing X-API-Key
  header), wraps the call in an `asyncio.Lock`-guarded TTL cache (60s,
  keyed on `(tool_name, contact_id, space_id)`).
- `contact_id` and `space_id` are guard-only by default. Strip them from
  the outgoing query dict unless the spec already declares either as a
  query param (forms scope tools listed in `TOOL_REQUIRED_QUERY_HINTS`
  already accept them as filters).

Deny payloads - verbatim user phrasing, JSON-wrapped:

```json
// Case 1: tool owned by an agent, but contact is not under that agent
{
  "error": "ACCESS_DENIED",
  "code": "CONTACT_NOT_AUTHORIZED",
  "message": "you are not allowed to access this function: <agent_name>",
  "agent_name": "<agent_name>"
}

// Case 2: tool exists but agent_id is NULL (unassigned)
{
  "error": "ACCESS_DENIED",
  "code": "TOOL_NOT_LINKED",
  "message": "the required tools are not linked to any supported agents in the system",
  "agent_name": null
}

// Case 3: tool name not in mcp_tools or is_active=false
{
  "error": "ACCESS_DENIED",
  "code": "UNKNOWN_TOOL",
  "message": "the required tools are not linked to any supported agents in the system",
  "agent_name": null
}

// Case 4: contact_id+space_id resolves to no respond_contacts row
{
  "error": "ACCESS_DENIED",
  "code": "UNKNOWN_CONTACT",
  "message": "you are not allowed to access this function: <agent_name>",
  "agent_name": "<agent_name>"
}
```

`<agent_name>` is the single owning agent's display name (only one - N:1).
Same value returned in `agent_name` for programmatic use.

Allow path: tool runs as today, `contact_id`/`space_id` consumed by guard
only (not forwarded unless the spec declares them as query params).

## 8. Backend access-check endpoint

New router file `app/api/v1/system/mcp_access.py` mounted under
`/api/v1/system/mcp-access`. Guarded by the existing X-API-Key
dependency (no module guard - platform-level).

```python
class McpAccessCheckIn(BaseModel):
    tool_name: str
    contact_id: str        # respond_io_id
    space_id: str          # respond_workspace_id (UUID-as-str)

class McpAccessCheckOut(BaseModel):
    allowed: bool
    decision: Literal[
        "allow", "deny_no_access", "deny_tool_unlinked",
        "deny_unknown_tool", "deny_unknown_contact",
    ]
    agent_name: str | None              # owner agent display name; NULL when tool unassigned

@router.post("/check", response_model=McpAccessCheckOut)
def check(payload: McpAccessCheckIn, db: Session = Depends(get_db)) -> McpAccessCheckOut:
    ...
```

Decision logic in `app/services/mcp_access_service.py::evaluate(...)`:

1. `tool = SELECT t.id, t.agent_id FROM mcp_tools t
   WHERE t.tool_name=:n AND t.is_active=true`.
   Miss → log `deny_unknown_tool`, return `agent_name=NULL`.
2. If `tool.agent_id IS NULL` → log `deny_tool_unlinked`,
   return `agent_name=NULL`.
3. `owner = SELECT id, name FROM access_agents
   WHERE id=tool.agent_id AND is_active=true`. Miss
   (deactivated owner) → log `deny_tool_unlinked`,
   return `agent_name=NULL`.
4. `contact = SELECT id FROM respond_contacts
   WHERE respond_io_id=:c AND respond_workspace_id=:s`. Miss →
   log `deny_unknown_contact`, return `agent_name=owner.name`.
5. `granted = EXISTS (SELECT 1 FROM contact_agent_access
   WHERE respond_contact_id=contact.id AND agent_id=owner.id
   AND is_allowed=true
   AND (valid_to IS NULL OR valid_to > now())
   AND (valid_from IS NULL OR valid_from <= now()))`.
6. If granted → log `allow`, `matched_agent_id=owner.id`,
   return `agent_name=owner.name`. Else → log `deny_no_access`,
   return `agent_name=owner.name`.

Every branch writes one `mcp_access_log` row in the same transaction as the
read so audit cannot drift from the answer.

## 9. AccessAgent ↔ MCP tool admin endpoints

Two new routes under `/api/v1/access-agents/{agent_id}/mcp-tools`:

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET    | `/{agent_id}/mcp-tools` | - | `[{tool_id, tool_name, description, module_key}]` (tools whose `agent_id = :agent_id`) |
| PUT    | `/{agent_id}/mcp-tools` | `{tool_ids: [UUID]}` | `[{...}]` (full new set for this agent) |

`PUT` semantics - single transaction:

1. `UPDATE mcp_tools SET agent_id = :agent_id WHERE id IN :tool_ids`
 - claims every selected tool for this agent (reassigns from any prior
   owner). Each reassignment is logged in a structured backend log
   (`logger.info("mcp tool reassigned", tool_id, from_agent, to_agent)`)
   so admins can trace ownership moves.
2. `UPDATE mcp_tools SET agent_id = NULL WHERE agent_id = :agent_id
   AND id NOT IN :tool_ids` - releases tools previously owned by this
   agent that are no longer selected.

Plus a list endpoint for the picker:

| Method | Path | Returns |
|--------|------|---------|
| GET    | `/api/v1/system/mcp-tools?is_active=true&limit=500` | `[{id, tool_name, description, module_key, current_agent_id, current_agent_name}]` - `current_agent_*` populated when tool is owned by another agent so the UI can warn before reassignment. Grouped client-side by `module_key`. |

## 10. UI - AccessAgentForm

`sorento_crm_frontend/app/(protected)/user-management/access-agents/components/AccessAgentForm.tsx`
grows one new card after the existing "Team Assignments" card, **edit mode
only** (parallels the team assignments treatment which is also edit-only):

```tsx
{isEditMode && accessAgentId && (
  <Card>
    <CardHeader>
      <CardTitle>MCP Tools</CardTitle>
    </CardHeader>
    <CardContent>
      <McpToolSelector
        value={selectedToolIds}
        onChange={setSelectedToolIds}
        disabled={isLoading}
      />
    </CardContent>
  </Card>
)}
```

`McpToolSelector` is a new component:

- Loads `GET /api/v1/system/mcp-tools?is_active=true` once via a
  `useMcpTools()` query hook.
- Loads existing linkage via `useAgentMcpTools(agentId)` and seeds
  `selectedToolIds`.
- Renders a searchable, grouped multi-select. Group header = `module_key`
  (or "Unbound" when empty); each row shows `tool_name` + truncated
  `description` with `title` tooltip.
- For tools whose `current_agent_id` is set and != the agent being edited,
  render a "currently owned by &lt;agent_name&gt; - selecting will reassign"
  badge next to the tool name, and require a `confirm()` step before the
  PUT submits if any reassignments are pending. This makes the N:1 move
  explicit instead of silent.
- On submit, after `updateMutation`, call
  `setAgentMcpTools(agentId, selectedToolIds)` (parallel to existing
  `setAgentTeams`).
- Empty state: "No MCP tools registered yet - modules with `mcp/tools.json`
  populate this list on upload."

CLAUDE.md mandates `<SearchableSelect>` for FK pickers, but that primitive
is single-value. We add a sibling `<SearchableMultiSelect>` modelled on it
(same Radix Combobox + checkbox rows + chip display), or reuse an existing
multi-select if `npm run` reveals one. Decision deferred to implementation
plan - interface above is independent of that primitive.

## 11. Migration

Single Alembic revision in `app/alembic/versions/` (matches where
`access.py` tables were originally migrated - we don't move them into a
per-module migration just for this change). Revision creates the two new
tables (`mcp_tools`, `mcp_access_log`) and indexes from §5. No data
backfill (catalog sync seeds rows on first boot).

Down-revision drops the two tables in reverse order
(`mcp_access_log`, `mcp_tools`).

## 12. Testing

Backend:

- `tests/services/test_mcp_tool_registry.py`
 - First sync inserts every `ToolSpec` with `is_active=true`,
    `agent_id=NULL`.
 - Second sync with one tool removed flips that row to `is_active=false`.
 - Re-adding a tool flips it back to `is_active=true`.
 - Sync **preserves** `agent_id` set by an admin between runs.
- `tests/services/test_mcp_access_service.py` covers all five decision
  branches with explicit fixtures.
- `tests/api/test_mcp_access_check.py` integration: hits the FastAPI
  endpoint with X-API-Key, asserts response shape + `mcp_access_log` row.
- `tests/api/test_access_agent_mcp_tools.py` for GET/PUT ownership routes:
 - Selecting a tool currently owned by another agent reassigns it
    (`agent_id` flips to the new owner; old agent's GET no longer lists it).
 - Removing a tool from an agent's set sets its `agent_id` to NULL.

MCP server:

- `sorento_crm_mcp/tests/test_access_guard.py`
 - Patches the backend access-check to return allow → tool executes.
 - Patches deny case 1 (no access) → returns verbatim Case 1 payload,
    underlying CRM client never called.
 - Patches deny case 2 (unlinked) → returns Case 2 payload.
 - TTL cache: second call within 60s does not re-hit backend; after
    `time.monotonic` advance, re-hits.
 - Missing `contact_id` or `space_id` → MCP raises `ValueError` before
    backend call.

Frontend:

- `vitest` test for `McpToolSelector`: seeds initial selection, toggles
  tool, verifies submit posts the full set.

## 13. Open questions / risks

- Catalog drift if a tool exists in code but its module is removed
  mid-deployment. Mitigation: sync runs on startup and module upload; the
  `is_active=false` flag and `agent_name` deny payload make it
  visible. If a tool is renamed in code without a migration, the old name
  stays in the table as `is_active=false`; any agent linkage on the old id
  becomes dead - accepted, since renames should be rare and the UI shows
  inactive tools as crossed-out.
- 60s cache means revoking access takes up to a minute to take effect on
  active MCP sessions. Acceptable for the current threat model. A
  `DELETE /system/mcp-access/cache` admin endpoint can be added later if
  needed; not in v1 scope.
- N:1 means a tool reassignment is destructive to the previous owner.
  Mitigation: UI badge + `confirm()` on reassignment (§10) and structured
  log on every reassignment (§9) so audits can reconstruct ownership
  history. Owners can also be discovered via `current_agent_id` on the
  picker endpoint before save.
- Performance: each MCP call adds one round-trip to backend on cache miss.
  Backend access-check is a single short transaction (3 indexed lookups).
  Profiled budget: <5ms backend + <20ms HTTP. Acceptable for read-only
  tools that already round-trip the backend for the actual data.

## 14. Phased rollout

- **Phase 1 - Tables + sync.** Migration + `mcp_tool_registry_service` +
  startup hook + module-upload integration. Catalog populates; nothing
  enforces yet. Ship + verify rows match `merged_catalog(CATALOG)`.
- **Phase 2 - Access-check endpoint + admin routes + UI card.** Backend
  endpoint + `/access-agents/{id}/mcp-tools` GET/PUT + UI card. Admins can
  link tools but no enforcement on MCP traffic. Ship + verify linkage UX.
- **Phase 3 - MCP guard.** Modify `_compile_tool` to require
  `contact_id`/`space_id` and call the access-check. Cache + deny payload.
  Ship + watch `mcp_access_log` for unexpected deny patterns. Roll back is
  a single MCP-server revert.
- **Phase 4 - Cleanup.** Remove forms-scope `TOOL_REQUIRED_QUERY_HINTS`
  for `contact_id`/`space_id` since the guard now enforces them globally
  (the existing per-tool list becomes redundant for those two keys). Keep
  the hint mechanism for any other required params.

Each phase has its own implementation plan and PR.
