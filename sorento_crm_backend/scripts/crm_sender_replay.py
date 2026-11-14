#!/usr/bin/env python3
"""No-send replay of past n8n sender runs against the CRM sender (N8N-RETIRE-A).

Run from sorento_crm_backend/:
    SORENTO_ENV_FILE=<local env> venv/bin/python scripts/crm_sender_replay.py --in <folder> [--out report.md] [--json]

Spec: documentation/plans/chatbot/n8n-retire-a-no-send-replay.md. Nothing leaves the process:
Python sockets are blocked for the run, the respond.io client is a fake, and every database
write sits inside one transaction that is rolled back. The report carries kinds, counts and
lengths only, never a message text, id, url, name or phone.
"""
from __future__ import annotations

import argparse
import contextlib
import ipaddress
import json
import logging
import os
import socket
import sys
import uuid
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIELDS = ("kind", "bytes", "units", "buttons", "attachment_type", "has_file_name", "presigned")
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", ""}
FAKE_PRESIGN_URL = "https://replay.invalid/presigned?X-Amz-Signature=replay&X-Amz-Expires=3600"


class ReplayNetworkBlocked(Exception):
    """Raised by any Python socket connect while the replay runs."""


_BLOCKED_METHODS = ("connect", "connect_ex", "sendto", "sendmsg")


@contextlib.contextmanager
def block_sockets() -> Iterator[None]:
    """Every Python socket entry point that could reach out raises `ReplayNetworkBlocked`."""
    def blocked(*_a: Any, **_k: Any) -> None:
        raise ReplayNetworkBlocked("network access is blocked during a replay")

    saved = {name: getattr(socket.socket, name) for name in _BLOCKED_METHODS}
    real_create, real_gai = socket.create_connection, socket.getaddrinfo
    for name in _BLOCKED_METHODS:
        setattr(socket.socket, name, blocked)
    socket.create_connection = blocked  # type: ignore[assignment]
    socket.getaddrinfo = blocked  # type: ignore[assignment]
    try:
        yield
    finally:
        for name, original in saved.items():
            setattr(socket.socket, name, original)
        socket.create_connection, socket.getaddrinfo = real_create, real_gai  # type: ignore[assignment]


