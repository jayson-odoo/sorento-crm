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
    assert client.calls[-1]["CacheControl"] == "public, max-age=31536000, s-maxage=86400, immutable"
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


# --------------------------------------------------------------------------- one resize routine (AC-1)

#: Every Image.open outside the rendition service, and why it is not a resize of a stored image.
#: A new entry needs a reason as good as these; a new resize goes through `downscale` instead.
_IMAGE_OPEN_ALLOWED = {
    "app/services/image_normalizer.py": "CMYK detection / RGB conversion at upload; no resize",
    "app/services/dealer_kit/catalog_photos.py": "crops artwork out of a catalogue PDF; dhash",
    "app/services/dealer_kit/flyer_extraction.py": "crops artwork out of a flyer PDF; no resize",
    "app/services/project_spec_sheet_service.py": "reads a picture's size to decide its print copy",
}


def test_image_open_lives_only_in_the_rendition_service():
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    for path in sorted((root / "app").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel == "app/services/image_thumbnailer.py" or rel in _IMAGE_OPEN_ALLOWED:
            continue
        if re.search(r"\bImage\.open\(", path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == [], (
        f"{offenders}: resize a stored image with image_thumbnailer.downscale, or add the module "
        "to _IMAGE_OPEN_ALLOWED with the reason it is not a resize"
    )


def test_every_upload_path_writes_both_renditions():
    """The upload paths call `store_thumbnail`, which IS `store_renditions` (thumb + medium)."""
    import pathlib

    assert rt.store_thumbnail is rt.store_renditions
    root = pathlib.Path(__file__).resolve().parent.parent
    sites = [
        "app/api/v1/resources/attachments.py",
        "app/services/entity_attachment_service.py",
        "app/services/catalogue_photo_service.py",
        "app/services/form_comment_service.py",
        "app/services/dealer_kit/asset_service.py",
        "app/tasks/import_tasks.py",
        "app/api/v1/public/portal.py",
        "app/services/product_image_service.py",
        "app/services/scm/shipment_line_photos.py",
        "app/services/so_line_attachments.py",
        "app/services/accessory_service.py",
    ]
    for rel in sites:
        text = (root / rel).read_text(encoding="utf-8")
        assert "store_thumbnail" in text or "store_renditions" in text, rel
        assert "image_thumbnailer import" in text, rel


# --------------------------------------------------------------------------- store_renditions (AC-2, AC-3)


class Bucket:
    def __init__(self, fail_on=None):
        self.objects = {}
        self.headers = {}
        self.downloads = []
        self.exists_calls = 0
        self.fail_on = fail_on

    def upload_file(self, file_content, file_path, content_type=None, cache_control=None, **_kw):
        if self.fail_on and file_path.endswith(self.fail_on):
            raise RuntimeError("storage down")
        self.objects[file_path] = file_content
        self.headers[file_path] = (content_type, cache_control)
        return file_path, file_path

    def download_file(self, key):
        self.downloads.append(key)
        return self.objects[key]

    def file_exists(self, key):
        self.exists_calls += 1
        return key in self.objects


def _photo(size=(3000, 2000), mode="RGB", fmt="JPEG"):
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new(mode, size, (10, 120, 200) if mode == "RGB" else (10, 120, 200, 0)).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def cdn(monkeypatch):
    from app.services import storage_router

    monkeypatch.setattr(storage_router, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}")


def test_store_renditions_writes_thumb_and_medium_from_one_decode(cdn, monkeypatch):
    import io

    from PIL import Image

    original = _photo()
    decoded = []
    real = rt.downscale

    def spy(raw, *a, **k):
        decoded.append(raw is original)
        return real(raw, *a, **k)

    monkeypatch.setattr(rt, "downscale", spy)
    bucket = Bucket()
    url = rt.store_renditions(bucket, "r2", "p/a.jpg", original, "image/jpeg")

    assert url == "https://cdn.test/p/a.jpg.thumb.jpg"
    assert decoded.count(True) == 1  # the original is decoded once; the thumb comes from the medium
    for key, edge in (("p/a.jpg.thumb.jpg", 320), ("p/a.jpg.medium.jpg", 1024)):
        assert bucket.headers[key] == ("image/jpeg", "public, max-age=31536000, s-maxage=86400, immutable")
        with Image.open(io.BytesIO(bucket.objects[key])) as im:
            assert max(im.size) == edge


def test_store_renditions_flattens_transparency_onto_white(cdn):
    import io

    from PIL import Image

    bucket = Bucket()
    rt.store_renditions(bucket, "r2", "p/cut.png", _photo((800, 800), "RGBA", "PNG"), "image/png")
    with Image.open(io.BytesIO(bucket.objects["p/cut.png.medium.jpg"])) as im:
        assert im.convert("RGB").getpixel((5, 5)) == (255, 255, 255)


def test_store_renditions_never_fails_the_upload(cdn):
    assert rt.store_renditions(Bucket(), "r2", "p/a.pdf", b"%PDF-1.4", "application/pdf") is None
    assert rt.store_renditions(Bucket(), "r2", "p/b.jpg", b"not an image", "image/jpeg") is None
    # A failed medium upload still leaves the thumb.
    bucket = Bucket(fail_on=".medium.jpg")
    assert rt.store_renditions(bucket, "r2", "p/c.jpg", _photo(), "image/jpeg")
    assert "p/c.jpg.thumb.jpg" in bucket.objects and "p/c.jpg.medium.jpg" not in bucket.objects


# --------------------------------------------------------------------------- rendition_urls (AC-4, AC-7, AC-8)


class _Row:
    def __init__(self, id, file_path, thumbnail_path=None, mime="image/jpeg"):
        self.id = id
        self.file_path = file_path
        self.thumbnail_path = thumbnail_path
        self.storage_provider = "r2"
        self.mime_type = mime


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_a):
        return self

    def all(self):
        return self.rows


class _Db:
    def __init__(self, rows):
        self.rows = rows

    def query(self, _model):
        return _Query(self.rows)


@pytest.fixture
def storage(monkeypatch):
    from app.services import storage_router

    bucket = Bucket()
    signed = []

    def sign(key, *, provider=None, expires_in=3600, strict=False):
        signed.append(key)
        return f"https://signed.test/{key}"

    monkeypatch.setattr(storage_router, "get_backend", lambda provider=None: bucket)
    monkeypatch.setattr(storage_router, "resolve_signed_url", sign)
    monkeypatch.setattr(rt, "_default_redis", lambda: None)
    return bucket, signed


def test_a_missing_medium_is_made_once_then_served_without_touching_storage(storage):
    bucket, signed = storage
    bucket.objects["p/a.jpg"] = _photo()
    db = _Db([_Row("A", "https://cdn.test/p/a.jpg")])
    released = []

    out = rt.rendition_urls(db, ["A"], "medium", release=lambda: released.append(1))
    assert out == {"A": "https://signed.test/p/a.jpg.medium.jpg"}
    assert released == [1]
    assert bucket.downloads == ["p/a.jpg"]
    assert "p/a.jpg.thumb.jpg" in bucket.objects  # both made from the one download

    bucket.downloads.clear()
    calls = bucket.exists_calls
    again = rt.rendition_urls(db, ["A"], "medium")
    assert again == out
    assert bucket.downloads == [] and bucket.exists_calls == calls
    # Never the original.
    assert "p/a.jpg" not in signed


def test_a_stored_thumbnail_is_signed_as_is_and_an_unreadable_file_is_left_out(storage):
    bucket, signed = storage
    bucket.objects["p/bad.jpg"] = b"not an image"
    db = _Db([
        _Row("T", "https://cdn.test/p/t.jpg", thumbnail_path="https://cdn.test/p/t.jpg.thumb.jpg"),
        _Row("B", "https://cdn.test/p/bad.jpg"),
    ])
    out = rt.rendition_urls(db, ["T", "B"], "thumb")
    assert out == {"T": "https://signed.test/p/t.jpg.thumb.jpg"}
    assert bucket.downloads == ["p/bad.jpg"]
    # The failure is remembered: asking again does not read the original again.
    rt.rendition_urls(db, ["B"], "thumb")
    assert bucket.downloads == ["p/bad.jpg"]
    assert "p/bad.jpg" not in signed and "p/t.jpg" not in signed


# --------------------------------------------------------------------------- review round 1


def test_a_big_png_still_gets_its_renditions(cdn):
    """Review B1: a PNG cannot draft-decode, so a 40 MP ceiling left a 42 MP PNG with no thumbnail
    and the grid loading its original. main made that thumbnail; so must this."""
    bucket = Bucket()
    big = _photo((7000, 6000), fmt="PNG")
    assert rt.generate_thumbnail(big, "image/png") is not None
    assert rt.store_renditions(bucket, "r2", "p/big.png", big, "image/png")
    assert {"p/big.png.thumb.jpg", "p/big.png.medium.jpg"} <= set(bucket.objects)


def test_renditions_decode_only_photograph_formats(cdn):
    """Security review: TIFF, PSD, ICO, EPS ... parsers carry most of Pillow's CVE history."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (800, 600), (1, 2, 3)).save(buffer, format="TIFF")
    bucket = Bucket()
    assert rt.store_renditions(bucket, "r2", "p/scan.tif", buffer.getvalue(), "image/tiff") is None
    assert bucket.objects == {}
    assert rt.store_renditions(bucket, "r2", "p/anim.gif", _photo((400, 300), fmt="GIF"), "image/gif")


def test_a_known_rendition_is_not_queued_behind_another_requests_generations(storage, monkeypatch):
    """Review S1: one slow page must not hold up a request whose rendition already exists."""
    import time as _time

    bucket, _signed = storage
    bucket.objects["p/k.jpg"] = _photo((600, 400))
    db_known = _Db([_Row("K", "https://cdn.test/p/k.jpg")])
    assert rt.rendition_urls(db_known, ["K"], "medium")  # now known in this process

    real_submit = rt._waiters.submit

    def blocked(*_a, **_k):
        raise AssertionError("a known rendition must be signed without the waiter pool")

    monkeypatch.setattr(rt._waiters, "submit", blocked)
    started = _time.monotonic()
    assert rt.rendition_urls(db_known, ["K"], "medium") == {"K": "https://signed.test/p/k.jpg.medium.jpg"}
    assert _time.monotonic() - started < 0.5
    monkeypatch.setattr(rt._waiters, "submit", real_submit)


def test_a_lock_held_past_the_budget_is_not_waited_on_again_at_once():
    """Security review nit: a holder that crashed costs one caller its budget, not every caller."""
    store = FakeStore()
    redis = FakeRedis(held_by_other=True)
    assert not rt.single_flight("held", store.exists, store.make, deadline=_deadline(0.3), redis=redis)
    started = time.monotonic()
    assert not rt.single_flight("held", store.exists, store.make, deadline=_deadline(5), redis=redis)
    assert time.monotonic() - started < 0.2
    assert store.made == 0
