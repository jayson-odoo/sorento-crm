"""PHOTO-FIRST-LOOKAHEAD: a queued photo is answered before the running text.

Plan `documentation/plans/chatbot/PLAN-photo-first-lookahead.md`, UAC
`photo-first-lookahead-acceptance-criteria.md` (PF-1 .. PF-5). Prod, 25 Oct 18:29: text
"check stock" sent at t0, photo at t0 + 201 ms (WhatsApp sends a photo once it has
uploaded, so a text tapped right after overtakes it). The photo row was queued while the
text turn ran, and the look-ahead only gave way to an EARLIER-sent row, so the text was
answered first. The rule now: a media row already queued goes first, whatever the send
times say; nothing waits for a photo that is not queued yet.

The harness is `test_inbox_queue_order.py`'s (real engine, real drain, recorded POSTs).
"""
from __future__ import annotations

import time

from tests.chatbot.test_inbox_queue_order import (  # noqa: F401 - fixtures used by name
    iq,
    iq_serial,
    media_worker,
    redis_client,
    wait_until,
    world,
)

PHOTO_LAG_SECONDS = 0.201


def _queued(world, contact, mid) -> bool:
    return (world.row_for(contact, mid) or {}).get("status") == "queued"


def _calls(world, *mids) -> list[str]:
    wanted = {str(m) for m in mids}
    return [m for m in world.parse_calls if m in wanted]


def test_photo_sent_201ms_after_the_running_text_is_answered_first(world, media_worker):
    """PF-1, the 18:29 shape: text T at t0 is mid-turn when photo P (t0 + 201 ms) is
    queued. T gives way before it writes anything; P is answered, then T."""
    contact = world.contact(covered=True, media=True)
    base = time.time() - 10
    text_mid = world.message(contact, base, "stock-text")
    photo = world.message(contact, base + PHOTO_LAG_SECONDS, "stock-photo")
    initial_state = world.session_vars(contact)
    seen: dict = {}
    world.parse_hooks[str(photo)] = lambda mid, block: seen.setdefault("state_when_photo_ran", world.session_vars(contact))

    world.gate.clear()
    world.webhook(world.body(contact, text_mid, text_value="check stock (stock-text)"))
    assert world.wait_parse_started(text_mid, timeout=10), "T never started"
    world.webhook(world.body(contact, photo, photo=True))
    assert wait_until(lambda: _queued(world, contact, photo), timeout=5), "P must be queued while T runs"
    world.gate.set()

    posts = world.wait_posts(2, contact, timeout=30)
    t_row = world.row_for(contact, text_mid)
    p_row = world.row_for(contact, photo)
    assert [p["turn_id"] for p in posts] == [p_row["id"], t_row["id"]], (
        f"expected the photo's POST, then the text's; got {world.posted_messages(contact)}"
    )
    assert _calls(world, text_mid, photo) == [str(text_mid), str(photo), str(text_mid)]
    assert seen["state_when_photo_ran"] == initial_state, "T wrote state before giving way"
    assert world.session_writes(t_row["id"]) == 1
    assert p_row["status"] == "done" and t_row["status"] == "done"


def test_photo_queued_after_the_text_committed_keeps_the_normal_order(world, media_worker, monkeypatch):
    """PF-2: once T's look-ahead has passed, a photo queued then does not stop it: T is
    answered, then P, and T runs once."""
    contact = world.contact(covered=True, media=True)
    base = time.time() - 10
    text_mid = world.message(contact, base, "late-text")
    photo = world.message(contact, base + PHOTO_LAG_SECONDS, "late-photo")
    module = iq()
    real_checkpoint = module.checkpoint
    sent = []

    def checkpoint_then_photo(turn_id=None):
        real_checkpoint(turn_id)
        run = module.current_run(turn_id)
        if not sent and run is not None and run.committed and world.message_of_turn(run.turn_id) == str(text_mid):
            sent.append(True)
            world.webhook(world.body(contact, photo, photo=True))

    monkeypatch.setattr(module, "checkpoint", checkpoint_then_photo)

    world.webhook(world.body(contact, text_mid, text_value="check stock (late-text)"))
    posts = world.wait_posts(2, contact, timeout=30)
    assert sent, "the photo was never sent after T committed"
    assert world.posted_messages(contact) == [str(text_mid), str(photo)], [p["turn_id"] for p in posts]
    assert _calls(world, text_mid, photo) == [str(text_mid), str(photo)], "T must not run twice"


