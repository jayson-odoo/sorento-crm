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

from fastapi import HTTPException, UploadFile, status

from app.config import settings


def allowed_extensions() -> tuple[str, ...]:
    """The spreadsheet extensions the SCM uploads accept, from `SCM_UPLOAD_EXTENSIONS`.

    Read here AND served to the browser (`GET /outstanding/config`) so the dialog cannot
    offer a type the server then refuses, nor refuse one it would have accepted.
    """
    raw = (settings.scm_upload_extensions or "").split(",")
    return tuple(f".{e.strip().lstrip('.').lower()}" for e in raw if e.strip())


async def read_upload(file: UploadFile) -> bytes:
    """The uploaded bytes, refusing a type outside the configured list.

    The message names what IS accepted, because "invalid file type" tells somebody holding a
    `.xls` nothing about what to do next.
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
    from app.services.excel_macro_stripper import maybe_strip

    data = await file.read()
    # The macro stripper rewrites through openpyxl, which cannot open legacy BIFF at all, so
    # a `.xls` is passed through untouched. It carries no macro sheet in the `.xlsm` sense,
    # and every reader opens it read-only.
    if name.endswith(".xls"):
        return data
    data, _ = maybe_strip(data, file.filename or "upload.xlsx")
    return data
