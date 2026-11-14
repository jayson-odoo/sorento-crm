# UAC: CI-ZERO-MINUTES (14 Nov 2026)

Plan: `PLAN-ci-zero-minutes-14nov.md`. Owner OK 14 Nov ~20:45.

## A. Workflows: GitHub Actions only builds, deploys and rolls back

A1. No workflow under `.github/workflows/` triggers on `pull_request`, `pull_request_target`, `push` or `schedule`.
    Every workflow's triggers are a subset of `{workflow_dispatch, merge_group}`.
A2. `deploy.yml` triggers are exactly `merge_group` and `workflow_dispatch` (the merge queue stays dormant, as today).
A3. `deploy.yml` has no `refuse-ci-full` job, and its text no longer contains `github.event_name == 'pull_request'`,
    `github.event.pull_request` or `github.event.label` (the PR-only steps and expression branches are gone, not
    left as dead code).
A4. The `lean-gate` job's name is the static string `Release tests`.
A5. `check-migration-heads` (`Single alembic head (fast gate)`) still exists and is still in `build-and-deploy`'s
    `needs`: a release still refuses two alembic heads.
A6. `outline-user-guides-sync.yml` triggers only on `workflow_dispatch` (manual fallback); crew's scheduler runs the
    same script (section C).
A7. `rollback.yml` and `tests-sharded.yml` keep their `workflow_dispatch` trigger unchanged.
A8. actionlint reports no new finding.

## B. `scripts/pr-gate.sh`: the PR gate, run by crew in the lane sandbox

Same checks the hosted `PR gate` ran on a `ci`-labelled PR (deploy.yml `lean-gate` at base 91643a99).

B1. Usage, from the repo root: `scripts/pr-gate.sh [--plan] [--base <ref>]`. Default base `refs/remotes/origin/main`
    (the caller fetched it). `CREW_CHANGED_FILES` (newline-separated repo paths) replaces the git diff, as in
    `scripts/crew-tests.sh`.
B2. Main must already be merged: when `<base>` is not an ancestor of HEAD, the script runs no check and its last line
    is `pr-gate: <head sha> FAIL main=<base sha> reason=main-not-merged`, exit 1. This holds with `--plan` too.
B3. Changed files = `git diff --name-only --no-renames <base> HEAD` (or `CREW_CHANGED_FILES`). Areas, the same
    regexes as deploy.yml `changes`:
    backend `^(sorento_crm_backend/|\.github/workflows/deploy\.yml$)`,
    frontend `^(sorento_crm_frontend/|\.github/workflows/deploy\.yml$)`,
    mcp `^(sorento_crm_mcp/|\.github/workflows/deploy\.yml$)`.
B4. Check ids, in this order. Always: `alembic-heads` (`python3 scripts/ci_alembic_heads.py`), `pii`
    (`python3 scripts/pii_guard.py`), `ai-coverage` (`python3 scripts/ci_ai_coverage.py --base <base sha>`),
    `outline-guides` (`python3 scripts/sync_user_guides_outline.py check`), `gitleaks`
    (`RANGE=<base sha>..<head sha> bash scripts/ci_gitleaks.sh`). Backend: `backend-imports` (the app.main and
    worker import chains, the two `python -c` lines of the hosted step) and `backend-collect`
    (`pytest --collect-only -q -p no:cacheprovider` in `sorento_crm_backend`). MCP: `mcp-imports` (the
    `create_mcp_app` import line). Frontend: `frontend-tsc` (`npx next typegen && npm run typecheck`) and
    `frontend-eslint` (ESLint over the ACMR-changed `*.ts *.tsx *.js *.jsx *.mjs *.cjs` files vs `<base>`).
B5. `--plan` runs nothing and prints `plan.checks=<ids space-separated>` plus `plan.main=<base sha>`, exit 0.
    Docs-only change -> `plan.checks=alembic-heads pii ai-coverage outline-guides gitleaks`. A change to
    `.github/workflows/deploy.yml` -> every id.
B6. A run executes every selected check even after one fails, then prints, as its last line,
    `pr-gate: <head sha> PASS main=<base sha> checks=<ids comma-separated>` (exit 0) or
    `pr-gate: <head sha> FAIL main=<base sha> checks=<ids> failed=<ids comma-separated>` (exit 1).
B7. Python checks use `sorento_crm_backend/venv/bin/python` when it exists, else `python3`; backend checks run with
    `SORENTO_ENV_FILE=.env.ci-tests` when that file exists (scripts/cloud-env-setup.sh writes it). The script never
    reaches the network except gitleaks' own download, and never posts anything: posting is crew's.

## C. Crew side (spec in the PR body; crew implements it in the crew tool)

C1. Crew runs `scripts/pr-gate.sh` on the lane's exact head and sets the commit status `PR gate` on that sha
    (success / failure, description from the last line, target_url = the PR comment carrying the full log tail).
C2. Crew re-runs it when main moves before a merge (B2 fails until the lane merges main).
C3. Crew's scheduler runs the Outline pull every 6 h and the push after a merge that changes a guide.

## D. Owner

D1. Ruleset `protect-main-branch` requires exactly one check, `PR gate`, accepted from any source.
D2. Order: crew status live (posting on open PRs) -> ruleset edit -> merge this PR.
