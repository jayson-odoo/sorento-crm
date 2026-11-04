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
and `tsc` plus ESLint over the changed frontend files. No pytest test and no vitest executes on
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

   The sha must be the PR's head at the time of `crew-done`; any later push needs a new run and
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
the new candidate. Only a green sweep on that exact sha is dispatched with the default
`skip_tests=true`; anything else goes out with `-f full_suite=true` or not at all.

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
