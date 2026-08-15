"""Hand-built flyer PDFs, for the two artwork cases the committed fixture cannot carry.

``tests/fixtures/dealer_kit/flyer_sample.pdf`` is three pages cut from the real
2025-2026 A3 flyer and is the right substrate for almost everything: it has the
overlapping artwork, the two-products-under-one-photo cards and the wall of
small print that a synthetic document would never reproduce. Two things it
cannot prove, both for the same reason - its images were thumbnailed to almost
nothing so the repository would not have to carry 20 MB:

* **Colour space.** Thumbnailing re-encoded every banner, so the fixture's images
  come back RGB. The real flyer's banners are DeviceCMYK JPEGs (15 of 15 measured
  on the first eight pages), which is the defect AC-F1 exists for, and PyMuPDF's
  own ``insert_image`` transcodes a CMYK JPEG to RGB on the way in - so a PDF
  built with the high-level API cannot carry the case either.
* **Pixels surviving a crop.** Proving AC-F2 cropped the right REGION needs a
  source image whose halves are told apart by their colour. The fixture's are
  blank.

So these are written as raw PDF bytes with a DCTDecode image XObject declared
``/DeviceCMYK``, which is byte-for-byte what the real document holds. Nothing
here replaces the real fixture; it covers the two seams the fixture lost.
"""
from __future__ import annotations

import io
from typing import Iterable, Sequence

# The real flyer's paper, in points. Used so the synthetic geometry can be the
# geometry actually measured on the document rather than round numbers.
A3_WIDTH_PT = 842.0
A3_HEIGHT_PT = 1191.0

# The oversized placement measured on flyer page 4: 1.17x the page width,
# anchored 662pt above the top edge. This is the AC-F2 case.
OVERSIZED_RECT = (-69.0, -662.0, 915.0, 722.0)

# A band across the top, which is what a real section banner is.
BANNER_RECT = (0.0, 0.0, A3_WIDTH_PT, 213.0)


def cmyk_jpeg(width: int, height: int, *, split: bool = False) -> bytes:
    """A CMYK JPEG, optionally with a colour change halfway down.

    ``split`` paints the top half in cyan and the bottom half in magenta so a
    test can say WHICH half of the source survived a crop. Without it the image
    is one flat colour, which is enough when only the colour SPACE is under test.
    """
    from PIL import Image

    image = Image.new("CMYK", (width, height), (255, 0, 0, 0))
    if split:
        bottom = Image.new("CMYK", (width, height - height // 2), (0, 255, 0, 0))
        image.paste(bottom, (0, height // 2))

    out = io.BytesIO()
    image.save(out, format="JPEG", quality=90)
    return out.getvalue()


def flyer_pdf(
    *,
    image: bytes,
    image_size: tuple[int, int],
    rect: Sequence[float],
    codes: Iterable[tuple[str, float, float]] = (),
    page_size: tuple[float, float] = (A3_WIDTH_PT, A3_HEIGHT_PT),
) -> bytes:
    """One A3 page carrying one CMYK image and any product codes named.

    ``rect`` is in fitz page coordinates (origin top-left), like everything the
    extractor deals in, and may lie partly outside the page - which is the whole
    point of the AC-F2 case. ``codes`` are ``(code, x, y)`` with ``y`` measured
    from the TOP, again matching the extractor rather than PDF's own bottom-up
    space.

    Written as raw bytes rather than through PyMuPDF because the high-level API
    decodes and re-encodes an inserted JPEG, which loses the CMYK the test is
    about. The xref table is written with real offsets, so the file is valid
    rather than something MuPDF has to repair.
    """
    page_width, page_height = page_size
    x0, y0, x1, y1 = rect
    pixels_wide, pixels_high = image_size

    # PDF space is bottom-up, so the placement matrix flips the rect over.
    matrix = f"{x1 - x0:.4f} 0 0 {y1 - y0:.4f} {x0:.4f} {page_height - y1:.4f}"
    text = "".join(
        f"BT /F1 9 Tf 1 0 0 1 {x:.2f} {page_height - y:.2f} Tm ({code}) Tj ET\n"
        for code, x, y in codes
    )
    content = f"q {matrix} cm /Im0 Do Q\n{text}".encode()

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /XObject << /Im0 5 0 R >> /Font << /F1 6 0 R >> >> "
            f"/Contents 4 0 R >>"
        ).encode(),
        4: (
            b"<< /Length "
            + str(len(content)).encode()
            + b" >>\nstream\n"
            + content
            + b"\nendstream"
        ),
        # /Decode inverts the samples, which is what a CMYK JPEG carrying an
        # Adobe APP14 marker needs and what every print-pipeline PDF declares.
        # Without it MuPDF reads the ink values straight and the picture comes
        # back black, so a crop test could not tell one half from the other.
        5: (
            f"<< /Type /XObject /Subtype /Image /Width {pixels_wide} "
            f"/Height {pixels_high} /ColorSpace /DeviceCMYK /BitsPerComponent 8 "
            f"/Decode [1 0 1 0 1 0 1 0] /Filter /DCTDecode /Length {len(image)} >>"
        ).encode()
        + b"\nstream\n"
        + image
        + b"\nendstream",
        6: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for number in sorted(objects):
        out += f"{offsets[number]:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


__all__ = [
    "A3_HEIGHT_PT",
    "A3_WIDTH_PT",
    "BANNER_RECT",
    "OVERSIZED_RECT",
    "cmyk_jpeg",
    "flyer_pdf",
]
