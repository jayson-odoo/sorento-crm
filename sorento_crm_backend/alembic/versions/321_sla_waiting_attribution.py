"""After-sales S4a: the system learns to say "waiting on someone who is not us".

Three fields on the SLA tracker, the same three on the event log, and two seeded
vocabularies. The tracker answers **what now**; the event log answers **what then**,
because a mutable column cannot say what we were waiting on when a breach happened
and reporting that reads the live column re-attributes every historical breach the
next time somebody edits the case (UAC ruling on AC-M1 versus AC-M7).

**Why the fields are on the tracker and not on the case.** AC-M1 says "a case", which
taken literally is a column on all six ``FORM_SLA_TYPES`` tables plus ``service_jobs``:
six write paths for one dimension. Group M itself speaks per-stage twice (R12 and
AC-M36d both say "on the Schedule stage"), a case running Acknowledge, Assess,
Schedule and Resolve concurrently is not waiting on one party, and AC-M7 counts
breaches, which are trackers. The case-level answer is derived from the case's open
trackers rather than stored. Recorded as Ruling 1 in
``PLAN-after-sales-warranty.md``.

**Both columns hold the lookup option's VALUE, not its id.** AC-M1 names the field
``waiting_on_reason_id`` and an id with a real FK was the first shape built here. It
does not work: every bound column in this system holds the value, and
``lookup_validator`` enforces exactly that on flush, so an id-holding bound column is
rejected by the generic validator (``invalid_lookup_value``), gets no dropdown from its
binding and cannot be mapped by ``POST /api/v1/lookup/resolve``. Unbinding the column to
keep the FK would have made it the only lookup column in the system with a bespoke
validation path. The value IS the stable identity - ``label`` is the display text, and
that is what admins reword - so history stays correct either way, and AC-M7's grouping
by party needs no join. Both vocabularies are ``lookup_options`` rows, which is AC-M1's
"configurable master data" plus the UAC's ruling that the party is configurable too:
AC-M1's own list omits ``dealer`` while AC-M18 requires it, so a code enum was already
one value short on day one.

**``lookup_options.attributes``.** Whether a party is us or a third party has to be a
property of the option, not a tuple in a service, or adding a party silently files it
on one side of the AC-M7 headline. ``lookup_options`` had nowhere to put per-option
metadata that is not a label, so this adds a generic nullable JSONB column rather than
a domain-specific ``is_external`` boolean on a core table. Unset reads as INTERNAL:
when we do not know whose delay it is, the conservative answer is ours, because the
failure mode in the other direction is a report that quietly excuses us.

**The paired-nulls constraint.** AC-M3 renders "waiting on maintenance since 3 Aug".
A party with no ``waiting_since`` renders half a sentence, and a ``waiting_since`` with
no party is a wait on nobody. Both halves are enforced in the database rather than in
the service, because the service is not the only writer a backfill or a fix-up script
ever has.

Every guard here is load-bearing: the shared dev database is stamped on another
worktree's chain, so this DDL gets applied by hand there and a plain ``add_column``
would abort the whole upgrade.

Revision ID: 321_sla_waiting_attribution
Revises: 320_notification_spine_calls
Create Date: 2026-08-03

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "321_sla_waiting_attribution"
down_revision = "320_notification_spine_calls"
branch_labels = None
depends_on = None

_TRACKING = "conversation_sla_tracking"
_EVENT_LOG = "conversation_sla_event_log"
_OPTIONS = "lookup_options"
_SETS = "lookup_sets"
_BINDINGS = "lookup_bindings"

_PARTY_CHECK = "ck_sla_tracking_waiting_party_pair"
_REASON_CHECK = "ck_sla_tracking_waiting_reason_needs_party"


def _inspector():
    return sa.inspect(op.get_bind())


def _tables() -> set:
    return set(_inspector().get_table_names())


def _columns(table: str) -> set:
    return {c["name"] for c in _inspector().get_columns(table)}


def _constraints(table: str) -> set:
    insp = _inspector()
    names = {c["name"] for c in insp.get_check_constraints(table)}
    names |= {c["name"] for c in insp.get_unique_constraints(table)}
    names |= {c.get("name") for c in insp.get_foreign_keys(table)}
    return {n for n in names if n}


def _indexes(table: str) -> set:
    return {ix["name"] for ix in _inspector().get_indexes(table)}


def _add_waiting_columns(table: str) -> None:
    columns = _columns(table)
    if "waiting_on_party" not in columns:
        op.add_column(table, sa.Column("waiting_on_party", sa.String(length=150), nullable=True))
    if "waiting_on_reason" not in columns:
        op.add_column(table, sa.Column("waiting_on_reason", sa.String(length=150), nullable=True))
    if "waiting_since" not in columns:
        op.add_column(table, sa.Column("waiting_since", sa.DateTime(timezone=False), nullable=True))


def upgrade() -> None:
    tables = _tables()

    # ------------------------------------------- per-option metadata (AC-M7's split)
    if _OPTIONS in tables and "attributes" not in _columns(_OPTIONS):
        op.add_column(
            _OPTIONS,
            sa.Column("attributes", sa.dialects.postgresql.JSONB(), nullable=True),
        )

    # ------------------------------------------------------------- the tracker (AC-M1)
    if _TRACKING in tables:
        _add_waiting_columns(_TRACKING)
        existing = _constraints(_TRACKING)
        if _PARTY_CHECK not in existing:
            # Half a pair renders half of AC-M3's sentence. Enforced here because the
            # service is not the only writer a fix-up script ever has.
            op.create_check_constraint(
                _PARTY_CHECK,
                _TRACKING,
                "(waiting_on_party IS NULL) = (waiting_since IS NULL)",
            )
        if _REASON_CHECK not in existing:
            op.create_check_constraint(
                _REASON_CHECK,
                _TRACKING,
                "waiting_on_reason IS NULL OR waiting_on_party IS NOT NULL",
            )
        if "ix_sla_tracking_waiting_party" not in _indexes(_TRACKING):
            # Partial: the overwhelming majority of trackers wait on nobody, and the
            # only queries are "who is waiting" and the AC-M7 grouping.
            op.create_index(
                "ix_sla_tracking_waiting_party",
                _TRACKING,
                ["waiting_on_party"],
                postgresql_where=sa.text("waiting_on_party IS NOT NULL"),
            )

    # ------------------------------------------------------- the event log (AC-M7)
    if _EVENT_LOG in tables:
        _add_waiting_columns(_EVENT_LOG)
        # No paired-nulls check here on purpose: an event log row is a photograph of
        # whatever was true, including a tracker mid-write, and a constraint that can
        # reject a historical record loses the record rather than fixing it.
        if "ix_sla_event_log_waiting_party" not in _indexes(_EVENT_LOG):
            op.create_index(
                "ix_sla_event_log_waiting_party",
                _EVENT_LOG,
                ["waiting_on_party"],
                postgresql_where=sa.text("waiting_on_party IS NOT NULL"),
            )

    # --------------------------------------------------------------- the vocabularies
    #
    # Seeded by the app-side converging seeder rather than by INSERTs written out here,
    # so the party and reason lists exist in exactly ONE place. The alternative is the
    # list living in a migration AND in the service that validates against it, which
    # drifts the first time somebody adds an option to one of them. Same shape as the
    # F1a line-disposition seed.
    if {_SETS, _OPTIONS, _BINDINGS} <= tables:
        from sqlalchemy.orm import Session

        from app.services.sla_waiting_service import seed_sla_waiting_lookups

        session = Session(bind=op.get_bind())
        try:
            seed_sla_waiting_lookups(session)
            session.commit()
        finally:
            session.close()


def downgrade() -> None:
    tables = _tables()
    conn = op.get_bind()

    if {_SETS, _OPTIONS, _BINDINGS} <= tables:
        for set_key in (_PARTY_SET_KEY, _REASON_SET_KEY):
            set_id = conn.execute(
                sa.text(f"SELECT id FROM {_SETS} WHERE set_key = :k AND tenant_id IS NULL"),
                {"k": set_key},
            ).scalar()
            if not set_id:
                continue
            # Bindings and options cascade from the set.
            conn.execute(sa.text(f"DELETE FROM {_SETS} WHERE id = :id"), {"id": set_id})

    for table in (_EVENT_LOG, _TRACKING):
        if table not in tables:
            continue
        for index in ("ix_sla_tracking_waiting_party", "ix_sla_event_log_waiting_party"):
            if index in _indexes(table):
                op.drop_index(index, table_name=table)
        existing = _constraints(table)
        for check in (_PARTY_CHECK, _REASON_CHECK):
            if check in existing:
                op.drop_constraint(check, table, type_="check")
        columns = _columns(table)
        for column in ("waiting_on_party", "waiting_on_reason", "waiting_since"):
            if column in columns:
                op.drop_column(table, column)

    if _OPTIONS in tables and "attributes" in _columns(_OPTIONS):
        op.drop_column(_OPTIONS, "attributes")
