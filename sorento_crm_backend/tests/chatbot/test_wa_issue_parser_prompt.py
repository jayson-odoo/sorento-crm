"""WA-COMPLAINT-INTAKE round 9: a report of a CRM or assistant problem is ideate, in the STORED parser prompt.

Contract: documentation/plans/chatbot/PROMPT-wa-issue-ideate.md. Production runs the stored
`chatbot_semantic_parser` version (v72, md5 d29c1983...), not the code template, so the rule has to ship
as a new stored version:

* `app.services.chatbot.head.issue_rule.apply_issue_rule(text) -> str | None` makes the doc's two edits by
  anchor (each anchor occurs exactly once in v72). It raises ValueError when an anchor is missing and
  returns None when the text already carries the rule (idempotent, a no-op signal).
* Round 12 widens edit 2's text and adds edit 4 (rule 1, line 157) and edit 5 (the "outranks" line 164),
  each appended in place after an anchor found exactly once: five edits on four lines, no line added.
  The rule-1 phrase "is NOT request_for_help, even when it names IT" is in the candidate AND the template.
* Round 13 adds edit 6: the DECISIVE signal-word rule (v72 line 58) gets an exception appended in place
  after its last sentence: a report that the assistant or a CRM screen got something wrong is ideate and
  the signal word sets no domain. Six edits on five lines, still no line added (1037 lines).
* Applied to v72 it gives exactly the committed candidate `prompt-wa-issue-ideate.txt` (md5 pinned here).
* The shared phrase "a problem with the CRM system or the assistant itself" is in the candidate AND the
  code template (`head.parser_template.TEMPLATE`), so the two agree.
* Migration `wa_0002_parser_issue_ideate` `publish(session)`: applies the rule to the text of the version
  holding the `production` label and publishes it as the next version, UNLABELLED, marker
  `wa_0002_parser_issue_ideate` in `config_json`; idempotent; publishes nothing (and does not raise) when
  the production text lacks an anchor; `downgrade()` removes only its own unlabelled row.
* After the owner moves the production label onto it, `ai_prompt_registry.get_prompt` serves the rule.

Postgres only (blank scratch schema); every test seeds its own prompt rows. Names that do not exist yet are
reached at call time, so a missing name fails its test and never the collection.
"""
from __future__ import annotations

import difflib
import hashlib
from pathlib import Path

import pytest

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from tests._pg_fixture import blank_session
from tests.chatbot.test_rearch_s12_config_ships import _load

# Writes the parser's prompt rows: one such test at a time across xdist workers
# (tests/conftest.py `_parser_prompt_rows_lock`).
pytestmark = pytest.mark.parser_prompt_rows

_PLANS = Path(__file__).resolve().parents[3] / "documentation" / "plans" / "chatbot"
BASE_PATH = _PLANS / "prompt-prod-v72-d29c1983.txt"
CANDIDATE_PATH = _PLANS / "prompt-wa-issue-ideate.txt"
BASE_MD5 = "d29c19830b22aa47403a88ddcb8e817d"  # production v72 (crew, 5 Nov)
# The lead fills this in once the coder has committed prompt-wa-issue-ideate.txt (md5 of that exact file).
# Until then this test is red on purpose.
CANDIDATE_MD5 = "d7d8c83742e2c43f56fc44cf9f0b9c1d"

PROMPT_NAME = "chatbot_semantic_parser"
MIGRATION_FILE = "wa_0002_parser_issue_ideate.py"
MARKER_KEY = "wa_0002_parser_issue_ideate"
SHARED_PHRASE = "a problem with the CRM system or the assistant itself"

