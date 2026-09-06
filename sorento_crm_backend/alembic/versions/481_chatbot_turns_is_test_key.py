"""`chatbot.turns` uniqueness gains `is_test`: a test turn and a live turn are two turns.

H57. D15's dedup question is "has this respond message already been turned into a turn",
and migration 474 answered it with `(contact_respond_id, message_id, attempt)`. That key
predates the dry-run audit and folds two different worlds into one row: a test turn run
from the Prompts screen against a REAL contact took the pair, so the customer's own live
delivery of that `messageId` came back `duplicate: true` carrying the test row's canned
reply - and a duplicate tells the caller to send nothing at all, so the customer was
answered with silence.

The engine's SELECT now narrows to the envelope's own `is_test` (`engine._existing_turn`).
This migration is what makes that legal: without `is_test` in the key the narrowed SELECT
would decide to insert a live row and the index would refuse it, turning a real customer's
message into a 500 instead of an answer.

`is_test` is NOT NULL with a `false` default (migration 472), so no row is excluded from
the key by Postgres's NULL-distinct rule and no backfill is needed - every existing row
already carries the value the new key reads. The old key is a strict subset of the new
one, so nothing that was unique stops being unique and the rebuild cannot fail on existing
data.

Revision ID: 481_chatbot_turns_is_test
Revises: 474_spo_allocations_source_ref
"""
from alembic import op

revision = "481_chatbot_turns_is_test"
down_revision = "474_spo_allocations_source_ref"
branch_labels = None
depends_on = None

_UQ = "uq_chatbot_turns_contact_message_attempt"


def upgrade():
    # Same NAME, wider key. Renaming would mean editing every reference to it (the model,
    # migration 474, the tests that name it), and the constraint answers the same question
    # it always did - "which rows are the same turn" - with one more column in the answer.
    op.drop_constraint(_UQ, "turns", schema="chatbot", type_="unique")
    op.create_unique_constraint(
        _UQ,
        "turns",
        ["contact_respond_id", "message_id", "attempt", "is_test"],
        schema="chatbot",
    )


def downgrade():
    # Narrowing CAN fail on real data, and that is correct: after this migration a contact
    # can hold a test row and a live row for one (message, attempt), which is exactly the
    # pair the old key forbade. Deleting one of them to make the constraint fit would throw
    # away a turn record, so the downgrade refuses instead and says which rows to resolve.
    op.execute(
        "DO $$ DECLARE clashes int; BEGIN "
        "  SELECT count(*) INTO clashes FROM ("
        "    SELECT 1 FROM chatbot.turns"
        "    GROUP BY contact_respond_id, message_id, attempt HAVING count(*) > 1"
        "  ) c; "
        "  IF clashes > 0 THEN "
        "    RAISE EXCEPTION 'cannot narrow uq_chatbot_turns_contact_message_attempt: at "
        "least one (contact, message, attempt) group holds both a test turn and a live "
        "turn. Delete the test rows you do not need, then downgrade again.'; "
        "  END IF; "
        "END $$;"
    )
    op.drop_constraint(_UQ, "turns", schema="chatbot", type_="unique")
    op.create_unique_constraint(
        _UQ,
        "turns",
        ["contact_respond_id", "message_id", "attempt"],
        schema="chatbot",
    )
