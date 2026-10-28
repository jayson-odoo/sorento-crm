"""Turn one showroom stop's video or photos into a single panorama.

A walkthrough stop is one spot in the showroom. Whoever films it stands there
and turns slowly on the spot (a video), or takes overlapping photos while
turning, or drops in one photo a 360 camera already produced. All three end as
ONE image plus the angle it covers, which is everything the viewer needs to
wrap it around the camera.

**Panoramas, not a reconstructed 3D model.** Photogrammetry or gaussian splats
need a GPU box and COLMAP-class tooling this stack does not run. A panorama per
stop, with stops joined in walking order, is what OpenCV (already a dependency)
can build on the worker, and it is what a customer actually looks at in a
virtual showroom tour.

Pure: bytes in, bytes out, no database and no storage, so the tests drive it
with synthetic frames.
"""
from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass

import cv2
import numpy as np

# A slow full turn is 15 to 30 seconds of video. 24 evenly spaced frames puts
# one every 15 degrees, so neighbours overlap by well over half a phone frame.
MAX_VIDEO_FRAMES = 24
# Every frame is scaled to this before stitching: full 4K frames cost minutes
# of CPU per stop and the viewer cannot show the extra detail on a laptop.
WORK_WIDTH = 1280
# WebGL's guaranteed texture size on the devices dealers carry.
MAX_OUTPUT_WIDTH = 8192
JPEG_QUALITY = 88

# shortcut: assumes a phone main camera (about 68 degrees across the long side);
# a wide or tele lens skews the computed angle. Upgrade by reading EXIF focal
# length or the stitcher's estimated cameras once a stop looks stretched.
PHONE_LONG_SIDE_FOV_DEG = 68.0

# A stitched turn this close to a full circle is treated as one.
FULL_TURN_DEG = 330.0

VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv")

_STITCH_FAILURES = {
    cv2.Stitcher_ERR_NEED_MORE_IMGS: (
        "The photos do not overlap enough to join. Stand in one spot and turn "
        "slowly, so each shot shares about a third with the one before."
    ),
    cv2.Stitcher_ERR_HOMOGRAPHY_EST_FAIL: (
        "The photos could not be lined up. Avoid blank walls and moving people, "
        "and turn on the spot rather than walking."
    ),
    cv2.Stitcher_ERR_CAMERA_PARAMS_ADJUST_FAIL: (
        "The photos could not be lined up. Turn on the spot rather than walking, "
        "and keep the phone at the same height."
    ),
}


class PanoramaError(Exception):
    """A refusal a designer can read and act on."""


@dataclass(frozen=True)
class Panorama:
    jpeg: bytes
    width: int
    height: int
    h_fov_deg: float
    v_fov_deg: float


def is_video(filename: str) -> bool:
    return (filename or "").lower().endswith(VIDEO_EXTENSIONS)


def build_panorama(sources: list[tuple[str, bytes]]) -> Panorama:
    """``sources`` is ``(filename, bytes)`` per uploaded file, in upload order."""
    frames: list[np.ndarray] = []
    for filename, data in sources:
        if is_video(filename):
            frames.extend(_video_frames(filename, data))
        else:
            frames.append(_decode_image(filename, data))

    if not frames:
        raise PanoramaError("There was nothing to build this stop from.")

    if len(frames) == 1:
        image = frames[0]
        height, width = image.shape[:2]
        if abs(width / height - 2.0) < 0.05:
            # A 2:1 photo is what a 360 camera exports: already the full sphere.
            return _encode(image, 360.0, 180.0)
        h_fov, v_fov = frame_fov(width, height)
        return _encode(image, h_fov, v_fov)

    return _stitch([_scale_to_width(frame, WORK_WIDTH) for frame in frames])


def frame_fov(width: int, height: int) -> tuple[float, float]:
    """Horizontal and vertical angle one phone frame of this shape covers."""
    focal = _focal_px(width, height)
    return (
        math.degrees(2 * math.atan((width / 2) / focal)),
        math.degrees(2 * math.atan((height / 2) / focal)),
    )


def _focal_px(width: int, height: int) -> float:
    return (max(width, height) / 2) / math.tan(math.radians(PHONE_LONG_SIDE_FOV_DEG / 2))


def _decode_image(filename: str, data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise PanoramaError(f"{filename} is not a photo or video this can read.")
    return image


def _video_frames(filename: str, data: bytes) -> list[np.ndarray]:
    # OpenCV reads video from a path only.
    suffix = os.path.splitext(filename)[1] or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(data)
        tmp.flush()
        capture = cv2.VideoCapture(tmp.name)
        try:
            total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if total <= 0:
                raise PanoramaError(f"{filename} is not a video this can read.")
            wanted = sorted({round(i * (total - 1) / max(MAX_VIDEO_FRAMES - 1, 1))
                             for i in range(min(MAX_VIDEO_FRAMES, total))})
            frames = []
            for index in wanted:
                capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = capture.read()
                if ok and frame is not None:
                    frames.append(frame)
        finally:
            capture.release()
    if not frames:
        raise PanoramaError(f"{filename} is not a video this can read.")
    return frames


def _scale_to_width(image: np.ndarray, width: int) -> np.ndarray:
    height, current = image.shape[:2]
    if current <= width:
        return image
    return cv2.resize(image, (width, round(height * width / current)), interpolation=cv2.INTER_AREA)


def _stitch(frames: list[np.ndarray]) -> Panorama:
    stitcher = cv2.Stitcher.create(cv2.Stitcher_PANORAMA)
    status, pano = stitcher.stitch(frames)
    if status != cv2.Stitcher_OK or pano is None:
        raise PanoramaError(
            _STITCH_FAILURES.get(status, "The photos could not be joined into one view.")
        )
    pano = _crop_black_border(pano)

    # The panorama stitcher warps onto a sphere whose radius is the frames' focal
    # length in pixels, so one pixel is 1/focal radians both ways.
    frame_height, frame_width = frames[0].shape[:2]
    focal = _focal_px(frame_width, frame_height)
    height, width = pano.shape[:2]
    h_fov = math.degrees(width / focal)
    if h_fov >= FULL_TURN_DEG:
        h_fov = 360.0
    return _encode(pano, min(h_fov, 360.0), min(math.degrees(height / focal), 180.0))


def _crop_black_border(image: np.ndarray) -> np.ndarray:
    """Trim the empty band warping leaves above and below the picture."""
    filled = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) > 0
    rows = np.where(filled.mean(axis=1) > 0.9)[0]
    cols = np.where(filled.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return image
    return image[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]


def _encode(image: np.ndarray, h_fov: float, v_fov: float) -> Panorama:
    image = _scale_to_width(image, MAX_OUTPUT_WIDTH)
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise PanoramaError("The panorama could not be saved.")
    height, width = image.shape[:2]
    return Panorama(
        jpeg=buffer.tobytes(),
        width=width,
        height=height,
        h_fov_deg=round(h_fov, 2),
        v_fov_deg=round(v_fov, 2),
    )
