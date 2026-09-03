"""The worker must drain every queue something enqueues to.

`notification_service` enqueues all delivery jobs with `queue_name="notifications"`,
but the worker's default queue list omitted it, so those jobs were never drained:
86 `notification_deliveries` rows sat `pending` in production, 32 of them in a single
month, and it cost email as well as web push. The failure is silent by construction -
the enqueue succeeds, the row stays `pending`, and nothing raises.

These tests pin the default so the next queue added cannot quietly drop it again.

#569 split draining across two compose services by latency class (`worker` for slow
batch jobs, `worker_fast` for the short customer-facing ones) so a 39-minute import
never again sits in front of a chatbot media turn or a WhatsApp send. Compose names
only a ROLE on each service (`WORKER_ROLE: batch` / `WORKER_ROLE: fast`), never a
queue - `worker.QUEUES` is the single ordered registry mapping each queue to its
role, so adding a queue is a one-line edit there and these tests fail until it is
classified. See the PRODUCTION note above worker.QUEUES.
"""
import importlib
import re
from itertools import chain
from pathlib import Path

import pytest

worker = importlib.import_module("worker")

# The real compose file (repo root, three levels up from this test) is gitignored
# everywhere - dev machines and the server both hand-edit their own copy, and it
# embeds live production secrets as env-var fallback defaults, so it must never be
# committed to git. That means it does not exist in a CI checkout: the compose test
# below skips there rather than fails, and is only load-bearing on a machine that
# actually has the file - typically whoever last edited it locally, and the server
# after a manual sync.
_COMPOSE_PATH = Path(__file__).resolve().parents[2] / "docker-compose.yml"

# PyYAML is not a dependency of this backend (checked at #569 time) and the compose
# file's `${VAR:-default}` interpolation and YAML anchors are more machinery than a
# one-line assertion needs, so this reads `WORKER_ROLE:` lines directly.
_WORKER_ROLE_LINE = re.compile(r'^\s*WORKER_ROLE:\s*"?([^"#\n]+?)"?\s*(?:#.*)?$', re.MULTILINE)
_WORKER_QUEUES_LINE = re.compile(r'^\s*WORKER_QUEUES:\s*"?([^"#\n]*)"?\s*(?:#.*)?$', re.MULTILINE)


def test_notifications_is_drained_by_default():
    """The queue every notification delivery is enqueued to must be in the default list."""
    assert "notifications" in worker.resolve_queue_names()


@pytest.mark.parametrize(
    "queue",
    ["imports", "respond_io", "catalogue_render", "media", "project_docs", "flyer_read",
     "notifications"],
)
def test_every_known_queue_is_drained_by_default(queue):
    """Each queue the codebase enqueues to, named individually so a drop is legible."""
    assert queue in worker.resolve_queue_names()


def test_worker_queues_env_still_overrides(monkeypatch):
    """A checkout may run a worker for only the queues it cares about."""
    monkeypatch.setenv("WORKER_QUEUES", "imports, notifications ,")
    assert worker.resolve_queue_names() == ["imports", "notifications"]


def test_blank_override_falls_back_to_the_default(monkeypatch):
    """An empty WORKER_QUEUES must not silently produce a worker draining nothing."""
    monkeypatch.setenv("WORKER_QUEUES", "   ")
    monkeypatch.delenv("WORKER_ROLE", raising=False)
    assert "notifications" in worker.resolve_queue_names()


def test_roles_are_pairwise_disjoint():
    """No queue is classified under two roles - QUEUES pairs each name with exactly one."""
    names = [name for name, _role in worker.QUEUES]
    assert len(names) == len(set(names)), (
        f"a queue name appears more than once in worker.QUEUES: {names!r}"
    )


def test_role_union_is_default_queues():
    """Every queue in DEFAULT_QUEUES is covered by the known roles, with no double-count."""
    by_role = {role: worker.queues_for_role(role) for role in worker.ROLES}
    union = set(chain(*by_role.values()))
    assert union == set(worker.DEFAULT_QUEUES)
    assert sum(len(v) for v in by_role.values()) == len(worker.DEFAULT_QUEUES)


def test_default_queues_starts_with_imports_and_ends_with_notifications():
    assert worker.DEFAULT_QUEUES[0] == "imports"
    assert worker.DEFAULT_QUEUES[-1] == "notifications"


def test_default_queues_is_byte_identical_to_pre_split_order():
    """The #569 split must not reorder the no-env fallback drain list."""
    assert worker.DEFAULT_QUEUES == (
        "imports",
        "respond_io",
        "catalogue_render",
        "media",
        "project_docs",
        "flyer_read",
        "notifications",
    )


def test_queues_for_role_fast(monkeypatch):
    assert worker.queues_for_role("fast") == ["respond_io", "media", "notifications"]


def test_queues_for_role_batch(monkeypatch):
    assert worker.queues_for_role("batch") == [
        "imports",
        "catalogue_render",
        "project_docs",
        "flyer_read",
    ]


def test_worker_role_fast_resolves_to_exactly_the_fast_queues(monkeypatch):
    monkeypatch.delenv("WORKER_QUEUES", raising=False)
    monkeypatch.setenv("WORKER_ROLE", "fast")
    assert worker.resolve_queue_names() == worker.queues_for_role("fast")


def test_worker_role_batch_resolves_to_exactly_the_batch_queues(monkeypatch):
    monkeypatch.delenv("WORKER_QUEUES", raising=False)
    monkeypatch.setenv("WORKER_ROLE", "batch")
    assert worker.resolve_queue_names() == worker.queues_for_role("batch")


def test_unknown_worker_role_exits(monkeypatch):
    monkeypatch.delenv("WORKER_QUEUES", raising=False)
    monkeypatch.setenv("WORKER_ROLE", "bogus")
    with pytest.raises(SystemExit):
        worker.resolve_queue_names()


def test_worker_queues_beats_worker_role(monkeypatch):
    """The explicit override wins even when a role is also set."""
    monkeypatch.setenv("WORKER_QUEUES", "media")
    monkeypatch.setenv("WORKER_ROLE", "batch")
    assert worker.resolve_queue_names() == ["media"]


def test_compose_names_only_known_roles_and_no_queue_lists():
    """Compose (where present) names a ROLE per service, never a queue list.

    Skips (not fails) when the compose file is absent - see _COMPOSE_PATH docstring
    above. Fails loudly if the file exists but carries either an unrecognized role
    value or a `WORKER_QUEUES:` line at all - a compose-level queue list is exactly
    the hard-coding the role design replaced.
    """
    if not _COMPOSE_PATH.exists():
        pytest.skip(
            f"{_COMPOSE_PATH} is gitignored and not present in this checkout - "
            "this test only runs where the real compose file does (a dev machine "
            "or the server), never in CI"
        )
    text = _COMPOSE_PATH.read_text()

    role_values = [m.strip() for m in _WORKER_ROLE_LINE.findall(text)]
    assert role_values, f"expected at least one 'WORKER_ROLE:' line in {_COMPOSE_PATH.name}"
    unknown = [v for v in role_values if v not in worker.ROLES]
    assert not unknown, (
        f"{_COMPOSE_PATH.name} sets WORKER_ROLE to unrecognized value(s) {unknown!r}; "
        f"known roles: {worker.ROLES}"
    )

    queue_lines = _WORKER_QUEUES_LINE.findall(text)
    assert not queue_lines, (
        f"{_COMPOSE_PATH.name} still sets 'WORKER_QUEUES:' on a service ({queue_lines!r}) - "
        "compose should name only a WORKER_ROLE; worker.QUEUES in worker.py owns the list"
    )
