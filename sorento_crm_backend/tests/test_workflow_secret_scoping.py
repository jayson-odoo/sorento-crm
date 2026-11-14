"""CI-SECRETS-ENV: no repository secret is reachable from a pull_request run.

A `pull_request` run executes the PR branch's OWN copy of the workflow, and a push to any
branch runs that branch's copy too, so a repo-level secret is readable by anyone who can push
a branch: the job `if:` lines on main protect nothing. The fix is GitHub environments with a
"main only" deployment branch policy (set in the repo settings, owner checklist in the PR):

  production     SSH_*, SMTP_*, OWNER_EMAIL, DOCKER_*  build-and-deploy, rollback (approval)
  release-build  DOCKER_*                              build-images (no reviewer)
  outline-sync   OUTLINE_*                             the Outline sync

These tests pin the workflow half: every `secrets.X` (other than the per-run GITHUB_TOKEN)
sits in a job that declares one of those environments, each secret only in the environment
that holds it, and no job reachable from a PR event declares an environment at all.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"

# Which environment may hold which secret. A secret named here in no workflow is fine; a
# secret used in a workflow and named nowhere here fails `test_every_secret_is_mapped`.
SECRET_ENVIRONMENTS = {
    "DOCKER_USERNAME": {"release-build", "production"},
    "DOCKER_PASSWORD": {"release-build", "production"},
    "SSH_HOST": {"production"},
    "SSH_HOST_B": {"production"},
    "SSH_USER": {"production"},
    "SSH_PRIVATE_KEY": {"production"},
    "SSH_KNOWN_HOSTS": {"production"},
    "SMTP_SERVER": {"production"},
    "SMTP_PORT": {"production"},
    "SMTP_USERNAME": {"production"},
    "SMTP_PASSWORD": {"production"},
    "OWNER_EMAIL": {"production"},
    "OUTLINE_API_TOKEN": {"outline-sync"},
    "OUTLINE_BASE_URL": {"outline-sync"},
    "OUTLINE_COLLECTION_ID": {"outline-sync"},
}
PR_EVENTS = {"pull_request", "pull_request_target"}


def _load(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if True in doc:  # PyYAML reads the bare key `on` as boolean True.
        doc["on"] = doc.pop(True)
    return doc


def _workflows() -> list[Path]:
    paths = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    if not paths:
        pytest.skip(f"{WORKFLOWS} not present (in-image run)")
    return paths


def _env_name(job: dict) -> str | None:
    env = job.get("environment")
    if env is None:
        return None
    return env if isinstance(env, str) else env.get("name")


def _jobs():
    for path in _workflows():
        doc = _load(path)
        triggers = doc["on"]
        events = {triggers} if isinstance(triggers, str) else set(triggers)
        for job_id, job in doc["jobs"].items():
            yield path.name, events, job_id, job


def _secrets(job: dict) -> set[str]:
    text = yaml.safe_dump(job)
    return set(re.findall(r"secrets\.([A-Za-z0-9_]+)", text)) - {"GITHUB_TOKEN"}


def test_no_workflow_triggers_on_pull_request_target():
    """pull_request_target runs with the base branch's secrets AND environment access."""
    for name, events, _, _ in _jobs():
        assert "pull_request_target" not in events, name


def test_every_secret_sits_in_an_environment_job():
    for name, _, job_id, job in _jobs():
        used = _secrets(job)
        if used:
            assert _env_name(job), f"{name}:{job_id} reads {sorted(used)} with no environment"


def test_every_secret_is_mapped():
    for name, _, job_id, job in _jobs():
        unknown = _secrets(job) - set(SECRET_ENVIRONMENTS)
        assert not unknown, f"{name}:{job_id} reads unmapped secrets {sorted(unknown)}"


def test_each_secret_only_in_the_environment_that_holds_it():
    for name, _, job_id, job in _jobs():
        env = _env_name(job)
        for secret in _secrets(job):
            allowed = SECRET_ENVIRONMENTS.get(secret, set())
            assert env in allowed, f"{name}:{job_id} reads {secret} in {env!r}, allowed {sorted(allowed)}"


def test_no_pr_reachable_job_declares_an_environment():
    """In a workflow with a PR trigger, an environment job must be gated off PR events.

    The branch policy is the real lock (a PR's own workflow copy can drop this `if`); the
    gate keeps the main copy from ever asking for an environment on a PR run."""
    for name, events, job_id, job in _jobs():
        env = _env_name(job)
        if not env or not (events & PR_EVENTS):
            continue
        cond = str(job.get("if", ""))
        assert "github.event_name == 'workflow_dispatch'" in cond, f"{name}:{job_id}"
        assert "github.ref == 'refs/heads/main'" in cond, f"{name}:{job_id}"


def test_environment_jobs_run_on_main_only():
    """A dispatch from another branch skips, instead of failing on the branch policy."""
    for name, _, job_id, job in _jobs():
        if _env_name(job):
            assert "refs/heads/main" in str(job.get("if", "")), f"{name}:{job_id}"


def test_build_images_uses_release_build_and_deploy_jobs_use_production():
    jobs = {(n, j): job for n, _, j, job in _jobs()}
    assert _env_name(jobs[("deploy.yml", "build-images")]) == "release-build"
    assert _env_name(jobs[("deploy.yml", "build-and-deploy")]) == "production"
    assert _env_name(jobs[("rollback.yml", "rollback")]) == "production"
    assert _env_name(jobs[("outline-user-guides-sync.yml", "sync")]) == "outline-sync"


def test_vapid_public_key_is_a_variable_not_a_secret():
    """It is inlined into the public browser bundle: config, not a secret."""
    text = (WORKFLOWS / "deploy.yml").read_text(encoding="utf-8")
    assert "secrets.NEXT_PUBLIC_VAPID_PUBLIC_KEY" not in text
    assert "NEXT_PUBLIC_VAPID_PUBLIC_KEY=${{ vars.NEXT_PUBLIC_VAPID_PUBLIC_KEY }}" in text
