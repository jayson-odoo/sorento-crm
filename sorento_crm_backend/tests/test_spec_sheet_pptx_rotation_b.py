"""B5: a rotated layer lands where the print page draws it (rotation about the box's top-left)."""
from __future__ import annotations

import io

EMU_PER_MM = 36000


def _deck(layers):
    from pptx import Presentation

    from app.services.spec_sheet_pptx import build_pptx

    return Presentation(io.BytesIO(build_pptx([{"layers": layers}], (338.7, 190.5))))


def _near(value, mm):
    return abs(int(value) - mm * EMU_PER_MM) <= 3


def test_rotation_zero_is_exact():
    deck = _deck([{"kind": "text", "x_mm": 10, "y_mm": 10, "width_mm": 40, "height_mm": 10, "text": "a", "rotation_deg": 0}])
    box = next(iter(deck.slides[0].shapes))
    assert _near(box.left, 10) and _near(box.top, 10) and box.rotation == 0


def test_a_quarter_turn_moves_the_box_so_its_top_left_stays_the_pivot():
    deck = _deck([{"kind": "text", "x_mm": 10, "y_mm": 10, "width_mm": 40, "height_mm": 10, "text": "a", "rotation_deg": 90}])
    box = next(iter(deck.slides[0].shapes))
    # Centre of the unrotated box (30, 15) swung 90 degrees about (10, 10) is (5, 30).
    assert box.rotation == 90
    assert _near(box.left + box.width // 2, 5) and _near(box.top + box.height // 2, 30)
