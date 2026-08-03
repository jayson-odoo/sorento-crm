"""S2a guards that are GREEN on arrival: things that must never appear.

Everything here asserts an ABSENCE, so none of it can be red before the implementation
exists. It is split out of ``tests/test_attachment_validator.py`` for exactly that
reason: that file is entirely red, and mixing in guards that pass by construction would
make the red count read as partial progress.

Five families:

1. **AC-M25's real teeth.** "No hardcoded branch per type exists" is not provable by
   checking that the prompt is in the registry - a validator can read the registry AND
   still say ``if attachment_type.code == "rma_readiness":``. The only thing that
   catches that is a source scan, and a source scan is an absence.

2. **One home per fact.** ``latitude`` / ``longitude`` must NOT also appear on
   ``attachments``. The coordinates are genuinely a property of the FILE, which is a
   real argument that AC-M22 put them on the wrong row (recorded in the report), but a
   column on both rows is strictly worse than a column on either: two copies of one
   fact eventually disagree and nothing says which is right.

3. **No new table.** AC-M20 says ``attachment_types`` gains three columns. A
   ``attachment_validation_configs`` / ``photo_types`` / ``service_job_photo_types``
   table beside it is a second policy row that can go missing, and AC-F10 - the very AC
   this slice supersedes - was exactly that table.

4. **The prompt key collision.** ``PROMPT_KEYS`` already contains a key named
   ``validator``: "Validator - confidence-gate the answer before send" (M3a, dormant).
   The attachment validator must not take that name, or activating M3a puts a
   photo-scoring instruction in front of the assistant's answer gate.

5. **``resources`` does not grow a dependency.** The validator lives in ``resources``
   (AC-M21) and reaches ``ai_prompt_registry`` and ``llm_provider``, neither of which is
   a module. If ``resources`` ever declares a dependency on ``complaints`` or
   ``service_jobs`` the arrow has been drawn backwards and the three consuming slices
   can no longer install independently.

Run: venv/bin/python -m pytest tests/test_attachment_validator_guards.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import pathlib
import re

# Importing the models package registers every table on Base.metadata, which is what
# the table and column guards below scan.
from app import models  # noqa: F401
from app.database import Base

REPO = pathlib.Path(__file__).resolve().parents[1]

VALIDATOR_MODULE = "app.services.attachment_validation_service"
VALIDATOR_PATH = REPO / "app" / "services" / "attachment_validation_service.py"

# Every attachment type code that exists in the repo today, plus the one AC-M26 seeds
# in S11. If any of them appears in the validator's source, per-type behaviour has
# stopped being data.
KNOWN_TYPE_CODES = (
    "rma_readiness",
    "response_attachment",
    "portal_submission",
    "workflow_submission_file",
    "complaint_document",
    "service_job_photo",
    "product_photo",
    "receipt",
)


def _maybe(dotted: str):
    """Import a module if it exists yet, else None. These guards must pass before S2a
    starts AND after it lands."""
    try:
        if importlib.util.find_spec(dotted) is None:
            return None
    except (ImportError, ModuleNotFoundError):
        return None
    return importlib.import_module(dotted)


def _validator_source() -> str:
    if not VALIDATOR_PATH.exists():
        return ""
    return VALIDATOR_PATH.read_text(encoding="utf-8")


def _strip_comments_and_docstrings(source: str) -> str:
    """Crude but sufficient: drop triple-quoted blocks and ``#`` comments.

    The docstrings of this slice legitimately NAME the type codes - explaining what
    rma_readiness is for is documentation, and a guard that failed on it would be
    telling the implementer not to explain themselves.
    """
    without_docstrings = re.sub(r'"""(?:.|\n)*?"""', "", source)
    without_docstrings = re.sub(r"'''(?:.|\n)*?'''", "", without_docstrings)
    return re.sub(r"#[^\n]*", "", without_docstrings)


# ============================================================================
# 1. AC-M25 - no hardcoded branch per type
# ============================================================================


def test_the_validator_source_never_names_an_attachment_type_code_ac_m25():
    """The test that fails the moment somebody writes
    ``if attachment_type.code == "rma_readiness":``.

    AC-M25 says per-type behaviour is DATA. The behavioural half of this lives in
    tests/test_attachment_validator.py (two runtime-created types differ only by their
    guidance), but a branch WITH a sensible default passes that test happily - the
    default handles the unknown type and the branch quietly handles the known one. Only
    the source says which.
    """
    code = _strip_comments_and_docstrings(_validator_source())
    if not code.strip():
        return  # not written yet; the red file names its absence
    found = [name for name in KNOWN_TYPE_CODES if name in code]
    assert not found, (
        f"The validator's source names attachment type code(s) {found}. AC-M25: "
        "'per-type behaviour is data. No hardcoded branch per type exists.' The moment "
        "one type is special-cased, adding the next photo type is a deployment - which "
        "is the exact cost this slice was created to remove, and the reason AC-F10's "
        "service_job_photo_types table was superseded."
    )


def test_the_validator_never_branches_on_a_type_code_at_all_ac_m25():
    """The generalisation of the test above, so a code invented AFTER this file was
    written is caught too. Reading ``.code`` for a log line is fine; comparing it is
    not, because a comparison is a branch."""
    code = _strip_comments_and_docstrings(_validator_source())
    if not code.strip():
        return
    offenders = re.findall(r"\.code\s*(?:==|!=|\bin\b|\bnot\s+in\b)", code)
    assert not offenders, (
        f"The validator compares an attachment type's `.code` ({offenders}). Every "
        "decision it makes must come from validation_guidance, min_score and "
        "validate_on_upload - the three columns AC-M20 added precisely so that no "
        "comparison against a code is ever needed."
    )


def test_the_validator_never_holds_its_own_prompt_text_ac_m25():
    """AC-M25 puts the prompt in ai_prompt_registry. A second copy inline is the one
    that actually runs after somebody edits it locally to debug something, and the
    registry version then drifts silently while the FE prompt editor shows text nobody
    is using."""
    code = _strip_comments_and_docstrings(_validator_source())
    if not code.strip():
        return
    module = _maybe(VALIDATOR_MODULE)
    if module is None:
        return
    # A prompt is long. Nothing legitimate in this module is a 200-character literal.
    long_literals = [
        literal
        for literal in re.findall(r'"([^"\\]{200,})"|\'([^\'\\]{200,})\'', code)
        for literal in literal
        if literal
    ]
    assert not long_literals, (
        "The validator holds a long string literal that looks like a prompt. AC-M25 "
        "puts the prompt in ai_prompt_registry, where it is versioned, labelled, "
        "editable without a deploy and covered by the hardcoded fallback when the DB "
        "is unreachable. An inline copy has none of those properties."
    )


# ============================================================================
# 2. One home per fact
# ============================================================================


def test_the_capture_pin_is_not_also_on_the_attachments_table():
    """AC-M22 puts latitude / longitude on the LINK row.

    There is a real argument that they belong on `attachments` instead - a geotag is a
    property of the photograph, and an attachment linked to two entities would carry the
    same coordinates twice. That argument is recorded rather than acted on. What is NOT
    arguable is having both: two copies of one immutable fact eventually disagree, and
    nothing in the schema says which one is right.
    """
    attachments = Base.metadata.tables["attachments"]
    present = [c for c in ("latitude", "longitude") if c in attachments.c]
    assert not present, (
        f"attachments now carries {present} as well as entity_attachment_links. Pick "
        "one row. If the file is the right home, MOVE the columns and update AC-M22 - "
        "do not leave a copy behind."
    )


def test_the_score_is_not_on_the_attachments_table():
    """The score is per (file, guidance) and the guidance is per TYPE per LINK. The same
    receipt scored as consumer-intake evidence and as rma_readiness proof gets two
    different numbers, and a column on `attachments` can hold only one of them - it
    would silently report the last upload's verdict for both."""
    attachments = Base.metadata.tables["attachments"]
    present = [
        c
        for c in ("ai_score", "ai_suggestion", "override_reason", "ai_validation_state")
        if c in attachments.c
    ]
    assert not present, (
        f"attachments carries {present}. These belong on entity_attachment_links "
        "(AC-M22) because they are a verdict about THIS use of the file, not about the "
        "file."
    )


