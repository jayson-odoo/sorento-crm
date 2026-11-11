"""SPEC-SHEET-DESIGNER-PARITY B5: PowerPoint export through the standard export / My Downloads
flow. Written test-FIRST. Postgres only; the queue, the browser and storage are faked.

Contract assumptions (the plan leaves these open):
- the export route takes `?format=pdf|pptx` as a query parameter (default pdf, else 422);
- the worker reads the layout through `dealer_kit_export_tasks._render_layout(url, size_mm)`
  which returns `{"page_mm": [w, h], "pages": [{"layers": [...]}]}` (the browser part);
- `python-pptx` must be in requirements.txt (it is installed in the venv, not yet listed).
"""
from __future__ import annotations

import base64
import io

import pytest

from ._pg_fixture import blank_session
from .test_project_spec_sheet import _chain, _sheet  # noqa: F401  (helpers, not tests)
from .test_project_spec_sheets_v2 import (  # noqa: F401  (helpers, not tests)
    VIEW_ONLY,
    _base,
    _client,
    _make,
    _restore,
)

EMU_PER_MM = 36000

PNG_1X1 = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


# ------------------------------------------------------------------ request_export


def test_requirements_list_python_pptx():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text().lower()
    assert "python-pptx" in text


def test_request_export_pptx_names_the_file_and_queues_the_pptx_task(monkeypatch):
    from app.services import project_spec_sheet_service as spec

    calls = []
    monkeypatch.setattr(
        "app.services.queue_service.enqueue_job", lambda *a, **k: calls.append((a, k))
    )
    with blank_session() as db:
        c = _chain(db)
        sheet = _sheet(db, c)
        pdf = spec.request_export(db, sheet, user_id=c["owner"])
        pptx = spec.request_export(db, sheet, user_id=c["owner"], fmt="pptx")

        assert pdf.filename.startswith("spec-sheet-") and pdf.filename.endswith("-SS1.pdf")
        assert pptx.filename.startswith("spec-sheet-") and pptx.filename.endswith("-SS1.pptx")
        assert pptx.filename[: -len(".pptx")] == pdf.filename[: -len(".pdf")]
        assert pptx.status == "pending"
        assert [c_[0][0].__name__ for c_ in calls] == ["generate_spec_sheet_pdf", "generate_spec_sheet_pptx"]
        args, kwargs = calls[1]
        assert args[1] == str(pptx.id)
        assert kwargs["queue_name"] == "catalogue_render"
        assert kwargs["job_timeout"] == calls[0][1]["job_timeout"] == 900


def test_a_queue_outage_marks_the_pptx_row_failed(monkeypatch):
    from app.services import project_spec_sheet_service as spec

    def down(*_a, **_k):
        raise RuntimeError("redis is down")

    monkeypatch.setattr("app.services.queue_service.enqueue_job", down)
    with blank_session() as db:
        c = _chain(db)
        sheet = _sheet(db, c)
        download = spec.request_export(db, sheet, user_id=c["owner"], fmt="pptx")
        assert download.status == "failed"
        assert "redis is down" in (download.error_message or "")


def test_the_public_print_payload_answers_a_pptx_download_too(monkeypatch):
    from app.services import project_spec_sheet_service as spec
    from app.services.dealer_kit.tag_sheet_export_service import resolve_tag_sheet_print_payload

    monkeypatch.setattr("app.services.queue_service.enqueue_job", lambda *a, **k: None)
    with blank_session() as db:
        c = _chain(db)
        sheet = _sheet(db, c)
        download = spec.request_export(db, sheet, user_id=c["owner"], fmt="pptx")
        payload = resolve_tag_sheet_print_payload(db, str(download.id))
        assert "cover" in payload["resolvedData"]


# ------------------------------------------------------------------ route


def test_the_export_route_takes_a_format_and_refuses_an_unknown_one(monkeypatch):
    queued = []
    monkeypatch.setattr("app.services.queue_service.enqueue_job", lambda *a, **k: queued.append((a, k)))
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        client, originals = _client(db, c["owner"], slugs=VIEW_ONLY)
        try:
            url = _base(c, f"/{sheet.id}/export")
            default = client.post(url)
            assert default.status_code == 200, default.text
            assert default.json()["filename"].endswith(".pdf")
            assert queued[-1][0][0].__name__ == "generate_spec_sheet_pdf"

            pptx = client.post(url, params={"format": "pptx"})
            assert pptx.status_code == 200, pptx.text
            assert pptx.json()["filename"].endswith(".pptx")
            assert queued[-1][0][0].__name__ == "generate_spec_sheet_pptx"

            count = len(queued)
            assert client.post(url, params={"format": "docx"}).status_code == 422
            assert len(queued) == count
        finally:
            _restore(originals)


