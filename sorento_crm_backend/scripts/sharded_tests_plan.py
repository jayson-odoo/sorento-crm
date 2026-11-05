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
each backend pool by its share of the full pool's estimated seconds (`file_costs`:
`.test_durations` plus the untimed test functions; `ceil(full_shards * selected / full)`), so a
delta shard is as long as a full one and no constant needs calibrating twice. A pool with no
file gets no runner. `pack` then puts whole files onto the pool's runners, longest first onto
the least loaded, written as <pool>-<i>.txt; each runner is a separate job.

Writes into --out: main.txt, scm.txt, migrations.txt, main_ddl.txt / scm_ddl.txt (the files of
each pool that name the `serial_ddl` marker; backend-relative test files),
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


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


DEF_RE = re.compile(r"^\s*(?:async\s+)?def (test_\w+)", re.M)


def file_costs(root: Path, files: list[str]) -> dict[str, float]:
    """Estimated seconds per test file: its recorded `.test_durations` seconds plus, for each
    test function the file defines that has no recorded run, the file's own mean per recorded
    function (the suite's mean for a file with none). The committed file held 26k of ~56k tests
    on 5 Nov 2026, so recorded seconds alone put 25.6k of an estimated 61k main-pool seconds on
    the files that happened to be timed."""
    try:
        durations = json.loads((root / ".test_durations").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        durations = {}
    rec: dict[str, list] = {}
    for node, secs in durations.items():
        f, _, rest = node.partition("::")
        entry = rec.setdefault(f, [0.0, set()])
        entry[0] += float(secs)
        entry[1].add(rest.split("[", 1)[0])
    n_fn = sum(len(e[1]) for e in rec.values())
    mean = (sum(e[0] for e in rec.values()) / n_fn) if n_fn else 1.0
    costs = {}
    for f in files:
        secs, fns = rec.get(f, (0.0, set()))
        per = secs / len(fns) if fns else mean
        missing = set(DEF_RE.findall(_text(root / f))) - fns
        costs[f] = max(secs + len(missing) * per, 0.1)
    return costs


def pack(files: list[str], n: int, costs: dict[str, float]) -> list[list[str]]:
    """Whole files onto n shards, longest first onto the least loaded (LPT). Whole files keep
    `--dist loadfile` and each module's fixtures on one runner; pytest-split's per-test
    least_duration spread every file over all 36 shards and made each one slower than the
    contiguous chunks (run 41982964838)."""
    shards: list[list[str]] = [[] for _ in range(n)]
    load = [0.0] * n
    for f in sorted(files, key=lambda f: (-costs[f], f)):
        i = min(range(n), key=lambda k: (load[k], k))
        shards[i].append(f)
        load[i] += costs[f]
    return [sorted(s) for s in shards]


def shards_for(selected: list[str], full: list[str], full_shards: int, costs: dict[str, float]) -> int:
    """Runners for a delta pool: its share of the full pool's estimated seconds."""
    if not selected:
        return 0
    total = sum(costs[f] for f in full) or 1.0
    return max(1, min(full_shards, math.ceil(full_shards * sum(costs[f] for f in selected) / total)))


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
        costs = file_costs(root, full_main + full_scm)
        sel_main, sel_scm, _ = pools(tests)
        n_main = shards_for(sel_main, full_main, main_shards, costs)
        n_scm = shards_for(sel_scm, full_scm, scm_shards, costs)
        reason = (f"delta {(base or '')[:10]}..{(head or '')[:10]}: backend {res.backend}, "
                  f"{len(tests)} of {res.total} test files ({res.backend_reason}); "
                  f"vitest {res.vitest} ({res.vitest_reason})")
    main, scm, migrations = pools(tests)
    costs = file_costs(root, main + scm)
    # The serial runner's `-m serial_ddl` passes collect only the files that name the marker
    # (it is applied in the test files themselves): collecting the whole main pool to run its
    # ~110 serial_ddl tests took 949 s of the serial runner's 21 min (run 41977895392).
    ddl = lambda files: [f for f in files if "serial_ddl" in _text(root / f)]  # noqa: E731
    n_vitest = vitest_shards if vitest == "full" else (1 if vitest == "related" else 0)
    return {
        "main": main, "scm": scm, "migrations": migrations, "vitest_related": related,
        "main_ddl": ddl(main), "scm_ddl": ddl(scm),
        "main_shard_files": pack(main, n_main, costs) if n_main else [],
        "scm_shard_files": pack(scm, n_scm, costs) if n_scm else [],
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
    for name in ("main", "scm", "migrations", "vitest_related", "main_ddl", "scm_ddl"):
        (out / f"{name}.txt").write_text("".join(f"{t}\n" for t in p[name]), encoding="utf-8")
    for pool in ("main", "scm"):
        for i, files in enumerate(p[f"{pool}_shard_files"], start=1):
            (out / f"{pool}-{i}.txt").write_text("".join(f"{t}\n" for t in files), encoding="utf-8")
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
