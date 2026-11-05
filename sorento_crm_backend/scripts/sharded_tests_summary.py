"""The `crew-tests:` comment of one .github/workflows/tests-sharded.yml run (CI-PARALLEL-ACTIONS).

Reads the junit files every shard uploaded (one directory per artifact, as
actions/download-artifact writes them with a pattern), the run's jobs (`gh api .../jobs`, one JSON
object per line) and the run's start time, and prints markdown whose first line is

  crew-tests: <head sha> <nightly full sweep | delta since nightly <base>> backend P passed/F failed, vitest P/F[ FAILED (<why>)]

followed by one row per shard (job conclusion, passed, failed, minutes), the failing test ids, the
wall clock and the billable runner minutes (each job rounded up to a whole minute, as GitHub bills
it; this summary job itself is not finished and not counted). A shard counts as FAILED when a
test failed, when its job did not succeed, or when it uploaded no junit (it crashed before
pytest/vitest wrote one): a run that lost a shard never reads as a pass. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

JOB_RE = re.compile(r"^(?:backend (?P<pool>\w+) (?P<bshard>\d+)/\d+|vitest (?P<vshard>\d+)/\d+)$")
MAX_IDS = 60


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def count_junit(paths: list[Path]) -> tuple[int, int, list[str]]:
    passed = failed = 0
    bad: list[str] = []
    for path in paths:
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            continue
        for case in root.iter("testcase"):
            kids = {c.tag for c in case}
            if kids & {"failure", "error"}:
                failed += 1
                bad.append(f"{case.get('classname') or case.get('file') or ''}::{case.get('name')}")
            elif "skipped" not in kids:
                passed += 1
    return passed, failed, bad


def summarise(junit: Path, jobs: list[dict], started: str, now: datetime, *, head: str, mode: str, base: str,
              reason: str, run_url: str) -> str:
    rows = []
    totals = {"backend": [0, 0], "vitest": [0, 0]}
    failing: list[str] = []
    problems: list[str] = []
    billable = 0
    for job in sorted(jobs, key=lambda j: j.get("name", "")):
        name = job.get("name", "")
        start, end = _ts(job.get("started_at")), _ts(job.get("completed_at"))
        minutes = 0
        if job.get("status") == "completed" and start and end and job.get("conclusion") != "skipped":
            minutes = max(1, math.ceil((end - start).total_seconds() / 60))
        billable += minutes
        m = JOB_RE.match(name)
        if not m:
            continue
        area = "backend" if m.group("pool") else "vitest"
        key = f"junit-backend-{m.group('pool')}-{m.group('bshard')}" if area == "backend" else f"junit-vitest-{m.group('vshard')}"
        files = sorted((junit / key).glob("*.xml")) if (junit / key).is_dir() else []
        p, f, bad = count_junit(files)
        totals[area][0] += p
        totals[area][1] += f
        failing += bad
        conclusion = job.get("conclusion") or job.get("status")
        verdict = "ok"
        if f:
            verdict = f"{f} failed"
        elif conclusion != "success":
            verdict = f"job {conclusion}"
        elif not files:
            verdict = "no junit"
        if verdict != "ok":
            problems.append(f"{name}: {verdict}")
        rows.append(f"| {name} | {conclusion} | {p} | {f} | {minutes} |")

    t0 = _ts(started)
    wall = math.ceil((now - t0).total_seconds() / 60) if t0 else 0
    label = "nightly full sweep" if mode == "full" else f"delta since nightly {base}"
    be, fe = totals["backend"], totals["vitest"]
    verdict = f" FAILED ({'; '.join(problems[:8])}{'; ...' if len(problems) > 8 else ''})" if problems else ""
    out = [
        f"crew-tests: {head} {label} backend {be[0]} passed/{be[1]} failed, vitest {fe[0]}/{fe[1]}{verdict}",
        "",
        f"selection: {reason}",
        f"wall clock: {wall} min (run start to this summary); billable runner minutes: {billable} "
        f"(each finished job rounded up to a minute; this summary job not counted)",
        f"run: {run_url}",
        "",
        "| shard | job | passed | failed | billed min |",
        "| --- | --- | --- | --- | --- |",
        *rows,
    ]
    if failing:
        out += ["", f"failing test ids ({len(failing)}):", "```",
                *failing[:MAX_IDS], *([f"... and {len(failing) - MAX_IDS} more"] if len(failing) > MAX_IDS else []),
                "```"]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--junit", required=True)
    ap.add_argument("--jobs", required=True, help="one job JSON object per line")
    ap.add_argument("--started", default="")
    ap.add_argument("--head", required=True)
    ap.add_argument("--mode", required=True)
    ap.add_argument("--base", default="")
    ap.add_argument("--reason", default="")
    ap.add_argument("--run-url", default="")
    args = ap.parse_args(argv)
    jobs = [json.loads(line) for line in Path(args.jobs).read_text(encoding="utf-8").splitlines() if line.strip()]
    sys.stdout.write(summarise(Path(args.junit), jobs, args.started, datetime.now(timezone.utc), head=args.head,
                               mode=args.mode, base=args.base, reason=args.reason, run_url=args.run_url))
    return 0


if __name__ == "__main__":
    sys.exit(main())
