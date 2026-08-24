# Status engine adopted as CORE, with entity-default graphs overridable per template

Sorento's statuses are hardcoded strings scattered across complaints, PR/SF, stock inquiries
and orders, plus an orphan `workflow_stages` table (0 rows) left behind by a deleted module.
The Project Sales module needs configurable pipeline stages, so rather than adding a seventh
private status vocabulary we are porting the `status_engine` from `foundryx-shared-service`
(`statuses` + `status_transitions` + a code-side entity registry) into sorento as a **core,
always-on** capability - not a toggleable module, because it is plumbing that other modules
will depend on. `workflow_stages` is dropped.

Each registered entity carries a **default** status graph; a Project Template may **override**
it, forking its own graph copy-on-write. Templates that never override keep inheriting. This
is a middle path between the shared-service's unscoped graphs and `dreamz_ems`'s
always-scoped-per-template graphs, and it means a Property Development template and a
Renovation template can have different ladders while most templates configure nothing.

## Consequences

- Cross-template pipeline reporting groups by **`key`**, never by status id - a forked graph
  has different ids for the same rung. `key` is documented in the source as *"machine key,
  stable per entity_type"* and is part of the `(entity_type, tenant_id, scope_id, key)` unique
  constraint, so the same rung carries the same key across every fork.
  **Not `category`** - the source model marks it a *"LEGACY cosmetic mirror … behavior
  branches on the trait flags below, never here"*, and reporting on it would resurrect a field
  its author deliberately demoted. It stays nullable and cosmetic.
- Statuses are **global**, not `CompanyScopedMixin`. SRT and MOCHA share one pipeline
  definition; per-company graphs would double the config surface for no current benefit.
  The source's `tenant_id` column comes across but stays on the stub tenant.
- All ported PKs and FKs are `UUID(as_uuid=False)`, **not** the source's `Column(String)` - 
  the uuid-id principle. The pg-UUID-vs-varchar drift is what broke `user_sessions.id` auth on
  production.
- The rule engine is a hard dependency (transition `conditions_json`). It is already ported
  into sorento but currently lives on the unmerged `feat/promo-expiry-rule-engine` branch,
  which must land first. `aggregates.py` still needs porting for aggregate-based auto edges.
- `project` is entity #1 and `project_task` is entity #2 (slice S2b) - the engine gets a
  second real consumer immediately rather than a year later. Existing hardcoded statuses
  elsewhere are **not** migrated now; they migrate entity by entity, later, deliberately.
- v1 ships manual transitions plus one auto edge (first PO recorded → Won). Time-based sweeps
  and the drag-and-drop graph editor are deferred.

## Rejected

- **Extending `workflow_stages`** - cheaper and already sorento-native, but it has no
  transitions, no conditions and no registry, so we would re-solve all of that later and
  maintain two divergent status engines across foundryx repos permanently.
- **Full port including derived edges, time sweeps and the graph editor** - the port would
  have become the project and the client's module would slip behind it.
