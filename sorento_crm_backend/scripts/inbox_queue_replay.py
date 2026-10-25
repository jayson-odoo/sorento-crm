"""CHAT-INBOX-QUEUE hand test: replay four scenarios through a running copy's real queue.

Plan `documentation/plans/chatbot/PLAN-chat-inbox-queue.md`. Run by crew on the Mac against a
running LOCAL test copy (backend + sweeper, and its RQ worker for the photo scenario):

    cd sorento_crm_backend
    venv/bin/python scripts/inbox_queue_replay.py --env-file .env.<copy> \\
        --api http://localhost:<copy backend port> --port 8399 \\
        --out ~/inbox-replay.md --state-file ~/inbox-replay-state.json

After a hard stop (kill -9, a crash) put the copy back with
`venv/bin/python scripts/inbox_queue_replay.py --env-file .env.<copy> --restore-from ~/inbox-replay-state.json`.
One run at a time per copy (a Postgres advisory lock held for the whole run).

**Each turn calls the copy's LLM provider** (its parser and lanes run for real), so a run costs
what that many real turns cost on the copy's keys; the provider and model are printed first.

**Refuses anything but a local, neutralised copy**: `check_target` judges the env file's
DATABASE_URL as dotenv resolves it (the last assignment wins; a relative path is read against
the backend directory, as Settings reads it): the host must be loopback with no `host` /
`hostaddr` / `dbname` / `service` override in its query, `DATABASE_URL` / `DIRECT_URL` (any
case) must not be exported in the shell, and `--api` must be http(s) on localhost;
`check_connected` then asks the server it actually reached (`inet_server_addr()`) and refuses
the shared dev DB by its exact name (SHARED_DEV_DATABASE); no other rule on the database name
(crew copies are prod clones). `check_neutralised` reads the ORIGINAL values
before setup and refuses unless respond.io, every n8n URL and SMTP are empty or on `.invalid`,
the workspace sender URL is empty, every proxy variable in the env file is a dead loopback
proxy (the lowercase `https_proxy` required), and the lowercase `no_proxy` is set to the local
hosts (plus the copy's LLM host), with no `*` in any NO_PROXY / no_proxy. A checked value the
env file leaves out, or sets empty, is judged by its Settings default (RESPOND_BASE_URL falls
back to https://api.respond.io, so it must be set to a `.invalid` host). It also refuses when an earlier run was not cleaned up
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
The state file also names the database it was written against; `--restore-from` refuses a
file from another one. Restore runs on the main path (SIGTERM and SIGHUP only exit, Ctrl-C
interrupts the run): it closes every open row of the synthetic contact (`failed`) and sets the
switch back, then repeats close-then-wait until a pass closes nothing and the contact's drain
mutex is gone (bounded); only then one transaction closes again, writes the workspace back and
removes the run's rows (`--keep-rows` keeps them, closed). The state file is removed last; on a
timeout or a second Ctrl-C it stays and the exact `--restore-from` command is printed.

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
burst, then a backend restart: `--restart-cmd "<shell command>"` runs it once itself (else the
tool asks a person to restart and waits); `--no-restart` skips it. The restart command must
RETURN (exit 0 once the restart is under way or done): a non-zero exit fails s4 at once with
its code in the report, and one still running after RESTART_CMD_SECONDS is killed with its
whole process group. Stdlib plus the repo's own
modules; never imports `app.services.chatbot`.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
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
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

SENDER_CHANNEL = "chatbot_sender"
OVERALL_SECONDS = 300.0
DRAIN_LET_GO_SECONDS = 180.0
# `--restart-cmd` is run once in scenario 4 and given this long to finish.
RESTART_CMD_SECONDS = 300.0
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# `app.api.v1.public.respond_webhook.MAX_KEYS`: the webhook verifies against the first ten.
MAX_WEBHOOK_KEYS = 10
CONTACT_PREFIX = "zzt-replay-"
# The shared dev DB other lanes' stacks run on: refused by its exact name.
SHARED_DEV_DATABASE = "sorento_cagent_stack"
# One run at a time per copy: a session-level advisory lock held for the whole run.
RUN_LOCK_KEY = 727327105
BACKEND = Path(__file__).resolve().parent.parent
# The crash-safety file lives in the user's own space (not /tmp: world-readable, cleaned on reboot).
DEFAULT_STATE_FILE = str(Path.home() / "inbox-replay-state.json")
CONNECTION_OVERRIDE_KEYS = frozenset({"host", "hostaddr", "dbname", "service"})


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
    try:
        parts = urlsplit(database_url or "")
        query = {k.lower() for k in parse_qs(parts.query, keep_blank_values=True)}
    except ValueError:
        parts, query = urlsplit(""), set()
    if query & CONNECTION_OVERRIDE_KEYS:
        reasons.append("the database URL overrides its host or database in the query string")
    for var in ("DATABASE_URL", "DIRECT_URL", "database_url", "direct_url"):
        if environ.get(var):
            reasons.append(f"{var} is exported in this shell; unset it, the env file is the one source")
    try:
        scheme = urlsplit(api or "").scheme.lower()
    except ValueError:
        scheme = ""
    if scheme not in ("http", "https") or _host(api or "") not in LOOPBACK_HOSTS:
        reasons.append("--api must be http(s) on localhost, 127.0.0.1 or [::1]")
    return reasons


def resolve_env_file(path: str) -> str:
    """The absolute file Settings reads for this SORENTO_ENV_FILE value (a relative path is
    read against the backend directory, as `app.config._resolve_settings_env_file` does)."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = BACKEND / candidate
    return str(candidate)


