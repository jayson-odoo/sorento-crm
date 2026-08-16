"""Rejoin the three heads main grew while three PRs were in flight (no schema change).

Nothing is created, altered or dropped here. A merge revision exists so that
``alembic upgrade head`` has ONE target again, and that is the whole of it.

**How main ended up with three heads.** All three legs branch off
``358_scm_po_spo_history_aliases`` and merged within a few hours of each other:

* ``359_scm_plan_feedback_r2`` -> ``359_flyer_read_background_job`` (PR #184,
  the flyer read moving to a background job)
* ``359_um_contacts_reference_perms`` + ``359_scm_plan_feedback_r2`` ->
  ``360_merge_um_gates_scm_r2``
* ``361_promotion_types`` -> ``362_promotion_type_perms``

None of them conflicted as TEXT, so every branch rebased cleanly and every PR
was green on its own. The clash is in the revision graph rather than in any
file, which is why it only appeared once the second and third legs were both on
main: the CI bootstrap calls ``alembic stamp head``, that resolves to more than
one revision, and every job that needs a database dies before it starts
(``MultipleHeads: 359_flyer_read_background_job, 362_promotion_type_perms``,
run 31927575178).

The lesson is cheap to state and easy to miss: a single head is a property of
the BRANCH POINT, not of your branch. Re-check ``alembic heads`` against the
latest default branch just before merging, not only after a rebase.
"""

# revision identifiers, used by Alembic.
revision = "363_merge_flyer_promo_um"
down_revision = (
    "359_flyer_read_background_job",
    "360_merge_um_gates_scm_r2",
    "362_promotion_type_perms",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: this revision exists only to rejoin the graph."""


def downgrade() -> None:
    """No-op: splitting the heads back apart is what created the problem."""
