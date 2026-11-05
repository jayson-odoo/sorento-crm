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

A `ci`-labelled PR run is `Changed areas` plus one `PR gate` job, **fast checks only**
(CI-CLOUD-GATE, owner 4 Nov 2026): main's head merged in, the alembic head, PII, Outline-guide
and gitleaks gates, the backend import chains and `pytest --collect-only`, the MCP import check,
and `tsc` plus ESLint over the changed frontend files (whole files: 54 files carry 195 ESLint
errors on main today, so touching one means fixing its errors). No pytest test and no vitest executes on
GitHub for a PR, and no job runs on the Mac runner: the tests run in the lane's own sandbox
(next section). **A merge does not deploy**: a push to main runs only the alembic head gate. The
release is `gh workflow run deploy.yml --repo foundryx-sdn-bhd/sorento-crm --ref main`,
dispatched by the orchestrator after a batch has merged AND the release sweep below passed on
that exact head; by default it runs no tests (`skip_tests` defaults to true), builds the images,
and its deploy job then waits for the owner's approval in the GitHub `production` environment
(owner decision 29 Sep 2026; `documentation/plans/ci/PLAN-ci-fast-gate-29sep.md`).
`-f full_suite=true` is the emergency full suite on GitHub (about 470 billed minutes, off by
default); `-f skip_tests=false` runs the lean release tests on GitHub
(`documentation/reference/CI-LABELS-AND-MINUTES.md`).

## Tests before crew-done (CI-CLOUD-GATE, mandatory)

Every lane, cloud or local, runs its changed-area tests itself, on the exact head it hands over:

1. Commit everything, then from the repo root (after `bash scripts/cloud-env-setup.sh`):

   ```
   scripts/crew-tests.sh
   ```

   It diffs the head against `merge-base(origin/main, HEAD)` and runs what the PR gate used to:
   the changed backend test files plus every test file that imports a changed module
   (`sorento_crm_backend/scripts/ci_select_tests.py`), the forms lifecycle chains when forms code
   changed (FORMS-REGRESSION), the regression guards (`tests/test_lessons_learnt_regressions.py`),
   the MCP suite when `sorento_crm_mcp/` changed, and `vitest run --changed <base>` plus the
   source-scanning guards when the frontend changed. Postgres only, through
   `SORENTO_ENV_FILE=.env.ci-tests`. It refuses a dirty tree, and `--plan` prints the selection
   without running it.
2. Post its last line on the PR **before** `crew-done`, with the commands it printed:

   ```
   crew-tests: <head sha> backend N passed/0 failed, vitest N/0
   commands:
     (cd sorento_crm_backend && SORENTO_ENV_FILE=.env.ci-tests venv/bin/python -m pytest ...)
     (cd sorento_crm_frontend && npx vitest run --changed <base> --passWithNoTests)
   ```

   Only a run that exited 0 counts: a failed or crashed run ends its line with
   `FAILED (exit N)`. The script refuses a head that does not contain `origin/main` (merge
   main first, as the PR gate does). The sha must be the PR's head at the time of `crew-done`; any later push needs a new run and
   a new `crew-tests:` comment. A failure is fixed, not posted as done. A test that fails on main
   too is named with its main run as evidence, never skipped or quarantined.
3. A lane may add tests the script does not pick (a module it knows is coupled) and lists them
   under `commands:`. It never drops what the script picked.

## Release sweep (CI-CLOUD-GATE, mandatory before each release)

