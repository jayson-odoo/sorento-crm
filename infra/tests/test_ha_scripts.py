"""Shell tests for infra/scripts/role-watcher.sh and infra/scripts/ha-checks.sh (HA-CF-FAILOVER).

No network, no Docker, no Postgres: fake `curl`, `docker`, role/observe/clock and `df` executables sit
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

TAG = "0123456789abcdef0123456789abcdef01234567"

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
echo "docker $* IMAGE_TAG=${IMAGE_TAG-UNSET}" >> "$FAKE_DIR/env.log"
args=" $* "
case "$args" in
  *" ps "*) [ -n "${FAKE_PS_FAIL:-}" ] && exit 1; for c in ${FAKE_RUNNING:-}; do echo "$c"; done; exit 0 ;;
  *" backup-list "*) echo "${FAKE_BACKUPS:-[]}"; exit 0 ;;
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
    # The role watcher's ROLE_CMD: answers from the same queue as the fake curl (200 = primary,
    # 000 = down, anything else = standby), so one queue drives every role reading.
    "fake-role": r"""#!/usr/bin/env bash
echo "role $*" >> "$FAKE_LOG"
q="$FAKE_DIR/codes"
if [ -s "$q" ]; then code=$(head -1 "$q"); tail -n +2 "$q" > "$q.tmp"; mv "$q.tmp" "$q"; else code=${FAKE_HTTP_CODE:-200}; fi
case "$code" in 200) echo primary ;; 000) exit 1 ;; *) echo standby ;; esac
""",
    # ha-checks' OBSERVE_CMD (ha-pg.sh observe) and CLOCK_CMD.
    "fake-observe": r"""#!/usr/bin/env bash
echo "observe $*" >> "$FAKE_LOG"
echo "self_pg=${FAKE_SELF_PG-primary}"
echo "self_streaming=${FAKE_STREAMING:-t}"
echo "self_lsn=100"
echo "sync_names="
echo "peer_pg=${FAKE_PEER_PG:-standby}"
echo "peer_lsn=100"
""",
    "fake-clock": "#!/usr/bin/env bash\necho \"${FAKE_NTP:-yes}\"\n",
    "fake-peer-hash": r"""#!/usr/bin/env bash
