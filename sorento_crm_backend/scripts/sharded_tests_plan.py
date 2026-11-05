"""Plan one run of .github/workflows/tests-sharded.yml (CI-PARALLEL-ACTIONS, 5 Nov 2026).

Owner, 5 Nov 2026: the release delta and the nightly full sweep run on GitHub-hosted runners,
sharded in parallel, instead of serially in one Claude Code cloud sandbox.

MODES
  full   every backend test file (tests/**/test_*.py minus tests/ci_excluded.txt), the
         tests/nightly_only.txt entries INCLUDED, and the full vitest suite. The nightly sweep.
  delta  scripts/release_delta_select.py on <base>..<head> (RELEASE-DELTA-AFFECTED: the changed
         tests, their dependents and the tests of what the change calls; never a
         tests/nightly_only.txt entry), and its vitest verdict (full | related | none).

POOLS (deploy.yml's split, which nightly-sweep.sh and release-delta.sh keep): tests/scm/ and the
rest of tests/ run in separate pytest sessions (several main-tree files import
tests.scm.conftest by name), tests/test_migration_*.py serially on one runner with the
`serial_ddl` tests of both pools.

SHARDS. A full run uses --main-shards / --scm-shards / --vitest-shards runners. A delta run sizes
each backend pool by its share of the full pool's committed `.test_durations` seconds
(`ceil(full_shards * selected / full)`, a file with no recorded test at the median file), so a
delta shard is as long as a full one and no constant needs calibrating twice. A pool with no
file gets no runner. pytest-split then balances the files of a pool across its runners by the
same durations (`--splits N --group i`), each runner a separate job.

Writes into --out: main.txt, scm.txt, migrations.txt (backend-relative test files),
vitest_related.txt (frontend-relative), plan.txt (the human summary); and key=value lines on
stdout (also appended to $GITHUB_OUTPUT when set): main_shards / scm_shards / vitest_shards (JSON
lists of 1-based shard numbers, [] for none), main_n, scm_n, vitest_n, serial (true|false),
vitest (full|related|none), reason (one line). Stdlib only.

Usage:
  sharded_tests_plan.py --mode full  --out <dir>
  sharded_tests_plan.py --mode delta --base <sha> --head <sha> --out <dir>
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_delta_select as rds  # noqa: E402

TEST_RE = re.compile(r"^tests/([A-Za-z0-9_.-]+/)*test_[A-Za-z0-9_.-]*\.py$")
MIGRATION_RE = re.compile(r"^tests/test_migration_[A-Za-z0-9_.-]*\.py$")

# Runners for a full run. Measured on GitHub-hosted 4-vCPU runners: see the plan
# (documentation/plans/ci/PLAN-ci-parallel-actions-05nov.md, "Measured").
MAIN_SHARDS = 36
SCM_SHARDS = 3
VITEST_SHARDS = 6


def all_tests(root: Path) -> list[str]:
    excluded = rds._excluded(root)
    found = []
    for path in (root / "tests").rglob("test_*.py"):
        rel = path.relative_to(root).as_posix()
        if TEST_RE.match(rel) and rel not in excluded:
            found.append(rel)
    return sorted(found)


def pools(tests: list[str]) -> tuple[list[str], list[str], list[str]]:
    main, scm, migrations = [], [], []
    for t in tests:
        if MIGRATION_RE.match(t):
            migrations.append(t)
        elif t.startswith("tests/scm/"):
            scm.append(t)
        else:
            main.append(t)
    return main, scm, migrations


def file_seconds(root: Path) -> dict[str, float]:
    try:
        durations = json.loads((root / ".test_durations").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    per_file: dict[str, float] = {}
    for node, secs in durations.items():
        f = node.split("::", 1)[0]
        per_file[f] = per_file.get(f, 0.0) + float(secs)
    return per_file


def shards_for(selected: list[str], full: list[str], full_shards: int, seconds: dict[str, float]) -> int:
    """Runners for a delta pool: its share of the full pool's recorded seconds."""
    if not selected:
        return 0
    known = [seconds[f] for f in full if f in seconds]
    median = statistics.median(known) if known else 1.0
    cost = lambda files: sum(seconds.get(f, median) for f in files)  # noqa: E731
    total = cost(full) or 1.0
    return max(1, min(full_shards, math.ceil(full_shards * cost(selected) / total)))


