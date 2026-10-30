#!/usr/bin/env python3
"""Re-check the lookup meaning floors from CACHED vectors (zero API spend, no embed call anywhere).

LOOKUP-EMBED-CENTRAL AC-LEC-25. For every list it measures how well the meaning signal alone separates the right
row from the wrong ones at each floor in a sweep, and prints a per-list table (positives, negatives, precision /
recall at the current floor, the best floor that keeps precision >= 0.95 and its recall, decision).

Two sources of pairs, both scored with the live `list_resolver` spelling / partial machinery:

* gold (optional): a labelled message set (`--gold gold_all.jsonl` with `--rows lists.jsonl` and `--vec-store` of
  cached vectors). A positive is the gold span against the gold row, negatives are the top 3 wrong rows.
* fixture (`--fixture lookup_meaning_only_labels.json` + `--fixture-vectors ...npz`): the committed meaning-only
  label set. pos = the phrase names the gold row(s); neg = names no row of the list (counted as false positives);
  excluded = never scored.

mo = meaning-only pairs: spelling < the list's spell floor AND partial < its partial floor, i.e. the pairs the
meaning floor alone decides. Choice rule: the highest mo recall with mo precision >= 0.95 over the sweep (ties to the
higher floor); with fewer than --min-positives positives the current floor is kept.

Run from sorento_crm_backend/ (a dummy DATABASE_URL is enough, nothing connects):
  DATABASE_URL=postgresql://x:x@localhost/none DIRECT_URL=postgresql://x:x@localhost/none JWT_SECRET=dummy \\
  venv/bin/python scripts/eval/tune_lookup_floors.py --fixture tests/fixtures/lookup_meaning_only_labels.json \\
      --fixture-vectors tests/fixtures/lookup_meaning_only_vectors.npz --out scripts/eval/lookup_floors_report.md \\
      [--gold GOLD.jsonl --rows LISTS.jsonl --vec-store 'DIR/chunk_*.npz']
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.chatbot.head import candidates, list_resolver as lr  # noqa: E402
from app.services.chatbot.head.lookup_lists import LookupRow, _fold  # noqa: E402

MODEL = "gemini-embedding-001"
LISTS = ("category", "file_type", "brand", "sales_channel")
SWEEP = np.round(np.arange(0.55, 0.8501, 0.01), 2)


def unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / (np.linalg.norm(v) or 1.0)


def load_store(pattern: str) -> dict[str, np.ndarray]:
    store: dict[str, np.ndarray] = {}
    for f in sorted(glob.glob(pattern)):
        z = np.load(f, allow_pickle=True)
        for t, v in zip(z["texts"], z["vecs"]):
            store[str(t)] = unit(v)
    return store


def pairs_for(ln, span, rows, store, index, gold_keys=None, gold_texts=None, kind_none="ool"):
    """(kind, cos, spell, partial, row label) tuples for one phrase against one list's rows."""
    if span not in store:
        return None
    folded = _fold(span)
    scores = lr._score_list(index, folded, candidates.trigrams(folded)) if folded else {}
    per_row = []
    for i, row in enumerate(index.rows):
        vs = [store[t] for t in row.texts if t in store]
        if not vs:
            continue
        cos = max(float(store[span] @ v) for v in vs)
        s = scores.get(i)
        per_row.append((row, cos, s.spell if s else 0.0, s.partial if s else 0.0))
    if gold_keys is None and gold_texts is None:  # a phrase naming nothing: its top 3 rows are false positives
        return [dict(ln=ln, span=span, kind=kind_none, cos=c, spell=sp, part=pa, row=r.label)
                for r, c, sp, pa in sorted(per_row, key=lambda x: -x[1])[:3]]
    is_gold = (lambda r: r.key in gold_keys) if gold_keys is not None else (
        lambda r: bool({t.casefold() for t in r.texts} & gold_texts))
    pos = [x for x in per_row if is_gold(x[0])]
    if not pos:
        return []
    best = max(pos, key=lambda x: x[1])
    out = [dict(ln=ln, span=span, kind="pos", cos=best[1], spell=best[2], part=best[3], row=best[0].label)]
    for r, c, sp, pa in sorted([x for x in per_row if not is_gold(x[0])], key=lambda x: -x[1])[:3]:
        out.append(dict(ln=ln, span=span, kind="neg", cos=c, spell=sp, part=pa, row=r.label))
    return out


