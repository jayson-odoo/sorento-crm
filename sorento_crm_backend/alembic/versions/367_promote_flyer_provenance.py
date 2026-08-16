"""Promote every flyer-sourced provenance entry to an authored one (D2, AC-B.10).

**Why this exists.** In the same deploy, derivation stops reading `product_flyer_text`
as an input. A value that only ever came from a flyer would then be dropped by the very
next `derive_for_code` on that code - fired by the change listener on any description
edit, not only by the nightly job - and it would be gone with nothing recording that it
had ever been there. So the values are re-stamped as a person's first, and only then
does the flyer stop being an input. That ordering is the whole point of the runbook
(`documentation/plans/master-data/RUNBOOK-flyer-promote.md`); steps 2 and 3 ship
together and this is step 2.

**Blast radius, measured rather than estimated.** On the copy of production,
2026-08-13: **3,353 provenance entries, across 1,389 spec rows and 695 product codes**
(6.1% of the catalogue). Re-measured on the same database 2026-08-16 the entry count
read **3,351** - two entries moved by hand in the intervening days - with the row and
code counts unchanged. An operator seeing 3,351 has not found a defect; a figure that
is not within a handful of these has found a different database.

**What moves, and what must not.** `provenance` only. Every entry whose `source` is
`flyer` becomes

    {"source": "human", "confidence": <kept>, "evidence": "flyer: " || <original>,
     "migrated_from": "flyer"}

and every other entry is written back byte-identical. `values`, `rendered_text` and
`derived_hash` are NOT touched - a checksum over `values` before and after is what
proves it, and the runbook takes one either side. `status` moves from `derived` to
`authored` because the row now holds an authored entry; `needs_review` outranks
`authored` and is left alone.

`migrated_from` is not decoration. It is what lets the product page badge a value the
user never typed as "Set by hand" and still explain why (AC-B.15), and it is what the
downgrade below reads.

**Idempotent and mismatch-based**, not "run once". The WHERE clause selects rows that
still hold at least one `source = 'flyer'` entry, so a second run updates zero rows and
a crashed partial run is COMPLETED by the next one rather than skipped. The
already-promoted entries in such a row are rewritten to exactly what they already say.

**Ranking is neutral on day one** because PR 1 shipped the source-keyed boost branch:
`human_source_boost` is seeded at 1.5, equal to `flyer_source_boost`, so a promoted
entry scores what it scored before (C3). Runbook step 1 verifies that branch is present
before this runs; do not run it otherwise, or 695 codes are silently demoted to 1.0 on
exactly the queries they used to win.

Revision ID: 367_promote_flyer_provenance
Revises: 366_merge_flyer_promo_scm_heads
Create Date: 2026-08-16
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "367_promote_flyer_provenance"
down_revision = "366_merge_flyer_promo_scm_heads"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


# Entries still carrying the flyer as their source, and the rows holding them.
_COUNT_FLYER = sa.text(
    """
    SELECT count(*) AS entries,
           count(DISTINCT s.id) AS rows
      FROM product_specifications s
      CROSS JOIN LATERAL jsonb_each(s.provenance) AS e(key, value)
     WHERE e.value->>'source' = 'flyer'
    """
)

# Entries carrying the promotion marker. The mirror image of the count above.
_COUNT_MIGRATED = sa.text(
    """
    SELECT count(*) AS entries,
           count(DISTINCT s.id) AS rows
      FROM product_specifications s
      CROSS JOIN LATERAL jsonb_each(s.provenance) AS e(key, value)
     WHERE e.value->>'migrated_from' = 'flyer'
    """
)

_PROMOTE = sa.text(
    """
    WITH targets AS (
        SELECT s.id
          FROM product_specifications s
         -- `jsonb_each` errors on anything that is not an object, and the column is
         -- nullable with no CHECK behind it: one row holding `null`, `[]` or a bare
         -- string aborts the whole statement mid-migration rather than being skipped.
         WHERE jsonb_typeof(s.provenance) = 'object'
           AND EXISTS (
                 SELECT 1
                   FROM jsonb_each(s.provenance) AS e(key, value)
                  WHERE e.value->>'source' = 'flyer'
               )
    ),
    promoted AS (
        SELECT t.id,
               jsonb_object_agg(
                   e.key,
                   CASE
                     WHEN e.value->>'source' = 'flyer'
                     THEN jsonb_strip_nulls(
                            jsonb_build_object(
                              'source', 'human',
                              'confidence', e.value->'confidence',
                              'evidence', 'flyer: ' || coalesce(e.value->>'evidence', ''),
                              'migrated_from', 'flyer'
                            )
                          )
                     ELSE e.value
                   END
               ) AS provenance
          FROM targets t
          JOIN product_specifications s ON s.id = t.id
          CROSS JOIN LATERAL jsonb_each(s.provenance) AS e(key, value)
         GROUP BY t.id
    )
    UPDATE product_specifications s
       SET provenance = promoted.provenance,
           -- needs_review outranks authored and is a statement about open exceptions,
           -- not about who wrote the values, so it stays.
           status = CASE WHEN s.status = 'derived' THEN 'authored' ELSE s.status END
      FROM promoted
     WHERE s.id = promoted.id
    """
)

_DEMOTE = sa.text(
    """
    WITH targets AS (
        SELECT s.id
          FROM product_specifications s
         -- Same guard as the upgrade: a non-object `provenance` is skipped rather
         -- than aborting the statement (see `_PROMOTE`).
         WHERE jsonb_typeof(s.provenance) = 'object'
           AND EXISTS (
                 SELECT 1
                   FROM jsonb_each(s.provenance) AS e(key, value)
                  WHERE e.value->>'migrated_from' = 'flyer'
               )
    ),
    restored AS (
        SELECT t.id,
               jsonb_object_agg(
                   e.key,
                   CASE
                     WHEN e.value->>'migrated_from' = 'flyer'
                     -- `jsonb_strip_nulls` mirrors the upgrade: an entry that carried
                     -- no `confidence` was promoted WITHOUT the key, and building it
                     -- back unstripped would restore it as an explicit JSON null - a
                     -- shape neither the promote nor derivation ever writes.
                     THEN jsonb_strip_nulls(
                            jsonb_build_object(
                              'source', 'flyer',
                              'confidence', e.value->'confidence',
                              'evidence',
                              regexp_replace(coalesce(e.value->>'evidence', ''), '^flyer: ', '')
                            )
                          )
                     ELSE e.value
                   END
               ) AS provenance
          FROM targets t
          JOIN product_specifications s ON s.id = t.id
          CROSS JOIN LATERAL jsonb_each(s.provenance) AS e(key, value)
         GROUP BY t.id
    )
    UPDATE product_specifications s
       SET provenance = restored.provenance,
           status = CASE
                      WHEN s.status = 'authored'
                       AND NOT EXISTS (
                             SELECT 1
                               FROM jsonb_each(restored.provenance) AS r(key, value)
                              -- This list IS `product_spec_write.AUTHORED_SOURCES`,
                              -- frozen into SQL because a migration must keep saying
                              -- what it said the day it ran. It is deliberately NOT
                              -- imported: the hazard is the other way round - `flyer`
                              -- JOINS that set in the bulk-ingestion slice after PRs
                              -- 1-4 (see AC-F.7), and an import would then make this
                              -- downgrade read a demoted `source='flyer'` entry as
                              -- authored and leave every row on `authored` forever.
                              -- If the set changes for a reason OTHER than the flyer
                              -- joining it, change this list to match by hand.
                              WHERE r.value->>'source' IN ('human', 'supplier')
                           )
                      THEN 'derived'
                      ELSE s.status
                    END
      FROM restored
     WHERE s.id = restored.id
    """
)


def _counts(bind, statement) -> tuple[int, int]:
    row = bind.execute(statement).first()
    return (int(row.entries or 0), int(row.rows or 0)) if row is not None else (0, 0)


def upgrade() -> None:
    bind = op.get_bind()

    entries, rows = _counts(bind, _COUNT_FLYER)
    logger.info(
        "promote flyer provenance: %s entries on %s rows carry source='flyer' before the run",
        entries,
        rows,
    )

    bind.execute(_PROMOTE)

    remaining, _ = _counts(bind, _COUNT_FLYER)
    migrated_entries, migrated_rows = _counts(bind, _COUNT_MIGRATED)
    logger.info(
        "promote flyer provenance: %s entries on %s rows now carry migrated_from='flyer'; "
        "%s source='flyer' entries remain",
        migrated_entries,
        migrated_rows,
        remaining,
    )


def downgrade() -> None:
    """Put every promoted entry back the way it was, exactly.

    The one thing it cannot know is whether an entry was promoted by THIS run or by an
    earlier partial one: `migrated_from='flyer'` is the only marker either leaves. So a
    row that was already half-promoted before the upgrade comes back fully demoted,
    which is the state the promotion was completing anyway.

    The evidence prefix is stripped rather than assumed absent, so an entry that carried
    no evidence at all comes back with an empty string instead of no key. Nor can it
    restore a key the promote never carried forward: the upgrade rebuilds a flyer entry
    from `source`, `confidence` and `evidence` alone, so anything else somebody had put
    on one is dropped there and gone by the time this runs. Both are inert today - all
    3,351 flyer entries carry exactly `confidence`, `evidence` and `source`, and nothing
    reads evidence for anything but display - and both are stated rather than
    discovered.
    """
    bind = op.get_bind()

    entries, rows = _counts(bind, _COUNT_MIGRATED)
    logger.info(
        "demote flyer provenance: %s entries on %s rows carry migrated_from='flyer' "
        "before the run",
        entries,
        rows,
    )

    bind.execute(_DEMOTE)

    restored_entries, restored_rows = _counts(bind, _COUNT_FLYER)
    remaining, _ = _counts(bind, _COUNT_MIGRATED)
    logger.info(
        "demote flyer provenance: %s entries on %s rows are back to source='flyer'; "
        "%s migrated_from='flyer' entries remain",
        restored_entries,
        restored_rows,
        remaining,
    )
