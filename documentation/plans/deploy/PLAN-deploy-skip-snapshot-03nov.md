# PLAN: skip the pre-migration snapshot when nothing migrates (DEPLOY-SKIP-SNAPSHOT)

Status: in review (PR #2127); small fix track (no migration, no auth, under 300 lines).

## Why

Owner, 3 Nov: "when there is no migration there is no need to backup." The 3 Nov hotfix release
(no migrations) spent 10+ minutes in "Pre-migration snapshot" of `scripts/blue_green_deploy.sh`.

## What

After the image pull and the first memory guard, `no_pending_migrations` compares:

- the NEW backend image's heads: `docker compose --profile <new> run --rm --no-deps -T --entrypoint alembic backend_<new> heads`
  (reads migration scripts only; no db connection, no `start.sh`), lines `<rev> (head)`;
- the app database's `select version_num from public.alembic_version` (same exec, user and HA
  handling as the existing alembic_version preflight).

Equal sets: log `no pending migrations: snapshot skipped`, no dump. Anything else (pending
migration, different revision, extra row, empty or unparseable output, a failing command):
`take_snapshot` exactly as before. Lock, memory guard (both calls), Postgres checks, health
checks and worker verification are unchanged.

## Acceptance

See `deploy-skip-snapshot-03nov-acceptance-criteria.md`.
