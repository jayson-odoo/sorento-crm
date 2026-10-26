"""Calibrate the registration queue's "meaning" bar on real project titles (PROJECT-REG-PORTAL D8).

READ-ONLY. Embeds every project's canonical line (`title | developer | state, mukim`, the same
`canonical_text` the queue uses) with the configured embedding model, scores every pair within a
company, and prints how the cosine spreads over three kinds of pair:

- likely_same: the two titles share a lot/PT number and a mukim (the team's stable key), and are
  not phase siblings;
- sibling: same lot or same title stem but a different phase / block designator;
- other: everything else.

The output names projects by CODE only, never by title, developer or person, so it can be pasted
into a public PR comment.

Usage (backend venv, against the dev copy; one embedding call per project):
    python -m scripts.calibrate_registration_semantic
    python -m scripts.calibrate_registration_semantic --company-code SRT --top 25
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models.base import set_company_scope  # noqa: E402

BARS = (0.70, 0.75, 0.78, 0.80, 0.82, 0.85, 0.88, 0.90)


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company-code", default=None, help="only this company (default: every company)")
    parser.add_argument("--top", type=int, default=20, help="nearest pairs to list")
    parser.add_argument("--batch", type=int, default=64)
    args = parser.parse_args()

    from app.models.projects import Project, ProjectParty, ProjectSalesProfile
    from app.services.embedding_worker import _embed_text_chunks
    from app.services.project_clash_service import are_sibling_developments, normalise_project_title
    from app.services.project_registration_service import canonical_text, parse_lot_numbers, parse_mukim

    db = SessionLocal()
    try:
        set_company_scope(db, None)
        query = (
            db.query(Project, ProjectParty.name, ProjectSalesProfile.state, ProjectSalesProfile.mukim)
            .outerjoin(ProjectParty, ProjectParty.id == Project.developer_party_id)
            .outerjoin(ProjectSalesProfile, ProjectSalesProfile.project_id == Project.id)
        )
        if args.company_code:
            from app.models.company import Company

            company = db.query(Company).filter(Company.code == args.company_code).first()
            if company is None:
                sys.exit(f"no company {args.company_code!r}")
            query = query.filter(Project.company_id == company.id)
        rows = query.all()
        if len(rows) < 2:
            sys.exit("fewer than two projects: nothing to calibrate")

        texts = [canonical_text(p.title, dev, state, mukim) for p, dev, state, mukim in rows]
        vectors = []
        for start in range(0, len(texts), args.batch):
            vectors.extend(_embed_text_chunks(texts[start : start + args.batch]))

        by_company = defaultdict(list)
        for index, (project, _dev, _state, mukim) in enumerate(rows):
            by_company[str(project.company_id)].append((index, project, mukim))

        scores = defaultdict(list)
        pairs = []
        for members in by_company.values():
            for i in range(len(members)):
                ia, pa, ma = members[i]
                lots_a = parse_lot_numbers(pa.title)
                muk_a = (ma or "").strip().casefold() or parse_mukim(pa.title)
                key_a = pa.normalised_title or normalise_project_title(pa.title)
                for j in range(i + 1, len(members)):
                    ib, pb, mb = members[j]
                    key_b = pb.normalised_title or normalise_project_title(pb.title)
                    sibling = are_sibling_developments(key_a, key_b)
                    muk_b = (mb or "").strip().casefold() or parse_mukim(pb.title)
                    same_lot = bool(lots_a & parse_lot_numbers(pb.title)) and bool(muk_a) and muk_a == muk_b
                    kind = "sibling" if sibling else ("likely_same" if same_lot else "other")
                    cos = _cosine(vectors[ia], vectors[ib])
                    scores[kind].append(cos)
                    pairs.append((cos, pa.project_code, pb.project_code, kind))

        print(f"projects: {len(rows)}  pairs: {len(pairs)}")
        for kind in ("likely_same", "sibling", "other"):
            values = sorted(scores[kind])
            if not values:
                print(f"{kind}: none")
                continue
            mid = values[len(values) // 2]
            print(f"{kind}: n={len(values)} min={values[0]:.3f} median={mid:.3f} max={values[-1]:.3f}")
        print("pairs at or above each bar (likely_same / sibling / other):")
        for bar in BARS:
            counts = [sum(1 for v in scores[k] if v >= bar) for k in ("likely_same", "sibling", "other")]
            print(f"  {bar:.2f}: {counts[0]} / {counts[1]} / {counts[2]}")
        print(f"nearest {args.top} pairs (codes only):")
        for cos, a, b, kind in sorted(pairs, reverse=True)[: args.top]:
            print(f"  {cos:.3f}  {a}  {b}  {kind}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
