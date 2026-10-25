"""The CHAT-INBOX-QUEUE hand-test replay tool is safe to run (RED, review round 4).

`scripts/inbox_queue_replay.py` rewires a running copy (its default respond workspace, its
direct-ingress switch, its webhook keys) for a local replay and puts everything back. These
tests pin the guards the reviewer and the security reviewer asked for, against a contract the
coder now builds to:

* `check_target(*, database_url, api, environ) -> list[str]`: the reasons to REFUSE (empty =
  go): the database host is not loopback; `DATABASE_URL` or `DIRECT_URL` is already exported
  in the process environment; `--api` is not http(s) on localhost / 127.0.0.1 / [::1]. (Round
  6: NO rule on the database NAME; crew copies are neutralised prod clones named
  `sorento_prod_<date>`. What makes a copy safe is `check_neutralised`, below.)
* `detect_leftover(db, *, state_file) -> list[str]`: the reasons an earlier run was not
  cleaned up: its state file exists; the default workspace's `base_url` or sender URL points
  at a loopback host; the direct-ingress contact list holds a `zzt-replay-` id.
* `main(argv: list[str] | None = None) -> int`: refuses (returns non-zero, writes nothing:
  no report, no state file, no database change, no `Replay` built) on any reason above;
  `--state-file PATH` names the crash-safety file; `--restore-from PATH` restores from one.
* `Replay.setup()` writes the original values (ciphertexts only) to `args.state_file`, mode
  0600, BEFORE it changes anything; `restore_from_file(path)` puts them back after a crash and
  removes the file; `install_signal_handlers(replay)` turns SIGTERM / SIGHUP into the same
  restore, then exits non-zero.
* `Replay.restore()` first commits a change that closes every open row of the synthetic
  contact (`failed`) and sets the switch back, then waits (bounded) for the contact's drain
  mutex `chatbot:drain:{contact}` to be gone, and only then writes back the workspace's
  `base_url`, API key and sender; `--keep-rows` still closes the open rows.
* The synthetic phone starts `+000` (no normalizer turns it into a real number), and every
  existing webhook signing key stays verifiable when the tool appends its own.

The script is imported by path. Database tests use the lane's throwaway DB (`SessionLocal`)
under the inbox-queue lock, with their own settings row and default workspace, removed at
teardown; detection tests use a blank schema.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import signal
import socket
import stat
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

import pytest
import redis as redis_lib
from sqlalchemy import event, text

from app.config import settings
from app.database import SessionLocal
from app.database import engine as db_engine
from app.utils.field_encryption import decrypt_secret, encrypt_secret
from tests.chatbot.test_inbox_queue_order import iq_serial, redis_client  # noqa: F401 - fixtures

BACKEND = Path(__file__).resolve().parents[1]
TOOL_PATH = BACKEND / "scripts" / "inbox_queue_replay.py"
ORIGINAL_API_KEY = "zzt-orig-api-key-plain-0001"
ORIGINAL_SENDER_KEY = "zzt-orig-sender-key-plain-0001"
ORIGINAL_BASE_URL = "https://api.respond.io"
ORIGINAL_SENDER_URL = "https://automate-zzt.example.com/webhook/orig-sender"
VALID_DB = "postgresql://sorento_crm:zzt@localhost:5432/sorento_iqr_copy"
VALID_API = "http://localhost:8106"
# The database this process actually connects to (the lane's throwaway copy).
THROWAWAY_URL = str(settings.database_url)
NEUTRAL_RESPOND = "https://api.respond.invalid"
NEUTRAL_N8N = "https://n8n.invalid/webhook"


def neutral_env_text(database_url: str) -> str:
    """An env file shaped like a crew copy's: respond.io and n8n on `.invalid`, no SMTP host,
    and egress through a dead loopback proxy (nothing listens on its port)."""
    return (
        f"DATABASE_URL={database_url}\nDIRECT_URL={database_url}\n"
        f"RESPOND_BASE_URL={NEUTRAL_RESPOND}\nN8N_WEBHOOK_URL={NEUTRAL_N8N}\nSMTP_HOST=\n"
        f"HTTPS_PROXY=http://127.0.0.1:{_free_port()}\n"
    )


def _tool():
    spec = importlib.util.spec_from_file_location("zzt_inbox_queue_replay", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _tool()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _key(n: int) -> str:
    return f"zzt-webhook-signing-key-{n:02d}-{'x' * 20}"  # >= 24 chars, like respond.io's


# --------------------------------------------------------------------------- #
# 2. The target guard
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("database_url", "api", "environ"),
    [
        (VALID_DB, VALID_API, {}),
        ("postgresql://u:p@127.0.0.1:5432/sorento_iqr_copy", "http://127.0.0.1:8106", {}),
        ("postgresql://u:p@[::1]:5432/sorento_iqr_copy", "http://[::1]:8106", {}),
        (VALID_DB, "https://localhost:8443", {}),
        ("postgresql://u:p@localhost:5432/sorento_prod_1020", VALID_API, {}),
        ("postgresql://u:p@localhost:5432/sorento_cagent_stack", VALID_API, {}),
    ],
    ids=["localhost", "127.0.0.1", "ipv6-loopback", "https-localhost", "crew-prod-clone-name", "any-local-name"],
)
def test_check_target_accepts_a_local_copy(tool, database_url, api, environ):
    assert tool.check_target(database_url=database_url, api=api, environ=environ) == []


@pytest.mark.parametrize(
    ("database_url", "api", "environ"),
    [
        ("postgresql://u:p@10.0.0.5:5432/sorento_iqr_copy", VALID_API, {}),
        ("postgresql://u:p@db.example-zzt.com:5432/sorento_iqr_copy", VALID_API, {}),
        (VALID_DB, VALID_API, {"DATABASE_URL": VALID_DB}),
        (VALID_DB, VALID_API, {"DIRECT_URL": VALID_DB}),
        (VALID_DB, "https://staging.example-zzt.com", {}),
        (VALID_DB, "http://192.168.1.5:8000", {}),
        (VALID_DB, "http://localhost.evil-zzt.com:8106", {}),
        (VALID_DB, "ftp://localhost:8106", {}),
    ],
    ids=[
        "db-private-ip", "db-remote-name",
        "database-url-exported", "direct-url-exported", "api-remote", "api-lan-ip",
        "api-lookalike-host", "api-not-http",
    ],
)
def test_check_target_refuses_anything_but_a_local_copy(tool, database_url, api, environ):
    reasons = tool.check_target(database_url=database_url, api=api, environ=environ)
    assert reasons, f"must refuse {database_url} / {api} / {sorted(environ)}"
    assert all(isinstance(r, str) and r for r in reasons)


def _db_counts() -> tuple[int, int, int]:
    db = SessionLocal()
    try:
        return (
            int(db.execute(text("SELECT count(*) FROM system_settings")).scalar()),
            int(db.execute(text("SELECT count(*) FROM respond_workspaces")).scalar()),
            int(db.execute(text("SELECT count(*) FROM respond_contacts WHERE respond_io_id LIKE 'zzt-replay-%'")).scalar()),
        )
    finally:
        db.close()


class _ReachedTheRun(Exception):
    pass


@pytest.fixture()
def guarded_main(tool, monkeypatch, tmp_path, iq_serial):
    """`main` with the copy reported healthy and `Replay` replaced by a sentinel: getting
    past the guard means building it, so a refusal can only come from the guard."""
    built: list[Any] = []

    class _Sentinel:
        def __init__(self, args):
            built.append(args)
            raise _ReachedTheRun()

    monkeypatch.setattr(tool, "healthy", lambda api: True)
    monkeypatch.setattr(tool, "Replay", _Sentinel)
    monkeypatch.setenv("SORENTO_ENV_FILE", os.environ.get("SORENTO_ENV_FILE", ".env.ci-tests"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DIRECT_URL", raising=False)

    def _run(
        *, database_url: str | None = None, api: str = VALID_API, state: Path | None = None, env_text: str | None = None
    ) -> dict[str, Any]:
        database_url = database_url or THROWAWAY_URL
        env_file = tmp_path / "zzt-copy.env"
        env_file.write_text(env_text if env_text is not None else neutral_env_text(database_url))
        out = tmp_path / "report.md"
        state_file = state or (tmp_path / "replay-state.json")
        argv = [
            "--env-file", str(env_file), "--api", api, "--port", str(_free_port()),
            "--out", str(out), "--state-file", str(state_file), "--no-restart",
        ]
        before = _db_counts()
        try:
            rc = tool.main(argv)
        except _ReachedTheRun:
            rc = "reached"
        except SystemExit as exc:  # argparse: the flags the contract names are missing
            pytest.fail(f"main exited through argparse ({exc.code}): it does not take the contract's flags")
        return {"rc": rc, "built": list(built), "out": out.exists(), "state": state_file,
                "db_changed": _db_counts() != before}

    return _run


@pytest.mark.parametrize(
    "case",
    ["db-remote", "database-url-exported", "api-remote"],
)
def test_main_refuses_a_target_that_is_not_a_local_copy(guarded_main, monkeypatch, case):
    kwargs: dict[str, Any] = {}
    if case == "db-remote":
        kwargs["database_url"] = "postgresql://u:p@db.example-zzt.com:5432/sorento_iqr_copy"
    elif case == "database-url-exported":
        monkeypatch.setenv("DATABASE_URL", VALID_DB)
    else:
        kwargs["api"] = "https://staging.example-zzt.com"
    run = guarded_main(**kwargs)
    assert run["rc"] != "reached" and run["built"] == [], f"{case}: main went past the guard"
    assert isinstance(run["rc"], int) and run["rc"] != 0, f"{case}: refusal must exit non-zero, got {run['rc']!r}"
    assert not run["out"] and not run["state"].exists(), f"{case}: a refused run wrote a file"
    assert not run["db_changed"], f"{case}: a refused run changed the database"


def test_main_refuses_when_an_earlier_runs_state_file_is_left(guarded_main, tmp_path):
    leftover = tmp_path / "leftover-state.json"
    leftover.write_text(json.dumps({"contact": "zzt-replay-0000000000"}))
    run = guarded_main(state=leftover)
    assert run["rc"] != "reached" and run["built"] == [], "main went past a leftover state file"
    assert isinstance(run["rc"], int) and run["rc"] != 0
    assert leftover.read_text() == json.dumps({"contact": "zzt-replay-0000000000"}), "the leftover was overwritten"


def test_main_reaches_the_run_for_a_local_copy(guarded_main):
    """The positive control: a clean local target gets past every guard."""
    run = guarded_main()
    assert run["rc"] == "reached", f"a clean local copy was refused: rc={run['rc']!r}"


@pytest.fixture()
def blank_db() -> Iterator[Any]:
    from tests._pg_fixture import blank_session

    with blank_session() as db:
        yield db


def _detection_world(db, *, base_url: str = ORIGINAL_BASE_URL, sender_url: str = ORIGINAL_SENDER_URL, contacts: str | None = None):
    from app.models.user import SystemSetting
    from app.schemas.respond_workspace import RespondWorkspaceCreate
    from app.services.respond_workspace_service import RespondWorkspaceService

    db.add(SystemSetting(
        id=str(uuid.uuid4()), name="ZZT replay detect",
        chatbot_direct_ingress_mode="contacts" if contacts else "off", chatbot_direct_ingress_contacts=contacts,
    ))
    workspace = RespondWorkspaceService(db).create(
        RespondWorkspaceCreate(space_id="ZZT-replay-detect", api_key="k", is_default=True)
    )
    workspace.base_url = base_url
    workspace.chatbot_sender_url = sender_url
    db.commit()


def test_detect_leftover_finds_nothing_on_a_clean_copy(tool, blank_db, tmp_path):
    _detection_world(blank_db)
    assert tool.detect_leftover(blank_db, state_file=str(tmp_path / "absent.json")) == []


@pytest.mark.parametrize("leftover", ["state-file", "base-url", "sender-url", "contact-list"])
def test_detect_leftover_finds_an_earlier_run_not_cleaned_up(tool, blank_db, tmp_path, leftover):
    state_file = tmp_path / "state.json"
    kwargs: dict[str, Any] = {}
    if leftover == "state-file":
        state_file.write_text("{}")
    elif leftover == "base-url":
        kwargs["base_url"] = "http://127.0.0.1:8399"
    elif leftover == "sender-url":
        kwargs["sender_url"] = "https://127.0.0.1:8399/sender"
    else:
        kwargs["contacts"] = "zzt-replay-1a2b3c4d5e"
    _detection_world(blank_db, **kwargs)
    assert tool.detect_leftover(blank_db, state_file=str(state_file)), f"missed the leftover {leftover}"


# --------------------------------------------------------------------------- #
# 3-5. setup / restore on the throwaway database
# --------------------------------------------------------------------------- #


class CopyWorld:
    """A settings row and a default respond workspace with known originals, a Replay
    built against them, and teardown of everything a run can leave."""

    def __init__(
        self, tool, tmp_path: Path, redis_client, *, webhook_keys: list[str], keep_rows: bool = False,
        base_url: str | None = ORIGINAL_BASE_URL, sender_url: str | None = ORIGINAL_SENDER_URL,
    ):
        from app.models.respond_workspace import RespondWorkspace
        from app.models.user import SystemSetting

        self.tool = tool
        self.redis = redis_client
        self.webhook_keys = webhook_keys
        db = SessionLocal()
        try:
            assert db.query(SystemSetting).count() == 0, "the throwaway DB already has a settings row"
            assert db.query(RespondWorkspace).filter(RespondWorkspace.is_default.is_(True)).count() == 0
            self.settings_id = str(uuid.uuid4())
            self.webhook_cipher = encrypt_secret(",".join(webhook_keys))
            db.add(SystemSetting(
                id=self.settings_id, name="ZZT replay copy", chatbot_direct_ingress_mode="off",
                chatbot_direct_ingress_contacts=None, respond_webhook_secret_ciphertext=self.webhook_cipher,
            ))
            self.api_cipher = encrypt_secret(ORIGINAL_API_KEY)
            self.sender_cipher = encrypt_secret(ORIGINAL_SENDER_KEY)
            workspace = RespondWorkspace(
                space_id="zzt-replay-copy", name="ZZT replay copy", is_default=True, is_active=True,
                api_key_ciphertext=self.api_cipher, base_url=base_url,
                chatbot_sender_url=sender_url, chatbot_sender_key_ciphertext=self.sender_cipher,
            )
            db.add(workspace)
            db.commit()
            self.workspace_id = str(workspace.id)
        finally:
            db.close()
        self.state_file = tmp_path / "replay-state.json"
        self.args = argparse.Namespace(
            env_file=os.environ.get("SORENTO_ENV_FILE", ".env.ci-tests"), api="http://localhost:1",
            port=_free_port(), out=str(tmp_path / "report.md"), scenarios="", no_restart=True,
            keep_rows=keep_rows, state_file=str(self.state_file), restore_from=None, restart_cmd=None,
        )
        self.replay = tool.Replay(self.args)

    def workspace(self) -> dict[str, Any]:
        db = SessionLocal()
        try:
            row = db.execute(
                text(
                    "SELECT base_url, api_key_ciphertext, chatbot_sender_url, chatbot_sender_key_ciphertext "
                    "FROM respond_workspaces WHERE id = CAST(:i AS uuid)"
                ),
                {"i": self.workspace_id},
            ).first()
            return dict(zip(("base_url", "api_key", "sender_url", "sender_key"), row)) if row else {}
        finally:
            db.close()

    def setting(self) -> dict[str, Any]:
        db = SessionLocal()
        try:
            row = db.execute(
                text(
                    "SELECT chatbot_direct_ingress_mode, chatbot_direct_ingress_contacts, "
                    "respond_webhook_secret_ciphertext FROM system_settings WHERE id = :i"
                ),
                {"i": self.settings_id},
            ).first()
            return dict(zip(("mode", "contacts", "webhook"), row)) if row else {}
        finally:
            db.close()

    def statuses(self) -> list[str]:
        db = SessionLocal()
        try:
            return [
                r[0]
                for r in db.execute(
                    text("SELECT status FROM chatbot.turns WHERE contact_respond_id = :c ORDER BY message_id"),
                    {"c": self.replay.contact},
                )
            ]
        finally:
            db.close()

    def open_rows(self) -> None:
        """A queued and a processing row of the synthetic contact (a drain was mid-run)."""
        db = SessionLocal()
        try:
            for i, status in enumerate(("processing", "queued")):
                db.execute(
                    text(
                        "INSERT INTO chatbot.turns (id, contact_respond_id, message_id, ingress, envelope, is_test, "
                        "status, stage, attempt, trace) VALUES (gen_random_uuid(), :c, :m, 'respond_webhook', "
                        "CAST('{}' AS jsonb), false, :s, :s, 1, CAST(:t AS jsonb))"
                    ),
                    {"c": self.replay.contact, "m": f"zzt-replay-msg-{i}", "s": status,
                     "t": json.dumps([{"facts": {"inbox": True}}])},
                )
            db.commit()
        finally:
            db.close()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.replay.local.server.server_close()
        db = SessionLocal()
        try:
            contacts = [
                r[0] for r in db.execute(text("SELECT respond_io_id FROM respond_contacts WHERE respond_io_id LIKE 'zzt-replay-%'"))
            ] + [self.replay.contact]
            for cid in set(contacts):
                pk = db.execute(text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), {"c": cid}).scalar()
                db.execute(text("DELETE FROM chatbot.turns WHERE contact_respond_id = :c"), {"c": cid})
                db.execute(text("DELETE FROM integration_log WHERE external_reference = :c"), {"c": cid})
                db.execute(text("DELETE FROM chat_histories WHERE contact_id = :c"), {"c": cid})
                if pk:
                    db.execute(text("DELETE FROM contact_media_limit WHERE contact_id = :pk"), {"pk": pk})
                db.execute(text("DELETE FROM respond_contacts WHERE respond_io_id = :c"), {"c": cid})
            db.execute(text("DELETE FROM system_settings WHERE id = :i"), {"i": self.settings_id})
            db.execute(text("DELETE FROM respond_workspaces WHERE id = CAST(:i AS uuid)"), {"i": self.workspace_id})
            db.execute(text("DELETE FROM system_settings WHERE name = 'ZZT replay'"))
            db.execute(text("DELETE FROM respond_workspaces WHERE space_id = 'zzt-replay'"))
            db.commit()
        finally:
            db.close()
        for key in list(self.redis.scan_iter("*zzt-replay-*")):
            self.redis.delete(key)


@pytest.fixture()
def copy_world(tool, tmp_path, redis_client, iq_serial) -> Iterator[Any]:
    worlds: list[CopyWorld] = []

    def _make(**kwargs: Any) -> CopyWorld:
        world = CopyWorld(tool, tmp_path, redis_client, webhook_keys=kwargs.pop("webhook_keys", [_key(1), _key(2)]), **kwargs)
        worlds.append(world)
        return world

    try:
        yield _make
    finally:
        for world in worlds:
            world.close()


@pytest.mark.parametrize("keep_rows", [False, True], ids=["remove-rows", "keep-rows"])
def test_restore_closes_open_rows_and_the_switch_before_the_drain_lets_go_and_only_then_the_workspace(
    copy_world, keep_rows
):
    """Item 3: restore FIRST commits closing every open row of the synthetic contact
    (`failed`) and the switch back, THEN waits for the contact's drain mutex to be gone, and
    only THEN writes back the workspace (base_url, API key, sender). With `--keep-rows` the
    open rows are still closed, never left queued."""
    world = copy_world(keep_rows=keep_rows)
    world.replay.setup()
    world.open_rows()
    drain = f"chatbot:drain:{world.replay.contact}"
    world.redis.set(drain, "zzt-a-drain-finishing-its-row", px=1500)
    seen: list[dict[str, Any]] = []

    def at_workspace_write(conn, cursor, statement, parameters, context, executemany):
        head = statement.lstrip().upper()
        if seen or not (head.startswith("UPDATE") or head.startswith("DELETE")) or "respond_workspaces" not in statement:
            return
        seen.append({"statuses": world.statuses(), "mode": world.setting().get("mode"), "drain_alive": bool(world.redis.exists(drain))})

    event.listen(db_engine, "before_cursor_execute", at_workspace_write)
    try:
        world.replay.restore()
    finally:
        event.remove(db_engine, "before_cursor_execute", at_workspace_write)

    assert seen, "restore never wrote the workspace back"
    moment = seen[0]
    assert moment["statuses"] and all(s == "failed" for s in moment["statuses"]), (
        f"the workspace was restored while the contact still had open rows: {moment['statuses']}"
    )
    assert moment["mode"] == "off", f"the workspace was restored before the switch was set back: {moment['mode']}"
    assert moment["drain_alive"] is False, "the workspace was restored while the contact's drain was still running"
    assert world.workspace() == {
        "base_url": ORIGINAL_BASE_URL, "api_key": world.api_cipher,
        "sender_url": ORIGINAL_SENDER_URL, "sender_key": world.sender_cipher,
    }
    if keep_rows:
        assert world.statuses() and all(s == "failed" for s in world.statuses()), world.statuses()


def test_setup_writes_the_original_values_to_a_0600_state_file_before_changing_anything(copy_world):
    """Item 4: the originals (ciphertexts only) are on disk, readable by the owner only,
    before the first write to the copy."""
    world = copy_world()
    first_write: list[bool] = []

    def at_first_write(conn, cursor, statement, parameters, context, executemany):
        head = statement.lstrip().upper()
        touches = any(t in statement for t in ("system_settings", "respond_workspaces", "respond_contacts"))
        if not first_write and touches and head.startswith(("UPDATE", "INSERT", "DELETE")):
            first_write.append(world.state_file.exists())

    event.listen(db_engine, "before_cursor_execute", at_first_write)
    try:
        world.replay.setup()
    finally:
        event.remove(db_engine, "before_cursor_execute", at_first_write)
    try:
        assert first_write == [True], "the state file must exist before the first write to the copy"
        assert stat.S_IMODE(world.state_file.stat().st_mode) == 0o600, oct(stat.S_IMODE(world.state_file.stat().st_mode))
        saved = world.state_file.read_text()
        for cipher in (world.api_cipher, world.sender_cipher, world.webhook_cipher):
            assert cipher in saved, "the state file must hold the original ciphertexts"
        for plain in (ORIGINAL_API_KEY, ORIGINAL_SENDER_KEY, *world.webhook_keys, world.replay.sender_key, world.replay.signing_key):
            assert plain not in saved, "the state file must never hold a plaintext secret"
    finally:
        world.replay.restore()


def test_restore_from_the_state_file_after_a_crash(tool, copy_world):
    """Item 4: the run died after setup (no restore ran). `restore_from_file` puts the copy
    back from the state file alone, closes the synthetic contact's open rows, and removes
    the file so the next run is not refused as a leftover."""
    world = copy_world()
    world.replay.setup()
    world.open_rows()
    contact = world.replay.contact
    assert world.state_file.exists(), "setup wrote no state file"

    tool.restore_from_file(str(world.state_file))

    assert world.workspace() == {
        "base_url": ORIGINAL_BASE_URL, "api_key": world.api_cipher,
        "sender_url": ORIGINAL_SENDER_URL, "sender_key": world.sender_cipher,
    }
    assert world.setting() == {"mode": "off", "contacts": None, "webhook": world.webhook_cipher}
    db = SessionLocal()
    try:
        open_rows = db.execute(
            text("SELECT count(*) FROM chatbot.turns WHERE contact_respond_id = :c AND status IN ('queued', 'processing')"),
            {"c": contact},
        ).scalar()
    finally:
        db.close()
    assert open_rows == 0
    assert not world.state_file.exists(), "a restored state file must be removed"


@pytest.mark.parametrize("signame", ["SIGTERM", "SIGHUP"])
def test_sigterm_and_sighup_only_exit_and_leave_the_restore_to_mains_finally(tool, copy_world, signame):
    """Item 4, as tightened in round 5 (security LOW): the installed handler does NO database
    work; it only raises a non-zero `SystemExit`, and `main`'s `finally` runs the restore
    (called directly; no real signal reaches pytest)."""
    world = copy_world()
    calls: list[int] = []
    world.replay.restore = lambda: calls.append(1)  # type: ignore[method-assign]
    signum = getattr(signal, signame)
    previous = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)}
    try:
        tool.install_signal_handlers(world.replay)
        handler = signal.getsignal(signum)
        assert callable(handler) and handler not in (previous[signum], signal.SIG_DFL, signal.SIG_IGN), (
            f"no handler installed for {signame}"
        )
        with pytest.raises(SystemExit) as exited:
            handler(signum, None)
        assert exited.value.code not in (0, None), f"{signame} must exit non-zero"
        assert calls == [], f"the {signame} handler must not restore itself (main's finally does)"
    finally:
        for sig, old in previous.items():
            signal.signal(sig, old)


def test_the_synthetic_phone_cannot_be_a_real_number(copy_world):
    """Item 5: a `+000` prefix, which no phone normalizer turns into a real number."""
    world = copy_world()
    assert world.replay.phone.startswith("+000"), world.replay.phone


@pytest.mark.parametrize("existing", [3, 10])
def test_every_existing_webhook_signing_key_stays_verifiable(copy_world, existing):
    """Item 5: appending the tool's key keeps every key respond.io signs with verifiable
    (no truncation of the existing ones)."""
    from app.api.v1.public.respond_webhook import webhook_keys

    originals = [_key(i) for i in range(existing)]
    world = copy_world(webhook_keys=originals)
    world.replay.setup()
    try:
        stored = decrypt_secret(world.setting()["webhook"])
        verifiable = set(webhook_keys(stored))
        missing = [k for k in originals if k not in verifiable]
        assert missing == [], f"{len(missing)} of respond.io's own keys stopped verifying: the tool truncated them"
    finally:
        world.replay.restore()


# --------------------------------------------------------------------------- #
# Round 5. Contract additions (the coder builds to these names):
#
# * `check_connected(engine) -> list[str]`: what the engine ACTUALLY connects to. Refuses a
#   `host` / `hostaddr` / `dbname` / `service` key in `engine.url.query`, and runs
#   `SELECT current_database(), inet_server_addr()`: refuses unless the server address is
#   NULL (unix socket) or loopback (round 6: no rule on the name).
# * `resolve_env_file(path) -> str`: the absolute file Settings reads for that value
#   (relative to the backend directory, as `app.config._resolve_settings_env_file` does).
# * `env_file_database_url(path) -> str`: DATABASE_URL as dotenv resolves it (the LAST
#   assignment wins, an `export ` prefix included), read from `resolve_env_file(path)`.
# * `check_target` also refuses a `host=`-style query key and a lowercase `database_url` /
#   `direct_url` in the process environment.
# * `RUN_LOCK_KEY` (int) and `take_run_lock(engine)`: a Postgres advisory lock held for the
#   whole run, taken before preflight; falsy when another session holds it.
# * The state file records `database` (current_database()) and `server_addr`;
#   `restore_from_file` refuses a file recorded against another database.
# * `Replay.restore()` repeats close-then-wait until a pass closes nothing and the drain mutex
#   is gone; on a timeout (`DRAIN_LET_GO_SECONDS`) it keeps the state file, prints the exact
#   `--restore-from` command, does NOT restore the workspace, and signals failure (a non-zero
#   `SystemExit`, or a False return). An interrupt (a second Ctrl-C) during restore prints
#   the same hint.
# --------------------------------------------------------------------------- #


class _ReachedSetup(Exception):
    pass


def _copy_snapshot(world: CopyWorld) -> tuple:
    db = SessionLocal()
    try:
        replay_contacts = db.execute(
            text("SELECT count(*) FROM respond_contacts WHERE respond_io_id LIKE 'zzt-replay-%'")
        ).scalar()
    finally:
        db.close()
    return (tuple(sorted(world.setting().items())), tuple(sorted(world.workspace().items())), replay_contacts)


@pytest.fixture()
def real_main(tool, monkeypatch, tmp_path):
    """`main` with the REAL `Replay` (so its `preflight` runs) against the throwaway copy,
    the copy reported healthy, and `Replay.setup` replaced by a sentinel: reaching setup
    means every guard let the run through. Run on a thread with a bound, so a refusal path
    that hangs is a failure, not a stuck suite."""
    monkeypatch.setattr(tool, "healthy", lambda api: True)
    monkeypatch.setattr(tool.Replay, "setup", lambda self: (_ for _ in ()).throw(_ReachedSetup()))
    # `main` runs on a worker thread here, where `signal.signal` is not allowed; the
    # handlers have their own test.
    monkeypatch.setattr(tool, "install_signal_handlers", lambda replay: None)
    monkeypatch.setenv("SORENTO_ENV_FILE", os.environ.get("SORENTO_ENV_FILE", ".env.ci-tests"))
    for var in ("DATABASE_URL", "DIRECT_URL", "database_url", "direct_url"):
        monkeypatch.delenv(var, raising=False)
    def _run(*, state: Path | None = None, env_text: str | None = None) -> dict[str, Any]:
        env_file = tmp_path / "zzt-crew-copy.env"
        env_file.write_text(env_text if env_text is not None else neutral_env_text(THROWAWAY_URL))
        env_file = str(env_file)
        out = tmp_path / "report.md"
        state_file = state or (tmp_path / "replay-state.json")
        argv = [
            "--env-file", env_file, "--api", VALID_API, "--port", str(_free_port()),
            "--out", str(out), "--state-file", str(state_file), "--no-restart",
        ]
        box: dict[str, Any] = {}

        def _call() -> None:
            try:
                box["rc"] = tool.main(argv)
            except _ReachedSetup:
                box["rc"] = "reached"
            except SystemExit as exc:
                box["rc"] = f"exit {exc.code}"
            except BaseException as exc:  # noqa: BLE001
                box["rc"] = f"raised {type(exc).__name__}: {exc}"

        thread = threading.Thread(target=_call, daemon=True)
        thread.start()
        thread.join(60)
        assert "rc" in box, "main hung (a refusal path that never returns: an unstarted server's shutdown?)"
        return {"rc": box["rc"], "out": out.exists(), "state": state_file}

    return _run


@pytest.mark.parametrize("leftover", ["loopback-base-url", "replay-contact-listed", "ten-webhook-keys"])
def test_main_refuses_through_preflight_and_changes_nothing(real_main, copy_world, leftover):
    """Round 5, item 1 (reviewer): the database half of the guard, reached through `main`.
    A copy an earlier run left rewired, or one already holding ten webhook keys, makes
    `main` return 2 with no state file written and nothing in the database changed."""
    world = copy_world(
        webhook_keys=[_key(i) for i in range(10)] if leftover == "ten-webhook-keys" else [_key(1)],
        base_url=NEUTRAL_RESPOND, sender_url=None,
    )
    db = SessionLocal()
    try:
        if leftover == "loopback-base-url":
            db.execute(
                text("UPDATE respond_workspaces SET base_url = 'http://127.0.0.1:8399' WHERE id = CAST(:i AS uuid)"),
                {"i": world.workspace_id},
            )
        elif leftover == "replay-contact-listed":
            db.execute(
                text("UPDATE system_settings SET chatbot_direct_ingress_contacts = 'zzt-replay-1a2b3c4d5e' WHERE id = :i"),
                {"i": world.settings_id},
            )
        db.commit()
    finally:
        db.close()
    before = _copy_snapshot(world)

    run = real_main()

    assert run["rc"] == 2, f"{leftover}: main must refuse with 2, got {run['rc']!r}"
    assert not run["state"].exists(), f"{leftover}: a refused run wrote a state file"
    assert _copy_snapshot(world) == before, f"{leftover}: a refused run changed the copy"


def test_main_reaches_setup_on_a_clean_copy(real_main, copy_world):
    """The positive control for the real-`Replay` path: a clean, neutralised copy passes."""
    copy_world(base_url=NEUTRAL_RESPOND, sender_url=None)
    run = real_main()
    assert run["rc"] == "reached", f"a clean copy was refused: {run['rc']!r}"


# ----------------------------------------------------------- the connected database


def test_check_connected_passes_the_throwaway_copy(tool, iq_serial):
    assert tool.check_connected(db_engine) == []


class _FakeRow(tuple):
    @property
    def current_database(self):
        return self[0]

    @property
    def inet_server_addr(self):
        return self[1]


class _FakeResult:
    def __init__(self, row):
        self._row = _FakeRow(row)

    def first(self):
        return self._row

    one = fetchone = first

    def __iter__(self):
        return iter([self._row])


class _FakeConnection:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *args, **kwargs):
        return _FakeResult(self.row)

    exec_driver_sql = execute

    def close(self):
        pass


class _FakeEngine:
    def __init__(self, url: str, row: tuple):
        from sqlalchemy.engine import make_url

        self.url = make_url(url)
        self.row = row

    def connect(self):
        return _FakeConnection(self.row)


@pytest.mark.parametrize(
    ("url", "row"),
    [
        ("postgresql://u:p@localhost/sorento_iqr_copy", ("sorento_iqr_copy", "127.0.0.1")),
        ("postgresql://u:p@localhost/sorento_iqr_copy", ("sorento_iqr_copy", None)),
        ("postgresql://u:p@localhost/sorento_iqr_copy", ("sorento_iqr_copy", "::1")),
        ("postgresql://u:p@localhost/sorento_prod_1020", ("sorento_prod_1020", "127.0.0.1")),
        ("postgresql://u:p@localhost/sorento_cagent_stack", ("sorento_cagent_stack", None)),
    ],
    ids=["tcp-loopback", "unix-socket", "ipv6-loopback", "crew-prod-clone", "any-local-name"],
)
def test_check_connected_accepts_a_local_connection(tool, url, row):
    assert tool.check_connected(_FakeEngine(url, row)) == []


@pytest.mark.parametrize(
    ("url", "row"),
    [
        ("postgresql://u:p@localhost/x?host=db.remote.example.com", ("x", None)),
        ("postgresql://u:p@localhost/x?hostaddr=10.1.2.3", ("x", None)),
        ("postgresql://u:p@localhost/x?dbname=sorento_cagent_stack", ("x", None)),
        ("postgresql://u:p@localhost/x?service=prod", ("x", None)),
        ("postgresql://u:p@localhost/sorento_iqr_copy", ("sorento_iqr_copy", "10.1.2.3")),
    ],
    ids=["query-host", "query-hostaddr", "query-dbname", "query-service", "server-remote"],
)
def test_check_connected_refuses_what_the_engine_really_reaches(tool, url, row):
    assert tool.check_connected(_FakeEngine(url, row)), f"must refuse {url} connected to {row}"


def test_check_target_refuses_a_host_hidden_in_the_query_string(tool):
    reasons = tool.check_target(
        database_url="postgresql://u:p@localhost/x?host=db.remote.example.com", api=VALID_API, environ={}
    )
    assert reasons, "a `host=` query key overrides the URL's host; the text check must refuse it"


@pytest.mark.parametrize("var", ["database_url", "direct_url"])
def test_check_target_refuses_a_lowercase_url_in_the_environment(tool, var):
    assert tool.check_target(database_url=VALID_DB, api=VALID_API, environ={var: VALID_DB}), var


def test_the_env_files_last_assignment_wins(tool, tmp_path):
    env = tmp_path / "zzt-copy.env"
    env.write_text(
        f"DATABASE_URL={VALID_DB}\n"
        "# later, someone pointed it elsewhere\n"
        "export DATABASE_URL=postgresql://u:p@db.remote.example.com:5432/sorento_iqr_copy\n"
    )
    assert tool.env_file_database_url(str(env)) == "postgresql://u:p@db.remote.example.com:5432/sorento_iqr_copy"


def test_main_refuses_an_env_file_whose_last_database_url_is_remote(guarded_main):
    run = guarded_main(
        env_text=(
            f"DATABASE_URL={THROWAWAY_URL}\n"
            "export DATABASE_URL=postgresql://u:p@db.remote.example.com:5432/sorento_iqr_copy\n"
        )
    )
    assert run["rc"] != "reached" and run["built"] == [], "main read the first DATABASE_URL, not the one dotenv uses"
    assert isinstance(run["rc"], int) and run["rc"] != 0
    assert not run["state"].exists() and not run["db_changed"]


def test_main_refuses_a_lowercase_database_url_in_the_shell(guarded_main, monkeypatch):
    monkeypatch.setenv("database_url", VALID_DB)
    run = guarded_main()
    assert run["rc"] != "reached" and run["built"] == [], "a lowercase database_url in the shell was ignored"
    assert isinstance(run["rc"], int) and run["rc"] != 0


def test_a_relative_env_file_resolves_the_way_settings_resolves_it(tool, tmp_path, monkeypatch):
    """Settings reads a relative SORENTO_ENV_FILE against the backend directory, not the
    cwd; the tool must judge that same file (a decoy in the cwd must not be read)."""
    name = "zzt-replay-relative.env"
    real = BACKEND / name
    real.write_text(f"DATABASE_URL={VALID_DB}\n")
    try:
        (tmp_path / name).write_text("DATABASE_URL=postgresql://u:p@db.remote.example.com/decoy\n")
        monkeypatch.chdir(tmp_path)
        assert tool.resolve_env_file(name) == str(real)
        assert tool.resolve_env_file(str(real)) == str(real)
        assert tool.env_file_database_url(name) == VALID_DB
    finally:
        real.unlink()


# ----------------------------------------------------------- one run at a time


def test_a_second_run_is_refused_while_the_first_holds_the_run_lock(tool, real_main, copy_world, tmp_path):
    """Round 5, item 3: run 1 holds the advisory lock for its whole run. Run 2 (its own
    state file) is refused before preflight, writes nothing, and never touches run 1's state
    file."""
    copy_world(base_url=NEUTRAL_RESPOND, sender_url=None)
    first_state = tmp_path / "run-1-state.json"
    first_state.write_text(json.dumps({"contact": "zzt-replay-run1000000"}))
    side = db_engine.connect()
    try:
        side.exec_driver_sql("SELECT pg_advisory_lock(%(k)s)", {"k": int(tool.RUN_LOCK_KEY)})
        assert not tool.take_run_lock(db_engine), "the lock is held by run 1; run 2 must not get it"
        run = real_main(state=tmp_path / "run-2-state.json")
    finally:
        with contextlib.suppress(Exception):
            side.exec_driver_sql("SELECT pg_advisory_unlock_all()")
        side.close()
    assert run["rc"] == 2, f"run 2 must be refused while run 1 holds the lock, got {run['rc']!r}"
    assert not run["state"].exists()
    assert first_state.read_text() == json.dumps({"contact": "zzt-replay-run1000000"}), "run 1's state file was touched"


# ----------------------------------------------------------- restore until quiet


def test_restore_closes_a_row_a_drain_reopened_during_the_wait(copy_world):
    """Round 5, item 4: a drain re-queues one of the contact's rows while restore waits for
    its mutex. Restore repeats close-then-wait until a pass closes nothing, so no row is
    left open (keep-rows run, so the rows can be read afterwards)."""
    world = copy_world(keep_rows=True)
    world.replay.setup()
    world.open_rows()
    drain = f"chatbot:drain:{world.replay.contact}"
    world.redis.set(drain, "zzt-a-drain-still-running", px=2500)

    def reopen() -> None:
        time.sleep(0.8)
        db = SessionLocal()
        try:
            db.execute(
                text(
                    "UPDATE chatbot.turns SET status = 'queued', stage = 'queued' "
                    "WHERE contact_respond_id = :c AND message_id = 'zzt-replay-msg-1'"
                ),
                {"c": world.replay.contact},
            )
            db.commit()
        finally:
            db.close()

    reopener = threading.Thread(target=reopen, daemon=True)
    reopener.start()
    world.replay.restore()
    reopener.join(5)
    assert world.statuses() and all(s == "failed" for s in world.statuses()), (
        f"a row a drain re-opened during the wait was left open: {world.statuses()}"
    )


def test_restore_that_times_out_keeps_the_state_file_and_does_not_restore_the_workspace(tool, copy_world, monkeypatch, capsys):
    """Round 5, item 4: the drain mutex never goes. Restore gives up after its bound, keeps
    the state file, prints the exact `--restore-from` command, signals failure, and does NOT
    write the workspace back under a drain that may still be running."""
    monkeypatch.setattr(tool, "DRAIN_LET_GO_SECONDS", 1.0)
    world = copy_world()
    world.replay.setup()
    world.redis.set(f"chatbot:drain:{world.replay.contact}", "zzt-a-drain-that-never-ends", ex=120)
    rewired = world.workspace()

    code: Any = "returned"
    try:
        result = world.replay.restore()
        code = result
    except SystemExit as exc:
        code = exc.code
    output = capsys.readouterr().out

    assert code is False or code not in (0, None, True, "returned"), f"a timed-out restore must signal failure: {code!r}"
    assert world.state_file.exists(), "a timed-out restore must keep the state file"
    assert f"--restore-from {world.state_file}" in output, f"no exact --restore-from hint in: {output!r}"
    assert world.workspace() == rewired, "the workspace was written back while the drain still held its mutex"
    world.redis.delete(f"chatbot:drain:{world.replay.contact}")
    tool.restore_from_file(str(world.state_file))


def test_an_interrupt_during_restore_prints_the_restore_from_hint(tool, copy_world, monkeypatch, capsys):
    """Round 5, item 6: a second Ctrl-C lands while restore runs. The state file stays and
    the operator is told the exact command to finish the job."""
    world = copy_world()
    world.replay.setup()
    real_restore_saved = tool.restore_saved

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(tool, "restore_saved", interrupted)
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        world.replay.restore()
    output = capsys.readouterr().out
    monkeypatch.setattr(tool, "restore_saved", real_restore_saved)
    try:
        assert world.state_file.exists(), "an interrupted restore must keep the state file"
        assert f"--restore-from {world.state_file}" in output, f"no exact --restore-from hint in: {output!r}"
    finally:
        tool.restore_from_file(str(world.state_file))


# ----------------------------------------------------------- the state file names its database


def test_the_state_file_records_the_database_and_server_it_was_written_against(copy_world):
    world = copy_world()
    world.replay.setup()
    try:
        saved = json.loads(world.state_file.read_text())
        db = SessionLocal()
        try:
            current = db.execute(text("SELECT current_database()")).scalar()
        finally:
            db.close()
        assert saved.get("database") == current, f"state file database {saved.get('database')!r} != {current!r}"
        assert "server_addr" in saved, f"the state file must record the server address: {sorted(saved)}"
    finally:
        world.replay.restore()


def test_restore_from_a_state_file_of_another_database_is_refused(tool, copy_world):
    world = copy_world()
    world.replay.setup()
    saved = json.loads(world.state_file.read_text())
    rewired = world.workspace()
    foreign = world.state_file.with_name("other-copy-state.json")
    foreign.write_text(json.dumps({**saved, "database": "sorento_some_other_copy"}))
    try:
        with contextlib.suppress(Exception, SystemExit):
            tool.restore_from_file(str(foreign))
        assert world.workspace() == rewired, "a state file from another database was restored into this one"
        assert foreign.exists(), "a refused state file must be kept"
    finally:
        tool.restore_from_file(str(world.state_file))


def test_the_documented_state_file_location_is_not_under_tmp(tool):
    """Round 5, item 6: /tmp is world-readable on many machines and cleaned at reboot; the
    crash-safety file (and its example) belongs in the user's own space."""
    import re as _re

    default = tool._parser().get_default("state_file") or ""
    assert not str(default).startswith(("/tmp", "/private/tmp")), default
    documented = _re.findall(r"--(?:state-file|restore-from)\s+(\S+)", tool.__doc__ or "")
    assert documented, "the docstring documents no state-file location"
    assert all(not p.startswith(("/tmp", "/private/tmp")) for p in documented), documented


