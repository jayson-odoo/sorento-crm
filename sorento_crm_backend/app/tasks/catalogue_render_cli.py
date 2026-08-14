"""Render one URL to a PDF file. Run as a SUBPROCESS, never in-process.

    python -m app.tasks.catalogue_render_cli <url> <out.pdf> [--landscape] [--paper A4]

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

# The flag the print page raises once its payload has arrived and every image
# has settled. Waiting on this rather than a fixed delay is what stops a slow
# catalogue being silently truncated.
READY_SELECTOR = "[data-dk-print-ready='true']"
READY_TIMEOUT_MS = 60_000


def render(url: str, out_path: str, *, landscape: bool, paper: str) -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=READY_TIMEOUT_MS)
            page.wait_for_selector(READY_SELECTOR, timeout=READY_TIMEOUT_MS)
            pdf_bytes = page.pdf(
                # These two ARE the page geometry, and they are the only
                # statement of it. `prefer_css_page_size` is deliberately not
                # set: the print page declares no `@page size`, so turning it on
                # would leave Chromium with nothing to size the paper by. Both
                # values come from the same `print_profile` the page renders, so
                # the document is laid out at `width: 100%` of whatever paper is
                # named here - including when `landscape` rotates it.
                format=paper,
                landscape=landscape,
                # The document's own margins are already in the print page's
                # CSS; Chromium's would be a second margin nobody chose.
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                print_background=True,
            )
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
    args = parser.parse_args(argv)

    try:
        written = render(args.url, args.out, landscape=args.landscape, paper=args.paper)
    except Exception as exc:  # noqa: BLE001 - the parent reads stderr for the reason
        print(f"render failed: {exc}", file=sys.stderr)
        return 1

    print(written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
