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
  set-sync) [ -e "$FAKE_DIR/set_sync_fail" ] && exit 1 ;;
  promote) [ -e "$FAKE_DIR/promote_fail" ] && exit 1 ;;
  sync-record)
    case "$2" in
      get)
        [ -e "$FAKE_DIR/rec_get_fail" ] && exit 1
        if [ -e "$FAKE_DIR/rec" ]; then cat "$FAKE_DIR/rec"; else printf 'rec_mode=async\nrec_primary=crm-a\nrec_since=1\n'; fi ;;
      put) [ -e "$FAKE_DIR/rec_put_fail" ] && exit 1 ;;
    esac ;;
  observe)
    [ -e "$FAKE_DIR/observe_fail" ] && exit 1
    printf 'self_pg=primary\nself_streaming=t\nself_lsn=100\nsync_names=\npeer_pg=standby\npeer_lsn=100\npeer_flush_lsn=100\n' ;;
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
        "CONTROLLER_ARMED": "yes",  # disarmed by default (section 11c); the loop tests arm it
    }


def run(env, ticks=5, **extra):
    e = {**env, "MAX_TICKS": str(ticks), **extra}
    return subprocess.run([sys.executable, str(CONTROLLER)], env=e, capture_output=True, text=True, timeout=60)


def pg_calls(tmp):
    p = tmp / "pg.log"
    return p.read_text().split() if p.exists() else []


def pg_lines(tmp):
    p = tmp / "pg.log"
    return [l.strip() for l in p.read_text().splitlines()] if p.exists() else []


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
    # `sync-record get` is a read; a healthy steady state never PUTs the record.
    assert set(calls) <= {"observe", "prune", "7", "sync-record", "get"}, calls
    assert "put" not in calls, calls
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


# ---------------------------------------------------------------- section 3 (HA-TONIGHT)

R2_ENV = {"R2_ENDPOINT": "https://r2.example.invalid", "R2_BUCKET": "bkt"}


def r2_env(tmp, **drop):
    creds = tmp / "r2.creds"
    creds.write_text("AWS_ACCESS_KEY_ID=AKID\nAWS_SECRET_ACCESS_KEY=SECRET\n")
    creds.chmod(0o600)
    e = {**R2_ENV, "R2_CREDENTIALS_FILE": str(creds), "SYNC_MODE": "on_commit"}
    for k in drop:
        e.pop(k, None)
    return e


def primary_obs(tmp, streaming, names, peer="standby"):
    (tmp / "ha-pg.sh").write_text(
        FAKE_PG.replace("self_streaming=t", f"self_streaming={streaming}")
        .replace("sync_names=", f"sync_names={names}")
        .replace("peer_pg=standby", f"peer_pg={peer}")
    )


def test_a_failed_sync_record_skips_the_set_sync_that_follows_it(box, cf):
    tmp, env = box
    _, base = cf
    primary_obs(tmp, "f", "crm-b", peer="unreachable")  # the standby stopped streaming: P4' drop
    (tmp / "rec_put_fail").write_text("")
    r = run(env, ticks=3, CF_API_BASE=base, **r2_env(tmp))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = pg_lines(tmp)
    assert "sync-record put async" in lines, lines
    assert not any(l.startswith("set-sync") for l in lines), lines
    assert "sync record write failed; NOT dropping the sync standby" in r.stdout, r.stdout


def test_a_confirmed_sync_record_is_followed_by_the_drop(box, cf):
    tmp, env = box
    _, base = cf
    primary_obs(tmp, "f", "crm-b", peer="unreachable")
    r = run(env, ticks=1, CF_API_BASE=base, **r2_env(tmp))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = pg_lines(tmp)
    assert "sync-record put async" in lines and "set-sync" in lines, lines
    assert lines.index("sync-record put async") < lines.index("set-sync")
    assert "NOT dropping" not in r.stdout


