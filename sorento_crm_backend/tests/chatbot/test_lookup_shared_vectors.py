"""SPAN-PASS-PROD: one lookup warm per container. The background warm (`_vector_embedder.fill`) shares its vectors
through a per-model file in `CHATBOT_LOOKUP_VECTOR_DIR`, serialised by a file lock. Contract:
documentation/plans/chatbot/span-pass-prod-acceptance-criteria.md (AC-1..AC-11). A second process is simulated by
clearing the module cache."""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
import uuid

import numpy as np
import pytest

import app.main  # noqa: F401  isort:skip
from app.services.chatbot.head import lookup_lists as ll
from tests.chatbot.test_semantic_bridge import R

LOGGER = "app.services.chatbot.head.lookup_lists"


class Fake:
    """request(chunk): records every requested text, returns deterministic non-zero dim-8 vectors."""

    def __init__(self, delay=0.0, fail_on_call=None, forbid=False, dim=8):
        self.dim = dim
        self.texts: list[str] = []
        self.calls = 0
        self.delay = delay
        self.fail_on_call = fail_on_call
        self.forbid = forbid
        self._lock = threading.Lock()

    def __call__(self, chunk):
        with self._lock:
            self.calls += 1
            n = self.calls
            self.texts.extend(chunk)
        assert not self.forbid, f"unexpected provider request for {chunk}"
        if self.delay:
            time.sleep(self.delay)
        if self.fail_on_call == n:
            raise RuntimeError("zz provider down")
        return [(vec(t) * 2)[: self.dim] for t in chunk]


def vec(text):
    d = hashlib.sha256(text.encode()).digest()[:8]
    return [(b + 1) / 256.0 for b in d]


def model(tag="m"):
    return "zzmodel" + tag + uuid.uuid4().hex[:8]


def texts(n, prefix="zz span"):
    return [f"{prefix} {i}" for i in range(n)]


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    d = tmp_path / "vectors"
    d.mkdir()
    monkeypatch.setenv("CHATBOT_LOOKUP_VECTOR_DIR", str(d))
    monkeypatch.setattr(ll, "_cache", {})
    monkeypatch.setattr(ll, "_matrices", {})
    monkeypatch.setattr(ll, "_pieces", {})
    monkeypatch.setattr(ll, "_warm_lock", threading.Lock())
    monkeypatch.setattr(ll, "_sleep", lambda s: None, raising=False)
    monkeypatch.setattr(ll, "_jitter", lambda: 0.0, raising=False)
    return d


def new_process():
    """A second worker process: nothing cached in memory."""
    ll._cache.clear()
    ll._matrices.clear()
    ll._pieces.clear()


def files(d, name=None):
    return [p for p in d.iterdir() if p.is_file() and (name is None or name in p.name)]


def snapshot(d):
    return {p.name: p.read_bytes() for p in files(d)}


# ---- AC-1
def test_ac1_second_process_loads_file_sends_nothing(env):
    m, ts = model(), texts(5)
    first = Fake()
    ll._vector_embedder(m, first, 2).fill(ts)
    assert sorted(first.texts) == sorted(ts)
    assert files(env, m), "the first warm wrote no shared file"
    new_process()
    second = Fake(forbid=True)
    emb = ll._vector_embedder(m, second, 2)
    emb.fill(ts)
    assert second.calls == 0
    assert emb.is_cached(ts)


def test_ac1_only_texts_the_file_lacks_are_sent(env):
    m = model()
    ll._vector_embedder(m, Fake(), 2).fill(texts(3))
    new_process()
    second = Fake()
    ll._vector_embedder(m, second, 2).fill(texts(5))
    assert sorted(second.texts) == sorted(texts(5)[3:]), second.texts


# ---- AC-2
def test_ac2_concurrent_warms_send_each_text_once(env):
    m, ts = model(), texts(6)
    fake = Fake(delay=0.3)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def run():
        try:
            emb = ll._vector_embedder(m, fake, len(ts))
            barrier.wait(5)
            emb.fill(ts)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run, daemon=True) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    assert not errors, errors
    assert len(fake.texts) == len(ts), f"{len(fake.texts)} texts requested for {len(ts)} (sent twice without a lock)"


# ---- AC-3
def test_ac3_file_is_written_by_atomic_rename(env, monkeypatch):
    m = model()
    renames: list[str] = []
    real_replace, real_rename = os.replace, os.rename

    def spy_replace(src, dst, *a, **kw):
        renames.append(str(dst))
        return real_replace(src, dst, *a, **kw)

    def spy_rename(src, dst, *a, **kw):
        renames.append(str(dst))
        return real_rename(src, dst, *a, **kw)

    monkeypatch.setattr(os, "replace", spy_replace)
    monkeypatch.setattr(os, "rename", spy_rename)
    ll._vector_embedder(m, Fake(), 2).fill(texts(4))
    assert any(m in r for r in renames), renames
    assert not [p for p in files(env) if "tmp" in p.name.lower()], files(env)