# The doc's edits, verbatim. Round 11 made three; round 12 widens edit 2's text and adds edits 4 and 5.
# Every edit changes a line in place: no line is added (the candidate keeps v72's 1037 lines).
EDIT1_OLD = "a complaint about existing behaviour (stays portal_link/complaint);"
EDIT1_NEW = "a complaint about a product or an order (stays portal_link/complaint);"
HUMAN_OLD = "asking for a human (stays request_for_help)."
HUMAN_NEW = (
    "asking for a human (stays request_for_help). ALSO ideate: the user reports a problem with the CRM system "
    "or the assistant itself (it errors, keeps loading, does not work or answers wrongly, whatever screen or "
    "list it is on), or says they want to report one before saying what it is: an issue to log, no routing, "
    "never request_for_help or an IT or support team, also when the user names IT or a team to report it to."
)
EDIT2_OLD = "  - ideate (an idea is never escalated), or none of these this turn -> NO routing: null / null"
EDIT2_NEW = (
    "  - ideate (an idea or an issue report is never escalated), or none of these this turn -> NO routing: "
    "null / null"
)
# Round 12 edit 4: MESSAGE TYPE rule 1 (v72 line 157), appended in place after the anchor.
RULE1_OLD = (
    'Customer/company names (e.g. "today plumbing", "total home") are NOT departments and never trigger '
    "request_for_help."
)
RULE1_NEW = RULE1_OLD + (
    " A report of a problem with the CRM system or the assistant is NOT request_for_help, even when it names "
    "IT, the IT team or a support team, or asks to report or send it to them: it is ideate (an issue to log, "
    "see the ideate bullet), message_type business_query, no routing. Only an ask to be put through to IT or "
    "a person that neither reports a problem nor says the user wants to report one stays request_for_help."
)
RULE1_LINE = 157
# Round 12 edit 5: the "outranks" line (v72 line 164), appended in place after the anchor.
OUTRANK_OLD = (
    '"request_for_help" outranks business_query, clarification and casual, even when the message also '
    "mentions a product or order."
)
OUTRANK_NEW = OUTRANK_OLD + " It never outranks a report of a CRM system or assistant problem (rule 1)."
OUTRANK_LINE = 164
# Round 12: the rule-1 phrase both the stored text and the code template carry.
RULE1_PHRASE = "is NOT request_for_help, even when it names IT"
# Round 13 edit 6: the DECISIVE signal-word rule (v72 line 58), appended in place after the anchor.
EDIT6_OLD = "Only with NO decisive term AND a genuinely ambiguous domain \u2192 domain_hint and intent_hint null."
EDIT6_NEW = EDIT6_OLD + (
    " One exception: when the user says the assistant (the bot, the AI, its answer) or a CRM screen got "
    "something wrong, a signal word only names what the problem was about and sets no domain; that report is "
    "ideate (see the ideate bullet). A user who questions or disputes a record's own figure or status, without "
    "blaming the assistant or a screen, keeps the domain."
)
EDIT6_LINE = 58
V72_LINE_COUNT = 1037


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _v72() -> str:
    assert _md5(BASE_PATH) == BASE_MD5, "the v72 base file changed"
    return BASE_PATH.read_text(encoding="utf-8")


def _expected_from_doc(text: str) -> str:
    """The doc's six edits, derived here independently of the code under test."""
    lines = text.split("\n")
    (i,) = [n for n, line in enumerate(lines) if EDIT1_OLD in line]
    assert lines[i].count(HUMAN_OLD) == 1, "edit 2's anchor sits on the ideate bullet's own line"
    (j,) = [n for n, line in enumerate(lines) if line == EDIT2_OLD]
    (k,) = [n for n, line in enumerate(lines) if RULE1_OLD in line]
    (m,) = [n for n, line in enumerate(lines) if OUTRANK_OLD in line]
    (q,) = [n for n, line in enumerate(lines) if EDIT6_OLD in line]
    assert len({i, j, k, m, q}) == 5, "the five edited lines are distinct"
    lines[j] = EDIT2_NEW
    lines[i] = lines[i].replace(EDIT1_OLD, EDIT1_NEW).replace(HUMAN_OLD, HUMAN_NEW)
    lines[k] = lines[k].replace(RULE1_OLD, RULE1_NEW)
    lines[m] = lines[m].replace(OUTRANK_OLD, OUTRANK_NEW)
    lines[q] = lines[q].replace(EDIT6_OLD, EDIT6_NEW)
    return "\n".join(lines)


def _apply():
    from app.services.chatbot.head.issue_rule import apply_issue_rule

    return apply_issue_rule