Before the orchestrator dispatches a release, one cloud session runs the **full** suite on the
release candidate (main's head to be released; about 56k backend tests, 56,489 collected on
4 Nov 2026, and 21k vitest, about 2 h), as RELEASE-SWEEP-4NOV did (#2157):

- backend: `cd sorento_crm_backend && SORENTO_ENV_FILE=.env.ci-tests venv/bin/python -m pytest -n auto --dist loadfile -m "not serial_ddl"`,
  then `-p no:xdist -m serial_ddl`, with `tests/scm/` as its own session and the
  `tests/ci_excluded.txt` entries left out (the shards' split, `deploy.yml` `test-backend`);
- frontend: `cd sorento_crm_frontend && npx vitest run`.

It posts `crew-tests: <candidate sha> backend N passed/F failed, vitest N/F` on the release PR
or issue it fixes from. A red sweep is fixed (a test-only fix PR, as #2157) and swept again on
the new candidate.

### Nightly sweep + release delta (owner ruling, 4 Nov 2026)

The full suite runs **nightly** on main; a release needs only the last green nightly plus a
delta on the diff since that nightly's sha. Both are one command in a cloud sandbox, and each
prints ONE line to post as is:

```
bash scripts/nightly-sweep.sh [<sha>]                    # default origin/main, ~2.5 h on 4 cores
# crew-tests: <sha> backend N passed/F failed, vitest N/F

bash scripts/release-delta.sh <nightly sha> [<head>]     # default head origin/main
# crew-tests: <head> delta since nightly <nightly sha> backend N passed/F failed (selected S of M test files: <why>), vitest N/F (<mode>)
```

The nightly runs the split above on a detached worktree of the sha with a FRESH database
bootstrapped from that sha's code: 10 xdist groups (pytest-split) of `tests/` minus `tests/scm`,
the migration tests, `serial_ddl` and `tests/ci_excluded.txt`; then `tests/test_migration_*.py`
and `-m serial_ddl` serially; then `tests/scm/` (xdist, then its `serial_ddl`); then
`npx vitest run`. The delta runs alembic heads == 1, `bootstrap_env` + `alembic upgrade head` on
a fresh database, and then **only the affected tests** (owner ruling 5 Nov 2026: "run only the
tests that are affected, dependent, or depended by"; RELEASE-DELTA-AFFECTED). Logs, junit files,
`selected.txt`, `selected_why.txt` (each file with the rule that picked it) and `failed.txt` stay
in the output directory the script names.

**Backend selection** (`sorento_crm_backend/scripts/release_delta_select.py`; its docstring is the
full rule, `tests/test_release_delta_select.py` pins it). The import graph covers every `.py`
under `app/`, `scripts/`, `tests/` (static AST imports incl. relative ones; in tests also dotted
`mock.patch` / `monkeypatch.setattr` strings; `from app.models import User` resolves through the
package's re-export to `app/models/user.py`). Edges are module-level (run at import) or lazy
(inside a function). It is cached as JSON per backend tree sha in
`~/.cache/sorento-release-delta/` (`RELEASE_DELTA_GRAPH_CACHE`); building it takes ~26 s, a
cached selection under 2 s.

| Rule | Selects |
| --- | --- |
| changed test file | itself |
| dependents | test files that import, through any chain of module-level imports, a changed module or a module that imports one (a lazy import is followed one hop, not further) |
| depended-by | for a changed module M and each module D it imports directly: `test_<D>.py` / `test_<D>_*.py` that import D |
| changed non-module file | test files that name it (alembic revision, workflow, shell script, frontend path); a template or data file under `app/` also through the module that names it |
| deleted module | test files that name its dotted path |
| migration tests | `tests/test_migration_*.py` only when `alembic/`, `alembic.ini` or `app/models/` changed |
| regression guards | `tests/test_lessons_learnt_regressions.py` on any backend change |

A test file counts as importing, at module level, every `conftest.py` above it (pytest imports
them first), and a changed package `__init__.py` counts as a change to every module of the package
(Python runs it before any of them). `tests/scm/` runs only when these rules reach it.
`tests/ci_excluded.txt` entries never run.
The selection runs in the PR gate's split: main tree and `tests/scm/` each under xdist and then
`-m serial_ddl`, the migration tests serially.

**Full backend suite** instead, the reason printed in the `crew-tests:` line: a `conftest.py`,
`tests/__init__.py`, `tests/_xdist_crash_guard.py`, `tests/ci_excluded.txt`, `pytest.ini`,
`pyproject.toml`, `setup.cfg` or `requirements*.txt` changed; env bootstrap changed
(`sorento_crm_backend/scripts/bootstrap_env.py`, `scripts/cloud-env-setup.sh`); the graph
cannot be built (a file does not parse); or the selector itself failed (its stderr is in
`selector.log`). A full run uses the same three sessions as a selection (main tree, `tests/scm/`,
migrations), not the nightly's 10 pytest-split groups: one `-n auto` session over the main tree
is what the PR gate's changed-files runner did.

Why lazy imports stop after one hop (measured 5 Nov on `42d1a56c..019770c1`): following every
import transitively selects ~95% of the test files from almost any change, because function-local
imports tie the services into one component. On that diff, following them on through module-level
importers selected 1,499 files, 1,319 of them only because `app/main.py` mounts the ingest router
and `document_ingest_service` imports the changed `po_link_history` inside a function.

**Frontend**: no frontend change runs no vitest. Otherwise `npx vitest related --run
<changed frontend files that exist at head>` plus the source-scanning guards
(`sorento_crm_frontend/scripts/source-guard-tests.sh`, tests that read files instead of importing
them); the FULL `vitest run` when `package.json`, `package-lock.json`, `vitest.config.*`,
`vitest.setup.*`, `tsconfig*.json`, `test-mocks/` or a `__mocks__/` directory changed.

What is not caught here is caught by the next nightly, which still runs everything.

Measured on 5 Nov 2026 (selection only; estimated CPU seconds from the committed
`sorento_crm_backend/.test_durations`, which holds 26,410 of the ~56k tests):

| Range | Old selection | New selection |
| --- | --- | --- |
| `42d1a56c..019770c1` (18 commits, `po_link_history` + one alembic revision) | 526 files, 396 of them `tests/scm/`; est 4,894 CPU-s | 262 files, 21 `tests/scm/`; est 2,384 CPU-s |
| `019770c1..30bbcc6a` (108 commits, incl. `app/models/user.py` and `procurement.py`) | 1,798 files, 397 `tests/scm/`; est 25,583 CPU-s | all 3,257 files; est 36,751 CPU-s |

The second range is not a defect of the rule: a changed User model is imported, directly or
through the root `conftest.py`, by every test file, so the honest affected set is the suite. The
old one-level regex missed 1,459 of those dependents.

`scripts/sweep-lib.sh` closes the sandbox gaps the 4 Nov sweep measured (RELEASE-SWEEP-4NOV-PM,
#2171), each of which shows up as reds that CI does not have:

| Gap | Symptom without it | What the script does |
| --- | --- | --- |
| Ubuntu's pgvector is 0.6.0 | 3 `hnsw.iterative_scan` tests fail (`test_lookup_embed_central_*`) | builds pgvector v0.8.0 when the packaged one is older |
| no DNS for `automate-sorento.foundryx.my` | 12 `tests/chatbot` retry tests 422 in `outbound_url_guard` | adds an `/etc/hosts` line (public IP; nothing connects to it) |
| `tests/scm/conftest.py` `_pg_url` ignores `SORENTO_ENV_FILE` | 25 `tests/scm` errors, ~2,100 skips | exports `DATABASE_URL` (CI sets it too) |

A database bootstrapped by `bootstrap_env` never holds the `MIGRATION_ONLY_TABLES`
(`alembic/env.py`), so a migration that reads one of them (`oiod_0002` reads
`projects.oi_delivery_date_backfill`) fails `alembic upgrade head` from an older bootstrapped
database while prod, which ran the creating migration, is fine. The delta therefore upgrades a
fresh database bootstrapped at the head, as CI does.

### Release runbook: the `release-sweep` status (machine-checked, owner 4 Nov 2026)

A release with `skip_tests=true` (the default) ships only a sha that carries a `success`
commit status with context `release-sweep`: the first step of `Changed areas`
("Release sweep passed on this sha") reads it and fails the run otherwise, so nothing builds or
deploys. Cloud sessions cannot set commit statuses; **crew does, from the Mac**, and only after
reading a green `crew-tests: <sha> backend N passed/0 failed, vitest N/0` sweep comment whose
sha is exactly the release candidate (main's head to be dispatched):

```
gh api -X POST repos/foundryx-sdn-bhd/sorento-crm/statuses/<sha> \
  -f state=success \
  -f context=release-sweep \
  -f description='crew-tests: backend N passed/0 failed, vitest N/0' \
  -f target_url='<URL of the crew-tests comment>'
```

`description` is at most 140 characters. Check it took:
`gh api repos/foundryx-sdn-bhd/sorento-crm/commits/<sha>/status --jq '.statuses[] | select(.context=="release-sweep") | .state'`
prints `success`. Then dispatch on main as usual:
`gh workflow run deploy.yml --repo foundryx-sdn-bhd/sorento-crm --ref main`. If main moved after
the sweep, the new head has no status and the release is refused: sweep the new head.

A red or failed sweep never gets the status (crew does not post `failure` or `pending` either:
the check reads anything but `success` as missing). The ways out are all explicit dispatch
inputs, visible in the run:

- `-f full_suite=true`: the full sharded suite on GitHub first (about 470 billed minutes).
- `-f skip_tests=false`: the lean release tests on GitHub first.
- `-f allow_unswept=true`: EMERGENCY, ships the sha untested; the run summary says
  `UNSWEPT RELEASE` and the step logs a warning. Owner's call only.

A docs-only change (every path under `documentation/**`, `.claude/**`, `.cursor/**`, a root-level
`*.md` or the PR template) runs only `Changed areas` and the `PR gate` fast-gate steps (alembic
head, PII, gitleaks) on a PR, and `Changed areas` plus `Single alembic head` on a merge-queue entry: no image build, no test suite (owner ruling 29 Sep 2026;
`documentation/plans/ci/PLAN-ci-docs-skip-29sep.md`). One
non-docs path anywhere in the change keeps the full pipeline: a markdown file inside a service
tree, either end of a rename, or documentation a test reads as input (`documentation/reference/`,
a plan's `fixtures/`, `samples/` or `seed-assets/` folder, and the plan files listed in the
workflow's `NOT_DOCS_RE`). A test that reads a new documentation path must add it there, or
`tests/test_ci_docs_only_filter.py` fails.

A PR with no `ci` label shows no checks and therefore cannot merge under branch protection - that
is intended, not a bug: it is what keeps a not-yet-ready PR from being mergeable by accident.

## LLM spend in test runs: replay by default (LLM-TEST-COST, 4 Oct 2026)

A scripted or browser-pass run answers the parser from recorded cassettes, not OpenAI. The
switch is `LLM_CASSETTE_MODE` on the BACKEND process (`off` is the default and the only value
production ever has; `record` calls live and writes a cassette; `replay` answers from the
cassette and fails a turn with "LLM cassette miss: ... key <sha256>" rather than calling live).
Cassettes live in `LLM_CASSETTE_DIR` (default `~/.cache/sorento-llm-cassettes`); a directory
inside the repository is refused, because a recording holds the model's answer to a real
message. Never commit one.

- Harness launchers (`documentation/plans/chatbot/evidence/*/harness/run_backend_live.py`,
  `run_worker_local.py`) start in replay; pass `--record` once to fill the cassettes, `--live` to
  spend without recording. Copy that pattern into a new lane's harness.
- `scripts/chatbot_console_check.py` stops after the first turn the backend answered live, unless
  `--live` is passed (a `--record` backend needs `--live` too).
- A recording is keyed on the exact request, and the parser's system prompt carries today's
  date, so by default a cassette is good for the day and
  prompt version it was recorded on. Set `LLM_CASSETTE_DATE` (e.g. `Saturday, 04 October 2026`)
  on the backend to pin the parser's "today" while recording AND replaying: the same cassettes
  then stay valid on later days. It is ignored when the mode is `off`.
- The OpenAI provider and the direct-HTTP embedding calls are recorded. In replay an Anthropic or
  Gemini call, Whisper transcription and the market-research call are refused: use `--live`
  when a pass needs them.
- Any mode but `off` runs only when `ENVIRONMENT` is development, dev, local, test or ci. A cassette dir inside any git checkout, or one not
  owned by you with mode 0700, is refused. Clear old cassettes with
  `find ~/.cache/sorento-llm-cassettes -name '*.json' -mtime +7 -delete`.

`LLM_BASE_URL` / `LLM_MODEL_OVERRIDE` point the OpenAI client at another OpenAI-compatible
endpoint or model when set. Nothing sets them today.
