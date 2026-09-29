# UAC: docs-only change to main skips build, tests and deploy

Plan: `PLAN-ci-docs-skip-29sep.md`. Every AC names how it is checked.

- **AC-1 Docs-only push to main runs nothing heavy.** A push whose compare range
  holds only `documentation/**`, `.claude/**`, `.cursor/**`, root-level `*.md` or
  `.github/PULL_REQUEST_TEMPLATE.md` runs `Changed areas` and `Single alembic head
  (fast gate)` only; validate-*, test-*, typecheck-frontend, build-images,
  build-and-deploy and notify-owner all show `skipped`. Check: the first docs merge
  after this lands, its run page.
- **AC-2 No email for a docs-only push.** notify-owner is skipped, so the owner gets
  neither "succeeded" nor "failed". Check: same run, inbox.
- **AC-3 Any non-docs path keeps the full pipeline.** A push touching one file under
  any of `sorento_crm_backend/`, `sorento_crm_frontend/`, `sorento_crm_mcp/`,
  `sorento_crm/`, `scripts/`, `.github/workflows/`, or a root file that is not
  `*.md`, reports `docs_only=false` and every area true, and the deploy runs as
  before. Check: `test_ci_docs_only_filter.py::test_non_docs_path_survives_the_grep`
  and the step simulation.
- **AC-4 Markdown inside a service tree is not docs.** A change to
  `sorento_crm_backend/tests/chatbot/replay_turns/*.md`,
  `sorento_crm_frontend/e2e/fixtures/**/*.md` or `sorento_crm_mcp/README.md` keeps
  the full pipeline. Check: same test.
- **AC-5 Nested folders do not match.** `sorento_crm_frontend/documentation/x.md` and
  `sorento_crm_backend/.claude/x.md` are not docs. Check:
  `test_regex_is_anchored_at_path_start`.
- **AC-6 PR and merge-queue runs classify the same way.** A `ci`-labelled docs-only
  PR run and a docs-only merge_group run report `docs_only=true`; mixed ones
  `false`. Check: step simulation (`pr docs-only`, `merge_group docs-only`, mixed
  variants).
- **AC-7 Fail-safe is the full pipeline.** A zero `before` SHA, a failed `gh api`
  call, an empty file list, `workflow_dispatch`, or a 300-file list all report
  `docs_only=false` with every area true. Check: step simulation.
- **AC-8 The regex under test is the regex that ships.** The pytest reads `DOCS_RE=`
  from deploy.yml and fails if the line is missing, duplicated or not a single
  quoted literal. Check: `_docs_regex()` assertions.
- **AC-10 Documentation a test reads is not docs.** A change under
  `documentation/reference/`, `plans/<domain>/fixtures/`, `plans/<domain>/samples/`,
  `plans/<domain>/seed-assets/` (also under `_archive/`),
  `plans/autocount/PLAN-autocount-cross-repo-contract.md` or
  `plans/_archive/scm/PLAN-scm-fulfilment-feedback-p4.md` keeps the full pipeline.
  Check: `test_one_non_docs_path_keeps_the_full_pipeline` (the last eight cases).
- **AC-11 The deny list cannot drift from the tests.** A test that reads a new
  documentation/ path fails
  `test_every_documentation_path_a_test_reads_keeps_the_full_pipeline` until
  `NOT_DOCS_RE` covers it. Check: kill test, dropping `reference/` from
  `NOT_DOCS_RE` goes red.
- **AC-12 Renames count both paths.** A file moved from a service tree into
  documentation/ (or the reverse, or out of a fixtures folder) is not docs-only on
  PR, push and merge_group; a plan archived within documentation/ is. Check:
  `test_rename_*`; kill test, dropping `previous_filename` from the compare filter
  goes red.
- **AC-13 Only a `ci` label run joins the per-PR concurrency group.** Adding
  `needs-hand-test`, `lane-running`, `needs-decision` or any other label to a PR
  with a live `ci` run does not cancel it (2026-09-28, #1304, run 36387225667):
  the non-`ci` run's group is its own run id and its cancel-in-progress is false.
  Two `ci` label events on the same PR still share the group, so the newer run
  supersedes the older; push, merge_group and dispatch runs stay unique and never
  cancel. Check: `test_concurrency_*`, which evaluate the workflow's two
  expressions as written with each event's context.
- **AC-9 Existing behaviour unchanged for code changes.** PR area flags, the
  concurrency groups, the `ci` label one-shot trigger, `check-migration-heads` on
  every event, and the deploy for a code push are untouched. Check: diff review;
  this PR's own CI run is a mixed diff (workflow + docs + test) and must run the
  full set.
