"""Every stored spec rule becomes a builder; no stored rule keeps a pattern (#1286, S1).

Owner ruling, 26 Sep 2026 (Q5, Q6, PR #1290): rules are configured easily and
fool-proof, backed by a rule engine, and "if the rule engine is not simple enough to
cover, then the engine is the problem". A rule is now `{"builder": {...}}` - the picks a
person makes, one per part - and the engine compiles it at run time
(`app/services/product_spec_rules.py`, contract `CONTRACT-product-specs-rule-engine.md`).

For every row of `product_spec_registry`, each stored rule is converted:

  * a rule that already carries a new-style builder is kept as it is;
  * a shipped rule whose pattern was a regular expression is converted by its pattern,
    through `_FROZEN_PATTERNS` below (every such pattern the shipped list ever held);
  * every other rule is converted by its kind (`contains`, `ends_with`, the code kinds,
    `from_field`, `name_head`) or by the sentence builder it was made from.

Neighbouring Words rules with the same answer are then folded into one rule with several
words, the way the rules grid shows them.

A rule nothing can express STOPS the migration with an error naming the key and the rule,
rather than dropping it (AC-S1.3). A rule reading the removed Brand specification's field
(`from_field brand`) is dropped with a WARNING: brand is not a specification any more
(spec_0001).

Self-contained on purpose: the mapping is frozen here, because
`app.services.product_spec_rules` will keep changing after this ships and a migration must
convert the same way on every database, whenever it runs. `_clean` is a frozen copy of
`product_spec_rules.clean_builder` as of 26 Sep 2026; converted shipped rules therefore
compare equal (by builder) to the shipped list, which is how the seed repair recognises
them.

Idempotent: a rule that is already a builder is left as it is, so a second run changes
nothing.

Downgrade is a no-op: the old engine could run a builder only through the old sentence
compiler, which is gone, so there is nothing to convert back to. Restore from backup if
this ever has to be undone.

Revision ID: spec_0002_rule_builders
Revises: spec_0001_drop_brand
Create Date: 2026-09-26
"""

from __future__ import annotations

import json
import logging
import re

from alembic import op
from sqlalchemy import text

revision = "spec_0002_rule_builders"
down_revision = "spec_0001_drop_brand"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_KINDS = ("words", "number", "size", "code", "product")
_SEED = "_seed"

# The size regex every shipped size rule carried (`product_spec_derivation._DIM_RE`).
_SIZE_REGEX = (
    r"(?:[LWHDlwhd]\s*)?(\d+(?:\.\d+)?)\s*(?:MM|mm)?\s*[xX*]\s*(?:[LWHDlwhd]\s*)?"
    r"(\d+(?:\.\d+)?)\s*(?:MM|mm)?(?:\s*[xX*]\s*(?:[LWHDlwhd]\s*)?(\d+(?:\.\d+)?)\s*"
    r"(?:MM|mm)?)?(?:\s*[xX*]\s*(?:[LWHDlwhd]\s*)?(\d+(?:\.\d+)?)\s*(?:MM|mm)?)?"
)

