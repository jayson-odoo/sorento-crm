"""Offline eval of the list resolver (ENTITY-EXTRACT-MATCH S1): spans in, rows out, scored against a gold file.

usage (cwd = the backend dir of the checkout under test):
  python -m scripts.chatbot_eval.span_resolve --lists F --gold F [--spans F] [--vectors DIR] [--half calib|test|all]

--lists    jsonl {list, row_id, label, texts}: the rows the resolver sees
--gold     jsonl {mid, mentions: [{span, type, row_ids, in_list, ...}]}: the labelled mentions
--spans    optional extractor run jsonl {mid, spans: [{text, type}]}: scores the right row end to end
--vectors  optional dir holding vecs.npy + index.json (vector store keyed sha1(model + NUL + text)): the
           meaning signal, read offline; without it the resolver is spelling and partial names only
--half     the gold messages whose sha1(mid) is even (calib), odd (test), or all

`oracle` resolves each gold mention's own span with its gold type (what the resolver can reach with a perfect
extractor); `right` resolves the extractor's spans and counts a gold mention right when a span covering it
resolved to one of its rows. A gold mention's row_ids are the rows that are acceptable answers, so an
`ambiguous` span whose candidates hold one of them counts right (as in the phase-1 numbers); the strict line
counts `resolved` only.
No DB, no network: this module imports only the stdlib, numpy (with --vectors) and the resolver. Importing the
resolver loads the app package, which needs DATABASE_URL and JWT_SECRET set in the environment (any value
will do, e.g. SORENTO_ENV_FILE=.env.ci-tests); it never opens a connection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

VECTOR_MODEL = "text-embedding-3-small"
_WORD = re.compile(r"\w+")


def _norm(text: str) -> str:
    return " ".join(_WORD.findall(str(text).casefold()))


def _covers(gold_span: str, span: str) -> bool:
    """Same words, one inside the other, or at least half the words shared."""
    a, b = _norm(gold_span), _norm(span)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    wa, wb = set(a.split()), set(b.split())
    return len(wa & wb) / len(wa | wb) >= 0.5


def _jsonl(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _in_half(mid: str, half: str) -> bool:
    if half == "all":
        return True
    return int(hashlib.sha1(mid.encode()).hexdigest(), 16) % 2 == (1 if half == "test" else 0)


def _offline_embedder(directory: str):
    """Vectors from a vector store dir; a text it does not hold is a zero vector (meaning 0.0)."""
    import numpy as np

    base = Path(directory)
    index = json.loads((base / "index.json").read_text())
    mat = np.load(base / "vecs.npy", mmap_mode="r")

    def embed(texts):
        out = np.zeros((len(texts), mat.shape[1]), dtype=np.float32)
        for i, t in enumerate(texts):
            j = index.get(hashlib.sha1((VECTOR_MODEL + "\x00" + t).encode()).hexdigest())
            if j is not None:
                out[i] = mat[j]
        return out

    return embed


def _hit(res: Any, row_ids: set[str], strict: bool = False) -> bool:
    """The resolution holds an acceptable row: resolved to one, or (not strict) ambiguous among rows holding one."""
    if res.status == "resolved":
        return res.candidates[0].row.key in row_ids
    return not strict and res.status == "ambiguous" and any(c.row.key in row_ids for c in res.candidates)


def _table(title: str, counts: dict[str, list[int]]) -> list[str]:
    lines = [f"{title}: type  hits/n"]
    for t in sorted(counts):
        n, ok = counts[t]
        lines.append(f"  {t:<16} {ok}/{n}")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Offline eval of the list resolver")
    ap.add_argument("--lists", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--spans")
    ap.add_argument("--vectors")
    ap.add_argument("--half", default="all", choices=("calib", "test", "all"))
    args = ap.parse_args(argv)

    from app.services.chatbot.head import list_resolver
    from app.services.chatbot.head.lookup_lists import LookupRow

    rows = [LookupRow(r["list"], str(r["row_id"]), r["label"], tuple(r["texts"])) for r in _jsonl(args.lists)]
    gold = {g["mid"]: g for g in _jsonl(args.gold) if _in_half(g["mid"], args.half)}
    embed = _offline_embedder(args.vectors) if args.vectors else None

    def usable(m: dict[str, Any]) -> bool:
        return bool(m.get("in_list")) and m.get("type") in list_resolver.SPAN_TYPES and m["type"] != "product_code"

    items = [(mid, m) for mid, g in gold.items() for m in g.get("mentions") or [] if usable(m)]
    oracle = list_resolver.resolve([list_resolver.Span(m["span"], m["type"]) for _, m in items], rows, embed=embed)
    by_type: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    ok = strict = 0
    for (_mid, m), res in zip(items, oracle):
        by_type[m["type"]][0] += 1
        right = _hit(res, set(m["row_ids"]))
        by_type[m["type"]][1] += right
        ok += right
        strict += _hit(res, set(m["row_ids"]), strict=True)
    lines = [f"oracle {ok}/{len(items)} ({100.0 * ok / len(items):.1f}%)" if items else "oracle 0/0",
             f"oracle strict (resolved only): {strict}/{len(items)}"]
    lines += _table("oracle per type", by_type)

    if args.spans:
        runs = {r["mid"]: r for r in _jsonl(args.spans)}
        flat = [(mid, s) for mid in gold for s in (runs.get(mid) or {}).get("spans") or []]
        results = list_resolver.resolve([list_resolver.Span(s["text"], s.get("type")) for _, s in flat], rows, embed=embed)
        resolved: dict[str, list[tuple[str, Any]]] = defaultdict(list)
        for (mid, s), res in zip(flat, results):
            resolved[mid].append((s["text"], res))
        by_type = defaultdict(lambda: [0, 0])
        right_n = strict_n = 0
        for mid, m in items:
            by_type[m["type"]][0] += 1
            hits = [res for text, res in resolved[mid] if _covers(m["span"], text)]
            good = any(_hit(r, set(m["row_ids"])) for r in hits)
            by_type[m["type"]][1] += good
            right_n += good
            strict_n += any(_hit(r, set(m["row_ids"]), strict=True) for r in hits)
        lines.append(f"right {right_n}/{len(items)} ({100.0 * right_n / len(items):.1f}%)" if items else "right 0/0")
        lines.append(f"right strict (resolved only): {strict_n}/{len(items)}")
        lines += _table("extractor spans per type", by_type)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
