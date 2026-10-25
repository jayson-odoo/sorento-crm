"""The CHAT-INBOX-QUEUE hand-test replay tool is safe to run (RED, review round 4).

`scripts/inbox_queue_replay.py` rewires a running copy (its default respond workspace, its
direct-ingress switch, its webhook keys) for a local replay and puts everything back. These
tests pin the guards the reviewer and the security reviewer asked for, against a contract the
coder now builds to:

* `check_target(*, database_url, api, environ) -> list[str]`: the reasons to REFUSE (empty =
  go): the database host is not loopback; the database is the shared dev DB
  `sorento_cagent_stack` or its name contains `prod`; `DATABASE_URL` or `DIRECT_URL` is
  already exported in the process environment; `--api` is not http(s) on localhost /
  127.0.0.1 / [::1].
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
    ],
    ids=["localhost", "127.0.0.1", "ipv6-loopback", "https-localhost"],
)
def test_check_target_accepts_a_local_copy(tool, database_url, api, environ):
    assert tool.check_target(database_url=database_url, api=api, environ=environ) == []


@pytest.mark.parametrize(
    ("database_url", "api", "environ"),
    [
        ("postgresql://u:p@10.0.0.5:5432/sorento_iqr_copy", VALID_API, {}),
        ("postgresql://u:p@db.example-zzt.com:5432/sorento_iqr_copy", VALID_API, {}),
        ("postgresql://u:p@localhost:5432/sorento_cagent_stack", VALID_API, {}),
        ("postgresql://u:p@localhost:5432/sorento_prod_copy", VALID_API, {}),
        ("postgresql://u:p@localhost:5432/PROD_mirror", VALID_API, {}),
        (VALID_DB, VALID_API, {"DATABASE_URL": VALID_DB}),
        (VALID_DB, VALID_API, {"DIRECT_URL": VALID_DB}),
        (VALID_DB, "https://staging.example-zzt.com", {}),
        (VALID_DB, "http://192.168.1.5:8000", {}),
        (VALID_DB, "http://localhost.evil-zzt.com:8106", {}),
        (VALID_DB, "ftp://localhost:8106", {}),
    ],
    ids=[
        "db-private-ip", "db-remote-name", "db-shared-dev", "db-prod-in-name", "db-prod-upper",
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

    def _run(*, database_url: str = VALID_DB, api: str = VALID_API, state: Path | None = None) -> dict[str, Any]:
        env_file = tmp_path / "zzt-copy.env"
        env_file.write_text(f"DATABASE_URL={database_url}\nDIRECT_URL={database_url}\n")
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
    ["db-remote", "db-shared-dev", "db-prod", "database-url-exported", "api-remote"],
)
def test_main_refuses_a_target_that_is_not_a_local_copy(guarded_main, monkeypatch, case):
    kwargs: dict[str, Any] = {}
    if case == "db-remote":
        kwargs["database_url"] = "postgresql://u:p@db.example-zzt.com:5432/sorento_iqr_copy"
    elif case == "db-shared-dev":
        kwargs["database_url"] = "postgresql://u:p@localhost:5432/sorento_cagent_stack"
    elif case == "db-prod":
        kwargs["database_url"] = "postgresql://u:p@localhost:5432/sorento_prod_copy"
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

    def __init__(self, tool, tmp_path: Path, redis_client, *, webhook_keys: list[str], keep_rows: bool = False):
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
                api_key_ciphertext=self.api_cipher, base_url=ORIGINAL_BASE_URL,
                chatbot_sender_url=ORIGINAL_SENDER_URL, chatbot_sender_key_ciphertext=self.sender_cipher,
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
            keep_rows=keep_rows, state_file=str(self.state_file), restore_from=None,
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
def test_sigterm_and_sighup_take_the_same_restore_path(tool, copy_world, signame):
    """Item 4: the installed handler restores, then exits non-zero (called directly; no real
    signal reaches pytest)."""
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
        assert calls == [1], f"{signame} must run the restore once"
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