# Every regular expression the shipped rules ever held, as the builder parts it means.
# Frozen from `tests/fixtures/legacy_shipped_rules.json` (26 Sep 2026). `value`,
# `look_in` and `only_when` come from the rule itself.
_FROZEN_PATTERNS: dict[str, dict] = {
    # Words, a flag or a picked value
    r"\bCHOPPING\s+BOARD\b": {"kind": "words", "words": ["CHOPPING BOARD"]},
    r"\bDISH\s+RACK\b": {"kind": "words", "words": ["DISH RACK"]},
    r"\bDIVERTER\b": {"kind": "words", "words": ["DIVERTER"]},
    r"DRAINER": {"kind": "words", "words": ["DRAINER"]},
    r"\bFILTER\s+TAP\b": {"kind": "words", "words": ["FILTER TAP"]},
    r"(?<!W/O )(?<!WITHOUT )SCREW": {
        "kind": "words",
        "words": ["SCREW"],
        "skip_after": ["W/O", "WITHOUT"],
    },
    r"\bLED\b": {"kind": "words", "words": ["LED"]},
    r"OVER\s*FLOW": {"kind": "words", "words": ["OVER FLOW"]},
    r"\bPULL[\s-]?OUT\s+SHOWER\b": {"kind": "words", "words": ["PULL OUT SHOWER"]},
    r"\bSHOWER\s+UNION\b": {"kind": "words", "words": ["SHOWER UNION"]},
    r"\bSLIDING\b": {"kind": "words", "words": ["SLIDING"]},
    r"\bFRAMELESS\b": {"kind": "words", "words": ["FRAMELESS"]},
    r"\bHIGH\s+BASIN\b": {"kind": "words", "words": ["HIGH BASIN"]},
    r"\bHONEYCOMB\b": {"kind": "words", "words": ["HONEYCOMB"]},
    r"\bRIMLESS\b": {"kind": "words", "words": ["RIMLESS"]},
    r"INTELLIGENT|AUTO\s*INDUCTION|SMART\s*(?:TOILET|WC)": {
        "kind": "words",
        "words": ["INTELLIGENT", "AUTO INDUCTION", "SMART TOILET", "SMART WC"],
    },
    r"\bSOFT[\s-]?CLOS(?:E|ING)\b": {"kind": "words", "words": ["SOFT CLOSE", "SOFT CLOSING"]},
    r"\bTHERMOSTATIC\b": {"kind": "words", "words": ["THERMOSTATIC"]},
    r"\bW/?O\s+OVERFLOW\b|\bWITHOUT\s+OVERFLOW\b": {
        "kind": "words",
        "words": ["W/O OVERFLOW", "WO OVERFLOW", "WITHOUT OVERFLOW"],
    },
    r"\bSINGLE\s+BOWLS?\b": {"kind": "words", "words": ["SINGLE BOWL", "SINGLE BOWLS"]},
    r"\bDOUBLE\s+BOWLS?\b": {"kind": "words", "words": ["DOUBLE BOWL", "DOUBLE BOWLS"]},
    r"\bTRIPLE\s+BOWLS?\b": {"kind": "words", "words": ["TRIPLE BOWL", "TRIPLE BOWLS"]},
    r"\bONE\s+BOWLS?\b": {"kind": "words", "words": ["ONE BOWL", "ONE BOWLS"]},
    r"\bTWO\s+BOWLS?\b": {"kind": "words", "words": ["TWO BOWL", "TWO BOWLS"]},
    r"\bTHREE\s+BOWLS?\b": {"kind": "words", "words": ["THREE BOWL", "THREE BOWLS"]},
    r"\bPP\b[^.]*SEAT": {"kind": "words", "words": ["PP ... SEAT"]},
    r"\bUF\b[^.]*SEAT": {"kind": "words", "words": ["UF ... SEAT"]},
    r"UREA[^.]*SEAT": {"kind": "words", "words": ["UREA ... SEAT"]},
    r"DUROPLAST": {"kind": "words", "words": ["DUROPLAST"]},
    # Numbers
    r"(?<!\d)(\d)\s*BOWLS?\b": {"kind": "number", "before": ["BOWL", "BOWLS"]},
    r"(?<![A-Z0-9])(?<![A-Z]-)(\d+(?:\.\d+)?)\s*(?:LITRES?|LITERS?|LTR|L)\b": {
        "kind": "number",
        "before": ["L", "LTR", "LITRE", "LITRES", "LITER", "LITERS"],
    },
    r"(?<![A-Z0-9])(\d+(?:\.\d+)?)\s*OZ\b": {"kind": "number", "before": ["OZ"]},
    r"\b(\d(?:\.\d)?)\s*M\b(?=[^A-Z]|$)": {"kind": "number", "before": ["M"]},
    r"\b(\d)\s*IN\s*1\b": {"kind": "number", "before": ["IN 1"]},
    r"(\d+(?:\.\d+)?)\s*HP\b": {"kind": "number", "before": ["HP"]},
    r"\b(\d)\s*-?\s*FUNCTIONS?\b": {"kind": "number", "before": ["FUNCTION", "FUNCTIONS"]},
    r"[SP]\s*-?\s*TRAP\s*[:,]?\s*(\d+(?:\.\d+)?)\s*MM": {
        "kind": "number",
        "after": ["S TRAP", "P TRAP"],
        "before": ["MM"],
    },
    r"\b(\d)\s*-?\s*WAYS?\b": {"kind": "number", "before": ["WAY", "WAYS"]},
    # The one size a row states when it does not state three, read off the description
    # with the trap span blanked: now "not below 10, never right after a trap".
    r"(?<![A-Z0-9X])(\d{2,4})\s*MM\b": {
        "kind": "number",
        "before": ["MM"],
        "ignore_below": 10,
        "skip_after": ["S TRAP", "P TRAP"],
    },
    # The flyer's labelled size rows
    r"L\s*(\d+(?:\.\d+)?)\s*[xX*]": {"kind": "size", "pick": "L"},
    r"W\s*(\d+(?:\.\d+)?)\s*[xX*]": {"kind": "size", "pick": "W"},
    r"H\s*(\d+(?:\.\d+)?)\s*(?:MM|mm)?": {"kind": "size", "pick": "H"},
}

