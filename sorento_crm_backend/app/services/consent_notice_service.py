"""The PDPA collection notice: configurable, versioned, immutable once published.

Fork 6 (hard gate on S3) settled the policy on 2026-07-31 - consent for **warranty and
service only**, erasure anonymises the person and retains the purchase, and PDPA 2010
s.7(2) requires the notice in **Bahasa Malaysia and English**. What was missing was the
wording itself, and the placeholder was visible in the code:
``CONSENT_NOTICE_VERSION = "2026-08-BM-EN-DRAFT"`` was stamped onto every profile and
resolved to nothing.

**Why a table and not a settings column.** Consent is evidence. The record has to survive
"prove what this person agreed to, eighteen months ago", which means the wording they saw
must still exist unchanged after somebody improves it. A settings string is edited in
place, retroactively rewriting what everybody consented to, silently. So: append-only
versions, publication as a separate act, and a stamp on the profile that resolves to the
exact row.

**The seeded text is a competent draft, not a lawyer's signature.** It covers every element
PDPA s.7(1) enumerates, and the Malay is written as Malay rather than translated word for
word. It still wants review by someone who signs off Malay legal wording for Sorento -
which is now a review of real text in the admin screen rather than a blocking blank.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.consent_notice import ConsentNotice
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

# The collection point S3's consumer portal uses.
CONSUMER_INTAKE_KEY = "consumer_intake"

# `consumer_profiles.consent_notice_version` is VARCHAR(32) (S2b), so the stamp format is
# contract, not taste: a longer scheme truncates or raises per row, at intake, on the write
# that matters. "consumer_intake.v1" is 18 characters and leaves room for four-digit
# versions and a longer key.
STAMP_SEPARATOR = ".v"
MAX_STAMP_LENGTH = 32


def stamp_for(notice: ConsentNotice) -> str:
    """The identifier written onto a consumer profile."""
    return f"{notice.notice_key}{STAMP_SEPARATOR}{notice.version}"


def _purposes() -> frozenset:
    """Fork 6's closed set, read from where it is already declared rather than restated.

    Two copies of a lawful-basis whitelist is how a second value appears quietly in one
    path.
    """
    from app.services.consumer_service import CONSENT_PURPOSES

    return CONSENT_PURPOSES


def create_notice(
    db: Session,
    *,
    notice_key: str = CONSUMER_INTAKE_KEY,
    purpose: str,
    body_en: str = "",
    body_ms: str = "",
    created_by: Optional[str] = None,
) -> ConsentNotice:
    """Add a DRAFT version. Drafts may be empty and are never served."""
    key = str(notice_key or "").strip()
    if not key:
        raise AppException(status_code=422, message="A notice key is required.", code="VALIDATION_ERROR")
    if purpose not in _purposes():
        raise AppException(
            status_code=422,
            message=(
                f"Unknown consent purpose '{purpose}'. Consent here is collected for "
                f"{', '.join(sorted(_purposes()))} only - fork 6. Marketing needs fresh "
                "consent from each person, captured with wording that says so."
            ),
            code="VALIDATION_ERROR",
        )

    highest = (
        db.query(func.max(ConsentNotice.version))
        .filter(ConsentNotice.notice_key == key)
        .scalar()
    )
    notice = ConsentNotice(
        id=str(uuid.uuid4()),
        notice_key=key,
        version=int(highest or 0) + 1,
        purpose=purpose,
        body_en=body_en or "",
        body_ms=body_ms or "",
        is_published=False,
        created_by=created_by,
    )
    if len(stamp_for(notice)) > MAX_STAMP_LENGTH:
        raise AppException(
            status_code=422,
            message=(
                f"The identifier '{stamp_for(notice)}' does not fit the "
                f"{MAX_STAMP_LENGTH}-character column it is written into."
            ),
            code="VALIDATION_ERROR",
        )
    db.add(notice)
    db.flush()
    return notice


def publish_notice(db: Session, notice_id: str, *, published_by: Optional[str] = None) -> ConsentNotice:
    """Make a draft the current notice. Both languages required (s.7(2))."""
    notice = db.query(ConsentNotice).filter(ConsentNotice.id == str(notice_id)).first()
    if notice is None:
        raise AppException(status_code=404, message="Consent notice not found.", code="NOT_FOUND")
    if notice.is_published:
        return notice

    if not (notice.body_en or "").strip():
        raise AppException(
            status_code=422,
            message="The English body is empty. A notice cannot be published without it.",
            code="VALIDATION_ERROR",
        )
    if not (notice.body_ms or "").strip():
        raise AppException(
            status_code=422,
            message=(
                "The Bahasa Malaysia body is empty. PDPA 2010 s.7(2) requires the "
                "collection notice in Bahasa Malaysia as well as English, so an "
                "English-only notice cannot be published."
            ),
            code="VALIDATION_ERROR",
        )

    notice.is_published = True
    notice.published_at = datetime.utcnow()
    notice.published_by = published_by
    db.flush()
    return notice


def update_notice(db: Session, notice_id: str, **fields) -> ConsentNotice:
    """Edit a DRAFT. Refuses a published row.

    Correcting published wording means publishing a new version. Editing in place would
    retroactively rewrite what everybody who already accepted was shown, which is the one
    thing this record exists to prevent.
    """
    notice = db.query(ConsentNotice).filter(ConsentNotice.id == str(notice_id)).first()
    if notice is None:
        raise AppException(status_code=404, message="Consent notice not found.", code="NOT_FOUND")
    if notice.is_published:
        raise AppException(
            status_code=422,
            message=(
                "A published notice is immutable - people consented to these exact words. "
                "Create a new version instead."
            ),
            code="consent_notice_published",
        )
    for field in ("body_en", "body_ms"):
        if field in fields and fields[field] is not None:
            setattr(notice, field, fields[field])
    if "purpose" in fields and fields["purpose"] is not None:
        if fields["purpose"] not in _purposes():
            raise AppException(
                status_code=422,
                message=f"Unknown consent purpose '{fields['purpose']}'.",
                code="VALIDATION_ERROR",
            )
        notice.purpose = fields["purpose"]
    db.flush()
    return notice


def current_notice(db: Session, notice_key: str = CONSUMER_INTAKE_KEY) -> Optional[ConsentNotice]:
    """The highest PUBLISHED version for a key, or None.

    None means the portal has nothing lawful to show and must not collect anything.
    """
    return (
        db.query(ConsentNotice)
        .filter(
            ConsentNotice.notice_key == str(notice_key),
            ConsentNotice.is_published.is_(True),
        )
        .order_by(ConsentNotice.version.desc())
        .first()
    )


def notice_for_stamp(db: Session, stamp: Optional[str]) -> Optional[ConsentNotice]:
    """Resolve what a consumer profile recorded back to the exact wording shown.

    Returns None rather than guessing: a stamp that names no notice is a fact worth
    surfacing, and a nearest-match would answer the evidential question with a lie.
    """
    raw = str(stamp or "").strip()
    if STAMP_SEPARATOR not in raw:
        return None
    key, _, version = raw.rpartition(STAMP_SEPARATOR)
    if not key or not version.isdigit():
        return None
    return (
        db.query(ConsentNotice)
        .filter(ConsentNotice.notice_key == key, ConsentNotice.version == int(version))
        .first()
    )


# --------------------------------------------------------------------------- #
# The seeded wording.
#
# Covers each element PDPA 2010 s.7(1) enumerates: the data collected, the purposes, the
# source, the right of access and correction with a contact point, who it may be disclosed
# to, whether supply is obligatory and what happens if it is not supplied.
#
# The Malay is written as Malay rather than transliterated from the English, because a
# word-for-word rendering of English legalese is not what s.7(2) is for. It still wants a
# review by whoever signs off Malay legal wording for Sorento - but that is now a review of
# real text on a screen, not a blocking blank.
# --------------------------------------------------------------------------- #

CONSUMER_INTAKE_EN = """**How Sorento uses your information**

