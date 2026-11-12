"""Dump a flyer page's text lines with bold marked as **...**, with PDF-point bboxes.

usage: venv/bin/python -I spans.py PDF PAGE [x0 y0 x1 y1]
Coordinates are PDF points (page is 595 x 842). Rendered PNGs in pages/: pNN.png at 1.2x,
hiNN.png at 2.5x, so point = pixel / zoom.
"""
import sys
import fitz

pdf, page = sys.argv[1], int(sys.argv[2])
clip = fitz.Rect(*map(float, sys.argv[3:7])) if len(sys.argv) >= 7 else None
pg = fitz.open(pdf)[page - 1]
rows = []
for b in pg.get_text("dict", clip=clip)["blocks"]:
    for ln in b.get("lines", []):
        parts = []
        for s in ln["spans"]:
            t = s["text"]
            if not t.strip():
                parts.append(t)
                continue
            bold = ("Bold" in s["font"]) or ("Black" in s["font"]) or bool(s["flags"] & 16)
            parts.append(f"**{t}**" if bold else t)
        txt = "".join(parts).replace("****", "")
        if txt.strip():
            x0, y0, x1, y1 = ln["bbox"]
            sz = max(s["size"] for s in ln["spans"])
            rows.append((round(y0), round(x0), round(x1), round(y1), round(sz, 1), txt))
rows.sort(key=lambda r: (r[1] // 60, r[0]))
for y0, x0, x1, y1, sz, txt in sorted(rows, key=lambda r: (r[0] // 8, r[1])):
    print(f"[{x0:3d},{y0:3d}-{x1:3d},{y1:3d}] sz{sz:<4} {txt}")