# ============================================================================
# 3. No new table
# ============================================================================


def test_no_second_photo_policy_table_appeared_ac_m20():
    """AC-M20: "No new tables - it is already the per-type upload policy table."

    AC-F10's `service_job_photo_types` master is the table this slice supersedes. A new
    one under a different name is the same mistake with a fresh spelling, and it splits
    "how many, how big, which extensions" from "how it is judged" across two rows an
    admin edits in two dialogs.
    """
    forbidden = (
        "service_job_photo_types",
        "attachment_validation_configs",
        "attachment_validations",
        "photo_types",
        "photo_validation_rules",
        "attachment_type_validations",
    )
    present = [name for name in forbidden if name in Base.metadata.tables]
    assert not present, (
        f"{present} exists. AC-M20 is explicit that attachment_types is already the "
        "per-type upload policy table and gains three columns instead."
    )


# ============================================================================
# 4. The prompt key collision
# ============================================================================


def test_the_existing_validator_prompt_key_still_means_the_answer_gate():
    """PROMPT_KEYS already has a key literally named `validator`, and it is the M3a
    answer confidence gate. The attachment validator must register its OWN key
    (`attachment_validator`), not reuse this one: activating M3a would otherwise put a
    photo-scoring instruction in front of the assistant's answer.
    """
    from app.services.ai_prompt_registry import PROMPT_KEYS

    spec = PROMPT_KEYS.get("validator")
    assert spec is not None
    role = (spec.role or "").lower()
    assert "answer" in role or "confidence" in role, (
        f"PROMPT_KEYS['validator'].role is now {spec.role!r}. That key is the M3a "
        "answer gate. The attachment validator has its own key, `attachment_validator`."
    )
    assert "attachment" not in role and "photo" not in role, (
        "The attachment validator has taken over the `validator` key. Two unrelated "
        "nodes now share one set of versions and one production label, so publishing "
        "either one silently republishes the other."
    )


