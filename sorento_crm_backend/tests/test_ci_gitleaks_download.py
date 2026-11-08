"""scripts/ci_gitleaks.sh fetches the pinned CLI robustly (CI-GITLEAKS-RETRY, 8 Nov 2026).

From 08:46Z on 8 Nov every PR gate died in "Secret scan (gitleaks)" on
`curl: (22) ... error: 504` (first red run 42464184985): github.com release-download
URLs flapped while the API asset endpoint stayed up. So the script now:

1. retries both curls (`--retry 5 --retry-all-errors --retry-delay 15 --connect-timeout 20`);
2. falls back to `gh release download` (the API path) ONLY when the direct download failed;
3. uses a tarball restored by `actions/cache` when present;
4. checks the tarball's sha256 against the release checksums file on EVERY path (direct,
   fallback, cache) and runs nothing when it does not match.

curl, gh and uname are stubbed on PATH; the fixture tarball holds a fake `gitleaks` that
only echoes, so no network and no real scan.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import subprocess
import tarfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci_gitleaks.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
VERSION = "8.30.1"
TARBALL = f"gitleaks_{VERSION}_linux_x64.tar.gz"
SUMS = f"gitleaks_{VERSION}_checksums.txt"
RAN = "FAKE-GITLEAKS-RAN"

pytestmark = pytest.mark.skipif(not SCRIPT.is_file(), reason="scripts/ not present (backend-only checkout)")

CURL_STUB = r"""#!/usr/bin/env bash
echo "curl $*" >> "$CALLS"
url="${@: -1}"
name="${url##*/}"
if [ -n "${CURL_FAIL:-}" ] && [[ "$url" == *"$CURL_FAIL"* ]]; then
  echo "curl: (22) The requested URL returned error: 504" >&2; exit 22
fi
cp "$DIRECT/$name" "./$name"
"""

GH_STUB = r"""#!/usr/bin/env bash
echo "gh $*" >> "$CALLS"
[ "${GH_FAIL:-0}" = "1" ] && { echo "stub gh: HTTP 502" >&2; exit 1; }
dest=.; pats=()
while [ $# -gt 0 ]; do
  case "$1" in -p) pats+=("$2"); shift ;; -D) dest="$2"; shift ;; esac; shift