def test_two_texts_and_a_photo_the_photo_goes_first_then_the_texts_in_send_order(world, media_worker):
    """PF-3: T1 runs, T2 and then P are queued behind it. P, T1, T2."""
    contact = world.contact(covered=True, media=True)
    base = time.time() - 10
    t1 = world.message(contact, base, "two-t1")
    t2 = world.message(contact, base + 0.1, "two-t2")
    photo = world.message(contact, base + PHOTO_LAG_SECONDS, "two-photo")

    world.gate.clear()
    world.webhook(world.body(contact, t1))
    assert world.wait_parse_started(t1, timeout=10), "T1 never started"
    world.webhook(world.body(contact, t2))
    world.webhook(world.body(contact, photo, photo=True))
    assert wait_until(lambda: _queued(world, contact, t2) and _queued(world, contact, photo), timeout=5)
    world.gate.set()

    world.wait_posts(3, contact, timeout=40)
    assert world.posted_messages(contact) == [str(photo), str(t1), str(t2)]
    assert _calls(world, t1, t2, photo) == [str(t1), str(photo), str(t1), str(t2)]


def test_no_photo_queued_changes_nothing_and_nothing_waits(world):
    """PF-4: T1 runs while a later text T2 is queued: T1, then T2, no yield, no wait."""
    contact = world.contact(covered=True)
    base = time.time() - 10
    t1 = world.message(contact, base, "plain-t1")
    t2 = world.message(contact, base + PHOTO_LAG_SECONDS, "plain-t2")

    world.gate.clear()
    world.webhook(world.body(contact, t1))
    assert world.wait_parse_started(t1, timeout=10), "T1 never started"
    world.webhook(world.body(contact, t2))
    assert wait_until(lambda: _queued(world, contact, t2), timeout=5)
    world.gate.set()

    posts = world.wait_posts(2, contact, timeout=30)
    assert world.posted_messages(contact) == [str(t1), str(t2)]
    assert _calls(world, t1, t2) == [str(t1), str(t2)]
    with world.lock:
        t1_end = max(t for kind, m, t in world.events if kind == "parse_end" and m == str(t1))
    assert posts[0]["t_start"] - t1_end < 1.5, "something waited between T1's parse and its POST"


def test_a_photo_of_another_contact_is_ignored(world, media_worker):
    """PF-5: contact A's running text does not give way to contact B's queued photo."""
    a = world.contact(covered=True, media=True)
    b = world.contact(covered=True, media=True)
    base = time.time() - 10
    text_mid = world.message(a, base, "other-text")
    photo = world.message(b, base + PHOTO_LAG_SECONDS, "other-photo")

    world.gate.clear()
    world.webhook(world.body(a, text_mid))
    assert world.wait_parse_started(text_mid, timeout=10), "A's text never started"
    world.webhook(world.body(b, photo, photo=True))
    assert wait_until(lambda: world.row_for(b, photo), timeout=5)
    world.gate.set()

    world.wait_posts(1, a, timeout=30)
    world.wait_posts(1, b, timeout=30)
    assert world.posted_messages(a) == [str(text_mid)]
    assert _calls(world, text_mid) == [str(text_mid)], "A's text gave way to another contact's photo"


def test_order_key_puts_photo_and_voice_first_and_keeps_send_order_otherwise():
    """The key itself, no database: image, voice (every kind) and an `image/*` file go first;
    a document, a sticker and a text keep their send order."""
    key = iq()._order_key
    for kind, mime in [("image", None), ("audio", None), ("voice", None), ("ptt", None), ("file", "image/png")]:
        assert key(5.0, kind, mime) == (0, 5.0), (kind, mime)
    for kind, mime in [(None, None), ("file", "application/pdf"), ("sticker", "image/webp")]:
        assert key(5.0, kind, mime) == (1, 5.0), (kind, mime)
    assert key(9.0, "image", None) < key(1.0, None, None), "a later photo goes before an earlier text"