# --------------------------------------------------------------------------- #
# Round 6 (crew re-audit). The copy is judged by NEUTRALISATION, not its database name:
#
# * `check_neutralised(db, env) -> list[str]`, run on the ORIGINAL values before setup (in
#   `main` / `preflight`, never inside `setup`), `env` being the copy's env file values. A
#   reason NAMES the value it refuses. Neutral means: the respond.io base URL (env
#   `RESPOND_BASE_URL` and every `respond_workspaces.base_url`) is empty or a `.invalid` host;
#   every n8n URL (env `N8N_WEBHOOK_URL`, `system_settings.n8n_*_webhook_url`,
#   `respond_workspaces.chatbot_retry_ingress_url`) is empty or `.invalid`; the SMTP host (env
#   `SMTP_HOST`, `system_settings.smtp_host`) is empty or `.invalid`; the workspace
#   `chatbot_sender_url` is empty or loopback; and egress is blocked: `HTTPS_PROXY` (or
#   `https_proxy`) points at a loopback address whose port refuses a TCP connect.
# * `--restart-cmd "<shell command>"`: scenario 4 runs it once itself, then waits for
#   /health down and up as before; `--no-restart` skips it.
# --------------------------------------------------------------------------- #

REAL_LOOKING = "https://automate-zzt.example.com/webhook/real"