done
for p in "${pats[@]}"; do cp "$API/$p" "$dest/$p"; done
"""


def _tarball(marker: str) -> bytes:
    body = f"#!/bin/sh\necho {marker} \"$@\"\n".encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("gitleaks")
        info.size, info.mode = len(body), 0o755
        tar.addfile(info, io.BytesIO(body))
    return buf.getvalue()


GOOD = _tarball(RAN)
EVIL = _tarball("TAMPERED-BINARY-RAN")
SUMS_TEXT = f"{hashlib.sha256(GOOD).hexdigest()}  {TARBALL}\n{'0' * 64}  gitleaks_{VERSION}_darwin_x64.tar.gz\n"


def _serve(where: Path, tarball: bytes = GOOD) -> None:
    where.mkdir(parents=True, exist_ok=True)
    (where / TARBALL).write_bytes(tarball)
    (where / SUMS).write_text(SUMS_TEXT)


def _run(tmp_path: Path, *, curl_fail: str = "", gh_fail: bool = False, api_tarball: bytes = GOOD,
         cache: bytes | None = None):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in (("curl", CURL_STUB), ("gh", GH_STUB), ("uname", "#!/bin/sh\necho x86_64\n")):
        (bindir / name).write_text(body)
        (bindir / name).chmod(0o755)
    _serve(tmp_path / "direct")
    _serve(tmp_path / "api", api_tarball)
    cache_dir = tmp_path / "cache"
    if cache is not None:
        _serve(cache_dir, cache)
    repo = tmp_path / "repo"
    repo.mkdir()
    git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for n in (1, 2):
        (repo / "f.txt").write_text(str(n))
        subprocess.run([*git, "-C", str(repo), "add", "f.txt"], check=True)
        subprocess.run([*git, "-C", str(repo), "commit", "-qm", str(n)], check=True)
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()
    calls = tmp_path / "calls.txt"
    calls.write_text("")
    env = {
        "PATH": f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": str(tmp_path), "RANGE": "HEAD~1..HEAD", "RUNNER_TEMP": str(runner_temp),
        "GITLEAKS_CACHE_DIR": str(cache_dir), "CALLS": str(calls),
        "DIRECT": str(tmp_path / "direct"), "API": str(tmp_path / "api"),
        "CURL_FAIL": curl_fail, "GH_FAIL": "1" if gh_fail else "0", "GH_TOKEN": "ghs_dummy",
    }
    result = subprocess.run(["bash", str(SCRIPT)], cwd=repo, env=env, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr, calls.read_text().splitlines(), cache_dir


def test_direct_download_is_used_and_gh_is_not_touched(tmp_path):
    rc, out, calls, cache_dir = _run(tmp_path)
    assert rc == 0, out
    assert RAN in out
    assert [c for c in calls if c.startswith("curl")] and not [c for c in calls if c.startswith("gh")], calls
    assert (cache_dir / TARBALL).read_bytes() == GOOD, "a verified download fills the cache"


def test_both_curls_retry_with_a_connect_timeout(tmp_path):
    rc, out, calls, _ = _run(tmp_path)
    assert rc == 0, out
    curls = [c for c in calls if c.startswith("curl")]
    assert len(curls) == 2, curls
    for c in curls:
        for flag in ("--retry 5", "--retry-all-errors", "--retry-delay 15", "--connect-timeout 20", "-f"):
            assert flag in c, (flag, c)


@pytest.mark.parametrize("failing", [TARBALL, SUMS])
def test_a_failing_direct_url_falls_back_to_the_api(tmp_path, failing):
    rc, out, calls, _ = _run(tmp_path, curl_fail=failing)
    assert rc == 0, out
    assert RAN in out
    gh = [c for c in calls if c.startswith("gh")]
    assert gh == [f"gh release download v{VERSION} -R gitleaks/gitleaks -p {TARBALL} -p {SUMS} -D . --clobber"], gh


def test_the_fallback_tarball_is_checksum_verified(tmp_path):
    rc, out, calls, cache_dir = _run(tmp_path, curl_fail="releases/download", api_tarball=EVIL)
    assert rc != 0, out
    assert "TAMPERED-BINARY-RAN" not in out and RAN not in out
    assert not (cache_dir / TARBALL).exists(), "an unverified tarball must not reach the cache"


def test_direct_and_api_both_down_fails_the_step(tmp_path):
    rc, out, _, _ = _run(tmp_path, curl_fail="releases/download", gh_fail=True)
    assert rc != 0, out
    assert RAN not in out


def test_a_cached_tarball_skips_the_network(tmp_path):
    rc, out, calls, _ = _run(tmp_path, cache=GOOD)
    assert rc == 0, out
    assert RAN in out
    assert calls == [], calls


def test_a_tampered_cache_is_rejected_and_redownloaded(tmp_path):
    rc, out, calls, cache_dir = _run(tmp_path, cache=EVIL)
    assert rc == 0, out
    assert RAN in out and "TAMPERED-BINARY-RAN" not in out
    assert [c for c in calls if c.startswith("curl")], calls
    assert (cache_dir / TARBALL).read_bytes() == GOOD


def test_the_token_is_never_printed(tmp_path):
    _, out, _, _ = _run(tmp_path, curl_fail=TARBALL)
    assert "ghs_dummy" not in out


def _steps() -> list[dict]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["lean-gate"]["steps"]


@pytest.mark.skipif(not WORKFLOW.is_file(), reason="workflow not present")
def test_the_pr_gate_caches_the_cli_and_hands_gh_the_job_token():
    steps = _steps()
    names = [s.get("name") for s in steps]
    scan = steps[names.index("Secret scan (gitleaks)")]
    cache_i = next(i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/cache@"))
    cache = steps[cache_i]
    assert cache_i < names.index("Secret scan (gitleaks)")
    assert cache.get("if") == scan.get("if") == "github.event_name == 'pull_request'"
    script_ver = re.search(r'GITLEAKS_VERSION="\$\{GITLEAKS_VERSION:-([^}]*)\}"', SCRIPT.read_text()).group(1)
    assert cache["with"]["key"] == f"gitleaks-{script_ver}-${{{{ runner.arch }}}}", cache["with"]["key"]
    assert scan["env"]["GITLEAKS_CACHE_DIR"] == cache["with"]["path"]
    assert scan["env"]["GH_TOKEN"] == "${{ github.token }}"
