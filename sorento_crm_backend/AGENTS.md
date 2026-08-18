# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- The shared local Postgres (the prod-copy `DATABASE_URL` DB) converges through
  `Base.metadata.create_all`, not `alembic upgrade`: its `alembic_version` stamp can sit many
  revisions behind the objects it actually holds. Tests that run against the real DB via
  `pg_session` (rather than a scratch schema from `tests/_pg_fixture.py`) fail with
  `UndefinedColumn` after a new migration until the equivalent additive DDL is applied; apply it
  idempotently (`ADD COLUMN IF NOT EXISTS`) instead of re-stamping. CI migrates to head and is
  unaffected.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
