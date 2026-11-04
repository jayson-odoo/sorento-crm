"""Tests for scripts/ha_release.sh (HA-CF-FAILOVER): the two-node release, primary first.

Fake `ssh` and `scp` on PATH: each host's role comes from <dir>/role-<host> (a list, one line per
--role call, the last line repeating), a deploy on a host fails when <dir>/fail-<host> exists.
Every call is logged. Run: python3 -m pytest infra/tests -q
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ha_release.sh"
SHA = "0123456789abcdef0123456789abcdef01234567"

FAKE_SSH = r"""#!/usr/bin/env bash
d="$FAKE_DIR"
host=""; cmd=""
for a in "$@"; do case "$a" in *@*) host=${a#*@}; host=${host%%:*} ;; esac; done
cmd="${@: -1}"
echo "ssh $host :: $cmd" >> "$d/calls.log"
[ -e "$d/down-$host" ] && exit 255
case "$cmd" in
  *--role*)
    f="$d/role-$host"; n=$(cat "$d/n-$host" 2>/dev/null || echo 0); n=$((n + 1)); echo $n > "$d/n-$host"
    line=$(sed -n "${n}p" "$f"); [ -z "$line" ] && line=$(tail -1 "$f")
    echo "$line" ;;
  *IMAGE_TAG=*)
    [ -e "$d/fail-$host" ] && exit 1
    echo "deployed $host" >> "$d/deployed.log" ;;
esac
exit 0
"""
FAKE_SCP = r"""#!/usr/bin/env bash
echo "scp $*" >> "$FAKE_DIR/calls.log"
exit 0
"""


@pytest.fixture
def env(tmp_path):
    b = tmp_path / "bin"
    b.mkdir()
    for name, body in (("ssh", FAKE_SSH), ("scp", FAKE_SCP)):
        (b / name).write_text(body)
        (b / name).chmod(0o755)
    key = tmp_path / "key"
    key.write_text("k")
    kh = tmp_path / "known_hosts"
    kh.write_text("hosta ssh-ed25519 AAAA\nhostb ssh-ed25519 BBBB\n")
    e = {"PATH": f"{b}:{os.environ['PATH']}", "FAKE_DIR": str(tmp_path), "HA_HOSTS": "hosta hostb",
         "SSH_USER": "deploy", "SSH_KEY_FILE": str(key), "IMAGE_TAG": SHA, "KNOWN_HOSTS_FILE": str(kh)}
    return e, tmp_path


def roles(d, **by_host):
    for h, lines in by_host.items():
        (d / f"role-{h}").write_text("\n".join(lines if isinstance(lines, list) else [lines]) + "\n")


def run(e, **extra):
    return subprocess.run(["bash", str(SCRIPT)], env={**e, **extra}, capture_output=True, text=True, timeout=30)


def deployed(d):
    p = d / "deployed.log"
    return p.read_text().split("\n")[:-1] if p.exists() else []


def test_primary_is_deployed_first_wherever_it_is(env):
    e, d = env
    roles(d, hosta="standby", hostb="primary")
    r = run(e)
    assert r.returncode == 0, r.stdout + r.stderr
    assert deployed(d) == ["deployed hostb", "deployed hosta"]


def test_no_primary_deploys_nothing(env):
    e, d = env
    roles(d, hosta="standby", hostb="standby")
    r = run(e)
    assert r.returncode == 1 and "exactly one primary" in r.stdout
    assert deployed(d) == []


def test_two_primaries_deploy_nothing(env):
    e, d = env
    roles(d, hosta="primary", hostb="primary")
    r = run(e)
    assert r.returncode == 1 and deployed(d) == []


def test_unreachable_primary_deploys_nothing(env):
    e, d = env
    roles(d, hosta="primary", hostb="standby")
    (d / "down-hosta").write_text("")
    r = run(e)
    assert r.returncode == 1 and deployed(d) == []


def test_failed_primary_deploy_leaves_the_standby_alone(env):
    e, d = env
    roles(d, hosta="primary", hostb="standby")
    (d / "fail-hosta").write_text("")
    r = run(e)
    assert r.returncode == 1 and "standbys were not touched" in r.stdout
    assert deployed(d) == []


def test_unreachable_standby_still_ships_the_primary_but_fails_the_release(env):
    e, d = env
    roles(d, hosta="primary", hostb="standby")
    (d / "down-hostb").write_text("")
    r = run(e)
    assert r.returncode == 1
    assert deployed(d) == ["deployed hosta"]


def test_failover_during_the_release_fails_it(env):
    e, d = env
    roles(d, hosta=["primary", "standby"], hostb=["standby", "primary"])
    r = run(e)
    assert r.returncode == 1 and "primary changed" in r.stdout


def test_a_non_ha_host_is_refused(env):
    e, d = env
    roles(d, hosta="primary", hostb="single")
    r = run(e)
    assert r.returncode == 1 and deployed(d) == []


def test_image_tag_must_be_a_sha(env):
    e, d = env
    roles(d, hosta="primary", hostb="standby")
    r = run(e, IMAGE_TAG="abc")
    assert r.returncode == 1 and deployed(d) == []


def test_host_keys_are_pinned_never_trusted_on_first_use(env):
    e, d = env
    roles(d, hosta="primary", hostb="standby")
    r = run(e)
    assert r.returncode == 0, r.stdout
    ssh_calls = [l for l in (d / "calls.log").read_text().splitlines()]
    assert ssh_calls
    # the fake logs only host + command for ssh; check the script's options directly
    src = SCRIPT.read_text()
    assert "StrictHostKeyChecking=yes" in src and "accept-new" not in src


def test_missing_known_hosts_deploys_nothing(env):
    e, d = env
    roles(d, hosta="primary", hostb="standby")
    (Path(e["KNOWN_HOSTS_FILE"])).write_text("")
    r = run(e)
    assert r.returncode == 1 and "SSH_KNOWN_HOSTS" in r.stdout
    assert deployed(d) == []
