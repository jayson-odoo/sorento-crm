"""S2 golden set — project registration clash matcher (ADR-0004, AC-C5/C6).

This is the module that decides whether a salesperson may claim a development, so a
wrong answer here either lets two people work the same tender (the problem the module
exists to solve) or falsely blocks a legitimate separate phase.

Normalisation is deliberately MINIMAL: casefold plus whitespace collapse, no
abbreviation dictionary and no digit stripping. Stripping digits would make
"Phase 3A" and "Phase 3B" identical and falsely block a real second phase. The cost
of minimal normalisation is that filler words ("project", "units") inflate similarity
between unrelated titles, which makes the similarity threshold the load-bearing dial;
it is a configurable setting rather than a constant for exactly that reason.

Titles used here are real rows from the database wherever possible.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.models.base import company_scope
from app.models.user import SystemSetting
from app.models.projects import Project, ProjectParty
from app.services.project_clash_service import find_clashes, normalise_project_title

from ._pg_fixture import blank_session

MARKER = "zzt-clash"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _party(db, company_id: str, name: str) -> ProjectParty:
    party = ProjectParty(
        id=_uid(), company_id=company_id, party_type="developer", name=name
    )
    db.add(party)
    db.flush()
    return party


def _project(
    db,
    company_id: str,
    developer: ProjectParty,
    title: str,
    *,
    outcome: str = "open",
    code: str | None = None,
) -> Project:
    project = Project(
        id=_uid(),
        company_id=company_id,
        project_code=code or f"{MARKER}-{uuid.uuid4().hex[:6]}",
        title=title,
        normalised_title=normalise_project_title(title),
        developer_party_id=developer.id,
        outcome=outcome,
    )
    db.add(project)
    db.flush()
    return project


def test_normalisation_collapses_casing_and_repeated_whitespace():
    """The database really does contain a doubled space in this title."""
    raw = "KSL Setia Alam Project  (733 units service apartment)"
    assert normalise_project_title(raw) == "ksl setia alam project (733 units service apartment)"


def test_titles_differing_only_in_case_and_spacing_share_one_key():
    padded = "  MENARA STAR HQ   TOILET RENOVATION "
    tidy = "Menara Star HQ Toilet Renovation"
    assert normalise_project_title(padded) == normalise_project_title(tidy)


def test_exact_duplicate_registration_is_blocked():
    """The core of ADR-0004: one development, one registration, per company."""
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _party(db, company_id, f"{MARKER} SP Setia")
        incumbent = _project(db, company_id, developer, "Setia Alam Phase 3B")

        clashes = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=developer.id,
            title="  setia alam   PHASE 3b ",
        )

        assert [c.project_id for c in clashes] == [incumbent.id]
        assert clashes[0].blocks is True
        assert clashes[0].similarity == 1.0


def test_abbreviated_title_still_clashes_with_its_full_form():
    """Real drift: salespeople type "Ph" for "Phase" and "Apt" for "Apartment".

    Exact-key matching alone misses these, which is the whole reason for trigram
    similarity on top of the exact key.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _party(db, company_id, f"{MARKER} SP Setia")
        incumbent = _project(db, company_id, developer, "Setia Alam Phase 3B")

        clashes = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=developer.id,
            title="Setia Alam Ph 3B",
        )

        assert [c.project_id for c in clashes] == [incumbent.id]
        assert clashes[0].blocks is True
        assert 0.7 <= clashes[0].similarity < 1.0


def test_sibling_phases_are_context_not_a_block():
    """Phase 3A and Phase 3B are separate developments, separately registrable.

    Measured trigram similarity between them is 0.818 -- HIGHER than the genuine
    abbreviation variants this matcher must catch ("Ph 3B" vs "Phase 3B" scores
    0.762). No similarity threshold can separate the two cases, so blocking cannot
    be a function of similarity alone.

    The discriminator is the digit-bearing tokens: "3a" and "3b" are the phase
    designators, and titles whose designators differ are siblings no matter how
    alike the rest reads. The sibling is still RETURNED, because seeing "Ali has
    Phase 3A" is exactly the context that stops two people duplicating an
    approach to one developer.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _party(db, company_id, f"{MARKER} SP Setia")
        sibling = _project(db, company_id, developer, "Setia Alam Phase 3A")

        clashes = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=developer.id,
            title="Setia Alam Phase 3B",
        )

        assert [c.project_id for c in clashes] == [sibling.id]
        assert clashes[0].blocks is False
        assert clashes[0].similarity > 0.8


def test_a_lost_project_is_context_and_never_blocks():
    """ADR-0004: only an OPEN pursuit blocks.

    Blocking forever would make a lost 2023 tender permanently unregistrable, and
    a re-tender is a normal, valuable event. The lost row still comes back so the
    new owner can read why it was lost before repeating the mistake.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _party(db, company_id, f"{MARKER} Mah Sing")
        lost = _project(
            db, company_id, developer, "M Vertica Cheras", outcome="lost"
        )

        clashes = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=developer.id,
            title="M Vertica Cheras",
        )

        assert [c.project_id for c in clashes] == [lost.id]
        assert clashes[0].blocks is False
        assert clashes[0].outcome == "lost"


