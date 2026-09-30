# CI-TESTS-ONLY acceptance criteria

Plan: `PLAN-ci-tests-only-30sep.md`. Each criterion names the simulation case in
`sorento_crm_backend/tests/test_ci_docs_only_filter.py` that pins it.

- AC-1 A `ci`-labelled PR whose only change is a backend test file outside `tests/scm/`
  runs the light checks (alembic gate, changed areas, validate-backend) AND the changed
  file, and never the six backend shards.
  `test_pull_request_that_changes_a_test_file_runs_it`,
  `test_tests_only_pull_request_is_not_docs_and_lists_the_changed_test`.
- AC-2 A PR that changes code and a test file runs the existing gates for the code and the
  changed test file. `test_pull_request_with_code_and_a_test_file_runs_both_gates`,
  `test_changed_test_files_are_listed_beside_code_changes`.
- AC-3 A change under `tests/scm/` runs the SCM shards, as before, and is not in the
  changed-files list. `test_scm_test_change_runs_the_scm_shards_not_the_changed_files_job`.
- AC-4 Harness files, helper modules, fixtures, `ci_excluded.txt`, MCP and frontend tests,
  and a path holding a shell metacharacter are not in the list.
  `test_paths_that_are_not_a_runnable_backend_test_file_are_not_listed`.
- AC-5 Off a PR (push, merge_group, workflow_dispatch) the list is empty and the job is
  skipped; the full shards cover the files. `test_changed_tests_are_never_listed_off_a_pull_request`,
  `test_changed_tests_job_never_runs_off_a_pull_request_or_with_another_label`.
- AC-6 Pure docs still skip everything but the root jobs, and the list is empty on every
  early exit. `test_docs_only_change_skips_everything`,
  `test_changed_tests_list_is_empty_on_every_early_exit`.
- AC-7 A deleted or renamed-away test file and a `ci_excluded.txt` entry are dropped before
  pytest runs; nothing left is a pass with nothing run; every step after the select step
  gates on its output. `test_changed_tests_step_*`,
  `test_changed_tests_job_steps_after_select_gate_on_its_output`.
- AC-8 Label gating unchanged: a non-`ci` label runs nothing.
  `test_pull_request_with_another_label_runs_nothing`.
