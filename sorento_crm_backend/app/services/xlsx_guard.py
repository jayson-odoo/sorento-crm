"""The zip pre-check for an uploaded .xlsx, shared by the supplier price list reader and the AI panel's
attachments. Moved out of `supplier_price_list_reader` with no change in behaviour."""
from __future__ import annotations

import zipfile
from typing import Optional

from app.services.error_handler import AppException

#: S2 (security review): the ZIP container's OWN declared sizes, inspected BEFORE
#: openpyxl ever decompresses anything. A small, highly-compressible file (real zero
#: bytes compress ~1000:1) sails through the on-disk `_MAX_FILE_BYTES` cap above and
#: hands openpyxl tens of megabytes to decompress - these two catch that independent
#: of how small the upload looked on the wire.
_MAX_ZIP_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
_MAX_ZIP_COMPRESSION_RATIO = 100
#: An `.xlsx` carrying this member (or declaring a macro-enabled content type) is a
#: macro workbook renamed to look like a plain one - refused outright, never parsed.
_MACRO_MEMBER = "xl/vbaProject.bin"
_MACRO_CONTENT_TYPE_MARKER = b"macroEnabled"


def inspect_xlsx_zip(data: bytes) -> None:
    """The zip pre-check S2 needs: summed declared uncompressed size, compression
    ratio, and a macro-project member/content type - all read from the archive's own
    directory, never by inflating a member. Deliberately does NOT use `read_only`
    on the eventual `openpyxl.load_workbook` call: that mode drops merged-cell
    metadata this reader depends on (`_vertical_merge_anchors`), so this check is the
    bound instead of a safer-but-lossier parse mode."""
    import io

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise AppException(
            422, "That file could not be read as an Excel workbook.",
            detail={"code": "file_type"}, code="file_type",
        ) from exc

    try:
        total_uncompressed = 0
        total_compressed = 0
        has_macro_member = False
        content_types_xml: Optional[bytes] = None
        for info in zf.infolist():
            total_uncompressed += info.file_size
            total_compressed += info.compress_size
            if info.filename == _MACRO_MEMBER:
                has_macro_member = True
            if info.filename == "[Content_Types].xml":
                content_types_xml = zf.read(info.filename)

        if total_uncompressed > _MAX_ZIP_UNCOMPRESSED_BYTES:
            raise AppException(
                422, "The file is too large to process safely.",
                detail={"code": "file_too_large"}, code="file_too_large",
            )
        if total_compressed and (total_uncompressed / total_compressed) > _MAX_ZIP_COMPRESSION_RATIO:
            raise AppException(
                422, "The file is too large to process safely.",
                detail={"code": "file_too_large"}, code="file_too_large",
            )
        if has_macro_member or (content_types_xml and _MACRO_CONTENT_TYPE_MARKER in content_types_xml):
            raise AppException(
                422, "Macro-enabled workbooks are not accepted.",
                detail={"code": "file_type"}, code="file_type",
            )
    finally:
        zf.close()
