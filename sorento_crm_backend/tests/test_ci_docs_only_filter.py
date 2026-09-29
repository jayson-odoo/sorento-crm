"""The gating logic in .github/workflows/deploy.yml, executed as it ships.

Three rules live in that workflow and are pinned here:

1. Docs-only (job `changes`, step "Detect changed areas"): a change whose every
   path is documentation skips image build, every test suite and the deploy
   (owner ruling 29 Sep 2026). `DOCS_RE` names what counts as documentation,
   `NOT_DOCS_RE` names the documentation/ paths that tests READ as live
   inputs, both ends of a rename count, and `SCM_RE` decides whether the SCM
   shards run on a PR.
2. Release by dispatch (the jobs' `if` lines): a push to main runs the alembic
   gate and nothing else; a `workflow_dispatch` on main runs the full suite
   (or, with `skip_tests`, nothing) then build-images and build-and-deploy,
   which carries `environment: production` so the owner approves each deploy.
3. Fast PR gate + queue (the jobs' `if` lines and the workflow `concurrency`):
   a `ci`-labelled PR runs the fast gates and the SCM shards only when SCM
   paths changed, the six backend shards run in the merge queue and in a
   release, and only a `ci` label run joins the per-PR concurrency group.

The shell steps are extracted from the workflow file and executed under the
same bash flags GitHub uses, with a stub `gh` that answers every API call from
a canned payload through the real `jq` filter the step passes. The `if`
expressions are evaluated as written with a small evaluator for the operators
they use. So nothing here is a copy that can drift from the workflow: the test
scans every backend and MCP test for the documentation/ paths test code reads
and fails when one would classify as docs (extend NOT_DOCS_RE).

Needs `bash` and `jq`, which the CI runner has; skipped when the workflow file
is not present, which is the case inside the backend Docker image
(validate-backend's `pytest --collect-only` and its regression gate run there,
and the image holds only sorento_crm_backend/).
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "deploy.yml"
TEST_TREES = [REPO / "sorento_crm_backend" / "tests", REPO / "sorento_crm_mcp" / "tests"]
ZERO_SHA = "0" * 40
SHA = "b" * 40
BEFORE = "a" * 40

# Stub `gh api`: answers from $GH_STUB_DIR/<key>.json, where <key> is the
# endpoint after `repos/<owner>/<repo>/` with every `/ ? & =` replaced by `_`,
# through the --jq filter the caller passed, exactly as gh would. A missing
# fixture is a failed call (as a 404 would be). --paginate is accepted and
# ignored (each fixture is one page).
GH_STUB = """\
#!/usr/bin/env bash
if [ "${GH_STUB_FAIL:-0}" = "1" ]; then echo "stub gh: failing on purpose" >&2; exit 1; fi
endpoint=""; expr=""
while [ $# -gt 0 ]; do
  case "$1" in
    api) ;;
    --jq) expr="$2"; shift ;;
    --paginate) ;;
    *) [ -z "$endpoint" ] && endpoint="$1" ;;
  esac
  shift
