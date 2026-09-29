# UAC: fast PR gate, full suite in the merge queue, validated push skips the replay

Plan: `PLAN-ci-fast-gate-29sep.md`. Every AC names how it is checked.

- **AC-1 A `ci`-labelled PR never runs the six backend shards.** `Backend test
  suite (Postgres, xdist) (1..6)` report `skipped` on every PR run. Check:
  `test_pull_request_fast_gate_*`; the first labelled PR after merge.
- **AC-2 SCM shards run on a PR only for SCM paths.** A PR touching
  `app/services/scm/`, `tests/scm/`, `app/models/scm.py`, an scm migration or a
  harness file runs the three SCM shards; a PR touching
  `app/services/procurement_service.py` or a frontend file does not. Check:
  `test_scm_path_on_a_pull_request_runs_the_scm_shards`,
  `test_non_scm_backend_path_on_a_pull_request_skips_the_scm_shards`.
- **AC-3 A merge-queue entry runs the full suite and never deploys.** Check:
  `test_merge_group_runs_the_full_suite_and_never_deploys`; the first queue run.
- **AC-4 A push to main after a green queue run runs build + deploy only.** The
  `changes` job prints `validated=true: run <id> (merge_group) ...`, the 16 test
  jobs show `skipped`, `build-images`, `build-and-deploy` and `notify-owner`
  run. Check: `test_prior_merge_queue_run_on_the_same_sha_validates`,
  `test_push_validated_runs_build_and_deploy_only`; the first queue merge's
  push run (also confirms the queue's SHA is main's SHA).
- **AC-5 A validated push still deploys when its gates are skipped.**
  `build-and-deploy` runs with every test need `skipped`, and does not run when
  `build-images` or the alembic gate failed. Check:
  `test_push_validated_with_a_failed_build_does_not_deploy`.
- **AC-6 Nothing uncertain validates.** No run on the SHA and no merged PR, a
  candidate with one `skipped` or `failure` gate, an all-skipped run, a
  fast-gate PR run, a failed jobs call, a failed API: all `validated=false` and
  the full suite runs. Check: `test_prior_*`.
- **AC-7 A full PR run on the merged PR's head validates.** Only when all 17
  gates succeeded in it. Check:
  `test_prior_full_pr_run_on_the_merged_pr_head_validates`.
- **AC-8 `GATES` names exactly the test jobs main runs.** Adding or renaming a
  test job without updating `GATES` fails the drift test. Check:
  `test_prior_gates_name_exactly_the_test_jobs_main_runs`.
- **AC-9 An unvalidated push with a failed gate does not deploy and still mails
  the owner.** Check: `test_push_with_a_failed_gate_does_not_deploy_but_still_notifies`.
- **AC-10 Docs-only, other-label and concurrency behaviour from #1370 is
  unchanged.** Check: the #1370 tests in the same file still pass (111 total).
- **AC-11 The two false comments are gone.** deploy.yml no longer claims an
  unlabelled PR "cannot merge"; both places point at the ruleset and the plan.
  Check: `grep -n "cannot merge" .github/workflows/deploy.yml` is empty.
- **AC-12 The ruleset list is exact.** The 18 names in the plan's table equal
  the `name:` values with matrix suffixes as reported on a real run. Check: the
  check names on this PR's own `ci` run against the table.
- **AC-13 Lint is not a gate.** No lint job is added; the plan records the
  measured 287 errors. Check: diff.