When you lodge a warranty or service request, Sorento Sdn Bhd collects your name, phone
number, email address (if you give one), the address of the property where the product is
installed, the receipt or invoice you upload, and details of the product and the fault you
report.

**Why we collect it.** We use this information only to verify your warranty, to arrange
and carry out service or a site visit, to keep you updated on your request, and to keep
the records of the purchase and the work done. We do not use it to send you marketing, and
we will not do so unless we ask you separately and you agree.

**Where it comes from.** From you directly, from the receipt or invoice you upload, and
from the dealer or retailer named on that receipt where we need to confirm the purchase.

**Who we may share it with.** The dealer or retailer you bought from, our own service
technicians, and any external contractor we assign to attend to your case - and only so far
as they need it to do that work. We may also disclose it where the law requires us to.

**Is it optional?** Providing this information is voluntary, but we cannot verify a
warranty or arrange a service visit without it, so a request may not be able to proceed.

**Your rights.** You may ask us at any time for a copy of the personal information we hold
about you, ask us to correct it if it is wrong, or ask us to limit how we use it. If you
ask us to erase your information, we will remove your personal details from our records,
but we will keep the record of the purchase and any warranty work, because a warranty may
still be claimed against that purchase years later.

**Contact.** Write to Sorento Sdn Bhd at the contact address published on sorento.com.my,
marked for the attention of the Personal Data Protection officer.

