"""After-sales S4: a customer stops being a second-class recipient.

Four tables, one idea: the ``notifications`` row becomes the single record of "we told
somebody something", whether that somebody is staff or a customer. Until now a
notification could only address a ``users.id`` - the column was NOT NULL - so "tell the
contact" had to be implemented somewhere else entirely, and it was
(``workflow_submission_notify`` sent and wrote an outbox row with no notification behind
it). One spine means the dedupe, the delivery fan-out, the outbox and the worker all
learn a second kind of recipient at once, and every one of those is a place where a
contact silently becomes a no-op instead of an error.

**What the tests forced out into the open.**

1. ``respond_contact_id`` is TEXT, not uuid. The plan's own DDL says
   ``respond_contact_id uuid REFERENCES respond_contacts(id)`` and
   ``respond_contacts.id`` is TEXT: Postgres refuses a uuid foreign key onto a text
   primary key, so that migration fails on the way to production while a uuid column on
   the model passes every model-level test. This is the FOURTH column in this build to
   hit the same trap (AC-A2, AC-F2b-1, S1's two, now this).

2. ``uq_notification_user_dedup_event`` is DROPPED, not amended. Postgres treats NULLs
   as distinct in a unique constraint, so the moment ``user_id`` became nullable that
   constraint stopped deduplicating every contact notification - no error, no signal,
   and the symptom is a customer receiving the same WhatsApp message twice. Two PARTIAL
   unique indexes replace it, one per recipient kind, because a single whole-table index
   cannot dedupe a column that is NULL for half the rows. The staff half is a like-for-
   like replacement of the dropped constraint and must keep working.

3. ``notifications_recipient_present`` is an XOR, not an OR. Neither recipient set is a
   row no delivery loop can address; BOTH set is a row that fans out to two different
   people, and the worker and the outbox renderer would each pick a different one.

4. ``activity_events.actor_id`` is widened from uuid to varchar. It holds ``users.id``,
   which is VARCHAR - the same model-versus-column type drift that broke
   ``user_sessions.id`` on prod. Every user id in the live database happens to be
   uuid-shaped today, but only because ``User.id`` defaults to uuid4; nothing enforces
   it, and S4 is the first writer here that does not come from a staff session.

``access_agents.assignment_fallback_user_id`` is the AC-M33 backstop, at agent level
because ``resolve_team_with_tier_fallback(agent, ...)`` is already where team resolution
happens. Its FK is DEFERRABLE INITIALLY DEFERRED on purpose: the FK is what stops the
backstop naming a user who never existed, but a configured backstop DOES decay, and
``_start_for_config`` treats an unresolvable one as "fall through to the ORIGINAL raise"
rather than crashing one line later. Checking at commit is what lets that state exist
long enough to be handled.

``conversation_sla_tracking.assignment_unresolved`` is NOT NULL with a server default of
false, which is what keeps every existing tracker readable: a three-valued "maybe
unresolved" has no meaning, and nullable would put a third state on a two-state switch
that every read site would then interpret differently.

**What stays broken after this migration.** The partial dedupe indexes still do nothing
when ``dedup_key`` or ``event_type`` is NULL, exactly as the dropped constraint did -
callers that pass neither are not deduplicated at all, which is unchanged behaviour and
not a regression, but it is not a guarantee either. Contact notifications carry no read
state a contact can set: ``read_at`` is written by the staff bell, and the portal has no
equivalent yet, so an ``in_app`` row for a contact is created and never marked read.
And AC-M35's "open case" is defined by a set copied into ``call_activity_service``
rather than read from the status graph, because the graph marks only ``closed`` and
``voided`` terminal - so a complaint ``rejected`` in 2024 still counts as open and can
have today's call auto-attached to it. Fixing the graph changes complaint editability
for live records and was explicitly held out of this slice.

Every idempotency guard here is load-bearing: the shared dev database is stamped on
another worktree's chain, so this DDL gets applied by hand there and a plain
``add_column`` would abort the whole upgrade.

Revision ID: 320_notification_spine_calls
Revises: 319_attachment_validator
Create Date: 2026-08-03

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "320_notification_spine_calls"
down_revision = "319_attachment_validator"
branch_labels = None
depends_on = None

_NOTIFICATIONS = "notifications"
_AGENTS = "access_agents"
_TRACKING = "conversation_sla_tracking"
_ACTIVITY = "activity_events"

_OLD_UNIQUE = "uq_notification_user_dedup_event"
_USER_DEDUP = "uq_notifications_user_dedup"
_CONTACT_DEDUP = "uq_notifications_contact_dedup"
_RECIPIENT_CHECK = "notifications_recipient_present"
_CONTACT_FK = "fk_notifications_respond_contact"
_FALLBACK_FK = "fk_access_agents_assignment_fallback_user"


def _inspector():
    return sa.inspect(op.get_bind())


def _tables() -> set:
    return set(_inspector().get_table_names())


def _columns(table: str) -> set:
    return {c["name"] for c in _inspector().get_columns(table)}


def _indexes(table: str) -> set:
    return {ix["name"] for ix in _inspector().get_indexes(table)}


def _constraints(table: str) -> set:
    insp = _inspector()
    names = {c["name"] for c in insp.get_check_constraints(table)}
    names |= {c["name"] for c in insp.get_unique_constraints(table)}
    names |= {c.get("name") for c in insp.get_foreign_keys(table)}
    return {n for n in names if n}


def upgrade() -> None:
    tables = _tables()

    # ---------------------------------------------------------------- notifications
    if _NOTIFICATIONS in tables:
        columns = _columns(_NOTIFICATIONS)
        op.alter_column(_NOTIFICATIONS, "user_id", existing_type=sa.String(), nullable=True)

        if "respond_contact_id" not in columns:
            op.add_column(
                _NOTIFICATIONS,
                sa.Column("respond_contact_id", sa.Text(), nullable=True),
            )
        existing = _constraints(_NOTIFICATIONS)
        if _CONTACT_FK not in existing and "respond_contacts" in tables:
            op.create_foreign_key(
                _CONTACT_FK,
                _NOTIFICATIONS,
                "respond_contacts",
                ["respond_contact_id"],
                ["id"],
                ondelete="CASCADE",
            )
        if "ix_notifications_respond_contact_id" not in _indexes(_NOTIFICATIONS):
            op.create_index(
                "ix_notifications_respond_contact_id",
                _NOTIFICATIONS,
                ["respond_contact_id"],
            )

        # DROP before creating the replacements: leaving it in place means contact
        # dedupe silently does nothing, and the failure is a duplicate customer
        # message rather than an error anybody sees.
        if _OLD_UNIQUE in _constraints(_NOTIFICATIONS):
            op.drop_constraint(_OLD_UNIQUE, _NOTIFICATIONS, type_="unique")
        elif _OLD_UNIQUE in _indexes(_NOTIFICATIONS):
            op.drop_index(_OLD_UNIQUE, table_name=_NOTIFICATIONS)

        indexes = _indexes(_NOTIFICATIONS)
        if _USER_DEDUP not in indexes:
            op.create_index(
                _USER_DEDUP,
                _NOTIFICATIONS,
                ["user_id", "source_entity_type", "dedup_key", "event_type"],
                unique=True,
                postgresql_where=sa.text("user_id IS NOT NULL"),
            )
        if _CONTACT_DEDUP not in indexes:
            op.create_index(
                _CONTACT_DEDUP,
                _NOTIFICATIONS,
                [
                    "respond_contact_id",
                    "source_entity_type",
                    "dedup_key",
                    "event_type",
                ],
                unique=True,
                postgresql_where=sa.text("respond_contact_id IS NOT NULL"),
            )
        if _RECIPIENT_CHECK not in _constraints(_NOTIFICATIONS):
            op.create_check_constraint(
                _RECIPIENT_CHECK,
                _NOTIFICATIONS,
                "(user_id IS NOT NULL) <> (respond_contact_id IS NOT NULL)",
            )

    # ------------------------------------------------- the assignment backstop (M33)
    if _AGENTS in tables and "assignment_fallback_user_id" not in _columns(_AGENTS):
        op.add_column(
            _AGENTS,
            sa.Column("assignment_fallback_user_id", sa.String(), nullable=True),
        )
    if (
        _AGENTS in tables
        and "users" in tables
        and _FALLBACK_FK not in _constraints(_AGENTS)
    ):
        op.create_foreign_key(
            _FALLBACK_FK,
            _AGENTS,
            "users",
            ["assignment_fallback_user_id"],
            ["id"],
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
        )

    if _TRACKING in tables and "assignment_unresolved" not in _columns(_TRACKING):
        op.add_column(
            _TRACKING,
            sa.Column(
                "assignment_unresolved",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    # ------------------------------------------------------------- calls (AC-M34)
    if _ACTIVITY in tables:
        actor = next(
            (c for c in _inspector().get_columns(_ACTIVITY) if c["name"] == "actor_id"),
            None,
        )
        if actor is not None and isinstance(actor["type"], sa.dialects.postgresql.UUID):
            op.alter_column(
                _ACTIVITY,
                "actor_id",
                existing_type=sa.dialects.postgresql.UUID(),
                type_=sa.String(length=100),
                existing_nullable=True,
                postgresql_using="actor_id::varchar(100)",
            )


def downgrade() -> None:
    tables = _tables()

    if _ACTIVITY in tables:
        actor = next(
            (c for c in _inspector().get_columns(_ACTIVITY) if c["name"] == "actor_id"),
            None,
        )
        if actor is not None and not isinstance(
            actor["type"], sa.dialects.postgresql.UUID
        ):
            # Any non-uuid actor written while the column was wide would abort this
            # cast, which is the correct outcome: the downgrade cannot keep the data.
            op.alter_column(
                _ACTIVITY,
                "actor_id",
                existing_type=sa.String(length=100),
                type_=sa.dialects.postgresql.UUID(),
                existing_nullable=True,
                postgresql_using="actor_id::uuid",
            )

    if _TRACKING in tables and "assignment_unresolved" in _columns(_TRACKING):
        op.drop_column(_TRACKING, "assignment_unresolved")

    if _AGENTS in tables:
        if _FALLBACK_FK in _constraints(_AGENTS):
            op.drop_constraint(_FALLBACK_FK, _AGENTS, type_="foreignkey")
        if "assignment_fallback_user_id" in _columns(_AGENTS):
            op.drop_column(_AGENTS, "assignment_fallback_user_id")

    if _NOTIFICATIONS in tables:
        if _RECIPIENT_CHECK in _constraints(_NOTIFICATIONS):
            op.drop_constraint(_RECIPIENT_CHECK, _NOTIFICATIONS, type_="check")
        indexes = _indexes(_NOTIFICATIONS)
        for name in (_USER_DEDUP, _CONTACT_DEDUP, "ix_notifications_respond_contact_id"):
            if name in indexes:
                op.drop_index(name, table_name=_NOTIFICATIONS)
        if _CONTACT_FK in _constraints(_NOTIFICATIONS):
            op.drop_constraint(_CONTACT_FK, _NOTIFICATIONS, type_="foreignkey")
        if "respond_contact_id" in _columns(_NOTIFICATIONS):
            # Contact notifications cannot be represented by the old shape at all, so
            # they go with the column rather than becoming rows addressed to nobody.
            op.execute("DELETE FROM notifications WHERE respond_contact_id IS NOT NULL")
            op.drop_column(_NOTIFICATIONS, "respond_contact_id")
        if _OLD_UNIQUE not in _constraints(_NOTIFICATIONS):
            op.create_unique_constraint(
                _OLD_UNIQUE,
                _NOTIFICATIONS,
                ["user_id", "source_entity_type", "dedup_key", "event_type"],
            )
        op.alter_column(
            _NOTIFICATIONS, "user_id", existing_type=sa.String(), nullable=False
        )
