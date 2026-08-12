"""Revision ids must fit the ``alembic_version.version_num`` column we provision.

alembic creates that column as ``VARCHAR(32)``, sized for its own 12-char hashes.
This project names revisions descriptively instead ("313_purchase_request_pic"),
and 60-odd of them run past 32 characters. The long-lived databases were widened at
some point - production is ``varchar(255)`` - so the mismatch stayed invisible.

A FRESH database is where it bites: alembic creates the table at 32 and the stamp
dies with

    StringDataRightTruncation: value too long for type character varying(32)
    [SQL: INSERT INTO alembic_version (version_num) VALUES ('...')]

which surfaced in CI's `bootstrap_env.py` step, so the whole backend suite reported
a failure that had nothing to do with the code under test. `bootstrap_env` now
provisions the column at the real width; these tests keep the two facts in sync.
"""
from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from scripts.bootstrap_env import ALEMBIC_VERSION_NUM_WIDTH


def _script_directory() -> ScriptDirectory:
    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_every_revision_id_fits_the_provisioned_column():
    """The invariant is relative to what we provision, not to alembic's default:
    a new id only has to fit the column `bootstrap_env` guarantees."""
    too_long = {
        rev.revision: len(rev.revision)
        for rev in _script_directory().walk_revisions()
        if len(rev.revision) > ALEMBIC_VERSION_NUM_WIDTH
    }
    assert not too_long, (
        f"revision ids longer than the provisioned varchar({ALEMBIC_VERSION_NUM_WIDTH}): "
        f"{too_long}. Shorten the id, or widen ALEMBIC_VERSION_NUM_WIDTH and make sure "
        "every existing database is widened with it."
    )


def test_the_head_fits_even_an_unwidened_database():
    """Extra belt for the head specifically. `bootstrap_env` widens the column
    before stamping, but a database provisioned some other way (a plain `alembic
    stamp`, a tool that creates the table itself) still gets 32 - and the head is
    the one id such a database is guaranteed to write.
    """
    ALEMBIC_DEFAULT_WIDTH = 32
    heads = _script_directory().get_heads()
    oversized = {h: len(h) for h in heads if len(h) > ALEMBIC_DEFAULT_WIDTH}
    assert not oversized, (
        f"head revision id exceeds alembic's own varchar({ALEMBIC_DEFAULT_WIDTH}): "
        f"{oversized}. A fresh database that alembic creates the version table for "
        "will fail to stamp it."
    )


def test_migration_graph_has_a_single_head():
    """A branch merge that forks the graph fails deploy the same way: silently on
    this machine, loudly in whatever runs `upgrade head`."""
    heads = _script_directory().get_heads()
    assert len(heads) == 1, f"expected a single alembic head, found {heads}"
