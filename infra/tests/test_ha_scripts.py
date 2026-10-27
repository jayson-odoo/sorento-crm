"""Shell tests for infra/scripts/role-watcher.sh and infra/scripts/ha-checks.sh (HA-TIER1-N8N-BOX).

No network, no Docker, no Postgres: fake `curl`, `docker`, `etcdctl` and `df` executables sit
first on PATH and log their argv to calls.log, like scripts/ops/tests/test_backup_scripts.py.

Run: python3 -m pytest infra/tests -q
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
WATCHER = SCRIPTS / "role-watcher.sh"
CHECKS = SCRIPTS / "ha-checks.sh"

FAKES = {
    # curl: -w '%{http_code}' prints FAKE_HTTP_CODES' next word (a queue in a file), else 200.
    # A plain ping (no -w) just logs.
    "curl": r"""#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_LOG"
case " $* " in
  *" -w "*)
    q="$FAKE_DIR/codes"
    if [ -s "$q" ]; then code=$(head -1 "$q"); tail -n +2 "$q" > "$q.tmp"; mv "$q.tmp" "$q"; else code=${FAKE_HTTP_CODE:-200}; fi
    printf '%s' "$code"; [ "$code" = "000" ] && exit 7; exit 0 ;;
  *"/cluster"*)
    if [ -n "${FAKE_CLUSTER:-}" ]; then echo "$FAKE_CLUSTER"; else echo '{"members": [{"role": "leader"}, {"role": "replica"}]}'; fi
    exit 0 ;;
esac
exit 0
""",
    # docker compose ... ps: prints FAKE_RUNNING ids; exec ... psql -Atc <sql>: answers by keyword.
    "docker": r"""#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_LOG"
args=" $* "
case "$args" in
  *" ps "*) [ -n "${FAKE_PS_FAIL:-}" ] && exit 1; for c in ${FAKE_RUNNING:-}; do echo "$c"; done; exit 0 ;;
  *"etcdctl endpoint health"*) for i in $(seq 1 "${FAKE_ETCD_HEALTHY:-3}"); do echo "http://m$i:2379 is healthy: took 2ms"; done; exit 0 ;;
  *" backup-list "*) echo "${FAKE_BACKUPS:-[]}"; exit 0 ;;
  *"pg_stat_replication WHERE"*) echo "${FAKE_REPLICAS:-1}"; exit 0 ;;
  *"pg_wal_lsn_diff"*) echo "${FAKE_LAG:-0}"; exit 0 ;;
  *"pg_stat_archiver"*) echo "${FAKE_ARCHIVER:-30 0}"; exit 0 ;;
  *"pg_ls_waldir"*) echo "${FAKE_WAL:-1000}"; exit 0 ;;
esac
exit 0
""",
    "df": r"""#!/usr/bin/env bash
