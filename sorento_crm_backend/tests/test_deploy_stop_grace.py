"""Zero-downtime deploy: no backend colour is stopped faster than gunicorn's own grace.

CHAT-INBOX-QUEUE (UAC IQ-19, IQ-21, IQ-25; plan "Zero-downtime deploy"): every backend
process runs inbox drains, and on SIGTERM a drain finishes the row it is in (its sender POST
and done mark) within gunicorn's `graceful_timeout`. `docker compose stop` without `-t`
SIGKILLs after Docker's default 10 s, cutting a turn mid-row, whichever colour it is: the
OLD colour at the switch, or the NEW one when its health check fails or Postgres went down.

A static check on the two files as text (no docker, no flock), so it runs on every machine;
`test_blue_green_deploy_guards.py` runs the script itself where it can.
"""
from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND.parent / "scripts" / "blue_green_deploy.sh"
GUNICORN_CONF = BACKEND / "gunicorn.conf.py"

_TIMEOUT_FLAG = re.compile(r"(?:-t|--timeout|--time)[ =](\d+)")


def _graceful_timeout() -> int:
    match = re.search(r"^graceful_timeout\s*=\s*[^\n]*?(\d+)", GUNICORN_CONF.read_text(), re.MULTILINE)
    assert match, "gunicorn.conf.py sets no graceful_timeout"
    return int(match.group(1))


def _backend_stops() -> list[tuple[int, str]]:
    stops = []
    for number, line in enumerate(SCRIPT.read_text().splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.search(r"docker[ -]compose\s+stop\b", stripped) and "backend_" in stripped:
            stops.append((number, stripped))
    return stops


def test_every_backend_colour_stop_waits_longer_than_gunicorns_grace():
    grace = _graceful_timeout()
    stops = _backend_stops()
    assert stops, "found no `docker compose stop` of a backend colour in the deploy script"
    short = []
    for number, line in stops:
        flag = _TIMEOUT_FLAG.search(line)
        if flag is None or int(flag.group(1)) <= grace:
            short.append(f"blue_green_deploy.sh:{number}: {line}")
    assert short == [], (
        f"these stops would SIGKILL a backend colour before gunicorn's graceful_timeout "
        f"({grace} s) lets its drains finish their row; give each `-t` above {grace}:\n" + "\n".join(short)
    )
