# PLAN: CI-HOSTED-RUNNERS (PR gate and test jobs back on GitHub-hosted runners)

Status: In progress. Track: small fix track (`.github/workflows/deploy.yml` routing + its pin test,
no app code, no migration, no auth/RBAC, no ingest). The owner merges (deploy pipeline).

## Why

Owner, 29 Oct 2026: CI is too slow. Every `ci` run lands on the one self-hosted runner
`sorento-mac-1`, so 6-8 PRs queue behind each other for hours. The repo is public again, so
GitHub-hosted `ubuntu-latest` minutes are free and jobs run in parallel.

## Facts (measured 29 Oct 2026)

- Routing today: repo variables `RUNNER_TESTS=mac` and `RUNNER_FAST=mac`
  (`documentation/plans/_archive/ci/PLAN-ci-runner-mac-26oct.md:3`), read by `deploy.yml`
  (`Pick the test runner` step and the fast jobs' `runs-on`).
- Run 40810095336 (PR #1968, frontend-only): `Changed areas` created 03:05:00, started 03:39:08
  (34 min queued, 13 s run); `PR gate` created 03:39:21, started 04:54:27 (75 min queued,
  8.5 min run). 118 min wall for 8.7 min of work, both on `sorento-mac-1`.
- Every test job already declares its Postgres (`pgvector/pgvector:pg16`) and Redis
  (`redis:7-alpine`) service containers and the workflow-level `TZ: UTC`; nothing about the job
  bodies is Mac-specific beyond `XDIST_WORKERS` (2 on the Mac, `auto` elsewhere).
- `scripts/ci-runner/up.sh` refuses to register a runner on a public repo: a self-hosted runner
  on a public repo is the risk that guard exists for.
- Releases are dispatched with `-f runner=github` (archived plan line 3), so the `runner` input
  must keep accepting that value.

## Change

1. The repo variables stop routing. Every job runs on `ubuntu-latest` unless a
   `workflow_dispatch` explicitly passes `runner=mac` (or `auto`). A PR run has no inputs, so a
   PR gate is always GitHub-hosted whatever the variables say.
2. Job names unchanged (`Changed areas`, `PR gate`, the fast-gate names, the shards).
3. `test_ci_runner_routing.py` pins the new rule.

## Proof

PR gate on this PR (crew adds `ci`), timings old vs new in the PR.