def env_file_database_url(path: str) -> str:
    """DATABASE_URL as dotenv resolves it (the last assignment wins, `export` included)."""
    from dotenv import dotenv_values

    return str(dotenv_values(resolve_env_file(path)).get("DATABASE_URL") or "")


def check_connected(engine: Any) -> list[str]:
    """What the engine ACTUALLY reaches: no host / database override in its URL query, and
    the server it connects to is local (unix socket or loopback). One exact-name refusal
    (`sorento_cagent_stack`, the shared dev DB); every other name is judged by
    `check_neutralised` (crew copies are neutralised prod clones)."""
    from sqlalchemy import text

    reasons: list[str] = []
    query = {str(k).lower() for k in (getattr(engine.url, "query", None) or {})}
    if query & CONNECTION_OVERRIDE_KEYS:
        reasons.append("the database URL overrides its host or database in the query string")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT current_database(), inet_server_addr()")).first()
    name, addr = (row[0], row[1]) if row is not None else ("", "unknown")
    if str(name or "") == SHARED_DEV_DATABASE:
        reasons.append(f"the connected database is {SHARED_DEV_DATABASE}, the shared dev DB other lanes' stacks run on")
    if addr is not None:
        try:
            loopback = ipaddress.ip_address(str(addr).split("/", 1)[0]).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            reasons.append("the connected database server is not on this machine")
    return reasons


N8N_SETTING_COLUMNS = (
    "n8n_attachment_webhook_url",
    "n8n_crm_chat_outbound_webhook_url",
    "n8n_stock_inquiry_revise_webhook_url",
    "n8n_close_convo_webhook_url",
)


def _neutral(value: Any) -> bool:
    """Empty, or a URL / host on the reserved `.invalid` TLD (never resolves anywhere)."""
    text_value = str(value or "").strip()
    if not text_value:
        return True
    host = _host(text_value) if "://" in text_value else text_value.split(":", 1)[0].lower()
    return host.rstrip(".").endswith(".invalid") or host == "invalid"


PROXY_VARS = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")


def _settings_default(key: str) -> str:
    """The Settings default a key left out of the env file falls back to (empty if none)."""
    from app.config import settings

    field = type(settings).model_fields.get(key.lower())
    default = getattr(field, "default", None) if field is not None else None
    return "" if default is None or not isinstance(default, str) else default


