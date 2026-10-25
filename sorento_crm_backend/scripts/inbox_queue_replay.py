"""CHAT-INBOX-QUEUE hand test: replay four scenarios through a running copy's real queue.

Plan `documentation/plans/chatbot/PLAN-chat-inbox-queue.md`. Run by crew on the Mac against a
running test copy (backend + sweeper, and its RQ worker for the photo scenario):

    cd sorento_crm_backend
    venv/bin/python scripts/inbox_queue_replay.py --env-file .env.<copy> \\
        --api http://localhost:8106 --port 8399 --out /tmp/inbox-replay.md

**No respond.io traffic, no real contact.** For the run only it points the copy at a local
server (127.0.0.1:`--port`) and restores every value afterwards, also on Ctrl-C or an error:

* the default respond workspace: `base_url` (the drain's takeover lookup,
  `RespondClient.get_contact_by_identifier`, is answered locally with no takeover flag), a
  throwaway API key (so no real key is ever sent anywhere), and the chatbot sender URL + key;
* `system_settings`: direct ingress mode `contacts` listing ONE synthetic contact
  (`zzt-replay-<hex>`, phone `+600...`, which no real number uses), and one extra webhook
  signing key appended to the existing ones (respond.io's own keep verifying);
* a synthetic `respond_contacts` row (AI allowed, photos allowed), removed at the end with
  everything it produced (`--keep-rows` keeps them for the trace screen).

**Where the replies are read.** The CRM's outbound URL guard refuses any loopback or private
sender URL by design (SSRF rule, `app/services/outbound_url_guard.py`), so no sender POST can
reach a local capture. The drain still stamps, attempts and LOGS every POST
(`integration_log`, channel `chatbot_sender`, with the full body) at the moment it would have
left; this script reads that log. Each reply's row therefore ends `failed` /
`send_unconfirmed` in this run: that is the guard refusing the local URL, not the queue.
The local `/sender` endpoint still records any POST that does arrive.

Scenarios (fresh message ids: a respond.io id IS its send time in epoch microseconds, so the
120 s stale gate passes): s1 a 10-message burst delivered shuffled; s2 a photo sent before a
text but delivered after it (its read needs the copy's RQ worker); s3 one message delivered
twice through the webhook and once through `/chat/turn`; s4 a 6-message burst, then a backend
restart (`--no-restart` skips the wait). Stdlib plus the repo's own modules; never imports
`app.services.chatbot`.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import random
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

SENDER_KEY_HEADER = "X-Chatbot-Sender-Key"
SENDER_CHANNEL = "chatbot_sender"
# A 1x1 JPEG, so a worker that fetches the photo gets an image.
PHOTO_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP////////////////////////////////////////////////////////"
    "//////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
)
OVERALL_SECONDS = 300.0


def last4(value: str | None) -> str:
    return f"...{value[-4:]}" if value else "(none)"


# --------------------------------------------------------------------------- #
# The local stand-in for respond.io and the sender
# --------------------------------------------------------------------------- #


class Local:
    def __init__(self, port: int, sender_key: str) -> None:
        self.port = port
        self.sender_key = sender_key
        self.lock = threading.Lock()
        self.lookups = 0
        self.media_fetches = 0
        self.sender_posts: list[dict[str, Any]] = []
        local = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def _answer(self, code: int, body: bytes, kind: str = "application/json") -> None:
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802 - http.server's name
                if self.path.startswith("/v2/contact/"):
                    ident = self.path.split("/v2/contact/", 1)[1].split("?", 1)[0]
                    ident = ident.split(":", 1)[1] if ident.startswith("id:") else ident
                    with local.lock:
                        local.lookups += 1
                    record = {
                        "id": ident,
                        "firstName": "Zzt",
                        "lastName": "Replay",
                        "custom_fields": [{"name": "is_human_intervened", "value": "false"}],
                    }
                    self._answer(200, json.dumps(record).encode())
                elif self.path.startswith("/media/"):
                    with local.lock:
                        local.media_fetches += 1
                    self._answer(200, PHOTO_JPEG, "image/jpeg")
                else:
                    self._answer(404, b"{}")

            def do_POST(self) -> None:  # noqa: N802
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if not self.path.startswith("/sender"):
                    self._answer(404, b"{}")
                    return
                try:
                    body = json.loads(raw or b"{}")
                except ValueError:
                    body = {}
                with local.lock:
                    local.sender_posts.append(
                        {
                            "at": time.time(),
                            "key_ok": self.headers.get(SENDER_KEY_HEADER) == local.sender_key,
                            "turn_id": str(body.get("turn_id")),
                            "actions": body.get("actions") or [],
                        }
                    )
                self._answer(200, b'{"ok": true}')

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


# --------------------------------------------------------------------------- #
# HTTP to the copy (no proxy, ever)
# --------------------------------------------------------------------------- #

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http(method: str, url: str, body: bytes | None = None, headers: dict | None = None, timeout: float = 15) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def healthy(api: str) -> bool:
    try:
        return http("GET", f"{api}/health", timeout=3)[0] == 200
    except Exception:  # noqa: BLE001 - down is the answer
        return False


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #


class Replay:
    def __init__(self, args: argparse.Namespace) -> None:
        from app.config import settings

        self.args = args
        self.api = args.api.rstrip("/")
        self.contact = f"zzt-replay-{uuid.uuid4().hex[:10]}"
        self.phone = f"+600{random.randrange(10**8, 10**9)}"
        self.signing_key = secrets.token_urlsafe(33)  # 44 chars, like a respond.io key
        self.sender_key = f"zzt-replay-{secrets.token_hex(12)}"
        self.api_key = getattr(settings, "external_api_key", None) or ""
        self.local = Local(args.port, self.sender_key)
        self.saved: dict[str, Any] = {}
        self.contact_pk: str | None = None
        self.labels: dict[str, str] = {}  # message id -> label
        self.notes: list[str] = []

    # ---------------------------------------------------------------- setup

    def setup(self) -> None:
        from sqlalchemy import text

        from app.config import settings
        from app.database import SessionLocal
        from app.models.respond_workspace import RespondWorkspace
        from app.models.user import SystemSetting
        from app.utils.field_encryption import decrypt_secret, encrypt_secret

        db = SessionLocal()
        try:
            row = db.query(SystemSetting).first()
            workspace = (
                db.query(RespondWorkspace).filter(RespondWorkspace.is_default.is_(True)).first()
            )
            # A bare database (no settings row, no default workspace) gets one for the run,
            # removed again at the end.
            created = {"settings": row is None, "workspace": workspace is None}
            if row is None:
                row = SystemSetting(id=str(uuid.uuid4()), name="ZZT replay")
                db.add(row)
            if workspace is None:
                workspace = RespondWorkspace(
                    space_id="zzt-replay", name="ZZT replay", is_default=True, is_active=True,
                    api_key_ciphertext=encrypt_secret("zzt-replay-placeholder"),
                )
                db.add(workspace)
            db.flush()
            self.saved = {
                "created": created,
                "settings_id": str(row.id),
                "mode": row.chatbot_direct_ingress_mode,
                "contacts": row.chatbot_direct_ingress_contacts,
                "webhook_secret": row.respond_webhook_secret_ciphertext,
                "workspace_id": str(workspace.id),
                "base_url": workspace.base_url,
                "api_key": workspace.api_key_ciphertext,
                "sender_url": workspace.chatbot_sender_url,
                "sender_key": workspace.chatbot_sender_key_ciphertext,
            }
            existing = ""
            if row.respond_webhook_secret_ciphertext:
                try:
                    existing = decrypt_secret(row.respond_webhook_secret_ciphertext) or ""
                except ValueError:
                    existing = ""
            if not existing:
                existing = getattr(settings, "respond_webhook_secret", "") or ""
            keys = [k for k in existing.replace(",", " ").split() if k][:9]
            row.respond_webhook_secret_ciphertext = encrypt_secret(",".join([*keys, self.signing_key]))
            row.chatbot_direct_ingress_mode = "contacts"
            row.chatbot_direct_ingress_contacts = self.contact
            workspace.base_url = self.local.base
            workspace.api_key_ciphertext = encrypt_secret(f"zzt-replay-not-a-key-{secrets.token_hex(8)}")
            workspace.chatbot_sender_url = f"https://127.0.0.1:{self.args.port}/sender"
            workspace.chatbot_sender_key_ciphertext = encrypt_secret(self.sender_key)
            self.contact_pk = str(
                db.execute(
                    text(
                        "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, chatbot_allowed) "
                        "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), true) RETURNING id"
                    ),
                    {"cid": self.contact, "phone": self.phone, "sv": json.dumps({"variables": {}})},
                ).scalar()
            )
            db.execute(
                text(
                    "INSERT INTO contact_media_limit (id, contact_id, modality, is_allowed) "
                    "VALUES (gen_random_uuid(), :pk, 'image', true)"
                ),
                {"pk": self.contact_pk},
            )
            db.commit()
        finally:
            db.close()
        print(f"contact {self.contact}; sender key {last4(self.sender_key)}; local server {self.local.base}")

    def restore(self) -> None:
        from sqlalchemy import text

        from app.database import SessionLocal
        from app.models.respond_workspace import RespondWorkspace
        from app.models.user import SystemSetting

        if not self.saved:
            return
        db = SessionLocal()
        try:
            row = db.query(SystemSetting).filter(SystemSetting.id == self.saved["settings_id"]).first()
            if row is not None and self.saved["created"]["settings"]:
                db.delete(row)
            elif row is not None:
                row.chatbot_direct_ingress_mode = self.saved["mode"]
                row.chatbot_direct_ingress_contacts = self.saved["contacts"]
                row.respond_webhook_secret_ciphertext = self.saved["webhook_secret"]
            workspace = db.query(RespondWorkspace).filter(RespondWorkspace.id == self.saved["workspace_id"]).first()
            if workspace is not None and self.saved["created"]["workspace"]:
                db.delete(workspace)
            elif workspace is not None:
                workspace.base_url = self.saved["base_url"]
                workspace.api_key_ciphertext = self.saved["api_key"]
                workspace.chatbot_sender_url = self.saved["sender_url"]
                workspace.chatbot_sender_key_ciphertext = self.saved["sender_key"]
            db.commit()
            print("restored: direct ingress mode and contacts, webhook keys, workspace base URL, API key, sender")
            if not self.args.keep_rows:
                self._remove_rows(db, text)
        finally:
            db.close()
        try:
            from app.services.queue_service import redis_conn

            for key in list(redis_conn.scan_iter(f"*{self.contact}*")):
                redis_conn.delete(key)
        except Exception:  # noqa: BLE001
            pass

    def _remove_rows(self, db: Any, text: Any) -> None:
        cid, pk = self.contact, self.contact_pk
        db.execute(text("DELETE FROM chatbot.turns WHERE contact_respond_id = :c"), {"c": cid})
        db.execute(text("DELETE FROM integration_log WHERE external_reference = :c"), {"c": cid})
        db.execute(text("DELETE FROM chat_histories WHERE contact_id = :c"), {"c": cid})
        if pk:
            db.execute(
                text(
                    "DELETE FROM media_extraction_job WHERE usage_id IN "
                    "(SELECT id FROM contact_media_usage WHERE contact_id = :pk)"
                ),
                {"pk": pk},
            )
            db.execute(text("DELETE FROM contact_media_usage WHERE contact_id = :pk"), {"pk": pk})
            db.execute(text("DELETE FROM contact_media_limit WHERE contact_id = :pk"), {"pk": pk})
        db.execute(text("DELETE FROM respond_contacts WHERE respond_io_id = :c"), {"c": cid})
        db.commit()
        print(f"removed the synthetic contact {cid} and its rows")

    # ---------------------------------------------------------------- messages

    def new_message(self, label: str, sent_at: float) -> int:
        mid = int(sent_at * 1_000_000)
        self.labels[str(mid)] = label
        return mid

    def body(self, mid: int, *, photo: bool = False) -> dict[str, Any]:
        label = self.labels[str(mid)]
        if photo:
            inner: dict[str, Any] = {
                "type": "attachment",
                "attachment": {"type": "image", "url": f"{self.local.base}/media/{label}.jpg", "mimeType": "image/jpeg", "size": len(PHOTO_JPEG)},
            }
        else:
            inner = {"type": "text", "text": f"price for SRTWC8517 ({label})"}
        return {
            "event_type": "message.received",
            "event_id": f"evt-{mid}",
            "contact": {"id": self.contact, "firstName": "Zzt", "lastName": "Replay", "phone": self.phone},
            "message": {
                "messageId": mid,
                "contactId": self.contact,
                "channelId": 12,
                "traffic": "incoming",
                "timestamp": mid // 1000,
                "message": inner,
                "sender": {"source": "contact"},
            },
            "channel": {"id": 12, "name": "ZZT WA", "source": "whatsapp_cloud"},
        }

    def burst(self, bodies: list[dict]) -> list[int]:
        """Deliver bodies at once (one thread each, started in this order), so the burst
        reaches the copy inside a few milliseconds, as a real one does."""
        codes: list[int] = [0] * len(bodies)

        def deliver(i: int, body: dict) -> None:
            codes[i] = self.webhook(body)

        threads = [threading.Thread(target=deliver, args=(i, b)) for i, b in enumerate(bodies)]
        for thread in threads:
            thread.start()
            time.sleep(0.005)
        for thread in threads:
            thread.join(30)
        return codes

    def webhook(self, body: dict) -> int:
        raw = json.dumps(body).encode()
        signature = hmac.new(self.signing_key.encode(), raw, hashlib.sha256).hexdigest()
        status, _ = http(
            "POST",
            f"{self.api}/api/v1/public/respond/webhook",
            raw,
            {"Content-Type": "application/json", "x-respond-signature": signature},
        )
        return status

    def chat_turn(self, body: dict) -> tuple[int, Any]:
        envelope = {
            "message": body,
            "contact": {
                "id": self.contact,
                "firstName": "Zzt",
                "custom_fields": [{"name": "is_human_intervened", "value": "false"}],
            },
            "ingress": "webhook",
        }
        status, raw = http(
            "POST",
            f"{self.api}/api/v1/external/chat/turn",
            json.dumps({"envelope": envelope}).encode(),
            {"Content-Type": "application/json", "X-API-Key": self.api_key},
        )
        try:
            return status, json.loads(raw or b"{}")
        except ValueError:
            return status, {}

    # ---------------------------------------------------------------- capture

    def captures(self) -> list[dict[str, Any]]:
        """Every sender POST attempt the copy made for this contact, in order, from its own
        log, plus any POST the local server received."""
        from sqlalchemy import text

        from app.database import SessionLocal

        db = SessionLocal()
        try:
            rows = db.execute(
                text(
                    "SELECT l.business_id, l.request_payload, l.status, l.created_at, t.message_id, t.status, t.stage "
                    "FROM integration_log l LEFT JOIN chatbot.turns t ON t.id = l.business_id "
                    "WHERE l.integration_channel = :ch AND l.external_reference = :c "
                    "ORDER BY l.created_at, l.id"
                ),
                {"ch": SENDER_CHANNEL, "c": self.contact},
            ).all()
        finally:
            db.close()
        out = []
        for turn_id, payload, log_status, at, message_id, turn_status, turn_stage in rows:
            try:
                actions = json.loads(payload or "{}").get("actions") or []
            except ValueError:
                actions = []
            texts = [str(a.get("text") or "") for a in actions if isinstance(a, dict) and a.get("text")]
            out.append(
                {
                    "turn_id": str(turn_id),
                    "message_id": str(message_id) if message_id is not None else None,
                    "label": self.labels.get(str(message_id), "?"),
                    "at": at,
                    "log_status": log_status,
                    "row": f"{turn_status}/{turn_stage}",
                    "text": (texts[0] if texts else "(no text action)")[:120].replace("\n", " "),
                }
            )
        return out

    def wait_for(self, mids: list[int], deadline: float, settle: float = 3.0) -> list[dict[str, Any]]:
        wanted = {str(m) for m in mids}
        while time.monotonic() < deadline:
            seen = {c["message_id"] for c in self.captures()}
            if wanted <= seen:
                time.sleep(settle)  # a second (double) answer gets its chance to show
                break
            time.sleep(1.0)
        return [c for c in self.captures() if c["message_id"] in wanted]

    # ---------------------------------------------------------------- scenarios

    def s1(self, deadline: float) -> dict[str, Any]:
        base = time.time() - 2
        mids = [self.new_message(f"s1-{i:02d}", base + 0.1 * i) for i in range(10)]
        order = list(mids)
        random.Random(20261025).shuffle(order)
        if order[0] == mids[0]:
            order.append(order.pop(0))
        codes = self.burst([self.body(m) for m in order])
        got = self.wait_for(mids, deadline)
        answered = [c["message_id"] for c in got]
        checks = [
            ("replies in send order", answered == [str(m) for m in mids]),
            ("one reply per message", len(answered) == len(set(answered)) == len(mids)),
        ]
        return {"title": "s1: 10-message burst, delivered shuffled", "codes": codes, "got": got, "checks": checks,
                "delivered": [self.labels[str(m)] for m in order]}

    def s2(self, deadline: float) -> dict[str, Any]:
        base = time.time() - 3
        photo = self.new_message("s2-photo", base)
        text_mid = self.new_message("s2-text", base + 1)
        codes = [self.webhook(self.body(text_mid))]
        time.sleep(0.5)
        codes.append(self.webhook(self.body(photo, photo=True)))
        got = self.wait_for([photo, text_mid], deadline)
        answered = [c["message_id"] for c in got]
        checks = [
            ("the photo answered before the text", answered[:2] == [str(photo), str(text_mid)]),
            ("one reply per message", sorted(answered) == sorted([str(photo), str(text_mid)])),
        ]
        return {"title": "s2: photo sent first, delivered after the text", "codes": codes, "got": got, "checks": checks,
                "delivered": ["s2-text", "s2-photo"]}

    def s3(self, deadline: float) -> dict[str, Any]:
        mid = self.new_message("s3-dup", time.time() - 1)
        body = self.body(mid)
        codes = [self.webhook(body), self.webhook(body)]
        status, answer = self.chat_turn(body)
        codes.append(status)
        got = self.wait_for([mid], deadline, settle=5.0)
        checks = [
            ("/chat/turn answered duplicate with nothing to send",
             status == 200 and answer.get("duplicate") is True and answer.get("actions") == []),
            ("exactly one reply", len(got) == 1),
        ]
        return {"title": "s3: one message, webhook twice + /chat/turn", "codes": codes, "got": got, "checks": checks,
                "delivered": ["s3-dup (webhook)", "s3-dup (webhook again)", "s3-dup (/chat/turn)"]}

    def s4(self, deadline: float) -> dict[str, Any]:
        base = time.time() - 2
        mids = [self.new_message(f"s4-{i}", base + 0.2 * i) for i in range(6)]
        order = list(mids)
        random.Random(1025).shuffle(order)
        codes = self.burst([self.body(m) for m in order])
        restarted = None
        if not self.args.no_restart:
            print("\n>>> RESTART THE COPY BACKEND NOW (stop it and start it again). Waiting for /health to go down...")
            went_down = self._wait_health(False, 180)
            came_back = went_down and self._wait_health(True, 240)
            restarted = bool(went_down and came_back)
            print(">>> backend is back; collecting" if restarted else ">>> no restart seen; collecting anyway")
            deadline = max(deadline, time.monotonic() + 120)
        got = self.wait_for(mids, deadline)
        answered = [c["message_id"] for c in got]
        checks = [
            ("every message answered once", sorted(answered) == sorted(str(m) for m in mids) and len(answered) == len(mids)),
            ("replies in send order", answered == [str(m) for m in mids]),
        ]
        if restarted is not None:
            checks.insert(0, ("the backend restarted mid-burst", restarted))
        return {"title": "s4: 6-message burst, backend restart mid-burst"
                + (" (restart skipped: --no-restart)" if self.args.no_restart else ""),
                "codes": codes, "got": got, "checks": checks, "delivered": [self.labels[str(m)] for m in order]}

    def _wait_health(self, up: bool, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if healthy(self.api) == up:
                return True
            time.sleep(0.5)
        return False

    # ---------------------------------------------------------------- report

    def report(self, results: list[dict[str, Any]]) -> str:
        lines = [
            "# CHAT-INBOX-QUEUE replay",
            "",
            f"Copy `{self.api}`; synthetic contact `{self.contact}`; local server `{self.local.base}`.",
            "Replies are read from the copy's own sender log (`integration_log`, channel `chatbot_sender`): the",
            "outbound URL guard refuses the local sender URL, so nothing left the machine and each reply row ends",
            "`failed/send_unconfirmed` in this run by design. A reply logged before an earlier-sent message even",
            "arrived cannot be put behind it (the queue orders what it has); real turns take seconds, a burst",
            "arrives in milliseconds.",
            f"Local server: {self.local.lookups} contact lookups answered, {self.local.media_fetches} photo fetches, "
            f"{len(self.local.sender_posts)} sender POSTs received.",
            "",
        ]
        for result in results:
            lines += [f"## {result['title']}", "", f"Delivered: {', '.join(result['delivered'])}",
                      f"HTTP codes: {result['codes']}", "", "| # | answers | logged at | send | row | reply |",
                      "|---|---|---|---|---|---|"]
            for i, c in enumerate(result["got"], 1):
                at = c["at"].strftime("%H:%M:%S.%f")[:-3] if hasattr(c["at"], "strftime") else str(c["at"])
                lines.append(f"| {i} | {c['label']} | {at} | {c['log_status']} | {c['row']} | {c['text']} |")
            if not result["got"]:
                lines.append("| - | (no reply captured) | | | | |")
            lines.append("")
            for name, ok in result["checks"]:
                lines.append(f"- {'PASS' if ok else 'FAIL'}: {name}")
            lines.append("")
        lines += self.notes
        return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--env-file", required=True, help="the copy's SORENTO_ENV_FILE")
    parser.add_argument("--api", required=True, help="the copy's backend, e.g. http://localhost:8106")
    parser.add_argument("--port", type=int, default=8399, help="port for the local stand-in server")
    parser.add_argument("--out", required=True, help="markdown report path")
    parser.add_argument("--scenarios", default="s1,s2,s3,s4")
    parser.add_argument("--no-restart", action="store_true", help="s4 without waiting for a restart")
    parser.add_argument("--keep-rows", action="store_true", help="keep the synthetic contact's rows")
    args = parser.parse_args()

    os.environ["SORENTO_ENV_FILE"] = args.env_file
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if not healthy(args.api.rstrip("/")):
        print(f"{args.api}/health does not answer 200; start the copy first.")
        return 2

    replay = Replay(args)
    results: list[dict[str, Any]] = []
    replay.local.start()
    try:
        replay.setup()
        started = time.monotonic()
        for name in [s.strip() for s in args.scenarios.split(",") if s.strip()]:
            remaining = OVERALL_SECONDS - (time.monotonic() - started)
            print(f"running {name} ...")
            result = getattr(replay, name)(time.monotonic() + max(30.0, min(120.0, remaining)))
            results.append(result)
            for check, ok in result["checks"]:
                print(f"  {'PASS' if ok else 'FAIL'}: {check}")
    except KeyboardInterrupt:
        replay.notes.append("Interrupted (Ctrl-C) before every scenario finished.")
        print("interrupted; restoring")
    finally:
        try:
            replay.restore()
        finally:
            replay.local.stop()
            text = replay.report(results)
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"report written to {args.out}")
    failed = [c for r in results for c in r["checks"] if not c[1]]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
