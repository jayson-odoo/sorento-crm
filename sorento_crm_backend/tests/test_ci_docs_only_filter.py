"""The docs-only classifier in .github/workflows/deploy.yml (job `changes`).

A docs-only push to main skips image build, every test suite and the deploy
(owner ruling 29 Sep 2026). The rule that decides "docs-only" lives in ONE
shell step in the workflow: `DOCS_RE` names what counts as documentation,
`NOT_DOCS_RE` names the documentation/ paths that tests READ as live inputs,
and both ends of a rename count. This file extracts that step's `run` block out
of the workflow and executes it under the same bash flags GitHub uses, with a
stub `gh` that answers from a canned API payload through the real `jq` filter
the step passes. So the shell under test is the shell that ships: nothing here
is a copy that can drift.

Three things are pinned:

1. Docs-only changes report `docs_only=true` and every area flag false; a
   single non-docs path anywhere keeps the full pipeline (every service tree,
   a migration, each Dockerfile, compose, both workflows, config, scripts,
   markdown fixtures inside the trees, a rename across the boundary).
2. Documentation paths that tests read as inputs are NOT docs. The last test
   below scans every backend and MCP test for such paths (pathlib `/` chains
   and open()/Path() arguments, never comments or docstrings) and runs each
   through the step, so a new test that reads a new documentation/ path fails
   here until NOT_DOCS_RE in the workflow covers it.
3. Every fail-safe (zero `before` SHA, a failed API call, an empty list, the
   300-file cap, workflow_dispatch) lands on the full pipeline.

Needs `bash` and `jq`, which the CI runner has; skipped when the workflow file
is not present, which is the case inside the backend Docker image
(validate-backend's `pytest --collect-only` and its regression gate run there,
and the image holds only sorento_crm_backend/).
"""
from __future__ import annotations

import ast
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

GH_STUB = """\
#!/usr/bin/env bash
# Stub `gh api`: answers every call from $GH_STUB_FIXTURE through the --jq
# filter the caller passed, exactly as gh would. --paginate is accepted and
# ignored (the fixture is one page).
if [ "${GH_STUB_FAIL:-0}" = "1" ]; then echo "stub gh: failing on purpose" >&2; exit 1; fi
expr=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--jq" ]; then expr="$2"; shift; fi
  shift
done
[ -n "$expr" ] || { echo "stub gh: no --jq filter given" >&2; exit 2; }
exec jq -r "$expr" "$GH_STUB_FIXTURE"
"""


def _step_script() -> str:
    """The `run` block of the `Detect changed areas` step, dedented."""
    if not WORKFLOW.exists():
        pytest.skip(f"{WORKFLOW} not present (in-image run)")
    if shutil.which("jq") is None:
        pytest.skip("jq is not installed (the CI runner has it)")
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "- name: Detect changed areas")
    run_at = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    indent = len(lines[run_at]) - len(lines[run_at].lstrip()) + 2
    body: list[str] = []
    for line in lines[run_at + 1:]:
        if line.strip() and (len(line) - len(line.lstrip())) < indent:
            break
        body.append(line)
    script = textwrap.dedent("\n".join(body))
    assert "DOCS_RE='" in script and "NOT_DOCS_RE='" in script, "step body not found in deploy.yml"
    assert "previous_filename" in script, "both jq filters must carry previous_filename"
    return script


def _json(value) -> str:
    import json

    return json.dumps(value)


def run_step(
    tmp_path: Path,
    event: str,
    files: list,
    *,
    gh_fails: bool = False,
    before: str = "a" * 40,
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
    payload = entries if event == "pull_request" else {"files": entries}
    fixture = tmp_path / "api.json"
    fixture.write_text(_json(payload))
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    (stub_dir / "gh").write_text(GH_STUB)
    (stub_dir / "gh").chmod(0o755)
    output = tmp_path / "output.txt"
    output.write_text("")
    env = {
        "PATH": f"{stub_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "GITHUB_OUTPUT": str(output),
        "GITHUB_REPOSITORY": "jayson-odoo/sorento-crm",
        "GH_TOKEN": "stub",
        "GH_STUB_FIXTURE": str(fixture),
        "GH_STUB_FAIL": "1" if gh_fails else "0",
        "EVENT": event,
        "PR": "1",
        "PUSH_BEFORE": before,
        "PUSH_AFTER": "b" * 40,
        "MG_BASE": "c" * 40,
        "MG_HEAD": "d" * 40,
    }
    # The same invocation GitHub uses for a `run:` step on ubuntu-latest.
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _step_script()],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"step failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    outputs = dict(line.split("=", 1) for line in output.read_text().splitlines() if "=" in line)
    assert set(outputs) == {"docs_only", "backend", "frontend", "mcp"}, outputs
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

