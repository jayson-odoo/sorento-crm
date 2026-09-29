Status: small fix track - in review (PR #1370)

# CI: a docs-only change to main skips image build, test suites and deploy

## Ruling

Owner, 29 Sep 2026: "all the docs merge don't need to trigger deployment". On the
Free plan (20 concurrent jobs, about one Sorento run at a time) a docs-only push to
main ran the full "Build and Deploy Sorento" workflow: three image builds, 14 test
jobs, the blue/green deploy, the owner email. That is 30 to 50 minutes of runner
time that changes nothing on the server, and it queues behind or ahead of real
deploys.

## Measured facts

- The last four docs merges to main (ad690927, 817ba108, d4c38cd3, d9108084) touch
  only `documentation/**`: plan and UAC markdown, PNG evidence, user guides.
- `changes` (deploy.yml) already computes per-area flags from the PR file list, but
  only on a `pull_request` event; a push and a merge-queue entry report every area
  as changed and run the full set.
- `*.md` files exist INSIDE the service trees and are not documentation:
  `sorento_crm_backend/tests/chatbot/replay_turns/*.md` and
  `sorento_crm_frontend/e2e/fixtures/**/*.md` are test fixtures, and
  `sorento_crm_mcp/Dockerfile` copies `README.md` into the image. So a blanket
  `**/*.md` rule would let a fixture change skip the suite that reads it.
- No required-check list is readable from the sandbox. Docs PR #1191 merged with
  zero check runs on its head, so a docs PR never carries the `ci` label today; the
  PR path is covered for completeness, the push to main is the case that costs.

## Change

One file, `.github/workflows/deploy.yml`, no migration, no auth change:

1. `changes` builds the changed file list for every event: PR files (as before), the
   `github.event.before...github.sha` compare on a push, the
   `merge_group.base_sha...head_sha` compare on a queue entry. One `gh api` call, no
   checkout, as before.
2. New output `docs_only`, true when every path matches
   `DOCS_RE='^(documentation/|\.claude/|\.cursor/|[^/]+\.md$|\.github/PULL_REQUEST_TEMPLATE\.md$)'`
   and no path matches `NOT_DOCS_RE`, the documentation/ paths tests read as live
   inputs (crew review of #1370): `documentation/reference/`,
   `plans/<domain>/fixtures/`, `plans/<domain>/samples/`,
   `plans/<domain>/seed-assets/` (also under `_archive/`),
   `plans/autocount/PLAN-autocount-cross-repo-contract.md` and
   `plans/_archive/scm/PLAN-scm-fulfilment-feedback-p4.md`. Evidence:
   `tests/scm/test_description_translation.py:433`,
   `tests/chatbot/test_samantha_26sep_s3_catalogue_sweep.py:146`,
   `tests/test_ingest_billing_documents_contract.py:23`,
   `tests/test_tag_template_seed_docs.py:36`,
   `sorento_crm_mcp/tests/test_presenters_top_selling.py:39`. Anything else (code,
   migration, Dockerfile, compose, workflow, lockfile, config, script, a markdown
   file inside a service tree) is not docs. Both jq filters emit
   `previous_filename` too, so a rename across the documentation boundary is
   judged on both of its paths.
3. Docs-only sets every area flag false, so validate-backend, validate-mcp,
   test-backend, test-backend-scm, validate-frontend and typecheck-frontend skip
   through their existing `if`s. `build-images`, `build-and-deploy` and
   `notify-owner` gate on `docs_only` directly; notify-owner needs it because its
   `always()` would otherwise mail "deploy failed" for a skipped deploy.
4. Fail-safe is the full pipeline: an empty list, a failed compare call, a zero
   `before` SHA, `workflow_dispatch`, or a list at the compare API's 300-file cap
   (possibly truncated) all report `docs_only=false`.
5. `check-migration-heads` still runs on every event (about 20 s). It is the fast
   gate and the required check by name, so a docs-only run still reports a real
   success on it; nothing about the concurrency groups or the `ci` label trigger
   changes.

What a docs-only push to main runs afterwards: `Changed areas` and `Single alembic
head (fast gate)`, both green, nothing else.

## Tests

- `sorento_crm_backend/tests/test_ci_docs_only_filter.py` extracts the step's `run`
  block out of deploy.yml and executes it under GitHub's bash flags with a stub
  `gh` that answers through the real `jq` filter from a canned API payload, so the
  shell under test is the shell that ships. Cases: docs-only on PR, push and
  merge_group; one non-docs path of each kind (each service tree, a migration,
  each Dockerfile, compose, both workflows, lockfile, config, scripts, markdown
  fixtures inside the trees, nested `documentation/` or `.claude/` folders, each
  test-input documentation path); renames across the boundary in both
  directions and within documentation; every fail-safe (zero SHA, gh failure on
  each event, empty list, 300 vs 299 files, workflow_dispatch).
- Self-check against drift: the same file scans every backend and MCP test with
  `ast` for the documentation/ paths test CODE names (pathlib `/` chains and
  `Path()`/`open()`/`read_text()`/`glob()` arguments; comments, docstrings and
  citation strings do not count), runs each through the step and fails when one
  would classify as docs. The fix is to extend `NOT_DOCS_RE`, never the test.
  Runs in `test-backend`; skips in the Docker image, where the workflow file is
  absent.

## Not done, on purpose

- No `paths-ignore` on the `push` trigger: it would stop the run entirely, so a
  docs merge would report no check at all, and it cannot express "everything except
  these trees" together with the merge_group and PR events. One classification, one
  place.
- "laneboard-style scripts" from the brief: nothing named laneboard exists in this
  repo, so there is no path to list. Add it to `DOCS_RE` when such a script lands.
- No skip for `.vscode/**`, `.gitignore`, root `*.yml` snapshots (`brands-grid.yml`
  and friends): not documentation, and rare enough that a full run costs nothing
  worth a wider rule.

UAC: `ci-docs-skip-29sep-acceptance-criteria.md` alongside.