_FIELD_TO_FACT = {
    "category": "class",
    "column:dimensions_length": "length",
    "column:dimensions_width": "width",
    "column:dimensions_height": "height",
}
_SOURCE_TO_LOOK_IN = {
    "description": "description",
    "flyer": "flyer",
    "class_tail": "name",
    "size_text": "description",
}
_SCALE_TO_UNIT = {10.0: "centimetres", 1000.0: "metres"}
_SPEAKABLE = re.compile(r"[A-Za-z0-9 &/'.\-]+")


class _Unconvertible(Exception):
    pass


class _Dropped(Exception):
    pass


# --------------------------------------------------------------------------- #
# frozen copy of product_spec_rules.clean_builder (26 Sep 2026)
# --------------------------------------------------------------------------- #
def _upper_list(raw) -> list[str]:
    out: list[str] = []
    if isinstance(raw, str):
        raw = [raw]
    for item in raw or []:
        word = " ".join(str(item or "").upper().split())
        if word and word not in out:
            out.append(word)
    return out


def _clean_number(raw):
    if raw is None or raw == "":
        return None
    value = float(raw)
    return int(value) if value.is_integer() else value


def _clean(builder: dict) -> dict:
    kind = builder.get("kind")
    out: dict = {"kind": kind}
    if kind in {"words", "number", "size"} and builder.get("look_in"):
        out["look_in"] = builder["look_in"]
    if kind == "words":
        out["words"] = _upper_list(builder.get("words"))
        if builder.get("at_end"):
            out["at_end"] = True
        skip = _upper_list(builder.get("skip_after"))
        if skip:
            out["skip_after"] = skip
        out["value"] = builder.get("value")
    elif kind == "number":
        for part in ("before", "after"):
            words = _upper_list(builder.get(part))
            if words:
                out[part] = words
        if builder.get("written_in"):
            out["written_in"] = builder["written_in"]
        floor = _clean_number(builder.get("ignore_below"))
        if floor is not None:
            out["ignore_below"] = floor
        skip = _upper_list(builder.get("skip_after"))
        if skip:
            out["skip_after"] = skip
    elif kind == "size":
        out["pick"] = builder.get("pick")
    elif kind == "code":
        out["code_match"] = builder.get("code_match")
        out["texts"] = _upper_list(builder.get("texts"))
        out["value"] = builder.get("value")
    elif kind == "product":
        out["fact"] = builder.get("fact")
    only_when = builder.get("only_when")
    if isinstance(only_when, dict) and only_when.get("spec"):
        out["only_when"] = {
            "spec": str(only_when["spec"]).strip(),
            "is": bool(only_when.get("is", True)),
            "values": [str(v).strip() for v in only_when.get("values") or [] if str(v).strip()],
        }
    return out


# --------------------------------------------------------------------------- #
# the conversion
# --------------------------------------------------------------------------- #
def _only_when(rule: dict) -> dict | None:
    gates = []
    for field, is_ in (("applies_when", True), ("unless", False)):
        for spec, values in (rule.get(field) or {}).items():
            values = [str(v) for v in values or [] if str(v).strip()]
            if values:
                gates.append({"spec": str(spec), "is": is_, "values": values})
    if len(gates) > 1:
        raise _Unconvertible("it has more than one condition, and a rule takes one")
    return gates[0] if gates else None


