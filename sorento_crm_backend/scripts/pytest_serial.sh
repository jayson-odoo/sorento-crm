#!/usr/bin/env bash
# Run pytest holding an exclusive lock, so two suites never run at once.
#
# Needed because conftest drops EVERY `zzt_%` schema at session start. Two
# concurrent sessions therefore delete each other's scratch schemas, and the
# damage shows up as hundreds of unrelated failures in files that touch nothing
# in common. Zero `errors` in the summary is the tell that a run was clean.
#
# Usage:  scripts/pytest_serial.sh tests/test_thing.py -q
set -uo pipefail
cd "$(dirname "$0")/.."

LOCK="${PYTEST_SERIAL_LOCK:-/private/tmp/sorento-pytest-${USER}.lock}"
WAIT_SECONDS="${PYTEST_SERIAL_WAIT:-2400}"

exec venv/bin/python - "$LOCK" "$WAIT_SECONDS" "$@" <<'PY'
import fcntl, os, subprocess, sys, time

lock_path, wait_seconds, *pytest_args = sys.argv[1:]
deadline = time.time() + float(wait_seconds)
handle = open(lock_path, "w")

while True:
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        break
    except BlockingIOError:
        if time.time() > deadline:
            print(f"pytest_serial: gave up waiting for {lock_path}", file=sys.stderr)
            raise SystemExit(75)  # EX_TEMPFAIL
        print("pytest_serial: another suite is running, waiting...", flush=True)
        time.sleep(15)

handle.write(f"{os.getpid()}\n")
handle.flush()
try:
    raise SystemExit(subprocess.call(["venv/bin/python", "-m", "pytest", *pytest_args]))
finally:
    fcntl.flock(handle, fcntl.LOCK_UN)
PY