def test_a_dormant_project_is_context_and_never_blocks():
    """Dormant is "gone quiet", not "gone". Same re-registration logic as lost."""
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _party(db, company_id, f"{MARKER} IOI Properties")
        dormant = _project(
            db, company_id, developer, "IOI Resort City Clubhouse", outcome="dormant"
        )

        clashes = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=developer.id,
            title="IOI Resort City Clubhouse",
        )

        assert [c.project_id for c in clashes] == [dormant.id]
        assert clashes[0].blocks is False


def test_the_same_title_under_a_different_developer_does_not_clash():
    """"Phase 2" is not a unique name. Every developer has one.

    Identity is developer PLUS title, so a title collision across developers must
    not even surface -- surfacing it would train users to dismiss the warning.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        incumbent_dev = _party(db, company_id, f"{MARKER} Gamuda Land")
        other_dev = _party(db, company_id, f"{MARKER} Sime Darby Property")
        _project(db, company_id, incumbent_dev, "Gardens Phase 2")

        clashes = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=other_dev.id,
            title="Gardens Phase 2",
        )

        assert clashes == []


def test_an_unrelated_title_under_the_same_developer_does_not_clash():
    """Two genuinely different developments for one developer, measured at 0.025."""
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _party(db, company_id, f"{MARKER} EcoWorld")
        _project(db, company_id, developer, "Setia Alam Phase 3B")

        clashes = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=developer.id,
            title="Eco Majestic Project",
        )

        assert clashes == []


def test_another_companys_project_is_invisible_even_to_a_wide_scope_session():
    """Company is a hard partition (ADR: multi-company isolation).

    SRT and MOCHA may each pursue the same physical development, and neither may
    learn that the other is doing so.

    The session here is scoped to BOTH companies on purpose. A superadmin has
    exactly that scope, so the ORM auto-filter stops restricting to one company and
    the matcher's own ``company_id`` predicate becomes the only thing standing
    between an admin registering a project and being told a DIFFERENT company's
    project blocks it. Scoping the session to one company would let this test pass
    even if the matcher ignored ``company_id`` entirely (verified by mutation).
    """
    with blank_session() as db:
        srt_id = _sorento(db)

        # The blank schema seeds Sorento only, so the second company is created
        # here. Raw insert because Company is not company-scoped itself.
        mocha_id = _uid()
        db.execute(
            text(
                "insert into companies (id, name, code, is_active) "
                "values (:id, :name, 'ZZTMOCHA', true)"
            ),
            {"id": mocha_id, "name": f"{MARKER} Mocha"},
        )
        db.flush()

        with company_scope(db, frozenset({srt_id, mocha_id})):
            mocha_dev = _party(db, mocha_id, f"{MARKER} UEM Sunrise")
            mocha_project = _project(
                db, mocha_id, mocha_dev, "Serene Heights Semenyih"
            )

            # Guard: the row really is visible to this session, so an empty result
            # below means the matcher filtered it, not that it was never readable.
            assert db.query(Project).filter(Project.id == mocha_project.id).first()

            clashes = find_clashes(
                db,
                company_id=srt_id,
                developer_party_id=mocha_dev.id,
                title="Serene Heights Semenyih",
            )

        assert clashes == []


def test_a_short_title_clashes_with_its_verbose_incumbent():
    """Real titles in the database carry parenthetical descriptions.

    "KSL Setia Alam Project  (733 units service apartment)" is an actual row. The
    second person to pursue it will type "KSL Setia Alam", and plain trigram
    similarity scores that pair at only 0.312 -- far below any workable threshold,
    because ``similarity()`` is symmetric and punishes the length difference. The
    duplicate would sail straight through, which is the exact failure this module
    exists to prevent.

    ``strict_word_similarity()`` is the asymmetric form: it asks how well the
    shorter string is covered by the longer one, and scores this pair 1.0 while
    leaving genuinely unrelated titles at 0.26 and below.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _party(db, company_id, f"{MARKER} KSL Holdings")
        incumbent = _project(
            db,
            company_id,
            developer,
            "KSL Setia Alam Project  (733 units service apartment)",
        )

        clashes = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=developer.id,
            title="KSL Setia Alam",
        )

        assert [c.project_id for c in clashes] == [incumbent.id]
        assert clashes[0].blocks is True