pct=$(cat "$FAKE_DIR/disk_pct" 2>/dev/null || echo 40)
# After a prune the fake disk drops to FAKE_DISK_AFTER_PRUNE.
if [ -n "${FAKE_DISK_AFTER_PRUNE:-}" ] && [ -f "$FAKE_DIR/pruned" ]; then pct=$FAKE_DISK_AFTER_PRUNE; fi
echo "Filesystem 1024-blocks Used Available Capacity Mounted"
echo "/dev/x 100 $pct $((100 - pct)) ${pct}% /"
""",
    "sleep": "#!/usr/bin/env bash\nexit 0\n",
}


@pytest.fixture
def env(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in FAKES.items():
        p = bindir / name
        p.write_text(body)
        p.chmod(0o755)
    log = tmp_path / "calls.log"
    log.touch()
    e = {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "FAKE_LOG": str(log),
        "FAKE_DIR": str(tmp_path),
        "HOME": str(tmp_path),
        "PROJECT_DIR": str(tmp_path),
    }
    return e, log, tmp_path


def run(script, env, **extra):
    e = {**env, **{k: str(v) for k, v in extra.items()}}
    return subprocess.run(["bash", str(script)], env=e, capture_output=True, text=True, timeout=30)


def calls(log):
    return log.read_text().splitlines()


# ---------------------------------------------------------------- role-watcher


def test_watcher_starts_workers_only_after_two_leader_readings(env):
    e, log, _ = env
    r = run(WATCHER, e, MAX_TICKS=1, FAKE_HTTP_CODE=200)
    assert r.returncode == 0
    assert not any("up -d" in c for c in calls(log)), "one reading must not act"

    r = run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=200)
    ups = [c for c in calls(log) if "--profile promoted up -d --no-deps worker worker_fast" in c]
    assert len(ups) == 1


def test_watcher_leaves_running_workers_alone_on_the_leader(env):
    e, log, _ = env
    run(WATCHER, e, MAX_TICKS=3, FAKE_HTTP_CODE=200, FAKE_RUNNING="a b")
    assert not any("up -d" in c or " stop " in c for c in calls(log))


def test_watcher_leader_retries_start_when_ps_fails(env):
    e, log, _ = env
    run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=200, FAKE_PS_FAIL=1)
    assert any("up -d --no-deps" in c for c in calls(log))


def _stops(log):
    return [c for c in calls(log) if c.endswith("--profile promoted stop worker worker_fast")]


def test_watcher_stops_workers_on_a_replica(env):
    e, log, _ = env
    run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=503, FAKE_RUNNING="a b")
    assert len(_stops(log)) == 1
    assert not any("up -d" in c for c in calls(log))


def test_watcher_stops_on_a_replica_even_when_ps_cannot_tell(env):
    """An unreadable `ps` or a worker stuck restarting must never leave one running."""
    e, log, _ = env
    run(WATCHER, e, MAX_TICKS=3, FAKE_HTTP_CODE=503, FAKE_PS_FAIL=1)
    assert len(_stops(log)) == 2  # ticks 2 and 3


def test_watcher_treats_unreachable_patroni_as_not_leader(env):
    e, log, _ = env
    run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE="000", FAKE_RUNNING="a")
    assert len(_stops(log)) == 1


def test_watcher_flapping_reading_never_acts(env):
    e, log, tmp = env
    (tmp / "codes").write_text("200\n503\n200\n503\n")
    run(WATCHER, e, MAX_TICKS=4, FAKE_RUNNING="a")
    assert not any("up -d" in c or " stop " in c for c in calls(log))


# ---------------------------------------------------------------- ha-checks

def _fresh_backup():
    from datetime import datetime, timedelta, timezone

    t = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f'[{{"time": "{t}"}}]'


def test_checks_all_ok_pings_success(env):
    e, log, _ = env
    r = run(CHECKS, e, HC_URL="https://hc.example/abc", FAKE_BACKUPS=_fresh_backup())
    assert r.returncode == 0, r.stdout + r.stderr
    pings = [c for c in calls(log) if "hc.example" in c]
    assert pings and not any("/fail" in c for c in pings)


@pytest.mark.parametrize(
    "extra, reason",
    [
        ({"FAKE_REPLICAS": 0}, "no replica streaming"),
        ({"FAKE_LAG": 99999999}, "replica lag"),
        ({"FAKE_ARCHIVER": "4000 0"}, "WAL archive stale"),
        ({"FAKE_ARCHIVER": "30 1"}, "WAL archive failing"),
        ({"FAKE_WAL": 20000000000}, "pg_wal"),
        ({"FAKE_ETCD_HEALTHY": 2}, "etcd 2/3"),
        ({"FAKE_BACKUPS": "[]"}, "base backup age"),
        ({"FAKE_CLUSTER": '{"members": [{"role": "replica"}, {"role": "replica"}]}'}, "cluster has 0 leaders"),
        ({"FAKE_CLUSTER": '{"members": [{"role": "leader"}, {"role": "leader"}]}'}, "cluster has 2 leaders"),
        ({"FAKE_CLUSTER": "not json"}, "cluster state unreadable"),
    ],
)
def test_checks_each_problem_pings_fail_with_its_reason(env, extra, reason):
    e, log, _ = env
    extra.setdefault("FAKE_BACKUPS", _fresh_backup())
    r = run(CHECKS, e, HC_URL="https://hc.example/abc", **extra)
    assert r.returncode == 1
    assert reason in r.stdout
    fails = [c for c in calls(log) if "hc.example/abc/fail" in c]
    assert fails and reason in fails[0]


def test_checks_accept_go_nanosecond_backup_timestamps(env):
    from datetime import datetime, timedelta, timezone

    t = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S") + ".123456789Z"
    e, _, _ = env
    r = run(CHECKS, e, FAKE_BACKUPS=f'[{{"time": "{t}"}}]')
    assert r.returncode == 0, r.stdout


def test_checks_skip_leader_checks_on_a_replica(env):
    e, log, _ = env
    r = run(CHECKS, e, FAKE_HTTP_CODE=503, FAKE_REPLICAS=0, FAKE_BACKUPS="[]")
    assert r.returncode == 0, r.stdout
    assert not any("psql" in c for c in calls(log))


def test_checks_alert_when_patroni_does_not_answer(env):
    e, _, _ = env
    r = run(CHECKS, e, FAKE_HTTP_CODE="000")
    assert r.returncode == 1 and "patroni not answering" in r.stdout


def test_checks_prune_keeps_newest_dumps_when_disk_is_high(env):
    e, _, tmp = env
    snap = tmp / "pre-migrate"
    snap.mkdir()
    for i in range(5):
        p = snap / f"pre-migrate-2026102{i}T000000Z-sha{i}.dump"
        p.write_text("x")
        os.utime(p, (1_000_000 + i, 1_000_000 + i))
    other = snap / "keep-me.txt"
    other.write_text("not a dump")
    (tmp / "disk_pct").write_text("90")
    r = run(CHECKS, e, ETCD_ONLY=1, SNAPSHOT_DIR=snap)
    left = sorted(p.name for p in snap.glob("pre-migrate-*.dump"))
    assert left == ["pre-migrate-20261023T000000Z-sha3.dump", "pre-migrate-20261024T000000Z-sha4.dump"]
    assert other.exists()
    assert "disk 90% used" in r.stdout  # the fake disk stays high: still alerts


def test_checks_no_prune_below_threshold(env):
    e, _, tmp = env
    snap = tmp / "pre-migrate"
    snap.mkdir()
    for i in range(4):
        (snap / f"pre-migrate-{i}.dump").write_text("x")
    (tmp / "disk_pct").write_text("82")
    r = run(CHECKS, e, ETCD_ONLY=1, SNAPSHOT_DIR=snap)
    assert len(list(snap.glob("*.dump"))) == 4
    assert r.returncode == 1 and "disk 82% used" in r.stdout


# ---------------------------------------------------------------- switchback

SWITCHBACK = SCRIPTS / "switchback.sh"

# 03:02 MYT on 27 Oct 2026 (19:02 UTC on 26 Oct).
IN_WINDOW = 1793041320
DAY = 24 * 3600


def _members(kl_role="Replica", kl_state="streaming", kl_lag=0, leader="in"):
    import json

    rows = [{"Member": "kl", "Role": kl_role, "State": kl_state, "Lag in MB": kl_lag}]
    if leader != "kl":
        rows.append({"Member": leader, "Role": "Leader", "State": "running"})
    return json.dumps(rows)


@pytest.fixture
def sb(env, tmp_path):
    e, log, _ = env
    patroni = tmp_path / "bin" / "docker"
    patroni.write_text(
        r"""#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_LOG"
