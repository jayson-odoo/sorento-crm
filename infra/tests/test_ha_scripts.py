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
esac
exit 0
""",
    # docker compose ... ps: prints FAKE_RUNNING ids; exec ... psql -Atc <sql>: answers by keyword.
    "docker": r"""#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_LOG"
args=" $* "
case "$args" in
  *" ps "*) for c in ${FAKE_RUNNING:-}; do echo "$c"; done; exit 0 ;;
  *" backup-list "*) echo "${FAKE_BACKUPS:-[]}"; exit 0 ;;
  *"pg_stat_replication WHERE"*) echo "${FAKE_REPLICAS:-1}"; exit 0 ;;
  *"pg_wal_lsn_diff"*) echo "${FAKE_LAG:-0}"; exit 0 ;;
  *"pg_stat_archiver"*) echo "${FAKE_ARCHIVER:-30 0}"; exit 0 ;;
  *"pg_ls_waldir"*) echo "${FAKE_WAL:-1000}"; exit 0 ;;
esac
exit 0
""",
    "etcdctl": r"""#!/usr/bin/env bash
for i in $(seq 1 "${FAKE_ETCD_HEALTHY:-3}"); do echo "http://m$i:2379 is healthy: took 2ms"; done
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
    ups = [c for c in calls(log) if "--profile promoted up -d worker worker_fast" in c]
    assert len(ups) == 1


def test_watcher_leaves_running_workers_alone_on_the_leader(env):
    e, log, _ = env
    run(WATCHER, e, MAX_TICKS=3, FAKE_HTTP_CODE=200, FAKE_RUNNING="a b")
    assert not any("up -d" in c or " stop " in c for c in calls(log))


def test_watcher_stops_workers_on_a_replica(env):
    e, log, _ = env
    run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=503, FAKE_RUNNING="a b")
    assert any(c.endswith("stop worker worker_fast") for c in calls(log))
    assert not any("up -d" in c for c in calls(log))


def test_watcher_treats_unreachable_patroni_as_not_leader(env):
    e, log, _ = env
    run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE="000", FAKE_RUNNING="a")
    assert any(c.endswith("stop worker worker_fast") for c in calls(log))


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