def test_ac3_merge_keeps_the_files_other_vectors(env):
    m = model()
    a, b = texts(3, "zz alpha"), texts(3, "zz beta")
    ll._vector_embedder(m, Fake(), 2).fill(a)
    new_process()
    ll._vector_embedder(m, Fake(), 2).fill(b)
    new_process()
    both = Fake(forbid=True)
    ll._vector_embedder(m, both, 2).fill(a + b)
    assert both.calls == 0


def test_ac3_a_warm_that_embeds_nothing_does_not_rewrite(env):
    m, ts = model(), texts(4)
    ll._vector_embedder(m, Fake(), 2).fill(ts)
    (path,) = [p for p in files(env, m) if p.stat().st_size > 0][:1]
    before = os.stat(path)
    new_process()
    ll._vector_embedder(m, Fake(forbid=True), 2).fill(ts)
    after = os.stat(path)
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns), "the file was rewritten"


# ---- AC-4
def test_ac4_failed_warm_keeps_stored_chunks_and_releases_lock(env):
    m, ts = model(), texts(4)
    failing = Fake(fail_on_call=2)
    with pytest.raises(RuntimeError):
        ll._vector_embedder(m, failing, 2).fill(ts)
    assert files(env, m), "the failed warm did not write the chunk it stored"
    new_process()
    nxt = Fake()
    done: list[bool] = []

    def run():
        ll._vector_embedder(m, nxt, 2).fill(ts)
        done.append(True)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(10)
    assert done, "the next warm hung: the lock was not released after the error"
    assert sorted(nxt.texts) == sorted(ts[2:]), nxt.texts


# ---- AC-5
def test_ac5_file_is_per_model_and_keeps_no_text_in_clear(env):
    a, b, ts = model("a"), model("b"), texts(3, "zz secret span")
    ll._vector_embedder(a, Fake(), 2).fill(ts)
    assert files(env, a), "no file for model a"
    assert not files(env, b)
    new_process()
    fb = Fake()
    ll._vector_embedder(b, fb, 2).fill(ts)
    assert sorted(fb.texts) == sorted(ts), "model b read model a vectors"
    assert files(env, b)
    new_process()
    fa = Fake(forbid=True)
    ll._vector_embedder(a, fa, 2).fill(ts)
    assert fa.calls == 0
    for p in files(env):
        blob = p.read_bytes()
        for t in ts:
            assert t.encode() not in blob, f"{t!r} in clear in {p.name}"


# ---- AC-6
def test_ac6_file_vectors_are_the_stored_unit_float32_vectors(env):
    m, ts = model(), texts(4)
    first = ll._vector_embedder(m, Fake(), 2)
    first.fill(ts)
    expected = {t: np.array(ll._cache[ll._key(t, m)]) for t in ts}
    scores_before = first.matrix(ts) @ first.matrix(ts)[0]
    new_process()
    second = ll._vector_embedder(m, Fake(forbid=True), 2)
    second.fill(ts)
    for t in ts:
        got = ll._cache[ll._key(t, m)]
        assert got.dtype == np.float32
        assert np.allclose(got, expected[t], atol=1e-6)
        assert abs(float(np.linalg.norm(got)) - 1.0) < 1e-5
    scores_after = second.matrix(ts) @ second.matrix(ts)[0]
    assert np.allclose(scores_before, scores_after, atol=1e-6)


# ---- AC-7
def test_ac7_corrupt_file_warns_embeds_everything_and_is_rewritten(env, caplog):
    m, ts = model(), texts(4)
    ll._vector_embedder(m, Fake(), 2).fill(ts)
    victims = files(env, m)
    assert victims, "no shared file was written"
    for p in victims:
        p.write_bytes(b"\x00garbage\xff not a vector file")
    new_process()
    again = Fake()
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        ll._vector_embedder(m, again, 2).fill(ts)
    assert sorted(again.texts) == sorted(ts)
    assert any(r.levelno == logging.WARNING for r in caplog.records), caplog.records
    new_process()
    third = Fake(forbid=True)
    ll._vector_embedder(m, third, 2).fill(ts)
    assert third.calls == 0


def test_ac7_unusable_directory_warns_and_the_warm_goes_on(env, tmp_path, monkeypatch, caplog):
    blocker = tmp_path / "afile"
    blocker.write_text("x")
    monkeypatch.setenv("CHATBOT_LOOKUP_VECTOR_DIR", str(blocker / "sub"))
    m, ts = model(), texts(3)
    fake = Fake()
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        emb = ll._vector_embedder(m, fake, 2)
        emb.fill(ts)
    assert sorted(fake.texts) == sorted(ts)
    assert emb.is_cached(ts)
    assert any(r.levelno == logging.WARNING for r in caplog.records), caplog.records