# --------------------------------------------------------------------------- #
# 1. The candidate file is v72 plus exactly the six edits, on five lines      #
# --------------------------------------------------------------------------- #
def test_R13_the_candidate_is_pinned_and_is_v72_plus_the_six_edits():
    """Round 13 (F3 kept): the six edits change five lines in place (ideate bullet, the DECISIVE rule on
    line 58, rule 1 on line 157, the outranks line 164, the routing line) and add none."""
    v72 = _v72()
    assert len(v72.split("\n")) - (1 if v72.endswith("\n") else 0) == V72_LINE_COUNT
    assert CANDIDATE_PATH.is_file(), f"missing committed candidate {CANDIDATE_PATH.name}"
    candidate = CANDIDATE_PATH.read_text(encoding="utf-8")
    assert len(candidate.split("\n")) == len(v72.split("\n")), "the candidate adds a line (F3)"
    assert candidate == _expected_from_doc(v72)

    removed, added = [], []
    for line in difflib.unified_diff(v72.split("\n"), candidate.split("\n"), lineterm="", n=0):
        if line.startswith(("---", "+++", "@@")):
            continue
        (removed if line.startswith("-") else added).append(line[1:])
    v72_lines = v72.split("\n")
    old_bullet = next(line for line in v72_lines if EDIT1_OLD in line)
    new_bullet = old_bullet.replace(EDIT1_OLD, EDIT1_NEW).replace(HUMAN_OLD, HUMAN_NEW)
    old_rule1 = v72_lines[RULE1_LINE - 1]
    old_outrank = v72_lines[OUTRANK_LINE - 1]
    old_decisive = v72_lines[EDIT6_LINE - 1]
    assert EDIT6_OLD in old_decisive, f"edit 6's anchor sits on v72 line {EDIT6_LINE}"
    assert RULE1_OLD in old_rule1, f"edit 4's anchor sits on v72 line {RULE1_LINE}"
    assert OUTRANK_OLD in old_outrank, f"edit 5's anchor sits on v72 line {OUTRANK_LINE}"
    new_rule1 = old_rule1.replace(RULE1_OLD, RULE1_NEW)
    new_outrank = old_outrank.replace(OUTRANK_OLD, OUTRANK_NEW)
    new_decisive = old_decisive.replace(EDIT6_OLD, EDIT6_NEW)
    assert len(removed) == 5 and len(added) == 5, (removed, added)
    assert sorted(removed) == sorted([old_bullet, old_decisive, old_rule1, old_outrank, EDIT2_OLD])
    assert sorted(added) == sorted([new_bullet, new_decisive, new_rule1, new_outrank, EDIT2_NEW])
    cand_lines = candidate.split("\n")
    assert cand_lines[EDIT6_LINE - 1] == new_decisive
    assert cand_lines[RULE1_LINE - 1] == new_rule1
    assert cand_lines[OUTRANK_LINE - 1] == new_outrank
    assert _md5(CANDIDATE_PATH) == CANDIDATE_MD5, "pin the candidate's md5 (CANDIDATE_MD5)"


def test_R9_apply_issue_rule_on_v72_returns_the_committed_candidate():
    v72 = _v72()
    got = _apply()(v72)
    assert got == _expected_from_doc(v72)
    assert got == CANDIDATE_PATH.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 2. Missing anchor raises; a text that already carries the rule is a no-op    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "anchor",
    [EDIT1_OLD, HUMAN_OLD, EDIT2_OLD, RULE1_OLD, OUTRANK_OLD, EDIT6_OLD],
    ids=["complaint_clause", "human_clause", "routing_line", "rule1_line", "outranks_line", "decisive_line"],
)
def test_R9_apply_issue_rule_raises_when_an_anchor_is_missing(anchor):
    text = _v72().replace(anchor, "zzt anchor gone")
    with pytest.raises(ValueError):
        _apply()(text)


def test_R12_edit4_edit5_and_edit6_anchors_occur_exactly_once_in_v72():
    v72 = _v72()
    assert v72.count(RULE1_OLD) == 1
    assert v72.count(OUTRANK_OLD) == 1
    assert v72.count(EDIT6_OLD) == 1


@pytest.mark.parametrize(
    "anchor", [RULE1_OLD, OUTRANK_OLD, EDIT6_OLD], ids=["rule1_line", "outranks_line", "decisive_line"]
)
def test_R12_apply_issue_rule_raises_when_an_edit4_edit5_or_edit6_anchor_occurs_twice(anchor):
    """Each new anchor must be found exactly once: a second copy is ambiguous, so refuse rather than guess."""
    text = _v72() + "\n" + anchor
    assert text.count(anchor) == 2
    with pytest.raises(ValueError):
        _apply()(text)