def plan(mode: str, root: Path, *, base: str | None = None, head: str | None = None,
         changed: list[str] | None = None, main_shards: int = MAIN_SHARDS, scm_shards: int = SCM_SHARDS,
         vitest_shards: int = VITEST_SHARDS) -> dict:
    full_tests = all_tests(root)
    full_main, full_scm, _ = pools(full_tests)
    if mode == "full":
        tests, vitest, related = full_tests, "full", []
        reason = f"full sweep: {len(full_tests)} backend test files (nightly-only included), full vitest"
        n_main, n_scm = (main_shards if full_main else 0), (scm_shards if full_scm else 0)
    else:
        if changed is None:
            changed = rds.git_changed(root.resolve().parent, base, head)
        key = rds.tree_sha(root.resolve().parent, head, rds.BACKEND_PREFIX) if head else None
        res = rds.select(changed, root, cache_key=key, cache_dir=None)
        tests, vitest, related = list(res.tests), res.vitest, list(res.vitest_files)
        seconds = file_seconds(root)
        sel_main, sel_scm, _ = pools(tests)
        n_main = shards_for(sel_main, full_main, main_shards, seconds)
        n_scm = shards_for(sel_scm, full_scm, scm_shards, seconds)
        reason = (f"delta {(base or '')[:10]}..{(head or '')[:10]}: backend {res.backend}, "
                  f"{len(tests)} of {res.total} test files ({res.backend_reason}); "
                  f"vitest {res.vitest} ({res.vitest_reason})")
    main, scm, migrations = pools(tests)
    n_vitest = vitest_shards if vitest == "full" else (1 if vitest == "related" else 0)
    return {
        "main": main, "scm": scm, "migrations": migrations, "vitest_related": related,
        "main_n": n_main, "scm_n": n_scm, "vitest_n": n_vitest, "vitest": vitest,
        "serial": bool(main or scm or migrations), "reason": reason,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=("full", "delta"), required=True)
    ap.add_argument("--base")
    ap.add_argument("--head")
    ap.add_argument("--out", required=True)
    ap.add_argument("--backend", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--main-shards", type=int, default=MAIN_SHARDS)
    ap.add_argument("--scm-shards", type=int, default=SCM_SHARDS)
    ap.add_argument("--vitest-shards", type=int, default=VITEST_SHARDS)
    args = ap.parse_args(argv)
    if args.mode == "delta" and not (args.base and args.head):
        ap.error("--mode delta needs --base and --head")

    p = plan(args.mode, Path(args.backend), base=args.base, head=args.head, main_shards=args.main_shards,
             scm_shards=args.scm_shards, vitest_shards=args.vitest_shards)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("main", "scm", "migrations", "vitest_related"):
        (out / f"{name}.txt").write_text("".join(f"{t}\n" for t in p[name]), encoding="utf-8")
    shards = lambda n: json.dumps(list(range(1, n + 1)))  # noqa: E731
    lines = [
        f"main_shards={shards(p['main_n'])}", f"scm_shards={shards(p['scm_n'])}",
        f"vitest_shards={shards(p['vitest_n'])}",
        f"main_n={p['main_n']}", f"scm_n={p['scm_n']}", f"vitest_n={p['vitest_n']}",
        f"serial={'true' if p['serial'] else 'false'}", f"vitest={p['vitest']}",
        f"reason={p['reason']}",
    ]
    summary = (f"{p['reason']}\nmain: {len(p['main'])} files on {p['main_n']} runners; "
               f"tests/scm: {len(p['scm'])} files on {p['scm_n']} runners; "
               f"migrations: {len(p['migrations'])} files (serial runner: {p['serial']}); "
               f"vitest: {p['vitest']} on {p['vitest_n']} runners\n")
    (out / "plan.txt").write_text(summary, encoding="utf-8")
    print("\n".join(lines))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