case " $* " in
  *" list "*) echo "$FAKE_MEMBERS" ;;
  *" switchover "*) exit ${FAKE_SWITCH_RC:-0} ;;
esac
"""
    )
    patroni.chmod(0o755)
    state = tmp_path / "state"
    return {**e, "STATE_DIR": str(state)}, log, state / "kl-healthy-since"


def _switches(log):
    return [c for c in calls(log) if " switchover " in c]


def test_switchback_after_24h_healthy_inside_the_window(sb):
    e, log, marker = sb
    marker.parent.mkdir()
    marker.write_text(str(IN_WINDOW - DAY - 60))
    r = run(SWITCHBACK, e, NOW=IN_WINDOW, FAKE_MEMBERS=_members())
    assert r.returncode == 0, r.stdout + r.stderr
    sw = _switches(log)
    assert len(sw) == 1 and "--leader in --candidate kl --force" in sw[0]
    assert not marker.exists()


def test_switchback_waits_until_24h(sb):
    e, log, marker = sb
    marker.parent.mkdir()
    marker.write_text(str(IN_WINDOW - DAY + 600))
    run(SWITCHBACK, e, NOW=IN_WINDOW, FAKE_MEMBERS=_members())
    assert _switches(log) == []


def test_switchback_outside_the_window_does_nothing(sb):
    e, log, marker = sb
    marker.parent.mkdir()
    marker.write_text(str(IN_WINDOW - 3 * DAY))
    run(SWITCHBACK, e, NOW=IN_WINDOW + 3600, FAKE_MEMBERS=_members())  # 04:02 MYT
    assert _switches(log) == []


def test_first_healthy_reading_starts_the_clock(sb):
    e, log, marker = sb
    run(SWITCHBACK, e, NOW=IN_WINDOW, FAKE_MEMBERS=_members())
    assert marker.read_text().strip() == str(IN_WINDOW)
    assert _switches(log) == []


@pytest.mark.parametrize(
    "members",
    [
        _members(kl_lag=3),
        _members(kl_state="starting"),
        _members(kl_role="Replica", kl_state="stopped"),
    ],
)
def test_any_unhealthy_reading_resets_the_clock(sb, members):
    e, log, marker = sb
    marker.parent.mkdir()
    marker.write_text(str(IN_WINDOW - 3 * DAY))
    run(SWITCHBACK, e, NOW=IN_WINDOW, FAKE_MEMBERS=members)
    assert not marker.exists()
    assert _switches(log) == []


def test_nothing_when_kl_already_leads(sb):
    e, log, marker = sb
    marker.parent.mkdir()
    marker.write_text(str(IN_WINDOW - 3 * DAY))
    run(SWITCHBACK, e, NOW=IN_WINDOW, FAKE_MEMBERS=_members(kl_role="Leader", kl_state="running", leader="kl"))
    assert _switches(log) == []
    assert not marker.exists()


def test_failed_switchover_keeps_the_clock_and_exits_nonzero(sb):
    e, log, marker = sb
    marker.parent.mkdir()
    marker.write_text(str(IN_WINDOW - 2 * DAY))
    r = run(SWITCHBACK, e, NOW=IN_WINDOW, FAKE_MEMBERS=_members(), FAKE_SWITCH_RC=1)
    assert r.returncode == 1
    assert marker.exists()


def test_patronictl_failure_resets_and_fails(sb):
    e, log, marker = sb
    marker.parent.mkdir()
    marker.write_text(str(IN_WINDOW - 2 * DAY))
    r = run(SWITCHBACK, e, NOW=IN_WINDOW, FAKE_MEMBERS="not json")
    assert r.returncode == 1 and not marker.exists()
