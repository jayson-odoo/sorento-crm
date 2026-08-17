"""Brand-aware routing: the brand is a tag on the PERSON, not a suffix on the set code.

Company-aware routing (320) gave a team-set row a company. Brand is the SECOND,
orthogonal axis: Cabana and Mocha are brands INSIDE the Sorento company, so the
company column cannot carry them. The workaround in production is three copies of
one team set - ``marketing_promotion_sorento`` / ``_mocha`` / ``_cabana`` - which
means the admin maintains three ladders for one function, n8n has to know which
suffix exists, and a tier-2 escalation of a Mocha conversation has no defined home.

The brand lives where the market segment already does: on the team MEMBERSHIP. One
set, one team per tier, and each member carries the brands they serve. Untagged
member = serves every brand, and when nobody in the team carries the brand asked
for, the whole team round-robins - so routing never dead-ends.

What this adds:

* ``team_member_brands`` - the join table, mirroring ``team_member_market_segments``
  (membership FK ON DELETE CASCADE + a lower-case brand code, the pair unique).
  ``brand_code`` is not an FK: deleting a brand would untag its specialists and
  quietly turn them into serve-all.
* ``conversation_sla_tracking.brand_code``, stamped at creation and read back by
  every escalation. Same pattern as ``company_id`` from 320, for the same reason:
  a scheduler tick has no request context to re-derive it from.
* The three suffixed promotion sets are COLLAPSED into one ``marketing_promotion``
  set. Per tier, ONE team survives (the ``_sorento`` one, which handles today's
  unbranded traffic); every other suffixed row's team MEMBERS are moved into it
  tagged with that row's brand, and the row itself is deleted. Nobody's work
  changes hands: a Mocha conversation still reaches the people who handled Mocha,
  because the tag follows them.

Where there is no ``_sorento`` row at a tier, the survivor comes from the next brand
in ``BRAND_PRIORITY`` (mocha, then cabana) and a warning names which one - its own
people keep their brand tag, so the fallback for an untagged brand is whoever else
is untagged there, or the whole team.

What this deliberately does NOT do:

* touch ``agent_teams`` at all. No new column, and the 320-era partial unique keys
  stay exactly as they are - the brand is not a property of a routing row any more.
* touch any set outside the three promotion keys. ``marketing_product`` and every
  other set come out byte-identical.
* delete the emptied teams. An admin may still be using them for something else, and
  an empty team is harmless once no ``agent_teams`` row points at it.
* reverse the collapse, or the membership moves, on downgrade. Which brand a person
  came from is recoverable from ``team_member_brands``, but which TEAM they sat in
  is not, and the deleted suffixed rows are not reconstructible from the survivors.
  Downgrade therefore restores the SCHEMA only (drops the join table and the tracker
  column); the people stay where the upgrade put them.

Revision ID: 371_brand_member_routing
Revises: 367_promote_flyer_provenance
"""
import logging

from alembic import op
from sqlalchemy import text as sa_text

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "371_brand_member_routing"
down_revision = "367_promote_flyer_provenance"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

BASE_CODE = "marketing_promotion"
# The one-release compatibility map. The resolver reads the same pairs
# (``split_legacy_team_set_code`` in app/services/user_service.py) so an n8n
# workflow still sending a suffixed key keeps routing while it is updated.
LEGACY_CODES = {
    f"{BASE_CODE}_sorento": "sorento",
    f"{BASE_CODE}_mocha": "mocha",
    f"{BASE_CODE}_cabana": "cabana",
}
# Sorento first: it is the incumbent set, so its policy and its teams are what the
# collapsed set inherits, and its people stay untagged because they are the ones
# handling unbranded traffic today (captain decision D5).
BRAND_PRIORITY = ["sorento", "mocha", "cabana"]


