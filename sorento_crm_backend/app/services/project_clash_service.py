"""Project registration clash matcher (ADR-0004).

Decides whether a salesperson may claim a development. Identity is
**developer + normalised title**, scoped to one company.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import Text, cast, func
from sqlalchemy.orm import Session

from app.models.projects import BLOCKING_OUTCOMES, Project, ProjectParty

# Surfacing and blocking are two separate bars, because the two mistakes are not
# equally bad. A missed duplicate is silent and produces the two-people-on-one-tender
# failure this module exists to prevent, so surfacing is generous. A false block is
# loud and, fired often enough, trains users to dismiss the warning entirely, so
# blocking is strict. Between the bars a candidate is shown as context: "Ali is
# working The Jerai Hotel, is yours the same one?"
#
# Both calibrated over all 63 distinct project titles in the live data (the corpus
# that gets migrated), scored with _score_expression:
#
#   1.000  "KSL Setia Alam"              inside "KSL Setia Alam Project  (733 units
#                                        service apartment)"          -> same
#   0.893  "Helicopter Centre in Subang" vs "Subang Helicopter Centre" -> same
#   0.864  "Menara Star Toilet"          inside "Menara Star HQ Toilet Renovation"
#   0.762  "Setia Alam Ph 3B"            vs "Setia Alam Phase 3B"      -> same
#   ---- 0.70 block bar ----
#   0.667  "Kami Residence"              vs "The Wyn Residence"        -> different
#   0.600  "IKI Hotel"                   vs "The Jerai Hotel"          -> different
#   0.556  "Taiga Residence"             vs "The Wyn Residence"        -> different
#   ---- 0.55 surface bar ----
#   0.261  "Tropicana Aman Phase 2"      vs "Setia Alam Phase 3B"      -> different
#
# The false positives below the block bar are all short titles sharing a generic noun
# (hotel, residence, project), which minimal normalisation cannot separate and which
# the pipeline is full of.
#
# Configurable (AC-C5) rather than constants: the right values depend on how the team
# names things, and only live use will tell.
DEFAULT_SURFACE_THRESHOLD = 0.55
DEFAULT_BLOCK_THRESHOLD = 0.70

# ``pg_trgm`` is installed into ``public`` (verified: ``pg_extension`` join
# ``pg_namespace``), and ``similarity()`` is schema-qualified rather than resolved
# through ``search_path``.
#
# ``entity_resolver.py`` calls it unqualified, which works in production because the
# search path ends in ``public``. It does NOT work under ``tests/_pg_fixture.py``,
# which pins ``search_path`` to the scratch schemas alone -- deliberately, because a
# path that falls through to ``public`` would let raw SQL in tests read and write the
# REAL tables on this prod-data copy. Qualifying here is the fix that does not
# weaken that guard.
_TRGM_SCHEMA = "public"


@dataclass(frozen=True)
class ClashCandidate:
    """One existing project that resembles the one being registered.

    ``blocks`` and ``similarity`` are separate on purpose. A lost project from
    three years ago can be a perfect title match (similarity 1.0) and still not
    block, because re-tendering it is legitimate. The UI shows every candidate as
    context; only a blocking one stops the save.
    """

    project_id: str
    project_code: str
    title: str
    outcome: str
    owner_user_id: Optional[str]
    similarity: float
    blocks: bool
    developer_party_id: Optional[str] = None
    developer_name: Optional[str] = None


def normalise_project_title(raw: str) -> str:
    """The comparison key for a project title.

    Deliberately MINIMAL: casefold and collapse whitespace, nothing else. No
    abbreviation dictionary (always incomplete) and no digit stripping, because
    stripping digits would make "Phase 3A" and "Phase 3B" the same key and falsely
    block a legitimately separate phase. Remaining drift ("Ph" vs "Phase", "Apt" vs
    "Apartment") is absorbed by trigram similarity instead.
    """
    return " ".join((raw or "").split()).casefold()


_DESIGNATOR = re.compile(r"[a-z]*\d[a-z\d]*")


def phase_designators(normalised_title: str) -> frozenset:
    """The digit-bearing tokens of a title: its phase, block and tower markers.

    "setia alam phase 3b" -> {"3b"}. "tower a2 block 5" -> {"a2", "5"}.

    These are what distinguish sibling developments under one developer, and they
    are the reason ``normalise_project_title`` does not strip digits.
    """
    return frozenset(_DESIGNATOR.findall(normalised_title))


def are_sibling_developments(left: str, right: str) -> bool:
    """Whether two titles name separate phases, blocks or towers of one development.

    Siblings when neither title's designator set contains the other's. "Phase 3A"
    ({"3a"}) against "Phase 3B" ({"3b"}) qualifies: two real developments, each
    separately registrable. "KSL Setia Alam" ({}) against "KSL Setia Alam Project
    (733 units service apartment)" ({"733"}) does not: the empty set is contained by
    every set, so one title merely omits detail the other spells out, and they are
    the same development.

    Containment rather than equality has one known cost. "KSL 733 units" and "KSL 733
    units Phase 3B" ({"733"} vs {"733", "3b"}) read as the same development and the
    second is blocked. Chosen deliberately: a false block is visible and has a
    recourse path (request to join, or dispute to a manager), whereas a false pass is
    silent and produces the two-people-on-one-tender failure the module exists to
    prevent.
    """
    a = phase_designators(left)
    b = phase_designators(right)
    return not (a <= b or b <= a)


def resolve_thresholds(db: Session) -> tuple:
    """``(surface, block)`` from ``system_settings``, falling back to the defaults.

    ``system_settings`` is a singleton, but the read still needs ORDER BY-free care:
    an unseeded database (and every blank test schema) has no row at all, and a
    missing settings row must not stop registrations. The fallback IS the shipped
    calibration, so "no row" and "freshly installed" behave identically.
    """
    from app.models.user import SystemSetting

    row = db.query(SystemSetting).first()
    if row is None:
        return DEFAULT_SURFACE_THRESHOLD, DEFAULT_BLOCK_THRESHOLD

    surface = getattr(row, "project_clash_surface_threshold", None)
    block = getattr(row, "project_clash_block_threshold", None)
    return (
        DEFAULT_SURFACE_THRESHOLD if surface is None else float(surface),
        DEFAULT_BLOCK_THRESHOLD if block is None else float(block),
    )


def _score_expression(key: str):
    """How alike the candidate title and ``key`` are, as a SQL expression.

    The strongest of three trigram measures:

    - ``similarity`` -- symmetric, good at spelling drift ("Ph" vs "Phase").
    - ``strict_word_similarity(key, stored)`` -- asymmetric, asks how well the typed
      title is covered by the stored one. This is what catches a short title typed
      against a verbose incumbent, where plain similarity collapses to 0.31 purely
      because of the length difference.
    - the same, reversed -- because whoever registers first decides which of the two
      titles is the stored one, and the answer must not depend on typing order.

    ``GREATEST`` defeats the ``gin_trgm_ops`` index, so this is a sequential scan.
    Acceptable: it is already filtered to one company and one developer, which is
    tens of rows, and correctness here outranks a scan the planner would likely
    choose anyway at that size.

    ``cast`` so Postgres sees ``text`` rather than ``unknown`` and can resolve the
    function overload.
    """
    trgm = getattr(func, _TRGM_SCHEMA)
    typed = cast(key, Text)
    stored = Project.normalised_title

    return func.greatest(
        trgm.similarity(stored, typed),
        trgm.strict_word_similarity(typed, stored),
        trgm.strict_word_similarity(stored, typed),
    )


def find_clashes(
    db: Session,
    *,
    company_id: str,
    developer_party_id: Optional[str],
    title: str,
    surface_threshold: Optional[float] = None,
    block_threshold: Optional[float] = None,
    include_other_developers: bool = False,
) -> List[ClashCandidate]:
    """Existing projects that may be the same development as ``title``.

    Scoped to one company and one developer: two different developers can each run
    a "Phase 2" and neither should hear about the other.

    ``include_other_developers`` widens the search to every developer, for the
    live preview. Those extra rows are context ONLY -- a title match under a
    different developer is not the same development, so it can never block. The
    widened search exists because the title is typed before the developer is chosen,
    and staying silent until then means the most common path gets no warning at all.

    Returns every candidate above the surfacing bar, most similar first, each already
    carrying its own ``blocks`` verdict. The caller never re-derives that decision.
    """
    key = normalise_project_title(title)
    configured_surface, configured_block = resolve_thresholds(db)
    surface = configured_surface if surface_threshold is None else surface_threshold
    block = configured_block if block_threshold is None else block_threshold

    score = _score_expression(key)

    query = db.query(Project, score.label("score")).filter(
        Project.company_id == company_id, score >= surface
    )
    if not include_other_developers:
        query = query.filter(Project.developer_party_id == developer_party_id)
    rows = query.order_by(score.desc()).all()

    developer_names = {}
    if include_other_developers:
        party_ids = {row.Project.developer_party_id for row in rows}
        party_ids.discard(None)
        if party_ids:
            developer_names = {
                party.id: party.name
                for party in db.query(ProjectParty)
                .filter(ProjectParty.id.in_(party_ids))
                .all()
            }

    return [
        ClashCandidate(
            project_id=row.Project.id,
            project_code=row.Project.project_code,
            title=row.Project.title,
            outcome=row.Project.outcome,
            owner_user_id=row.Project.owner_user_id,
            similarity=round(float(row.score), 4),
            # Three independent conditions, all required to stop a registration:
            # similar enough to be the same development, still being pursued, and
            # not a sibling phase. Everything else is returned as context.
            developer_party_id=row.Project.developer_party_id,
            developer_name=developer_names.get(row.Project.developer_party_id),
            blocks=(
                # A different developer's project is never the same development,
                # however alike the titles read.
                row.Project.developer_party_id == developer_party_id
                and float(row.score) >= block
                and row.Project.outcome in BLOCKING_OUTCOMES
                and not are_sibling_developments(row.Project.normalised_title, key)
            ),
        )
        for row in rows
    ]
