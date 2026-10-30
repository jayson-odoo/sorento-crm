"""AC-S1-12: the offline span-resolve eval CLI on the committed synthetic fixture.

Hand-computed on tests/chatbot/fixtures/span_resolve/: 5 gold mentions (srt, the Chinese word for
water closet, kimlan, mocha, "trading sdn bhd" which names no single customer). Oracle (gold span +
gold type): 4 of 5 right (the generic span is the miss). Extractor spans (--spans) leave out the
water closet mention, so the right-row count is 3 of 5.
"""
from __future__ import annotations

import re
import socket
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parents[1] / "chatbot" / "fixtures" / "span_resolve"


def test_cli_prints_oracle_and_right_row_numbers_offline(monkeypatch, capsys):
    from scripts.chatbot_eval import span_resolve  # red: module does not exist yet

    def _no_network(*a, **k):
        raise AssertionError("span_resolve touched the network or a DB socket")

    monkeypatch.setattr(socket.socket, "connect", _no_network)
    argv = [
        "--lists", str(FIXTURE / "lists.jsonl"),
        "--gold", str(FIXTURE / "gold.jsonl"),
        "--spans", str(FIXTURE / "spans.jsonl"),
        "--half", "all",
    ]
    span_resolve.main(argv)
    out = capsys.readouterr().out.lower()
    oracle = re.search(r"oracle[^\n]*?(\d+)/(\d+)", out)
    assert oracle, out
    assert (oracle.group(1), oracle.group(2)) == ("4", "5")
    right = re.search(r"right[^\n]*?(\d+)/(\d+)", out)
    assert right, out
    assert (right.group(1), right.group(2)) == ("3", "5")


def test_fixture_files_exist_and_are_small():
    for name in ("lists.jsonl", "gold.jsonl", "spans.jsonl"):
        path = FIXTURE / name
        assert path.is_file(), path
        assert len(path.read_text().splitlines()) <= 20
