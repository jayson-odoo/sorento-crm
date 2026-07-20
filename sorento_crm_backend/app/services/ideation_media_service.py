"""Multi-modal ideation capture — media lookback, selection, snapshot + vision
(DC-1..DC-9; PLAN-ideation-ideate-intent.md Group F / Phase 2f).

The binding problem: WhatsApp is a stream of separate messages and media carries
no intent of its own. Solved **ideate-branch-contained** — no aggregation window
over the live classifier:

- **Lookback (DC-1/2/3):** on the first ideate turn, PULL the contact's recent
  messages from the Respond List Messages API (no park endpoint, no buffer table)
  and surface a numbered menu of recent inbound media for the human to pick from.
- **Selection (DC-7):** the parser extracts reference-positions ('1,3'/'all'/'none');
  this module resolves them against the pending candidates. The human filter means
  a complaint's photo appearing in the menu is simply not picked — no cross-intent
  bookkeeping needed.
- **Snapshot + vision (DC-4/6):** the picked media's bytes are fetched from the
  (expiring) Respond CDN and stored durably via ``storage_router`` (R2/S3); images
  get an OpenAI vision caption. The durable URL + caption go to ``create_idea``.

Every external seam (Respond fetch, durable store, vision) is injected so the turn
service + tests can stub them; the module itself is pure resolution logic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Respond message.type values we treat as attachable media (else it's text /
# template / system and never a capture candidate).
_MEDIA_KINDS = {"image", "video", "file", "audio"}
# message.type == "attachment" carries the real kind under message.attachment.type.
_ATTACHMENT_WRAPPER = "attachment"
_KIND_ICON = {"image": "📷", "video": "🎥", "audio": "🎤", "file": "📄"}

# Lookback bound (DC-2): the last N INBOUND messages; media among them become
# candidates. Kept small so the WhatsApp menu stays short.
LOOKBACK_INBOUND_LIMIT = 10


@dataclass
class MediaCandidate:
    """One recent inbound media message eligible for the capture menu."""

    source_msg_id: str
    kind: str  # image | video | file | audio
    url: str  # Respond CDN url (transient — snapshotted on pick)
    filename: Optional[str] = None
    received_at: Optional[datetime] = None


# ── extraction from a Respond List Messages payload ───────────────────────────


def _ms_to_dt(ts: Any) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(int(ts) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def _is_incoming(item: dict) -> bool:
    return (item.get("traffic") or "").lower() in ("incoming", "inbound", "")


def _media_kind_and_url(msg: dict) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Resolve ``(kind, url, filename)`` from a Respond ``message`` object, tolerant
    of the two shapes seen in the wild: a flat ``type: image`` with an ``image.url``
    sub-object, or ``type: attachment`` with ``attachment: {type, url, ...}``. Returns
    ``(None, None, None)`` for text / template / anything with no media url."""
    mtype = (msg.get("type") or "").lower()
    payload: Any = None
    kind: Optional[str] = None
    if mtype in _MEDIA_KINDS:
        kind = mtype
        payload = msg.get(mtype)
    elif mtype == _ATTACHMENT_WRAPPER:
        att = msg.get("attachment") or {}
        kind = (att.get("type") or "file").lower()
        if kind not in _MEDIA_KINDS:
            kind = "file"
        payload = att
    else:
        return None, None, None

    url = None
    filename = None
    if isinstance(payload, dict):
        url = payload.get("url") or payload.get("link")
        filename = payload.get("filename") or payload.get("name") or payload.get("fileName")
    elif isinstance(payload, str):
        url = payload
    if not url:
        return None, None, None
    return kind, url, filename


