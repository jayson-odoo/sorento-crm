"""AGENTIC-KNOWLEDGE P1, reading a file (UAC AC-K5 service half, K7, K8, K9).

Red tests written before `app/services/knowledge_service.py` exists. Three layers:
pure extraction (PDF pages, DOCX sections), pure chunking, and the read pipeline over a
real Postgres schema with fake fetch / OCR / embed seams (no network, no model).
"""
from __future__ import annotations

import io
import zipfile
from decimal import Decimal

import pytest

from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
from app.models.resources import Attachment
from tests._knowledge_seed import (
    DIM,
    one_hot,
    seed_attachment,
    seed_chunk,
    seed_type,
)
from tests._pg_fixture import blank_session

# ---------------------------------------------------------------- document builders


def pdf_bytes(pages: list[str | None]) -> bytes:
    """A PDF with one page per entry: text is drawn on the page, None leaves it blank (a scan)."""
    import pymupdf

    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


TEXT_A = "Annual leave is fourteen days after three years of service."
TEXT_B = "Medical leave needs a certificate from a registered doctor."

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx_bytes(paragraphs: list[tuple[str | None, str | list[str]]]) -> bytes:
    """A minimal .docx. Each entry is (style id or None, text or list of run texts)."""
    body = []
    for style, text in paragraphs:
        runs = text if isinstance(text, list) else [text]
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        run_xml = "".join(f"<w:r><w:t xml:space=\"preserve\">{r}</w:t></w:r>" for r in runs)
        body.append(f"<w:p>{ppr}{run_xml}</w:p>")
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_W}"><w:body>{"".join(body)}</w:body></w:document>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
    return buf.getvalue()


def never_ocr(png: bytes, page_no: int) -> str:
    raise AssertionError("OCR must only be called for a page with no usable text layer")


# ---------------------------------------------------------------- AC-K7 PDF extraction


def test_text_pdf_pages_are_read_from_the_text_layer_without_ocr():
    from app.services.knowledge_service import extract_pdf_pages

    pages = extract_pdf_pages(pdf_bytes([TEXT_A, TEXT_B]), ocr=never_ocr)

    assert [p.page for p in pages] == [1, 2]
    assert TEXT_A in pages[0].text
    assert TEXT_B in pages[1].text
    assert [p.ocr for p in pages] == [False, False]


def test_a_page_without_a_text_layer_goes_to_ocr_and_is_flagged():
    from app.services.knowledge_service import extract_pdf_pages

    calls: list[tuple[bytes, int]] = []

    def ocr(png: bytes, page_no: int) -> str:
        calls.append((png, page_no))
        return "Scanned policy words transcribed by the vision reader"

    pages = extract_pdf_pages(pdf_bytes([TEXT_A, None, TEXT_B]), ocr=ocr)

    assert [p.page for p in pages] == [1, 2, 3]
    assert [p.ocr for p in pages] == [False, True, False]
    assert len(calls) == 1, "only the blank page may be sent to OCR"
    assert calls[0][0].startswith(b"\x89PNG"), "the vision reader is handed a PNG image"
    assert calls[0][1] == pages[1].page, "the page number handed to OCR is the page's own number"
    assert "Scanned policy words" in pages[1].text


def test_ocr_threshold_is_forty_stripped_characters():
    from app.services.knowledge_service import OCR_TEXT_MIN_CHARS, extract_pdf_pages

    assert OCR_TEXT_MIN_CHARS == 40
    seen: list[int] = []

    def ocr(png: bytes, page_no: int) -> str:
        seen.append(page_no)
        return "ocr text for the short page"

    short = "a" * (OCR_TEXT_MIN_CHARS - 1)
    exact = "b" * OCR_TEXT_MIN_CHARS
    pages = extract_pdf_pages(pdf_bytes([short, exact]), ocr=ocr)

    assert [p.ocr for p in pages] == [True, False]
    assert seen == [1]


def test_extract_pdf_pages_rejects_bytes_that_are_not_a_pdf():
    from app.services.knowledge_service import extract_pdf_pages

    with pytest.raises(Exception):
        extract_pdf_pages(b"this is not a pdf at all", ocr=never_ocr)


