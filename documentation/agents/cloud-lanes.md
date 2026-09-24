# Cloud lanes

Claude Code cloud environments (code.claude.com/docs/en/cloud-environments.md) give a lane its
own managed VM (Ubuntu, 4 vCPU, 16 GB, 30 GB disk, Postgres 16 + Redis 7 preinstalled but not
running, Docker present). Use one when a local instance would be the 4th-or-later concurrent
agent on this machine, and the work needs no prod-copy data: `planner`, `reviewer`,
`security-reviewer`, `guide-writer`, `triage`, and a Phase 2 `coder` + `tester` pair that can
work against an empty, freshly seeded database rather than real rows.

## What stays local

- Owner hand tests.
- A browser pass on prod-copy data (agent-browser against the local dev stack).
- Anything that needs the RQ worker against real rows (Respond.io sends, chatbot media,
  catalogue/dealer-kit renders, AutoCount pulls) - the worker needs `REDIS_URL` reachable and
  real integration credentials that do not belong on a shared cloud VM.
- Anything reading `tests/ci_excluded.txt`'s tests as a real gate (they assert against
  business data that only exists in the prod-copy DB, never in a freshly bootstrapped one).

## Launching a cloud lane

From the repo, on the branch/worktree the lane will use:

```
cc <acct> --cloud "<brief>"
```

The environment setup script field (the managed VM runs this once, before Claude launches,
under a 5-minute cap, and caches the result) should point at:

```
bash scripts/cloud-env-setup.sh
```

It starts Postgres + Redis, creates the `sorento`/`sorento_ci` role and database, ensures the
`vector` extension, relaxes durability the same way the CI backend job does, writes
`sorento_crm_backend/.env.ci-tests`, builds the backend venv and installs the MCP package into
it, and runs `npm ci --force` for the frontend - the same substrate
`.github/workflows/deploy.yml`'s `test-backend` / `validate-frontend` jobs use. It is idempotent;
if the first prompt reports the setup step timed out, just ask the session to rerun it
(`bash scripts/cloud-env-setup.sh`) - state already built (venv, node_modules, bootstrapped
schema) is detected and skipped. `bash scripts/cloud-env-setup.sh --check` verifies the result
without changing anything.

## The one rule

**The prod-copy database is never restored to the cloud VM.** A cloud lane's Postgres is always
the empty, `scripts.bootstrap_env`-seeded schema (reference data only - roles, order statuses,
permissions - no business rows, no customer data). A journey that needs real data runs locally
instead.
