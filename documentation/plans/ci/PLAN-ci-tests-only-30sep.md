Status: small fix track - in review (PR #1393)

# CI: a PR that changes a backend test file runs that file on the PR

## Symptom

PR #1387 (MEDIA-FLAKE) changed one file, `sorento_crm_backend/tests/test_media_job_lifecycle.py`.
No workflow run started on push, and the ruleset requires the light checks to report, so
nothing could merge until crew added the `ci` label. The brief named the docs-skip path
filter from PR #1370 as the cause, to be confirmed.

## Measured facts

- The `ci` run on #1387, 36665697605, job "Changed areas", printed:
  `changed files (1): sorento_crm_backend/tests/test_media_job_lifecycle.py`,
  `docs_only=false`, `backend=true`, `frontend=false`, `mcp=false`, `scm=false`. "Single
  alembic head (fast gate)" and "Validate backend imports" ran. So the docs filter did not
  treat `tests/` as docs: `DOCS_RE` (`.github/workflows/deploy.yml`, job `changes`, step
  "Detect changed areas") matches `documentation/`, `.claude/`, `.cursor/`, a root-level
  `*.md` or the PR template, nothing under a service tree.
- No run on push is by design since PR #1375: `pull_request: types: [labeled]`
  (`deploy.yml` lines 27-30, and the trigger comment above them). Every PR, whatever it
  changes, shows no checks until the `ci` label is added. Not specific to tests.
- What that run never did: execute the changed test. `test-backend` carries
  `github.event_name != 'pull_request'` (owner ruling 29 Sep 2026: the six shards run in the
  merge queue and the release only) and `SCM_RE` covers `tests/scm/` only. A change to any
  other backend test file was first executed in the queue or the release, which is where
  #1387's original flake had surfaced.

## Change

One file, `.github/workflows/deploy.yml`; no product code, no migration, no auth change.

1. `changes` emits `backend_tests`: the PR's changed `sorento_crm_backend/tests/**/test_*.py`
   files outside `tests/scm/` (the SCM shards' job), space-separated, sorted. The regex's
   character class admits only `[A-Za-z0-9_.-]` in a path, so nothing a shell would parse can
   reach the pytest argument line. Empty off a PR (push, merge_group, workflow_dispatch: the
   full shards run every file) and on every early exit (docs-only, skip_tests, failed file
   list call), so the changed-files job never doubles a shard.
2. New job `test-backend-changed` ("Backend changed tests (Postgres)"), `needs: [changes]`,
   `if: github.event_name == 'pull_request' && needs.changes.outputs.backend_tests != ''`.
   Same Postgres + Redis services, durability relax and `bootstrap_env` as the shards. Step
   "Select the changed test files to run" turns the list into backend-relative paths and
   drops what the checkout does not hold (a deleted or renamed-away path is in the PR's file
   list) and `tests/ci_excluded.txt` entries; every later step gates on its `files` output,
   so a list that trims to nothing is a pass with nothing run. Pytest runs the selected files
   serially (`-p no:xdist`): a PR changes a few files, and one process at a time is what
   makes a changed `tests/test_migration_*.py` or a `serial_ddl` test safe without the
   shards' two-pass split. The file list reaches pytest through an env var, never inlined.
3. Untouched: the `ci` label gating, the concurrency groups, the area flags, `SCM_RE`, the
   queue's and the release's full runs, and the docs-only skip.

## Tests

`sorento_crm_backend/tests/test_ci_docs_only_filter.py`, 31 new cases (137 total), the
shell extracted from the workflow file and run under GitHub's bash flags with the stub `gh`:

- #1387's file list end to end: the step's outputs, then the job set from those outputs
  (light checks plus `test-backend-changed`, never the six shards).
- The list beside code and frontend changes; scm test plus non-scm test.
- Not listed: `tests/scm/**`, `conftest.py`, `_pg_fixture.py`, helper modules, fixtures,
  `ci_excluded.txt`, `.test_durations`, MCP and frontend tests, shell-unsafe names.
- A rename lists both ends; the select step drops the missing one.
- Empty on push, merge_group, workflow_dispatch and every early exit.
- Select step against a scratch checkout: present files, a deleted file, an excluded file,
  nothing left.
- Job simulation: skipped off a PR and with a non-`ci` label; every post-select step gated on
  the select output; pytest serial over `$FILES`.

Kill test: with the workflow reverted the new cases fail. The PR itself changes a test file,
so its `ci` run exercises `test-backend-changed` over the simulation file.
