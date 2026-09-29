#!/usr/bin/env python3
"""Write the shared rule-compiler fixture both compilers are pinned to (#1286, AC-S1.1).

`app/services/product_spec_rules.compile_builder` (Python) and `compileBuilder` in the
frontend's `lib/ruleSentence.ts` (TypeScript) must compile every builder to the same
fields, or a rule saved from the screen is refused as a mismatch. This writes one entry,
`{"spec_key", "builder", "compiled"}`, per shipped rule plus a handful of the plan's
examples (D5) that the shipped list does not cover, with `compiled` produced by the
Python compiler. pytest (`tests/test_product_spec_rule_engine.py`) and vitest
(`lib/ruleSentence.compile.test.ts`) both assert their compiler reproduces it exactly.

Regenerate after any change to the compiler or the shipped rules, from
sorento_crm_backend/ (it only needs the settings to import, never the database):

    SORENTO_ENV_FILE=.env.ci-tests venv/bin/python -m scripts.generate_rule_builder_fixture

then commit the rewritten JSON with the change that caused it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "sorento_crm_frontend"
    / "app"
    / "(protected)"
    / "master-data-management"
    / "product-specifications"
    / "lib"
    / "__fixtures__"
    / "rule-builders.json"
)

# Plan D5 examples and edge shapes the shipped list does not hold.
EXAMPLES: list[tuple[str, dict]] = [
    (
        "finish",
        {
            "kind": "words",
            "look_in": "any",
            "words": ["GUNMETAL", "GUN METAL"],
            "value": "gunmetal",
        },
    ),
    (
        "finish",
        {"kind": "words", "look_in": "flyer", "words": ["BRUSHED GOLD"], "value": "french_gold"},
    ),
    ("is_soft_close", {"kind": "words", "words": ["SOFT-CLOSE"], "value": True}),
    (
        "material",
        {
            "kind": "words",
            "look_in": "description",
            "words": ["S/STEEL (304)", "SUS.304+"],
            "value": "stainless_steel",
        },
    ),
    ("dim_length", {"kind": "number", "look_in": "description", "after": ["LENGTH"]}),
    (
        "dim_length",
        {"kind": "number", "look_in": "any", "before": ["CM"], "written_in": "centimetres"},
    ),
    ("dim_width", {"kind": "size", "look_in": "any", "pick": 2}),
    (
        "finish",
        {
            "kind": "code",
            "code_match": "starts_with",
            "texts": ["SRTSC", "srtwc"],
            "value": "chrome",
        },
    ),
    ("finish", {"kind": "code", "code_match": "contains", "texts": ["-GM-"], "value": "gunmetal"}),
    (
        "diameter",
        {
            "kind": "size",
            "look_in": "description",
            "pick": 1,
            "only_when": {"spec": "shape", "is": True, "values": ["round", "square"]},
        },
    ),
    ("dim_width", {"kind": "product", "fact": "width"}),
]


def entries() -> list[dict]:
    from app.services.product_spec_registry import _rules_from_shipped_tables
    from app.services.product_spec_rules import compile_builder

    out: list[dict] = []
    for spec_key, rules in _rules_from_shipped_tables().items():
        for rule in rules:
            builder = rule["builder"]
            out.append(
                {"spec_key": spec_key, "builder": builder, "compiled": compile_builder(builder)}
            )
    for spec_key, builder in EXAMPLES:
        out.append({"spec_key": spec_key, "builder": builder, "compiled": compile_builder(builder)})
    return out


def main() -> None:
    data = entries()
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(data)} entries to {FIXTURE}")


if __name__ == "__main__":
    main()
