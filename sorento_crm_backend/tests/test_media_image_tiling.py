"""Panel tiling for the chatbot media image lane.

The real fixture is the promo flyer the split exists for: three product panels
in one 841x317 frame, whose per-panel product codes sit at 4-5 px.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest
from PIL import Image

from app.services.llm_provider import ImagePart
from app.services.media_extract.tiling import (
    MAX_SPLITS,
    OVERLAP_FRACTION,
    split_count,
    split_image_part,
)

FIXTURES = Path(__file__).parent / "fixtures"
THREE_PANEL_FLYER = FIXTURES / "promo_flyer_three_panel.png"


def _part(image: Image.Image, fmt: str = "PNG") -> ImagePart:
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    mime = "image/jpeg" if fmt == "JPEG" else "image/png"
    return ImagePart(mime=mime, data_b64=base64.b64encode(buf.getvalue()).decode())


def _decode(part: ImagePart) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(part.data_b64)))


# ----- split_count: the derived count, not a fixed 3 ------------------------


@pytest.mark.parametrize(
    "width,height,expected",
    [
        (841, 317, 3),    # the three-panel promo flyer: ratio 2.65
        (455, 580, 1),    # single-product portrait flyer: ratio 1.27, left alone
        (1000, 1000, 1),  # square
        (600, 400, 1),    # an ordinary 3:2 photo of one item is left alone
        (1024, 768, 1),   # 4:3, likewise
        (4000, 500, MAX_SPLITS),  # panorama is capped, not ratio 8
    ],
)
def test_split_count_is_derived_from_aspect_ratio(width, height, expected):
    assert split_count(width, height) == expected


def test_the_threshold_is_the_multi_panel_shape_not_an_ordinary_photo():
    """A lone product must not pay for crops; a panel sheet must get them."""
    assert split_count(1199, 600) == 1  # ratio 1.998
    assert split_count(1200, 600) == 2  # ratio 2.0 exactly


def test_a_tiny_frame_is_never_split():
    """Crops of a frame this small carry no more detail than the whole."""
    assert split_count(600, 150) == 1


# ----- split_image_part -----------------------------------------------------


def test_three_panel_flyer_splits_into_three_crops():
    part = _part(Image.open(THREE_PANEL_FLYER))
    crops = split_image_part(part)
    assert len(crops) == 3


def test_crops_overlap_so_a_code_on_a_seam_survives_whole():
    source = Image.open(THREE_PANEL_FLYER)
    crops = [_decode(c) for c in split_image_part(_part(source))]

    # Every crop keeps full height: the split is along the long (horizontal) axis.
    assert {c.height for c in crops} == {source.height}

    # Overlap means the widths sum to MORE than the source width.
    total = sum(c.width for c in crops)
    assert total > source.width
    plain_step = source.width / 3
    assert total == pytest.approx(source.width + 4 * plain_step * OVERLAP_FRACTION, abs=4)


def test_a_portrait_single_product_flyer_is_passed_through_untouched():
    part = _part(Image.new("RGB", (455, 580), "white"))
    crops = split_image_part(part)
    assert crops == [part]


def test_a_tall_frame_splits_along_the_vertical_axis():
    source = Image.new("RGB", (300, 1200), "white")
    crops = [_decode(c) for c in split_image_part(_part(source))]
    assert len(crops) == 4  # ratio 4
    assert {c.width for c in crops} == {300}


def test_jpeg_stays_jpeg_and_png_stays_png():
    jpeg_crops = split_image_part(_part(Image.new("RGB", (841, 317), "white"), fmt="JPEG"))
    assert {c.mime for c in jpeg_crops} == {"image/jpeg"}

    png_crops = split_image_part(_part(Image.new("RGB", (841, 317), "white")))
    assert {c.mime for c in png_crops} == {"image/png"}


def test_rgba_png_survives_a_jpeg_source_mime():
    """A JPEG mime on RGBA pixels must not raise - it is converted, not dropped."""
    part = ImagePart(
        mime="image/jpeg",
        data_b64=_part(Image.new("RGBA", (841, 317), (255, 255, 255, 255))).data_b64,
    )
    crops = split_image_part(part)
    assert len(crops) == 3


def test_undecodable_bytes_are_sent_whole_rather_than_failing_the_job():
    part = ImagePart(mime="image/png", data_b64=base64.b64encode(b"not an image").decode())
    assert split_image_part(part) == [part]


# ----- the wiring: crops ride the SAME call, not one call each ---------------


def _run_image_lane(monkeypatch, image_bytes: bytes, mime: str):
    """Drive `_extract_image` with the provider and the usage log stubbed out.

    Neither stub hides the thing under test: the split happens between
    `_render_files` and the provider call, and what is asserted is the `images`
    kwarg the provider actually received.
    """
    import json
    from types import SimpleNamespace

    from app.services.llm_provider import ChatResult
    from app.services.media_extract import service as service_module
    from app.services.media_extract.service import MediaExtractService, MediaJobInput

    monkeypatch.setattr(
        service_module, "fetch_media_bytes", lambda url: (image_bytes, mime)
    )

    seen: dict = {}

    class _StubProvider:
        def chat(self, **kwargs):
            seen.update(kwargs)
            return ChatResult(
                content=json.dumps(
                    {
                        "image_kind": "label",
                        "entities": [],
                        "attributes": [],
                        "conflicts": [],
                        "needs_clarification": False,
                        "truncated": False,
                        "notes": None,
                    }
                ),
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            )

    monkeypatch.setattr(
        MediaExtractService,
        "_resolve_image_provider",
        lambda self, tier, settings: (_StubProvider(), "gemini", "gemini-2.5-flash"),
    )
    monkeypatch.setattr(MediaExtractService, "_log_usage", lambda self, *a, **k: None)

    svc = MediaExtractService(db=None)  # type: ignore[arg-type]
    job = MediaJobInput(
        job_id="zzt-tiling",
        modality="image",
        tier="standard",
        media_url="https://cdn.respond.io/flyer.png",
        mime_type=mime,
        caption=None,
        usage_id=None,
    )
    svc._extract_image(job, SimpleNamespace(max_entities=10))
    return seen


def test_the_three_panel_flyer_reaches_the_provider_as_three_images_in_one_call(
    monkeypatch,
):
    seen = _run_image_lane(monkeypatch, THREE_PANEL_FLYER.read_bytes(), "image/png")
    assert len(seen["images"]) == 3


def test_a_single_product_flyer_still_reaches_the_provider_as_one_image(monkeypatch):
    buf = io.BytesIO()
    Image.new("RGB", (455, 580), "white").save(buf, format="PNG")
    seen = _run_image_lane(monkeypatch, buf.getvalue(), "image/png")
    assert len(seen["images"]) == 1
