# UAC: CI-STALE-MERGE-REF

- AC-1: A `ci` re-label whose GitHub merge commit was built on an older main (parent 1 is not
  main's head now) never takes the `pr-validated-tree` marker: every area the PR touches is tested.
- AC-2: A merge commit whose parent 2 is not the PR head now is likewise never validated.
- AC-3: When parent 1 is main's head and parent 2 is the PR head, an existing marker still skips
  the tests (the CI-COST round 2 saving is kept).
- AC-4: A failed lookup (merge commit, main ref or artifacts) tests.
- AC-5: The PR gate checks out the PR head and merges main's head at job time before any gate
  runs; the log names the main it merged.
- AC-6: A PR head that conflicts with main fails the PR gate with an error naming the files.
- AC-7: The validated-tree marker a passing PR gate uploads is the tree of that live merge.
- AC-8: The import-based selection reads the same live merge.
- AC-9: Off a pull_request (push, merge_group, release dispatch) checkout ref, fetch depth and
  steps are what they were.
