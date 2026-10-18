# PLAN: CI-MAC-CAP (xdist workers OOM-killed on the Mac runner)

Status: In progress. Track: small fix track (CI config + its pin test, no migration, no auth/RBAC,
no ingest).

## Evidence

Release run 39126899668 (main 0f5c6537e0), the first full suite on the Mac runner
(`RUNNER_TESTS=mac` since 14 Oct 2026):

- Shard 5 `Backend test suite (Postgres, xdist) (5)` on runner `sorento-mac-1`: `[gw1]`, `[gw3]`,
  `[gw0]`, `[gw5]` "node down: Not properly terminated" between 12:57:46 and 13:00:07, then
  `INTERNALERROR> KeyError: <WorkerController gw7>` (xdist `scheduler/loadscope.py`) and
  "2 failed, 2206 passed ... in 380.52s". The 2 failures are the crashed workers' tests, no
  assertion failed.
- `colima ssh -p ci -- sudo dmesg`: four "Out of memory: Killed process (python)" at about
  1.3-1.4 GB each. The VM is 4 CPU, 6 GiB, no swap (`scripts/ci-runner/up.sh:13`).
- Shard 7 hung until the job's 90 min cap after a worker died.

Cause: `-n auto` is 4 workers on the 4-CPU VM, 4 x ~1.4 GB plus Postgres plus Redis does not fit
in 6 GiB. GitHub-hosted runners (16 GB) never hit it. xdist's default `--max-worker-restart` is
4 x workers (`xdist/dsession.py` `get_default_max_worker_restart`), so each OOM respawned a
worker into the same memory pressure (gw4..gw7 are respawns) instead of failing.

## Change

`.github/workflows/deploy.yml`, every xdist call in a job that can land on the Mac
(`test-backend`, `test-backend-scm`, `lean-gate`):

1. `-n auto` becomes `-n "$XDIST_WORKERS"`, with the step env
   `XDIST_WORKERS: ${{ needs.changes.outputs.tests_runner == 'sorento-mac' && 2 || 'auto' }}`:
   2 workers on the Mac (2 x 1.4 GB fits beside Postgres and Redis), unchanged on GitHub-hosted.
   Env, not an inline `${{ }}`: tests/test_ci_docs_only_filter.py executes the PR gate's script
   in bash, which cannot run one (the step already passes FILES the same way).
2. `--max-worker-restart 0`: a crashed worker ends the session at once ("worker gwN crashed and
   worker restarting disabled", the crashed test reported failed) instead of respawning or
   hanging to the cap. Applies on both runner kinds: a worker crash is never a healthy run.

Pinned by `sorento_crm_backend/tests/test_ci_runner_routing.py` (red first).

Not changed (crew's call): `RUNNER_TESTS`, the colima VM size. Raising the `ci` VM to >= 10 GiB
is the alternative that keeps 4 workers.