# ============================================================================
# 5. The module boundary
# ============================================================================


def test_resources_does_not_grow_a_dependency_on_a_consuming_module_ac_m21():
    """AC-M21 puts the validator in `resources`, which is the module complaints, service
    jobs and the forms platform ALREADY depend on. `ai_prompt_registry` and
    `llm_provider` are plain services, not modules, so nothing about this slice changes
    the manifest. If `resources` ever declares complaints or service_jobs as a
    dependency the arrow has been drawn backwards and the install resolver has a cycle.
    """
    manifest = importlib.import_module("app.modules.resources.manifest")
    dependencies = set(getattr(manifest, "DEPENDENCIES", ()))
    forbidden = {"complaints", "service_jobs", "warranty", "consumers", "workflow_forms"}
    assert not (dependencies & forbidden), (
        f"resources now depends on {sorted(dependencies & forbidden)}. The validator "
        "is core-to-resources precisely so those modules can depend on IT."
    )


def test_the_validator_does_not_live_in_a_consuming_module_ac_m21():
    """One validator, in one place. A copy under service_jobs or complaints is how two
    photo types end up judged by two prompts nobody can compare - and it is the exact
    shape R5's grill moved away from when it took photo validation out of
    `service_jobs`.
    """
    strays = [
        path
        for path in (REPO / "app" / "services").rglob("*.py")
        if "attachment_valid" in path.name and path != VALIDATOR_PATH
    ]
    assert not strays, (
        f"A second attachment validator exists at {[str(p) for p in strays]}. AC-M21: "
        "it lives ONCE, in the resources module beside attachments."
    )
