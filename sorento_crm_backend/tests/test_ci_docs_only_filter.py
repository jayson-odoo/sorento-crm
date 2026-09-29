"""The docs-only classifier in .github/workflows/deploy.yml (job `changes`).

A docs-only push to main skips image build, every test suite and the deploy
(owner ruling 29 Sep 2026). The rule that decides "docs-only" is ONE regex in
the workflow, `DOCS_RE`, and the step applies it with `grep -Ev` over the
changed file list. This test reads that exact line out of the workflow file and
runs the same grep over it, so the regex under test is the regex that ships:
nothing here is a copy that can drift.

The point of every mixed case below is the same: a single non-docs path in a
change must keep the full pipeline, whatever else the change touches.

Dependency-free apart from `bash` and `grep`, which the CI runner has. Skipped
when the workflow file is not present, which is the case inside the backend
Docker image (validate-backend's `pytest --collect-only` and its regression
gate run there, and the image holds only sorento_crm_backend/).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy.yml"


def _docs_regex() -> str:
    if not WORKFLOW.exists():
        pytest.skip(f"{WORKFLOW} not present (in-image run)")
    lines = [
        line.strip()
        for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("DOCS_RE=")
    ]
    assert len(lines) == 1, f"expected exactly one DOCS_RE= line in deploy.yml, found {len(lines)}"
    match = re.fullmatch(r"DOCS_RE='([^']+)'", lines[0])
    assert match, f"DOCS_RE must be a single-quoted literal on one line, got: {lines[0]}"
    return match.group(1)


def _non_docs(files: list[str]) -> list[str]:
    """The paths `grep -Ev DOCS_RE` leaves, i.e. the ones that are NOT docs.

    An empty result is what the workflow reads as docs-only.
    """
    result = subprocess.run(
        ["bash", "-c", 'printf "%s\\n" "$@" | grep -Ev "$DOCS_RE" || true', "_", *files],
        env={"DOCS_RE": _docs_regex(), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.split()


DOCS_ONLY = [
    "documentation/plans/ci/PLAN-ci-docs-skip.md",
    "documentation/plans/_archive/scm/evidence/AC-19b-filters-panel.png",
    "documentation/plans/scm/fixtures/FSCU8103365.xlsx",
    "documentation/user-guides/README.md",
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


def test_docs_only_paths_all_match():
    """Every path a docs merge touches is docs: nothing survives the grep."""
    assert _non_docs(DOCS_ONLY) == []


@pytest.mark.parametrize(
    "path",
    [
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
    ],
)
def test_non_docs_path_survives_the_grep(path):
    """One non-docs path in an otherwise docs-only change keeps the full pipeline."""
    assert _non_docs(DOCS_ONLY + [path]) == [path]


def test_regex_is_anchored_at_path_start():
    """`documentation/` and friends match only as the FIRST path segment.

    A folder named `documentation` nested inside a service tree is code (it is
    inside the Docker build context), and a nested `.claude/` is not the repo's
    agent config.
    """
    nested = [
        "sorento_crm_frontend/documentation/x.md",
        "sorento_crm_backend/.claude/agents/x.md",
        "sorento_crm_mcp/CLAUDE.md",
    ]
    assert _non_docs(nested) == nested
