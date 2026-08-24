"""The worker must drain every queue something enqueues to.

`notification_service` enqueues all delivery jobs with `queue_name="notifications"`,
but the worker's default queue list omitted it, so those jobs were never drained:
86 `notification_deliveries` rows sat `pending` in production, 32 of them in a single
month, and it cost email as well as web push. The failure is silent by construction -
the enqueue succeeds, the row stays `pending`, and nothing raises.

These tests pin the default so the next queue added cannot quietly drop it again.
"""
import importlib

import pytest

worker = importlib.import_module("worker")


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