def test_a_verbose_title_clashes_with_its_short_incumbent():
    """The same containment, in the other direction.

    Whoever registers first decides which of the two titles is the stored one, so
    coverage has to be checked both ways or the outcome depends on typing order.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _party(db, company_id, f"{MARKER} KSL Holdings")
        incumbent = _project(db, company_id, developer, "KSL Setia Alam")

        clashes = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=developer.id,
            title="KSL Setia Alam Project (service apartment)",
        )

        assert [c.project_id for c in clashes] == [incumbent.id]
        assert clashes[0].blocks is True


def test_an_unrelated_project_by_the_same_developer_survives_containment_scoring():
    """The asymmetric score must not turn every shared prefix into a clash.

    "KSL Residence Johor" and "KSL Setia Alam Project" share a developer and a
    leading word. Measured at 0.20, comfortably below threshold -- pinned here
    because loosening the scoring is exactly how that would stop being true.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _party(db, company_id, f"{MARKER} KSL Holdings")
        _project(
            db,
            company_id,
            developer,
            "KSL Setia Alam Project  (733 units service apartment)",
        )

        clashes = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=developer.id,
            title="KSL Residence Johor",
        )

        assert clashes == []


def test_two_different_hotels_surface_as_context_but_do_not_block():
    """Both of these are real titles from the live data.

    "IKI Hotel" and "The Jerai Hotel" are different developments that happen to
    share a generic noun, and short titles sharing a generic noun score 0.600 --
    above the surfacing bar. Blocking there would fire on ordinary unrelated work
    (the pipeline is full of hotels, residences and renovations) and train users to
    dismiss the warning, which costs more than the duplicate it was meant to catch.

    So surfacing and blocking are separate bars. Everything above the surfacing bar
    is shown, because a silent miss is the unrecoverable failure; only a score above
    the higher blocking bar actually stops the save.

    Calibrated on all 63 distinct titles in the live data: genuine same-development
    pairs score 0.762 and up (including 0.893 for the reordered "Helicopter Centre
    in Subang" / "Subang Helicopter Centre"), while unrelated pairs sharing a generic
    noun top out at 0.667.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _party(db, company_id, f"{MARKER} Jerai Group")
        other = _project(db, company_id, developer, "The Jerai Hotel")

        clashes = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=developer.id,
            title="IKI Hotel",
        )

        assert [c.project_id for c in clashes] == [other.id]
        assert clashes[0].blocks is False


def test_a_reordered_title_still_blocks():
    """Real pair from the live data, scoring 0.893.

    Word order carries no meaning in these titles, and someone typing the same
    development the other way round must not get a second registration.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _party(db, company_id, f"{MARKER} Subang Airport")
        incumbent = _project(db, company_id, developer, "Subang Helicopter Centre")

        clashes = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=developer.id,
            title="Helicopter Centre in Subang",
        )

        assert [c.project_id for c in clashes] == [incumbent.id]
        assert clashes[0].blocks is True