# ---------------------------------------------------------------- AC-K8 DOCX extraction


def test_docx_headings_start_sections_and_text_before_the_first_heading_is_section_one():
    from app.services.knowledge_service import extract_docx_sections

    content = docx_bytes(
        [
            (None, "Welcome to the company."),
            ("Heading1", "Leave"),
            (None, "Annual leave is fourteen days."),
            ("Heading2", "Medical leave"),
            (None, "Bring a doctor's certificate."),
            ("Heading1", "Conduct"),
            (None, "Be kind."),
        ]
    )

    sections = extract_docx_sections(content)

    assert [s.page for s in sections] == [1, 2, 3, 4]
    assert [s.heading for s in sections] == [None, "Leave", "Medical leave", "Conduct"]
    assert "Welcome to the company." in sections[0].text
    assert "Annual leave is fourteen days." in sections[1].text
    assert "Bring a doctor's certificate." in sections[2].text
    assert "Be kind." in sections[3].text
    assert all(not s.ocr for s in sections)


def test_docx_without_a_preamble_numbers_the_first_heading_section_one():
    from app.services.knowledge_service import extract_docx_sections

    sections = extract_docx_sections(
        docx_bytes([("Heading1", "Leave"), (None, "Fourteen days."), ("Heading1", "Pay"), (None, "Monthly.")])
    )

    assert [s.page for s in sections] == [1, 2]
    assert [s.heading for s in sections] == ["Leave", "Pay"]


def test_docx_other_styles_do_not_start_a_section_and_runs_are_joined_in_order():
    from app.services.knowledge_service import extract_docx_sections

    sections = extract_docx_sections(
        docx_bytes(
            [
                ("Heading1", "Leave"),
                ("Heading3", "A minor heading"),
                (None, ["Annual ", "leave ", "is 14 days."]),
                ("ListParagraph", "second paragraph"),
            ]
        )
    )

    assert len(sections) == 1
    assert sections[0].heading == "Leave"
    text = sections[0].text
    assert "Annual leave is 14 days." in text
    assert text.index("Annual leave is 14 days.") < text.index("second paragraph"), "paragraph order is kept"


def test_docx_with_no_headings_is_one_section_with_no_heading():
    from app.services.knowledge_service import extract_docx_sections

    sections = extract_docx_sections(docx_bytes([(None, "First."), (None, "Second.")]))

    assert len(sections) == 1
    assert sections[0].page == 1
    assert sections[0].heading is None
    assert "First." in sections[0].text and "Second." in sections[0].text


# ---------------------------------------------------------------- AC-K9 chunking


def _numbered_words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i:05d}" for i in range(n))


def test_chunks_never_cross_a_page_and_stay_within_the_size():
    from app.services.knowledge_service import Page, chunk_pages

    pages = [
        Page(page=1, heading="Leave", text=_numbered_words(400, "a")),
        Page(page=2, heading=None, text=_numbered_words(300, "b")),
    ]

    chunks = chunk_pages(pages, size=900, overlap=120)

    assert chunks, "long pages yield chunks"
    assert all(len(c.text) <= 900 for c in chunks)
    for c in chunks:
        words = c.text.split()
        prefixes = {w[0] for w in words}
        assert prefixes == ({"a"} if c.page == 1 else {"b"}), "a chunk holds one page's words only"
    assert {c.page for c in chunks} == {1, 2}
    assert all(c.heading == "Leave" for c in chunks if c.page == 1)
    assert all(c.heading is None for c in chunks if c.page == 2)


def test_chunk_index_is_zero_based_across_the_whole_document():
    from app.services.knowledge_service import Page, chunk_pages

    chunks = chunk_pages(
        [Page(1, None, _numbered_words(300, "a")), Page(2, None, _numbered_words(300, "b"))]
    )

    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert len(chunks) >= 4


