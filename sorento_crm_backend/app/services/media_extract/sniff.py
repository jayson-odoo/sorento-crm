"""What the downloaded bytes really are, read from their first bytes.

The media url and its `content-type` are both supplied by someone else, and on
24 Oct 2026 a download that was not an image reached the vision model labelled
`image/jpeg`: the job failed in two seconds with no reason in the trace, or
"completed" with Gemini saying the file looked corrupted. The first bytes are
the only part of the answer this side can check, so the lanes check them before
a provider is called and fail the job with a reason a person can read.
"""
from __future__ import annotations

from typing import Optional

# ISO-BMFF brands (`....ftyp<brand>`) that are still images, not video.
_HEIF_BRANDS = {b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1", b"msf1", b"avif"}
# Brands that are audio-only MP4 (voice notes from iOS arrive as M4A).
_AUDIO_MP4_BRANDS = {b"M4A ", b"M4B ", b"M4P ", b"F4A "}


def _ftyp_brand(head: bytes) -> Optional[bytes]:
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return head[8:12]
    return None


def sniff_mime(data: bytes) -> Optional[str]:
    """The mime type the first bytes show, or None when they match nothing known."""
    head = data[:16]
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    brand = _ftyp_brand(head)
    if brand is not None:
        if brand in _HEIF_BRANDS:
            return "image/avif" if brand == b"avif" else "image/heic"
        if brand in _AUDIO_MP4_BRANDS:
            return "audio/mp4"
        if brand.startswith(b"3g"):
            return "video/3gpp"
        if brand == b"qt  ":
            return "video/quicktime"
        return "video/mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        # Matroska / WebM: the same container carries video and audio-only files.
        return "video/webm"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        # An ID3 tag, or an MPEG audio / AAC ADTS frame sync.
        return "audio/mpeg"
    if head.startswith(b"#!AMR"):
        return "audio/amr"
    if head.startswith(b"fLaC"):
        return "audio/flac"
    return None


def expected_kind(modality: str, declared_mime: Optional[str]) -> str:
    """What the bytes must be for this job: the voice lane wants audio; the image
    lane also reads PDFs and video, so a specific declared mime picks one of the
    three, and none (or a generic one like octet-stream) leaves all three open."""
    if modality == "voice":
        return "audio"
    mime = (declared_mime or "").split(";")[0].strip().lower()
    if mime == "application/pdf":
        return "pdf"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("image/"):
        return "image"
    return "visual"


def matches_kind(sniffed: Optional[str], kind: str) -> bool:
    if sniffed is None:
        return False
    if kind == "pdf":
        return sniffed == "application/pdf"
    if kind == "visual":
        return sniffed == "application/pdf" or sniffed.startswith(("image/", "video/"))
    if kind == "audio":
        # WebM / MP4 voice notes share their container with video.
        return sniffed.startswith("audio/") or sniffed in {"video/webm", "video/mp4", "video/3gpp"}
    return sniffed.startswith(f"{kind}/")


def mismatch_reason(data: bytes, content_type: Optional[str], kind: str) -> str:
    """The job error: which modality was expected and what actually arrived."""
    label = {
        "image": "an image",
        "audio": "an audio file",
        "visual": "an image, pdf or video",
    }.get(kind, f"a {kind}")
    return (
        f"Downloaded file is not {label}: content-type {content_type or 'none'}, "
        f"{len(data)} bytes, first bytes {data[:16].hex()}"
    )
