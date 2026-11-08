"""RESPOND-BASE-URL-LEAK: every Respond.io call honours the configured base URL.

A crew test copy runs on a prod-clone database (real workspace rows, real Respond.io
credentials) and points RESPOND_BASE_URL at a `.invalid` host so nothing reaches a customer.
Before this lane a Stock Inquiry submit still went to the real API: a workspace row's
`base_url` beat the env override, and integration-log labels hard-coded the real host.

Three guards:

* the source guard: the real API host is written down in ONE module
  (`app/services/integration_service.py`), so a new call site cannot build its own URL;
* the resolver order: env RESPOND_BASE_URL > workspace base_url > default;
* the red-first journey: the Stock Inquiry send job, with RESPOND_BASE_URL on a `.invalid` host
  and a workspace row on the real host, makes ZERO requests to the real host.

No network: the Respond.io HTTP client is replaced by an httpx MockTransport.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import httpx
import pytest

# MUST be first app import - resolves circular-import in app.modules.runtime.guards.
from app.main import app  # noqa: E402,F401

from app.config import settings
from app.services import integration_service
from app.services.integration_service import (
    RESPOND_DEFAULT_BASE_URL,
    RespondClient,
    resolve_respond_base_url,
    respond_endpoint,
)

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
CLIENT_MODULE = BACKEND / "app" / "services" / "integration_service.py"
REAL_HOST = "api.respond.io"
OVERRIDE = "https://api.respond.invalid"

# The API host (any regional `api-<x>` spelling), or respond.io itself as a host
# (`//respond.io`). app.respond.io (inbox links) and cdn.respond.io (media) are not the API and
# are not matched.
_HOST_RE = re.compile(r"api(?:-[a-z0-9]+)?\.respond\.io(?![a-z0-9-])|//respond\.io(?![a-z0-9.-])", re.IGNORECASE)


def _scanned_files() -> list[Path]:
    roots = [
        BACKEND / "app",
        BACKEND / "scripts",
        REPO / "sorento_crm_mcp" / "sorento_crm_mcp",
    ]
    files = [p for root in roots if root.is_dir() for p in root.rglob("*.py")]
    files += [p for p in (BACKEND / "worker.py", BACKEND / "main.py") if p.is_file()]
    return [p for p in files if p.resolve() != CLIENT_MODULE.resolve()]


def test_the_real_respond_host_is_written_only_in_the_client_module():
    offenders = []
    for path in _scanned_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _HOST_RE.search(line):
                offenders.append(f"{path.relative_to(REPO)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "The Respond.io API host may only appear in app/services/integration_service.py; build "
        "URLs and log labels with respond_endpoint()/RespondClient so RESPOND_BASE_URL applies:\n"
        + "\n".join(offenders)
    )


def test_the_guard_scans_real_code():
    # A guard that scans nothing passes forever.
    names = {p.name for p in _scanned_files()}
    assert {"procurement_service.py", "respond_io_tasks.py"} <= names
    assert _HOST_RE.search(f'"https://{REAL_HOST}/v2/contact"')
    assert _HOST_RE.search('"HTTPS://API.RESPOND.IO"')
    assert _HOST_RE.search('"https://respond.io"')
    assert not _HOST_RE.search('"https://app.respond.io/space/1/inbox/2"')
    assert not _HOST_RE.search(OVERRIDE)


def test_replay_tool_accepts_its_loopback_lookup_server_and_refuses_the_real_host():
    """CHAT-INBOX-QUEUE's replay tool used to rewrite the workspace row's base_url to reach its
    local lookup server; RESPOND_BASE_URL now beats that row, so the env must be allowed to name
    the loopback server, and must still refuse the real host."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("zzt_replay", BACKEND / "scripts" / "inbox_queue_replay.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)

    def respond_reasons(value):
        env = {"RESPOND_BASE_URL": value} if value is not None else {}
        return [r for r in tool.check_env(env) if "RESPOND_BASE_URL" in r]

    assert respond_reasons("http://127.0.0.1:8399") == []
    assert respond_reasons(OVERRIDE) == []
    assert respond_reasons(f"https://{REAL_HOST}")
    assert respond_reasons(None), "unset resolves to the real host and must be refused"
    assert respond_reasons("http://127.0.0.1.example.com:8399")
    assert tool.respond_base_url_of({"respond_base_url": "a", "RESPOND_BASE_URL": "b"}) in {"a", "b"}