def test_consecutive_chunks_of_one_page_overlap_and_nothing_is_lost():
    from app.services.knowledge_service import Page, chunk_pages

    text = _numbered_words(500, "w")
    chunks = chunk_pages([Page(1, None, text)], size=900, overlap=120)

    assert len(chunks) >= 2
    for prev, nxt in zip(chunks, chunks[1:]):
        shared = set(prev.text.split()) & set(nxt.text.split())
        assert shared, "consecutive chunks of a page share the overlap"
    covered = {w for c in chunks for w in c.text.split()}
    assert covered == set(text.split()), "every word of the page lands in some chunk"


def test_custom_size_and_overlap_are_respected():
    from app.services.knowledge_service import Page, chunk_pages

    chunks = chunk_pages([Page(1, None, _numbered_words(200))], size=200, overlap=30)

    assert len(chunks) > 3
    assert all(len(c.text) <= 200 for c in chunks)


def test_a_short_page_is_one_chunk_and_a_blank_page_is_none():
    from app.services.knowledge_service import Page, chunk_pages

    chunks = chunk_pages([Page(1, "Leave", TEXT_A), Page(2, None, "   \n  ")])

    assert len(chunks) == 1
    assert chunks[0].text.strip() == TEXT_A
    assert (chunks[0].index, chunks[0].page, chunks[0].heading) == (0, 1, "Leave")


# ---------------------------------------------------------------- read pipeline (DB)


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def fake_embed(texts):
    """Distinct one-hot vectors, 1536 floats each."""
    return [one_hot(i + 2) for i, _ in enumerate(texts)]


class EmbedSpy:
    def __init__(self):
        self.batches: list[list[str]] = []

    def __call__(self, texts):
        self.batches.append(list(texts))
        return fake_embed(texts)

    @property
    def all_texts(self) -> list[str]:
        return [t for b in self.batches for t in b]


def _knowledge_chunks(db, attachment) -> list[EmbeddingChunk]:
    return (
        db.query(EmbeddingChunk)
        .filter(EmbeddingChunk.source_type == "knowledge", EmbeddingChunk.source_id == str(attachment.id))
        .order_by(EmbeddingChunk.chunk_index)
        .all()
    )


def _knowledge_docs(db, attachment) -> list[EmbeddingDocument]:
    return (
        db.query(EmbeddingDocument)
        .filter(EmbeddingDocument.source_type == "knowledge", EmbeddingDocument.source_id == str(attachment.id))
        .all()
    )


def _fresh(db, attachment) -> Attachment:
    db.expire_all()
    return db.query(Attachment).filter(Attachment.id == attachment.id).one()


def test_reading_a_pdf_writes_a_gemini_knowledge_document_and_chunks(db):
    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db), "Employee Handbook 2026.pdf")
    embed = EmbedSpy()
    ocr_calls: list[int] = []

    def ocr(png, page_no):
        ocr_calls.append(page_no)
        return "Scanned page about overtime pay rates for weekends"

    ks.read_attachment(
        db, str(att.id), fetch=lambda a: pdf_bytes([TEXT_A, None, TEXT_B]), ocr=ocr, embed=embed
    )

    row = _fresh(db, att)
    assert row.ai_read_status == "done", row.ai_read_error
    assert row.ai_read_pages == 3
    assert row.ai_read_ocr_pages == 1
    assert abs(Decimal(str(row.ai_read_cost_usd)) - ks.OCR_COST_PER_PAGE_USD) < Decimal("0.0001")
    assert row.ai_read_at is not None
    assert row.ai_read_error in (None, "")

    docs = _knowledge_docs(db, att)
    assert len(docs) == 1
    assert docs[0].source_type == ks.KNOWLEDGE_SOURCE == "knowledge"
    assert docs[0].company_id == row.company_id

    chunks = _knowledge_chunks(db, att)
    assert chunks
    assert {c.model_name for c in chunks} == {ks.KNOWLEDGE_MODEL} == {"gemini-embedding-001"}
    assert {c.embedding_provider for c in chunks} == {"gemini"}
    assert all(c.is_current for c in chunks)
    assert all(c.company_id == row.company_id for c in chunks)
    assert all(len(list(c.embedding)) == DIM for c in chunks)
    for c in chunks:
        meta = c.metadata_json
        assert meta["attachment_id"] == str(att.id)
        assert meta["page"] in (1, 2, 3)
        assert "heading" in meta
    assert {c.metadata_json["page"] for c in chunks} == {1, 2, 3}
    assert any("overtime pay" in c.chunk_text for c in chunks), "the OCR page text is searchable too"
    assert sorted(embed.all_texts) == sorted(c.chunk_text for c in chunks), "each chunk is embedded once"
    assert len(ocr_calls) == 1


