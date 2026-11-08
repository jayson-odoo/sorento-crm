"""HA-TONIGHT S5 compose tools (crew review 8 Nov): compose-ha-urls.py, compose-env-hash.py --all,
ha-env-for-replica.py, compose-find-keys.py.

The rewrite must parse quoted values and trailing comments, and the before/after proof must see
every key of every service (the first version skipped exactly the keys the rewrite touches).
The docker tests run `docker compose config` for real and are skipped where docker is missing.

Run: python3 -m pytest infra/tests -q
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


urls = load("compose-ha-urls")


def run(script, args=(), stdin="", **kw):
    return subprocess.run([sys.executable, "-I", str(SCRIPTS / f"{script}.py"), *args],
                          input=stdin, capture_output=True, text=True, timeout=60, **kw)


# ------------------------------------------------------------------ compose-ha-urls.py


@pytest.mark.parametrize("line, want", [
    ("  DATABASE_URL: postgresql://u:p@pgbouncer:5432/d",
     "  DATABASE_URL: '${HA_DATABASE_URL:-postgresql://u:p@pgbouncer:5432/d}'"),
    ('  DIRECT_URL: "postgresql://u:p@db:5432/d"  # direct, for alembic',
     "  DIRECT_URL: '${HA_DIRECT_URL:-postgresql://u:p@db:5432/d}' # direct, for alembic"),
    ("  DIRECT_URL: 'postgresql://u:p''q@db:5432/d' # c",
     "  DIRECT_URL: '${HA_DIRECT_URL:-postgresql://u:p''q@db:5432/d}' # c"),
    ('  DATABASE_URL: "postgresql://u:p\\"q@db:5432/d"',
     "  DATABASE_URL: '${HA_DATABASE_URL:-postgresql://u:p\"q@db:5432/d}'"),
    ("  DATABASE_URL: postgresql://u:p@db:5432/d # plain comment",
     "  DATABASE_URL: '${HA_DATABASE_URL:-postgresql://u:p@db:5432/d}' # plain comment"),
    ("  ANALYTICS_RO_DATABASE_URL: postgresql://ro:p@pgbouncer:5432/d",
     "  ANALYTICS_RO_DATABASE_URL: '${HA_ANALYTICS_RO_DATABASE_URL:-postgresql://ro:p@pgbouncer:5432/d}'"),
    ("      - DATABASE_URL=postgresql://u:p@pgbouncer:5432/d",
     "      - 'DATABASE_URL=${HA_DATABASE_URL:-postgresql://u:p@pgbouncer:5432/d}'"),
    ('      - "DIRECT_URL=postgresql://u:p@db:5432/d"   # quoted item',
     "      - 'DIRECT_URL=${HA_DIRECT_URL:-postgresql://u:p@db:5432/d}' # quoted item"),
])
def test_rewrite_handles_quotes_and_comments(line, want):
    new, changed = urls.rewrite_line(line)
    assert changed and new == want


@pytest.mark.parametrize("line", [
    "  REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}",
    "  READ_DATABASE_URL_X: postgresql://x@db:5432/d",
    "  DATABASE_URL:",
    "  DATABASE_URL: # nothing",
    "  DATABASE_URL: '${HA_DATABASE_URL:-postgresql://u:p@db:5432/d}'",
])
def test_rewrite_leaves_other_lines_alone(line):
    assert urls.rewrite_line(line) == (line, False)


@pytest.mark.parametrize("line", [
    "  DATABASE_URL: *dburl",
    "  DATABASE_URL: &dburl postgresql://u:p@db:5432/d",
    "  DATABASE_URL: ${DB:-postgresql://u:p@db:5432/d}",
    '  DATABASE_URL: "postgresql://u:p\\tq@db/d"',
    '  DATABASE_URL: "postgresql://u:p@db/d" trailing',
    '  DATABASE_URL: "unterminated',
])
def test_rewrite_stops_on_what_it_cannot_parse_and_leaves_the_file(tmp_path, line):
    f = tmp_path / "docker-compose.yml"
    f.write_text("services:\n  a:\n    environment:\n" + line + "\n")
    before = f.read_text()
    r = run("compose-ha-urls", [str(f)])
    assert r.returncode != 0 and "STOP" in r.stderr
    assert f.read_text() == before


def test_rewrite_is_idempotent(tmp_path):
    f = tmp_path / "docker-compose.yml"
    f.write_text('x:\n  DATABASE_URL: "postgresql://u:p@db/d"  # c\n')
    assert "changed lines: 1" in run("compose-ha-urls", [str(f)]).stdout
    once = f.read_text()
    assert "changed lines: 0" in run("compose-ha-urls", [str(f)]).stdout
    assert f.read_text() == once


# ------------------------------------------------------------------ compose-env-hash.py


CFG = {
    "name": "p",
    "services": {
        "backend_blue": {"image": "i", "environment": {"JWT_SECRET": "s", "DATABASE_URL": "u1", "REDIS_URL": "r"}},
        "db": {"image": "pg", "environment": {"POSTGRES_PASSWORD": "pw"}},
        "worker": {"image": "i", "environment": ["DATABASE_URL=u1", "ENABLE_SCHEDULER=true"]},
    },
    "networks": {"n": {}},
}


def test_hash_all_sees_every_key_of_every_service():
    out = run("compose-env-hash", ["--all"], json.dumps(CFG)).stdout
    for needle in ("backend_blue DATABASE_URL ", "backend_blue REDIS_URL ", "db POSTGRES_PASSWORD ",
                   "worker DATABASE_URL ", "db __service__ ", "__top__ networks "):
        assert needle in out, out
    assert "u1" not in out and "pw" not in out


@pytest.mark.parametrize("mutate", [
    lambda c: c["services"]["backend_blue"]["environment"].update(DATABASE_URL="u2"),
    lambda c: c["services"]["worker"]["environment"].__setitem__(0, "DATABASE_URL=u2"),
    lambda c: c["services"]["db"].update(image="pg2"),
    lambda c: c["networks"].update(m={}),
])
def test_hash_all_changes_when_anything_changes(mutate):
    a = run("compose-env-hash", ["--all"], json.dumps(CFG)).stdout
    c = json.loads(json.dumps(CFG))
    mutate(c)
    assert run("compose-env-hash", ["--all"], json.dumps(c)).stdout != a


def test_parity_mode_still_skips_the_per_node_urls():
    out = run("compose-env-hash", [], json.dumps(CFG)).stdout
    assert "JWT_SECRET" in out and "DATABASE_URL" not in out and "db " not in out


# ------------------------------------------------------------------ ha-env-for-replica.py


def test_env_lines_unescape_compose_dollars(tmp_path):
    cfg = {"services": {"backend_blue": {"environment": {
        "DATABASE_URL": "postgresql://u:pa$$ss@pgbouncer:5432/d",
        "DIRECT_URL": "postgresql://u:pa$$ss@db:5432/d"}}}}
    out = tmp_path / "env"
    with open(out, "w") as fh:
        r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "ha-env-for-replica.py")],
                           input=json.dumps(cfg), stdout=fh, stderr=subprocess.PIPE, text=True)
    assert r.returncode == 0, r.stderr
    text = out.read_text()
    assert "HA_DATABASE_URL='postgresql://u:pa$ss@sorento_crm_replica:5432/d'" in text
    assert "HA_DIRECT_URL='postgresql://u:pa$ss@sorento_crm_replica:5432/d'" in text
    assert "REDIS_URL=redis://redis:6379/0" in text


# ------------------------------------------------------------------ compose-find-keys.py


def test_find_keys_prints_paths_never_values():
    cfg = {"services": {
        "backend_blue": {"environment": {"ANALYTICS_RO_DATABASE_URL": "postgresql://ro:secret@pgbouncer:5432/d",
                                         "DATABASE_URL": "postgresql://u:p@sorento_crm_replica:5432/d"}},
        "mcp_blue": {"environment": ["CRM_BASE_URL=https://crm.example"]}}}
    r = run("compose-find-keys", ["@pgbouncer", "crm.example"], json.dumps(cfg))
    assert "FOUND services.backend_blue.environment.ANALYTICS_RO_DATABASE_URL" in r.stdout
    assert "FOUND services.mcp_blue.environment.CRM_BASE_URL" in r.stdout
    assert "HITS: 2" in r.stdout and "secret" not in r.stdout


# ------------------------------------------------------------------ real docker compose round trip

needs_docker = pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not installed")

COMPOSE = """x-backend-env: &backend-env
  DATABASE_URL: postgresql://app:pa$$ss@pgbouncer:5432/sorento
  DIRECT_URL: "postgresql://app:pa$$ss@db:5432/sorento"  # alembic
  REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}