def _dead_proxy() -> str:
    return f"http://127.0.0.1:{_free_port()}"


def _crew_env(**overrides: str | None) -> dict[str, str]:
    env = {"RESPOND_BASE_URL": NEUTRAL_RESPOND, "N8N_WEBHOOK_URL": NEUTRAL_N8N, "SMTP_HOST": "", "HTTPS_PROXY": _dead_proxy()}
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def _neutral_db(db, **columns: Any) -> None:
    """A blank-schema copy shaped like a crew copy: everything outbound on `.invalid` or
    empty. `columns` override `settings.<col>` / `workspace.<col>`."""
    from app.models.user import SystemSetting
    from app.schemas.respond_workspace import RespondWorkspaceCreate
    from app.services.respond_workspace_service import RespondWorkspaceService

    row = SystemSetting(id=str(uuid.uuid4()), name="ZZT crew copy")
    db.add(row)
    workspace = RespondWorkspaceService(db).create(
        RespondWorkspaceCreate(space_id="ZZT-crew-copy", api_key="k", is_default=True)  # gitleaks:allow
    )
    workspace.base_url = NEUTRAL_RESPOND
    workspace.chatbot_sender_url = None
    workspace.chatbot_retry_ingress_url = None
    for name, value in columns.items():
        target, column = name.split(".", 1)
        setattr(row if target == "settings" else workspace, column, value)
    db.commit()