def test_cost_is_ocr_pages_times_the_named_estimate(db):
    from app.services import knowledge_service as ks

    assert Decimal(str(ks.OCR_COST_PER_PAGE_USD)) > 0
    att = seed_attachment(db, seed_type(db))

    ks.read_attachment(
        db,
        str(att.id),
        fetch=lambda a: pdf_bytes([None, TEXT_A, None]),
        ocr=lambda png, n: "A scanned page with plenty of words in it for the test",
        embed=fake_embed,
    )

    row = _fresh(db, att)
    assert row.ai_read_ocr_pages == 2
    assert abs(Decimal(str(row.ai_read_cost_usd)) - ks.OCR_COST_PER_PAGE_USD * 2) < Decimal("0.0001")


def test_a_text_only_pdf_costs_nothing_and_never_calls_ocr(db):
    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db))

    ks.read_attachment(db, str(att.id), fetch=lambda a: pdf_bytes([TEXT_A, TEXT_B]), ocr=never_ocr, embed=fake_embed)

    row = _fresh(db, att)
    assert (row.ai_read_status, row.ai_read_pages, row.ai_read_ocr_pages) == ("done", 2, 0)
    assert Decimal(str(row.ai_read_cost_usd)) == 0


def test_reading_a_docx_uses_sections_as_pages_and_keeps_the_heading(db):
    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db), "Leave Policy.docx")
    content = docx_bytes(
        [
            ("Heading1", "Leave"),
            (None, "Annual leave is fourteen days after three years."),
            ("Heading1", "Conduct"),
            (None, "Treat everyone with respect."),
        ]
    )

    ks.read_attachment(db, str(att.id), fetch=lambda a: content, ocr=never_ocr, embed=fake_embed)

    row = _fresh(db, att)
    assert (row.ai_read_status, row.ai_read_pages, row.ai_read_ocr_pages) == ("done", 2, 0)
    chunks = _knowledge_chunks(db, att)
    by_page = {c.metadata_json["page"]: c.metadata_json["heading"] for c in chunks}
    assert by_page == {1: "Leave", 2: "Conduct"}


def test_reading_again_replaces_the_previous_knowledge_chunks(db):
    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db))
    first = "First edition says staff get ten days of annual leave in total."
    second = "Second edition says staff get fourteen days of annual leave in total."

    ks.read_attachment(db, str(att.id), fetch=lambda a: pdf_bytes([first]), ocr=never_ocr, embed=fake_embed)
    ks.read_attachment(db, str(att.id), fetch=lambda a: pdf_bytes([second]), ocr=never_ocr, embed=fake_embed)

    assert len(_knowledge_docs(db, att)) == 1, "one knowledge document per attachment"
    texts = " ".join(c.chunk_text for c in _knowledge_chunks(db, att) if c.is_current)
    assert "Second edition" in texts
    assert "First edition" not in texts, "the previous reading is replaced, not kept beside it"
    current = [c for c in _knowledge_chunks(db, att) if c.is_current]
    assert [c.chunk_index for c in current] == list(range(len(current))), "no duplicate chunk indexes"
    assert _fresh(db, att).ai_read_status == "done"


def test_an_unsupported_extension_is_marked_unsupported_and_writes_nothing(db):
    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db), "Price list.xlsx")

    ks.read_attachment(db, str(att.id), fetch=lambda a: b"PK", ocr=never_ocr, embed=fake_embed)

    row = _fresh(db, att)
    assert row.ai_read_status == "unsupported"
    assert _knowledge_chunks(db, att) == []
    assert _knowledge_docs(db, att) == []


