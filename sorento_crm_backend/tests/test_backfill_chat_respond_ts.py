"""Backfill of chat_histories.respond_ts from the Respond message id.

Covers UAC OBS-S4-31.

CAVEAT ON COVERAGE: these run on sqlite, which has no server-side cursors, so they
CANNOT reproduce the production failure that prompted the rewrite — psycopg2's
"named cursor isn't valid anymore", raised when `yield_per`'s server-side cursor is
killed by a mid-iteration `commit()`. What they do pin is the keyset paging that
replaced it: that committing mid-run neither skips nor re-processes rows, and that
a dry run writes nothing.
"""
import importlib.util
import os
import sys
from datetime import datetime

import pytest
from sqlalchemy import BigInteger, Integer, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import JSON

from app.database import Base
from app.models.chat_history import ChatHistory

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "backfill_chat_respond_ts.py",
)


def _load_script():
    spec = importlib.util.spec_from_file_location("backfill_chat_respond_ts", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def engine():
    for col in ChatHistory.__table__.columns:
        if isinstance(col.type, (JSONB, ARRAY)):
            col.type = JSON()
            col.server_default = None
        if col.primary_key and isinstance(col.type, BigInteger):
            col.type = Integer()
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng, tables=[ChatHistory.__table__])
    return eng


@pytest.fixture
def run(engine, monkeypatch):
    """Run the script's main() against the in-memory DB with given argv."""
    mod = _load_script()
    monkeypatch.setattr(mod, "SessionLocal", sessionmaker(bind=engine))

    def _run(*argv):
        monkeypatch.setattr(sys, "argv", ["backfill", *argv])
        return mod.main()

    return _run


# Real production shapes: sent_at within a second of the id's own timestamp.
ROWS = [
    ("1784602082000000", datetime(2026, 7, 21, 2, 48, 2), "incoming"),
    ("1784602125363985", datetime(2026, 7, 21, 2, 48, 45, 363000), "outgoing"),
    ("1784602116000000", datetime(2026, 7, 21, 2, 48, 36), "incoming"),
    ("1234556", datetime(2026, 7, 21, 2, 48, 50), "outgoing"),  # not a timestamp
]


def _seed(engine, rows=ROWS, delivery_status=None):
    s = sessionmaker(bind=engine)()
    for mid, sent, typ in rows:
        s.add(ChatHistory(
            channel="whatsapp", contact_id="437264483", phone_number="+60166753328",
            message="x", sent_at=sent, type=typ, message_id=mid,
            delivery_status=delivery_status, resolve_attempts=5,
        ))
    s.commit()
    s.close()


def _fetch(engine):
    s = sessionmaker(bind=engine)()
    out = s.query(ChatHistory).order_by(ChatHistory.id.asc()).all()
    s.close()
    return out


def test_dry_run_writes_nothing(engine, run, capsys):
    _seed(engine)
    run("--dry-run")
    assert all(r.respond_ts is None for r in _fetch(engine))
    assert "dry run, nothing written" in capsys.readouterr().out


@pytest.mark.parametrize("batch", ["1", "2", "1000"])
def test_every_derivable_row_is_filled_regardless_of_batch_size(engine, run, batch):
    """batch=1 commits per row — the paging path that a mid-loop commit breaks."""
    _seed(engine)
    run("--batch", batch)

    rows = _fetch(engine)
    assert [r.respond_ts for r in rows] == [
        datetime(2026, 7, 21, 2, 48, 2),
        datetime(2026, 7, 21, 2, 48, 45, 363985),
        datetime(2026, 7, 21, 2, 48, 36),
        None,  # 1234556 is not a plausible timestamp
    ]


def test_rerun_is_a_no_op(engine, run, capsys):
    _seed(engine)
    run("--batch", "1")
    before = [r.respond_ts for r in _fetch(engine)]

    capsys.readouterr()
    run("--batch", "1")
    assert "respond_ts_set=0" in capsys.readouterr().out
    assert [r.respond_ts for r in _fetch(engine)] == before


def test_false_not_sent_cleared_only_for_rows_we_can_vouch_for(engine, run):
    """Respond minting an id proves the message existed; an unparseable id proves nothing."""
    _seed(engine, delivery_status="not_sent")
    run("--batch", "2")

    rows = _fetch(engine)
    for row in rows[:3]:
        assert row.delivery_status is None and row.resolve_attempts == 0
    # The unparseable row keeps its verdict rather than being silently absolved.
    assert rows[3].delivery_status == "not_sent"
    assert rows[3].resolve_attempts == 5