def _convert(rule: dict, spec_key: str) -> dict:
    """The builder one stored rule means. Raises _Unconvertible or _Dropped."""
    existing = rule.get("builder")
    if isinstance(existing, dict) and existing.get("kind") in _KINDS:
        return existing

    match = str(rule.get("match") or "contains").lower()
    pattern = str(rule.get("pattern") or "")
    source = str(rule.get("source") or "").lower()
    look_in = _SOURCE_TO_LOOK_IN.get(source) or ("name" if spec_key == "class" else "any")
    legacy = existing if isinstance(existing, dict) else {}
    legacy_kind = legacy.get("kind")
    value = rule.get("value")

    builder: dict | None = None
    if match == "from_field" and pattern == "brand":
        raise _Dropped("it read the product's brand field, which is not a specification")
    if match == "regex" and pattern == _SIZE_REGEX and rule.get("capture"):
        builder = {"kind": "size", "look_in": look_in, "pick": int(rule["capture"])}
    elif match in {"regex", "present"} and pattern in _FROZEN_PATTERNS:
        builder = {**_FROZEN_PATTERNS[pattern]}
        if builder["kind"] in {"words", "number", "size"}:
            builder["look_in"] = look_in
        if builder["kind"] == "words":
            builder["value"] = True if value is None and match == "present" else value
    elif match == "contains" and pattern:
        builder = {"kind": "words", "look_in": look_in, "words": [pattern], "value": value}
    elif match == "ends_with" and pattern:
        builder = {
            "kind": "words",
            "look_in": look_in,
            "words": [pattern],
            "at_end": True,
            "value": value,
        }
    elif match == "code_suffix" and pattern:
        builder = {
            "kind": "code",
            "code_match": "ends_with",
            "texts": [f"-{pattern.upper()}"],
            "value": value,
        }
    elif match in {"code_contains", "code_starts_with"} and pattern:
        builder = {
            "kind": "code",
            "code_match": "contains" if match == "code_contains" else "starts_with",
            "texts": [pattern],
            "value": value,
        }
    elif match == "from_field" and pattern in _FIELD_TO_FACT:
        builder = {"kind": "product", "fact": _FIELD_TO_FACT[pattern]}
    elif match == "name_head":
        builder = {"kind": "product", "fact": "name"}
    elif legacy_kind in {"number_before", "number_after"} and legacy.get("word"):
        part = "before" if legacy_kind == "number_before" else "after"
        builder = {"kind": "number", "look_in": look_in, part: [legacy["word"]]}
    elif legacy_kind == "number_between" and legacy.get("from") and legacy.get("to"):
        builder = {
            "kind": "number",
            "look_in": look_in,
            "after": [legacy["from"]],
            "before": [legacy["to"]],
        }
    elif legacy_kind == "size_triple":
        builder = {"kind": "size", "look_in": look_in, "pick": int(legacy.get("position") or 1)}
    elif legacy_kind in {"text_contains", "text_ends_with", "word_present"} and legacy.get("word"):
        builder = {
            "kind": "words",
            "look_in": look_in,
            "words": [legacy["word"]],
            "value": True if legacy_kind == "word_present" else value,
        }
        if legacy_kind == "text_ends_with":
            builder["at_end"] = True
    elif match == "present" and pattern and _SPEAKABLE.fullmatch(pattern):
        builder = {
            "kind": "words",
            "look_in": look_in,
            "words": [pattern],
            "value": True if value is None else value,
        }

    if builder is None:
        raise _Unconvertible("no kind of rule can express it")
    if builder["kind"] in {"words", "code"} and builder.get("value") is None:
        raise _Unconvertible("it sets no value")
    if rule.get("scale"):
        if builder["kind"] != "number":
            raise _Unconvertible("only a number can be written in another unit")
        unit = _SCALE_TO_UNIT.get(float(rule["scale"]))
        if unit is None:
            raise _Unconvertible(f"a scale of {rule['scale']} is not a unit")
        builder["written_in"] = unit
    only_when = _only_when(rule)
    if only_when:
        builder["only_when"] = only_when
    return _clean(builder)


def _fold_key(entry: dict) -> str | None:
    builder = entry["builder"]
    if builder.get("kind") != "words":
        return None
    rest = {k: v for k, v in builder.items() if k != "words"}
    return json.dumps([rest, bool(entry.get(_SEED))], sort_keys=True, default=str)


def _fold(entries: list[dict]) -> list[dict]:
    """Neighbouring Words rules with the same answer (and the same origin) become one."""
    folded: list[dict] = []
    for entry in entries:
        key = _fold_key(entry)
        if folded and key is not None and key == _fold_key(folded[-1]):
            merged = dict(folded[-1]["builder"])
            merged["words"] = _upper_list(list(merged["words"]) + list(entry["builder"]["words"]))
            folded[-1] = {**folded[-1], "builder": merged}
            continue
        folded.append(entry)
    return folded