def test_a_fetch_failure_marks_failed_with_a_readable_error_and_writes_nothing(db):
    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db))

    def fetch(a):
        raise RuntimeError("the bucket is unreachable")

    ks.read_attachment(db, str(att.id), fetch=fetch, ocr=never_ocr, embed=fake_embed)

    row = _fresh(db, att)
    assert row.ai_read_status == "failed"
    assert row.ai_read_error and row.ai_read_error.strip()
    assert _knowledge_chunks(db, att) == []


def test_an_embed_failure_marks_failed_and_leaves_no_half_written_chunks(db):
    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db))

    def embed(texts):
        raise RuntimeError("embedding provider returned 500")

    ks.read_attachment(db, str(att.id), fetch=lambda a: pdf_bytes([TEXT_A, TEXT_B]), ocr=never_ocr, embed=embed)

    row = _fresh(db, att)
    assert row.ai_read_status == "failed"
    assert row.ai_read_error
    assert _knowledge_chunks(db, att) == []
    assert _knowledge_docs(db, att) == []


def test_a_corrupt_pdf_marks_failed(db):
    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db))

    ks.read_attachment(db, str(att.id), fetch=lambda a: b"not a pdf", ocr=never_ocr, embed=fake_embed)

    assert _fresh(db, att).ai_read_status == "failed"
    assert _knowledge_chunks(db, att) == []


def test_the_stored_error_carries_no_key_fragment(db):
    """AC-K9: a readable error, no key fragments (a provider error often echoes the key)."""
    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db))
    secret = "AIzaSyZZTSECRET0123456789abcdefghij"

    def embed(texts):
        raise RuntimeError(f"400 Bad Request for url https://example.test/embed?key={secret}")

    ks.read_attachment(db, str(att.id), fetch=lambda a: pdf_bytes([TEXT_A]), ocr=never_ocr, embed=embed)

    row = _fresh(db, att)
    assert row.ai_read_status == "failed"
    assert row.ai_read_error
    assert secret not in row.ai_read_error
    assert "AIzaSy" not in row.ai_read_error


# ---------------------------------------------------------------- queue_read (AC-K5, service half)


@pytest.fixture
def enqueued(monkeypatch):
    from app.services import knowledge_service as ks

    calls: list[str] = []
    monkeypatch.setattr(ks, "_enqueue", lambda attachment_id: calls.append(str(attachment_id)))
    return calls


@pytest.mark.parametrize("audience", ["staff", "dealer", "public"])
def test_queue_read_queues_a_file_whose_type_is_ai_readable(db, enqueued, audience):
    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db, audience=audience))

    assert ks.queue_read(db, att) is True

    assert _fresh(db, att).ai_read_status == "queued"
    assert enqueued == [str(att.id)]


def test_queue_read_ignores_a_file_whose_type_is_off(db, enqueued):
    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db, audience="off"))

    assert ks.queue_read(db, att) is False

    assert _fresh(db, att).ai_read_status is None
    assert enqueued == []


def test_queue_read_ignores_a_file_with_no_type(db, enqueued):
    from app.services import knowledge_service as ks

    att = seed_attachment(db, None)

    assert ks.queue_read(db, att) is False
    assert _fresh(db, att).ai_read_status is None
    assert enqueued == []


def test_constants_match_the_contract():
    from app.services import knowledge_service as ks

    assert ks.KNOWLEDGE_SOURCE == "knowledge"
    assert ks.KNOWLEDGE_MODEL == "gemini-embedding-001"
    assert ks.AI_AUDIENCES == ("off", "staff", "dealer", "public")
    assert ks.READ_PERMISSION == "resource.attachments.view"
    assert ks.MAX_REQUEUE_PER_SAVE == 500
    assert ks.KNOWLEDGE_TOOL == "crm_knowledge_search"
    assert ks.KNOWLEDGE_PROTOCOL_HEADER == "KNOWLEDGE PROTOCOL"
    assert 0 < ks.KNOWLEDGE_SIMILARITY_FLOOR < 1
    assert Decimal(str(ks.OCR_COST_PER_PAGE_USD)) > 0


def test_knowledge_is_not_a_records_source():
    """AC-K10 constant half: the records reader's keep set must never list `knowledge`."""
    from app.services.embedding_settings import RECORD_KEEP_SET

    assert "knowledge" not in RECORD_KEEP_SET