def test_an_add_sets_the_standby_and_writes_the_record_only_on_a_later_caught_up_tick(box, cf):
    tmp, env = box
    _, base = cf
    primary_obs(tmp, "t", "")
    (tmp / "rec").write_text("rec_mode=async\nrec_primary=crm-a\nrec_since=1\n")
    r = run(env, ticks=1, CF_API_BASE=base, **r2_env(tmp))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = pg_lines(tmp)
    assert "set-sync crm-b" in lines and "sync-record put sync" not in lines, lines
    # later: the primary already carries the standby and the standby has flushed past the mark
    primary_obs(tmp, "t", "crm-b")
    (tmp / "pg.log").unlink()
    r = run(env, ticks=2, CF_API_BASE=base, **r2_env(tmp))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "sync-record put sync" in pg_lines(tmp), pg_lines(tmp)


def test_a_failed_set_sync_skips_every_later_action_of_the_tick(box, cf):
    tmp, env = box
    _, base = cf
    # an add (set_sync) and a lost peer slot (ensure_slot) in the same tick; set_sync fails
    (tmp / "ha-pg.sh").write_text(FAKE_PG.replace("peer_flush_lsn=100", "peer_flush_lsn=100\\npeer_slot=f"))
    (tmp / "set_sync_fail").write_text("")
    r = run(env, ticks=1, CF_API_BASE=base, **r2_env(tmp))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = pg_lines(tmp)
    assert "set-sync crm-b" in lines, lines
    assert "ensure-slot" not in lines and "sync-record put sync" not in lines, lines
    assert "set_sync failed" in r.stdout, r.stdout


def test_a_failed_promote_skips_the_async_record_that_follows_it(box, cf):
    tmp, env = box
    state, base = cf
    state["body"] = {"success": True, "result": {"pop_health": {"SG": {"healthy": False}}}}
    standby_box(tmp, "rec_mode=sync\nrec_primary=crm-b\nrec_since=5\n")
    (tmp / "promote_fail").write_text("")
    r = run(env, ticks=10, CF_API_BASE=base, **FAST_PROMOTE, **r2_env(tmp))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = pg_lines(tmp)
    assert "promote" in lines, (lines, r.stdout)
    assert "sync-record put async" not in lines[lines.index("promote"):], lines
    assert "promote failed" in r.stdout


def test_a_failed_sync_put_keeps_its_own_alert_text(box, cf):
    tmp, env = box
    _, base = cf
    primary_obs(tmp, "t", "crm-b")
    (tmp / "rec").write_text("rec_mode=async\nrec_primary=crm-a\nrec_since=1\n")
    (tmp / "rec_put_fail").write_text("")
    r = run(env, ticks=2, CF_API_BASE=base, **r2_env(tmp))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "sync record write failed (sync)" in r.stdout, r.stdout
    assert "NOT dropping" not in r.stdout


def test_r2_credentials_readable_by_others_warn_and_a_missing_file_refuses(box, cf):
    tmp, env = box
    _, base = cf
    primary_obs(tmp, "t", "crm-b")
    e = r2_env(tmp)
    Path(e["R2_CREDENTIALS_FILE"]).chmod(0o644)
    r = run(env, ticks=1, CF_API_BASE=base, **e)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "warning" in r.stdout and "r2.creds" in r.stdout and "mode 600" in r.stdout
    Path(e["R2_CREDENTIALS_FILE"]).unlink()
    (tmp / "pg.log").unlink()
    r = run(env, ticks=1, CF_API_BASE=base, **e)
    assert r.returncode == 2, r.stdout + r.stderr
    assert pg_calls(tmp) == []


def test_an_unreadable_record_is_unknown_and_changes_nothing_in_steady_state(box, cf):
    tmp, env = box
    _, base = cf
    primary_obs(tmp, "t", "crm-b")
    (tmp / "rec_get_fail").write_text("")
    r = run(env, ticks=3, CF_API_BASE=base, **r2_env(tmp))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "tick failed" not in r.stdout, r.stdout
    assert not any(l.startswith(("set-sync", "sync-record put")) for l in pg_lines(tmp)), pg_lines(tmp)


