"""N8N-RETIRE-A: the no-send replay tool `scripts/crm_sender_replay.py` (RED, tests first).

Contract: documentation/plans/chatbot/n8n-retire-a-no-send-replay.md. The tool is imported by
path. Fixtures are SYNTHETIC (tests/fixtures/crm_sender_replay/), never a real execution.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import socket
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import settings
from app.database import SessionLocal

BACKEND = Path(__file__).resolve().parents[1]
TOOL_PATH = BACKEND / "scripts" / "crm_sender_replay.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "crm_sender_replay"
MSG_URL = "https://api.respond.io/v2/contact/id:zzt-replay-1/message"


def _tool():
    spec = importlib.util.spec_from_file_location("zzt_crm_sender_replay", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def tool():
    return _tool()


def _desc(tool, method, url, body):
    return tool.describe_request(method, url, body)


def _log_count() -> int:
    from app.models.integration import IntegrationLog

    db = SessionLocal()
    try:
        return db.query(IntegrationLog).filter(IntegrationLog.integration_channel == "chatbot_sender").count()
    finally:
        db.close()


def _folder(tmp_path: Path, *names: str, bad: bool = False) -> Path:
    folder = tmp_path / "in"
    folder.mkdir()
    for n in names:
        shutil.copy(FIXTURES / n, folder / n)
    if bad:
        (folder / "unreadable.json").write_text("{not json", encoding="utf-8")
    return folder


def _strings(node: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(node, str):
        out.add(node)
    elif isinstance(node, dict):
        for k, v in node.items():
            out |= _strings(k) | _strings(v)
    elif isinstance(node, list):
        for v in node:
            out |= _strings(v)
    return out


# --- 1. describe_request (AC: descriptor per request) ---------------------------------------

def test_describe_text_counts_utf8_bytes_and_utf16_units(tool):
    d = _desc(tool, "POST", MSG_URL, {"message": {"type": "text", "text": "ab😀"}})
    assert d["kind"] == "text"
    assert d["bytes"] == 2 + 4
    assert d["units"] == 2 + 2
    assert d["buttons"] == 0
    assert d["has_file_name"] is False
    assert d["presigned"] is False


def test_describe_quick_reply_uses_title_and_counts_buttons(tool):
    d = _desc(tool, "POST", MSG_URL,
              {"message": {"type": "quick_reply", "title": "pick😀", "replies": ["a", "b", "c"]}})
    assert d["kind"] == "quick_reply"
    assert d["bytes"] == 4 + 4
    assert d["units"] == 4 + 2
    assert d["buttons"] == 3


def test_describe_attachment_type_file_name_and_presigned(tool):
    plain = _desc(tool, "POST", MSG_URL, {"message": {"type": "attachment", "attachment": {
        "type": "image", "url": "https://files.example.invalid/a.png", "fileName": "a.png"}}})
    assert plain["kind"] == "attachment"
    assert plain["attachment_type"] == "image"
    assert plain["has_file_name"] is True
    assert plain["presigned"] is False
    assert plain["bytes"] == 0 and plain["buttons"] == 0
    signed = _desc(tool, "POST", MSG_URL, {"message": {"type": "attachment", "attachment": {
        "type": "file", "url": "https://files.example.invalid/a.pdf?X-Amz-Signature=zzt&X-Amz-Expires=60"}}})
    assert signed["attachment_type"] == "file"
    assert signed["has_file_name"] is False
    assert signed["presigned"] is True


def test_describe_assign_comment_contact_update_other(tool):
    base = "https://api.respond.io/v2/contact/id:zzt-replay-1"
    assert _desc(tool, "POST", base + "/conversation/assignee", {"assigneeId": 7})["kind"] == "assign"
    c = _desc(tool, "POST", base + "/comment", {"text": "zzt note"})
    assert c["kind"] == "comment"
    u = _desc(tool, "PUT", base, {"custom_fields": [{"name": "zzt", "value": "v"}]})
    assert u["kind"] == "contact_update"
    assert _desc(tool, "GET", base + "/message/list", None)["kind"] == "other"


# --- 2. compare ------------------------------------------------------------------------------

def _two(tool):
    a = _desc(tool, "POST", MSG_URL, {"message": {"type": "text", "text": "x"}})
    b = _desc(tool, "POST", MSG_URL, {"message": {"type": "quick_reply", "title": "y", "replies": ["1", "2"]}})
    return a, b


def test_compare_identical_is_same(tool):
    a, b = _two(tool)
    assert tool.compare([a, b], [dict(a), dict(b)])["verdict"] == "SAME"


def test_compare_different_count_is_diff(tool):
    a, b = _two(tool)
    assert tool.compare([a, b], [a])["verdict"] == "DIFF"


def test_compare_names_index_and_field(tool):
    a, b = _two(tool)
    b2 = dict(b, buttons=b["buttons"] + 1)
    result = tool.compare([a, b], [a, b2])
    assert result["verdict"] == "DIFF"
    flat = json.dumps(result)
    assert "buttons" in flat
    # The differing index (1) is named against the field, and index 0 is not.
    diffs = result.get("differences") or result.get("diffs") or result.get("fields")
    assert diffs is not None, f"compare result must carry per-index differences: {result}"
    as_map = {int(k): v for k, v in diffs.items()} if isinstance(diffs, dict) else {
        int(x["index"]): x["fields"] for x in diffs}
    assert list(as_map) == [1]
    assert list(as_map[1]) == ["buttons"] or as_map[1] == ["buttons"] or set(as_map[1]) == {"buttons"}


# --- 3. block_sockets ------------------------------------------------------------------------

def test_block_sockets_blocks_and_restores(tool):
    with tool.block_sockets():
        with pytest.raises(tool.ReplayNetworkBlocked):
            socket.create_connection(("127.0.0.1", 9))
        with pytest.raises(tool.ReplayNetworkBlocked):
            httpx.get("https://example.invalid")
    # Restored: a plain connect now fails for the normal reason (nothing listens), not the guard.
    with pytest.raises(OSError) as info:
        socket.create_connection(("127.0.0.1", 9), timeout=2)
    assert not isinstance(info.value, tool.ReplayNetworkBlocked)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        socket.create_connection(listener.getsockname(), timeout=2).close()
    finally:
        listener.close()


def test_replay_network_blocked_is_an_exception(tool):
    assert issubclass(tool.ReplayNetworkBlocked, Exception)


# --- 4. main ---------------------------------------------------------------------------------

def _totals(out: str) -> dict[str, int]:
    found = {}
    for key in ("executions", "SAME", "DIFF", "ERROR"):
        m = re.search(rf"{key}\D{{0,6}}(\d+)", out, re.IGNORECASE)
        assert m, f"totals line must carry {key}: {out!r}"
        found[key] = int(m.group(1))
    return found


def test_main_plain_text_is_same(tool, tmp_path, capsys):
    folder = _folder(tmp_path, "plain_text.json")
    assert tool.main(["--in", str(folder)]) == 0
    out = capsys.readouterr().out
    assert _totals(out) == {"executions": 1, "SAME": 1, "DIFF": 0, "ERROR": 0}


def test_main_quick_reply_button_count_is_diff(tool, tmp_path, capsys):
    folder = _folder(tmp_path, "quick_reply_buttons_diff.json")
    assert tool.main(["--in", str(folder)]) == 0
    out = capsys.readouterr().out
    assert _totals(out) == {"executions": 1, "SAME": 0, "DIFF": 1, "ERROR": 0}
    assert "buttons" in out


def test_main_mixed_folder_with_unreadable_file(tool, tmp_path, capsys):
    folder = _folder(tmp_path, "plain_text.json", "quick_reply_buttons_diff.json", bad=True)
    assert tool.main(["--in", str(folder)]) == 0
    out = capsys.readouterr().out
    assert _totals(out) == {"executions": 3, "SAME": 1, "DIFF": 1, "ERROR": 1}


# --- 5. no rows left -------------------------------------------------------------------------

def test_main_leaves_no_integration_log_rows(tool, tmp_path):
    before = _log_count()
    folder = _folder(tmp_path, "plain_text.json", "quick_reply_buttons_diff.json", bad=True)
    assert tool.main(["--in", str(folder)]) == 0
    assert _log_count() == before


# --- 6. output privacy -----------------------------------------------------------------------

@pytest.mark.parametrize("as_json", [False, True])
def test_output_contains_no_input_string_values(tool, tmp_path, capsys, as_json):
    folder = _folder(tmp_path, "plain_text.json", "quick_reply_buttons_diff.json", bad=True)
    report = tmp_path / "report.out"
    args = ["--in", str(folder), "--out", str(report)] + (["--json"] if as_json else [])
    assert tool.main(args) == 0
    printed = capsys.readouterr().out + (report.read_text(encoding="utf-8") if report.exists() else "")
    assert printed.strip(), "the tool must print a report"
    leaves: set[str] = set()
    for f in FIXTURES.glob("*.json"):
        leaves |= _strings(json.loads(f.read_text(encoding="utf-8")))
    # Short structural words (methods, kinds, "text") may legitimately appear; invented values may not.
    secret = {s for s in leaves if s.startswith("zzt") or "example.invalid" in s or "zzt" in s}
    assert secret, "fixtures must carry invented values"
    for s in secret:
        assert s not in printed, f"input value leaked into the report: {s!r}"
    for needle in ("zzt-replay-1", "example.invalid", "😀"):
        assert needle not in printed


# --- 7. loopback refusal ---------------------------------------------------------------------

def test_main_refuses_non_loopback_database(tool, tmp_path, monkeypatch, capsys):
    from app.services.chatbot import crm_sender

    def boom(*a, **k):
        raise AssertionError("nothing may run when the database is not loopback")

    monkeypatch.setattr(crm_sender, "send", boom)
    monkeypatch.setattr(settings, "database_url", "postgresql://u:p@db.example.invalid:5432/zzt", raising=False)
    before = _log_count_safe()
    folder = _folder(tmp_path, "plain_text.json")
    rc = tool.main(["--in", str(folder)])
    assert rc != 0
    out = capsys.readouterr().out
    assert not re.search(r"\bSAME\b\D{0,6}\d", out)
    assert _log_count_safe() == before


def _log_count_safe() -> int:
    return _log_count()


# --- 8. nothing real is constructed or reached ----------------------------------------------

def test_main_never_builds_the_real_respond_client(tool, tmp_path, monkeypatch, capsys):
    from app.services.integration_service import RespondClient

    def real_client(*a, **k):
        raise AssertionError("the real RespondClient must never be built during a replay")

    monkeypatch.setattr(RespondClient, "for_identifier", classmethod(lambda cls, *a, **k: real_client()))
    folder = _folder(tmp_path, "plain_text.json", "quick_reply_buttons_diff.json")
    assert tool.main(["--in", str(folder)]) == 0
    out = capsys.readouterr().out
    # Both executions reached a verdict; neither was an ERROR from the guarded constructor.
    assert _totals(out) == {"executions": 2, "SAME": 1, "DIFF": 1, "ERROR": 0}


def test_fake_client_records_calls_and_answers_success(tool):
    fake = tool.FakeRespondClient()
    resp = fake.send_message("id:zzt-replay-1", "zzt hi")
    assert isinstance(resp, dict) and resp.get("messageId")
    fake.send_quick_reply("id:zzt-replay-1", "zzt pick", ["a", "b"])
    fake.send_attachment("id:zzt-replay-1", "image", "https://files.example.invalid/a.png", None)
    fake.set_conversation_assignee("id:zzt-replay-1", 7)
    fake.create_comment("id:zzt-replay-1", "zzt note")
    fake.update_contact("id:zzt-replay-1", {"custom_fields": []})
    assert len(fake.calls) == 6
