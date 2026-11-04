"""The controller's I/O loop (HA-CF-FAILOVER, security review S2): run the real main() as a
process against a fake ha-pg.sh and a fake Cloudflare API, with 1 s ticks.

Run: python3 -m pytest infra/tests -q
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

CONTROLLER = Path(__file__).resolve().parents[1] / "scripts" / "cf_failover.py"

FAKE_PG = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_DIR/pg.log"
case "$1" in
  fence) [ -e "$FAKE_DIR/fence_fail" ] && exit 1 ;;
  observe)
    [ -e "$FAKE_DIR/observe_fail" ] && exit 1
    printf 'self_pg=primary\nself_streaming=t\nself_lsn=100\nsync_names=\npeer_pg=standby\npeer_lsn=100\n' ;;
esac
exit 0
"""


@pytest.fixture
def cf():
    """A fake Cloudflare answering every pool with `body` (settable)."""
    state = {"body": {"success": True, "result": {"pop_health": {"SG": {"healthy": True}}}}}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            raw = json.dumps(state["body"]).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(raw)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield state, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def box(tmp_path):
    pg = tmp_path / "ha-pg.sh"
    pg.write_text(FAKE_PG)
    pg.chmod(0o755)
    wd = tmp_path / "watchdog"
    wd.write_bytes(b"")
    token = tmp_path / "token"
    token.write_text("t\n")
    token.chmod(0o600)
    return tmp_path, {
        "NODE_NAME": "crm-a", "PEER_NAME": "crm-b", "TICK": "1",
        "CF_CHECK_INTERVAL": "1", "CF_CONSECUTIVE_DOWN": "1",  # FENCE_AFTER = 2 s
        "PG_CMD": str(pg), "STATE_FILE": str(tmp_path / "state.json"), "FAKE_DIR": str(tmp_path),
        "WATCHDOG_DEVICE": str(wd), "CF_ACCOUNT_ID": "acc", "CF_POOL_SELF": "pa", "CF_POOL_PEER": "pb",
        "CF_API_TOKEN_FILE": str(token), "PATH": os.environ["PATH"],
    }


def run(env, ticks=5, **extra):
    e = {**env, "MAX_TICKS": str(ticks), **extra}
    return subprocess.run([sys.executable, str(CONTROLLER)], env=e, capture_output=True, text=True, timeout=60)


def pg_calls(tmp):
    p = tmp / "pg.log"
    return p.read_text().split() if p.exists() else []


def test_a_controller_that_cannot_observe_fences_and_never_arms_the_watchdog(box, cf):
    tmp, env = box
    _, base = cf
    (tmp / "observe_fail").write_text("")
    r = run(env, ticks=5, CF_API_BASE=base)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "fence" in pg_calls(tmp), r.stdout
    assert pg_calls(tmp).count("fence") == 1
    assert (tmp / "watchdog").read_bytes() == b"", "a failing loop must not keep the box alive"
    assert "fencing this node" in r.stdout


def test_healthy_ticks_pet_the_watchdog_and_take_no_action(box, cf):
    tmp, env = box
    _, base = cf
    r = run(env, ticks=3, CF_API_BASE=base)
    assert r.returncode == 0, r.stdout + r.stderr
    calls = pg_calls(tmp)
    assert set(calls) <= {"observe", "prune", "7"}, calls
    assert (tmp / "watchdog").read_bytes().startswith(b"\0")
    assert (tmp / "watchdog").read_bytes().endswith(b"V")  # MAX_TICKS exit disarms


@pytest.mark.parametrize("body", [
    {"success": True, "result": []},
    {"success": True, "result": {"pop_health": []}},
    {"success": True, "result": {"pop_health": {"SG": "yes"}}},
    ["not", "a", "dict"],
])
def test_a_malformed_cloudflare_answer_is_unknown_not_a_crash(box, cf, body):
    tmp, env = box
    state, base = cf
    state["body"] = body
    r = run(env, ticks=2, CF_API_BASE=base)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "tick failed" not in r.stdout, r.stdout
    assert "cf_self='unknown'" in r.stdout or "action" not in r.stdout


def test_plain_http_cloudflare_base_is_refused(box):
    _, env = box
    r = run(env, ticks=1, CF_API_BASE="http://api.cloudflare.example/client/v4")
    assert r.returncode == 2 and "https" in r.stdout


def test_an_unwritable_state_file_is_a_failed_tick(box, cf):
    tmp, env = box
    _, base = cf
    r = run(env, ticks=4, CF_API_BASE=base, STATE_FILE=str(tmp / "missing-dir" / "state.json"))
    assert r.returncode == 0
    assert "tick failed" in r.stdout and "fence" in pg_calls(tmp)


def test_a_failed_fence_stops_petting_the_watchdog(box, cf):
    # Review B1/B2: Cloudflare cannot see this primary and no standby streams, so its lease
    # expires (2 s) and it fences; the fence fails and Postgres still reads primary. From then
    # on the watchdog is never petted, so the box reboots and comes back read-only (D1).
    tmp, env = box
    state, base = cf
    state["body"] = {"success": True, "result": {"pop_health": {"SG": {"healthy": False}}}}
    (tmp / "fence_fail").write_text("")
    obs_not_streaming = FAKE_PG.replace("self_streaming=t", "self_streaming=f").replace("peer_pg=standby", "peer_pg=unreachable")
    (tmp / "ha-pg.sh").write_text(obs_not_streaming)
    r = run(env, ticks=8, CF_API_BASE=base)
    assert r.returncode == 0, r.stdout + r.stderr
    calls = pg_calls(tmp)
    assert calls.count("fence") >= 3, calls       # retried every tick
    pets = (tmp / "watchdog").read_bytes().rstrip(b"V").count(b"\0")
    assert pets <= 2, pets                        # only the ticks before the lease ran out
    assert "watchdog not petted" in r.stdout