def _dead_loopback_proxy(proxy: str) -> bool:
    """A loopback proxy whose port refuses a TCP connect: egress is blocked, not routed."""
    import socket

    try:
        parts = urlsplit(proxy)
        host, port = (parts.hostname or "").lower(), parts.port
    except ValueError:
        return False
    if host not in LOOPBACK_HOSTS or not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return False
    except OSError:
        return True


def check_neutralised(db: Any, env: Any) -> list[str]:
    """The reasons this copy is NOT neutralised (empty means safe to rewire), read on the
    ORIGINAL values before setup; `env` is the copy's env file. Each reason names its value."""
    from app.models.respond_workspace import RespondWorkspace
    from app.models.user import SystemSetting

    env = env or {}
    reasons: list[str] = []

    def need(label: str, value: Any, rule: str = "must be empty or a .invalid host") -> None:
        if not _neutral(value):
            reasons.append(f"{label} = {value!r} {rule}")

    for key in ("RESPOND_BASE_URL", "N8N_WEBHOOK_URL", "SMTP_HOST"):
        # Judged as the app RESOLVES it: absent, bare or empty falls back to the Settings
        # default (RESPOND_BASE_URL's is the real https://api.respond.io).
        resolved = env.get(key) or _settings_default(key)
        if env.get(key):
            need(f"env {key}", resolved)
        else:
            need(f"env {key} (unset, resolves to)", resolved, "so set it to a .invalid host")
    row = db.query(SystemSetting).first()
    if row is not None:
        for column in N8N_SETTING_COLUMNS:
            need(f"system_settings.{column}", getattr(row, column, None))
        need("system_settings.smtp_host", getattr(row, "smtp_host", None))
    for workspace in db.query(RespondWorkspace).all():
        space = workspace.space_id
        need(f"respond_workspaces[{space}].base_url", workspace.base_url)
        need(f"respond_workspaces[{space}].chatbot_retry_ingress_url", workspace.chatbot_retry_ingress_url)
        sender = (workspace.chatbot_sender_url or "").strip()
        if sender and _host(sender) not in LOOPBACK_HOSTS:
            reasons.append(f"respond_workspaces[{space}].chatbot_sender_url = {sender!r} must be empty")
    # Egress: the LOWERCASE keys are required (httpx and urllib prefer them, and only a
    # lowercase `no_proxy` in the file overrides the worker's launched `no_proxy='*'`);
    # EVERY proxy variable present is probed.
    if not env.get("https_proxy"):
        reasons.append("env https_proxy (lowercase) is not set: egress must go through a dead loopback proxy")
    for var in [v for v in PROXY_VARS if env.get(v)]:
        if not _dead_loopback_proxy(env[var]):
            reasons.append(f"env {var} = {env[var]!r} must be a loopback proxy whose port refuses connections")
    if not env.get("no_proxy"):
        reasons.append(
            "env no_proxy (lowercase) is not set: it must list the local hosts (plus the copy's LLM host) only, never '*'"
        )
    for var in [v for v in ("NO_PROXY", "no_proxy") if v in env]:
        if "*" in str(env.get(var) or ""):
            reasons.append(
                f"env {var} = {env.get(var)!r} lets every host past the proxy; list the local hosts "
                "(plus the copy's LLM host) only"
            )
    return reasons


def take_run_lock(engine: Any) -> Any:
    """The run lock (one run at a time): a connection holding the advisory lock, kept open
    for the whole run, or None when another run holds it."""
    from sqlalchemy import text

    conn = engine.connect()
    try:
        got = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": RUN_LOCK_KEY}).scalar()
        conn.commit()
    except Exception:
        conn.close()
        raise
    if not got:
        conn.close()
        return None
    return conn


def release_run_lock(conn: Any) -> None:
    from sqlalchemy import text

    if conn is None:
        return
    try:
        conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": RUN_LOCK_KEY})
        conn.commit()
    except Exception:  # noqa: BLE001 - closing the session releases it anyway
        pass
    finally:
        conn.close()


