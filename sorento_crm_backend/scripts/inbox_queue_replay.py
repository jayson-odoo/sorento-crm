"""CHAT-INBOX-QUEUE hand test: replay four scenarios through a running copy's real queue.

Plan `documentation/plans/chatbot/PLAN-chat-inbox-queue.md`. Run by crew on the Mac against a
running LOCAL test copy (backend + sweeper, and its RQ worker for the photo scenario):

    cd sorento_crm_backend
    venv/bin/python scripts/inbox_queue_replay.py --env-file .env.<copy> \\
        --api http://localhost:<copy backend port> --port 8399 \\
        --out /tmp/inbox-replay.md --state-file /tmp/inbox-replay-state.json

After a hard stop (kill -9, a crash) put the copy back with
`--env-file .env.<copy> --restore-from /tmp/inbox-replay-state.json`.

**Each turn calls the copy's LLM provider** (its parser and lanes run for real), so a run costs
what that many real turns cost on the copy's keys; the provider and model are printed first.

**Refuses anything but a local copy** (`check_target`): the database host must be loopback, the
database must not be the shared dev DB nor have `prod` in its name, `DATABASE_URL` /
`DIRECT_URL` must not be exported in the shell (the env file is the one source), and `--api`
must be http(s) on localhost. It also refuses when an earlier run was not cleaned up
(`detect_leftover`) or when the copy already holds the maximum number of webhook keys (the
tool could not add one that verifies without dropping one of respond.io's).

**No respond.io traffic, no real contact.** For the run only it points the copy at a local
server on 127.0.0.1:`--port`, which answers the drain's takeover lookup
(`RespondClient.get_contact_by_identifier`) with no takeover flag:

* the default respond workspace: `base_url` (the local server), a throwaway API key (so no
  real key is ever sent anywhere), and a chatbot sender URL + key;
* `system_settings`: direct ingress mode `contacts` listing ONE synthetic contact
  (`zzt-replay-<hex>`, phone `+000...`, which no normalizer turns into a real number), and one
  extra webhook signing key appended to the existing ones (respond.io's own keep verifying);
* a synthetic `respond_contacts` row (AI allowed, photos allowed).

The originals (ciphertexts only) go to `--state-file` (mode 0600) BEFORE the first change.
Restore, at the end and on Ctrl-C, SIGTERM, SIGHUP or an error: first one commit closes every
open row of the synthetic contact (`failed`) and sets the switch back; then it waits (bounded)
until the contact's drain mutex is gone; only then one transaction writes the workspace back
and removes the run's rows (`--keep-rows` keeps them, closed). The state file is removed last.

**Where the replies are read.** The CRM's outbound URL guard refuses any loopback or private
sender URL by design (SSRF rule, `app/services/outbound_url_guard.py`), so no sender POST can
leave; the drain still stamps, attempts and LOGS every POST (`integration_log`, channel
`chatbot_sender`, with the full body) at the moment it would have left, and the report is read
from that log. Each reply's row therefore ends `failed` / `send_unconfirmed` in this run.

Scenarios (fresh message ids: a respond.io id IS its send time in epoch microseconds, so the
120 s stale gate passes): s1 a 10-message burst delivered shuffled; s2 a photo sent before a
text but delivered after it (its read is attempted by the copy's RQ worker and fails, since
the photo URL is a closed local port: what s2 shows is the photo answered first); s3 one
message delivered twice through the webhook and once through `/chat/turn`; s4 a 6-message
burst, then a backend restart (`--no-restart` skips the wait). Stdlib plus the repo's own
modules; never imports `app.services.chatbot`.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import random
import secrets
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

SENDER_CHANNEL = "chatbot_sender"
OVERALL_SECONDS = 300.0
DRAIN_LET_GO_SECONDS = 180.0
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
SHARED_DEV_DATABASE = "sorento_cagent_stack"
# `app.api.v1.public.respond_webhook.MAX_KEYS`: the webhook verifies against the first ten.
MAX_WEBHOOK_KEYS = 10
CONTACT_PREFIX = "zzt-replay-"


def last4(value: str | None) -> str:
    return f"...{value[-4:]}" if value else "(none)"


class Refused(Exception):
    """A reason this run must not start (nothing has been written)."""


class Abort(Exception):
    """The run stops at once (the restore still runs)."""


# --------------------------------------------------------------------------- #
# The target guard
# --------------------------------------------------------------------------- #


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def check_target(*, database_url: str, api: str, environ: Any) -> list[str]:
    """The reasons to refuse this target (empty means go): only a LOCAL copy."""
    reasons: list[str] = []
    db_host = _host(database_url or "")
    if db_host not in LOOPBACK_HOSTS:
        reasons.append("the database host is not loopback: this tool only rewires a local copy")
    name = (urlsplit(database_url or "").path or "").lstrip("/").split("?", 1)[0]
    if name == SHARED_DEV_DATABASE:
        reasons.append(f"the database is the shared dev DB ({SHARED_DEV_DATABASE})")
    if "prod" in name.lower():
        reasons.append("the database name contains 'prod'")
    for var in ("DATABASE_URL", "DIRECT_URL"):
        if environ.get(var):
            reasons.append(f"{var} is exported in this shell; unset it, the env file is the one source")
    try:
        scheme = urlsplit(api or "").scheme.lower()
    except ValueError:
        scheme = ""
    if scheme not in ("http", "https") or _host(api or "") not in LOOPBACK_HOSTS:
        reasons.append("--api must be http(s) on localhost, 127.0.0.1 or [::1]")
    return reasons


def _env_file_value(path: str, name: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                key, sep, value = line.strip().partition("=")
                if sep and key.strip() == name:
                    return value.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def detect_leftover(db: Any, *, state_file: str) -> list[str]:
    """The reasons an earlier run was not cleaned up (empty means clean)."""
    from app.models.respond_workspace import RespondWorkspace
    from app.models.user import SystemSetting

    reasons: list[str] = []
    if state_file and os.path.exists(state_file):
        reasons.append(f"an earlier run's state file is still there ({state_file}); restore with --restore-from")
    workspace = db.query(RespondWorkspace).filter(RespondWorkspace.is_default.is_(True)).first()
    if workspace is not None:
        if _host(workspace.base_url or "") in LOOPBACK_HOSTS:
            reasons.append("the default workspace's base_url points at a loopback host (an earlier run?)")
        if _host(workspace.chatbot_sender_url or "") in LOOPBACK_HOSTS:
            reasons.append("the default workspace's sender URL points at a loopback host (an earlier run?)")
    row = db.query(SystemSetting).first()
    if row is not None and CONTACT_PREFIX in (row.chatbot_direct_ingress_contacts or ""):
        reasons.append("the direct-ingress contact list holds a zzt-replay- contact (an earlier run?)")
    return reasons


# --------------------------------------------------------------------------- #
# The local stand-in for respond.io's contact lookup
# --------------------------------------------------------------------------- #


class Local:
    def __init__(self, port: int) -> None:
        self.port = port
        self.lock = threading.Lock()
        self.lookups = 0
        local = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def _answer(self, code: int, body: bytes) -> None:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802 - http.server's name
                if not self.path.startswith("/v2/contact/"):
                    self._answer(404, b"{}")
                    return
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

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        if self.thread.is_alive():
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
# Restore (shared by the run, the signal handlers and --restore-from)
# --------------------------------------------------------------------------- #


def _drain_gone(contact: str, timeout: float) -> bool:
    from app.services.queue_service import redis_conn

    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if not redis_conn.exists(f"chatbot:drain:{contact}"):
                return True
        except Exception:  # noqa: BLE001 - keep waiting; redis may be restarting
            pass
        time.sleep(0.2)
    return False


def _remove_rows(db: Any, contact: str) -> None:
    from sqlalchemy import text

    params = {"c": contact}
    pk = db.execute(text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), params).scalar()
    turn_ids = "SELECT id::text FROM chatbot.turns WHERE contact_respond_id = :c"
    db.execute(
        text(
            "DELETE FROM chatbot.chat_ask_items WHERE ask_id IN "
            "(SELECT id FROM chatbot.chat_ask_facts WHERE contact_respond_id = :c)"
        ),
        params,
    )
    db.execute(text("DELETE FROM chatbot.chat_ask_facts WHERE contact_respond_id = :c"), params)
    db.execute(text("DELETE FROM chatbot.chat_episode_facts WHERE contact_respond_id = :c"), params)
    db.execute(text("DELETE FROM conversation_frames WHERE contact_respond_id = :c"), params)
    db.execute(text(f"DELETE FROM ai_assistant_usage_logs WHERE chatbot_turn_id IN ({turn_ids})"), params)
    db.execute(
        text(
            "DELETE FROM media_extraction_job WHERE usage_id IN "
            "(SELECT id FROM contact_media_usage WHERE respond_io_id = :c)"
        ),
        params,
    )
    db.execute(text("DELETE FROM contact_media_usage WHERE respond_io_id = :c"), params)
    db.execute(text("DELETE FROM chatbot.turns WHERE contact_respond_id = :c"), params)
    db.execute(text("DELETE FROM integration_log WHERE external_reference = :c"), params)
    db.execute(text("DELETE FROM chat_histories WHERE contact_id = :c"), params)
    if pk:
        db.execute(text("DELETE FROM ai_assistant_usage_logs WHERE contact_id = :pk"), {"pk": str(pk)})
        db.execute(text("DELETE FROM contact_media_limit WHERE contact_id = :pk"), {"pk": pk})
    db.execute(text("DELETE FROM respond_contacts WHERE respond_io_id = :c"), params)


def restore_saved(saved: dict[str, Any], *, keep_rows: bool) -> None:
    """Put the copy back from `saved` (the state file's content), in the safe order."""
    from sqlalchemy import text

    from app.database import SessionLocal
    from app.models.respond_workspace import RespondWorkspace
    from app.models.user import SystemSetting

    contact = saved["contact"]
    created = saved.get("created") or {}
    # 1. Close every open row of the synthetic contact and set the switch back, in one
    #    commit: a drain mid-row then finds its row closed and posts nothing more.
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE chatbot.turns SET status = 'failed', stage = 'replay_restore', "
                "error = 'Closed by the replay tool restore.', finished_at = now() "
                "WHERE contact_respond_id = :c AND status IN ('queued', 'processing', 'delegated')"
            ),
            {"c": contact},
        )
        row = db.query(SystemSetting).filter(SystemSetting.id == saved["settings_id"]).first()
        if row is not None:
            # A row this run created had no mode of its own: `off` until step 3 removes it.
            row.chatbot_direct_ingress_mode = saved["mode"] or "off"
            row.chatbot_direct_ingress_contacts = saved["contacts"]
            row.respond_webhook_secret_ciphertext = saved["webhook_secret"]
        db.commit()
    finally:
        db.close()
    # 2. Wait (bounded) for the contact's drain to let go.
    if not _drain_gone(contact, DRAIN_LET_GO_SECONDS):
        print(f"warning: the drain of {contact} still held its mutex after {DRAIN_LET_GO_SECONDS:.0f}s")
    # 3. Only then the workspace, and the run's rows, in one transaction.
    db = SessionLocal()
    try:
        workspace = db.query(RespondWorkspace).filter(RespondWorkspace.id == saved["workspace_id"]).first()
        if workspace is not None and created.get("workspace"):
            db.delete(workspace)
        elif workspace is not None:
            workspace.base_url = saved["base_url"]
            workspace.api_key_ciphertext = saved["api_key"]
            workspace.chatbot_sender_url = saved["sender_url"]
            workspace.chatbot_sender_key_ciphertext = saved["sender_key"]
        if not keep_rows:
            _remove_rows(db, contact)
        if created.get("settings"):
            db.execute(text("DELETE FROM system_settings WHERE id = :i"), {"i": saved["settings_id"]})
        db.commit()
    finally:
        db.close()
    try:
        from app.services.queue_service import redis_conn

        for key in list(redis_conn.scan_iter(f"*{contact}*")):
            redis_conn.delete(key)
    except Exception:  # noqa: BLE001
        pass
    print("restored: switch, webhook keys, workspace base URL, API key and sender"
          + ("" if keep_rows else f"; removed {contact} and its rows"))


