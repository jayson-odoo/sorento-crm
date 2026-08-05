"""The contact-facing stock inquiry reply text.

Two defects in the message the contact actually received:

    There is a response to your stock inquiry fe-sorento.foundryx.my/...: list price rm 1.00 per unit

1. The ``:`` sits immediately after the URL, so WhatsApp's autolinker swallows it
   into the href and the link opens as invalid.
2. The link is the read-only ``/view/stock-inquiry?token=`` page built on whatever
   origin the staff browser happened to be on, rather than the interactive portal
   link the backend already resolves for the template's ``portal_url`` variable.

Both came from the frontend composing the message itself
(``StockInquiryDetail.tsx``/``StockInquiryForm.tsx``) and posting the whole string
as ``purchasing_response``. Composition moves to the backend, which already has the
portal link, and the URL goes last on its own line so nothing can glue to it.

Pure functions -- no database, no fixtures.
"""
from __future__ import annotations

from app.services.procurement_service import StockInquiryService

PORTAL = "https://fe-sorento.foundryx.my/portal/stock-inquiry/abc123"
LEGACY_VIEW = "https://fe-sorento.foundryx.my/view/stock-inquiry?token=deadbeef"
BODY = "list price rm 1.00 per unit"


def _compose(body: str, url: str) -> str:
    return StockInquiryService.compose_stock_inquiry_reply_message(body, url)


def test_url_is_last_and_nothing_follows_it():
    """The reported bug: a ':' directly after the URL breaks the link."""
    message = _compose(BODY, PORTAL)

    assert message.rstrip().endswith(PORTAL), f"URL is not last:\n{message}"
    assert f"{PORTAL}:" not in message, "a colon is glued to the URL - WhatsApp will break the link"
    after = message.split(PORTAL, 1)[1]
    assert after.strip() == "", f"trailing text after the URL: {after!r}"


def test_url_sits_on_its_own_line():
    """Separated by a blank line, so no adjacent word can be absorbed into the href."""
    message = _compose(BODY, PORTAL)
    lines = [line for line in message.split("\n") if line.strip()]
    assert lines[-1].strip() == PORTAL, f"last non-empty line is not the bare URL: {lines[-1]!r}"


def test_the_body_still_reads_as_a_sentence():
    """The colon belongs after the preamble, not after the link."""
    message = _compose(BODY, PORTAL)
    assert message.startswith("There is a response to your stock inquiry:")
    assert BODY in message


def test_no_url_leaves_no_dangling_whitespace():
    """A contact with no portal link still gets a clean message."""
    message = _compose(BODY, "")
    assert message == "There is a response to your stock inquiry:\n" + BODY
    assert not message.endswith("\n")


def test_a_legacy_frontend_composed_string_is_normalised_not_doubled():
    """Old FE (or a saved row) posts the whole composed string; recomposing must not
    stack a second preamble or keep the stale view link."""
    legacy = f"There is a response to your stock inquiry {LEGACY_VIEW}: {BODY}"

    bare = StockInquiryService._bare_stock_inquiry_reply(legacy)
    assert bare == BODY, f"preamble not stripped: {bare!r}"

    message = _compose(bare, PORTAL)
    assert message.count("There is a response to your stock inquiry") == 1
    assert LEGACY_VIEW not in message, "stale read-only view link survived"
    assert message.rstrip().endswith(PORTAL)


def test_bare_text_from_the_new_frontend_passes_through_untouched():
    """The new FE sends only the purchasing wording, so stripping is a no-op."""
    assert StockInquiryService._bare_stock_inquiry_reply(BODY) == BODY


def test_attachment_sentence_stays_with_the_body_above_the_url():
    """The D1-D4 attachment sentence is part of the update core, not a trailer."""
    body_with_sentence = f"{BODY}\nPlease see 2 attachments in the response: 2"
    message = _compose(body_with_sentence, PORTAL)

    assert message.index(body_with_sentence) < message.index(PORTAL)
    assert message.rstrip().endswith(PORTAL)
