"""Upload channel for outstanding orders, until AutoCount is integrated.

Two steps on purpose. `POST .../preview` says what would change and writes nothing;
`POST .../apply` writes it. Nothing is ever saved from a single click, because the whole
plan is built on this data and a wrong file quietly imported is a week of unpicking.

Unlike the other importers in this codebase this one runs INLINE rather than on the RQ
queue. The user is looking at a diff and waiting to confirm it, so a job id they then have
to poll would break the one interaction that matters. Extracts are a few thousand rows, well
inside a request. If a client ever exports something large enough to time out, the queue
pattern (`spo_import`) is the escape hatch, and the preview/apply split already matches it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import PO, SO
from app.services.scm.upload_intake import allowed_extensions, read_upload

router = APIRouter()

# Uploading the open order book rewrites what the whole plan is computed from, so it sits
# behind the operator capability rather than the read one.
_WRITE = require_permission("scm.reorder.run")

_DOC_TYPES = {"sales-orders": SO, "purchase-orders": PO}

# Document types `apply` can actually WRITE. Preview works for every readable type, because it
# only reads, but the write path must refuse anything it cannot persist correctly rather than
# persist it somewhere plausible-looking.
#
# This exists because it already went wrong: `apply` branched on doc_type only to pick a reader,
# then unconditionally constructed SalesOrder / SalesOrderLine. Uploading the purchase order book
# therefore created SALES orders whose so_number was the PO number - silent cross-table
# corruption that a reader-level doc_type check did nothing to stop. Keep this allow-list even
# after the PO write path lands: a type that can be read but not written must fail loudly.
_WRITABLE_DOC_TYPES = {SO, PO}


def _doc_type(kind: str) -> str:
    try:
        return _DOC_TYPES[kind]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown document type '{kind}'. Expected one of: "
                   f"{', '.join(sorted(_DOC_TYPES))}.",
        )


def _assert_writable(kind: str, doc_type: str) -> None:
    """Refuse `apply` for a type this route can read but not write.

    501 rather than 400: the request is well formed and authorized, and the file may be
    perfectly good - the server simply has no write path for this book yet, which is what
    501 means. A 400 would land in the same bucket as this route's other 400s ("your file
    is missing a column", "that is not an xlsx"), so the operator would go looking for a
    problem with their export that does not exist.
    """
    if doc_type in _WRITABLE_DOC_TYPES:
        return
    writable = ", ".join(sorted(k for k, v in _DOC_TYPES.items() if v in _WRITABLE_DOC_TYPES))
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            f"Applying the {kind.replace('-', ' ')} book is not implemented yet. "
            f"Preview it to check the file; only {writable.replace('-', ' ')} can be applied."
        ),
    )


@router.get("/outstanding/config")
def get_outstanding_upload_config(_user: dict = Depends(_WRITE)):
    """What the upload dialog may offer, so the browser and the server agree.

    The dialog used to hard-code its own accept list, which is how it came to refuse a file
    the reader can parse perfectly well.
    """
    return {"allowed_extensions": list(allowed_extensions())}


@router.post("/outstanding/{kind}/preview")
async def preview_outstanding_import(
    kind: str,
    file: UploadFile = File(..., description="AutoCount outstanding-orders extract (.xlsx)"),
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """What this file would change. Writes nothing."""
    doc_type = _doc_type(kind)
    result = svc.preview(db, await read_upload(file), doc_type)
    # A file whose header cannot answer the question is a 200 carrying `ok: false`, not an
    # error: the screen needs to render WHICH columns are missing so the export can be
    # fixed, and an exception body would lose that.
    return result.to_dict()


@router.post("/outstanding/{kind}/apply")
async def apply_outstanding_import(
    kind: str,
    file: UploadFile = File(..., description="The same file the preview was taken from"),
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Write the upload. Returns the same counts the preview showed."""
    doc_type = _doc_type(kind)
    _assert_writable(kind, doc_type)
    out = svc.apply(db, await read_upload(file), doc_type,
                    actor=current_user.get("id"))
    if not out.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The file is missing required columns: "
                   + ", ".join(out.get("missing_columns") or []),
        )
    db.commit()
    return out
