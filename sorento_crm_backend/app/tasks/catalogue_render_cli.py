"""Render one URL to a PDF file. Run as a SUBPROCESS, never in-process.

    python -m app.tasks.catalogue_render_cli <url> <out.pdf> [--landscape] [--paper A4]
        [--width-mm W --height-mm H]

RQ forks a work-horse per job, and driving Playwright's sync API inside that
fork segfaults on macOS (signal 11) - the browser launch does not survive a
fork it did not expect. `OBJC_DISABLE_INITIALIZE_FORK_SAFETY` covers the Obj-C
abort, not this.

A freshly spawned process has no forked state to trip over, so it works the same
on macOS and in Linux containers. It also isolates Chromium's memory from the
worker: a runaway render takes its own process down, not the queue.
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

# The flag the print page raises once its payload has arrived and every image
# has settled. Waiting on this rather than a fixed delay is what stops a slow
# catalogue being silently truncated.
READY_SELECTOR = "[data-dk-print-ready='true']"
READY_TIMEOUT_MS = 60_000


def pdf_options(
    *, paper: str, landscape: bool, size_mm: Optional[tuple[float, float]] = None
) -> dict:
    """The geometry ``page.pdf`` is given, and the only statement of it.

    A named paper (``format``) unless an explicit size is asked for: the project spec sheet
    (PS-SPEC-SHEET) prints at its templates' own size, 338.7 x 190.5 mm in the owner's sample,
    which no paper name covers. With a size, Chromium takes ``width``/``height`` and ``format``
    must be absent, or it wins. Every caller that names a paper (catalogues, tag sheets) gets
    exactly the options it got before this existed.
    """
    options: dict = {
        # The document's own margins are already in the print page's CSS; Chromium's would be
        # a second margin nobody chose.
        "margin": {"top": "0", "right": "0", "bottom": "0", "left": "0"},
        "print_background": True,
    }
    if size_mm is not None:
        width, height = size_mm
        options["width"] = f"{width}mm"
        options["height"] = f"{height}mm"
    else:
        # `prefer_css_page_size` is deliberately not set: the print page declares no
        # `@page size`, so turning it on would leave Chromium with nothing to size the paper
        # by. Both values come from the same `print_profile` the page renders, so the document
        # is laid out at `width: 100%` of whatever paper is named here - including when
        # `landscape` rotates it.
        options["format"] = paper
        options["landscape"] = landscape
    return options


def render(
    url: str,
    out_path: str,
    *,
    landscape: bool,
    paper: str,
    size_mm: Optional[tuple[float, float]] = None,
) -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=READY_TIMEOUT_MS)
            page.wait_for_selector(READY_SELECTOR, timeout=READY_TIMEOUT_MS)
            pdf_bytes = page.pdf(**pdf_options(paper=paper, landscape=landscape, size_mm=size_mm))
        finally:
            browser.close()

    with open(out_path, "wb") as handle:
        handle.write(pdf_bytes)
    return len(pdf_bytes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a print page to PDF")
    parser.add_argument("url")
    parser.add_argument("out")
    parser.add_argument("--landscape", action="store_true")
    parser.add_argument("--paper", default="A4")
    # Both or neither: an explicit page size in millimetres, in place of the paper name.
    parser.add_argument("--width-mm", type=float, default=None)
    parser.add_argument("--height-mm", type=float, default=None)
    args = parser.parse_args(argv)
    size_mm = (
        (args.width_mm, args.height_mm)
        if args.width_mm is not None and args.height_mm is not None
        else None
    )

    try:
        written = render(
            args.url, args.out, landscape=args.landscape, paper=args.paper, size_mm=size_mm
        )
    except Exception as exc:  # noqa: BLE001 - the parent reads stderr for the reason
        print(f"render failed: {exc}", file=sys.stderr)
        return 1

    print(written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
