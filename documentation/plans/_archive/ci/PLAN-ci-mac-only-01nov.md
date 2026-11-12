# PLAN: CI-MAC-ONLY (every CI job on the Mac runner; only images + deploy on GitHub)

Status: Superseded by PLAN-ci-cloud-gate-04nov.md (owner held CI-MAC-ONLY 2 Nov: the Mac ran the release suite in 5-6 h; owner 4 Nov "yes cloud CI"). Track: small fix track (`.github/workflows/*.yml` routing, its pin tests and
docs; no app code, no migration, no auth/RBAC, no ingest). The owner merges (deploy pipeline).

## Why

Owner, 1 Nov 2026 ~22:00: the repo is PRIVATE again, so GitHub-hosted Actions minutes bill
against a 3,000 min/month quota. "only the build and deploy to server should be ran on github,
others can run on mac mini as the runner".

## Facts (read from main at 1fc0fab9)

- Self-hosted runner `sorento-mac-1`, labels `self-hosted, Linux, ARM64, sorento-mac`
  (`scripts/ci-runner/README.md:3`), colima VM 4 CPU / 6 GB, rootless Docker, service
  containers publish on the VM's localhost (`scripts/ci-runner/README.md` "Layout").
- `deploy.yml` routes by the dispatch input `runner` (github|auto|mac, default github) through
  the `Pick the test runner` step of `changes` (`deploy.yml:410`) and the fast jobs'
  `inputs.runner == 'mac'` expression (`deploy.yml:187,227,358,2358,2403`). `validate-backend`
  and `validate-mcp` are hard `ubuntu-latest` (`deploy.yml:753,843`). Every test job already
  carries its own Postgres/Redis service containers and `TZ: UTC`, and the XDIST tuning
  (2 workers on the Mac) exists (`deploy.yml:1075,1343,1736,1774`).
- `build-images` (`deploy.yml:2011`) and `build-and-deploy` (`deploy.yml:2140`) are
  `ubuntu-latest` and must stay there (prod images are amd64; an amd64 build on the arm64 VM
  is QEMU and OOMs, `scripts/ci-runner/README.md` "No image builds here").
- `outline-user-guides-sync.yml` (push + cron every 6 h) and `never-stuck-nightly.yml`
  (manual) are `ubuntu-latest`; `rollback.yml` (manual) stays on GitHub (it SSHes to prod).
- Releases are dispatched with `-f runner=github`
  (`documentation/plans/_archive/ci/PLAN-ci-runner-mac-26oct.md:3`), so the `runner` input
  stays declared (GitHub rejects an undeclared input) but routes nothing.

## Change

1. Every job except `build-images`, `build-and-deploy` (and `rollback.yml`) runs on
   `runs-on: [self-hosted, sorento-mac]`. No fallback to `ubuntu-latest`: a busy or offline Mac
   queues the job (crew's ci_backlog alarm covers a stuck queue).
2. The `Pick the test runner` step and the `tests_runner` output go; `XDIST_WORKERS` is `2`
   in every backend test step (the Mac value it already had).
3. `outline-user-guides-sync` and `never-stuck-nightly` move to the Mac too.
4. Pin tests (`test_ci_runner_routing.py`) assert the new routing; docs (CLAUDE.md, runner
   README, the comment above `jobs:`) say where jobs run.

## Proof

The PR's own `ci` run (crew labels) lands `Changed areas` and `PR gate` on `sorento-mac-1`;
run id and each job's runner name posted on the PR. Expected GitHub-hosted minutes per release
from recent `build-images` / `build-and-deploy` timings, in the PR body.
