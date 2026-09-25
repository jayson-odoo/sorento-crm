"""Chatbot stock ask v2 S3, AC-SA314: an `incoming` entry with a packing list
attaches it to the reply via a `send_attachments` action; without one, no
attachment action. `_stock_ask_packing_list_files` is the seam engine.py's
`tasks_after_reply` call site reads (see engine.py near `_attachments_src`);
`_send_actions` is the existing action-list builder every other domain's
attachment already flows through - this proves the two compose correctly.
"""
from __future__ import annotations

from app.services.chatbot.engine import _send_actions, _stock_ask_packing_list_files
from app.services.chatbot.turn.compose import Answer


def _envelope(entries):
    return {"stock_availability": entries}


def _incoming_entry(**over):
    base = {
        "product_id": "p1",
        "product_code": "SRTW2000",
        "needs_quantity": False,
        "requested_qty": 150,
        "branch": "incoming",
        "eta": "19/10/2026",
        "packing_list": {
            "filename": "packing-list.pdf",
            "file_path": "/attachments/pl.pdf",
            "mime_type": "application/pdf",
        },
    }
    base.update(over)
    return base


def test_incoming_entry_with_packing_list_yields_one_file():
    files = _stock_ask_packing_list_files([_envelope([_incoming_entry()])])
    assert files == [
        {
            "url": "/attachments/pl.pdf",
            "filename": "packing-list.pdf",
            "mimeType": "application/pdf",
        }
    ]


def test_incoming_entry_without_packing_list_yields_nothing():
    """Toggle off (`packing_list_allowed` false): the entry carries no
    `packing_list` key at all, gated server-side - this reads that, no file."""
    entry = _incoming_entry(packing_list=None)
    assert _stock_ask_packing_list_files([_envelope([entry])]) == []


def test_non_incoming_branches_never_attach_even_with_a_stray_packing_list():
    for branch in ("too_big", "in_stock", "no_incoming"):
        entry = _incoming_entry(branch=branch)
        assert _stock_ask_packing_list_files([_envelope([entry])]) == []


def test_multi_product_turn_attaches_only_the_incoming_ones():
    entries = [
        _incoming_entry(product_code="SRT5674", branch="in_stock", packing_list=None),
        _incoming_entry(product_code="SRTW2000", branch="incoming"),
    ]
    files = _stock_ask_packing_list_files([_envelope(entries)])
    assert len(files) == 1
    assert files[0]["url"] == "/attachments/pl.pdf"


def test_send_actions_emits_send_attachments_when_answer_files_carries_the_packing_list():
    files = _stock_ask_packing_list_files([_envelope([_incoming_entry()])])
    answer = Answer(text="SRTW2000 x 150: no stock at the moment, ETA 19/10/2026.")
    answer.files.extend(files)
    reply = {
        "text": answer.text,
        "quick_replies": None,
        "result_set": None,
        "attachments_src": answer.files or None,
    }

    actions = _send_actions(reply, dry_run=False)

    assert [a["kind"] for a in actions] == ["send_message", "send_attachments"]
    assert actions[1]["attachments_src"] == files


def test_send_actions_emits_no_attachment_action_without_one():
    reply = {
        "text": "SRT5674 x 150: no stock and no incoming at the moment, please refer to your salesman.",
        "quick_replies": None,
        "result_set": None,
        "attachments_src": None,
    }

    actions = _send_actions(reply, dry_run=False)

    assert [a["kind"] for a in actions] == ["send_message"]