def _current_database() -> tuple[str, Any]:
    from sqlalchemy import text

    from app.database import engine

    with engine.connect() as conn:
        row = conn.execute(text("SELECT current_database(), inet_server_addr()")).first()
    return str(row[0]), (str(row[1]) if row[1] is not None else None)


def restore_hint(state_file: str) -> str:
    env_file = os.environ.get("SORENTO_ENV_FILE", ".env.<copy>")
    return (
        f"to finish the restore run: venv/bin/python scripts/inbox_queue_replay.py "
        f"--env-file {env_file} --restore-from {state_file}"
    )


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


def _close_open_rows(db: Any, contact: str) -> int:
    from sqlalchemy import text

    return int(
        db.execute(
            text(
                "UPDATE chatbot.turns SET status = 'failed', stage = 'replay_restore', "
                "error = 'Closed by the replay tool restore.', finished_at = now() "
                "WHERE contact_respond_id = :c AND status IN ('queued', 'processing', 'delegated')"
            ),
            {"c": contact},
        ).rowcount
        or 0
    )


def _drain_alive(contact: str) -> bool:
    from app.services.queue_service import redis_conn

    try:
        return bool(redis_conn.exists(f"chatbot:drain:{contact}"))
    except Exception:  # noqa: BLE001 - unreadable reads as alive: do not restore under it
        return True


def restore_saved(saved: dict[str, Any], *, keep_rows: bool, state_file: str = "") -> bool:
    """Put the copy back from `saved` (the state file's content), in the safe order. False
    (nothing written back to the workspace) when the contact's drain does not go quiet."""
    from sqlalchemy import text

    from app.database import SessionLocal
    from app.models.respond_workspace import RespondWorkspace
    from app.models.user import SystemSetting

    contact = saved["contact"]
    created = saved.get("created") or {}
    # 1. Close every open row of the synthetic contact and set the switch back: a drain
    #    mid-row then finds its row closed and posts nothing more.
    db = SessionLocal()
    try:
        _close_open_rows(db, contact)
        row = db.query(SystemSetting).filter(SystemSetting.id == saved["settings_id"]).first()
        if row is not None:
            # A row this run created had no mode of its own: `off` until step 3 removes it.
            row.chatbot_direct_ingress_mode = saved["mode"] or "off"
            row.chatbot_direct_ingress_contacts = saved["contacts"]
            row.respond_webhook_secret_ciphertext = saved["webhook_secret"]
        db.commit()
    finally:
        db.close()
    # 2. Close-then-wait until a pass closes nothing and the drain has let go (bounded).
    deadline = time.monotonic() + DRAIN_LET_GO_SECONDS
    while True:
        db = SessionLocal()
        try:
            closed = _close_open_rows(db, contact)
            db.commit()
        finally:
            db.close()
        if closed == 0 and not _drain_alive(contact):
            break
        if time.monotonic() >= deadline:
            print(
                f"restore stopped: the drain of {contact} did not go quiet within "
                f"{DRAIN_LET_GO_SECONDS:.0f}s; the workspace was NOT written back"
            )
            if state_file:
                print(restore_hint(state_file))
            return False
        time.sleep(0.2)
    # 3. Only then, in one transaction: close again, the workspace, the run's rows.
    db = SessionLocal()
    try:
        _close_open_rows(db, contact)
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
    return True


def restore_from_file(path: str) -> bool:
    """After a hard stop: restore from the state file alone, then remove it. Refuses a file
    written against another database (it stays)."""
    with open(path, encoding="utf-8") as fh:
        saved = json.load(fh)
    current, _addr = _current_database()
    if saved.get("database") != current:
        raise Refused(
            f"the state file was written against database {saved.get('database')!r}, "
            f"not the connected {current!r}; nothing restored"
        )
    if not restore_saved(saved, keep_rows=bool(saved.get("keep_rows")), state_file=path):
        return False
    os.remove(path)
    return True