def restore_from_file(path: str) -> None:
    """After a hard stop: restore from the state file alone, then remove it."""
    with open(path, encoding="utf-8") as fh:
        saved = json.load(fh)
    restore_saved(saved, keep_rows=bool(saved.get("keep_rows")))
    os.remove(path)


def install_signal_handlers(replay: "Replay") -> None:
    """SIGTERM and SIGHUP take the restore path, then exit non-zero (Ctrl-C does it through
    KeyboardInterrupt)."""

    def _on_signal(signum: int, frame: Any) -> None:
        print(f"signal {signum}: restoring the copy")
        try:
            replay.restore()
        finally:
            raise SystemExit(128 + signum)

    for name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is not None:
            signal.signal(sig, _on_signal)


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #


class Replay:
    def __init__(self, args: argparse.Namespace) -> None:
        from app.config import settings

        self.args = args
        self.api = args.api.rstrip("/")
        self.contact = f"{CONTACT_PREFIX}{uuid.uuid4().hex[:10]}"
        self.phone = f"+000{random.randrange(10**8, 10**9)}"
        self.signing_key = secrets.token_urlsafe(33)  # 44 chars, like a respond.io key
        self.sender_key = f"zzt-replay-{secrets.token_hex(12)}"
        self.api_key = getattr(settings, "external_api_key", None) or ""
        self.local = Local(args.port)
        self.saved: dict[str, Any] = {}
        self.restored = False
        self.verified = False
        self.labels: dict[str, str] = {}  # message id -> label
        self.notes: list[str] = []

    # ---------------------------------------------------------------- preflight

    def preflight(self) -> list[str]:
        """The database half of the guard, read-only: leftovers and the webhook key count."""
        from app.database import SessionLocal
        from app.models.user import SystemSetting

        db = SessionLocal()
        try:
            reasons = detect_leftover(db, state_file=self.args.state_file)
            row = db.query(SystemSetting).first()
            if row is not None and len(self._existing_keys(row)) >= MAX_WEBHOOK_KEYS:
                reasons.append(
                    f"the copy already has {MAX_WEBHOOK_KEYS} webhook signing keys: the tool cannot add one "
                    "that verifies without dropping one of respond.io's"
                )
            self._describe(db)
        finally:
            db.close()
        return reasons

    def _describe(self, db: Any) -> None:
        from app.database import engine
        from app.models.ai_assistant import AIAssistantConfig

        url = engine.url
        print(f"database: {url.host}:{url.port}/{url.database}")
        config = db.query(AIAssistantConfig).first()
        if config is not None:
            print(f"LLM: provider {config.provider}, model {config.model} (per-prompt overrides may apply)")
        else:
            print("LLM: no AI assistant configuration on this copy (turns will answer the error reply)")

    @staticmethod
    def _existing_keys(row: Any) -> list[str]:
        from app.config import settings
        from app.utils.field_encryption import decrypt_secret

        existing = ""
        if row.respond_webhook_secret_ciphertext:
            try:
                existing = decrypt_secret(row.respond_webhook_secret_ciphertext) or ""
            except ValueError:
                existing = ""
        if not existing:
            existing = getattr(settings, "respond_webhook_secret", "") or ""
        return [k for k in existing.replace(",", " ").split() if k]

    # ---------------------------------------------------------------- setup

    def _write_state(self) -> None:
        payload = json.dumps(self.saved, default=str).encode()
        fd = os.open(self.args.state_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        os.chmod(self.args.state_file, 0o600)

    def setup(self) -> None:
        from sqlalchemy import text

        from app.database import SessionLocal
        from app.models.respond_workspace import RespondWorkspace
        from app.models.user import SystemSetting
        from app.utils.field_encryption import encrypt_secret

        db = SessionLocal()
        try:
            row = db.query(SystemSetting).first()
            workspace = db.query(RespondWorkspace).filter(RespondWorkspace.is_default.is_(True)).first()
            keys = self._existing_keys(row) if row is not None else []
            # The originals, ciphertexts only, on disk BEFORE the first change.
            self.saved = {
                "contact": self.contact,
                "keep_rows": bool(self.args.keep_rows),
                "created": {"settings": row is None, "workspace": workspace is None},
                "settings_id": str(row.id) if row is not None else str(uuid.uuid4()),
                "mode": row.chatbot_direct_ingress_mode if row is not None else None,
                "contacts": row.chatbot_direct_ingress_contacts if row is not None else None,
                "webhook_secret": row.respond_webhook_secret_ciphertext if row is not None else None,
                "workspace_id": str(workspace.id) if workspace is not None else str(uuid.uuid4()),
                "base_url": workspace.base_url if workspace is not None else None,
                "api_key": workspace.api_key_ciphertext if workspace is not None else None,
                "sender_url": workspace.chatbot_sender_url if workspace is not None else None,
                "sender_key": workspace.chatbot_sender_key_ciphertext if workspace is not None else None,
            }
            self._write_state()
            # A bare database (no settings row, no default workspace) gets one for the run,
            # removed again at the end.
            if row is None:
                row = SystemSetting(id=self.saved["settings_id"], name="ZZT replay")
                db.add(row)
            if workspace is None:
                workspace = RespondWorkspace(
                    id=self.saved["workspace_id"], space_id="zzt-replay", name="ZZT replay",
                    is_default=True, is_active=True, api_key_ciphertext=encrypt_secret("zzt-replay-placeholder"),
                )
                db.add(workspace)
            # Every existing key kept (the webhook verifies the first ten; preflight refuses a
            # copy that already holds ten).
            row.respond_webhook_secret_ciphertext = encrypt_secret(",".join([*keys, self.signing_key]))
            row.chatbot_direct_ingress_mode = "contacts"
            row.chatbot_direct_ingress_contacts = self.contact
            workspace.base_url = self.local.base
            workspace.api_key_ciphertext = encrypt_secret(f"zzt-replay-not-a-key-{secrets.token_hex(8)}")
            workspace.chatbot_sender_url = f"https://127.0.0.1:{self.args.port}/sender"
            workspace.chatbot_sender_key_ciphertext = encrypt_secret(self.sender_key)
            db.flush()
            pk = db.execute(
                text(
                    "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, chatbot_allowed) "
                    "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), true) RETURNING id"
                ),
                {"cid": self.contact, "phone": self.phone, "sv": json.dumps({"variables": {}})},
            ).scalar()
            db.execute(
                text(
                    "INSERT INTO contact_media_limit (id, contact_id, modality, is_allowed) "
                    "VALUES (gen_random_uuid(), :pk, 'image', true)"
                ),
                {"pk": pk},
            )
            db.commit()
        finally:
            db.close()
        print(f"contact {self.contact}; sender key {last4(self.sender_key)}; local server {self.local.base}")

    def restore(self) -> None:
        if self.restored or not self.saved:
            return
        self.restored = True
        restore_saved(self.saved, keep_rows=bool(self.args.keep_rows))
        if self.args.state_file and os.path.exists(self.args.state_file):
            os.remove(self.args.state_file)

    # ---------------------------------------------------------------- messages

    def new_message(self, label: str, sent_at: float) -> int:
        mid = int(sent_at * 1_000_000)
        self.labels[str(mid)] = label
        return mid

    def body(self, mid: int, *, photo: bool = False) -> dict[str, Any]:
        label = self.labels[str(mid)]
        if photo:
            # A closed local port: the read fails without any traffic leaving the machine.
            inner: dict[str, Any] = {
                "type": "attachment",
                "attachment": {"type": "image", "url": f"https://127.0.0.1:9/{label}.jpg", "mimeType": "image/jpeg", "size": 2048},
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

    def _row_exists(self, mid: int, timeout: float = 5.0) -> bool:
        from sqlalchemy import text

        from app.database import SessionLocal

        end = time.monotonic() + timeout
        while time.monotonic() < end:
            db = SessionLocal()
            try:
                found = db.execute(
                    text("SELECT 1 FROM chatbot.turns WHERE contact_respond_id = :c AND message_id = :m"),
                    {"c": self.contact, "m": str(mid)},
                ).first()
            finally:
                db.close()
            if found:
                return True
            time.sleep(0.2)
        return False

    def webhook(self, body: dict) -> int:
        raw = json.dumps(body).encode()
        signature = hmac.new(self.signing_key.encode(), raw, hashlib.sha256).hexdigest()
        status, _ = http(
            "POST",
            f"{self.api}/api/v1/public/respond/webhook",
            raw,
            {"Content-Type": "application/json", "x-respond-signature": signature},
        )
        if not self.verified:
            # The first delivery proves the copy and this tool share one database.
            if status != 200:
                raise Abort(f"the first webhook answered HTTP {status}, not 200")
            if not self._row_exists(body["message"]["messageId"]):
                raise Abort(
                    "the first webhook created no queued row in the database this tool wrote: "
                    "is --env-file the copy's own?"
                )
            self.verified = True
        return status

    def burst(self, bodies: list[dict]) -> list[int]:
        """The first body alone (it is checked), then the rest at once, one thread each, so
        the burst reaches the copy inside a few milliseconds, as a real one does."""
        codes: list[int] = [0] * len(bodies)
        start = 0
        if not self.verified and bodies:
            codes[0] = self.webhook(bodies[0])
            start = 1

        def deliver(i: int, body: dict) -> None:
            codes[i] = self.webhook(body)

        threads = [threading.Thread(target=deliver, args=(i, bodies[i])) for i in range(start, len(bodies))]
        for thread in threads:
            thread.start()
            time.sleep(0.005)
        for thread in threads:
            thread.join(30)
        return codes

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
        """Every sender POST attempt the copy made for this contact, in order, from its log."""
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
            f"Copy `{self.api}`; synthetic contact `{self.contact}`; local lookup server `{self.local.base}` "
            f"({self.local.lookups} contact lookups answered).",
            "Replies are read from the copy's own sender log (`integration_log`, channel `chatbot_sender`): the",
            "outbound URL guard refuses the local sender URL, so nothing left the machine and each reply row ends",
            "`failed/send_unconfirmed` in this run by design. A reply logged before an earlier-sent message even",
            "arrived cannot be put behind it (the queue orders what it has); real turns take seconds, a burst",
            "arrives in milliseconds.",
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CHAT-INBOX-QUEUE replay against a local copy")
    parser.add_argument("--env-file", required=True, help="the copy's SORENTO_ENV_FILE")
    parser.add_argument("--api", help="the copy's backend, e.g. http://localhost:8106")
    parser.add_argument("--port", type=int, default=8399, help="port for the local lookup server")
    parser.add_argument("--out", help="markdown report path")
    parser.add_argument("--state-file", default="inbox-replay-state.json", help="crash-safety file (originals)")
    parser.add_argument("--restore-from", help="restore the copy from a state file and exit")
    parser.add_argument("--scenarios", default="s1,s2,s3,s4")
    parser.add_argument("--no-restart", action="store_true", help="s4 without waiting for a restart")
    parser.add_argument("--keep-rows", action="store_true", help="keep the synthetic contact's (closed) rows")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database_url = _env_file_value(args.env_file, "DATABASE_URL")
    api = (args.api or "http://localhost").rstrip("/")
    reasons = check_target(database_url=database_url, api=api, environ=os.environ)
    if not args.restore_from and not args.api:
        reasons.append("--api is required for a run")
    if not args.restore_from and not args.out:
        reasons.append("--out is required for a run")
    if not args.restore_from and args.state_file and os.path.exists(args.state_file):
        reasons.append(f"an earlier run's state file is still there ({args.state_file}); restore with --restore-from")
    if reasons:
        for reason in reasons:
            print(f"refused: {reason}")
        return 2

    os.environ["SORENTO_ENV_FILE"] = args.env_file
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if args.restore_from:
        restore_from_file(args.restore_from)
        return 0
    if not healthy(api):
        print(f"refused: {api}/health does not answer 200; start the copy first")
        return 2

    replay = Replay(args)
    reasons = replay.preflight()
    if reasons:
        replay.local.stop()
        for reason in reasons:
            print(f"refused: {reason}")
        return 2

    results: list[dict[str, Any]] = []
    install_signal_handlers(replay)
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
    except Abort as exc:
        replay.notes.append(f"Stopped: {exc}")
        print(f"stopped: {exc}; restoring")
        results.append({"title": "stopped", "codes": [], "got": [], "checks": [(str(exc), False)], "delivered": []})
    finally:
        try:
            replay.restore()
        finally:
            replay.local.stop()
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(replay.report(results))
            print(f"report written to {args.out}")
    failed = [c for r in results for c in r["checks"] if not c[1]]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
