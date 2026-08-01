# How an entity joins the status engine

**Status:** Accepted 2026-08-01. Extends `0001` (status engine is core) and `0012` (adopt, do not re-port).
Binding on every future entity registration.

## Why this exists

Within one slice the engine acquired **two** registration patterns, for good reasons in both cases:

- `project`, `project_task`, `project_lead` and `workflow_submission` are **FK-based**: a `status_id` column
  pointing at `statuses.id`.
- `complaint` is **key-valued**: `complaints.status` is a `VARCHAR(50)` holding the status key itself, with no
  FK and no CHECK, and it predates the engine by 300-odd migrations.

Two patterns with no written rule is how a codebase ends up with five. The next person registering an entity
has no way to know which is correct, and the wrong choice is expensive in opposite directions: an unnecessary
data migration on one side, a permanent second-class citizen on the other.

## The rule

### 1. A new table is FK-based. No exceptions.

`status_id`, `UUID(as_uuid=False)`, `ForeignKey("statuses.id")`, NOT NULL, resolved from the graph's initial
status for that record's scope at creation time.

A new table has no legacy excuse. Choosing a key column for a new table buys nothing and permanently costs the
FK, the referential integrity, and the ability to rename a status without a data migration.

### 2. A pre-engine table with a key column uses the adapter, and that is a bridge, not a home.

`assert_transition_allowed_by_key(db, entity_type, from_key, to_key, scope_id=None)` resolves both ends via
`StatusGraph.by_key` and delegates to the id-based guard, so **the authority is never duplicated**. Register
with `status_attr` naming the key column.

This is legitimate, not a hack: converting `complaints.status` to an FK would touch every site that branches on
the string by name (and `complaint_fulfilment_service` branches on `processed_by_cs` / `fulfilled`), which is
precisely the change that would stop the registration being a behavioural no-op. Adopting the engine and
migrating the column are two different risks and must not be taken in one slice.

**But state the exit.** A key-valued entity stays key-valued only while the cost of conversion exceeds the cost
of carrying it. The trigger to convert is any of: the vocabulary needs a rename; a second consumer needs to join
against status metadata; or the by-name branches are being removed anyway for another reason. Conversion is its
own slice with its own gate, never a rider on a feature.

### 3. Reporting groups by `key`. Never by id, never by `category`.

A forked graph re-keys ids for the same rungs, so grouping by id silently splits one pipeline rung into two
columns. `category` is a legacy cosmetic mirror that ADR-0001 demoted; nothing may branch on it. The engine
itself must not even mention it, and there is a test that greps for the string to keep that true.

### 4. Per-owner graph variation uses `scope_resolver`, not a new entity type.