def test_R11_S5_the_human_clause_on_another_line_raises():
    """Review S5: the anchor occurs once but not on the ideate bullet's own line: refuse, never publish a
    text that only half carries the rule."""
    v72 = _v72()
    moved = v72.replace(" " + HUMAN_OLD, "", 1) + "\n" + HUMAN_OLD
    assert moved.count(HUMAN_OLD) == 1
    with pytest.raises(ValueError):
        _apply()(moved)


def test_R9_apply_issue_rule_is_idempotent():
    apply_issue_rule = _apply()
    once = apply_issue_rule(_v72())
    assert once is not None and SHARED_PHRASE in once
    assert apply_issue_rule(once) is None


# --------------------------------------------------------------------------- #
# 3. The stored text and the code template share the phrase                   #
# --------------------------------------------------------------------------- #
def test_R9_the_shared_phrase_is_in_the_candidate_and_the_code_template():
    from app.services.chatbot.head.parser_template import TEMPLATE

    assert SHARED_PHRASE in TEMPLATE
    assert SHARED_PHRASE not in _v72(), "v72 must not carry it already"
    assert SHARED_PHRASE in CANDIDATE_PATH.read_text(encoding="utf-8")


def test_R12_the_rule1_phrase_is_in_the_candidate_and_the_code_template():
    """Round 12: the code template mirrors edit 4 in rule 1, so both texts carry the same phrase."""
    from app.services.chatbot.head.parser_template import TEMPLATE

    assert RULE1_PHRASE not in _v72(), "v72 must not carry it already"
    assert RULE1_PHRASE in CANDIDATE_PATH.read_text(encoding="utf-8")
    assert RULE1_PHRASE in TEMPLATE


def test_R12_N5_the_code_template_ideate_line_names_loading_screens_and_a_named_team():
    """Review N5: the template's ideate line says a screen or list that keeps loading is an issue, and that it
    stays an issue when the user names IT or a team."""
    from app.services.chatbot.head.parser_template import TEMPLATE

    (line,) = [ln for ln in TEMPLATE.split("\n") if ln.startswith("- ideate / submit_idea:")]
    assert "keeps loading" in line
    assert "names IT or a team" in line


# --------------------------------------------------------------------------- #
# 4. The migration publishes the next version, unlabelled, once               #
# --------------------------------------------------------------------------- #
def _production_on(db, template: str, version: int = 72) -> AIPromptVersion:
    """A `chatbot_semantic_parser` version holding the `production` label, with this template."""
    row = AIPromptVersion(
        name=PROMPT_NAME, version=version, type="text", template=template, variables=[], config_json={},
        commit_message="zzt production",
    )
    db.add(row)
    db.flush()
    db.add(AIPromptLabel(name=PROMPT_NAME, label="production", version_id=row.id))
    db.flush()
    return row


def _parser_rows(db) -> dict[str, AIPromptVersion]:
    db.expire_all()
    return {r.id: r for r in db.query(AIPromptVersion).filter(AIPromptVersion.name == PROMPT_NAME)}


def _production_id(db) -> str:
    return (
        db.query(AIPromptLabel)
        .filter(AIPromptLabel.name == PROMPT_NAME, AIPromptLabel.label == "production")
        .one()
        .version_id
    )


def _migration():
    return _load(MIGRATION_FILE)


def test_R9_migration_revision_id():
    mig = _migration()
    assert mig.revision == MARKER_KEY
    assert len(mig.revision) <= 32


def test_R9_publish_adds_one_unlabelled_version_with_the_rule_and_the_marker():
    mig = _migration()
    with blank_session() as db:
        v72_text = _v72()
        prod = _production_on(db, v72_text)
        before = _parser_rows(db)

        mig.publish(db)

        new = [r for vid, r in _parser_rows(db).items() if vid not in before]
        assert len(new) == 1, f"expected one new version, found {len(new)}"
        (row,) = new
        assert row.version == max(r.version for r in before.values()) + 1
        assert row.template == _apply()(v72_text)
        assert (row.config_json or {}).get(MARKER_KEY), row.config_json
        assert _production_id(db) == prod.id, "the production label moved"
        labelled = {lab.version_id for lab in db.query(AIPromptLabel).filter(AIPromptLabel.name == PROMPT_NAME)}
        assert row.id not in labelled

        mig.publish(db)
        assert len(_parser_rows(db)) == len(before) + 1, "a second publish added a version"