def extract_media_candidates(
    list_messages_payload: dict,
    *,
    inbound_limit: int = LOOKBACK_INBOUND_LIMIT,
) -> list[MediaCandidate]:
    """From a Respond List Messages payload, return the media among the last
    ``inbound_limit`` INBOUND messages, newest-first (menu position 1 = most recent).
    Non-media inbound messages still count toward the window but aren't returned
    (DC-2). Outbound/assistant messages are ignored."""
    items = list_messages_payload.get("items")
    if not isinstance(items, list):
        items = list_messages_payload.get("data") if isinstance(list_messages_payload.get("data"), list) else []

    inbound: list[tuple[Optional[datetime], dict]] = []
    for item in items:
        if not isinstance(item, dict) or not _is_incoming(item):
            continue
        statuses = item.get("status") or []
        ts = statuses[0].get("timestamp") if isinstance(statuses, list) and statuses and isinstance(statuses[0], dict) else None
        inbound.append((_ms_to_dt(ts), item))

    # Newest first. ``None`` timestamps sort last (treated as oldest).
    inbound.sort(key=lambda p: (p[0] or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    window = inbound[:inbound_limit]

    candidates: list[MediaCandidate] = []
    for received_at, item in window:
        msg = item.get("message") or {}
        kind, url, filename = _media_kind_and_url(msg)
        if not kind or not url:
            continue
        source_msg_id = str(item.get("messageId") or item.get("channelMessageId") or "").strip()
        if not source_msg_id:
            continue
        candidates.append(
            MediaCandidate(
                source_msg_id=source_msg_id,
                kind=kind,
                url=url,
                filename=filename,
                received_at=received_at,
            )
        )
    return candidates


# ── menu rendering + selection resolution ─────────────────────────────────────


def _relative_time(received_at: Optional[datetime], *, now: Optional[datetime] = None) -> str:
    if received_at is None:
        return "recently"
    now = now or datetime.now(timezone.utc)
    secs = max(0, int((now - received_at).total_seconds()))
    if secs < 60:
        return "just now"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m ago"
    hrs = mins // 60
    if hrs < 24:
        return f"{hrs}h ago"
    return f"{hrs // 24}d ago"


def build_menu_text(candidates: list[MediaCandidate], *, now: Optional[datetime] = None) -> str:
    """The numbered media menu appended to the first reply (DC-8). Type icon +
    filename (if any) + relative time — no thumbnails (WhatsApp text)."""
    lines = []
    for i, c in enumerate(candidates, start=1):
        icon = _KIND_ICON.get(c.kind, "📎")
        label = (c.filename or c.kind).strip()
        lines.append(f"{i}. {icon} {label} ({_relative_time(c.received_at, now=now)})")
    body = "\n".join(lines)
    return (
        f"I also saw {len(candidates)} recent file"
        f"{'s' if len(candidates) != 1 else ''} — which relate to this idea?\n"
        f"{body}\n"
        f"Reply with the numbers (e.g. 1,3), 'all', or 'none'."
    )


def parse_selection(selection: Optional[str], candidates: list[MediaCandidate]) -> list[MediaCandidate]:
    """Resolve a parser-extracted reference-position string to the picked candidates.
    ``all`` → every candidate; ``none``/empty/no digits → []; otherwise the 1-indexed
    positions present in the string (deduped, out-of-range ignored). Deterministic —
    never an LLM call (DC-7)."""
    if not candidates:
        return []
    raw = (selection or "").strip().lower()
    if not raw or "none" in raw:
        return []
    if "all" in raw:
        return list(candidates)
    import re

    picked: list[MediaCandidate] = []
    seen: set[int] = set()
    for tok in re.findall(r"\d+", raw):
        idx = int(tok)
        if 1 <= idx <= len(candidates) and idx not in seen:
            seen.add(idx)
            picked.append(candidates[idx - 1])
    return picked


# ── snapshot + vision (durable capture of the picked media) ───────────────────


@dataclass
class MediaClients:
    """Injected seams so the turn service + tests control I/O. Defaults wire the
    real Respond CDN fetch / storage_router / OpenAI vision."""

    fetch_bytes: Callable[[str], tuple[bytes, Optional[str]]]
    store_bytes: Callable[[bytes, str, Optional[str]], str]
    caption_image: Callable[[bytes, Optional[str]], Optional[str]]


def snapshot_and_caption(
    candidates: list[MediaCandidate], clients: MediaClients
) -> list[dict[str, Any]]:
    """Durably capture each picked candidate → the §5.1 ``attachments[]`` element
    ``{source_msg_id, url, type, filename?, caption?}`` (DC-4/6/9). Per-item failures
    are logged + skipped (never fail the whole turn — D-5 resilience)."""
    out: list[dict[str, Any]] = []
    for c in candidates:
        try:
            data, content_type = clients.fetch_bytes(c.url)
        except Exception:  # noqa: BLE001 — a dead CDN url must not fail the turn
            logger.warning("ideation media fetch failed for msg=%s", c.source_msg_id, exc_info=True)
            continue
        key = _storage_key(c)
        try:
            durable_url = clients.store_bytes(data, key, content_type)
        except Exception:  # noqa: BLE001
            logger.warning("ideation media store failed for msg=%s", c.source_msg_id, exc_info=True)
            continue
        caption: Optional[str] = None
        if c.kind == "image":
            try:
                caption = clients.caption_image(data, content_type)
            except Exception:  # noqa: BLE001 — vision is best-effort (DC-6)
                logger.warning("ideation vision caption failed for msg=%s", c.source_msg_id, exc_info=True)
                caption = None
        element: dict[str, Any] = {
            "source_msg_id": c.source_msg_id,
            "url": durable_url,
            "type": c.kind,
        }
        if c.filename:
            element["filename"] = c.filename
        if caption:
            element["caption"] = caption
        out.append(element)
    return out


def _storage_key(c: MediaCandidate) -> str:
    from app.services.storage_router import sanitize_storage_filename

    name = sanitize_storage_filename(c.filename or f"{c.kind}")
    return f"ideation/attachments/{c.source_msg_id}/{name}"


def fold_captions_into_text(message_text: str, attachments: list[dict[str, Any]]) -> str:
    """Append ``(attached <type>: <caption>)`` notes so create_idea's semantic
    collection/dedup sees the visual content (DC-6/9)."""
    notes = [
        f"(attached {a['type']}: {a['caption']})"
        for a in attachments
        if a.get("caption")
    ]
    if not notes:
        return message_text
    joined = " ".join(notes)
    return f"{message_text}\n{joined}" if message_text else joined


# ── default real seams ────────────────────────────────────────────────────────


def default_clients() -> MediaClients:
    return MediaClients(
        fetch_bytes=_default_fetch_bytes,
        store_bytes=_default_store_bytes,
        caption_image=_default_caption_image,
    )


def _default_fetch_bytes(url: str) -> tuple[bytes, Optional[str]]:
    import httpx

    with httpx.Client(timeout=20, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content, resp.headers.get("content-type")


def _default_store_bytes(data: bytes, key: str, content_type: Optional[str]) -> str:
    from app.services.storage_router import cdn_base_url, default_provider, get_backend

    provider = default_provider()
    backend = get_backend(provider)
    backend.upload_file(data, key, content_type or "application/octet-stream")
    return cdn_base_url(provider, key)


def _default_caption_image(data: bytes, content_type: Optional[str]) -> Optional[str]:
    import base64

    from app.config import settings
    from app.services.llm_provider import ImagePart, OpenAIProvider

    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        return None  # key-gated (DC-6): no key → attach without caption
    provider = OpenAIProvider(api_key=api_key, default_model="gpt-4o-mini")
    image = ImagePart(mime=content_type or "image/jpeg", data_b64=base64.b64encode(data).decode())
    result = provider.chat(
        messages=[
            {
                "role": "user",
                "content": (
                    "This image was attached to a product-improvement idea over WhatsApp. "
                    "Describe what it shows in one concise sentence for the idea record "
                    "(focus on any UI, sketch, screenshot, or defect depicted). No preamble."
                ),
            }
        ],
        images=[image],
        max_tokens=120,
    )
    text = (getattr(result, "content", None) or "").strip()
    return text or None