FULL_PIPELINE = {"docs_only": "false", "backend": "true", "frontend": "true", "mcp": "true"}
DOCS_SKIP = {"docs_only": "true", "backend": "false", "frontend": "false", "mcp": "false"}


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
    assert out == {"docs_only": "false", "backend": "true", "frontend": "false", "mcp": "false"}
    out = run_step(tmp_path, "pull_request", ["sorento_crm_frontend/app/page.tsx"])
    assert out == {"docs_only": "false", "backend": "false", "frontend": "true", "mcp": "false"}
    out = run_step(tmp_path, "pull_request", ["sorento_crm_mcp/pyproject.toml"])
    assert out == {"docs_only": "false", "backend": "false", "frontend": "false", "mcp": "true"}


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
        "docs_only": "false", "backend": "true", "frontend": "false", "mcp": "false",
    }
    moved_in = [("sorento_crm_mcp/tests/fixtures/x.md", "documentation/plans/scm/x.md")]
    assert run_step(tmp_path, "pull_request", moved_in) == {
        "docs_only": "false", "backend": "false", "frontend": "false", "mcp": "true",
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


# ---------------------------------------------------------------------------
# Workflow-level concurrency: only a `ci` label run joins the per-PR group.
# ---------------------------------------------------------------------------
#
# Every label added to a PR fires the workflow (trigger `types: [labeled]`);
# the jobs skip on the label name, but the run still joins a concurrency
# group. With the PR number as the group for every pull_request event, adding
# `needs-hand-test` cancelled a live `ci` run (2026-09-28, #1304, run
# 36387225667). The two expressions are evaluated here as written in the
# workflow, with GitHub's semantics for the operators they use (`&&` and `||`
# return an operand, like JavaScript; a missing context value is the empty
# string).

_GH_TOKEN = re.compile(r"'[^']*'|\d+|[A-Za-z_][\w.-]*|&&|\|\||==|!=|[()]")


def _gh_eval(expression: str, context: dict) -> object:
    """Evaluate the subset of GitHub's expression language the workflow uses."""

    def lookup(path: str):
        node = context
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return ""
            node = node[part]
        return node

    python = []
    for token in _GH_TOKEN.findall(expression):
        if token == "&&":
            python.append(" and ")
        elif token == "||":
            python.append(" or ")
        elif token in ("==", "!=", "(", ")"):
            python.append(f" {token} ")
        elif token.startswith("'") or token.isdigit():
            python.append(token)
        elif token in ("true", "false", "null"):
            python.append({"true": "True", "false": "False", "null": "None"}[token])
        else:
            python.append(f"lookup({token!r})")
    return eval("".join(python), {"__builtins__": {}}, {"lookup": lookup})  # noqa: S307


def _gh_render(template: str, context: dict) -> str:
    return re.sub(r"\$\{\{(.*?)\}\}", lambda m: str(_gh_eval(m.group(1).strip(), context)), template)


def _concurrency() -> tuple[str, str]:
    """The workflow-level `group` and `cancel-in-progress` lines, verbatim."""
    if not WORKFLOW.exists():
        pytest.skip(f"{WORKFLOW} not present (in-image run)")
    text = WORKFLOW.read_text(encoding="utf-8")
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
    return _gh_render(group, ctx), bool(_gh_eval(cancel.strip("${} "), ctx))


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
    ctx = {"github": {"event": {"pull_request": {"number": 5}}}}
    assert _gh_eval("github.event.pull_request.number || github.run_id", ctx) == 5
    assert _gh_eval("github.event.label.name || 'none'", ctx) == "none"  # missing -> ''
    assert _gh_eval("(true && false && 5) || 9", ctx) == 9
    assert _gh_eval("('a' == 'a' && 'b' == 'b' && 5) || 9", ctx) == 5
    assert _gh_eval("github.event_name == 'pull_request'", ctx) is False


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
