# PLAN: CI-CLOUD-GATE (GitHub = fast checks + build/deploy; tests run in cloud sandboxes)

Status: In progress (PR #2076, reworked from CI-MAC-ONLY). Track: infra, no product behaviour,
no migration, no auth/RBAC. Workflow permissions and secrets change, so the security reviewer
joins.

## Why

- The repo is PRIVATE: GitHub-hosted Actions bill against 3,000 min/month, and one PR gate has
  used 60+ min (the import-selected backend tests, the forms chains, vitest).
- CI-MAC-ONLY (this PR's first form) moved every job onto `sorento-mac-1`. The owner held it:
  measured 2 Nov, the release full suite took 5-6 h there (28 jobs one at a time, 10-25 min
  each) against about 15 min on GitHub-hosted runners.
- Owner, 4 Nov ~15:10 MYT: "yes cloud CI". Tests run in Claude Code cloud sandboxes, which
  already run each lane (`documentation/agents/cloud-lanes.md`) and the pre-release full sweep
  (RELEASE-SWEEP-4NOV, #2157).

## Design

1. **PR gate on GitHub = fast checks only** (`deploy.yml` job `lean-gate`, check name `PR gate`,
   still the one required check). On a pull request it runs: merge main's head, single alembic
   head, PII guard, Outline guide check, gitleaks, backend dependency install + the app/worker
   import smoke + `pytest --collect-only` (imports every test file, executes none), MCP import
   check, frontend `tsc` + ESLint over the changed frontend files (whole changed files: the
   tree has 195 errors in 54 files on main, so a PR that touches one of them fixes its errors;
   no baseline mechanism). No pytest execution, no
   vitest, no Postgres or Redis service container (their image is empty on a PR, so they never
   start).
2. **Release on GitHub = build + deploy by default.** `skip_tests` now defaults to `true`: the
   candidate's tests already ran in the cloud sweep. `full_suite=true` (the emergency "full
   suite on GitHub", off by default) wins over `skip_tests` and runs the full shards;
   `skip_tests=false` alone keeps the lean release tests job.
   **Machine-checked sweep (owner answer (b), 4 Nov 2026):** a `skip_tests` release's first
   step in `Changed areas` requires a `success` commit status with context `release-sweep` on
   the dispatched sha, which crew sets from the Mac (`gh api .../statuses/<sha>`, runbook in
   `cloud-lanes.md`) after reading the sweep's green `crew-tests:` comment. Without it the run
   fails before anything builds. `allow_unswept=true` (default false) is the visible emergency
   override: the run summary says `UNSWEPT RELEASE`.
3. **No job on the Mac runner.** The `runner` dispatch input, the runner picker step and its
   `RUNNERS_READ_TOKEN` read are gone; every job is `ubuntu-latest`. The owner can delete the
   `RUNNERS_READ_TOKEN` secret and stop the runner (`scripts/ci-runner/`), which this PR leaves
   in the repo for a later decision.
4. **Tests in the cloud** (contract in `documentation/agents/cloud-lanes.md`):
   - per lane: `scripts/crew-tests.sh` on the exact head runs what the old PR gate ran (the
     import-selected backend tests, the forms chains on a forms change, the regression guards,
     the MCP suite, `vitest --changed` plus the source-scanning guards) and prints the
     `crew-tests: <sha> ...` line the lane posts on its PR before `crew-done`;
   - per release: one full-suite cloud sweep (about 52k backend + 21k vitest, about 2 h) on the
     release candidate before the dispatch, as RELEASE-SWEEP-4NOV did.

## Minutes

See the PR body and `documentation/reference/CI-LABELS-AND-MINUTES.md` for the measured step
times. Target: PR gate under about 10 min.

## Tests (red first)

- `sorento_crm_backend/tests/test_ci_cloud_gate.py`: no step that runs on a pull request
  executes pytest (other than `--collect-only`) or vitest; no workflow job names the Mac label
  or a self-hosted runner; the service containers do not start on a PR; skip_tests defaults to
  true and full_suite wins over it; `scripts/crew-tests.sh --plan` picks the same tests the old
  PR gate did (selection, forms chains, guards, vitest).
- the release-sweep step executed with a stub `gh`: swept sha passes, missing / failed /
  pending / lookup failure refused, `allow_unswept` passes and is named in the summary, a
  release that tests on GitHub needs no sweep; security fixes (no persisted token in the PR
  gate checkout, eslint `--`, crew-tests.sh ignores an exported database URL).
- `test_ci_docs_only_filter.py` and `test_ci_runner_routing.py` follow the new contract.