By submitting this form you confirm you have read this notice."""

CONSUMER_INTAKE_MS = """**Cara Sorento menggunakan maklumat anda**

Apabila anda membuat aduan waranti atau permohonan servis, Sorento Sdn Bhd mengumpul nama
anda, nombor telefon, alamat e-mel (jika diberikan), alamat premis tempat produk dipasang,
resit atau invois yang anda muat naik, serta butiran produk dan kerosakan yang anda
laporkan.

**Tujuan pengumpulan.** Maklumat ini digunakan semata-mata untuk mengesahkan waranti anda,
menguruskan dan menjalankan kerja servis atau lawatan ke lokasi, memberi anda maklum balas
mengenai permohonan anda, dan menyimpan rekod pembelian serta kerja yang telah dilakukan.
Maklumat ini tidak digunakan untuk menghantar bahan pemasaran kepada anda, dan kami tidak
akan berbuat demikian melainkan kami memohon kebenaran anda secara berasingan dan anda
bersetuju.

**Sumber maklumat.** Daripada anda sendiri, daripada resit atau invois yang anda muat naik,
dan daripada pengedar atau peniaga yang dinyatakan pada resit tersebut apabila kami perlu
mengesahkan pembelian itu.

**Pihak yang mungkin menerima maklumat anda.** Pengedar atau peniaga tempat anda membeli,
juruteknik servis kami sendiri, dan mana-mana kontraktor luar yang kami tugaskan untuk
mengendalikan kes anda - setakat yang diperlukan untuk melaksanakan kerja tersebut sahaja.
Kami juga boleh mendedahkan maklumat ini apabila dikehendaki oleh undang-undang.

**Adakah ia wajib?** Pemberian maklumat ini adalah secara sukarela, tetapi kami tidak dapat
mengesahkan waranti atau mengaturkan lawatan servis tanpanya, dan permohonan anda mungkin
tidak dapat diteruskan.

**Hak anda.** Anda boleh pada bila-bila masa meminta salinan maklumat peribadi yang kami
simpan mengenai anda, meminta pembetulan jika maklumat itu tidak tepat, atau meminta kami
mengehadkan penggunaannya. Sekiranya anda meminta maklumat anda dihapuskan, kami akan
membuang butiran peribadi anda daripada rekod kami, tetapi rekod pembelian dan kerja
waranti akan dikekalkan, kerana tuntutan waranti masih boleh dibuat terhadap pembelian
tersebut beberapa tahun kemudian.

**Hubungi kami.** Sila hubungi Sorento Sdn Bhd di alamat yang tersiar di sorento.com.my,
untuk perhatian pegawai Perlindungan Data Peribadi.

Dengan menghantar borang ini, anda mengesahkan bahawa anda telah membaca notis ini."""


def seed_consent_notices(db: Session) -> dict:
    """Publish v1 of the consumer intake notice if no published version exists.

    Idempotent and never rewrites published wording: a deploy that re-ran this and changed
    what people had agreed to would be the immutability bug with extra steps.
    """
    from app.services.consumer_service import CONSENT_PURPOSE_WARRANTY_SERVICE

    existing = current_notice(db, CONSUMER_INTAKE_KEY)
    if existing is not None:
        return {"created": 0, "published": 0, "version": existing.version}

    notice = create_notice(
        db,
        notice_key=CONSUMER_INTAKE_KEY,
        purpose=CONSENT_PURPOSE_WARRANTY_SERVICE,
        body_en=CONSUMER_INTAKE_EN,
        body_ms=CONSUMER_INTAKE_MS,
        created_by=None,
    )
    publish_notice(db, str(notice.id))
    return {"created": 1, "published": 1, "version": notice.version}
