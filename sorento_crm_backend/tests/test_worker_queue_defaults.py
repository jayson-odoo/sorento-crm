"""The worker must drain every queue something enqueues to.

`notification_service` enqueues all delivery jobs with `queue_name="notifications"`,
but the worker's default queue list omitted it, so those jobs were never drained:
86 `notification_deliveries` rows sat `pending` in production, 32 of them in a single
month, and it cost email as well as web push. The failure is silent by construction -
the enqueue succeeds, the row stays `pending`, and nothing raises.

These tests pin the default so the next queue added cannot quietly drop it again.

#569 split draining across two compose services by latency class (`worker` for slow
batch jobs, `worker_fast` for the short customer-facing ones) so a 39-minute import
never again sits in front of a chatbot media turn or a WhatsApp send. The class below
guards that split the same way: a queue added to one WORKER_QUEUES list but not the
other, or added to neither, falls in the gap this file exists to catch.
"""
import importlib
import re
from pathlib import Path

import pytest

worker = importlib.import_module("worker")

# The real compose file (repo root, three levels up from this test) is gitignored
# everywhere - dev machines and the server both hand-edit their own copy, and it
# embeds live production secrets as env-var fallback defaults, so it must never be
# committed to git. That means it does not exist in a CI checkout: these tests skip
# there rather than fail, and are only load-bearing on a machine that actually has
# the file - typically whoever last edited it locally, and the server after a manual
# sync. See the PRODUCTION note above worker.DEFAULT_QUEUES.
_COMPOSE_PATH = Path(__file__).resolve().parents[2] / "docker-compose.yml"

# PyYAML is not a dependency of this backend (checked at #569 time) and the compose
# file's `${VAR:-default}` interpolation and YAML anchors are more machinery than a
# two-line assertion needs, so this reads the two `WORKER_QUEUES:` lines directly.
_WORKER_QUEUES_LINE = re.compile(r'^\s*WORKER_QUEUES:\s*"?([^"#\n]+?)"?\s*(?:#.*)?$', re.MULTILINE)


def _compose_worker_queue_lists():
    """The WORKER_QUEUES lists compose defines, in file order (worker, worker_fast).

    Skips (not fails) when the compose file is absent - see _COMPOSE_PATH docstring.
    Fails loudly if the file exists but does not carry exactly two such lines, since
    that is itself a sign the split moved and this test's assumptions no longer hold.
    """
    if not _COMPOSE_PATH.exists():
        pytest.skip(
            f"{_COMPOSE_PATH} is gitignored and not present in this checkout - "
            "these tests only run where the real compose file does (a dev machine "
            "or the server), never in CI"
        )
    text = _COMPOSE_PATH.read_text()
    matches = _WORKER_QUEUES_LINE.findall(text)
    assert len(matches) == 2, (
        f"expected exactly 2 'WORKER_QUEUES:' lines in {_COMPOSE_PATH.name} "
        f"(one on `worker`, one on `worker_fast`), found {len(matches)}: {matches!r}"
    )
    return [[q.strip() for q in raw.split(",") if q.strip()] for raw in matches]


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
    assert "notifications" in worker.resolve_queue_names()


def test_compose_worker_and_worker_fast_queues_are_disjoint():
    """A queue must never be claimed by both drain loops.

    Nothing prevents two RQ workers from draining the same queue - it would just
    mean two work-horses can race a compare-and-set job (media, notifications) or
    double-send (respond_io). Disjoint compose lists is how #569 keeps that from
    happening by construction rather than by convention.
    """
    lists = _compose_worker_queue_lists()
    worker_queues, worker_fast_queues = (set(names) for names in lists)
    overlap = worker_queues & worker_fast_queues
    assert not overlap, (
        f"worker and worker_fast both drain {sorted(overlap)} - a queue is a "
        "latency class and belongs to exactly one service (see #569)"
    )


def test_compose_worker_queues_union_matches_worker_default_queues():
    """Every queue in worker.DEFAULT_QUEUES must be drained by exactly one compose service.

    This is the #569 regression this file exists to catch, generalised: the
    'notifications' incident was one queue missing from the only worker there was.
    Post-split, a queue can now ALSO go missing by being added to worker.py but
    never landing in either compose WORKER_QUEUES line - same silent-drop failure,
    new place for it to happen.
    """
    lists = _compose_worker_queue_lists()
    union = set(lists[0]) | set(lists[1])
    default = set(worker.DEFAULT_QUEUES)
    assert union == default, (
        f"compose WORKER_QUEUES union {sorted(union)} != worker.DEFAULT_QUEUES "
        f"{sorted(default)} - missing from compose: {sorted(default - union)}, "
        f"extra in compose: {sorted(union - default)}. Adding/removing a queue is "
        "a three-place change: worker.DEFAULT_QUEUES, the two compose "
        "WORKER_QUEUES lines, and the server's hand-edited copy of compose."
    )