[ -n "${FAKE_PEER_HASH_FAIL:-}" ] && exit 1
cd "$PROJECT_DIR" && sha256sum ${SHARED_FILES}
[ -n "${FAKE_PEER_EXTRA_LINE:-}" ] && echo "$FAKE_PEER_EXTRA_LINE"
exit 0
""",
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
    (tmp_path / ".ha-image-tag").write_text(TAG + "\n")
    e = {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "FAKE_LOG": str(log),
        "FAKE_DIR": str(tmp_path),
        "HOME": str(tmp_path),
        "PROJECT_DIR": str(tmp_path),
        "ROLE_CMD": str(bindir / "fake-role"),
        "OBSERVE_CMD": str(bindir / "fake-observe"),
        "CLOCK_CMD": str(bindir / "fake-clock"),
        "ROLE_WATCHER_ARMED": "yes",  # disarmed by default (section 11c); the watcher tests arm it
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
    ups = [c for c in calls(log) if "--profile promoted up -d" in c and "--no-deps" in c and c.endswith("worker worker_fast")]
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


def test_watcher_treats_an_unreadable_role_as_not_leader(env):
    e, log, _ = env
    run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE="000", FAKE_RUNNING="a")
    assert len(_stops(log)) == 1


def test_watcher_flapping_reading_never_acts(env):
    e, log, tmp = env
    (tmp / "codes").write_text("200\n503\n200\n503\n")
    run(WATCHER, e, MAX_TICKS=4, FAKE_RUNNING="a")
    assert not any("up -d" in c or " stop " in c for c in calls(log))


@pytest.mark.parametrize("armed", [None, "", "no", "true", "YES", "1"])
def test_watcher_not_armed_exits_3_and_calls_nothing(env, armed):
    e, log, tmp = env
    e = dict(e)
    e.pop("ROLE_WATCHER_ARMED")
    extra = {} if armed is None else {"ROLE_WATCHER_ARMED": armed}
    r = run(WATCHER, e, MAX_TICKS=3, FAKE_HTTP_CODE=200, FAKE_RUNNING="a b", **extra)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "not armed" in (r.stdout + r.stderr) and "ROLE_WATCHER_ARMED=yes" in (r.stdout + r.stderr)
    assert not any(c.startswith("docker") for c in calls(log)), calls(log)
    assert not any(c.startswith("role") for c in calls(log)), "a disarmed watcher must not even read the role"


def test_watcher_armed_still_runs(env):
    e, log, _ = env
    r = run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=503, FAKE_RUNNING="a")
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(_stops(log)) == 1


# ---------------------------------------------------------------- role-watcher, H4b deploy path


def _ups(log):
    return [c for c in calls(log) if " up -d" in c]


def test_watcher_leader_start_never_recreates_a_running_worker(env):
    e, log, tmp = env
    run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=200)
    ups = _ups(log)
    assert len(ups) == 1, calls(log)
    assert "--no-recreate" in ups[0], ups[0]


def test_watcher_leader_starts_workers_on_the_recorded_image_tag(env):
    e, log, tmp = env
    run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=200)
    lines = [c for c in (tmp / "env.log").read_text().splitlines() if " up -d" in c]
    assert len(lines) == 1, lines
    assert lines[0].endswith("IMAGE_TAG=" + TAG), lines[0]


def test_watcher_leader_without_a_recorded_tag_starts_nothing_but_replica_still_stops(env):
    e, log, tmp = env
    (tmp / ".ha-image-tag").unlink()
    r = run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=200)
    assert not _ups(log), calls(log)
    assert "no image tag" in (r.stdout + r.stderr).lower(), r.stdout + r.stderr
    run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=503, FAKE_RUNNING="a b")
    assert len(_stops(log)) == 1


def _lock(tmp, mode=0o600):
    lock = tmp / "deploy.lock"
    lock.touch()
    lock.chmod(mode)
    return lock


def test_watcher_exclusive_deploy_lock_skips_a_leader_tick_but_a_replica_still_stops(env):
    import fcntl

    e, log, tmp = env
    lock = _lock(tmp)
    with open(lock, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        r = run(WATCHER, e, MAX_TICKS=3, FAKE_HTTP_CODE=200, FAKE_RUNNING="a", DEPLOY_LOCK_PATH=lock)
        assert not _ups(log) and not _stops(log), calls(log)
        assert "skip" in (r.stdout + r.stderr).lower(), r.stdout + r.stderr
        run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=503, FAKE_RUNNING="a", DEPLOY_LOCK_PATH=lock)
    assert len(_stops(log)) == 1, calls(log)


def test_watcher_shared_lock_holder_does_not_block_the_leader(env):
    import fcntl

    e, log, tmp = env
    lock = _lock(tmp)
    with open(lock, "r") as fh:
        fcntl.flock(fh, fcntl.LOCK_SH)  # the weekly restore test holds it shared
        run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=200, DEPLOY_LOCK_PATH=lock)
    assert len(_ups(log)) == 1, calls(log)


def _unsafe_lock(tmp, kind):
    if kind == "symlink":
        real = tmp / "real.lock"
        real.touch(); real.chmod(0o600)
        link = tmp / "link.lock"
        link.symlink_to(real)
        return link
    if kind == "fifo":
        fifo = tmp / "fifo.lock"
        os.mkfifo(fifo, 0o600)
        return fifo
    if kind == "dir_group_writable":
        d = tmp / "lockdir"
        d.mkdir(); d.chmod(0o775)
        lock = d / "deploy.lock"
        lock.touch(); lock.chmod(0o600)
        return lock
    lock = tmp / "other.lock"
    lock.touch(); lock.chmod(0o646)
    return lock


def _run_bounded(e, tmp, kind, **extra):
    """run() with a hard cap, so a watcher that blocks opening a FIFO fails the test, not hangs it."""
    full = {**e, **{k: str(v) for k, v in extra.items()}}
    try:
        return subprocess.run(["bash", str(WATCHER)], env=full, capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        pytest.fail(f"watcher hung on a {kind} lock path")
    finally:
        if kind == "fifo":  # release any opener still blocked on the pipe
            try:
                os.close(os.open(tmp / "fifo.lock", os.O_RDWR | os.O_NONBLOCK))
            except OSError:
                pass


UNSAFE = ["symlink", "fifo", "dir_group_writable", "file_other_writable"]


@pytest.mark.parametrize("kind", UNSAFE)
def test_watcher_unsafe_lock_path_blocks_a_leader_start_and_is_logged(env, kind):
    e, log, tmp = env
    lock = _unsafe_lock(tmp, kind)
    r = _run_bounded(e, tmp, kind, MAX_TICKS=2, FAKE_HTTP_CODE=200, DEPLOY_LOCK_PATH=lock)
    assert not _ups(log), calls(log)
    out = (r.stdout + r.stderr).lower()
    assert "unsafe" in out and "lock" in out, out


@pytest.mark.parametrize("kind", UNSAFE)
def test_watcher_unsafe_lock_path_still_lets_a_replica_stop(env, kind):
    e, log, tmp = env
    lock = _unsafe_lock(tmp, kind)
    _run_bounded(e, tmp, kind, MAX_TICKS=2, FAKE_HTTP_CODE=503, FAKE_RUNNING="a", DEPLOY_LOCK_PATH=lock)
    assert len(_stops(log)) == 1, calls(log)


def test_watcher_accepts_a_lock_file_others_can_read(env):
    e, log, tmp = env
    lock = _lock(tmp, 0o644)
    r = run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=200, DEPLOY_LOCK_PATH=lock)
    assert len(_ups(log)) == 1, calls(log)
    assert "unsafe" not in (r.stdout + r.stderr).lower()


def _unsafe_project(tmp, kind):
    proj = tmp / "proj"
    proj.mkdir()
    (proj / ".ha-image-tag").write_text(TAG + "\n")
    (proj / ".ha-image-tag").chmod(0o644)
    if kind == "symlink":
        link = tmp / "projlink"
        link.symlink_to(proj)
        return link
    proj.chmod(0o775)
    return proj


@pytest.mark.parametrize("kind", ["symlink", "group_writable"])
def test_watcher_unsafe_project_dir_blocks_a_leader_start_and_is_logged(env, kind):
    e, log, tmp = env
    proj = _unsafe_project(tmp, kind)
    r = run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=200, PROJECT_DIR=proj)
    assert not _ups(log), calls(log)
    out = r.stdout + r.stderr
    assert str(proj) in out and "unsafe" in out.lower(), out


@pytest.mark.parametrize("kind", ["symlink", "group_writable"])
def test_watcher_unsafe_project_dir_still_lets_a_replica_stop(env, kind):
    e, log, tmp = env
    proj = _unsafe_project(tmp, kind)
    run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=503, FAKE_RUNNING="a", PROJECT_DIR=proj)
    assert len(_stops(log)) == 1, calls(log)


def _bad_tag(tmp, kind):
    f = tmp / ".ha-image-tag"
    f.unlink()
    if kind == "symlink":
        secret = tmp / "secret.txt"
        secret.write_text("API_SECRET=hunter2-do-not-log\n")
        f.symlink_to(secret)
    elif kind == "writable":
        f.write_text(TAG + "\n"); f.chmod(0o664)
    else:
        f.write_text(kind + "\n")


@pytest.mark.parametrize("kind", ["symlink", "writable", "abc123", "A" * 40, "g" * 40, "0" * 41, TAG + " x"])
def test_watcher_refuses_an_invalid_image_tag_file(env, kind):
    e, log, tmp = env
    _bad_tag(tmp, kind)
    r = run(WATCHER, e, MAX_TICKS=2, FAKE_HTTP_CODE=200)
    assert not _ups(log), calls(log)
    out = (r.stdout + r.stderr).lower()
    assert "invalid" in out, out
    assert "hunter2" not in out, "the log must never echo what the tag file points at"


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


def test_checks_one_node_phase_expects_no_replica(env):
    # Node A runs alone for weeks before node B exists.
    e, log, _ = env
    r = run(
        CHECKS, e, HC_URL="https://hc.example/abc", EXPECT_REPLICAS=0,
        FAKE_STREAMING="f", FAKE_PEER_PG="unreachable", FAKE_BACKUPS=_fresh_backup(),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    pings = [c for c in calls(log) if "hc.example" in c]
    assert pings and not any("/fail" in c for c in pings)


@pytest.mark.parametrize(
    "extra, reason",
    [
        ({"FAKE_STREAMING": "f"}, "no replica streaming"),
        ({"FAKE_LAG": 99999999}, "replica lag"),
        ({"FAKE_ARCHIVER": "4000 0"}, "WAL archive stale"),
        ({"FAKE_ARCHIVER": "30 1"}, "WAL archive failing"),
        ({"FAKE_WAL": 20000000000}, "pg_wal"),
        ({"FAKE_BACKUPS": "[]"}, "base backup age"),
        ({"FAKE_PEER_PG": "primary"}, "TWO PRIMARIES"),
        ({"FAKE_SELF_PG": "standby", "FAKE_PEER_PG": "standby"}, "no primary"),
        ({"FAKE_SELF_PG": "standby", "FAKE_PEER_PG": "unreachable"}, "peer unreachable"),
        ({"FAKE_SELF_PG": "down"}, "local postgres down"),
        ({"FAKE_SELF_PG": ""}, "role unreadable"),
        ({"FAKE_NTP": "no"}, "clock not NTP-synced"),
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


def test_checks_skip_primary_checks_on_a_standby(env):
    e, log, _ = env
    r = run(CHECKS, e, FAKE_SELF_PG="standby", FAKE_PEER_PG="primary", FAKE_STREAMING="f", FAKE_BACKUPS="[]")
    assert r.returncode == 0, r.stdout
    assert not any("psql" in c for c in calls(log))


def _shared(tmp, **contents):
    names = []
    for name, body in contents.items():
        (tmp / name).write_text(body)
        names.append(name)
    return " ".join(names)


def test_checks_identical_config_on_both_nodes_is_ok(env):
    e, _, tmp = env
    files = _shared(tmp, **{"a.env": "X=1\n", "b.yml": "y\n"})
    peer = str(Path(e["PATH"].split(":")[0]) / "fake-peer-hash")
    r = run(CHECKS, e, FAKE_BACKUPS=_fresh_backup(), SHARED_FILES=files, PEER_HASH_CMD=peer)
    assert r.returncode == 0, r.stdout


def test_checks_name_a_differing_config_file_never_its_content(env):
    e, _, tmp = env
    files = _shared(tmp, **{"a.env": "SECRET=hunter2\n", "b.yml": "y\n"})
    peer_dir = tmp / "peer"
    peer_dir.mkdir()
    (peer_dir / "a.env").write_text("SECRET=other\n")
    (peer_dir / "b.yml").write_text("y\n")
    peer = str(Path(e["PATH"].split(":")[0]) / "fake-peer-hash")
    r = run(CHECKS, e, FAKE_BACKUPS=_fresh_backup(), SHARED_FILES=files,
            PEER_HASH_CMD=f"env PROJECT_DIR={peer_dir} {peer}")
    assert r.returncode == 1
    assert "config differs between nodes: a.env" in r.stdout
    assert "b.yml" not in r.stdout.split("config differs")[1].splitlines()[0]
    assert "hunter2" not in r.stdout and "other" not in r.stdout


def test_checks_peer_hashes_unreadable_alerts(env):
    e, _, tmp = env
    files = _shared(tmp, **{"a.env": "X=1\n"})
    peer = str(Path(e["PATH"].split(":")[0]) / "fake-peer-hash")
    r = run(CHECKS, e, FAKE_BACKUPS=_fresh_backup(), SHARED_FILES=files, PEER_HASH_CMD=peer, FAKE_PEER_HASH_FAIL=1)
    assert r.returncode == 1 and "peer config hashes unreadable" in r.stdout


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
    r = run(CHECKS, e, SNAPSHOT_DIR=snap, FAKE_BACKUPS=_fresh_backup())
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
    r = run(CHECKS, e, SNAPSHOT_DIR=snap, FAKE_BACKUPS=_fresh_backup())
    assert len(list(snap.glob("*.dump"))) == 4
    assert r.returncode == 1 and "disk 82% used" in r.stdout


# ---------------------------------------------------------------- ha-pg.sh observe (review round 2)

ADAPTER = SCRIPTS / "ha-pg.sh"


@pytest.mark.parametrize("pg_exec, running, ready, state, want", [
    ("false", "true", "", "", "self_pg=unknown"),                                    # exec broken, container up
    ("{fake}", "true", "rejecting connections", "in crash recovery", "self_pg=down"),
    ("{fake}", "true", "rejecting connections", "in archive recovery", "self_pg=down"),
    ("{fake}", "true", "rejecting connections", "starting up", "self_pg=down"),
    ("{fake}", "true", "rejecting connections", "in production", "self_pg=unknown"),  # smart shutdown
    ("{fake}", "true", "no response", "in production", "self_pg=unknown"),            # overloaded, writable
    ("{fake}", "true", "no response", "in crash recovery", "self_pg=unknown"),
    ("{fake}", "true", "accepting connections", "in production", "self_pg=unknown"),
    ("false", "false", "", "", "self_pg=down"),                                       # container stopped
])
def test_observe_never_calls_a_running_but_unanswering_postgres_down(tmp_path, pg_exec, running, ready, state, want):
    # `exec psql` fails while the container runs: Postgres may still take writes, so the
    # controller must see "unknown" (a failed tick), never "down" (D1), unless the postmaster
    # refuses every connection because it is recovering or starting (nothing can write then).
    fake = tmp_path / "fake-exec"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'case "$1" in pg_isready) echo "/var/run/postgresql:5432 - {ready}"; exit 1 ;;\n'
        f'  pg_controldata) echo "Database cluster state:               {state}"; exit 0 ;;\n'
        '  *) exit 2 ;; esac\n'
    )
    fake.chmod(0o755)
    e = {
        "PATH": os.environ["PATH"], "NODE_NAME": "crm-a", "PEER_NAME": "crm-b", "PEER_HOST": "peer",
        "PGDATA": "/v/pgdata", "PG_EXEC": pg_exec.format(fake=fake), "PG_RUNNING": running,
        "PG_START": "true", "PG_STOP": "true", "PG_OFFLINE_SH": "false", "PEER_PSQL": "false",
    }
    r = subprocess.run(["bash", str(ADAPTER), "observe"], env=e, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert want in r.stdout.splitlines(), r.stdout


# ---------------------------------------------------------------- ha-pg.sh names (G11, section 11a)

TEMPLATES = SCRIPTS.parent / "templates"

FAKE_EXEC = r"""#!/usr/bin/env bash
# Stands in for `docker exec db`: logs the SQL (last argument of psql -c) and answers by keyword.
sql="${@: -1}"
printf '%s\n---\n' "$sql" >> "$FAKE_DIR/sql.log"
if [ "$sql" = "SELECT CASE WHEN pg_is_in_recovery() THEN 'standby' ELSE 'primary' END" ]; then
  echo "${FAKE_ROLE:-primary}"