# ================================================================ FIX ROUND 1 (review findings)

# ---------------------------------------------------------------- SS2: caps and the knowledge queue


def test_the_read_caps_and_queue_are_named_constants():
    from app.services import knowledge_service as ks

    assert ks.MAX_PAGES == 300
    assert ks.MAX_OCR_PAGES == 100
    assert ks.MAX_DOCX_XML_BYTES == 20 * 1024 * 1024
    assert ks.MAX_PAGE_AREA_PT2 > 0
    assert ks.QUEUE == "knowledge"
    assert ks.STALE_AFTER_SECONDS > 0


def test_the_worker_drains_the_knowledge_queue_as_a_batch_queue():
    import worker

    assert ("knowledge", "batch") in tuple(worker.QUEUES)


def test_a_pdf_over_the_page_cap_fails_with_a_readable_error_and_writes_nothing(db, monkeypatch):
    import re

    from app.services import knowledge_service as ks

    monkeypatch.setattr(ks, "MAX_PAGES", 2)
    att = seed_attachment(db, seed_type(db))

    ks.read_attachment(db, str(att.id), fetch=lambda a: pdf_bytes([TEXT_A, TEXT_B, TEXT_A]), ocr=never_ocr, embed=fake_embed)

    row = _fresh(db, att)
    assert row.ai_read_status == "failed"
    assert re.search(r"page", row.ai_read_error or "", re.I)
    assert re.search(r"limit|more than|too many|maximum|at most", row.ai_read_error or "", re.I)
    assert _knowledge_chunks(db, att) == [] and _knowledge_docs(db, att) == []


def test_more_scanned_pages_than_the_ocr_cap_fails_and_ocr_stops_at_the_cap(db, monkeypatch):
    from app.services import knowledge_service as ks

    monkeypatch.setattr(ks, "MAX_OCR_PAGES", 1)
    att = seed_attachment(db, seed_type(db))
    calls: list[int] = []

    def ocr(png, page_no):
        calls.append(page_no)
        return "A scanned page with plenty of words in it for the test"

    ks.read_attachment(db, str(att.id), fetch=lambda a: pdf_bytes([None, None, None]), ocr=ocr, embed=fake_embed)

    row = _fresh(db, att)
    assert row.ai_read_status == "failed"
    assert row.ai_read_error
    assert len(calls) <= 1, "the vision reader is never called past the cap"
    assert _knowledge_chunks(db, att) == [] and _knowledge_docs(db, att) == []


def test_a_page_larger_than_the_area_cap_is_not_sent_to_ocr(db, monkeypatch):
    from app.services import knowledge_service as ks

    monkeypatch.setattr(ks, "MAX_PAGE_AREA_PT2", 1000)  # a default page is about 500,000 pt2

    pages = ks.extract_pdf_pages(pdf_bytes([None]), ocr=never_ocr)

    assert all(not p.ocr for p in pages), "an oversize page is treated as having no text"


def test_a_docx_whose_document_xml_is_over_the_cap_fails_and_writes_nothing(db, monkeypatch):
    from app.services import knowledge_service as ks

    monkeypatch.setattr(ks, "MAX_DOCX_XML_BYTES", 100)
    att = seed_attachment(db, seed_type(db), "Big.docx")
    content = docx_bytes([("Heading1", "Leave"), (None, "Annual leave is fourteen days after three years. " * 10)])

    ks.read_attachment(db, str(att.id), fetch=lambda a: content, ocr=never_ocr, embed=fake_embed)

    row = _fresh(db, att)
    assert row.ai_read_status == "failed"
    assert row.ai_read_error
    assert _knowledge_chunks(db, att) == [] and _knowledge_docs(db, att) == []


def test_extract_docx_sections_refuses_an_oversize_document_xml(monkeypatch):
    from app.services import knowledge_service as ks

    monkeypatch.setattr(ks, "MAX_DOCX_XML_BYTES", 100)

    with pytest.raises(Exception):
        ks.extract_docx_sections(docx_bytes([(None, "word " * 100)]))


# ---------------------------------------------------------------- SN1: no key fragment in any log line


