"""WA-COMPLAINT-INTAKE round 9: a report of a CRM or assistant problem is ideate, in the STORED parser prompt.

Contract: documentation/plans/chatbot/PROMPT-wa-issue-ideate.md. Production runs the stored
`chatbot_semantic_parser` version (v72, md5 d29c1983...), not the code template, so the rule has to ship
as a new stored version:

* `app.services.chatbot.head.issue_rule.apply_issue_rule(text) -> str | None` makes the doc's two edits by
  anchor (each anchor occurs exactly once in v72). It raises ValueError when an anchor is missing and
  returns None when the text already carries the rule (idempotent, a no-op signal).
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
CANDIDATE_MD5 = "edfb489f352ac552d82266b1bd362095"

PROMPT_NAME = "chatbot_semantic_parser"
MIGRATION_FILE = "wa_0002_parser_issue_ideate.py"
MARKER_KEY = "wa_0002_parser_issue_ideate"
SHARED_PHRASE = "a problem with the CRM system or the assistant itself"

# The doc's two edits, verbatim.
EDIT1_OLD = "a complaint about existing behaviour (stays portal_link/complaint);"
EDIT1_NEW = "a complaint about a product or an order (stays portal_link/complaint);"
INSERTED_LINE = (
    "    → ALSO ideate: the user REPORTS a problem with the CRM system or the assistant itself (an error, a "
    "screen or page that does not load, does not work or shows wrong data, an answer from the assistant that "
    "is wrong). That is an issue to log: domain_hint \"ideate\", intent_hint \"submit_idea\", message_type "
    "\"business_query\", no routing (null / null). It is never request_for_help, never an IT or support team, "
    "and never the domain of the screen or data it is about; only an explicit ask for a person to take it "
    "over is request_for_help."
)
EDIT2_OLD = "  - ideate (an idea is never escalated), or none of these this turn -> NO routing: null / null"
EDIT2_NEW = (
    "  - ideate (an idea or an issue report is never escalated), or none of these this turn -> NO routing: "
    "null / null"
)


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _v72() -> str:
    assert _md5(BASE_PATH) == BASE_MD5, "the v72 base file changed"
    return BASE_PATH.read_text(encoding="utf-8")


def _expected_from_doc(text: str) -> str:
    """The doc's edits, derived here independently of the code under test."""
    lines = text.split("\n")
    (i,) = [n for n, line in enumerate(lines) if EDIT1_OLD in line]
    (j,) = [n for n, line in enumerate(lines) if line == EDIT2_OLD]
    lines[j] = EDIT2_NEW
    lines[i] = lines[i].replace(EDIT1_OLD, EDIT1_NEW)
    lines.insert(i + 1, INSERTED_LINE)
    return "\n".join(lines)


def _apply():
    from app.services.chatbot.head.issue_rule import apply_issue_rule

    return apply_issue_rule


# --------------------------------------------------------------------------- #
# 1. The candidate file is v72 plus exactly the two edits                     #
# --------------------------------------------------------------------------- #
def test_R9_the_candidate_is_pinned_and_is_v72_plus_the_two_edits():
    v72 = _v72()
    assert CANDIDATE_PATH.is_file(), f"missing committed candidate {CANDIDATE_PATH.name}"
    assert _md5(CANDIDATE_PATH) == CANDIDATE_MD5, "pin the candidate's md5 (CANDIDATE_MD5)"
    candidate = CANDIDATE_PATH.read_text(encoding="utf-8")
    assert candidate == _expected_from_doc(v72)

    removed, added = [], []
    for line in difflib.unified_diff(v72.split("\n"), candidate.split("\n"), lineterm="", n=0):
        if line.startswith(("---", "+++", "@@")):
            continue
        (removed if line.startswith("-") else added).append(line[1:])
    old_bullet = next(line for line in v72.split("\n") if EDIT1_OLD in line)
    assert sorted(removed) == sorted([old_bullet, EDIT2_OLD])
    assert sorted(added) == sorted([old_bullet.replace(EDIT1_OLD, EDIT1_NEW), INSERTED_LINE, EDIT2_NEW])


def test_R9_apply_issue_rule_on_v72_returns_the_committed_candidate():
    v72 = _v72()
    got = _apply()(v72)
    assert got == _expected_from_doc(v72)
    assert got == CANDIDATE_PATH.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 2. Missing anchor raises; a text that already carries the rule is a no-op    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("anchor", [EDIT1_OLD, EDIT2_OLD], ids=["ideate_bullet", "routing_line"])
def test_R9_apply_issue_rule_raises_when_an_anchor_is_missing(anchor):
    text = _v72().replace(anchor, "zzt anchor gone")
    with pytest.raises(ValueError):
        _apply()(text)


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