def test_ac7_file_of_another_width_is_ignored(env, caplog):
    m, ts = model(), texts(4)
    ll._vector_embedder(m, Fake(dim=4), 2).fill(ts)
    assert files(env, m)
    new_process()
    pre = np.ones(8, dtype=np.float32) / np.sqrt(8)
    ll._cache[ll._key("zz pre-stored", m)] = pre
    fake = Fake(dim=8)
    emb = ll._vector_embedder(m, fake, 2)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        emb.fill(ts)
    assert sorted(fake.texts) == sorted(ts), "the other-width file vectors were used"
    for t in ts:
        assert ll._cache[ll._key(t, m)].shape == (8,)
    assert emb.matrix(ts).shape == (len(ts), 8)
    assert any(r.levelno == logging.WARNING for r in caplog.records), caplog.records
    new_process()
    again = Fake(dim=8, forbid=True)
    ll._vector_embedder(m, again, 2).fill(ts)
    assert again.calls == 0


# ---- AC-8
@pytest.mark.parametrize("off", ["off", "0", "false", "no", "OFF", "False"])
def test_ac8_off_makes_no_file_and_reads_none(env, tmp_path, monkeypatch, off):
    m, ts = model(), texts(3)
    ll._vector_embedder(m, Fake(), 2).fill(ts)
    assert files(env, m), "with the dir set, a warm writes the shared file"
    before = snapshot(env)
    new_process()
    monkeypatch.setenv("CHATBOT_LOOKUP_VECTOR_DIR", off)
    fake = Fake()
    ll._vector_embedder(m, fake, 2).fill(ts)
    assert sorted(fake.texts) == sorted(ts), "off must not read the file"
    assert snapshot(env) == before
    assert not (tmp_path / off).exists() and not os.path.exists(off)


def test_ac8_default_dir_is_the_system_temp_dir(env, tmp_path, monkeypatch):
    import tempfile

    other = tmp_path / "systmp"
    other.mkdir()
    monkeypatch.delenv("CHATBOT_LOOKUP_VECTOR_DIR", raising=False)
    monkeypatch.setattr(tempfile, "tempdir", str(other))
    m = model()
    ll._vector_embedder(m, Fake(), 2).fill(texts(2))
    assert files(other, m)


# ---- AC-9
def test_ac9_over_cap_merge_writes_only_the_asked_texts(env, monkeypatch):
    monkeypatch.setattr(ll, "_CACHE_CAP", 5)
    m = model()
    a, b = texts(3, "zz alpha"), texts(4, "zz beta")
    ll._vector_embedder(m, Fake(), 2).fill(a)
    assert files(env, m)
    new_process()
    ll._vector_embedder(m, Fake(), 2).fill(b)  # 3 + 4 > 5: only b is kept
    new_process()
    fb = Fake()
    ll._vector_embedder(m, fb, 2).fill(b)
    assert fb.calls == 0, "this warm's own texts must be in the file"
    new_process()
    fa = Fake()
    ll._vector_embedder(m, fa, 2).fill(a)
    assert sorted(fa.texts) == sorted(a), "the over-cap merge kept the old texts"


# ---- AC-10 (passes today: the turn path never touches a file; it guards the future)
def test_ac10_embed_and_pieces_never_read_or_write_the_file(env):
    m, ts = model(), texts(3)
    ll._vector_embedder(m, Fake(), 2).fill(ts)
    before = snapshot(env)
    new_process()
    fake = Fake()
    emb = ll._vector_embedder(m, fake, 2)
    emb(ts)
    assert sorted(fake.texts) == sorted(ts), "embed() read the shared file"
    new_process()
    fp = Fake()
    ll._vector_embedder(m, fp, 2).pieces(ts)
    assert sorted(fp.texts) == sorted(ts), "pieces() read the shared file"
    assert snapshot(env) == before, "the turn path wrote the shared file"


def test_ac10_turn_path_creates_no_file_when_none_exists(env):
    m, ts = model(), texts(3)
    emb = ll._vector_embedder(m, Fake(), 2)
    emb(ts)
    emb.pieces(["zz piece"])
    assert not files(env)


# ---- AC-11
def test_ac11_warm_log_says_how_many_came_from_the_shared_file(env, caplog):
    m = model()
    rows = [R("customer", f"c{i}", f"zz cust {i}") for i in range(5)]
    n = len(ll.row_texts(rows))

    def run_warm(emb):
        with caplog.at_level(logging.INFO, logger=LOGGER):
            ll.warm(rows, emb)
            for t in threading.enumerate():
                if t.name == "lookup-lists-warm":
                    t.join(10)

    run_warm(ll._vector_embedder(m, Fake(), 2))
    new_process()
    caplog.clear()
    run_warm(ll._vector_embedder(m, Fake(forbid=True), 2))
    lines = [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno == logging.INFO]
    assert any(f"({n} from the shared file)" in line for line in lines), lines