done
[ -n "$expr" ] || { echo "stub gh: no --jq filter given" >&2; exit 2; }
key=$(printf '%s' "$endpoint" | sed -E 's#^repos/[^/]+/[^/]+/##; s#[/?&=]#_#g')
file="$GH_STUB_DIR/$key.json"
[ -f "$file" ] || { echo "stub gh: no fixture for $endpoint ($key)" >&2; exit 1; }
exec jq -r "$expr" "$file"
"""


def _fixture_key(endpoint: str) -> str:
    return re.sub(r"[/?&=]", "_", re.sub(r"^repos/[^/]+/[^/]+/", "", endpoint))


def _workflow_text() -> str:
    if not WORKFLOW.exists():
        pytest.skip(f"{WORKFLOW} not present (in-image run)")
    return WORKFLOW.read_text(encoding="utf-8")


def _step_script(step_name: str) -> str:
    """The `run` block of the named step, dedented."""
    if shutil.which("jq") is None:
        pytest.skip("jq is not installed (the CI runner has it)")
    lines = _workflow_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == f"- name: {step_name}")
    run_at = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    indent = len(lines[run_at]) - len(lines[run_at].lstrip()) + 2
    body: list[str] = []
    for line in lines[run_at + 1:]:
        if line.strip() and (len(line) - len(line.lstrip())) < indent:
            break
        body.append(line)
    return textwrap.dedent("\n".join(body))


def _run_shell(tmp_path: Path, script: str, env: dict, fixtures: dict, *, gh_fails: bool = False) -> dict[str, str]:
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    (stub_dir / "gh").write_text(GH_STUB)
    (stub_dir / "gh").chmod(0o755)
    fixture_dir = tmp_path / "api"
    fixture_dir.mkdir(exist_ok=True)
    for endpoint, payload in fixtures.items():
        (fixture_dir / f"{_fixture_key(endpoint)}.json").write_text(json.dumps(payload))
    output = tmp_path / "output.txt"
    output.write_text("")
    full_env = {
        "PATH": f"{stub_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "GITHUB_OUTPUT": str(output),
        "GITHUB_REPOSITORY": "jayson-odoo/sorento-crm",
        "GH_TOKEN": "stub",
        "GH_STUB_DIR": str(fixture_dir),
        "GH_STUB_FAIL": "1" if gh_fails else "0",
        **env,
    }
    # The same invocation GitHub uses for a `run:` step on ubuntu-latest.
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        env=full_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"step failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    return dict(line.split("=", 1) for line in output.read_text().splitlines() if "=" in line)


# ---------------------------------------------------------------------------
# Step "Detect changed areas"
# ---------------------------------------------------------------------------

AREA_KEYS = {"docs_only", "backend", "frontend", "mcp", "scm"}


def run_step(
    tmp_path: Path,
    event: str,
    files: list,
    *,
    gh_fails: bool = False,
    before: str = BEFORE,
    skip_tests: str = "",
) -> dict[str, str]:
    """Run the real step with `files` as the API answer; return $GITHUB_OUTPUT.

    Each entry of `files` is a path, or a (new_path, previous_path) pair for a
    rename, shaped into the PR-files array or the compare object exactly as the
    GitHub API returns them.
    """
    entries = []
    for f in files:
        if isinstance(f, tuple):
            entries.append({"filename": f[0], "previous_filename": f[1], "status": "renamed"})
        else:
            entries.append({"filename": f, "status": "modified"})
    fixtures = {
        "repos/jayson-odoo/sorento-crm/pulls/1/files": entries,
        f"repos/jayson-odoo/sorento-crm/compare/{before}...{SHA}": {"files": entries},
        f"repos/jayson-odoo/sorento-crm/compare/{'c' * 40}...{'d' * 40}": {"files": entries},
    }
    env = {
        "EVENT": event, "PR": "1", "PUSH_BEFORE": before, "PUSH_AFTER": SHA,
        "MG_BASE": "c" * 40, "MG_HEAD": "d" * 40, "SKIP_TESTS": skip_tests,
    }
    outputs = _run_shell(tmp_path, _step_script("Detect changed areas"), env, fixtures, gh_fails=gh_fails)
    assert set(outputs) == AREA_KEYS, outputs
    return outputs


DOCS_ONLY = [
    "documentation/plans/ci/PLAN-ci-docs-skip-29sep.md",
    "documentation/plans/_archive/scm/evidence/AC-19b-filters-panel.png",
    "documentation/plans/scm/mockups/so-change-management-grill-v4.html",
    "documentation/user-guides/README.md",
    "documentation/adr/0001-example.md",
    "CLAUDE.md",
    "PRINCIPLES.md",
    "LESSONS-LEARNT.md",
    "README.md",
    ".claude/agents/coder.md",
    ".claude/skills/feature/SKILL.md",
    ".claude/evidence/shared-brand-S2/01-folder-context-menu-1280.png",
    ".cursor/rules/frontend.mdc",
    ".github/PULL_REQUEST_TEMPLATE.md",
]

FULL_PIPELINE = {"docs_only": "false", "backend": "true", "frontend": "true", "mcp": "true", "scm": "true"}
DOCS_SKIP = {"docs_only": "true", "backend": "false", "frontend": "false", "mcp": "false", "scm": "false"}
NO_AREA = {"backend": "false", "frontend": "false", "mcp": "false", "scm": "false"}


@pytest.mark.parametrize("event", ["pull_request", "push", "merge_group"])
def test_docs_only_change_skips_everything(tmp_path, event):
    assert run_step(tmp_path, event, DOCS_ONLY) == DOCS_SKIP


NON_DOCS = [
    # code in each service tree
    "sorento_crm_backend/app/main.py",
    "sorento_crm_frontend/app/(protected)/page.tsx",
    "sorento_crm_mcp/sorento_crm_mcp/server.py",
    # migration
    "sorento_crm_backend/alembic/versions/900_docs_skip_guard.py",
    # Dockerfiles and compose
    "sorento_crm_backend/Dockerfile",
    "sorento_crm_frontend/Dockerfile",
    "sorento_crm_mcp/Dockerfile",
    "sorento_crm/docker-compose.yml",
    # the workflow itself, and the other workflow
    ".github/workflows/deploy.yml",
    ".github/workflows/outline-user-guides-sync.yml",
    # config, lockfiles, scripts
    "sorento_crm_frontend/package-lock.json",
    "sorento_crm_frontend/next.config.mjs",
    "sorento_crm_backend/requirements.txt",
    "sorento_crm_backend/tests/ci_excluded.txt",
    "sorento_crm_backend/.test_durations",
    "scripts/blue_green_deploy.sh",
    "scripts/git-hooks/pre-push",
    ".gitignore",
    "pyrightconfig.json",
    # markdown INSIDE a service tree is a fixture or an image input, never docs
    "sorento_crm_backend/tests/chatbot/replay_turns/turn_01.md",
    "sorento_crm_frontend/e2e/fixtures/project-cs/notes.md",
    "sorento_crm_mcp/README.md",
    "sorento_crm_backend/README.md",
    "sorento_crm_frontend/docs/README.md",
    "scripts/git-hooks/README.md",
    # a root-level file that is not markdown
    "e2e-stack.sh",
    "brands-grid.yml",
    # nested folders: only the FIRST path segment is docs
    "sorento_crm_frontend/documentation/x.md",
    "sorento_crm_backend/.claude/agents/x.md",
    "sorento_crm_mcp/CLAUDE.md",
    # documentation/ paths that tests read as live inputs (crew review of #1370)
    "documentation/reference/ADR-PRODUCT-STANDARDS.md",
    "documentation/plans/scm/fixtures/FSCU8103365.xlsx",
    "documentation/plans/scm/fixtures/Jinbaichuan_Invoice.xlsx",
    "documentation/plans/chatbot/samples/top-selling-01.json",
    "documentation/plans/dealer-kit/seed-assets/pdf-geometry.json",
    "documentation/plans/_archive/scm/fixtures/moved-with-the-plan.xlsx",
    "documentation/plans/autocount/PLAN-autocount-cross-repo-contract.md",
    "documentation/plans/_archive/scm/PLAN-scm-fulfilment-feedback-p4.md",
]


@pytest.mark.parametrize("path", NON_DOCS)
def test_one_non_docs_path_keeps_the_full_pipeline(tmp_path, path):
    """One non-docs path in an otherwise docs-only push keeps the full pipeline."""
    assert run_step(tmp_path, "push", DOCS_ONLY + [path]) == FULL_PIPELINE


def test_pull_request_area_flags_still_follow_the_service_trees(tmp_path):
    out = run_step(tmp_path, "pull_request", DOCS_ONLY + ["sorento_crm_backend/app/main.py"])
    assert out == {"docs_only": "false", "backend": "true", "frontend": "false", "mcp": "false", "scm": "false"}
    out = run_step(tmp_path, "pull_request", ["sorento_crm_frontend/app/page.tsx"])
    assert out == {"docs_only": "false", "backend": "false", "frontend": "true", "mcp": "false", "scm": "false"}
    out = run_step(tmp_path, "pull_request", ["sorento_crm_mcp/pyproject.toml"])
    assert out == {"docs_only": "false", "backend": "false", "frontend": "false", "mcp": "true", "scm": "false"}


SCM_PATHS = [
    "sorento_crm_backend/app/api/v1/scm/orders.py",
    "sorento_crm_backend/app/services/scm/sales_order_service.py",
    "sorento_crm_backend/app/modules/scm/bootstrap.py",
    "sorento_crm_backend/app/models/scm.py",
    "sorento_crm_backend/app/schemas/scm_orders.py",
    "sorento_crm_backend/tests/scm/test_committed_v.py",
    "sorento_crm_backend/alembic/versions/273_scm_schema.py",
    # the harness every backend test depends on
    "sorento_crm_backend/tests/conftest.py",
    "sorento_crm_backend/tests/_pg_fixture.py",
    "sorento_crm_backend/tests/ci_excluded.txt",
    "sorento_crm_backend/.test_durations",
    "sorento_crm_backend/scripts/bootstrap_env.py",
    "sorento_crm_backend/requirements.txt",
    ".github/workflows/deploy.yml",
]


@pytest.mark.parametrize("path", SCM_PATHS)
def test_scm_path_on_a_pull_request_runs_the_scm_shards(tmp_path, path):
    out = run_step(tmp_path, "pull_request", [path])
    assert out["scm"] == "true", out
    assert out["backend"] == "true", out


@pytest.mark.parametrize(
    "path",
    [
        "sorento_crm_backend/app/services/procurement_service.py",
        "sorento_crm_backend/app/api/v1/master_data/products.py",
        "sorento_crm_backend/tests/test_rbac.py",
        "sorento_crm_backend/app/models/product.py",
        "sorento_crm_backend/alembic/versions/900_products_x.py",
        "sorento_crm_backend/app/schemas/user.py",
        "sorento_crm_frontend/app/page.tsx",
    ],
)
def test_non_scm_backend_path_on_a_pull_request_skips_the_scm_shards(tmp_path, path):
    out = run_step(tmp_path, "pull_request", [path])
    assert out["scm"] == "false", out


@pytest.mark.parametrize("event", ["push", "merge_group"])
def test_scm_follows_backend_off_a_pull_request(tmp_path, event):
    """Off a PR the SCM shards run for any code change (the queue; a push's flags are unused)."""
    out = run_step(tmp_path, event, ["sorento_crm_frontend/app/page.tsx"])
    assert out == FULL_PIPELINE


@pytest.mark.parametrize("event", ["push", "merge_group"])
def test_rename_out_of_a_service_tree_is_not_docs(tmp_path, event):
    """A rename reports the docs path as `filename`; the old path must count too."""
    moved_out = [("documentation/plans/scm/old-notes.md", "sorento_crm_backend/docs/old-notes.md")]
    assert run_step(tmp_path, event, moved_out) == FULL_PIPELINE
    moved_in = [("sorento_crm_backend/tests/fixtures/x.md", "documentation/plans/scm/x.md")]
    assert run_step(tmp_path, event, moved_in) == FULL_PIPELINE
    fixture_moved = [("documentation/plans/scm/notes/x.xlsx", "documentation/plans/scm/fixtures/x.xlsx")]
    assert run_step(tmp_path, event, fixture_moved) == FULL_PIPELINE


def test_rename_on_a_pull_request_flags_the_tree_it_left(tmp_path):
    """On a PR the area flags follow the trees; the old path of a rename counts."""
    moved_out = [("documentation/plans/scm/old-notes.md", "sorento_crm_backend/docs/old-notes.md")]
    assert run_step(tmp_path, "pull_request", moved_out) == {
        "docs_only": "false", "backend": "true", "frontend": "false", "mcp": "false", "scm": "false",
    }
    moved_in = [("sorento_crm_mcp/tests/fixtures/x.md", "documentation/plans/scm/x.md")]
    assert run_step(tmp_path, "pull_request", moved_in) == {
        "docs_only": "false", "backend": "false", "frontend": "false", "mcp": "true", "scm": "false",
    }
    fixture_moved = [("documentation/plans/scm/notes/x.xlsx", "documentation/plans/scm/fixtures/x.xlsx")]
    assert run_step(tmp_path, "pull_request", fixture_moved)["docs_only"] == "false"


@pytest.mark.parametrize("event", ["pull_request", "push", "merge_group"])
def test_rename_within_documentation_is_docs(tmp_path, event):
    archived = [
        ("documentation/plans/_archive/scm/PLAN-x.md", "documentation/plans/scm/PLAN-x.md"),
        ("documentation/plans/_archive/scm/x-acceptance-criteria.md", "documentation/plans/scm/x-acceptance-criteria.md"),
    ]
    assert run_step(tmp_path, event, archived) == DOCS_SKIP


def test_fail_safes_land_on_the_full_pipeline(tmp_path):
    assert run_step(tmp_path, "push", DOCS_ONLY, before=ZERO_SHA) == FULL_PIPELINE
    assert run_step(tmp_path, "push", DOCS_ONLY, gh_fails=True) == FULL_PIPELINE
    assert run_step(tmp_path, "merge_group", DOCS_ONLY, gh_fails=True) == FULL_PIPELINE
    assert run_step(tmp_path, "pull_request", DOCS_ONLY, gh_fails=True) == FULL_PIPELINE
    assert run_step(tmp_path, "push", []) == FULL_PIPELINE
    assert run_step(tmp_path, "workflow_dispatch", DOCS_ONLY) == FULL_PIPELINE
    many = [f"documentation/plans/x/{i}.md" for i in range(300)]
    assert run_step(tmp_path, "push", many) == FULL_PIPELINE, "300 files is the compare cap"
    assert run_step(tmp_path, "push", many[:299]) == DOCS_SKIP


def test_release_always_tests_the_whole_head(tmp_path):
    """A dispatch has no diff: every area counts, docs_only is never true."""
    assert run_step(tmp_path, "workflow_dispatch", DOCS_ONLY) == FULL_PIPELINE
    assert run_step(tmp_path, "workflow_dispatch", [], skip_tests="false") == FULL_PIPELINE


def test_release_with_skip_tests_zeroes_every_area_but_is_not_docs_only(tmp_path):
    """build-images and build-and-deploy gate on the event, so they still run."""
    out = run_step(tmp_path, "workflow_dispatch", [], skip_tests="true")
    assert out == {"docs_only": "false", **NO_AREA}
    # The input is honoured on a dispatch only: it is empty on every other
    # event, and even a stray "true" must not silence a PR or queue run.
    assert run_step(tmp_path, "pull_request", ["sorento_crm_frontend/x.ts"], skip_tests="true")["frontend"] == "true"
    assert run_step(tmp_path, "merge_group", ["sorento_crm_backend/app/main.py"], skip_tests="true") == FULL_PIPELINE


# ---------------------------------------------------------------------------
# The `if` lines and the workflow-level concurrency, evaluated as written.
# ---------------------------------------------------------------------------
#
# A small evaluator for the subset of GitHub's expression language the
# workflow uses: `&&` and `||` return an operand (like JavaScript), `!`
# negates, a missing context value is the empty string, `contains()` on a
# list is membership, `needs.*.result` is the list of every need's result,
# and the status functions read the run state the scenario provides.

_GH_TOKEN = re.compile(r"'[^']*'|\d+|[A-Za-z_][\w.*-]*|&&|\|\||==|!=|[(),!]")
_GH_FUNCS = {"always", "cancelled", "success", "failure", "contains"}


def _gh_eval(expression: str, context: dict) -> object:
    def lookup(path: str):
        if path == "needs.*.result":
            return [job.get("result", "") for job in context.get("needs", {}).values()]
        node = context
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return ""
            node = node[part]
        return node

    def contains(haystack, needle):
        if isinstance(haystack, list):
            return needle in haystack
        return str(needle).lower() in str(haystack).lower()

    state = context.get("_run", {})
    funcs = {
        "lookup": lookup,
        "contains": contains,
        "always": lambda: True,
        "cancelled": lambda: state.get("cancelled", False),
        "success": lambda: state.get("success", True),
        "failure": lambda: state.get("failure", False),
    }
    python = []
    for token in _GH_TOKEN.findall(expression):
        if token == "&&":
            python.append(" and ")
        elif token == "||":
            python.append(" or ")
        elif token == "!":
            python.append(" not ")
        elif token in ("==", "!=", "(", ")", ","):
            python.append(f" {token} ")
        elif token.startswith("'") or token.isdigit():
            python.append(token)
        elif token in ("true", "false", "null"):
            python.append({"true": "True", "false": "False", "null": "None"}[token])
        elif token in _GH_FUNCS:
            python.append(token)
        else:
            python.append(f"lookup({token!r})")
    return eval("".join(python), {"__builtins__": {}}, funcs)  # noqa: S307


def _gh_render(template: str, context: dict) -> str:
    return re.sub(r"\$\{\{(.*?)\}\}", lambda m: str(_gh_eval(m.group(1).strip(), context)), template, flags=re.S)


def _expression(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("${{") and raw.endswith("}}"):
        raw = raw[3:-2].strip()
    return raw


def _job_ifs() -> dict[str, dict]:
    """job id -> {"if": expression or None, "needs": [...]} from the workflow text."""
    text = _workflow_text()
    jobs_text = text[text.index("\njobs:\n"):]
    jobs: dict[str, dict] = {}
    for block in re.split(r"\n(?=  [a-z][\w-]*:\n)", jobs_text):
        head = re.match(r"  ([a-z][\w-]*):\n", block)
        if not head:
            continue
        lines = block.splitlines()
        cond = None
        for i, line in enumerate(lines):
            m = re.match(r"^    if: (.*)$", line)
            if not m:
                continue
            value = m.group(1).strip()
            if value in (">-", ">", "|", "|-"):
                folded = []
                for cont in lines[i + 1:]:
                    if cont.strip() and (len(cont) - len(cont.lstrip())) <= 4:
                        break
                    folded.append(cont.strip())
                value = " ".join(folded)
            cond = _expression(value)
            break
        needs = re.search(r"^    needs:\s*(\[[^\]]*\]|\n(?:      .*\n?)+)", block, re.M)
        need_ids: list[str] = []
        if needs:
            need_ids = re.findall(r"[a-z][\w-]*", needs.group(1))
        jobs[head.group(1)] = {"if": cond, "needs": need_ids}
    return jobs


def _simulate(event: str, *, label: str | None = None, outputs: dict | None = None,
              forced: dict | None = None, ref: str = "refs/heads/main") -> dict[str, str]:
    """Result of every job (success/skipped/failure) for one run, in file order.

    Mirrors GitHub's rule: a job whose `if` names no status function skips
    when any need did not succeed; `always()` / `!cancelled()` conditions are
    evaluated against the needs' results instead.
    """
    github = {"event_name": event, "event": {}, "run_id": 1, "workflow": "Build and Deploy Sorento", "ref": ref}
    if event == "pull_request":
        github["event"] = {"pull_request": {"number": 1370}, "label": {"name": label or "ci"}}
    results: dict[str, str] = {}
    forced = forced or {}
    for job_id, job in _job_ifs().items():
        needs = {n: {"result": results[n], "outputs": (outputs or {}) if n == "changes" else {}} for n in job["needs"]}
        ctx = {"github": github, "needs": needs, "_run": {"cancelled": False}}
        cond = job["if"]
        uses_status_fn = bool(cond) and bool(re.search(r"\b(always|cancelled|success|failure)\(\)", cond))
        if not uses_status_fn and any(r != "success" for r in (results[n] for n in job["needs"])):
            results[job_id] = "skipped"
            continue
        runs = True if cond is None else bool(_gh_eval(cond, ctx))
        results[job_id] = (forced.get(job_id, "success") if runs else "skipped")
    return results


def _ran(results: dict[str, str]) -> set[str]:
    return {job for job, r in results.items() if r != "skipped"}


GATES_ON_PR = {"check-migration-heads", "changes", "release-ci-label"}


def test_pull_request_fast_gate_backend_with_scm_paths():
    ran = _ran(_simulate("pull_request", outputs={"backend": "true", "scm": "true", "frontend": "false", "mcp": "false", "docs_only": "false"}))
    assert ran == GATES_ON_PR | {"validate-backend", "test-backend-scm"}
    assert "test-backend" not in ran, "the six backend shards never run on a pull_request"


def test_pull_request_fast_gate_backend_without_scm_paths():
    ran = _ran(_simulate("pull_request", outputs={"backend": "true", "scm": "false", "frontend": "false", "mcp": "false", "docs_only": "false"}))
    assert ran == GATES_ON_PR | {"validate-backend"}


def test_pull_request_fast_gate_frontend_and_mcp():
    ran = _ran(_simulate("pull_request", outputs={"backend": "false", "scm": "false", "frontend": "true", "mcp": "true", "docs_only": "false"}))
    assert ran == GATES_ON_PR | {"validate-frontend", "typecheck-frontend", "validate-mcp"}


def test_pull_request_docs_only_runs_the_root_jobs_only():
    ran = _ran(_simulate("pull_request", outputs={**NO_AREA, "docs_only": "true"}))
    assert ran == GATES_ON_PR


def test_pull_request_with_another_label_runs_nothing():
    for label in ["needs-hand-test", "lane-running", "needs-decision"]:
        assert _ran(_simulate("pull_request", label=label)) == set(), label


def test_merge_group_runs_the_full_suite_and_never_deploys():
    ran = _ran(_simulate("merge_group", outputs=FULL_PIPELINE))
    assert ran == {
        "check-migration-heads", "changes", "validate-backend", "validate-mcp",
        "test-backend-scm", "test-backend", "validate-frontend", "typecheck-frontend",
    }


RELEASE_ONLY = {"check-migration-heads", "changes", "build-images", "build-and-deploy", "notify-owner"}
FULL_SUITE = {
    "check-migration-heads", "changes", "validate-backend", "validate-mcp",
    "test-backend-scm", "test-backend", "validate-frontend", "typecheck-frontend",
}


def test_push_to_main_runs_the_alembic_gate_and_nothing_else():
    """Owner decision 29 Sep 2026: a merge does not test or deploy."""
    for outputs in (FULL_PIPELINE, {**NO_AREA, "docs_only": "true"}):
        results = _simulate("push", outputs=outputs)
        assert _ran(results) == {"check-migration-heads"}, results
        assert results["changes"] == "skipped"
        assert results["build-images"] == "skipped"
        assert results["build-and-deploy"] == "skipped"
        assert results["notify-owner"] == "skipped"


def test_release_runs_the_full_suite_then_builds_and_deploys():
    ran = _ran(_simulate("workflow_dispatch", outputs=FULL_PIPELINE))
    assert ran == FULL_SUITE | RELEASE_ONLY


def test_release_with_skip_tests_builds_and_deploys_only():
    ran = _ran(_simulate("workflow_dispatch", outputs={"docs_only": "false", **NO_AREA}))
    assert ran == RELEASE_ONLY


def test_release_dispatched_on_another_ref_tests_but_never_ships():
    results = _simulate("workflow_dispatch", outputs=FULL_PIPELINE, ref="refs/heads/crew/ci-fast-gate")
    assert _ran(results) == FULL_SUITE
    assert results["build-images"] == "skipped"
    assert results["build-and-deploy"] == "skipped"
    assert results["notify-owner"] == "skipped"


@pytest.mark.parametrize("failed", ["test-backend", "test-backend-scm", "validate-frontend", "typecheck-frontend",
                                    "validate-backend", "validate-mcp", "check-migration-heads", "build-images"])
def test_release_with_a_failed_gate_does_not_deploy_but_still_notifies(failed):
    results = _simulate("workflow_dispatch", outputs=FULL_PIPELINE, forced={failed: "failure"})
    assert results["build-and-deploy"] == "skipped", failed
    assert results["notify-owner"] == "success", "the owner is mailed about the failed release"


def test_release_with_skip_tests_and_a_failed_build_does_not_deploy():
    for failed in ("build-images", "check-migration-heads"):
        results = _simulate("workflow_dispatch", outputs={"docs_only": "false", **NO_AREA}, forced={failed: "failure"})
        assert results["build-and-deploy"] == "skipped", failed


def test_deploy_job_carries_the_production_environment():
    """The owner's approval gate: the only job that touches the server."""
    text = _workflow_text()
    block = re.search(r"\n  build-and-deploy:\n(.*?)\n  [a-z][\w-]*:\n", text, re.S).group(1)
    assert re.search(r"^    environment:\n      name: production$", block, re.M), block
    for other in ("build-images", "notify-owner", "test-backend", "changes"):
        other_block = re.search(rf"\n  {other}:\n(.*?)\n  [a-z][\w-]*:\n", text, re.S).group(1)
        assert "environment:" not in other_block, other


def test_merge_group_never_deploys_whatever_the_flags():
    results = _simulate("merge_group", outputs=FULL_PIPELINE)
    assert results["build-images"] == "skipped"
    assert results["build-and-deploy"] == "skipped"
    assert results["notify-owner"] == "skipped"


def _concurrency() -> tuple[str, str]:
    """The workflow-level `group` and `cancel-in-progress` lines, verbatim."""
    text = _workflow_text()
    block = re.search(r"^concurrency:\n((?:  .*\n)+)", text, re.M)
    assert block, "workflow-level concurrency block not found"
    group = re.search(r"^  group: (.*)$", block.group(1), re.M)
    cancel = re.search(r"^  cancel-in-progress: (.*)$", block.group(1), re.M)
    assert group and cancel, block.group(1)
    return group.group(1).strip(), cancel.group(1).strip()


def _event(event: str, *, label: str | None = None, pr: int | None = None, run_id: int) -> dict:
    ctx = {"workflow": "Build and Deploy Sorento", "event_name": event, "run_id": run_id, "event": {}}
    if pr is not None:
        ctx["event"]["pull_request"] = {"number": pr}
    if label is not None:
        ctx["event"]["label"] = {"name": label}
    return {"github": ctx}


def _resolve(ctx: dict) -> tuple[str, bool]:
    group, cancel = _concurrency()
    return _gh_render(group, ctx), bool(_gh_eval(_expression(cancel), ctx))


def test_concurrency_ci_label_runs_share_the_pr_group_and_cancel():
    first = _resolve(_event("pull_request", label="ci", pr=1370, run_id=1))
    second = _resolve(_event("pull_request", label="ci", pr=1370, run_id=2))
    assert first == ("ci-Build and Deploy Sorento-1370", True)
    assert second[0] == first[0], "a re-added ci label must supersede the older ci run"
    other_pr = _resolve(_event("pull_request", label="ci", pr=1371, run_id=3))
    assert other_pr[0] != first[0], "one PR's ci run must not cancel another PR's"


@pytest.mark.parametrize("label", ["needs-hand-test", "lane-running", "needs-decision", "ready-for-agent"])
def test_concurrency_other_label_events_join_no_group_and_cancel_nothing(label):
    ci_group, _ = _resolve(_event("pull_request", label="ci", pr=1370, run_id=1))
    group, cancel = _resolve(_event("pull_request", label=label, pr=1370, run_id=2))
    assert group != ci_group, f"a {label} event must not join the PR's ci group"
    assert group.endswith("-2"), "falls through to the run id, a group nothing else can join"
    assert cancel is False


@pytest.mark.parametrize("event", ["push", "merge_group", "workflow_dispatch"])
def test_concurrency_non_pr_events_are_unique_and_never_cancel(event):
    group, cancel = _resolve(_event(event, run_id=77))
    assert group == "ci-Build and Deploy Sorento-77"
    assert cancel is False


def test_gh_eval_matches_github_semantics():
    """Guard on the evaluator itself for the operators the workflow relies on."""
    ctx = {"github": {"event": {"pull_request": {"number": 5}}},
           "needs": {"a": {"result": "success"}, "b": {"result": "skipped"}}}
    assert _gh_eval("github.event.pull_request.number || github.run_id", ctx) == 5
    assert _gh_eval("github.event.label.name || 'none'", ctx) == "none"  # missing -> ''
    assert _gh_eval("(true && false && 5) || 9", ctx) == 9
    assert _gh_eval("('a' == 'a' && 'b' == 'b' && 5) || 9", ctx) == 5
    assert _gh_eval("github.event_name == 'pull_request'", ctx) is False
    assert _gh_eval("!contains(needs.*.result, 'failure')", ctx) is True
    assert _gh_eval("contains(needs.*.result, 'skipped')", ctx) is True
    assert _gh_eval("!cancelled() && needs.a.result == 'success'", ctx) is True
    assert _gh_eval("always() && needs.b.result == 'success'", ctx) is False


# ---------------------------------------------------------------------------
# Self-check: every documentation/ path a test reads must NOT be docs.
# ---------------------------------------------------------------------------

_PATH_CALLS = {"Path", "PurePath", "open", "read_text", "read_bytes", "glob", "rglob", "exists", "joinpath"}


def _div_chain(node: ast.AST) -> list[str]:
    """`base / "documentation" / "plans" / name` -> its string parts, in order."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _div_chain(node.left) + _div_chain(node.right)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    return []


def _documentation_inputs() -> dict[str, str]:
    """documentation/ paths that test CODE names as files or folders.

    Two shapes count: a pathlib `/` chain holding a "documentation" segment
    (the outermost chain only, so a prefix is not reported beside its full
    path), and a string literal starting with `documentation/` passed straight
    to Path()/open()/read_text()/glob() and friends. Docstrings, comments and
    strings that only cite a plan in an assertion message do not count.
    Returns path -> "file:line" of the first mention.
    """
    found: dict[str, str] = {}
    self_file = Path(__file__).resolve()
    for tree_root in TEST_TREES:
        for py in sorted(tree_root.rglob("*.py")):
            if py.resolve() == self_file:
                continue
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            inner: set[int] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                    for child in (node.left, node.right):
                        if isinstance(child, ast.BinOp) and isinstance(child.op, ast.Div):
                            inner.add(id(child))
            where = f"{py.relative_to(REPO)}"
            for node in ast.walk(tree):
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and id(node) not in inner:
                    parts = _div_chain(node)
                    if "documentation" in parts:
                        path = "/".join(parts[parts.index("documentation"):])
                        found.setdefault(path, f"{where}:{node.lineno}")
                elif isinstance(node, ast.Call):
                    func = node.func
                    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                    if name not in _PATH_CALLS:
                        continue
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                                and arg.value.startswith("documentation/"):
                            found.setdefault(arg.value, f"{where}:{arg.lineno}")
    return found


def _probe(path: str) -> str:
    """A concrete file path inside what a test names (a folder, a glob or a file)."""
    parts = [p for p in path.split("/") if p and "*" not in p]
    if "." not in parts[-1]:
        parts.append("probe.txt")
    return "/".join(parts)


def test_documentation_inputs_scan_finds_the_known_readers():
    """Guard on the scanner itself: the readers the crew review cited are found."""
    inputs = _documentation_inputs()
    for expected in [
        "documentation/plans/scm/fixtures",
        "documentation/reference",
        "documentation/plans/autocount/PLAN-autocount-cross-repo-contract.md",
        "documentation/plans/_archive/scm/PLAN-scm-fulfilment-feedback-p4.md",
        "documentation/plans/dealer-kit/seed-assets/pdf-geometry.json",
        "documentation/plans/chatbot/samples",
    ]:
        assert expected in inputs, f"{expected} not found by the scan; found: {sorted(inputs)}"


def test_every_documentation_path_a_test_reads_keeps_the_full_pipeline(tmp_path):
    """A test that reads documentation/ must not be skipped by a change to it.

    Fails when a test reads a documentation/ path that the workflow would
    classify as docs. The fix is to extend NOT_DOCS_RE in deploy.yml (job
    `changes`) to cover the new path, never to loosen this test.
    """
    inputs = _documentation_inputs()
    assert len(inputs) >= 5, f"scan found too few documentation readers: {inputs}"
    misclassified = {}
    for path, where in sorted(inputs.items()):
        probe = _probe(path)
        out = run_step(tmp_path, "push", [probe])
        if out["docs_only"] != "false":
            misclassified[probe] = where
    assert not misclassified, (
        "these documentation/ paths are read by tests but the workflow treats a "
        "change to them as docs-only; extend NOT_DOCS_RE in deploy.yml: "
        f"{misclassified}"
    )