def fixture_decisions(doc, fstore, frows, fidx, ln, floor):
    """One decision per meaning-only phrase of the fixture: a phrase no row of the list reaches by spelling or
    partial, whose nearest row by meaning is at or above `floor`. Correct when the phrase is a positive and that
    row is one of its gold rows. Returns (decisions, correct, eligible_positives)."""
    fs = lr.FLOORS[ln]
    ix = fidx[ln]
    made = correct = eligible = 0
    wrong = []
    for e in doc["entries"]:
        if e["list"] != ln or e["kind"] == "excluded" or e["phrase"] not in fstore:
            continue
        p = e["phrase"]
        folded = _fold(p)
        sc = lr._score_list(ix, folded, candidates.trigrams(folded)) if folded else {}
        if any((sc[i].spell >= fs["spell"] or sc[i].partial >= fs["partial"]) for i in sc):
            continue  # spelling or partial decides this phrase, not the meaning floor
        if e["kind"] == "pos":
            eligible += 1
        best = None
        for r in ix.rows:
            vs = [fstore[t] for t in r.texts if t in fstore]
            if vs:
                cos = max(float(fstore[p] @ v) for v in vs)
                if best is None or cos > best[0]:
                    best = (cos, r)
        if best is None or best[0] < floor:
            continue
        made += 1
        gold = {t.casefold() for t in e.get("gold", [])}
        if e["kind"] == "pos" and gold & {t.casefold() for t in best[1].texts}:
            correct += 1
        else:
            wrong.append((p, best[1].label, round(best[0], 2)))
    return made, correct, eligible, wrong


def stats(ps, floor):
    tp = sum(p["kind"] == "pos" and p["cos"] >= floor for p in ps)
    fp = sum(p["kind"] in ("neg", "ool") and p["cos"] >= floor for p in ps)
    npos = sum(p["kind"] == "pos" for p in ps)
    return (tp / (tp + fp) if tp + fp else float("nan")), (tp / npos if npos else float("nan")), tp, fp


