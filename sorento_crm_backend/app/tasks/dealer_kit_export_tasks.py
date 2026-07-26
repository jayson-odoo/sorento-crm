"""Render a catalogue page to PDF with headless Chromium.

Chromium rather than WeasyPrint on purpose. The print page is the SAME React
tree the editor and the public catalogue render, so "the PDF matches the screen"
is structural. A second HTML-to-PDF engine would have its own CSS grid support,
its own font metrics and its own idea of a page break, and the two would drift -
visibly, in a document that goes to a printer.

The worker never decides who the document is for. It reads the snapshot written
at enqueue, and if there is none it fails the download rather than falling back
to a system principal (which is a staff principal, and would print internal
prices into a consumer's copy).
"""
from __future__ import annotations

import logging
import os

from app.database import SessionLocal
from app.models.dealer_kit import Page
from app.services.company_scope import set_company_scope
from app.services.dealer_kit import export_service, render_token
from app.services.download_service import DownloadService
from app.services.storage_router import default_provider, get_backend

logger = logging.getLogger(__name__)

# Where the worker can reach the frontend. Not the public hostname necessarily -
# inside a container this is usually the service name.
PRINT_BASE_ENV = "DEALER_KIT_PRINT_BASE_URL"
DEFAULT_PRINT_BASE = "http://localhost:3000"

# Chromium waits for the page to say it is done rather than for a fixed delay:
# the print page sets this once every collection has resolved and every image
# has settled, so a slow catalogue is not silently truncated.
READY_SELECTOR = "[data-dk-print-ready='true']"
READY_TIMEOUT_MS = 60_000


def _print_url(download_id: str) -> str:
    base = os.environ.get(PRINT_BASE_ENV, DEFAULT_PRINT_BASE).rstrip("/")
    token = render_token.issue(download_id)
    return f"{base}/c/print/{download_id}?token={token}"


def _render_pdf(url: str, *, landscape: bool, paper: str) -> bytes:
    """Render in a freshly SPAWNED subprocess, never in this process.

    RQ forks a work-horse per job, and driving Playwright's sync API inside that
    fork segfaults on macOS (signal 11) - the browser launch does not survive a
    fork it did not expect, and OBJC_DISABLE_INITIALIZE_FORK_SAFETY only covers
    the Obj-C abort. A spawned process has no forked state to trip over, behaves
    the same in a Linux container, and keeps Chromium's memory out of the
    worker: a runaway render takes its own process down, not the queue.
    """
    import subprocess
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as workdir:
        out_path = os.path.join(workdir, "catalogue.pdf")
        command = [
            sys.executable,
            "-m",
            "app.tasks.catalogue_render_cli",
            url,
            out_path,
            "--paper",
            paper,
        ]
        if landscape:
            command.append("--landscape")

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=(READY_TIMEOUT_MS // 1000) + 60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                (result.stderr or "").strip() or "PDF renderer exited non-zero"
            )

        with open(out_path, "rb") as handle:
            return handle.read()


def generate_catalogue_pdf(download_id: str) -> dict:
    """Render the catalogue behind ``download_id`` and store the PDF.

    Takes only the download id: everything else comes from the snapshot, so the
    task cannot be invoked with a viewer that disagrees with what was requested.
    """
    db = SessionLocal()
    svc = DownloadService(db)
    try:
        svc.mark_processing(download_id)

        # Refuses when the snapshot is missing rather than guessing an audience.
        request = export_service.get_request(db, download_id)

        page = None
        set_company_scope(db, None)
        page = db.query(Page).filter(Page.id == request.page_id).first()
        if page is None:
            raise RuntimeError("The exported page no longer exists")

        profile = page.print_profile or {}
        pdf_bytes = _render_pdf(
            _print_url(download_id),
            landscape=(profile.get("orientation") == "landscape"),
            paper=profile.get("pageSize") or "A4",
        )

        download = svc.get(download_id)
        filename = (download.filename if download else None) or f"catalogue-{download_id}.pdf"

        provider = default_provider()
        backend = get_backend(provider)
        stored_key, _signed = backend.upload_file(
            file_content=pdf_bytes,
            file_path=f"exports/dealer-kit-catalogue/{download_id}/{filename}",
            content_type="application/pdf",
        )

        svc.mark_ready(
            download_id,
            storage_provider=provider,
            storage_key=stored_key,
            filename=filename,
        )
        logger.info(
            "generate_catalogue_pdf: download %s ready (%d bytes, audience=%s)",
            download_id,
            len(pdf_bytes),
            request.audience,
        )
        return {"download_id": download_id, "status": "ready", "bytes": len(pdf_bytes)}
    except Exception as exc:  # noqa: BLE001 - mark failed, never poison the queue
        logger.exception("generate_catalogue_pdf failed for download %s", download_id)
        try:
            svc.mark_failed(download_id, str(exc))
        except Exception:
            logger.exception(
                "generate_catalogue_pdf: could not mark download %s failed", download_id
            )
        return {"download_id": download_id, "status": "failed", "error": str(exc)}
    finally:
        db.close()