def test_the_thresholds_come_from_system_settings(monkeypatch):
    """AC-C5: the threshold is a system setting, not a constant.

    How the team names projects decides where the bars belong, and that is only
    knowable from live use. A redeploy to tune a number nobody can measure in advance
    is the wrong shape.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _party(db, company_id, f"{MARKER} Jerai Group")
        other = _project(db, company_id, developer, "The Jerai Hotel")

        # Default bars: 0.600 surfaces as context, does not block.
        default_result = find_clashes(
            db, company_id=company_id, developer_party_id=developer.id, title="IKI Hotel"
        )
        assert [c.blocks for c in default_result] == [False]

        # Lower the block bar in settings; the same pair now blocks.
        db.add(SystemSetting(id=_uid(), project_clash_block_threshold=0.5))
        db.flush()

        tuned = find_clashes(
            db, company_id=company_id, developer_party_id=developer.id, title="IKI Hotel"
        )
        assert [c.project_id for c in tuned] == [other.id]
        assert tuned[0].blocks is True


def test_without_a_developer_a_title_match_blocks_rather_than_merely_informing():
    """Reverses an earlier decision, on evidence: developer-less matches used to be context.

    The original rule was "identity is developer PLUS title, so a title-only match cannot
    BLOCK", on the grounds that two developers can each have a "Phase 2". True, but it made
    the exclusivity lock opt-out with a blank optional field as the opt-out: an exact
    re-registration of a claimed title sailed through whenever Developer was left empty,
    and the candidate list showed the incumbent while nothing stopped the save.

    An unnamed developer does not make the two projects different - it leaves sameness
    UNPROVEN, and the module prefers a visible block with Ask-to-join / Dispute recourse
    over a silent duplicate (the same reasoning as ``are_sibling_developments``). Naming a
    different developer clears it, so the verdict is never a dead end.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _party(db, company_id, f"{MARKER} SP Setia")
        incumbent = _project(db, company_id, developer, "Setia Alam Phase 3B")

        for widened in (False, True):
            found = find_clashes(
                db,
                company_id=company_id,
                developer_party_id=None,
                title="Setia Alam Phase 3B",
                include_other_developers=widened,
            )
            assert [c.project_id for c in found] == [incumbent.id], (
                "a blank developer must search every developer, not only the "
                f"developer-less ones (include_other_developers={widened})"
            )
            assert found[0].blocks is True, "sameness unproven is not sameness disproven"

        # The widened search is the live preview, so it also has to name who holds it.
        widened = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=None,
            title="Setia Alam Phase 3B",
            include_other_developers=True,
        )
        assert widened[0].developer_name == f"{MARKER} SP Setia"


def test_naming_a_different_developer_releases_the_unproven_block():
    """The escape hatch, pinned: the block is about what is unknown, not about the title.

    Without this, widening the developer-less search would strand a legitimate registration
    with no way through the dialog.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        setia = _party(db, company_id, f"{MARKER} SP Setia")
        _project(db, company_id, setia, "Setia Alam Phase 3B")
        mah_sing = _party(db, company_id, f"{MARKER} Mah Sing")

        found = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=mah_sing.id,
            title="Setia Alam Phase 3B",
            include_other_developers=True,
        )

        assert [c.blocks for c in found] == [False]


def test_widening_never_downgrades_a_real_block():
    """With the developer known, the widened search must still block its own matches.

    Otherwise the preview (which widens) would disagree with the create (which does
    not), and the user would be told they are fine right up until the save fails.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _party(db, company_id, f"{MARKER} SP Setia")
        other = _party(db, company_id, f"{MARKER} Gamuda Land")
        mine = _project(db, company_id, developer, "Setia Alam Phase 3B")
        theirs = _project(db, company_id, other, "Setia Alam Phase 3B")

        widened = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=developer.id,
            title="setia alam ph 3b",
            include_other_developers=True,
        )

        by_id = {c.project_id: c for c in widened}
        assert set(by_id) == {mine.id, theirs.id}
        assert by_id[mine.id].blocks is True
        assert by_id[theirs.id].blocks is False


# --------------------------------------------------------------------------- #
# Containment: a name that IS an existing name, however far the typing got     #
# --------------------------------------------------------------------------- #


def test_a_partly_typed_name_inside_an_existing_one_overlaps():
    """Reported from the browser: "Kepong Metropo" scores 0.667 against "Kepong
    Metropolitan Serviced Apartments", under the 0.70 block bar, so it surfaced as a mere
    suggestion when it is in fact the same development."""
    from app.services.project_clash_service import titles_overlap

    assert titles_overlap("kepong metropolitan serviced apartments", "kepong metropo")


def test_a_longer_separate_development_does_not_overlap():
    """The reason the fix is containment and NOT a lower threshold. This scores 0.606, so
    dropping the bar to catch 0.667 would block a registration that has to be allowed."""
    from app.services.project_clash_service import titles_overlap

    assert not titles_overlap(
        "kepong metropolitan serviced apartments", "kepong metropolitan times square"
    )


def test_containment_is_symmetric():
    """Whoever registered first decided which title is the longer one."""
    from app.services.project_clash_service import titles_overlap

    assert titles_overlap("kepong metropo", "kepong metropolitan serviced apartments")


def test_a_couple_of_characters_never_overlap():
    """Blocking on the second keystroke would fight the person typing."""
    from app.services.project_clash_service import titles_overlap

    assert not titles_overlap("kepong metropolitan serviced apartments", "kep")
    assert not titles_overlap("kepong metropolitan serviced apartments", "")