def test_the_pptx_export_needs_the_same_right_as_the_pdf(monkeypatch):
    monkeypatch.setattr("app.services.queue_service.enqueue_job", lambda *a, **k: None)
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        client, originals = _client(db, c["owner"], slugs=[])
        try:
            url = _base(c, f"/{sheet.id}/export")
            assert client.post(url).status_code == 403
            assert client.post(url, params={"format": "pptx"}).status_code == 403
        finally:
            _restore(originals)


# ------------------------------------------------------------------ worker task


class _Session:
    def query(self, *_a, **_k):
        return self

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return type("D", (), {"filename": "spec-sheet-x-SS1.pptx", "id": "d1", "kind": "k"})()

    def close(self):
        pass


def _wire(monkeypatch, layout=None, fail=None):
    from app.services import project_spec_sheet_service as spec
    from app.tasks import dealer_kit_export_tasks as tasks

    seen = {"ready": [], "failed": [], "uploads": []}

    class Downloads:
        def __init__(self, _db):
            pass

        def mark_processing(self, _id):
            pass

        def mark_ready(self, download_id, **kw):
            seen["ready"].append((download_id, kw))

        def mark_failed(self, download_id, message=None, *_a, **_k):
            seen["failed"].append((download_id, message))

    class Backend:
        def upload_file(self, file_content, file_path, content_type=None, **_k):
            seen["uploads"].append((file_content, file_path, content_type))
            return file_path, file_path

    def render_layout(*_a, **_k):
        if fail:
            raise RuntimeError(fail)
        return layout

    monkeypatch.setattr(tasks, "SessionLocal", lambda: _Session())
    monkeypatch.setattr(tasks, "DownloadService", Downloads)
    monkeypatch.setattr(tasks, "get_backend", lambda _p: Backend())
    monkeypatch.setattr(tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(tasks, "_render_layout", render_layout, raising=False)
    monkeypatch.setattr(spec, "page_size_for_download", lambda db, d: (338.7, 190.5))
    monkeypatch.setattr(spec, "prepare_export_images", lambda db, d: None)
    return tasks, seen


def test_the_pptx_worker_builds_the_deck_stores_it_and_marks_the_download_ready(monkeypatch):
    from pptx import Presentation

    layout = {
        "page_mm": [338.7, 190.5],
        "pages": [
            {"layers": [{"kind": "text", "x_mm": 5, "y_mm": 5, "width_mm": 50, "height_mm": 10, "text": "HELLO"}]},
            {"layers": []},
        ],
    }
    tasks, seen = _wire(monkeypatch, layout=layout)

    result = tasks.generate_spec_sheet_pptx("d1")

    assert result["status"] == "ready", result
    assert seen["failed"] == []
    assert len(seen["uploads"]) == 1
    content, path, content_type = seen["uploads"][0]
    assert path.startswith("exports/quotation-spec-sheet/d1/") and path.endswith(".pptx")
    assert "presentationml" in (content_type or "")
    assert len(Presentation(io.BytesIO(content)).slides) == 2
    assert seen["ready"][0][0] == "d1"
    assert seen["ready"][0][1]["filename"].endswith(".pptx")


def test_a_browser_failure_marks_the_pptx_download_failed(monkeypatch):
    tasks, seen = _wire(monkeypatch, fail="browser crashed")
    result = tasks.generate_spec_sheet_pptx("d1")
    assert result["status"] == "failed"
    assert seen["ready"] == [] and seen["uploads"] == []
    assert len(seen["failed"]) == 1 and "browser crashed" in seen["failed"][0][1]


# ------------------------------------------------------------------ builder


def _deck(pages, page_mm=(338.7, 190.5)):
    from pptx import Presentation

    from app.services.spec_sheet_pptx import build_pptx

    data = build_pptx(pages, page_mm)
    assert isinstance(data, bytes)
    return Presentation(io.BytesIO(data))


def _near(value, mm):
    return abs(int(value) - mm * EMU_PER_MM) <= 2


def test_one_slide_per_page_at_the_page_size():
    deck = _deck([{"layers": []}, {"layers": []}, {"layers": []}])
    assert len(deck.slides) == 3
    assert _near(deck.slide_width, 338.7) and _near(deck.slide_height, 190.5)


def test_a_text_layer_is_a_text_box_with_its_position_text_style_and_colour():
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Pt

    deck = _deck(
        [
            {
                "layers": [
                    {
                        "kind": "text",
                        "x_mm": 12.5,
                        "y_mm": 20,
                        "width_mm": 80,
                        "height_mm": 15,
                        "rotation_deg": 0,
                        "text": "Wall hung WC",
                        "fontFamily": "DM Sans",
                        "fontSize": 14,
                        "bold": True,
                        "italic": False,
                        "underline": False,
                        "color": "#112233",
                        "align": "center",
                    }
                ]
            }
        ]
    )
    boxes = [s for s in deck.slides[0].shapes if s.has_text_frame and s.text_frame.text == "Wall hung WC"]
    assert len(boxes) == 1
    box = boxes[0]
    assert _near(box.left, 12.5) and _near(box.top, 20)
    assert _near(box.width, 80) and _near(box.height, 15)
    paragraph = box.text_frame.paragraphs[0]
    run = paragraph.runs[0]
    assert run.font.bold is True
    assert run.font.size == Pt(14)
    assert run.font.name == "DM Sans"
    assert run.font.color.rgb == RGBColor(0x11, 0x22, 0x33)
    assert paragraph.alignment == PP_ALIGN.CENTER


def test_an_image_layer_is_a_picture_at_its_box():
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    deck = _deck(
        [{"layers": [{"kind": "image", "x_mm": 10, "y_mm": 15, "width_mm": 40, "height_mm": 30, "url": PNG_1X1}]}]
    )
    pictures = [s for s in deck.slides[0].shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert len(pictures) == 1
    assert _near(pictures[0].left, 10) and _near(pictures[0].top, 15)
    assert _near(pictures[0].width, 40) and _near(pictures[0].height, 30)


def test_a_shape_layer_keeps_its_fill():
    from pptx.dml.color import RGBColor

    deck = _deck(
        [
            {
                "layers": [
                    {
                        "kind": "shape",
                        "shape": "rect",
                        "x_mm": 5,
                        "y_mm": 5,
                        "width_mm": 30,
                        "height_mm": 20,
                        "fill": "#ff0000",
                        "stroke": "#000000",
                        "strokeWidth": 0.5,
                    }
                ]
            }
        ]
    )
    shapes = list(deck.slides[0].shapes)
    assert len(shapes) == 1
    assert shapes[0].fill.fore_color.rgb == RGBColor(0xFF, 0x00, 0x00)
    assert _near(shapes[0].left, 5) and _near(shapes[0].width, 30)


def test_a_table_layer_is_a_real_table_with_text_a_merged_cell_and_a_border_colour():
    deck = _deck(
        [
            {
                "layers": [
                    {
                        "kind": "table",
                        "x_mm": 10,
                        "y_mm": 20,
                        "width_mm": 60,
                        "height_mm": 12,
                        "columns_mm": [30, 30],
                        "rows_mm": [6, 6],
                        "cells": [
                            {"row": 0, "col": 0, "rowSpan": 1, "colSpan": 2, "text": "REF Q-1", "fill": "#eeeeee"},
                            {"row": 1, "col": 0, "rowSpan": 1, "colSpan": 1, "text": "A", "fill": None},
                            {"row": 1, "col": 1, "rowSpan": 1, "colSpan": 1, "text": "B", "fill": None},
                        ],
                        # Table-local coordinates: the top edge of the whole first row.
                        "edges": [
                            {"x1_mm": 0, "y1_mm": 0, "x2_mm": 60, "y2_mm": 0, "color": "#ff0000", "width_mm": 0.5}
                        ],
                    }
                ]
            }
        ]
    )
    tables = [s for s in deck.slides[0].shapes if s.has_table]
    assert len(tables) == 1
    shape = tables[0]
    assert _near(shape.left, 10) and _near(shape.top, 20)
    table = shape.table
    assert len(table.rows) == 2 and len(table.columns) == 2
    assert table.cell(0, 0).text == "REF Q-1"
    assert table.cell(0, 0).is_merge_origin is True
    assert table.cell(0, 0).span_width == 2
    assert table.cell(1, 0).text == "A" and table.cell(1, 1).text == "B"
    top_colours = table.cell(0, 0)._tc.xpath("a:tcPr/a:lnT//a:srgbClr/@val")
    assert [v.upper() for v in top_colours] == ["FF0000"]


def test_unknown_layer_kinds_are_skipped_never_a_crash():
    deck = _deck(
        [
            {
                "layers": [
                    {"kind": "hologram", "x_mm": 1, "y_mm": 1, "width_mm": 5, "height_mm": 5},
                    {"kind": "text", "x_mm": 1, "y_mm": 1, "width_mm": 20, "height_mm": 5, "text": "kept"},
                ]
            }
        ]
    )
    texts = [s.text_frame.text for s in deck.slides[0].shapes if s.has_text_frame]
    assert texts == ["kept"]
