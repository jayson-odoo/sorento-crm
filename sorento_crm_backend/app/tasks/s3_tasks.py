"""Background tasks for S3 operations (e.g. delete files after attachment hard delete)."""
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def delete_s3_files(s3_keys: list[str]) -> dict:
    """
    Delete one or more files from S3 by key. Runs in a background job.
    Logs warnings for failures but does not raise; returns counts.
    """
    if not s3_keys:
        return {"deleted": 0, "failed": 0}

    from app.services.s3_service import S3Service

    s3 = S3Service()
    deleted = 0
    failed = 0
    for raw_key in s3_keys:
        key = raw_key.strip()
        if not key:
            continue
        try:
            # If stored as full URL, extract path as key
            if key.startswith("https://"):
                parsed = urlparse(key)
                key = parsed.path.lstrip("/")
            s3.delete_file(key)
            deleted += 1
        except Exception as e:
            failed += 1
            logger.warning("S3 delete failed for key %s: %s", raw_key, e)
    return {"deleted": deleted, "failed": failed}
