"""CLI entry point.

    python -m scripts.scm_sim init
    python -m scripts.scm_sim run [--baseline] [--scenario SIM-P007]
    python -m scripts.scm_sim compare [--strict]
    python -m scripts.scm_sim seed-auth
    python -m scripts.scm_sim serve [--port PORT]

CRITICAL ORDERING: ``DATABASE_URL`` (and ``DIRECT_URL``) are resolved to the sim database
and written into ``os.environ`` here, BEFORE this module imports anything under
``scripts.scm_sim.runner`` (which is the first thing that touches ``app.*``). Every module
in this package keeps its ``app.*`` imports function-local for exactly this reason - do not
add a module-level ``from app...`` import anywhere in this package.
"""
from __future__ import annotations

import argparse
import os
import sys


def _set_sim_database_env() -> None:
    # Import-light: only touches sqlalchemy + the local filesystem, never app.*.
    sys.path.insert(0, os.getcwd())
    from scripts.scm_sim.runner import resolve_sim_database_url

    url = resolve_sim_database_url()
    os.environ["DATABASE_URL"] = url
    os.environ["DIRECT_URL"] = url
    print(f"[scm_sim] using database: {url.rsplit('@', 1)[-1]}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.scm_sim")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create + bootstrap the dedicated sim database.")

    run_p = sub.add_parser("run", help="Wipe, reseed, run the engine, write a snapshot.")
    run_p.add_argument("--baseline", action="store_true",
                       help="Also write the result to baselines/baseline.json.")
    run_p.add_argument("--scenario", default=None, metavar="CODE",
                       help="Seed + run only this one scenario code (e.g. SIM-P007).")

    cmp_p = sub.add_parser("compare", help="Diff snapshots/current.json vs baselines/baseline.json.")
    cmp_p.add_argument("--strict", action="store_true",
                       help="Exit 1 if anything changed/new/gone (default: report only).")

    sub.add_parser("seed-auth", help="Copy superadmin/admin auth from the real dev "
                    "database into the sim database (idempotent).")

    serve_p = sub.add_parser("serve", help="Serve app.main:app against the sim database "
                              "(uvicorn, foreground).")
    serve_p.add_argument("--port", type=int, default=8060, metavar="PORT",
                         help="Port to bind (default: 8060, matches the FE build baked-in "
                              "NEXT_PUBLIC_API_URL).")

    args = parser.parse_args()

    if args.command == "compare":
        # No database needed to compare two JSON files on disk.
        from scripts.scm_sim.compare import compare
        from scripts.scm_sim.runner import BASELINE_PATH, SNAPSHOT_PATH
        return compare(BASELINE_PATH, SNAPSHOT_PATH, strict=args.strict)

    _set_sim_database_env()
    from scripts.scm_sim import runner

    if args.command == "init":
        runner.cmd_init()
        return 0

    if args.command == "run":
        runner.run_once(scenario_code=args.scenario, bless=args.baseline)
        return 0

    if args.command == "seed-auth":
        runner.cmd_seed_auth()
        return 0

    if args.command == "serve":
        runner.cmd_serve(args.port)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