def install_signal_handlers(replay: "Replay") -> None:
    """SIGTERM and SIGHUP only exit (non-zero); `main`'s `finally` runs the restore, on the
    main path, never inside a signal handler."""
    _ = replay

    def _on_signal(signum: int, frame: Any) -> None:
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
        self.sender_key = f"zzt-replay-{secrets.token_hex(12)}"  # gitleaks:allow
        self.api_key = getattr(settings, "external_api_key", None) or ""
        self.local = Local(args.port)
        # Only values THIS process read and wrote (never loaded from another run's file).
        self.saved: dict[str, Any] = {}
        self.state_written = False
        self.restored = False
        self.verified = False
        self.labels: dict[str, str] = {}  # message id -> label
        self.notes: list[str] = []

    # ---------------------------------------------------------------- preflight

    def preflight(self) -> list[str]:
        """The database half of the guard, read-only: leftovers and the webhook key count."""
        from app.database import SessionLocal
        from app.models.user import SystemSetting

        from dotenv import dotenv_values

        db = SessionLocal()
        try:
            reasons = detect_leftover(db, state_file=self.args.state_file)
            reasons += check_neutralised(db, dotenv_values(resolve_env_file(self.args.env_file)))
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
        self.state_written = True
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
            database, server_addr = _current_database()
            # The originals, ciphertexts only, on disk BEFORE the first change.
            self.saved = {
                "database": database,
                "server_addr": server_addr,
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
                    is_default=True, is_active=True, api_key_ciphertext=encrypt_secret("zzt-replay-placeholder"),  # gitleaks:allow
                )
                db.add(workspace)
            # Every existing key kept (the webhook verifies the first ten; preflight refuses a
            # copy that already holds ten).
            row.respond_webhook_secret_ciphertext = encrypt_secret(",".join([*keys, self.signing_key]))
            row.chatbot_direct_ingress_mode = "contacts"
            row.chatbot_direct_ingress_contacts = self.contact
            workspace.base_url = self.local.base
            workspace.api_key_ciphertext = encrypt_secret(f"zzt-replay-not-a-key-{secrets.token_hex(8)}")  # gitleaks:allow
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

    def restore(self) -> bool:
        """True when the copy is back (or this process changed nothing); False when the
        drain did not go quiet (the state file stays, the hint is printed)."""
        if self.restored or not self.saved or not self.state_written:
            return True
        try:
            done = restore_saved(self.saved, keep_rows=bool(self.args.keep_rows), state_file=self.args.state_file)
        except KeyboardInterrupt:
            print("restore interrupted; the copy is NOT fully restored")
            print(restore_hint(self.args.state_file))
            raise
        if not done:
            return False
        self.restored = True
        if os.path.exists(self.args.state_file):
            os.remove(self.args.state_file)
        return True

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
            command = getattr(self.args, "restart_cmd", None)
            if command:
                restarted, failure = self._run_restart(command)
                if failure:
                    self.notes.append(failure)
                    return {"title": "s4: 6-message burst, backend restart mid-burst", "codes": codes, "got": [],
                            "checks": [(failure, False)], "delivered": [self.labels[str(m)] for m in order]}
            else:
                print("\n>>> RESTART THE COPY BACKEND NOW (stop it and start it again). Waiting for /health to go down...")
                went_down = self._wait_health(False, 180)
                restarted = bool(went_down and self._wait_health(True, 240))
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

    def _run_restart(self, command: str) -> tuple[bool, str | None]:
        """Run `--restart-cmd` once (shell) while watching /health go down and come back.
        A non-zero exit fails at once (its code in the notes); a command still running after
        RESTART_CMD_SECONDS is killed and reaped. Returns (restarted, failure)."""
        import subprocess

        print(f"\n>>> restarting the copy backend: {command}")
        # Its own process group, so a compound command's children are stopped with it.
        process = subprocess.Popen(command, shell=True, start_new_session=True)
        started = time.monotonic()

        def stop() -> None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            process.wait()

        def failed() -> str | None:
            code = process.poll()
            if code not in (None, 0):
                return f"the restart command exited {code}"
            if code is None and time.monotonic() - started > RESTART_CMD_SECONDS:
                stop()
                return f"the restart command did not return within {RESTART_CMD_SECONDS:.0f}s (killed)"
            return None

        went_down = came_back = False
        end = started + 180
        while time.monotonic() < end and not went_down:
            failure = failed()
            if failure:
                return False, failure
            went_down = self._wait_health(False, 0.5)
        end = time.monotonic() + 240
        while went_down and time.monotonic() < end and not came_back:
            failure = failed()
            if failure:
                return False, failure
            came_back = self._wait_health(True, 0.5)
        try:
            process.wait(timeout=max(0.0, RESTART_CMD_SECONDS - (time.monotonic() - started)))
        except subprocess.TimeoutExpired:
            stop()
            return False, f"the restart command did not return within {RESTART_CMD_SECONDS:.0f}s (killed)"
        if process.returncode not in (0, None):
            return False, f"the restart command exited {process.returncode}"
        return bool(went_down and came_back), None

    def _wait_health(self, up: bool, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if healthy(self.api) == up:
                return True
            time.sleep(0.2)
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
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE, help="crash-safety file (originals)")
    parser.add_argument("--restore-from", help="restore the copy from a state file and exit")
    parser.add_argument("--scenarios", default="s1,s2,s3,s4")
    parser.add_argument("--no-restart", action="store_true", help="s4 without a restart")
    parser.add_argument("--restart-cmd", help="shell command s4 runs once to restart the copy backend")
    parser.add_argument("--keep-rows", action="store_true", help="keep the synthetic contact's (closed) rows")
    return parser