def _create_team_member_brands() -> None:
    """The join table, in the shape ``team_member_market_segments`` already has."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS team_member_brands (
            team_member_id uuid NOT NULL
                REFERENCES team_members(id) ON DELETE CASCADE,
            brand_code text NOT NULL,
            created_at timestamp without time zone NOT NULL DEFAULT now(),
            PRIMARY KEY (team_member_id, brand_code)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_team_member_brands_team_member_id "
        "ON team_member_brands (team_member_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_team_member_brands_brand_code "
        "ON team_member_brands (brand_code)"
    )


def _tag(bind, member_id, brand: str) -> None:
    bind.execute(
        sa_text(
            "INSERT INTO team_member_brands (team_member_id, brand_code) "
            "VALUES (:m, :b) ON CONFLICT DO NOTHING"
        ),
        {"m": member_id, "b": brand},
    )


def _move_members(bind, from_team_id, to_team_id, brand: str) -> None:
    """Move a suffixed tier's people into the surviving team, tagged with its brand.

    Appended to the BACK of the round-robin queue (``sort_order`` continues past the
    highest one already there), because joining a rotation should not hand the newcomer
    the next conversation. ``include_in_round_robin`` travels with them: somebody
    excluded in the Mocha team is excluded here too.
    """
    if str(from_team_id) == str(to_team_id):
        return

    base = bind.execute(
        sa_text(
            "SELECT coalesce(max(sort_order), 0) FROM team_members WHERE team_id = :t"
        ),
        {"t": to_team_id},
    ).scalar() or 0

    rows = bind.execute(
        sa_text(
            "SELECT id, user_id FROM team_members WHERE team_id = :t "
            "ORDER BY sort_order NULLS LAST, user_id"
        ),
        {"t": from_team_id},
    ).mappings().all()

    offset = 0
    for row in rows:
        already = bind.execute(
            sa_text(
                "SELECT id FROM team_members WHERE team_id = :t AND user_id = :u"
            ),
            {"t": to_team_id, "u": row["user_id"]},
        ).scalar()
        if already:
            # Tagging them would NARROW somebody who currently serves every brand in
            # the surviving team - a routing change nobody asked for. Left exactly as
            # it is, and named here so the admin can decide.
            logger.warning(
                "brand-member routing: user %s is already a member of team %s, so "
                "their %s membership was left in place and NOT tagged %r. Tag them by "
                "hand if they should only serve that brand.",
                row["user_id"],
                to_team_id,
                brand,
                brand,
            )
            continue
        offset += 1
        bind.execute(
            sa_text(
                "UPDATE team_members SET team_id = :to, sort_order = :s WHERE id = :i"
            ),
            {"to": to_team_id, "s": base + offset, "i": row["id"]},
        )
        _tag(bind, row["id"], brand)


def _tag_existing_members(bind, team_id, brand: str) -> None:
    """Tag the surviving team's OWN people, when it is not the all-brands default.

    Only reached when no ``_sorento`` row exists at that tier: the survivor is then a
    brand team that got promoted, and its people handle that brand specifically. The
    ``_sorento`` team is never tagged - it is the fallback.
    """
    rows = bind.execute(
        sa_text("SELECT id FROM team_members WHERE team_id = :t"), {"t": team_id}
    ).all()
    for (member_id,) in rows:
        _tag(bind, member_id, brand)


def _collapse_promotion_sets(bind) -> None:
    """Turn the three suffixed promotion sets into one set, per (agent, company).

    Re-runnable: after the first pass no suffixed row is left, so the group query
    returns nothing and this is a no-op.
    """
    groups = bind.execute(
        sa_text(
            """
            SELECT DISTINCT agent_id, company_id FROM agent_teams
            WHERE code = ANY(:codes)
            """
        ),
        {"codes": list(LEGACY_CODES)},
    ).all()

    for agent_id, company_id in groups:
        rows = bind.execute(
            sa_text(
                """
                SELECT id, code, tier, team_id, policy_id
                FROM agent_teams
                WHERE agent_id = :a AND company_id = :c AND code = ANY(:codes)
                """
            ),
            {
                "a": agent_id,
                "c": company_id,
                "codes": list(LEGACY_CODES) + [BASE_CODE],
            },
        ).mappings().all()

        suffixed = [r for r in rows if r["code"] in LEGACY_CODES]
        base_rows = [r for r in rows if r["code"] == BASE_CODE]

        # One policy per code is an invariant (resolve_policy_id_for 409s otherwise),
        # so the collapsed set gets ONE: the _sorento set's, else the first non-null
        # among the other suffixes, else whatever an existing base row already had.
        policy_id = _pick_policy(suffixed, base_rows)

        for tier in {r["tier"] for r in suffixed}:
            _collapse_tier(
                bind,
                agent_id,
                company_id,
                tier,
                [r for r in suffixed if r["tier"] == tier],
                [r for r in base_rows if r["tier"] == tier],
            )

        if policy_id is not None:
            bind.execute(
                sa_text(
                    "UPDATE agent_teams SET policy_id = :p "
                    "WHERE agent_id = :a AND company_id = :c AND code = :code "
                    "AND policy_id IS DISTINCT FROM :p"
                ),
                {"p": policy_id, "a": agent_id, "c": company_id, "code": BASE_CODE},
            )


def _pick_policy(suffixed, base_rows):
    for brand in BRAND_PRIORITY:
        for row in suffixed:
            if LEGACY_CODES[row["code"]] == brand and row["policy_id"] is not None:
                return row["policy_id"]
    for row in base_rows:
        if row["policy_id"] is not None:
            return row["policy_id"]
    return None


def _first_by_brand_priority(rows):
    """The row whose suffix comes first in ``BRAND_PRIORITY``, or None for no rows.

    Deterministic on purpose: which row survives must not depend on the order
    Postgres happened to return the group in.
    """
    for brand in BRAND_PRIORITY:
        for row in rows:
            if LEGACY_CODES[row["code"]] == brand:
                return row
    return None


def _collapse_tier(bind, agent_id, company_id, tier, tier_suffixed, tier_base) -> None:
    """One tier: keep ONE team, fold everybody else's people into it tagged.

    The same routine for tier 1 and for tiers 2/3. Today all three suffixed sets share
    a tier-2 and a tier-3 team, so those tiers just lose their duplicate rows; where
    they differ, the odd team's people move rather than their ladder disappearing.
    """
    if tier_base:
        survivor_team_id = tier_base[0]["team_id"]
        remaining = list(tier_suffixed)
    else:
        winner = _first_by_brand_priority(tier_suffixed)
        if winner is None:
            return
        winner_brand = LEGACY_CODES[winner["code"]]
        bind.execute(
            sa_text("UPDATE agent_teams SET code = :code WHERE id = :i"),
            {"code": BASE_CODE, "i": winner["id"]},
        )
        survivor_team_id = winner["team_id"]
        remaining = [r for r in tier_suffixed if r["id"] != winner["id"]]
        if winner_brand != "sorento":
            # The set has no _sorento row, so the promoted team is a BRAND team: its
            # people handle that brand, not the unbranded traffic. Tagging them keeps
            # that true; leaving them untagged would silently widen their queue.
            logger.warning(
                "brand-member routing: agent %s company %s has no %s_sorento tier %s "
                "row, so the %s team survives as the tier's team and its members were "
                "tagged %r. Add an untagged member if somebody should take a brand "
                "nobody is tagged for.",
                agent_id,
                company_id,
                BASE_CODE,
                tier,
                winner_brand,
                winner_brand,
            )
            _tag_existing_members(bind, survivor_team_id, winner_brand)

    for row in remaining:
        _move_members(bind, row["team_id"], survivor_team_id, LEGACY_CODES[row["code"]])
        bind.execute(sa_text("DELETE FROM agent_teams WHERE id = :i"), {"i": row["id"]})


def _rewrite_trackers(bind) -> None:
    """An OPEN tracker keeps escalating after the upgrade.

    Resolved rows have team_set_code cleared already, so this only ever touches live
    ones - but it is written unconditionally because a row that is somehow still
    carrying a suffixed code must not be left pointing at a code that no longer exists.
    """
    for legacy_code, brand in LEGACY_CODES.items():
        bind.execute(
            sa_text(
                "UPDATE conversation_sla_tracking "
                "SET team_set_code = :base, brand_code = :b "
                "WHERE team_set_code = :legacy"
            ),
            {"base": BASE_CODE, "b": brand, "legacy": legacy_code},
        )


def _warn_unknown_brand_codes(bind) -> None:
    """Every tag written above must name a real brand, or it routes to nothing.

    Not a constraint and not a fix: ``brands`` is company-scoped with per-company ids
    while the routing handle is the CODE, and a brand created later is perfectly
    legitimate. But a code with no brand at all is a typo the admin cannot see from
    the roster, so it is named here while the data is in front of us.
    """
    rows = bind.execute(
        sa_text("SELECT DISTINCT brand_code FROM team_member_brands")
    ).all()
    for (brand_code,) in rows:
        found = bind.execute(
            sa_text("SELECT count(*) FROM brands WHERE lower(brand_code) = lower(:b)"),
            {"b": brand_code},
        ).scalar()
        if not found:
            logger.warning(
                "brand-member routing: team members are tagged with brand %r, which "
                "exists nowhere in the brands table. Escalations asking for it will "
                "fall back to the untagged members until that brand is created.",
                brand_code,
            )


def upgrade():
    bind = op.get_bind()

    op.execute(
        "ALTER TABLE conversation_sla_tracking ADD COLUMN IF NOT EXISTS brand_code text"
    )
    _create_team_member_brands()

    _collapse_promotion_sets(bind)
    _rewrite_trackers(bind)
    _warn_unknown_brand_codes(bind)


def downgrade():
    # Schema only. The collapse and the membership moves are NOT reversed: which team
    # each person sat in before is not recorded anywhere, and the deleted suffixed
    # rows cannot be rebuilt from the survivors. Going back means re-creating the
    # three sets by hand first.
    op.execute("DROP TABLE IF EXISTS team_member_brands")
    op.execute(
        "ALTER TABLE conversation_sla_tracking DROP COLUMN IF EXISTS brand_code"
    )