# A standby that sees the peer as primary on the first tick, then never again.
STANDBY_FAKE = FAKE_PG.split("  observe)")[0] + r"""  observe)
    n=$(cat "$FAKE_DIR/n" 2>/dev/null || echo 0); echo $((n+1)) > "$FAKE_DIR/n"
    printf 'self_pg=standby\nself_streaming=f\nself_lsn=100\nsync_names=\npeer_slot=t\n'
    if [ "$n" -lt 1 ]; then printf 'peer_pg=primary\npeer_lsn=100\n'; else printf 'peer_pg=unreachable\npeer_lsn=\n'; fi ;;
esac
exit 0
"""
FAST_PROMOTE = {"FENCE_MARGIN": "1", "PROMOTE_AFTER": "3", "FENCE_HOLD": "10"}


def standby_box(tmp, rec):
    (tmp / "ha-pg.sh").write_text(STANDBY_FAKE)
    (tmp / "rec").write_text(rec)


def test_a_standby_promotes_through_the_loop_only_on_a_sync_record_from_the_peer(box, cf):
    tmp, env = box
    state, base = cf
    state["body"] = {"success": True, "result": {"pop_health": {"SG": {"healthy": False}}}}
    standby_box(tmp, "rec_mode=sync\nrec_primary=crm-b\nrec_since=5\n")
    r = run(env, ticks=10, CF_API_BASE=base, **FAST_PROMOTE, **r2_env(tmp))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = pg_lines(tmp)
    assert "promote" in lines, (lines, r.stdout)
    assert "sync-record put async" in lines[lines.index("promote"):], lines


def test_a_standby_does_not_promote_through_the_loop_on_an_async_record(box, cf):
    tmp, env = box
    state, base = cf
    state["body"] = {"success": True, "result": {"pop_health": {"SG": {"healthy": False}}}}
    standby_box(tmp, "rec_mode=async\nrec_primary=crm-b\nrec_since=4242\n")
    r = run(env, ticks=10, CF_API_BASE=base, **FAST_PROMOTE, **r2_env(tmp))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "promote" not in pg_lines(tmp)
    assert "1970-01-01T01:10:42Z" in r.stdout, r.stdout  # 4242 as UTC ISO time


def test_a_standby_does_not_promote_through_the_loop_when_the_record_cannot_be_read(box, cf):
    tmp, env = box
    state, base = cf
    state["body"] = {"success": True, "result": {"pop_health": {"SG": {"healthy": False}}}}
    standby_box(tmp, "rec_mode=sync\nrec_primary=crm-b\nrec_since=5\n")
    (tmp / "rec_get_fail").write_text("")
    r = run(env, ticks=10, CF_API_BASE=base, **FAST_PROMOTE, **r2_env(tmp))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "promote" not in pg_lines(tmp)


@pytest.mark.parametrize("armed", [None, "", "no", "true", "YES", "1"])
def test_not_armed_exits_3_without_opening_the_watchdog_or_calling_anything(box, cf, armed):
    tmp, env = box
    _, base = cf
    env = dict(env)
    env.pop("CONTROLLER_ARMED")
    extra = {} if armed is None else {"CONTROLLER_ARMED": armed}
    r = run(env, ticks=3, CF_API_BASE=base, **extra)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "not armed" in r.stdout and "CONTROLLER_ARMED=yes" in r.stdout, r.stdout
    assert pg_calls(tmp) == [], "a disarmed controller must not touch Postgres"
    assert (tmp / "watchdog").read_bytes() == b"", "a disarmed controller must not open the watchdog"
    assert not (tmp / "state.json").exists()


@pytest.mark.parametrize("missing", ["R2_ENDPOINT", "R2_BUCKET", "R2_CREDENTIALS_FILE"])
def test_sync_mode_without_r2_settings_refuses_to_start(box, cf, missing):
    tmp, env = box
    _, base = cf
    r = run(env, ticks=2, CF_API_BASE=base, **r2_env(tmp, **{missing: None}))
    assert r.returncode == 2, r.stdout + r.stderr
    assert pg_calls(tmp) == []
    assert (tmp / "watchdog").read_bytes() == b""


def test_sync_mode_with_all_r2_settings_starts(box, cf):
    tmp, env = box
    _, base = cf
    primary_obs(tmp, "t", "crm-b")
    r = run(env, ticks=2, CF_API_BASE=base, **r2_env(tmp))
    assert r.returncode == 0, r.stdout + r.stderr