def test_a_failed_read_logs_no_key_fragment(db, caplog):
    import logging

    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db))

    def embed(texts):
        raise RuntimeError("400 Bad Request for url https://example.test/embed?key=AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKE12345")

    with caplog.at_level(logging.DEBUG):
        ks.read_attachment(db, str(att.id), fetch=lambda a: pdf_bytes([TEXT_A]), ocr=never_ocr, embed=embed)

    formatter = logging.Formatter()
    rendered = "\n".join(formatter.format(r) for r in caplog.records)
    assert "AIza" not in rendered
    assert _fresh(db, att).ai_read_status == "failed"


# ---------------------------------------------------------------- RS1: a file that changed, a doc that appeared


def test_a_file_that_changes_while_it_is_read_writes_nothing(db):
    """The hash read at the start must still be the file's hash at write time."""
    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db))
    att.file_hash = "hash-one"
    att.ai_read_status = "queued"
    db.flush()

    def embed(texts):
        att.file_hash = "hash-two"  # a replace upload lands during the embedding call
        db.flush()
        return fake_embed(texts)

    ks.read_attachment(db, str(att.id), fetch=lambda a: pdf_bytes([TEXT_A]), ocr=never_ocr, embed=embed)

    row = _fresh(db, att)
    assert _knowledge_chunks(db, att) == [], "stale content is never written"
    assert _knowledge_docs(db, att) == []
    assert row.ai_read_status != "done"
    assert row.ai_read_status != "failed" or not row.ai_read_error


def test_a_knowledge_document_that_appears_during_the_read_is_replaced_not_a_duplicate_key(db):
    """Two reads of one file racing: the second must replace, never fail on the unique index."""
    from app.services import knowledge_service as ks

    att = seed_attachment(db, seed_type(db))

    def embed(texts):
        seed_chunk(db, att, one_hot(5), text="written by the other read", index=0)
        return fake_embed(texts)

    ks.read_attachment(db, str(att.id), fetch=lambda a: pdf_bytes([TEXT_A]), ocr=never_ocr, embed=embed)

    row = _fresh(db, att)
    assert row.ai_read_status == "done", row.ai_read_error
    low = (row.ai_read_error or "").lower()
    for fragment in ("duplicate", "integrityerror", "insert into", "select "):
        assert fragment not in low
    assert len(_knowledge_docs(db, att)) == 1
    texts = " ".join(c.chunk_text for c in _knowledge_chunks(db, att) if c.is_current)
    assert "written by the other read" not in texts
    assert TEXT_A in texts


# ---------------------------------------------------------------- RB1: re-queue across companies


def test_turning_a_type_on_queues_files_of_every_company_under_a_single_company_scope(db, enqueued):
    from sqlalchemy import text as sql

    from app.models.base import set_company_scope
    from app.services import knowledge_service as ks
    from tests._knowledge_seed import SORENTO_COMPANY_ID, seed_company

    other = seed_company(db)
    att_type = seed_type(db, audience="staff")
    mine = seed_attachment(db, att_type, "mine.pdf", company_id=SORENTO_COMPANY_ID)
    theirs = seed_attachment(db, att_type, "theirs.pdf", company_id=other)
    shared = seed_attachment(db, att_type, "shared.pdf")
    db.execute(sql("UPDATE attachments SET company_id = NULL WHERE id = :i"), {"i": str(shared.id)})
    db.flush()

    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))
    ks.queue_type_files(db, str(att_type.id))

    assert sorted(enqueued) == sorted([str(mine.id), str(theirs.id), str(shared.id)])


# ---------------------------------------------------------------- bulk import


def test_the_bulk_import_queues_a_file_of_a_readable_type_and_skips_an_off_type(db, enqueued):
    from app.tasks import import_tasks

    readable = seed_attachment(db, seed_type(db, audience="staff"), "a.pdf")
    off = seed_attachment(db, seed_type(db, audience="off"), "b.pdf")

    import_tasks._queue_ai_read(db, readable)
    import_tasks._queue_ai_read(db, off)

    assert enqueued == [str(readable.id)]
    assert _fresh(db, readable).ai_read_status == "queued"
    assert _fresh(db, off).ai_read_status is None
