"""Diff a current snapshot against the blessed baseline, human-readable.

This is a report, not a test: it informs, it does not gate, unless ``--strict`` is passed
(then a CHANGED/NEW/GONE scenario exits 1 - useful for a pre-merge sanity check, still never
a pytest assertion).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from scripts.scm_sim.snapshot import META_KEY

#: Field-path substrings -> a human group label for the report. Checked in order; the
#: first match wins. Purely cosmetic (grouping a long diff so it is skimmable) - never
#: changes what is compared.
_GROUPS: list[tuple[str, str]] = [
    ("price_history", "price advice"),
    ("level_suggestion", "level suggestion"),
    ("trajectory", "level suggestion"),
    ("recommendations.*.recommended_qty", "quantity suggestion"),
    ("recommendations.*.rounded_qty", "quantity suggestion"),
    ("recommendations.*.rec_type", "quantity suggestion"),
    ("recommendations.*.disposition", "disposition"),
    ("recommendations.*.triggered_reason", "quantity suggestion"),
    ("po_book", "cover composition"),
    ("net_position", "cover composition"),
    ("inputs.on_order", "cover composition"),
    ("inputs.po_ordered", "cover composition"),
    ("inputs.covered_", "cover composition"),
    ("disposition", "disposition"),
    ("order_summary_row", "order summary"),
    ("reorder_level", "level suggestion"),
]


def load_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"[scm_sim] {path} does not exist yet.")
    return json.loads(path.read_text())


def _group_for(path: str) -> str:
    for needle, label in _GROUPS:
        prefix = needle.split(".*.")[0]
        if needle in path or path.startswith(prefix):
            return label
    return "other"


def _walk_diff(old: Any, new: Any, prefix: str = "") -> Iterable[tuple[str, Any, Any]]:
    """Yield ``(dotted.path, old_value, new_value)`` for every leaf that differs.

    Lists are compared index-by-index (recommendations lists are already sorted by
    ``rec_type`` at write time, so this is stable rather than order-noisy).
    """
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            path = f"{prefix}.{key}" if prefix else key
            if key not in old:
                yield path, None, new[key]
            elif key not in new:
                yield path, old[key], None
            else:
                yield from _walk_diff(old[key], new[key], path)
    elif isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            yield f"{prefix}[]", old, new
            return
        for i, (o, n) in enumerate(zip(old, new)):
            yield from _walk_diff(o, n, f"{prefix}[{i}]")
    else:
        if old != new:
            yield prefix, old, new


def compare(baseline_path: Path, current_path: Path, *, strict: bool = False) -> int:
    baseline = load_json(baseline_path)
    current = load_json(current_path)

    # Run-level facts (currently just the planning mode the run executed under, S2)
    # live under a reserved key, never walked as a 39th "scenario" - popped off first so
    # a mode flip gets its own explicit META line instead of a scenario-shaped diff.
    baseline_meta = baseline.pop(META_KEY, None)
    current_meta = current.pop(META_KEY, None)
    meta_diffs = list(_walk_diff(baseline_meta or {}, current_meta or {}))

    codes = sorted(set(baseline) | set(current))
    same, changed, new, gone = [], [], [], []
    per_scenario_diffs: dict[str, list[tuple[str, Any, Any]]] = {}

    for code in codes:
        if code not in baseline:
            new.append(code)
            continue
        if code not in current:
            gone.append(code)
            continue
        diffs = list(_walk_diff(baseline[code], current[code]))
        if diffs:
            changed.append(code)
            per_scenario_diffs[code] = diffs
        else:
            same.append(code)

    print("=== scm_sim compare ===")
    print(f"  baseline: {baseline_path}")
    print(f"  current:  {current_path}")
    print(f"  {len(same)} same, {len(changed)} changed, {len(new)} new, {len(gone)} gone\n")

    if meta_diffs:
        print("META     run metadata changed (a mode flip shows here, never inside a "
              "scenario diff):")
        for path, old_v, new_v in meta_diffs:
            print(f"  {path}: {old_v!r} -> {new_v!r}")
        print()

    for code in new:
        print(f"NEW      {code}  ({current[code].get('title', '')})")
    for code in gone:
        print(f"GONE     {code}  ({baseline[code].get('title', '')})")
    for code in changed:
        title = current.get(code, baseline.get(code, {})).get("title", "")
        print(f"CHANGED  {code}  ({title})")
        grouped: dict[str, list[tuple[str, Any, Any]]] = {}
        for path, old_v, new_v in per_scenario_diffs[code]:
            grouped.setdefault(_group_for(path), []).append((path, old_v, new_v))
        for group in sorted(grouped):
            print(f"    [{group}]")
            for path, old_v, new_v in grouped[group]:
                print(f"      {path}: {old_v!r} -> {new_v!r}")
        print()

    if not changed and not new and not gone and not meta_diffs:
        print("All scenarios SAME.")

    if strict and (changed or new or gone or meta_diffs):
        return 1
    return 0
