"""Generated pictures for the catalogue photo tests (no real catalogue is committed).

``pattern(seed)`` draws an 8x8 grid of random grey levels scaled up to a picture.
A re-encode at another size or quality keeps the grid, so its dHash barely moves;
two different seeds are unrelated grids, so their dHashes sit far apart.
"""
from __future__ import annotations

import io
import random


def pattern(seed: int, size: tuple[int, int] = (240, 240), *, color: bool = True):
    from PIL import Image

    rng = random.Random(seed)
    grid = Image.new("RGB", (8, 8))
    for x in range(8):
        for y in range(8):
            level = rng.randint(0, 255)
            grid.putpixel((x, y), (level, (level * 3 + seed) % 256, 255 - level) if color else (level,) * 3)
    return grid.resize(size, Image.NEAREST)


def encode(image, fmt: str = "JPEG", quality: int = 90) -> bytes:
    out = io.BytesIO()
    if fmt == "JPEG":
        image.convert("RGB").save(out, format="JPEG", quality=quality)
    else:
        image.save(out, format=fmt)
    return out.getvalue()


def png_of(seed: int, size: tuple[int, int] = (240, 240)) -> bytes:
    return encode(pattern(seed, size), "PNG")