@pytest.mark.parametrize("proxy_var", ["HTTPS_PROXY", "https_proxy"])
def test_check_neutralised_passes_a_crew_shaped_copy(tool, blank_db, proxy_var):
    """The crew copy: DB `sorento_prod_1020` on localhost (judged by `check_target`, see
    the accept cases), respond.io and n8n on `.invalid`, no SMTP host, a dead loopback proxy."""
    _neutral_db(blank_db, **{"settings.n8n_attachment_webhook_url": "https://n8n.invalid/webhook/attach"})
    env = _crew_env(HTTPS_PROXY=None)
    env[proxy_var] = _dead_proxy()
    assert tool.check_neutralised(blank_db, env) == []


@pytest.mark.parametrize(
    ("named", "env_overrides", "columns"),
    [
        ("RESPOND_BASE_URL", {"RESPOND_BASE_URL": "https://api.respond.io"}, {}),
        ("base_url", {}, {"workspace.base_url": "https://api.respond.io"}),
        ("N8N_WEBHOOK_URL", {"N8N_WEBHOOK_URL": REAL_LOOKING}, {}),
        ("n8n_attachment_webhook_url", {}, {"settings.n8n_attachment_webhook_url": REAL_LOOKING}),
        ("n8n_crm_chat_outbound_webhook_url", {}, {"settings.n8n_crm_chat_outbound_webhook_url": REAL_LOOKING}),
        ("n8n_stock_inquiry_revise_webhook_url", {}, {"settings.n8n_stock_inquiry_revise_webhook_url": REAL_LOOKING}),
        ("n8n_close_convo_webhook_url", {}, {"settings.n8n_close_convo_webhook_url": REAL_LOOKING}),
        ("chatbot_retry_ingress_url", {}, {"workspace.chatbot_retry_ingress_url": REAL_LOOKING}),
        ("SMTP_HOST", {"SMTP_HOST": "smtp.example-zzt.com"}, {}),
        ("smtp_host", {}, {"settings.smtp_host": "smtp.example-zzt.com"}),
        ("chatbot_sender_url", {}, {"workspace.chatbot_sender_url": REAL_LOOKING}),
        ("proxy", {"HTTPS_PROXY": "http://10.255.255.1:3128"}, {}),
        ("proxy", {"HTTPS_PROXY": None}, {}),
    ],
    ids=[
        "env-respond", "workspace-respond", "env-n8n", "n8n-attachment", "n8n-chat-outbound",
        "n8n-stock-revise", "n8n-close-convo", "retry-ingress", "env-smtp", "settings-smtp",
        "sender-real-host", "proxy-not-loopback", "no-proxy",
    ],
)
def test_check_neutralised_refuses_each_real_looking_value_and_names_it(tool, blank_db, named, env_overrides, columns):
    _neutral_db(blank_db, **columns)
    reasons = tool.check_neutralised(blank_db, _crew_env(**env_overrides))
    assert reasons, f"a copy with a real-looking {named} must be refused"
    assert any(named.lower() in r.lower() for r in reasons), f"no reason names {named}: {reasons}"