def test_the_client_module_holds_the_default(monkeypatch):
    monkeypatch.setattr(settings, "respond_base_url", None)
    assert RESPOND_DEFAULT_BASE_URL == f"https://{REAL_HOST}"
    assert resolve_respond_base_url(None) == RESPOND_DEFAULT_BASE_URL


@pytest.mark.parametrize(
    "env, workspace, expected",
    [
        (OVERRIDE, f"https://{REAL_HOST}", OVERRIDE),  # env beats a prod-clone workspace row
        (OVERRIDE + "/", None, OVERRIDE),
        (None, "https://ws.respond.invalid/", "https://ws.respond.invalid"),
        ("", "https://ws.respond.invalid", "https://ws.respond.invalid"),
        ("  ", None, RESPOND_DEFAULT_BASE_URL),
        (None, None, RESPOND_DEFAULT_BASE_URL),
    ],
)
def test_resolver_order_env_then_workspace_then_default(monkeypatch, env, workspace, expected):
    monkeypatch.setattr(settings, "respond_base_url", env)
    assert resolve_respond_base_url(workspace) == expected
    assert RespondClient(api_key="zzt-key", base_url=workspace).base_url == expected
    assert respond_endpoint("/v2/contact/id:1/message", workspace) == f"{expected}/v2/contact/id:1/message"


def test_every_client_constructor_honours_the_env_override(monkeypatch):
    monkeypatch.setattr(settings, "respond_base_url", OVERRIDE)
    monkeypatch.setattr(
        integration_service,
        "_resolve_workspace_credentials",
        lambda *a, **k: ("zzt-key", f"https://{REAL_HOST}", "1"),
    )
    assert RespondClient().base_url == OVERRIDE
    assert RespondClient.for_identifier(None, "123").base_url == OVERRIDE

    class _Workspace:
        base_url = f"https://{REAL_HOST}"
        space_id = "1"

    monkeypatch.setattr(integration_service, "_decrypt_workspace_key", lambda ws: "zzt-key")
    assert RespondClient.for_workspace(_Workspace()).base_url == OVERRIDE


def test_stock_inquiry_send_with_override_makes_zero_calls_to_the_real_host(monkeypatch):
    """The SI submit/void notice job (what the worker runs after `_enqueue_stock_inquiry_
    respond_message`), on a copy whose workspace row still says the real host."""
    from app.database import SessionLocal
    from app.models.integration import IntegrationLog
    from app.services import crm_chat_outbound_webhook
    from app.tasks import respond_io_tasks

    monkeypatch.setattr(settings, "respond_base_url", OVERRIDE)
    # A prod-clone workspace row: real key shape, real host.
    monkeypatch.setattr(
        integration_service,
        "_resolve_workspace_credentials",
        lambda *a, **k: ("zzt-key", f"https://{REAL_HOST}", "1"),
    )
    # The CRM's own n8n mirror is not Respond.io and is not under test.
    monkeypatch.setattr(
        crm_chat_outbound_webhook, "enqueue_crm_chat_outbound_webhook", lambda *a, **k: None
    )

    seen: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path.endswith("/message/list"):
            return httpx.Response(200, json={"items": []})
        return httpx.Response(200, json={"messageId": 1, "contactId": 1})

    monkeypatch.setattr(
        RespondClient,
        "_http",
        staticmethod(lambda timeout=15: httpx.Client(transport=httpx.MockTransport(_handler))),
    )

    inquiry_id = str(uuid.uuid4())
    try:
        try:
            respond_io_tasks.send_stock_inquiry_respond_message(
                inquiry_id,
                f"9{uuid.uuid4().int % 10**8:08d}",  # unknown contact: the kill switch fails open
                "ZZT stock inquiry received",
                "1",
                None,
                "1",
                False,
                None,
            )
        except Exception:  # noqa: BLE001 - a downstream failure still must not reach the real host
            pass
    finally:
        db = SessionLocal()
        try:
            labels = [
                row.endpoint
                for row in db.query(IntegrationLog).filter(IntegrationLog.business_id == inquiry_id)
            ]
            db.query(IntegrationLog).filter(IntegrationLog.business_id == inquiry_id).delete(
                synchronize_session=False
            )
            db.commit()
        finally:
            db.close()

    assert seen, "the send path made no Respond.io request at all; the test proves nothing"
    assert not [u for u in seen if REAL_HOST in u], f"real Respond.io host was called: {seen}"
    assert all(u.startswith(OVERRIDE + "/") for u in seen), seen
    # The outbox row names the URL actually used, not a hard-coded real one.
    assert labels and all(REAL_HOST not in (label or "") for label in labels), labels
