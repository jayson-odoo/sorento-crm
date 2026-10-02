"""A parser prompt version IDENTICAL in rendered output to an existing one, with registry
variables wherever that version hard-codes a registry list EXACTLY (owner hand test #1405,
item 3). Every list whose registry differs today stays literal and is reported.

Dry run by default: prints the report and the identity check, writes nothing.
`--save` inserts the result as ONE new UNLABELLED version, only if its rendered output is
byte-identical to the source; it never labels, publishes or stages.

    venv/bin/python -m scripts.prompt_dynamic_identical_version --from-version 53
    venv/bin/python -m scripts.prompt_dynamic_identical_version --from-version 53 --save
    venv/bin/python -m scripts.prompt_dynamic_identical_version --verify 55

    venv/bin/python -m scripts.prompt_dynamic_identical_version --verify 57 --against 56

`--verify N` renders version N the way a turn does and compares it with the owner's
production file (`alembic/data/chatbot_semantic_parser.prod-20261001.txt`), printing the
first differing line when they part. `--against M` compares with version M rendered the
same way instead (owner Q-A = (a): the rebuild of his edited plain-text version is checked
against that version, so his edits are not differences). Read-only.

Omit --from-version to start from the `production` version.
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys

PROMPT_NAME = "chatbot_semantic_parser"


def build(db, *, from_version: int | None = None, save: bool = False) -> dict:
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
    from app.services import chatbot_prompt_vars as pv
    from app.services.ai_prompt_registry import _substitute, extract_tokens

    query = db.query(AIPromptVersion).filter(AIPromptVersion.name == PROMPT_NAME)
    if from_version is None:
        source = (
            query.join(AIPromptLabel, AIPromptLabel.version_id == AIPromptVersion.id)
            .filter(AIPromptLabel.label == "production")
            .one()
        )
    else:
        source = query.filter(AIPromptVersion.version == from_version).one()

    # Render the SOURCE the way a turn does too: a source that already uses variables
    # (a wording layer) is compared on its rendered text.
    def rendered(template: str) -> str:
        values = {n: pv.render_value(db, n) for n in extract_tokens(template) & set(pv.VARIABLE_NAMES)}
        return _substitute(template, values)

    before = rendered(source.template)
    template, report = pv.identical_wording_layer(source.template, db)
    after = rendered(template)
    result = {
        "from_version": source.version,
        "identical": before == after,
        "diff": "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), n=1)),
        "report": report,
        "template": template,
        "saved_version": None,
    }
    if not save:
        return result
    if not result["identical"]:
        raise SystemExit("refused: the rendered output differs from the source; nothing saved")
    existing = query.filter(AIPromptVersion.template == template).order_by(AIPromptVersion.version.desc()).first()
    if existing is not None:
        result["saved_version"] = existing.version
        return result
    top = max((v.version for v in query.all()), default=0)
    replaced = sorted({r["variable"] for r in report if r["action"] == "replaced"})
    row = AIPromptVersion(
        name=PROMPT_NAME,
        version=top + 1,
        type="text",
        template=template,
        variables=list(source.variables or []),
        config_json={"identical_to_version": source.version, "identical_report": report},
        commit_message=(
            f"Same rendered prompt as v{source.version}, with registry variables where its "
            f"lists match the registries exactly ({', '.join(replaced) or 'none'}). "
            "Unlabelled: promote only after review."
        ),
    )
    db.add(row)
    db.flush()
    result["saved_version"] = row.version
    return result


def verify(db, version: int, snapshot=None, *, against_version: int | None = None) -> dict:
    """Render version `version` (a fixed date for `{{current_date}}`) and compare it with the
    owner's file, or with version `against_version`, rendered with the same date."""
    from app.models.ai_prompt import AIPromptVersion
    from app.services import ai_prompt_registry

    def rendered(v: int) -> str:
        row = db.query(AIPromptVersion).filter(AIPromptVersion.name == PROMPT_NAME, AIPromptVersion.version == v).one()
        out, _ = ai_prompt_registry.render(db, PROMPT_NAME, current_date="D", override_version_id=row.id)
        return out

    out = rendered(version)
    if against_version is not None:
        want, against = rendered(against_version), f"v{against_version}"
    else:
        want, against = snapshot.read_text(encoding="utf-8").replace("{{current_date}}", "D"), snapshot.name
    if out == want:
        return {"version": version, "against": against, "equal": True, "first_difference": None,
                "chars": (len(out), len(want))}
    a, b = out.splitlines(), want.splitlines()
    i = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return {
        "version": version,
        "against": against,
        "equal": False,
        "first_difference": {
            "line": i + 1,
            "rendered": a[i] if i < len(a) else "<end>",
            "file": b[i] if i < len(b) else "<end>",
        },
        "chars": (len(out), len(want)),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-version", type=int, default=None)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--verify", type=int, default=None, metavar="N")
    parser.add_argument("--against", type=int, default=None, metavar="M")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()

    import pathlib

    import app.main  # noqa: F401  registers every model
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        if args.verify is not None:
            snapshot = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "data" / "chatbot_semantic_parser.prod-20261001.txt"
            v = verify(db, args.verify, snapshot, against_version=args.against)
            print(f"# v{v['version']} rendered == {v['against']}: {v['equal']} ({v['chars'][0]} vs {v['chars'][1]} chars)")
            if v["first_difference"]:
                d = v["first_difference"]
                print(f"    first difference at line {d['line']}:\n    rendered:  {d['rendered']!r}\n    reference: {d['file']!r}")
            return 0 if v["equal"] else 1
        result = build(db, from_version=args.from_version, save=args.save)
        if args.save:
            db.commit()
        print(f"# source v{result['from_version']}; rendered output identical: {result['identical']}")
        if result["diff"]:
            print(result["diff"])
        for row in result["report"]:
            line = f"line {row['line']}" if row.get("line") else "not found"
            print(f"- {{{{{row['variable']}}}}} ({line}): {row['action']}")
            if row["action"] == "kept literal":
                if row.get("order_or_format_only"):
                    print("    same items, different order or format")
                if row.get("only_in_text"):
                    print(f"    only in the prompt text: {json.dumps(row['only_in_text'], ensure_ascii=False)}")
                if row.get("only_in_registry"):
                    print(f"    only in the registry:    {json.dumps(row['only_in_registry'], ensure_ascii=False)}")
                d = row.get("first_difference")
                if d:
                    print(f"    first difference, item {d['item']}: text {d['text']!r} | registry {d['registry']!r}")
        if args.save:
            print(f"# saved as v{result['saved_version']} (unlabelled)")
        return 0 if result["identical"] else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
