"""Zero-downtime deploy: no backend colour is stopped faster than gunicorn's own grace.

CHAT-INBOX-QUEUE (UAC IQ-19, IQ-21, IQ-25; plan "Zero-downtime deploy"): every backend
process runs inbox drains, and on SIGTERM a drain finishes the row it is in (its sender POST
and done mark) within gunicorn's `graceful_timeout`. A stop without a timeout SIGKILLs after
Docker's default 10 s, cutting a turn mid-row, whichever colour it is: the OLD colour at the
switch, or the NEW one when its health check fails or Postgres went down.

A static check on the two files as text (no docker, no flock), so it runs on every machine;
`test_blue_green_deploy_guards.py` runs the script itself where it can. `short_backend_stops`
takes the script TEXT, so the samples below prove it catches what a reviewer could write:
a backslash-continued command, `down`, `restart`, `rm -s`, `up --force-recreate`, a plain
`docker stop`, and services named through a `${svc}_${NEW}` loop.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND.parent / "scripts" / "blue_green_deploy.sh"
GUNICORN_CONF = BACKEND / "gunicorn.conf.py"

_TIMEOUT = re.compile(r"(?:^|\s)(?:-t|--timeout|--time)(?:\s+|=)(\d+)\b")
_COMPOSE = re.compile(r"\bdocker(?:\s+compose|-compose)\b(?P<rest>.*)")
_PLAIN_DOCKER_STOP = re.compile(r"\bdocker\s+(?:container\s+)?(?:stop|restart)\b(?P<rest>.*)")
# A backend container or service: named literally, or a colour-templated name a loop fills
# in (`${svc}_${NEW}`, `"$svc"_"$OLD"`), which may be the backend.
_BACKEND_TARGET = re.compile(r"backend|\$\{?svc\}?[\"']?_[\"']?\$\{?(?:NEW|OLD|ACTIVE)\}?")


def graceful_timeout(conf_text: str) -> int:
    match = re.search(r"^graceful_timeout\s*=\s*[^\n]*?(\d+)", conf_text, re.MULTILINE)
    assert match, "gunicorn.conf.py sets no graceful_timeout"
    return int(match.group(1))


def _logical_lines(script_text: str) -> list[tuple[int, str]]:
    """The script's commands with backslash continuations joined, comments dropped."""
    out: list[tuple[int, str]] = []
    buffer, start = "", 0
    for number, raw in enumerate(script_text.splitlines(), start=1):
        line = raw.rstrip()
        if not buffer:
            start = number
            if line.lstrip().startswith("#"):
                continue
        if line.endswith("\\"):
            buffer += line[:-1] + " "
            continue
        buffer += line
        out.append((start, " ".join(buffer.split())))
        buffer = ""
    if buffer:
        out.append((start, " ".join(buffer.split())))
    return out


def _segments(line: str) -> list[str]:
    return [s.strip() for s in re.split(r"&&|\|\||;|\|(?!\|)|\bdo\b|\bthen\b", line) if s.strip()]


def _stops_a_backend(segment: str) -> bool:
    plain = _PLAIN_DOCKER_STOP.search(segment)
    if plain is not None and _BACKEND_TARGET.search(plain.group("rest")):
        return True
    compose = _COMPOSE.search(segment)
    if compose is not None:
        rest = compose.group("rest")
        words = rest.split()
        if "down" in words:
            return True  # every service, backends included
        if not _BACKEND_TARGET.search(rest):
            return False
        if "stop" in words or "restart" in words:
            return True
        if "rm" in words and re.search(r"(?:^|\s)(?:-\w*s\w*|--stop)\b", rest):
            return True
        if "up" in words and "--force-recreate" in words:
            return True
        return False
    return False


def short_backend_stops(script_text: str, grace: int) -> list[str]:
    """Every command in `script_text` that can stop or recreate a backend colour container
    without a `-t N` / `--timeout N` above `grace`, as `line N: command`."""
    short = []
    for number, line in _logical_lines(script_text):
        for segment in _segments(line):
            if not _stops_a_backend(segment):
                continue
            flag = _TIMEOUT.search(segment)
            if flag is None or int(flag.group(1)) <= grace:
                short.append(f"line {number}: {segment}")
    return short


def test_every_backend_colour_stop_waits_longer_than_gunicorns_grace():
    grace = graceful_timeout(GUNICORN_CONF.read_text())
    script = SCRIPT.read_text()
    found = [s for n, line in _logical_lines(script) for s in _segments(line) if _stops_a_backend(s)]
    assert len(found) >= 3, f"expected the NEW (x2) and OLD backend stops, found {found}"
    short = short_backend_stops(script, grace)
    assert short == [], (
        f"these would SIGKILL a backend colour before gunicorn's graceful_timeout ({grace} s) "
        f"lets its drains finish their row; give each `-t` above {grace}:\n" + "\n".join(short)
    )


@pytest.mark.parametrize(
    "sample",
    [
        'docker compose stop \\\n  "backend_${OLD}" "frontend_${OLD}" "mcp_${OLD}" || true',
        'echo stopping && docker compose stop "backend_${NEW}"',
        "docker compose down",
        "docker compose down --remove-orphans",
        'for svc in backend frontend mcp; do docker compose restart "${svc}_${NEW}"; done',
        'docker compose rm -sf "backend_${OLD}"',
        'docker compose rm --stop -f "backend_${OLD}"',
        'docker compose up -d --force-recreate --no-deps "backend_${NEW}"',
        'docker stop "$(docker compose ps -q backend_${OLD})"',
        'docker compose stop -t 100 "backend_${OLD}"',
        'docker compose stop -t 150 "backend_${OLD}"',
    ],
    ids=[
        "continued-line", "after-and", "down", "down-flags", "svc-loop-restart", "rm-sf",
        "rm-stop", "up-force-recreate", "plain-docker-stop", "below-grace", "equal-to-grace",
    ],
)
def test_the_check_catches_a_short_backend_stop(sample):
    assert short_backend_stops(sample, 150), f"missed a short backend stop in: {sample!r}"


@pytest.mark.parametrize(
    "sample",
    [
        'docker compose stop -t 160 \\\n  "backend_${OLD}" "frontend_${OLD}"',
        'docker compose stop --timeout=200 "backend_${NEW}"',
        'docker compose down --timeout 160',
        "docker compose up -d --force-recreate --no-deps worker worker_fast",
        'docker compose rm -f "backend_${OLD}" "frontend_${OLD}"',
        '# docker compose stop "backend_${OLD}"',
        'docker compose logs --tail=200 "backend_${NEW}" || true',
    ],
    ids=["continued-with-t", "timeout-equals", "down-with-timeout", "workers-only", "rm-without-stop", "comment", "logs"],
)
def test_the_check_passes_a_safe_command(sample):
    assert short_backend_stops(sample, 150) == []
