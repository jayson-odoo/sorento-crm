"""Unit tests for the multi-modal capture core (ideation_media_service) - DC-1..DC-9.

Pure resolution logic: candidate extraction from a Respond List Messages payload,
menu rendering, selection parsing, and the snapshot+caption pipeline with injected
seams. No live Respond / storage / OpenAI.
"""
from datetime import datetime, timezone

from app.services.ideation_media_service import (
    MediaCandidate,
    MediaClients,
    build_menu_text,
    extract_media_candidates,
    fold_captions_into_text,
    parse_selection,
    snapshot_and_caption,
)


def _msg(mid, kind, url, *, traffic="incoming", ts=1_721_000_000_000, filename=None, wrap=False):
    if wrap:
        message = {"type": "attachment", "attachment": {"type": kind, "url": url, "filename": filename}}
    elif kind == "text":
        message = {"type": "text", "text": url}
    else:
        message = {"type": kind, kind: {"url": url, "filename": filename}}
    return {"messageId": mid, "traffic": traffic, "status": [{"timestamp": ts}], "message": message}


# ── extraction ────────────────────────────────────────────────────────────────


def test_extract_filters_to_inbound_media_newest_first():
    payload = {
        "items": [
            _msg("m3", "image", "https://c/3.jpg", ts=3000),
            _msg("m2", "text", "just words", ts=2000),
            _msg("m1", "video", "https://c/1.mp4", ts=1000),
            _msg("out", "image", "https://c/x.jpg", traffic="outgoing", ts=2500),
        ]
    }
    cands = extract_media_candidates(payload)
    assert [c.source_msg_id for c in cands] == ["m3", "m1"]  # newest-first, media only, no outbound
    assert cands[0].kind == "image"
    assert cands[1].kind == "video"


def test_extract_handles_attachment_wrapper_shape():
    payload = {"items": [_msg("m1", "file", "https://c/spec.pdf", filename="spec.pdf", wrap=True)]}
    cands = extract_media_candidates(payload)
    assert len(cands) == 1
    assert cands[0].kind == "file"
    assert cands[0].filename == "spec.pdf"


def test_extract_respects_inbound_window():
    # 12 inbound text messages then one older image → image is outside the last-10 window.
    items = [_msg(f"t{i}", "text", "x", ts=10_000 + i) for i in range(12)]
    items.append(_msg("old_img", "image", "https://c/old.jpg", ts=1))
    cands = extract_media_candidates({"items": items}, inbound_limit=10)
    assert cands == []


# ── selection ─────────────────────────────────────────────────────────────────


def _cands(n):
    return [MediaCandidate(source_msg_id=f"m{i}", kind="image", url=f"u{i}") for i in range(1, n + 1)]


def test_parse_selection_positions():
    picked = parse_selection("1,3", _cands(3))
    assert [c.source_msg_id for c in picked] == ["m1", "m3"]


def test_parse_selection_all_and_none():
    assert len(parse_selection("all", _cands(3))) == 3
    assert parse_selection("none", _cands(3)) == []
    assert parse_selection("", _cands(3)) == []


def test_parse_selection_ignores_out_of_range_and_dupes():
    picked = parse_selection("2 and 2 and 9", _cands(3))
    assert [c.source_msg_id for c in picked] == ["m2"]


# ── menu text ─────────────────────────────────────────────────────────────────


def test_build_menu_text_numbered_with_time():
    now = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
    cands = [
        MediaCandidate("m1", "image", "u1", filename="mockup.jpg", received_at=datetime(2026, 7, 20, 11, 58, tzinfo=timezone.utc)),
    ]
    text = build_menu_text(cands, now=now)
    assert "1." in text and "mockup.jpg" in text and "2m ago" in text
    assert "1,3" in text and "none" in text


# ── snapshot + caption ────────────────────────────────────────────────────────


def _clients(caption="a sketch"):
    return MediaClients(
        fetch_bytes=lambda url: (b"rawbytes", "image/jpeg"),
        store_bytes=lambda data, key, ct: f"https://durable.cdn/{key}",
        caption_image=lambda data, ct: caption,
    )


def test_snapshot_builds_attachment_elements():
    cands = [MediaCandidate("m1", "image", "https://respond/1.jpg", filename="a.jpg")]
    atts = snapshot_and_caption(cands, _clients())
    assert len(atts) == 1
    a = atts[0]
    assert a["source_msg_id"] == "m1"
    assert a["type"] == "image"
    assert a["url"].startswith("https://durable.cdn/")
    assert a["filename"] == "a.jpg"
    assert a["caption"] == "a sketch"


def test_snapshot_skips_video_caption():
    cands = [MediaCandidate("m1", "video", "https://respond/1.mp4")]
    atts = snapshot_and_caption(cands, _clients())
    assert atts[0].get("caption") is None


def test_snapshot_skips_item_on_fetch_failure():
    def boom(url):
        raise RuntimeError("dead cdn")

    clients = MediaClients(boom, lambda d, k, c: "x", lambda d, c: None)
    assert snapshot_and_caption([MediaCandidate("m1", "image", "u")], clients) == []


def test_snapshot_degrades_when_vision_fails():
    def vision_boom(data, ct):
        raise RuntimeError("no key")

    clients = MediaClients(
        fetch_bytes=lambda url: (b"x", "image/png"),
        store_bytes=lambda d, k, c: "https://durable/x",
        caption_image=vision_boom,
    )
    atts = snapshot_and_caption([MediaCandidate("m1", "image", "u")], clients)
    assert len(atts) == 1 and atts[0].get("caption") is None  # attached without caption


def test_fold_captions_into_text():
    atts = [{"type": "image", "caption": "a sketch"}, {"type": "file"}]
    assert fold_captions_into_text("my idea", atts) == "my idea\n(attached image: a sketch)"
    assert fold_captions_into_text("only", []) == "only"
