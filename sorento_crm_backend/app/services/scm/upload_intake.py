"""Reading an uploaded spreadsheet, shared by every SCM upload channel.

Extracted the moment there was a second channel: `purchase_history.py` was importing
`outstanding_import._read_upload`, and reaching for another module's private helper is how
two routes end up with quietly different accept lists.

The accept list belongs to the CUSTOMER, not to us, which is why it is configuration rather
than a constant: AutoCount's own "Purchase Order Listing With Detail" export is legacy `.xls`,
and hard-coding the pair we happened to start with means telling somebody to re-save 13 MB of
order history by hand before the system will look at it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, UploadFile, status

from app.config import settings


def allowed_extensions() -> tuple[str, ...]:
    """The spreadsheet extensions the SCM uploads accept, from `SCM_UPLOAD_EXTENSIONS`.

    Read here AND served to the browser (`GET /outstanding/config`) so the dialog cannot
    offer a type the server then refuses, nor refuse one it would have accepted.
    """
    raw = (settings.scm_upload_extensions or "").split(",")
    return tuple(f".{e.strip().lstrip('.').lower()}" for e in raw if e.strip())


@dataclass(frozen=True)
class RetainedUpload:
    """One upload, in both the forms a queued import needs.

    `data` is what the reader parses (macros stripped, so openpyxl will open it) and
    `source_bytes` is exactly what arrived. They are kept apart because the source file the
    job retains for tracing must be the operator's own file: handing the stripped copy to
    `store_import_source_file` means the bytes somebody downloads from the job to check what
    they uploaded are bytes they never had.
    """

    data: bytes
    filename: str
    source_bytes: bytes
    source_name: str
    content_type: Optional[str]


async def read_upload_retained(file: UploadFile) -> RetainedUpload:
    """The uploaded bytes for a QUEUED import: what to parse, and what to keep.

    Same extension guard and same macro strip as `read_upload` - the difference is only that
    the original is not thrown away. Used by the `apply` routes, which hand the parse copy to
    the worker and the original to the source-file store.
    """
    name = (file.filename or "").lower()
    allowed = allowed_extensions()
    if not name.endswith(allowed):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid file type: {file.filename or 'unknown'}. "
                f"Upload {', '.join(allowed)}."
            ),
        )
    source_name = file.filename or "upload.xlsx"
    source_bytes = await file.read()
    if not source_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty",
        )
    if name.endswith(".xls"):
        # Legacy BIFF: openpyxl cannot open it at all, so there is nothing to strip.
        return RetainedUpload(source_bytes, source_name, source_bytes, source_name,
                              file.content_type)
    from app.services.excel_macro_stripper import maybe_strip

    data, cleaned_name = maybe_strip(source_bytes, source_name)
    return RetainedUpload(data, cleaned_name, source_bytes, source_name, file.content_type)


async def read_upload(file: UploadFile) -> bytes:
    """Just the bytes to parse, for a read that keeps nothing (preview, Test).

    The same guards as `read_upload_retained` because it IS that function - the extension
    check, the empty-file refusal and the macro strip were written twice and drifted: the
    preview path accepted a zero-byte upload and handed it to a reader, which reported "this
    file could not be read" where the apply path says "the uploaded file is empty".
    """
    return (await read_upload_retained(file)).data
