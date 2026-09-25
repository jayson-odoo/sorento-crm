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

## CI trigger (standing rule, 25 Sep 2026)

A push to a lane's PR never runs CI - `.github/workflows/deploy.yml`'s `pull_request` trigger is
`types: [labeled]` only, gated on the label being exactly `ci`. The orchestrator is the only one
who adds that label, and only once the lane is genuinely ready for CI (Phase 3, or a small-fix
track PR ready to merge). A lane, cloud or local, never adds the `ci` label to its own PR and does
not wait for CI on that PR unless its brief says the label was already added - a lane that needs a
CI result waits for the orchestrator to say so, it does not poll the PR itself. A workflow run
removes the label again the moment it fires, so the operator recipe to re-run CI against a new
head is always `gh pr edit <n> --add-label ci`, never leaving the label sitting on the PR.

The `[skip ci]` convention for intermediate commits (a commit message containing it skips creating
a run for that push) stays in place as belt and braces - it costs nothing now that pushes to a PR
do not trigger runs on their own, and it still matters for pushes to `main`.

A PR with no `ci` label shows no checks and therefore cannot merge under branch protection - that
is intended, not a bug: it is what keeps a not-yet-ready PR from being mergeable by accident.
