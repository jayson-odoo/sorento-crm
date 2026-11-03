"""SUPPLIER-ASK: measure the supplier list's meaning floor on real supplier rows (owner ruling, 1 Nov 2026).

The supplier span list matches by meaning like the customer list, but its floor must be measured, not copied. This
scores test phrases against the active supplier rows with the embedder the chatbot uses (`lookup_lists.embedder`,
the dev config's Gemini model) and prints, per phrase, the best rows by cosine and whether the expected supplier is
the hit at each candidate floor, then a hit / miss / false-positive count per floor.

Only the test phrases are embedded. The supplier row vectors are read from the lookup word store
(`embedding_chunks`, source `lookup_word`); a row text with no stored vector is listed and skipped, unless
`--embed-missing` is given, which runs `lookup_word_store.sync_lookup_words` once to embed and store them (what the
backend's start-up warm does after deploy).

Run from `sorento_crm_backend/` with the dev copy's env:

    venv/bin/python -m scripts.measure_supplier_span_floor
    venv/bin/python -m scripts.measure_supplier_span_floor --phrase "pembekal taiyang=400-X001,400-X006,400-X008"

A phrase's expectation is a comma list of supplier codes (any of them is a hit) or `-` (it must match no supplier).
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

#: (phrase, expected supplier codes or empty for "no supplier"). The owner's message and the console pass 2 forms.
TAIYANG = "400-X001,400-X006,400-X008"
DEFAULT_PHRASES: list[tuple[str, str]] = [
    ("太阳", TAIYANG),
    ("tai yang", TAIYANG),
    ("Taiyang", TAIYANG),
    ("taiyang", TAIYANG),
    ("Taiyan", TAIYANG),
    ("taiyng", TAIYANG),
    ("pembekal taiyang", TAIYANG),
    ("taiyang punya PO", TAIYANG),
    ("400-X008", "400-X008"),
    ("basin", "-"),
    ("water closet", "-"),
    ("stock", "-"),
    ("outstanding", "-"),
    ("sorento", "-"),
]
FLOORS = (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85)


def _parse_phrase(raw: str) -> tuple[str, str]:
    phrase, _, expected = raw.rpartition("=")
    if not phrase:
        raise SystemExit(f"--phrase needs 'text=CODES' or 'text=-': {raw!r}")
    return phrase.strip(), expected.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phrase", action="append", default=[], help="'text=CODE,CODE' or 'text=-'; repeatable")
    parser.add_argument("--only", action="store_true", help="score only the --phrase values, not the default list")
    parser.add_argument("--embed-missing", action="store_true", help="embed and store supplier rows with no vector")
    parser.add_argument("--top", type=int, default=3)
    args = parser.parse_args(argv)
    phrases = ([] if args.only else list(DEFAULT_PHRASES)) + [_parse_phrase(p) for p in args.phrase]

    from app.database import SessionLocal
    from app.models.base import set_company_scope
    from app.models.procurement import Supplier
    from app.services.chatbot.head import list_resolver
    from app.services.chatbot.head import lookup_lists as ll
    from app.services.chatbot.head import lookup_word_store

    db = SessionLocal()
    set_company_scope(db, None)
    try:
        embed = ll.embedder(db)
        if embed is None:
            print("No embedder configured (no key for the chatbot lookup embedder).", file=sys.stderr)
            return 2
        model = getattr(embed, "model", "?")
        rows = [r for r in ll.load_rows(db, include_suppliers=True) if r.list_name == "supplier"]
        codes = {str(sid): code for sid, code in db.query(Supplier.id, Supplier.supplier_code).all()}
        texts = ll.row_texts(rows)
        if args.embed_missing:
            result = lookup_word_store.sync_lookup_words(db, model=model)
            db.commit()
            print(f"sync_lookup_words: {result}")
        loaded = lookup_word_store.load_lookup_vectors(db, model, only=texts)
        missing = [t for t in texts if ll._key(t, model) not in ll._cache]
        print(f"model {model}: {len(rows)} active suppliers, {len(texts)} row texts, {loaded} stored vectors loaded, "
              f"{len(missing)} without a vector{' (skipped; --embed-missing embeds them)' if missing else ''}")
        usable = [t for t in texts if t not in set(missing)]
        row_vec = {t: ll._cache[ll._key(t, model)] for t in usable}
        phrase_vecs = ll._unit_rows(np.asarray(embed([p for p, _ in phrases]), dtype=np.float32))
        floor_now = list_resolver._meaning_floor(embed, "supplier")
        print(f"current supplier meaning floor for this model: {floor_now}; runner-up margin "
              f"{list_resolver.AMBIGUITY_MARGIN}\n")

        tally = {f: {"hit": 0, "ambiguous_hit": 0, "miss": 0, "false_positive": 0, "clean": 0} for f in FLOORS}
        print("| phrase | expected | best rows (code cosine) | expected rank | " + " | ".join(f"{f:.2f}" for f in FLOORS) + " |")
        print("|---" * (4 + len(FLOORS)) + "|")
        for (phrase, expected), qv in zip(phrases, phrase_vecs):
            scored = sorted(
                (
                    (max(float(np.dot(qv, row_vec[t])) for t in r.texts if t in row_vec), codes.get(str(r.key), r.key))
                    for r in rows
                    if any(t in row_vec for t in r.texts)
                ),
                reverse=True,
            )
            want = {c for c in expected.split(",") if c and c != "-"}
            rank = next((i + 1 for i, (_s, c) in enumerate(scored) if c in want), None) if want else None
            best = ", ".join(f"{c} {s:.3f}" for s, c in scored[: args.top])
            cells = []
            for f in FLOORS:
                passing = [(s, c) for s, c in scored if s >= f]
                close = [c for s, c in passing if passing and s >= passing[0][0] - list_resolver.AMBIGUITY_MARGIN]
                if not want:
                    verdict = "FP" if passing else "ok"
                    tally[f]["false_positive" if passing else "clean"] += 1
                elif passing and passing[0][1] in want:
                    verdict = "hit" if len(close) == 1 else f"ask{len(close)}"
                    tally[f]["hit" if len(close) == 1 else "ambiguous_hit"] += 1
                else:
                    verdict = "miss"
                    tally[f]["miss"] += 1
                cells.append(verdict)
            print(f"| {phrase} | {expected} | {best} | {rank or '-'} | " + " | ".join(cells) + " |")
        print("\n| floor | hit | ask (hit within margin) | miss | false positive | clean negative |")
        print("|---|---|---|---|---|---|")
        for f in FLOORS:
            t = tally[f]
            print(f"| {f:.2f} | {t['hit']} | {t['ambiguous_hit']} | {t['miss']} | {t['false_positive']} | {t['clean']} |")
        return 0
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