def f2(x):
    return "n/a" if x != x else f"{x:.2f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixture")
    ap.add_argument("--fixture-vectors")
    ap.add_argument("--gold")
    ap.add_argument("--rows", help="lists.jsonl of the gold run (list,row_id,label,texts)")
    ap.add_argument("--vec-store", help="glob of cached vector chunks (arrays texts, vecs)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-positives", type=int, default=15)
    args = ap.parse_args()

    cur = lr.MEANING_FLOORS_BY_MODEL[MODEL]
    pairs: list[dict] = []
    skipped = collections.Counter()

    if args.gold:
        store = load_store(args.vec_store)
        raw = [json.loads(line) for line in open(args.rows)]
        grows = [LookupRow(r["list"], str(r["row_id"]), r["label"], tuple(r["texts"])) for r in raw if r["list"] in LISTS]
        gidx = lr._prepare(grows)
        seen = set()
        for g in (json.loads(line) for line in open(args.gold)):
            for m in g["mentions"]:
                ln = m["type"]
                if ln not in LISTS:
                    continue
                key = (ln, m["span"], frozenset(map(str, m["row_ids"])), bool(m["in_list"]))
                if key in seen:
                    continue
                seen.add(key)
                got = pairs_for(ln, m["span"], grows, store, gidx[ln],
                                gold_keys=set(map(str, m["row_ids"])) if m["in_list"] else None)
                if got is None:
                    skipped[(ln, "no vector")] += 1
                    continue
                for p in got:
                    p["src"] = "gold"
                pairs += got

    fixture_pairs: list[dict] = []
    if args.fixture:
        doc = json.load(open(args.fixture))
        z = np.load(args.fixture_vectors, allow_pickle=True)
        fstore = {str(t): unit(v) for t, v in zip(z["texts"], z["vecs"])}
        frows = [LookupRow(r["list"], r["key"], r["label"], tuple(r["texts"])) for r in doc["rows"]]
        fidx = lr._prepare(frows)
        for e in doc["entries"]:
            if e["kind"] == "excluded":
                continue
            ln = e["list"]
            lrows = [r for r in frows if r.list_name == ln]
            if e["kind"] == "pos":
                got = pairs_for(ln, e["phrase"], lrows, fstore, fidx[ln], gold_texts={t.casefold() for t in e["gold"]})
            else:
                got = pairs_for(ln, e["phrase"], lrows, fstore, fidx[ln])
            if got is None:
                skipped[(ln, "fixture no vector")] += 1
                continue
            for p in got:
                p["src"] = "fixture"
            fixture_pairs += got
        pairs += fixture_pairs

    md = []
    sweep_rows = []
    for ln in LISTS:
        ps = [p for p in pairs if p["ln"] == ln]
        floors = lr.FLOORS[ln]
        for p in ps:
            p["mo"] = p["spell"] < floors["spell"] and p["part"] < floors["partial"]
        mo = [p for p in ps if p["mo"]]
        fx = [p for p in mo if p["src"] == "fixture"]
        npos = sum(p["kind"] == "pos" for p in ps)
        nneg = sum(p["kind"] in ("neg", "ool") for p in ps)
        nmo = sum(p["kind"] == "pos" for p in mo)
        c = cur[ln]
        best = None
        for f in SWEEP:
            P, R, tp, fp = stats(mo, f)
            if tp and P >= 0.95 and (best is None or R > best[1] or (R == best[1] and f > best[0])):
                best = (float(f), R)
        notes = []
        if npos < args.min_positives:
            chosen = c
            notes.append(f"{npos} positives (< {args.min_positives}): current floor kept")
        elif best is None:
            chosen = c
            notes.append("no floor reaches mo precision 0.95 with a rescue: current kept")
        else:
            chosen = best[0]
        Pa, Ra, *_ = stats(ps, c)
        Pm, Rm, tpm, fpm = stats(mo, c)
        Pf, Rf, tpf, fpf = stats(fx, c)
        Pn, Rn, tpn, fpn = stats(mo, chosen)
        md.append(
            f"| {ln} | {npos} ({nmo} mo) | {nneg} | {c:.2f} | {f2(Pa)} / {f2(Ra)} | mo {f2(Pm)} / {f2(Rm)} (tp {tpm}, fp {fpm}); fixture mo {f2(Pf)} / {f2(Rf)} (tp {tpf}, fp {fpf}) "
            f"| {f2(best[0]) if best else 'none'} / {f2(best[1]) if best else 'n/a'} | strict bound only; decided on the fixture decisions below |"
        )
        for f in SWEEP:
            a = stats(ps, f)
            b = stats(mo, f)
            sweep_rows.append(f"{ln},{f},{f2(a[0])},{f2(a[1])},{f2(b[0])},{f2(b[1])},{b[2]},{b[3]}")

    dec_md = []
    if args.fixture:
        for ln in LISTS:
            c = cur[ln]
            made, ok, elig, wrong = fixture_decisions(doc, fstore, frows, fidx, ln, c)
            best = None
            for f in SWEEP:
                m, k, _e, _w = fixture_decisions(doc, fstore, frows, fidx, ln, f)
                if m and k / m >= 0.95 and (best is None or k > best[1] or (k == best[1] and f > best[0])):
                    best = (float(f), k, m)
            line = f"| {ln} | {elig} | {made} | {ok} | {f2(ok / made) if made else 'n/a'} | {f2(ok / elig) if elig else 'n/a'} | "
            line += (f"{best[0]:.2f}: {best[1]} of {best[2]} right, recall {best[1] / elig:.2f}" if best else "none") + " | "
            if made < 10:
                line += f"{made} decisions: too few to move a floor, KEEP {c:.2f}"
            elif made and ok / made >= 0.95:
                line += f"KEEP {c:.2f} (precision {ok / made:.2f} >= 0.95)"
            else:
                line += f"precision {f2(ok / made)} at {c:.2f} is under 0.95; " + (f"{best[0]:.2f} reaches it: owner decides" if best else "no floor reaches it")
            line += " | " + ("; ".join(f"{a} -> {b} ({d})" for a, b, d in wrong) or "none") + " |"
            dec_md.append(line)

    counts = collections.Counter((p["ln"], p["src"], p["kind"]) for p in pairs)
    doc_lines = [
        "# Lookup meaning floors, gemini-embedding-001 (cached vectors, zero API spend)", "",
        "mo = meaning-only pairs (spelling < spell floor and partial < partial floor, `list_resolver.FLOORS`). "
        "Precision counts wrong rows and phrases that name nothing in the list as false positives. "
        "Best floor = highest mo recall with mo precision >= 0.95 over the 0.55..0.85 sweep.", "",
        "| list | positives (meaning-only) | negatives | current floor | P / R all pairs at current | P / R meaning-only at current | best floor with mo P >= 0.95 / recall | decision |",
        "|---|---|---|---|---|---|---|---|", *md, "",
        "## Fixture decisions (the pinned metric)", "",
        "One decision per meaning-only phrase (no row reaches it by spelling or partial; the nearest row by meaning is at or above the floor). Correct = a positive phrase whose nearest row is one of its gold rows; a negative phrase that gets a row, or a wrong row, is a false positive.", "",
        "| list | meaning-only positives | decisions at current | right | precision | recall | best floor with precision >= 0.95 | decision | wrong decisions at current |",
        "|---|---|---|---|---|---|---|---|---|", *dec_md, "",
        "## Pair metric (gold messages + fixture)", "",
        "(wrong rows of a positive phrase count as false positives, so this is the strict bound)", "",
        "Pair counts (list, source, kind): " + "; ".join(f"{k[0]}/{k[1]}/{k[2]} {v}" for k, v in sorted(counts.items())), "",
        "Skipped for missing vectors: " + ("; ".join(f"{k[0]}/{k[1]}: {v}" for k, v in sorted(skipped.items())) or "none"), "",
        "Sweep (list,floor,P_all,R_all,P_mo,R_mo,tp_mo,fp_mo):", "```", "list,floor,P_all,R_all,P_mo,R_mo,tp_mo,fp_mo", *sweep_rows, "```",
    ]
    open(args.out, "w").write("\n".join(doc_lines) + "\n")
    print("\n".join(doc_lines[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