def test_R9_publish_with_no_anchor_in_production_adds_nothing_and_does_not_raise():
    mig = _migration()
    with blank_session() as db:
        _production_on(db, "zzt production text with no ideate anchors\n== ROUTING ==\n")
        before = _parser_rows(db)
        mig.publish(db)
        assert set(_parser_rows(db)) == set(before)


def test_R9_downgrade_removes_only_its_own_unlabelled_row():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mig = _migration()
    with blank_session() as db:
        prod = _production_on(db, _v72())
        other = AIPromptVersion(
            name=PROMPT_NAME, version=50, type="text", template="zzt someone else's unlabelled draft",
            variables=[], config_json={}, commit_message="zzt other",
        )
        db.add(other)
        db.flush()
        mig.publish(db)
        published = [r for r in _parser_rows(db).values() if (r.config_json or {}).get(MARKER_KEY)]
        assert len(published) == 1, "fixture: publish wrote its marked row"
        published_id, prod_id, other_id = published[0].id, prod.id, other.id

        with Operations.context(MigrationContext.configure(db.connection())):
            mig.downgrade()

        left = _parser_rows(db)
        assert published_id not in left
        assert prod_id in left and other_id in left
        assert _production_id(db) == prod_id


# --------------------------------------------------------------------------- #
# 5. The active prompt carries the rule only after the label moves            #
# --------------------------------------------------------------------------- #
def _live_text(db) -> str:
    from app.services import ai_prompt_registry

    ai_prompt_registry.bust_cache(PROMPT_NAME)
    return ai_prompt_registry.get_prompt(db, PROMPT_NAME).text


def test_R9_control_the_active_v72_prompt_lacks_the_rule():
    """The crew's finding: production serves v72, which does not carry the rule."""
    with blank_session() as db:
        _production_on(db, _v72())
        assert SHARED_PHRASE not in _live_text(db)


def test_R9_the_active_prompt_carries_the_rule_after_promotion():
    mig = _migration()
    with blank_session() as db:
        _production_on(db, _v72())
        mig.publish(db)
        assert SHARED_PHRASE not in _live_text(db), "publishing alone must not change the live prompt"
        (new,) = [r for r in _parser_rows(db).values() if (r.config_json or {}).get(MARKER_KEY)]
        # The Prompts page's promotion: the production label row now points at the new version.
        label = (
            db.query(AIPromptLabel)
            .filter(AIPromptLabel.name == PROMPT_NAME, AIPromptLabel.label == "production")
            .one()
        )
        label.version_id = new.id
        db.flush()
        assert SHARED_PHRASE in _live_text(db)


def test_R10_B2_downgrade_keeps_a_promoted_row_and_its_production_label():
    """Review B2: once the owner has moved the production label onto the published row, a downgrade must not
    delete that row (the label row would cascade with it and production would point at nothing)."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mig = _migration()
    with blank_session() as db:
        old = _production_on(db, _v72())
        mig.publish(db)
        (new,) = [r for r in _parser_rows(db).values() if (r.config_json or {}).get(MARKER_KEY)]
        label = (
            db.query(AIPromptLabel)
            .filter(AIPromptLabel.name == PROMPT_NAME, AIPromptLabel.label == "production")
            .one()
        )
        label.version_id = new.id
        db.flush()
        new_id, label_id, old_id = new.id, label.id, old.id

        with Operations.context(MigrationContext.configure(db.connection())):
            mig.downgrade()

        left = _parser_rows(db)
        assert new_id in left, "the downgrade deleted the promoted row"
        assert old_id in left
        prod = (
            db.query(AIPromptLabel)
            .filter(AIPromptLabel.name == PROMPT_NAME, AIPromptLabel.label == "production")
            .one_or_none()
        )
        assert prod is not None and prod.id == label_id, "the production label is gone"
        assert prod.version_id == new_id
        assert SHARED_PHRASE in _live_text(db)
