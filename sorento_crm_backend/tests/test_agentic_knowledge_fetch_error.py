"""AGENTIC-KNOWLEDGE fix round 2 (D2): a storage failure shows staff a fixed sentence, never raw config text."""
from __future__ import annotations

import logging

import pytest

from app.models.resources import Attachment
from tests._knowledge_seed import seed_attachment, seed_type
from tests._pg_fixture import blank_session

RAW = "S3 configuration incomplete: set AWS_S3_BUCKET_NAME, AWS_ACCESS_KEY_ID in the backend environment"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def test_a_storage_failure_stores_the_fixed_sentence_and_keeps_the_raw_text_in_the_log(db, caplog):
    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db))

    def fetch(a):
        raise RuntimeError(RAW)

    with caplog.at_level(logging.DEBUG):
        ks.read_attachment(db, str(att.id), fetch=fetch, ocr=lambda p, n: "", embed=lambda t: [])

    db.expire_all()
    row = db.query(Attachment).filter(Attachment.id == att.id).one()
    assert row.ai_read_status == "failed"
    assert row.ai_read_error == "The file could not be downloaded from storage."
    assert "AWS_S3_BUCKET_NAME" not in row.ai_read_error
    assert "AWS_S3_BUCKET_NAME" in caplog.text, "the raw cause is still in the log"
