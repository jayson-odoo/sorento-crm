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
    "  DATABASE_URL: ${DB:-postgresql://u:p@db:5432/d",
    "  DATABASE_URL: postgresql://u:p@db:5432/d}",
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


def auto_env(d):
    """ha-env-for-replica.py --auto on node directory d; returns (stdout text, stderr)."""
    out = d / "gen.env"
    with open(out, "w") as fh:
        p = subprocess.run([sys.executable, "-I", str(SCRIPTS / "ha-env-for-replica.py"), "--auto",
                            str(d / "docker-compose.yml")], stdout=fh, stderr=subprocess.PIPE, text=True)
    assert p.returncode == 0, p.stderr
    return out.read_text(), p.stderr


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
    text, err = auto_env(b)
    assert "HA_DATABASE_URL_2 (worker.DATABASE_URL)" in err, err
    (b / ".env").write_text(text)
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


# ------------------------------------------------------------------ 8 Nov: A's real shape (two blocks, nested ${...})

A_SHAPE = """x-backend-env: &backend-env
  DATABASE_URL: postgresql://app:pw@pgbouncer:5432/${POSTGRES_DB:-sorento_ai_automation}
  DIRECT_URL: postgresql://app:pw@db:5432/${POSTGRES_DB:-sorento_ai_automation}
  REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}
x-other-env: &other-env
  DATABASE_URL: ${DATABASE_URL:-postgresql://app:pw@203.0.113.9:5432/sorento_ai_automation?schema=public}
  DIRECT_URL: ${DIRECT_URL:-${DATABASE_URL:-postgresql://app:pw@203.0.113.9:5432/sorento_ai_automation?schema=public}}
services:
  backend_blue:
    image: busybox
    environment:
      <<: *backend-env
  frontend_blue:
    image: busybox
    environment:
      <<: *other-env
"""


def test_nested_values_get_numbered_names_and_a_line_map():
    new, n = urls.rewrite(A_SHAPE)
    assert n == 4
    assert [(k, v) for _no, k, v in urls.rewrite.lines] == [
        ("DATABASE_URL", "HA_DATABASE_URL"), ("DIRECT_URL", "HA_DIRECT_URL"),
        ("DATABASE_URL", "HA_DATABASE_URL_2"), ("DIRECT_URL", "HA_DIRECT_URL_2")]
    assert "'${HA_DIRECT_URL_2:-${DIRECT_URL:-${DATABASE_URL:-postgresql://app:pw@203.0.113.9:5432/" in new
    again, n2 = urls.rewrite(new)
    assert n2 == 0 and again == new


@needs_docker
def test_a_shape_round_trip(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    (a / "docker-compose.yml").write_text(A_SHAPE)
    (a / ".env").write_text("POSTGRES_DB=sorento_ai_automation\n")
    before = run("compose-env-hash", ["--all"], compose_json(a)).stdout
    r = run("compose-ha-urls", [str(a / "docker-compose.yml")])
    assert "changed lines: 4" in r.stdout and "-> HA_DATABASE_URL_2" in r.stdout, r.stdout + r.stderr
    assert run("compose-env-hash", ["--all"], compose_json(a)).stdout == before  # node A unchanged

    # node B: same file; its .env still carries the old line that pointed at A's public address
    b = tmp_path / "b"
    b.mkdir()
    shutil.copy(a / "docker-compose.yml", b / "docker-compose.yml")
    (b / ".env").write_text("POSTGRES_DB=sorento_ai_automation\nDATABASE_URL=postgresql://app:pw@203.0.113.9:5432/sorento_ai_automation?schema=public\n")
    gen, err = auto_env(b)   # BEFORE the old .env line is commented out (block 2 falls back to it)
    assert "HA_DATABASE_URL_2 (frontend_blue.DATABASE_URL)" in err and "HA_DIRECT_URL (backend_blue.DIRECT_URL)" in err, err
    gen = [gen]
    env = (b / ".env").read_text().replace("\nDATABASE_URL=", "\n#DATABASE_URL=")
    (b / ".env").write_text(env + "".join(gen))
    cfg = json.loads(compose_json(b))
    be, fe = cfg["services"]["backend_blue"]["environment"], cfg["services"]["frontend_blue"]["environment"]
    assert be["DATABASE_URL"] == "postgresql://app:pw@sorento_crm_replica:5432/sorento_ai_automation"
    assert fe["DATABASE_URL"] == "postgresql://app:pw@sorento_crm_replica:5432/sorento_ai_automation?schema=public"
    assert fe["DIRECT_URL"] == fe["DATABASE_URL"]
    hits = run("compose-find-keys", ["@pgbouncer", "@db:", "@db/", "203.0.113.9"], compose_json(b)).stdout
    assert "HITS: 0" in hits, hits