services:
  backend_blue:
    image: busybox
    environment:
      <<: *backend-env
  worker:
    image: busybox
    environment:
      - "DATABASE_URL=postgresql://app:pa$$ss@pgbouncer:5432/sorento"  # same
      - ENABLE_SCHEDULER=true
"""


def compose_json(d):
    r = subprocess.run(["docker", "compose", "config", "--format", "json"], cwd=d,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


@needs_docker
def test_round_trip_a_unchanged_and_b_reads_the_replica(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    (a / "docker-compose.yml").write_text(COMPOSE)
    before = run("compose-env-hash", ["--all"], compose_json(a)).stdout
    assert "changed lines: 3" in run("compose-ha-urls", [str(a / "docker-compose.yml")]).stdout
    after = run("compose-env-hash", ["--all"], compose_json(a)).stdout
    assert before == after  # node A: byte-identical resolution, every key of every service

    b = tmp_path / "b"
    b.mkdir()
    shutil.copy(a / "docker-compose.yml", b / "docker-compose.yml")
    with open(b / ".env", "w") as fh:
        r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "ha-env-for-replica.py")],
                           input=compose_json(b), stdout=fh, stderr=subprocess.PIPE, text=True)
    assert r.returncode == 0, r.stderr
    cfg = json.loads(compose_json(b))
    be = cfg["services"]["backend_blue"]["environment"]
    assert be["DATABASE_URL"] == be["DIRECT_URL"] == "postgresql://app:pa$$ss@sorento_crm_replica:5432/sorento"
    assert be["REDIS_URL"] == "redis://redis:6379/0"
    found = run("compose-find-keys", ["@pgbouncer", "@db:"], compose_json(b)).stdout
    assert "HITS: 0" in found, found


def test_env_lines_swap_the_analytics_url_only_when_set(tmp_path):
    base = {"DATABASE_URL": "postgresql://u:p@pgbouncer:5432/d", "DIRECT_URL": "postgresql://u:p@db:5432/d"}
    for extra, want in (({}, False), ({"ANALYTICS_RO_DATABASE_URL": "postgresql://ro:q@pgbouncer:5432/d"}, True)):
        out = tmp_path / "env"
        with open(out, "w") as fh:
            r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "ha-env-for-replica.py")],
                               input=json.dumps({"services": {"backend_blue": {"environment": {**base, **extra}}}}),
                               stdout=fh, stderr=subprocess.PIPE, text=True)
        assert r.returncode == 0, r.stderr
        text = out.read_text()
        assert ("HA_ANALYTICS_RO_DATABASE_URL='postgresql://ro:q@sorento_crm_replica:5432/d'" in text) == want, text


def test_find_keys_catches_a_url_without_a_port():
    cfg = {"services": {"backend_blue": {"environment": {"X_URL": "postgresql://u:p@db/d"}}}}
    r = run("compose-find-keys", ["@pgbouncer", "@db:", "@db/"], json.dumps(cfg))
    assert "FOUND services.backend_blue.environment.X_URL" in r.stdout and "HITS: 1" in r.stdout


# ------------------------------------------------------------------ S5.1b on A (owner 8 Nov 23:53)
# A's compose has, besides the literal anchor lines, `DATABASE_URL: ${DATABASE_URL:-<url>}` lines.
# The rewrite nests them: `${HA_DATABASE_URL:-${DATABASE_URL:-<url>}}`, so A (no HA_) resolves
# exactly what it did, whether or not its .env sets DATABASE_URL.


@pytest.mark.parametrize("line, want", [
    ("    DATABASE_URL: ${DATABASE_URL:-postgresql://u:p@203.0.113.9:5432/d}",
     "    DATABASE_URL: '${HA_DATABASE_URL:-${DATABASE_URL:-postgresql://u:p@203.0.113.9:5432/d}}'"),
    ('    DIRECT_URL: "${DIRECT_URL:-postgresql://u:p@203.0.113.9:5432/d}"  # c',
     "    DIRECT_URL: '${HA_DIRECT_URL:-${DIRECT_URL:-postgresql://u:p@203.0.113.9:5432/d}}' # c"),
    ("    DIRECT_URL: ${DIRECT_URL-postgresql://u:p@h:5432/d}",
     "    DIRECT_URL: '${HA_DIRECT_URL:-${DIRECT_URL-postgresql://u:p@h:5432/d}}'"),
    ("    DATABASE_URL: ${DATABASE_URL}",
     "    DATABASE_URL: '${HA_DATABASE_URL:-${DATABASE_URL}}'"),
    ("      - DATABASE_URL=${DATABASE_URL:-postgresql://u:pa$$s@h:5432/d}",
     "      - 'DATABASE_URL=${HA_DATABASE_URL:-${DATABASE_URL:-postgresql://u:pa$$s@h:5432/d}}'"),
])
def test_rewrite_nests_a_same_key_variable(line, want):
    new, changed = urls.rewrite_line(line)
    assert changed and new == want
    assert urls.rewrite_line(new) == (new, False)  # idempotent


@pytest.mark.parametrize("line", [
    "    DATABASE_URL: ${OTHER_URL:-postgresql://u:p@h/d}",          # a different variable
    "    DATABASE_URL: ${DATABASE_URL:-${X}}",                       # nested already
    "    DATABASE_URL: ${DATABASE_URL:?must be set}x",                # text after the brace
    "    DATABASE_URL: ${DATABASE_URL:?must be set}",                 # required form: by hand
    "    DATABASE_URL: postgresql://u:${PW}@h/d",                    # partial interpolation
])
def test_rewrite_still_stops_on_other_interpolation(line):
    with pytest.raises(urls.Stop):
        urls.rewrite_line(line)


COMPOSE_A = COMPOSE + """  legacy:
    image: busybox
    environment:
      DATABASE_URL: ${DATABASE_URL:-postgresql://app:pa$$ss@203.0.113.9:5432/sorento}
      DIRECT_URL: ${DIRECT_URL:-postgresql://app:pa$$ss@203.0.113.9:5432/sorento}
"""


@needs_docker
@pytest.mark.parametrize("a_env", ["", "DATABASE_URL=postgresql://app:x@198.51.100.7:5432/sorento\n"])
def test_round_trip_with_a_variable_line(tmp_path, a_env):
    a = tmp_path / "a"
    a.mkdir()
    (a / "docker-compose.yml").write_text(COMPOSE_A)
    (a / ".env").write_text(a_env)
    before = run("compose-env-hash", ["--all"], compose_json(a)).stdout
    assert "changed lines: 5" in run("compose-ha-urls", [str(a / "docker-compose.yml")]).stdout
    assert run("compose-env-hash", ["--all"], compose_json(a)).stdout == before  # A-UNCHANGED

    b = tmp_path / "b"
    b.mkdir()
    shutil.copy(a / "docker-compose.yml", b / "docker-compose.yml")
    (b / ".env").write_text("#DATABASE_URL=postgresql://app:x@203.0.113.9:5432/sorento\n")
    with open(b / ".env", "a") as fh:
        r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "ha-env-for-replica.py")],
                           input=compose_json(b), stdout=fh, stderr=subprocess.PIPE, text=True)
    assert r.returncode == 0, r.stderr
    cfg = json.loads(compose_json(b))
    for svc in ("backend_blue", "legacy"):
        e = cfg["services"][svc]["environment"]
        assert e["DATABASE_URL"] == e["DIRECT_URL"] == "postgresql://app:pa$$ss@sorento_crm_replica:5432/sorento"
    found = run("compose-find-keys", ["@pgbouncer", "@db:", "203.0.113.9"], compose_json(b)).stdout
    assert "HITS: 0" in found, found
