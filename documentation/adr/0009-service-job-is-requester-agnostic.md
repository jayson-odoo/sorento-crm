# A Service Job knows nothing about complaints

`service_jobs` is its own installable module with dependencies `["base", "resources"]` and **no
foreign key to `complaints`**. It attaches to whatever requested it through
`source_entity_type` / `source_entity_id`, the same polymorphic pattern
`conversation_sla_tracking` already uses in this codebase.

A future reader will look at a Complaint detail page listing its Service Jobs and reasonably ask
why the child does not simply carry `complaint_id`. This is deliberate.

## Why

The reuse axis that matters is `dreamz_ems`, which needs technician scheduling and has no concept
called a complaint. Its backend today is `auth / tenant / workflow / form / status / terminology /
catalog / document / review` with no scheduling model at all, so this is the model it will adopt
rather than one it will adapt. A hard FK to `complaints` makes the module unportable at the schema
level, and there is no version of "port the scheduling module" that begins with "first create a
complaints table".

This is the same reasoning as ADR-0005 for the page builder: build it here, keep the model free of
the local domain, and let the portable thing port.

It is worth stating what portability does **not** mean here, because the ask is easy to over-read.
`dreamz_ems` is a separate FastAPI application with its own Postgres. "Reuse" means porting the
model and code, not sharing a database, a schema or a service. That is why this ADR does not put
`service_jobs` in its own schema and does not drop to id-value-only references within Sorento: the
module lives in `public` with normal FKs to `attachments` and `users`, per the `PRINCIPLES.md`
default. Only the *requester* edge is polymorphic, because only that edge is domain-specific.

## Consequences

- Integrity on the requester edge is service-layer, not database-enforced. Deleting a Complaint must
  explicitly deal with its Service Jobs; Postgres will not cascade.
- `complaints` declares a hard dependency on `service_jobs`, not the reverse. The arrow points from
  the domain-specific module to the generic one.
- The vocabulary is enforced, not incidental. A Service Job has a site, a window, an assignee and
  photographic proof. It must never acquire `within_warranty`, `dealer_id`, or anything else that
  only means something in after-sales - that is what the Complaint above it is for.
- Technician clocks (`proposed_at`, `confirmed_at`, `arrived_at`, `completed_at`) live on the job
  rather than in the form-SLA engine, because form SLA resolves assignees through
  `agent_teams` -> `team_members` -> `users`, and a Technician is deliberately not a user. Form SLA
  routes and escalates staff; a technician is dispatched, and escalating a site visit to tier 2 of a
  team the technician does not belong to has no meaning.