If two records of the same kind need different states, that is a **scope fork**, not a second entity type.
`scope_resolver(record) -> scope_id | None` covers both the direct case (`lambda s: s.definition_id`) and the
indirect one (a task whose graph belongs to its project's template). `None` resolves the default graph.

Minting `exchange_request_submission` and `service_complaint_submission` as separate entity types to get
different states is the failure this rule prevents: it multiplies the registration surface, splits reporting,
and each new form type becomes code again instead of configuration.

The corollary: **a default graph should be minimal.** Every real variation forks. A default that grows to
satisfy each new consumer becomes a union of everything and describes nothing.

### 5. Exactly one `is_initial` per graph. Multiple entry points are expressed some other way.

Not a style preference: `status_service.validate_graph` raises `status_graph_multiple_initial`, and the statuses
API calls it after **every** status and transition write. A graph seeded with two initial rows does not merely
resolve arbitrarily, it **422s the first edit an admin makes** to any status of that entity.

Complaints genuinely have two entry points (`draft` from the portal, `new` from the column default on every API
and n8n create). The resolution: `is_initial` and `is_default` on the one a bare create lands on, the other
declared in an entity-level constant, and a test pinning `initial_status(...).key` against the column default so
the engine and the column cannot drift apart.

Do **not** invent an edge between two entry points to satisfy a reachability check. An edge that no code
performs is false documentation, and it will be read as intent later.

### 6. `count_records` and `migrate_records` are not optional, and must be honest.

They back "block delete if referenced" and "migrate records". An entity that under-reports its own usage lets an
admin delete a status out from under live records. For a key-valued entity these count and rewrite by the
**key** the status row carries, not by its id.

### 7. A guard on the action routes is not a guard.

**This is the lesson that cost the most to learn.** `complaints` had five well-behaved action routes
(`/approve`, `/reject`, `/process`, `/close`, `/void`) and **two** generic write paths that applied a bare
`Optional[str]` status through a blind `setattr` loop. Guarding only the action routes would have produced a
status engine that was documentation rather than enforcement, while looking complete.

So: registering an entity means guarding **every** path that writes the status column, and the way you find them
is to grep for writes to the column, not to enumerate the routes you know about. There were two, and the second
(`update_complaint_and_reply`) was found only because someone went looking after the first was fixed.

### 8. Guards on a legacy column need fail-open escapes, chosen deliberately.

Two, both load-bearing, both discovered by asking what a guard would newly reject:

- **A write repeating the status the record already holds is not a transition** and must be skipped. This
  matters more than it looks: such a write leaves no audit diff, so it is invisible to any historical evidence
  used to argue the guard is safe.
- **An unseeded graph makes the guard inert.** Failing closed there rejects every status write on a deploy
  where the code lands before the seed migration.

### 9. Prove a "no-op" registration against history, not against reasoning.

Before guarding a legacy write path, aggregate what has actually happened. For complaints that meant every
status change in `audit_logs` across 1.87M rows: **11** distinct `from -> to` pairs, all declared edges except
one documented outlier. That is evidence a guard rejects only a class of call with no history. "The frontend
never sends it" is a weaker claim, because the frontend is not the only caller.

### 10. Seeds converge, they do not insert-if-absent.

A seed is "set where mismatch": a re-run repairs a drifted label, colour or flag in place. Insert-if-absent can
never correct a prior bad run, which is the standing rule for backfills in this repo and applies identically to
graph seeds. Seed via the same function the application and tests use, called from the migration, so the graph
cannot drift between what a test asserts and what a deploy creates.

### 11. One status trail. Reuse `audit_logs`; do not build a second table.

Auditing here is declarative: a model sets `__audit_track__ = True` and `__audit_entity_type__`, and flush
listeners capture `old_values` / `new_values` for every tracked column. So a status change on an audited entity
is **already** recorded, with actor, timestamp, trace_id, contact attribution and company scoping. That is why
complaints need no bespoke history table.

**Amended 2026-08-01, after F1.** The original wording banned a companion table outright and told you to put
the edge and remark on the entity as columns. That was too absolute, and the alternative was worse: a
submission has one current status but many transitions, so carrying the edge on the entity means `last_edge` /
`last_remark` columns whose only purpose is to be diffed out of a JSONB audit row. That is a worse shape than a
table, and reading history back out of `audit_logs` JSONB is worse than querying one.

The rule that actually matters is narrower, so state it that way:

- **`audit_logs` owns "what changed".** The before and after of the status column. Never duplicate that as the
  source of truth.
- **A companion log may exist for what `audit_logs` cannot express** - *which edge* authorised the move, and the
  remark that came with it. Those are the two things a reviewer reads and neither is a column diff.
- **The companion log is never authoritative for current status.** If you can reconstruct "where is this record
  now" from it, you have built the second trail this rule forbids.
- **Exactly one code path may write the status column.** This is the condition that makes the two consistent,
  and it is the real content of the original warning: the trails disagree the moment something writes the status
  without going through the service that logs. A direct write that bypasses it is a defect, not a shortcut.

`WorkflowSubmissionTransitionLog` after F1 is the worked example: it keeps `from_status_id` / `to_status_id` /
`status_transition_id` / `remark` and nothing else, with `ON DELETE SET NULL` on the edge so history outlives an
admin editing the graph.

If you do write an event log for any reason, note that `create_event_log` interprets **naive datetimes as
Malaysia time** while tracking columns store naive UTC, so passing a naive UTC value silently shifts it by
eight hours.

### 12. Retiring a legacy status surface is a different risk class from adding one.

Adding a graph is additive and its failures are loud. Removing the thing it replaces is neither. Three checks
are mandatory before deleting any legacy status surface, because each has already produced a real defect here:

**Map the boot import path first.** A "private" helper may be imported by an unrelated module that sits on
`app.main`'s import chain. `_collect_field_defs` in `workflow_forms_service` looks internal and is imported by
the list-query stack, which the API router mounts at startup. Deleting it is an `ImportError` at `uvicorn`
startup: a dead API, not a stale screen. Grep for importers of every symbol you intend to remove, and grep for
readers of every column you intend to drop.

**Persisted config rows outlive the code that created them.** Dropping a status column while a
`list_query_fields` row still resolves it via `getattr(Model, name)` turns every filter or export request that
includes that field into a runtime `AttributeError`, on a deploy that changed no data. Row counts of zero in the
entity tables do not mean the feature's configuration surface is empty. Drop or repoint the config rows **in the
same migration** as the column.

**A silent-empty result is worse than a crash.** A field-metadata builder pointed at a document shape it no
longer understands returns an empty list, so grids and exports quietly lose their columns with no error anywhere.
Prefer changes that fail loudly; where a silent-empty path is possible, add a test that asserts non-empty rather
than merely "does not raise". The same trap in reverse: an FE flag derived from the retired shape
(`terminal` from `schema.states[].is_terminal`) becomes `false` and **enables editing on closed records**, which
is an authorization regression that throws nothing.

### 13. Note when your default posture inverts.

The schema-embedded gating this engine replaces failed **open** (absent config means allow). The engine fails
**closed** (a status outside the graph is rejected). Swapping one for the other silently changes who can do what.
State the inversion in the slice that performs it, and keep the pre-existing default while re-keying, so the
change of mechanism and the change of policy are never the same commit.

## Consequences

- Registering an entity is now a checklist, and a slice that skips items 7 through 9 ships an advisory graph.
- The two patterns are legitimised and bounded, so neither spreads by accident.
- `service_job`, warranty and RMA registrations are pre-decided by rule 1: FK-based, because their tables do not
  exist yet.
- Two open questions this ADR deliberately does **not** answer, because they are not about joining the engine:
  who owns per-status **role permissions** (see the forms-platform decision ledger), and whether an entity's
  graph should ever be company-scoped. Statuses are global today: SRT and MOCHA share one pipeline definition.