elif [[ "$sql" == *pg_promote* ]]; then
  echo t
elif [[ "$sql" == *pg_stat_replication* ]]; then
  echo "primary|100|t||t"
else
  echo ok
fi
"""

FAKE_OFFLINE = r"""#!/usr/bin/env bash
printf '%s\n---\n' "$1" >> "$FAKE_DIR/offline.log"
exit 0
"""

FAKE_PEER_PSQL = r"""#!/usr/bin/env bash
printf '%s\n---\n' "$*" >> "$FAKE_DIR/peer.log"
echo "primary|100"
"""


def adapter_env(tmp, **extra):
    bindir = tmp / "abin"
    bindir.mkdir(exist_ok=True)
    for name, body in (("fake-exec", FAKE_EXEC), ("fake-offline", FAKE_OFFLINE), ("fake-peer-psql", FAKE_PEER_PSQL)):
        f = bindir / name
        f.write_text(body)
        f.chmod(0o755)
    e = {
        "PATH": os.environ["PATH"], "HOME": str(tmp), "FAKE_DIR": str(tmp),
        "NODE_NAME": "crm-a", "PEER_NAME": "crm-b", "PEER_HOST": "peer", "PGDATA": "/v/pgdata",
        "PG_EXEC": str(bindir / "fake-exec"), "PG_RUNNING": "false", "PG_START": "true", "PG_STOP": "true",
        "PG_OFFLINE_SH": str(bindir / "fake-offline"), "PEER_PSQL": str(bindir / "fake-peer-psql"),
    }
    e.update({k: str(v) for k, v in extra.items()})
    return e


def adapter(e, *args, timeout=30):
    return subprocess.run(["bash", str(ADAPTER), *args], env=e, capture_output=True, text=True, timeout=timeout)


def sql_log(tmp):
    p = tmp / "sql.log"
    return p.read_text() if p.exists() else ""


ADOPTED = dict(SELF_APP_NAME="sorento_crm_replica", SELF_SLOT="sorento_crm_replica_slot",
               PEER_APP_NAME="sorento_crm_peer_app", PEER_SLOT="sorento_crm_peer_slot")


def test_observe_sql_uses_the_adopted_peer_names(tmp_path):
    r = adapter(adapter_env(tmp_path, PG_RUNNING="true", **ADOPTED), "observe")
    assert r.returncode == 0, r.stderr
    sql = sql_log(tmp_path)
    assert "application_name = 'sorento_crm_peer_app'" in sql
    assert "slot_name = 'sorento_crm_peer_slot'" in sql
    assert "'crm-b'" not in sql and "'crm_b'" not in sql


def test_observe_sql_defaults_to_the_node_names(tmp_path):
    r = adapter(adapter_env(tmp_path, PG_RUNNING="true"), "observe")
    assert r.returncode == 0, r.stderr
    sql = sql_log(tmp_path)
    assert "application_name = 'crm-b'" in sql
    assert "slot_name = 'crm_b'" in sql


def test_ensure_slot_creates_the_adopted_peer_slot(tmp_path):
    r = adapter(adapter_env(tmp_path, **ADOPTED), "ensure-slot")
    assert r.returncode == 0, r.stderr
    sql = sql_log(tmp_path)
    assert "pg_create_physical_replication_slot('sorento_crm_peer_slot'" in sql
    assert "slot_name = 'sorento_crm_peer_slot'" in sql
    assert "crm_b" not in sql


def test_ensure_slot_defaults_to_the_peer_name_with_underscores(tmp_path):
    adapter(adapter_env(tmp_path), "ensure-slot")
    assert "pg_create_physical_replication_slot('crm_b'" in sql_log(tmp_path)


def test_promote_creates_the_adopted_peer_slot_and_drops_both_stale_ones(tmp_path):
    r = adapter(adapter_env(tmp_path, FAKE_ROLE="standby", **ADOPTED), "promote")
    assert r.returncode == 0, r.stderr
    sql = sql_log(tmp_path)
    assert "IN ('sorento_crm_peer_slot', 'sorento_crm_replica_slot')" in sql
    assert "pg_create_physical_replication_slot('sorento_crm_peer_slot'" in sql
    assert "'crm_b'" not in sql and "'crm_a'" not in sql


def test_promote_defaults_to_the_node_names_with_underscores(tmp_path):
    r = adapter(adapter_env(tmp_path, FAKE_ROLE="standby"), "promote")
    assert r.returncode == 0, r.stderr
    sql = sql_log(tmp_path)
    assert "IN ('crm_b', 'crm_a')" in sql
    assert "pg_create_physical_replication_slot('crm_b'" in sql


def _standby_conf(tmp):
    scripts = (tmp / "offline.log").read_text().split("\n---\n")
    conf = [x for x in scripts if "postgresql.auto.conf" in x]
    assert conf, scripts
    return conf[0]


def test_rejoin_writes_the_adopted_self_names_into_the_standby_conf(tmp_path):
    r = adapter(adapter_env(tmp_path, **ADOPTED), "rejoin")
    assert r.returncode == 0, r.stderr
    conf = _standby_conf(tmp_path)
    assert "application_name=sorento_crm_replica " in conf
    assert "primary_slot_name = 'sorento_crm_replica_slot'" in conf
    assert "application_name=crm-a" not in conf and "'crm_a'" not in conf


def test_rejoin_defaults_to_the_node_names(tmp_path):
    r = adapter(adapter_env(tmp_path), "rejoin")
    assert r.returncode == 0, r.stderr
    conf = _standby_conf(tmp_path)
    assert "application_name=crm-a " in conf
    assert "primary_slot_name = 'crm_a'" in conf


@pytest.mark.parametrize("key, bad", [
    ("SELF_APP_NAME", "UPPER"), ("SELF_APP_NAME", "has space"), ("SELF_APP_NAME", "x" * 33), ("SELF_APP_NAME", "a'b"),
    ("PEER_APP_NAME", "UPPER"), ("PEER_APP_NAME", "semi;colon"), ("PEER_APP_NAME", "x" * 33), ("PEER_APP_NAME", "a.b"),
    ("SELF_SLOT", "with-dash"), ("SELF_SLOT", "UPPER"), ("SELF_SLOT", "x" * 64), ("SELF_SLOT", "a'b"),
    ("PEER_SLOT", "with-dash"), ("PEER_SLOT", "has space"), ("PEER_SLOT", "x" * 64), ("PEER_SLOT", "a;b"),
])
def test_invalid_names_exit_2(tmp_path, key, bad):
    r = adapter(adapter_env(tmp_path, **{key: bad}), "role")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert not (tmp_path / "sql.log").exists(), "a bad name must be refused before anything runs"


@pytest.mark.parametrize("key, good", [
    ("SELF_APP_NAME", "x" * 32), ("PEER_APP_NAME", "a-b_c9"), ("SELF_SLOT", "x" * 63), ("PEER_SLOT", "a_b9"),
])
def test_valid_boundary_names_are_accepted(tmp_path, key, good):
    r = adapter(adapter_env(tmp_path, **{key: good}), "role")
    assert r.returncode == 0, (r.stdout, r.stderr)


# ---------------------------------------------------------------- ha-pg.sh sync-record (section 11b)

import json  # noqa: E402
import shutil  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

REAL_CURL = shutil.which("curl")


def _curl_has_sigv4():
    if not REAL_CURL:
        return False
    out = subprocess.run([REAL_CURL, "--help", "all"], capture_output=True, text=True).stdout
    return "aws-sigv4" in out


needs_sigv4 = pytest.mark.skipif(not _curl_has_sigv4(), reason="the installed curl has no --aws-sigv4 (needs curl 7.75+)")

SECRET = "wJalrXUtnFEMI-K7MDENG-bPxRfiCYEXAMPLEKEY"
KEY_ID = "AKIDEXAMPLE0123456789"
GOOD_BODY = {"mode": "sync", "primary": "crm-b", "since": 1700000000}


@pytest.fixture
def s3():
    """A fake S3 on 127.0.0.1: one object, every request recorded."""
    st = {"body": json.dumps(GOOD_BODY).encode(), "get_status": 200, "put_status": 200, "delay": 0, "reqs": []}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _rec(self, body=b""):
            st["reqs"].append({"method": self.command, "path": self.path, "body": body,
                               "auth": self.headers.get("Authorization", "")})
            if st["delay"]:
                time.sleep(st["delay"])

        def do_GET(self):
            self._rec()
            self.send_response(st["get_status"])
            self.send_header("Content-Length", str(len(st["body"])))
            self.end_headers()
            try:
                self.wfile.write(st["body"])
            except OSError:
                pass

        def do_PUT(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self._rec(raw)
            if st["put_status"] == 200:
                st["body"] = raw
            self.send_response(st["put_status"])
            self.send_header("Content-Length", "0")
            self.end_headers()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    st["url"] = f"http://127.0.0.1:{srv.server_address[1]}"
    yield st
    srv.shutdown()


def r2_adapter_env(tmp, s3, **extra):
    """Adapter env with R2 settings and a logging curl wrapper that then runs the real one."""
    bindir = tmp / "cbin"
    bindir.mkdir(exist_ok=True)
    wrapper = bindir / "curl"
    wrapper.write_text(f'#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "{tmp}/curl.argv"\nexec {REAL_CURL} "$@"\n')
    wrapper.chmod(0o755)
    creds = tmp / "r2.creds"
    creds.write_text(f"AWS_ACCESS_KEY_ID={KEY_ID}\nAWS_SECRET_ACCESS_KEY={SECRET}\n")
    creds.chmod(0o600)
    e = adapter_env(tmp, R2_ENDPOINT=s3["url"], R2_BUCKET="bkt", R2_CREDENTIALS_FILE=creds, **extra)
    e["PATH"] = f"{bindir}:{e['PATH']}"
    return e


def baseline_ok(e, *verb):
    """The same call works with good settings: a negative test below fails for the right reason
    (the failure it names), not because the verb does not exist yet (usage exits 2 too)."""
    r = adapter(e, "sync-record", *verb)
    assert r.returncode == 0, ("baseline sync-record call failed", r.stdout, r.stderr)
    assert "usage" not in r.stderr


def _kv(out):
    return dict(l.split("=", 1) for l in out.splitlines() if "=" in l)


@needs_sigv4
def test_sync_record_get_prints_the_record(tmp_path, s3):
    r = adapter(r2_adapter_env(tmp_path, s3), "sync-record", "get")
    assert r.returncode == 0, r.stderr
    assert _kv(r.stdout) == {"rec_mode": "sync", "rec_primary": "crm-b", "rec_since": "1700000000"}
    req = s3["reqs"][0]
    assert req["method"] == "GET" and req["path"] == "/bkt/ha/sync-state.json"
    assert req["auth"].startswith("AWS4-HMAC-SHA256"), "the request must be SigV4 signed"
    assert KEY_ID in req["auth"] and SECRET not in req["auth"]


@needs_sigv4
def test_sync_record_key_is_overridable(tmp_path, s3):
    r = adapter(r2_adapter_env(tmp_path, s3, SYNC_RECORD_KEY="ha/other.json"), "sync-record", "get")
    assert r.returncode == 0, r.stderr
    assert s3["reqs"][0]["path"] == "/bkt/ha/other.json"


@needs_sigv4
@pytest.mark.parametrize("status", [404, 403, 500])
def test_sync_record_get_http_errors_are_nonzero(tmp_path, s3, status):
    e = r2_adapter_env(tmp_path, s3)
    baseline_ok(e, "get")
    s3["get_status"] = status
    r = adapter(e, "sync-record", "get")
    assert r.returncode != 0
    assert "rec_mode" not in r.stdout


@needs_sigv4
@pytest.mark.parametrize("body", [
    b"",
    b"not json",
    b"[]",
    b'{"mode": "maybe", "primary": "crm-b", "since": 1}',
    b'{"mode": "sync", "since": 1}',
    b'{"mode": "sync", "primary": "crm-b"}',
    b'{"mode": "sync", "primary": "crm-b", "since": "yesterday"}',
    b'{"mode": "sync", "primary": "crm-b", "since": 1.5}',
    b'{"mode": "sync", "primary": "crm-b", "since": true}',
    b'{"mode": "sync", "primary": "crm-b", "since": -5}',
    b'{"mode": "sync", "primary": "Bad Name", "since": 1}',
    b'{"mode": "sync", "primary": "crm-b\\nrec_mode=sync", "since": 1}',   # line injection into the output
    b'{"mode": null, "primary": null, "since": null}',
])
def test_sync_record_get_a_bad_body_is_nonzero(tmp_path, s3, body):
    e = r2_adapter_env(tmp_path, s3)
    baseline_ok(e, "get")
    s3["body"] = body
    r = adapter(e, "sync-record", "get")
    assert r.returncode != 0, r.stdout
    assert "rec_mode" not in r.stdout


@needs_sigv4
def test_sync_record_get_gives_up_on_a_stalled_server(tmp_path, s3):
    e = r2_adapter_env(tmp_path, s3)
    baseline_ok(e, "get")
    s3["delay"] = 9
    t0 = time.time()
    r = adapter(e, "sync-record", "get", timeout=30)
    assert r.returncode != 0
    assert time.time() - t0 < 8, "curl -m 5 must bound the call"


@needs_sigv4
@pytest.mark.parametrize("mode", ["sync", "async"])
def test_sync_record_put_writes_the_record(tmp_path, s3, mode):
    before = int(time.time())
    r = adapter(r2_adapter_env(tmp_path, s3), "sync-record", "put", mode)
    assert r.returncode == 0, r.stderr
    req = s3["reqs"][0]
    assert req["method"] == "PUT" and req["path"] == "/bkt/ha/sync-state.json"
    assert req["auth"].startswith("AWS4-HMAC-SHA256")
    body = json.loads(req["body"])
    assert set(body) == {"mode", "primary", "since"}
    assert body["mode"] == mode and body["primary"] == "crm-a"
    assert isinstance(body["since"], int) and before - 2 <= body["since"] <= int(time.time()) + 2


@needs_sigv4
def test_sync_record_put_then_get_round_trips(tmp_path, s3):
    e = r2_adapter_env(tmp_path, s3)
    assert adapter(e, "sync-record", "put", "async").returncode == 0
    r = adapter(e, "sync-record", "get")
    assert r.returncode == 0, r.stderr
    kv = _kv(r.stdout)
    assert kv["rec_mode"] == "async" and kv["rec_primary"] == "crm-a" and kv["rec_since"].isdigit()


@needs_sigv4
@pytest.mark.parametrize("status", [403, 500, 204, 201])
def test_sync_record_put_succeeds_only_on_http_200(tmp_path, s3, status):
    e = r2_adapter_env(tmp_path, s3)
    baseline_ok(e, "put", "sync")
    s3["put_status"] = status
    r = adapter(e, "sync-record", "put", "sync")
    assert r.returncode != 0


@needs_sigv4
@pytest.mark.parametrize("mode", ["maybe", "", "SYNC", "sync async"])
def test_sync_record_put_refuses_a_bad_mode_without_a_request(tmp_path, s3, mode):
    e = r2_adapter_env(tmp_path, s3)
    baseline_ok(e, "put", "async")
    s3["reqs"].clear()
    r = adapter(e, "sync-record", "put", mode)
    assert r.returncode != 0
    assert s3["reqs"] == []


@needs_sigv4
def test_sync_record_put_without_a_mode_is_refused(tmp_path, s3):
    e = r2_adapter_env(tmp_path, s3)
    baseline_ok(e, "put", "sync")
    s3["reqs"].clear()
    r = adapter(e, "sync-record", "put")
    assert r.returncode != 0 and s3["reqs"] == []


@needs_sigv4
@pytest.mark.parametrize("verb", [("get",), ("put", "sync")])
def test_sync_record_credentials_never_appear_on_argv_or_in_output(tmp_path, s3, verb):
    r = adapter(r2_adapter_env(tmp_path, s3), "sync-record", *verb)
    assert r.returncode == 0, r.stderr
    argv = (tmp_path / "curl.argv").read_text()
    assert argv.strip(), "the fake curl was not used"
    for secret in (SECRET, KEY_ID):
        assert secret not in argv, "credentials must reach curl on stdin (-K -), never argv"
        assert secret not in r.stdout + r.stderr
    assert "--aws-sigv4" in argv and "aws:amz:auto:s3" in argv
    assert "-K" in argv.split()


@needs_sigv4
def test_sync_record_a_failed_call_does_not_print_credentials_either(tmp_path, s3):
    e = r2_adapter_env(tmp_path, s3)
    baseline_ok(e, "get")
    s3["get_status"] = 500
    r = adapter(e, "sync-record", "get")
    assert r.returncode != 0
    assert SECRET not in r.stdout + r.stderr and KEY_ID not in r.stdout + r.stderr


@needs_sigv4
@pytest.mark.parametrize("missing", ["R2_ENDPOINT", "R2_BUCKET", "R2_CREDENTIALS_FILE"])
@pytest.mark.parametrize("verb", [("get",), ("put", "sync")])
def test_sync_record_missing_settings_exit_2(tmp_path, s3, missing, verb):
    e = r2_adapter_env(tmp_path, s3)
    baseline_ok(e, *verb)
    (tmp_path / "curl.argv").unlink()
    e.pop(missing)
    r = adapter(e, "sync-record", *verb)
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "usage" not in r.stderr
    assert not (tmp_path / "curl.argv").exists(), "no request without complete settings"


@needs_sigv4
@pytest.mark.parametrize("endpoint", ["http://example.com", "ftp://r2.example", "r2.example", "http://127.0.0.1.evil.example"])
def test_sync_record_refuses_a_non_https_endpoint(tmp_path, s3, endpoint):
    e = r2_adapter_env(tmp_path, s3)
    baseline_ok(e, "get")
    (tmp_path / "curl.argv").unlink()
    e["R2_ENDPOINT"] = endpoint
    r = adapter(e, "sync-record", "get")
    assert r.returncode != 0 and "usage" not in r.stderr
    assert not (tmp_path / "curl.argv").exists(), "the credentials must never be sent to a non-https endpoint"


# ---------------------------------------------------------------- section 11c: shipped templates


def test_services_do_not_restart_after_exit_3():
    for unit in ("cf-failover.service", "role-watcher.service"):
        text = (TEMPLATES / "systemd" / unit).read_text()
        assert "RestartPreventExitStatus=3" in text, unit


def test_env_example_ships_disarmed_and_lists_the_new_keys():
    text = (TEMPLATES / "ha-pg.env.example").read_text()
    lines = [l.split(" #")[0].strip() if not l.lstrip().startswith("#") else l.strip() for l in text.splitlines()]
    assert "CONTROLLER_ARMED=no" in lines
    assert "ROLE_WATCHER_ARMED=no" in lines
    for key in ("SELF_APP_NAME", "SELF_SLOT", "PEER_APP_NAME", "PEER_SLOT",
                "R2_ENDPOINT", "R2_BUCKET", "R2_CREDENTIALS_FILE"):
        assert any(l.lstrip("# ").startswith(key + "=") for l in lines), key
    assert not any(l.startswith("SYNC_MODE=on_commit") for l in lines), "on_commit stays commented until the drill"
    assert any(l.startswith("#") and "SYNC_MODE=on_commit" in l for l in lines)