def test_check_neutralised_refuses_a_live_proxy(tool, blank_db):
    """A loopback proxy that ANSWERS is a real way out, not a blocked one."""
    _neutral_db(blank_db)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    try:
        port = listener.getsockname()[1]
        reasons = tool.check_neutralised(blank_db, _crew_env(HTTPS_PROXY=f"http://127.0.0.1:{port}"))
    finally:
        listener.close()
    assert reasons and any("proxy" in r.lower() for r in reasons), reasons


@pytest.mark.parametrize("unsafe", ["env-respond", "workspace-respond"])
def test_main_refuses_a_copy_that_is_not_neutralised(real_main, copy_world, unsafe):
    """Through `main`, on the ORIGINAL values: refused with 2, nothing written."""
    if unsafe == "workspace-respond":
        world = copy_world(base_url="https://api.respond.io", sender_url=None)
        env_text = None
    else:
        world = copy_world(base_url=NEUTRAL_RESPOND, sender_url=None)
        env_text = neutral_env_text(THROWAWAY_URL).replace(NEUTRAL_RESPOND, "https://api.respond.io")
    before = _copy_snapshot(world)
    run = real_main(env_text=env_text)
    assert run["rc"] == 2, f"{unsafe}: a copy that is not neutralised must be refused, got {run['rc']!r}"
    assert not run["state"].exists()
    assert _copy_snapshot(world) == before