def _u16(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _base() -> dict[str, Any]:
    return {"kind": "other", "bytes": 0, "units": 0, "buttons": 0,
            "attachment_type": None, "has_file_name": False, "presigned": False}


def describe_request(method: str, url: str, body: Any) -> dict[str, Any]:
    """One respond.io request as a descriptor: kinds, counts and lengths only."""
    out = _base()
    path = (url or "").split("?", 1)[0].rstrip("/")
    body = body if isinstance(body, dict) else {}
    if path.endswith("/message") and method.upper() == "POST":
        message = body.get("message") if isinstance(body.get("message"), dict) else {}
        mtype = message.get("type")
        if mtype == "text":
            text = str(message.get("text") or "")
            out.update(kind="text", bytes=len(text.encode("utf-8")), units=_u16(text))
        elif mtype == "quick_reply":
            title = str(message.get("title") or "")
            replies = message.get("replies")
            out.update(kind="quick_reply", bytes=len(title.encode("utf-8")), units=_u16(title),
                       buttons=len(replies) if isinstance(replies, list) else 0)
        elif mtype == "attachment":
            att = message.get("attachment") if isinstance(message.get("attachment"), dict) else {}
            link = str(att.get("url") or "")
            out.update(kind="attachment", attachment_type=att.get("type"),
                       has_file_name=bool(att.get("fileName")),
                       presigned=("X-Amz-Signature" in link or "Signature=" in link))
    elif path.endswith("/conversation/assignee"):
        out["kind"] = "assign"
    elif path.endswith("/comment"):
        out["kind"] = "comment"
    elif method.upper() in ("PUT", "PATCH", "POST") and "/contact/" in path and "custom_fields" in body:
        out["kind"] = "contact_update"
    return out


def compare(n8n: list[dict[str, Any]], crm: list[dict[str, Any]]) -> dict[str, Any]:
    """SAME when both sides match request for request, in order; else DIFF with the fields per index."""
    differences: dict[int, list[str]] = {}
    for i in range(min(len(n8n), len(crm))):
        fields = [f for f in FIELDS if n8n[i].get(f) != crm[i].get(f)]
        if fields:
            differences[i] = fields
    same = not differences and len(n8n) == len(crm)
    return {"verdict": "SAME" if same else "DIFF", "differences": differences,
            "request_counts": [len(n8n), len(crm)]}


class FakeRespondClient:
    """Records every call as the respond.io request it would be and answers success."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self._n = 0

    def _record(self, method: str, ident: str, tail: str, body: dict | None) -> dict:
        from app.services.integration_service import respond_endpoint  # the one Respond host source (#2272)

        self.calls.append((method, respond_endpoint(f"/v2/contact/{ident}{tail}"), body))
        self._n += 1
        return {"messageId": 1_700_000_000_000_000 + self._n}

    def send_message(self, ident: str, text: str) -> dict:
        return self._record("POST", ident, "/message", {"message": {"type": "text", "text": text}})

    def send_quick_reply(self, ident: str, text: str, replies: list[str]) -> dict:
        return self._record("POST", ident, "/message",
                            {"message": {"type": "quick_reply", "title": text, "replies": list(replies)}})

    def send_attachment(self, ident: str, kind: str, url: str, caption: str | None = None,
                        filename: str | None = None) -> dict:
        att: dict[str, Any] = {"type": kind, "url": url}
        if filename:
            att["fileName"] = filename
        return self._record("POST", ident, "/message", {"message": {"type": "attachment", "attachment": att}})

    def set_conversation_assignee(self, ident: str, assignee: Any) -> dict:
        return self._record("POST", ident, "/conversation/assignee", {"assigneeId": assignee})

    def create_comment(self, ident: str, text: str) -> dict:
        return self._record("POST", ident, "/comment", {"text": text})

    def update_contact(self, ident: str, payload: dict) -> dict:
        return self._record("PUT", ident, "", payload)

    def list_messages(self, ident: str, limit: int = 20, cursor: Any = None) -> dict:
        return {"items": []}

    def get_contact_by_identifier(self, ident: str) -> dict:
        return {"id": ident, "custom_fields": []}


def _is_loopback(host: str) -> bool:
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _loopback_database() -> bool:
    """The configured target is loopback: no host or hostaddr override in the query, and an
    empty host does not fall through to PGHOST / PGHOSTADDR pointing elsewhere."""
    from sqlalchemy.engine import make_url

    from app.config import settings

    try:
        url = make_url(settings.database_url)
    except Exception:  # noqa: BLE001
        return False
    if any(key in url.query for key in ("host", "hostaddr")):
        return False
    host = url.host or ""
    if not host:
        for name in ("PGHOSTADDR", "PGHOST"):
            value = os.environ.get(name, "")
            if value and not value.startswith("/") and not _is_loopback(value):
                return False
        return True
    return _is_loopback(host)


def _server_addr(connection: Any) -> str | None:
    """The address the connected server reports for this session (NULL on a unix socket)."""
    from sqlalchemy import text

    value = connection.execute(text("SELECT inet_server_addr()")).scalar()
    return None if value is None else str(value)


class _Refused(Exception):
    pass


def _crm_requests(session: Any, sender_input: dict[str, Any]) -> list[dict[str, Any]]:
    from app.services.chatbot import crm_sender

    fake = FakeRespondClient()
    if sender_input.get("is_test"):
        return []
    turn_id = str(uuid.uuid4())  # log rows need a UUID; the input's own id is never stored
    real_presign, real_link = crm_sender._presign, crm_sender._link_message_id
    crm_sender._presign = lambda db, url, filename=None: FAKE_PRESIGN_URL  # type: ignore[assignment]
    crm_sender._link_message_id = lambda *a, **k: None  # type: ignore[assignment]
    try:
        class _Held:
            def __getattr__(self, name: str) -> Any:
                return getattr(session, name)

            def close(self) -> None:
                pass

        crm_sender.send(
            lambda: _Held(),
            turn_id=turn_id,
            contact_id=str(sender_input.get("contact_id") or ""),
            actions=list(sender_input.get("actions") or []),
            ctx=sender_input.get("ctx"),
            client=fake,
        )
    finally:
        crm_sender._presign, crm_sender._link_message_id = real_presign, real_link  # type: ignore[assignment]
    return [describe_request(m, u, b) for m, u, b in fake.calls]


def _replay_one(session: Any, path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        sender_input = data["sender_input"]
        n8n = [describe_request(str(r.get("method") or ""), str(r.get("url") or ""), r.get("body"))
               for r in data.get("respond_requests") or []]
    except Exception:  # noqa: BLE001 - unreadable input is an ERROR, never printed
        return {"verdict": "ERROR"}
    try:
        crm = _crm_requests(session, sender_input)
    except Exception:  # noqa: BLE001
        return {"verdict": "ERROR"}
    return compare(n8n, crm)


def run(folder: Path) -> dict[str, Any]:
    from sqlalchemy.orm import Session

    from app.database import engine

    results: list[dict[str, Any]] = []
    connection = engine.connect()
    try:
        addr = _server_addr(connection)
        connection.rollback()
        if addr is not None and not _is_loopback(addr):
            raise _Refused()
    except BaseException:
        connection.close()
        raise
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    previous_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)  # the sender's log lines carry message text and ids
    try:
        with block_sockets():
            for path in sorted(folder.glob("*.json")):
                results.append(_replay_one(session, path))
    finally:
        logging.disable(previous_disable)
        session.close()
        transaction.rollback()
        connection.close()
    totals = {"executions": len(results), "SAME": 0, "DIFF": 0, "ERROR": 0}
    per_field = {f: 0 for f in FIELDS}
    items = []
    for number, res in enumerate(results, 1):
        totals[res["verdict"]] += 1
        for fields in (res.get("differences") or {}).values():
            for f in fields:
                per_field[f] += 1
        items.append({"n": number, **res,
                      "differences": {str(k): v for k, v in (res.get("differences") or {}).items()}})
    return {"totals": totals, "per_field": per_field, "executions": items}


def render(report: dict[str, Any]) -> str:
    t = report["totals"]
    lines = [f"executions: {t['executions']}", f"SAME: {t['SAME']}", f"DIFF: {t['DIFF']}", f"ERROR: {t['ERROR']}", ""]
    for item in report["executions"]:
        line = f"#{item['n']} {item['verdict']}"
        if item["verdict"] == "DIFF":
            counts = item.get("request_counts")
            if counts and counts[0] != counts[1]:
                line += f" requests n8n={counts[0]} crm={counts[1]}"
            for idx, fields in item["differences"].items():
                line += f" [request {idx}: {', '.join(fields)}]"
        lines.append(line)
    lines += ["", "requests differing per field:"]
    lines += [f"  {f}: {n}" for f, n in report["per_field"].items()]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="No-send replay of n8n sender executions")
    parser.add_argument("--in", dest="folder", required=True)
    parser.add_argument("--out")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not _loopback_database():
        print("Refused: the database host is not loopback, nothing was run.")
        return 2
    try:
        report = run(Path(args.folder))
    except _Refused:
        print("Refused: the database server address is not loopback, nothing was run.")
        return 2
    text = json.dumps(report, indent=2) + "\n" if args.json else render(report)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PGGSSENCMODE", "disable")
    sys.exit(main())
