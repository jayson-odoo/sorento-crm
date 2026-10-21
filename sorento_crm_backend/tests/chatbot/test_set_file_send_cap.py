"""CHAT-RELEASE-1021 crew review fix 1: a described file / certificate set sends one page of files.

SET-STOCK-RENDER (#1744) lists a set longer than one reply instead of withholding it, and the
files of the listed products went out with it: the attachments fetch returns up to 1000 rows
(`fetch.SET_ROW_LIMIT`), so a 60-product certificate set sent 150 files in one WhatsApp turn,
and with the composer on, the files of all 50 fetched products while the page listed 20.

The capped-list rule applies to the files too, with its own page size (`answer.SET_LIST_MAX`,
no new number): a turn sends only the files of the products it lists, never more than one
page of them, whole products only. Composer on, the page ends where its files would pass the
cap and closes with the existing 'Reply "more" to see the next N.'. Composer off, set paging
does not exist ("more" is not a continuation there), so the files stop at the cap and no
"more" line is printed.
"""
from __future__ import annotations

import json
import re
import uuid

import pytest

from tests.chatbot.test_counted_set_no_paging import _bare_verdict, _link_to_default_company, _tap_cert_verdict
from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401 - fixtures used by name
from tests.chatbot.test_lane_require import (
    _cert_fake_call_tool,
    _certificate_for,
    _s4_codes_in,
    _s4_contact_id,
    _s4_envelope,
    _s4_real_resolve_entity,
    _s4_seed_contact,
    _s4_wire_engine,
    _seed_category_and_uom,
    _seed_registry,
    _tap_product,
)

FILES_PER_PRODUCT = 3
MORE = re.compile(r'Reply "more" to see the next (\d+)\.')


def _with_files(inner):
    """`_cert_fake_call_tool`'s rows, plus what the MCP presenter adds to a file row: each
    product's files in `attachments` and their urls on the row (`file_urls`)."""

    def fake(name, args):
        env = json.loads(inner(name, args))
        atts = []
        for it in env["items"]:
            urls = []
            for k in range(FILES_PER_PRODUCT):
                url = f"https://files.zzt.test/{it['title']}-{k}.pdf"
                urls.append(url)
                atts.append(
                    {"url": url, "filename": f"{it['title']}-{k}.pdf", "mimeType": "application/pdf", "attachmentType": "Certification"}
                )
            it["file_urls"] = urls
        env["attachments"] = atts
        return json.dumps(env)

    return fake


def _world(session_factory, monkeypatch, n):
    db = session_factory()
    category_id, uom_id = _seed_category_and_uom(db)
    _seed_registry(db)
    for _ in range(n):
        product = _tap_product(db, category_id=category_id, uom_id=uom_id)
        _certificate_for(db, product_id=product.id)
    db.commit()
    contact_id = _s4_contact_id(f"filecap{uuid.uuid4().hex[:6]}")
    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})
    _link_to_default_company(session_factory, contact_id)
    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_with_files(_cert_fake_call_tool(db)),
    )
    return engine_mod, contact_id


def _say(engine_mod, session_factory, contact_id, n, text):
    turn = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id=f"ZZT-filecap-{contact_id}-{n}", text=text),
        session_factory=session_factory,
    )
    assert turn.status == "done", turn.error
    reply = (turn.reply or {}).get("text") or ""
    sent = [
        str(f.get("url") or f.get("filename") or "")
        for a in turn.actions or []
        if isinstance(a, dict) and a.get("kind") == "send_attachments"
        for f in (a.get("attachments_src") or a.get("attachments") or [])
        if isinstance(f, dict)
    ]
    return reply, sent


def _codes_of(sent):
    return {re.sub(r"-\d+\.pdf$", "", u.rsplit("/", 1)[-1]) for u in sent}


def _gate(monkeypatch, on):
    from tests.chatbot.test_composers_stock_xd import _set_gate

    _set_gate(monkeypatch, on)


def test_composer_off_a_60_product_cert_set_sends_at_most_one_page_of_whole_products_files(
    session_factory, stub_parser, stub_access, monkeypatch
):
    from app.services.chatbot.lanes.business.answer import SET_LIST_MAX

    _gate(monkeypatch, False)
    engine_mod, contact_id = _world(session_factory, monkeypatch, 60)
    stub_parser(_tap_cert_verdict())
    stub_access()
    reply, sent = _say(engine_mod, session_factory, contact_id, 1, "which tap has cert")

    assert 0 < len(sent) <= SET_LIST_MAX, len(sent)
    assert len(sent) == len(set(sent))
    # Whole products only: every product whose files went out sent all of them.
    assert len(sent) == FILES_PER_PRODUCT * len(_codes_of(sent)), sent
    # Only files of products the reply lists.
    assert _codes_of(sent) <= _s4_codes_in(reply), (_codes_of(sent) - _s4_codes_in(reply))
    # "more" does not page a set with the composer off, so no reply offers it.
    assert not MORE.search(reply), reply


def test_composer_on_each_page_sends_the_files_of_its_own_products_and_ends_with_the_more_line(
    session_factory, stub_parser, stub_access, monkeypatch
):
    from app.services.chatbot.lanes.business.answer import SET_LIST_MAX

    _gate(monkeypatch, True)
    engine_mod, contact_id = _world(session_factory, monkeypatch, 60)
    stub_parser(_tap_cert_verdict())
    stub_access()
    reply, sent = _say(engine_mod, session_factory, contact_id, 1, "which tap has cert")

    listed = _s4_codes_in(reply)
    assert 0 < len(sent) <= SET_LIST_MAX, len(sent)
    assert _codes_of(sent) == listed, (_codes_of(sent) ^ listed)
    assert len(sent) == FILES_PER_PRODUCT * len(listed)
    more = MORE.search(reply)
    assert more and int(more.group(1)) == min(SET_LIST_MAX, 60 - len(listed)), reply

    stub_parser(_bare_verdict(continuation=True, user_goal="more"))
    reply2, sent2 = _say(engine_mod, session_factory, contact_id, 2, "more")
    listed2 = _s4_codes_in(reply2)
    assert listed2 and not (listed2 & listed), reply2
    assert 0 < len(sent2) <= SET_LIST_MAX, len(sent2)
    assert _codes_of(sent2) == listed2, (_codes_of(sent2) ^ listed2)


@pytest.mark.parametrize("on", [False, True], ids=["composer_off", "composer_on"])
def test_a_set_whose_files_fit_one_page_sends_them_all(session_factory, stub_parser, stub_access, monkeypatch, on):
    _gate(monkeypatch, on)
    engine_mod, contact_id = _world(session_factory, monkeypatch, 7)
    stub_parser(_tap_cert_verdict())
    stub_access()
    reply, sent = _say(engine_mod, session_factory, contact_id, 1, "which tap has cert")

    assert len(sent) == 7 * FILES_PER_PRODUCT, sent
    assert _codes_of(sent) == _s4_codes_in(reply)
    assert not MORE.search(reply), reply
