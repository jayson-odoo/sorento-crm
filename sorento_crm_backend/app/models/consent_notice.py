"""The PDPA collection notice, versioned and immutable once published (fork 6).

`consumer_profiles.consent_notice_version` records WHICH wording a person saw. Until now
it recorded a literal that pointed at nothing, which made the one question a consent record
exists to answer - "prove what this person agreed to" - unanswerable.

**Rows are immutable after publication.** Correcting wording means publishing a new version;
the old row stays exactly as the people who accepted it saw it. That is why there is no
`updated_at` here: an updated_at on this table would advertise a mutation that must not
happen.

**Both language bodies are NOT NULL.** PDPA 2010 s.7(2) requires the notice in Bahasa
Malaysia and English, and a nullable column is how "the Malay is coming later" becomes a
permanent state. A draft with an empty body is representable (empty string) and simply
cannot be published - the guard lives in the service, at publish, so a draft can be worked
on.
"""
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ConsentNotice(Base):
    __tablename__ = "consent_notices"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Which collection point this notice governs. A key rather than one global row: the
    # technician portal and any future dealer portal collect different data for different
    # purposes and each need their own wording.
    notice_key = Column(String(64), nullable=False)
    # max(version) + 1 per key, assigned server-side.
    version = Column(Integer, nullable=False)
    # The lawful basis this wording establishes. Closed set, validated in the service
    # against consumer_service.CONSENT_PURPOSES - a notice that could declare `marketing`
    # is how fork 6's one-way door gets propped open.
    purpose = Column(String(32), nullable=False)
    body_en = Column(Text, nullable=False, server_default="")
    body_ms = Column(Text, nullable=False, server_default="")
    is_published = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    published_at = Column(DateTime(timezone=False), nullable=True)
    published_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("notice_key", "version", name="uq_consent_notices_key_version"),
        # A published row without a timestamp cannot answer "when did this wording take
        # effect", which is half of what publication means.
        CheckConstraint(
            "(is_published = false) OR (published_at IS NOT NULL)",
            name="ck_consent_notices_published_at",
        ),
        Index("ix_consent_notices_key_published", "notice_key", "is_published"),
    )
