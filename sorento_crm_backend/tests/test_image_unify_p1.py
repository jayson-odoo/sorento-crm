"""IMAGE-UNIFY P1: the parts of the rendition service that do not depend on #2126.

Plan: documentation/plans/resources/PLAN-image-unify-03nov.md ("On-demand path", "Print copy",
"Cache-Control", "Overwrites"). UAC: image-unify-acceptance-criteria.md AC-5, AC-6, AC-9, AC-12.

No database and no storage: the single-flight path is driven with in-memory fakes, the storage
backends with a recording boto client.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.services import image_thumbnailer as rt


# --------------------------------------------------------------------------- print copy (Q1)


def test_print_box_px_is_layer_box_at_300_dpi():
    # 40 x 30 mm -> 472.4 x 354.3 px, rounded up so the copy is never short of the box.
    assert rt.print_box_px(40, 30) == (473, 355)
    assert rt.print_box_px(95, 44.5) == (1123, 526)  # 1122.05 rounds up


@pytest.mark.parametrize(
    "src, box, fit, crop, expected",
    [
        # contain: the image fits inside the box, the tighter axis decides.
        ((4000, 3000), (473, 355), "contain", None, 473 / 4000),
        ((3000, 4000), (473, 355), "contain", None, 355 / 4000),
        # cover: the image fills the box, the looser axis decides.
        ((4000, 3000), (473, 200), "cover", None, 473 / 4000),
        ((4000, 1000), (473, 355), "cover", None, 355 / 1000),
        # stretch: each axis on its own; the copy keeps aspect, so the sharper axis decides.
        ((4000, 3000), (473, 100), "stretch", None, 473 / 4000),
        # crop: only the cropped window is drawn into the box, so it needs more source pixels.
        ((4000, 3000), (473, 355), "contain", {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5}, 473 / 2000),
        # never upscale: a small source prints from itself.
        ((300, 200), (473, 355), "contain", None, 1.0),
        ((300, 200), (473, 355), "cover", None, 1.0),
    ],
)
def test_print_scale(src, box, fit, crop, expected):
    assert rt.print_scale(src[0], src[1], box, fit, crop) == pytest.approx(expected)


def test_print_scale_unknown_fit_reads_as_contain_and_bad_crop_is_clamped():
    assert rt.print_scale(4000, 3000, (473, 355), None, None) == pytest.approx(473 / 4000)
    # A zero-size crop (corrupt saved value) must not divide by zero; it clamps like the FE does
    # (lib/dealer-kit/image-crop.ts, MIN_CROP_FRACTION 0.02) and the scale stays capped at 1.
    assert rt.print_scale(4000, 3000, (473, 355), "contain", {"x": 0, "y": 0, "width": 0, "height": 0}) == 1.0


# --------------------------------------------------------------------------- single flight (Q4)


class FakeStore:
    """Object existence plus a counter of how often the expensive work ran."""

    def __init__(self, present=False, delay=0.0, fail=False):
        self.present = present
        self.delay = delay
        self.fail = fail
        self.made = 0
        self.checked = 0
        self._lock = threading.Lock()

    def exists(self):
        with self._lock:
            self.checked += 1
        return self.present

    def make(self):
        time.sleep(self.delay)
        with self._lock:
            self.made += 1
        if self.fail:
            return False
        self.present = True
        return True


class FakeLock:
    """Behaves like redis-py's Lock: with ``thread_local`` (its default) the token lives in the
    acquiring thread, and a release from any other thread raises LockNotOwnedError."""

    def __init__(self, owner, held_by_other, thread_local=True):
        self.owner = owner
        self.held_by_other = held_by_other
        self.thread_local = thread_local
        self.acquired_in = None
        self.released = False

    def acquire(self, blocking=False):
        if self.owner.down:
            raise ConnectionError("redis down")
        if self.owner.held_by_other:
            return False
        self.owner.taken += 1
        self.acquired_in = threading.get_ident()
        return True

    def release(self):
        if self.thread_local and threading.get_ident() != self.acquired_in:
            raise RuntimeError("LockNotOwnedError: token is thread-local")
        self.released = True
        self.owner.released += 1


class FakeRedis:
    def __init__(self, held_by_other=False, down=False):
        self.held_by_other = held_by_other
        self.down = down
        self.taken = 0
        self.released = 0
        self.names = []

    def lock(self, name, timeout=None, blocking=False, thread_local=True):
        self.names.append(name)
        return FakeLock(self, self.held_by_other, thread_local=thread_local)

    def exists(self, name):
        if self.down:
            raise ConnectionError("redis down")
        return 1 if self.held_by_other else 0


@pytest.fixture(autouse=True)
def _fresh_memo():
    rt.reset_rendition_memo()
    yield
    rt.reset_rendition_memo()


def _deadline(seconds=5.0):
    return time.monotonic() + seconds


def test_present_object_is_memoised_and_never_checked_again():
    store = FakeStore(present=True)
    assert rt.single_flight("k1", store.exists, store.make, deadline=_deadline(), redis=FakeRedis())
    assert rt.single_flight("k1", store.exists, store.make, deadline=_deadline(), redis=FakeRedis())
    assert store.checked == 1
    assert store.made == 0


def test_missing_object_is_made_once_then_memoised():
    store = FakeStore()
    redis = FakeRedis()
    assert rt.single_flight("k2", store.exists, store.make, deadline=_deadline(), redis=redis)
    assert rt.single_flight("k2", store.exists, store.make, deadline=_deadline(), redis=redis)
    assert store.made == 1
    assert store.checked == 1
    assert redis.taken == 1 and redis.released == 1
    assert redis.names == ["image-rendition:k2"]


def test_concurrent_callers_in_one_process_make_it_once():
    store = FakeStore(delay=0.3)
    results = []

    def ask():
        results.append(
            rt.single_flight("k3", store.exists, store.make, deadline=_deadline(), redis=FakeRedis())
        )

    threads = [threading.Thread(target=ask) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [True] * 8
    assert store.made == 1


def test_lock_held_by_another_process_waits_then_sees_the_object():
    store = FakeStore()
    redis = FakeRedis(held_by_other=True)

    def other_process_finishes():
        time.sleep(0.4)
        store.present = True
        redis.held_by_other = False

    threading.Thread(target=other_process_finishes).start()
    assert rt.single_flight("k4", store.exists, store.make, deadline=_deadline(), redis=redis)
    assert store.made == 0


def test_lock_held_by_another_process_past_the_budget_returns_false_without_making():
    store = FakeStore()
    redis = FakeRedis(held_by_other=True)
    started = time.monotonic()
    assert not rt.single_flight("k5", store.exists, store.make, deadline=_deadline(0.5), redis=redis)
    assert time.monotonic() - started < 1.5
    assert store.made == 0


def test_redis_down_still_makes_the_object():
    store = FakeStore()
    assert rt.single_flight("k6", store.exists, store.make, deadline=_deadline(), redis=FakeRedis(down=True))
    assert store.made == 1


def test_no_redis_configured_still_makes_the_object():
    store = FakeStore()
    assert rt.single_flight("k6b", store.exists, store.make, deadline=_deadline(), redis=None)
    assert store.made == 1


def test_slow_generation_returns_false_on_time_and_finishes_in_the_background():
    store = FakeStore(delay=1.0)
    started = time.monotonic()
    assert not rt.single_flight("k7", store.exists, store.make, deadline=_deadline(0.3), redis=FakeRedis())
    assert time.monotonic() - started < 0.9
    time.sleep(1.2)
    assert store.made == 1
    # Finished in the background: the next ask is a memo hit, no second generation.
    assert rt.single_flight("k7", store.exists, store.make, deadline=_deadline(), redis=FakeRedis())
    assert store.made == 1


def test_failed_generation_is_memoised_as_a_miss_and_not_retried():
    store = FakeStore(fail=True)
    assert not rt.single_flight("k8", store.exists, store.make, deadline=_deadline(), redis=FakeRedis())
    assert not rt.single_flight("k8", store.exists, store.make, deadline=_deadline(), redis=FakeRedis())
    assert store.made == 1


def test_generation_that_raises_is_a_miss_and_releases_everything():
    redis = FakeRedis()

    def boom():
        raise RuntimeError("decode failed")

    assert not rt.single_flight("k9", lambda: False, boom, deadline=_deadline(), redis=redis)
    assert redis.released == 1
    # Nothing left in flight: a later caller is answered from the miss memo at once.
    started = time.monotonic()
    assert not rt.single_flight("k9", lambda: False, boom, deadline=_deadline(), redis=redis)
    assert time.monotonic() - started < 0.2


def test_forget_drops_both_memos():
    store = FakeStore(fail=True)
    assert not rt.single_flight("k10", store.exists, store.make, deadline=_deadline(), redis=None)
    rt.forget_rendition("k10")
    store.fail = False
    assert rt.single_flight("k10", store.exists, store.make, deadline=_deadline(), redis=None)
    assert store.made == 2


# --------------------------------------------------------------------------- Cache-Control


class RecordingClient:
    def __init__(self):
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)


def _r2():
    from app.services.r2_service import R2Service

    svc = R2Service.__new__(R2Service)
    svc.client = RecordingClient()
    svc.bucket_name = "bucket"
    svc.get_signed_url = lambda key, expires_in=3600: f"https://cdn.test/{key}"
    return svc, svc.client


def _s3():
    from app.services.s3_service import S3Service

    svc = S3Service.__new__(S3Service)
    svc.s3_client = RecordingClient()
    svc.bucket_name = "bucket"

    class Signer:
        def generate_url(self, key, expires_in=3600):
            return f"https://cdn.test/{key}"

    svc._cloudfront_signer = Signer()
    return svc, svc.s3_client


@pytest.mark.parametrize("make", [_r2, _s3])
def test_upload_file_sends_cache_control_when_given(make):
    svc, client = make()
    svc.upload_file(
        file_content=b"x",
        file_path="a/b.jpg.medium.jpg",
        content_type="image/jpeg",
        cache_control=rt.RENDITION_CACHE_CONTROL,
    )
    assert client.calls[-1]["CacheControl"] == "public, max-age=31536000, immutable"
    assert client.calls[-1]["ContentType"] == "image/jpeg"


@pytest.mark.parametrize("make", [_r2, _s3])
def test_upload_file_without_cache_control_is_unchanged(make):
    svc, client = make()
    svc.upload_file(file_content=b"x", file_path="a/b.jpg", content_type="image/jpeg")
    assert "CacheControl" not in client.calls[-1]


# --------------------------------------------------------------------------- overwrites (AC-9)


def test_promotion_upload_key_is_unique_per_attachment():
    from app.api.v1.resources.attachments import new_upload_storage_key

    first = new_upload_storage_key("promotion", "promotion", "P1", "A1", "flyer.jpg")
    second = new_upload_storage_key("promotion", "promotion", "P1", "A2", "flyer.jpg")
    assert first == "promotion/P1/A1/flyer.jpg"
    assert second == "promotion/P1/A2/flyer.jpg"


def test_generic_upload_key_is_unchanged():
    from app.api.v1.resources.attachments import new_upload_storage_key

    assert new_upload_storage_key("product", "product", "E1", "A1", "x.png") == "product/A1/x.png"
    # No entity id: a promotion upload falls through to the generic shape, as before.
    assert new_upload_storage_key("promotion", "promotion", None, "A1", "x.png") == "promotion/A1/x.png"