def convert_rules(spec_key: str, rules: list) -> list[dict]:
    """A key's stored rules as builders, folded. Raises RuntimeError naming the rule."""
    converted: list[dict] = []
    for n, rule in enumerate(rules or [], start=1):
        if not isinstance(rule, dict):
            raise RuntimeError(
                f"spec_0002: rule {n} of {spec_key} is not a rule and cannot be converted: {rule!r}"
            )
        try:
            builder = _convert(rule, spec_key)
        except _Dropped as reason:
            logger.warning(
                "spec_0002: dropped rule %s of %s (%s): %s",
                n,
                spec_key,
                reason,
                json.dumps(rule, default=str, sort_keys=True),
            )
            continue
        except _Unconvertible as reason:
            raise RuntimeError(
                f"spec_0002: rule {n} of {spec_key} cannot be converted ({reason}): "
                f"{json.dumps(rule, default=str, sort_keys=True)}. Fix or remove it on the "
                "specification's screen, then run the migration again."
            ) from None
        entry: dict = {"builder": builder}
        if rule.get(_SEED):
            entry[_SEED] = True
        if not rule.get(_SEED) and rule.get("builder") is not builder:
            logger.warning(
                "spec_0002: %s rule %s %s -> %s",
                spec_key,
                n,
                json.dumps(rule, default=str, sort_keys=True),
                json.dumps(builder, default=str, sort_keys=True),
            )
        converted.append(entry)
    return _fold(converted)


# The three corrections the parity run found (#1286 fix round 1), frozen. Applied to a
# key's stored rules only where the shipped rule they correct is still there, carrying
# the seed's marker: a rule a person edited is theirs and is left alone.
_ROUND = {"spec": "shape", "is": False, "values": ["round", "square"]}
_OLD_HOSE = {"kind": "number", "look_in": "any", "before": ["M"], "written_in": "metres"}
_NEW_HOSE = {
    **_OLD_HOSE,
    "only_when": {
        "spec": "class",
        "is": False,
        "values": ["Bathtub", "Jacuzzi", "Bathtub and Jacuzzi"],
    },
}
_LONE_SIZE = {
    "kind": "number",
    "look_in": "description",
    "before": ["MM"],
    "ignore_below": 10,
    "skip_after": ["S TRAP", "P TRAP"],
    "only_when": _ROUND,
}
_LENGTH_WORD = {
    "kind": "number",
    "look_in": "description",
    "after": ["LENGTH"],
    "before": ["MM"],
    "only_when": _ROUND,
}
_BOWL_COUNT_CAP = 9


def _corrected(spec_key: str, rules: list[dict]) -> list[dict]:
    if spec_key == "hose_length":
        return [
            {"builder": _NEW_HOSE, _SEED: True}
            if rule.get(_SEED) and rule.get("builder") == _OLD_HOSE
            else rule
            for rule in rules
        ]
    if spec_key == "dim_length" and not any(r.get("builder") == _LENGTH_WORD for r in rules):
        for index, rule in enumerate(rules):
            if rule.get(_SEED) and rule.get("builder") == _LONE_SIZE:
                return (
                    rules[: index + 1]
                    + [{"builder": _LENGTH_WORD, _SEED: True}]
                    + rules[index + 1 :]
                )
    return rules


def upgrade() -> None:
    bind = op.get_bind()
    # A count has a ceiling: "6086 BOWL ONLY" is a model number. Set where no cap was
    # ever set - before this there was none to clear.
    capped = bind.execute(
        text(
            "UPDATE product_spec_registry SET max_value = :cap"
            " WHERE spec_key = 'bowl_count' AND max_value IS NULL RETURNING spec_key"
        ),
        {"cap": _BOWL_COUNT_CAP},
    ).all()
    if capped:
        logger.warning("spec_0002: bowl_count capped at %s", _BOWL_COUNT_CAP)
    rows = bind.execute(
        text(
            "SELECT spec_key, derivation_rules FROM product_spec_registry"
            " WHERE jsonb_typeof(derivation_rules) = 'array'"
            " AND jsonb_array_length(derivation_rules) > 0"
            " ORDER BY spec_key"
        )
    ).all()
    for spec_key, rules in rows:
        converted = _corrected(spec_key, convert_rules(spec_key, list(rules or [])))
        if converted == rules:
            continue
        bind.execute(
            text(
                "UPDATE product_spec_registry"
                " SET derivation_rules = CAST(:rules AS jsonb) WHERE spec_key = :key"
            ),
            {"rules": json.dumps(converted), "key": spec_key},
        )
        logger.warning(
            "spec_0002: %s rules converted to builders: %s before, %s after folding and corrections",
            spec_key,
            len(rules or []),
            len(converted),
        )


def downgrade() -> None:
    # No-op on purpose: see the module docstring.
    pass
