# PLAN: release delta runs only the affected tests (RELEASE-DELTA-AFFECTED)

Status: in progress (small fix track: CI/test tooling only, no migration, no auth change)

Owner ruling, 5 Nov 2026 ~11:40 MYT (verbatim): "hm we should run the SCM tests only if they are
affected, the key is to run only the tests that are affected, dependent, or depended by".

## Today

`scripts/release-delta.sh` always runs the migration tests, ALL of `tests/scm/` (~5,400 tests),
the backend test files the diff touches or that import a touched `app/` module (one regex level),
and the FULL vitest.

## Change

A stdlib selector, `sorento_crm_backend/scripts/release_delta_select.py`, builds the backend
import graph (every `.py` under `app/`, `scripts/`, `tests/`; static AST imports incl. relative
ones, plus dotted `app.x.y` strings such as `mock.patch` targets) and caches it per backend tree
sha. Rules are in the module docstring and in `documentation/agents/cloud-lanes.md`.

- dependents: a test file whose transitive imports reach a changed module;
- depended-by: for a changed module M and each module D that M imports directly, the test files
  named `test_<D>.py` / `test_<D>_*.py` that import D directly;
- `tests/scm/` only when the graph selects it; migration tests only on `alembic/` or
  `app/models/` changes;
- frontend: `vitest related --run <changed files>` plus the source-scanning guards; full vitest on
  shared config / setup changes;
- full suite fallback: any conftest.py, test infra, pytest/pyproject/requirements, package.json /
  lockfile, env bootstrap, or a graph build failure. The reason is printed.
- the `crew-tests:` line gains `selected N of M`.

## Proof

Old vs new selection on `42d1a56c..019770c1` and `019770c1..main`: counts and time, posted on
the PR.