# ----------------------------------------------------------- one command for the restart


def test_main_accepts_a_restart_command(tool):
    args = tool._parser().parse_args(
        ["--env-file", ".env.zzt", "--api", VALID_API, "--out", "r.md", "--restart-cmd", "zzt-restart-copy-backend"]
    )
    assert args.restart_cmd == "zzt-restart-copy-backend"


class _Commands:
    """Every way the tool could start a process, recorded instead of run."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        self.calls: list[Any] = []
        calls = self.calls

        class _Proc:
            returncode = 0
            pid = 0

            def __init__(self, *args, **kwargs):
                calls.append(args[0] if args else kwargs.get("args"))

            def wait(self, *a, **k):
                return 0

            def poll(self):
                return 0

            def communicate(self, *a, **k):
                return ("", "")

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def _run(*args, **kwargs):
            calls.append(args[0] if args else kwargs.get("args"))
            return subprocess.CompletedProcess(args[0] if args else kwargs.get("args"), 0, "", "")

        def _call(*args, **kwargs):
            calls.append(args[0] if args else kwargs.get("args"))
            return 0

        for name, fake in (("run", _run), ("Popen", _Proc), ("call", _call), ("check_call", _call), ("check_output", lambda *a, **k: _call(*a, **k) and b"" or b"")):
            monkeypatch.setattr(subprocess, name, fake)
        monkeypatch.setattr(os, "system", lambda cmd: calls.append(cmd) or 0)


def _quiet_s4(world: CopyWorld, monkeypatch) -> None:
    """Scenario 4 with no copy behind it: deliveries answer 200, /health goes down then up
    at once, and there is nothing to collect."""
    monkeypatch.setattr(world.replay, "burst", lambda bodies: [200] * len(bodies))
    monkeypatch.setattr(world.replay, "_wait_health", lambda up, timeout: True)
    monkeypatch.setattr(world.replay, "wait_for", lambda mids, deadline, settle=3.0: [])


def test_scenario_4_runs_the_restart_command_once_itself(copy_world, monkeypatch):
    world = copy_world()
    world.args.restart_cmd = "zzt-restart-copy-backend --now"
    world.args.no_restart = False
    commands = _Commands(monkeypatch)
    _quiet_s4(world, monkeypatch)

    result = world.replay.s4(time.monotonic() + 5)

    ran = [c for c in commands.calls if "zzt-restart-copy-backend" in (c if isinstance(c, str) else " ".join(map(str, c or [])))]
    assert len(ran) == 1, f"the restart command must run exactly once, ran {commands.calls}"
    assert ("the backend restarted mid-burst", True) in result["checks"], result["checks"]


def test_scenario_4_with_no_restart_runs_no_command(copy_world, monkeypatch):
    world = copy_world()
    world.args.restart_cmd = "zzt-restart-copy-backend --now"
    world.args.no_restart = True
    commands = _Commands(monkeypatch)
    _quiet_s4(world, monkeypatch)

    result = world.replay.s4(time.monotonic() + 5)

    assert commands.calls == [], f"--no-restart must not run the restart command: {commands.calls}"
    assert not any(name == "the backend restarted mid-burst" for name, _ in result["checks"])