def _refuse(reasons: list[str]) -> int:
    for reason in reasons:
        print(f"refused: {reason}")
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    env_file = resolve_env_file(args.env_file)
    api = (args.api or "http://localhost").rstrip("/")
    reasons = [] if os.path.exists(env_file) else [f"the env file {env_file} does not exist"]
    reasons += check_target(database_url=env_file_database_url(env_file), api=api, environ=os.environ)
    if not args.restore_from and not args.api:
        reasons.append("--api is required for a run")
    if not args.restore_from and not args.out:
        reasons.append("--out is required for a run")
    if not args.restore_from and args.state_file and os.path.exists(args.state_file):
        reasons.append(f"an earlier run's state file is still there ({args.state_file}); restore with --restore-from")
    if reasons:
        return _refuse(reasons)

    os.environ["SORENTO_ENV_FILE"] = env_file
    sys.path.insert(0, str(BACKEND))
    from app.database import engine

    reasons = check_connected(engine)
    if reasons:
        return _refuse(reasons)
    if not args.restore_from and not healthy(api):
        return _refuse([f"{api}/health does not answer 200; start the copy first"])
    lock = take_run_lock(engine)
    if lock is None:
        return _refuse(["another replay run holds this copy's run lock; wait for it to finish"])
    try:
        if args.restore_from:
            try:
                return 0 if restore_from_file(args.restore_from) else 3
            except Refused as exc:
                return _refuse([str(exc)])
        return _run(args)
    finally:
        release_run_lock(lock)


def _run(args: argparse.Namespace) -> int:
    replay = Replay(args)
    reasons = replay.preflight()
    if reasons:
        replay.local.stop()
        return _refuse(reasons)

    results: list[dict[str, Any]] = []
    install_signal_handlers(replay)
    replay.local.start()
    restored = False
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
        print("interrupted; restoring (a second Ctrl-C stops the restore; the state file stays)")
    except Abort as exc:
        replay.notes.append(f"Stopped: {exc}")
        print(f"stopped: {exc}; restoring")
        results.append({"title": "stopped", "codes": [], "got": [], "checks": [(str(exc), False)], "delivered": []})
    finally:
        try:
            restored = replay.restore()
        finally:
            replay.local.stop()
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(replay.report(results))
            print(f"report written to {args.out}")
    if not restored:
        return 3
    failed = [c for r in results for c in r["checks"] if not c[1]]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
