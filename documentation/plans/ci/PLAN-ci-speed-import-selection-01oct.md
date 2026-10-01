Status: small fix track (CI only, no product code, no migration) - in build

# CI-SPEED: PR CI runs the tests that import what the PR changed; release shard 1 rebalanced

Owner approval: 1 Oct retro, decision 4.

## Measured facts (from crew's CI analysis, deploy.yml on main at 53c5f7af)

- A PR runs only the backend test files it changes (`BACKEND_TESTS_RE`, job `changes`), the SCM
  shards only on SCM paths (`SCM_RE`), and the six main shards never (`test-backend` carries
  `github.event_name != 'pull_request'`).
- 6 of 14 releases since 26 Sep failed at the full run (~40 min each). 1 Oct:
  `tests/test_ingest_parity_security_fixes.py` imports `app.services.shipping_order_ingest_service`
  (line 42) and `shipping_order_rules`, both changed by #1411 (123d4282c), and never ran on the PR.
- Release critical path is main shard 1: p50 34.3 / max 41.2 min vs 18-23 for shards 2-6. Its
  xdist step is 25.6 min vs 12.5 on shard 2. The serial migration and serial_ddl steps run only
  on shard 1 (+2.2 min).

## Change

1. `sorento_crm_backend/scripts/ci_select_tests.py` (stdlib only): given the PR's changed files,
   maps each changed `sorento_crm_backend/app/**.py` to its dotted module, adds every `app/`
   module that imports it (one level), and selects every test file that names any of those
   modules (`import app.x`, `from app.x import`, `from app.pkg import x`, or a dotted string
   such as a `mock.patch` target). Changed test files are always selected. Cap by time
   (crew ruling 1 Oct, option b): the selection's estimated CPU seconds from the committed
   `.test_durations` (summed per file; a file with no history counts at the median file) above
   3600 reports `full=true` instead of a list. #1411: 216 files, ~2668 CPU-s, under the budget. The selected list is printed in the job log.
2. `changes` checks out the backend tree (only when the PR touches `sorento_crm_backend/app/`) and
   runs the script. `backend_tests` becomes the selection; `backend_full=true` makes the six main
   shards and the SCM shards run on that PR (and the changed-files job steps aside).
3. `test-backend-changed` runs the selection in two passes, like the shards: xdist `--dist
   loadfile` for everything not migration / serial_ddl, then those serially.
4. Release shard rebalance: refresh `.test_durations` from a real run, keep the slow chatbot replay
   files on different shards, move the serial migration / DDL steps off the slowest shard.

Not changed: caching, the production gate, image builds, release ordering.

## Tests

`sorento_crm_backend/tests/test_ci_select_tests.py` (red first): direct import, from-package
import, relative import, transitive one level (and not two), patch-string match, budget on both
sides of the threshold, median for unknown files, scm exclusion, CLI outputs, and #1411's real
diff selecting `tests/test_ingest_parity_security_fixes.py`. `tests/test_ci_docs_only_filter.py`
covers the `backend_code` output, the select step and the job gating on `backend_full`.
