"""Fold legacy "+ Additional from X" tier rows onto their tier (lane TARGET-TIER-ADDITIONAL).

Owner, 5 Nov 11:10: a tier's Additional sits on the tier row ("A/C I 6% + 1%") and only the
REACHED tier's pays; Bonus is the tier's RM Additional, paid for the reached tier only. This
script moves each "+ Additional" row onto the main tier of the same period and threshold
(`commission_service.fold_additionals`) and reports, for every target with an additional row or
a Bonus, each period's commission and bonus before and after.

    python scripts/fold_tier_additionals.py            # dry run: report only, writes nothing
    python scripts/fold_tier_additionals.py --apply    # owner-approved: write the fold

"Before" is what the CRM paid until this lane: every reached "+ Additional" row stacked and every
reached tier's Bonus added up. "After" is this lane's engine on the folded tiers. A row the fold
cannot place is left as it is (it keeps paying as a line of its own) and listed with the reason.
A dealer period another target replaces still reads its own payout here.
"""
from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fold_rows(target, tiers, rates):
    from app.services.sales.commission_service import FoldRow

    pct = (target.threshold_unit or "pct") == "pct"
    return [
        FoldRow(
            period_start=t.period_start,
            threshold=Decimal(t.from_pct if pct else t.threshold),
            is_additional=bool(t.is_additional),
            rate=t.rate,
            account_rates=rates.get(t.id),
            additional_rate=t.additional_rate,
            bonus_amount=t.bonus_amount,
        )
        for t in tiers
    ]


def report(db) -> List[dict]:
    """One entry per target with a "+ Additional" row or a Bonus: its fold and each period's
    payout before and after. Writes nothing."""
    from app.models.base import get_company_scope, set_company_scope
    from app.models.sales import SalesTarget, SalesTargetCommissionTier
    from app.services.sales import commission_service
    from app.services.sales import target_service as ts

    scope = get_company_scope(db)
    set_company_scope(db, None)
    ids = [
        row[0]
        for row in db.query(SalesTargetCommissionTier.target_id)
        .filter(
            (SalesTargetCommissionTier.is_additional.is_(True))
            | (SalesTargetCommissionTier.bonus_amount > 0)
        )
        .distinct()
    ]
    targets = (
        db.query(SalesTarget).filter(SalesTarget.id.in_(ids)).order_by(SalesTarget.target_no).all()
        if ids
        else []
    )
    out: List[dict] = []
    for target in targets:
        set_company_scope(db, frozenset({target.company_id}))
        tiers = ts._tiers(db, target.id)
        rates = ts._tier_rates(db, [t.id for t in tiers])
        fold = commission_service.fold_additionals(_fold_rows(target, tiers, rates))
        before = ts._engine_tiers(tiers, rates)
        after = [
            t._replace(additional_rate=fold.rates.get(i, t.additional_rate))
            for i, t in enumerate(before)
            if i not in fold.moves
        ]
        starts_before = [t.period_start for t in tiers]
        starts_after = [s for i, s in enumerate(starts_before) if i not in fold.moves]
        periods = ts._periods(db, target.id)
        by_account = ts._achieved_by_account(db, target.company_id, [(target, p) for p in periods])
        ratios = ts.point_ratios(db) if target.threshold_unit == "points" else []
        rows = []
        for p in periods:
            achieved = by_account.get(p.id, {})
            old = ts.period_payout(target, p, before, starts_before, achieved, ratios)
            new = ts.period_payout(target, p, after, starts_after, achieved, ratios)
            # Before this lane every reached tier's Bonus added up.
            ladder = ts.tier_ladder(before, starts_before, p, target, ratios)
            old_bonus = sum(
                (
                    Decimal(str(r["additional"]["value"]))
                    for r in ladder[: old.tier_reached or 0]
                    if r["additional"] and r["additional"]["kind"] == "amount"
                ),
                Decimal("0"),
            )
            old_total = (old.commission or 0) + old_bonus
            new_total = (new.commission or 0) + (new.bonus or 0)
            rows.append(
                {
                    "period_start": p.period_start,
                    "achieved": sum(achieved.values(), Decimal("0")),
                    "tier": old.tier_reached,
                    "old_commission": old.commission,
                    "old_bonus": old_bonus,
                    "new_commission": new.commission,
                    "new_bonus": new.bonus,
                    "delta": new_total - old_total,
                }
            )
        out.append(
            {
                "target_id": target.id,
                "target_no": target.target_no,
                "name": target.name,
                "additional_rows": sum(1 for t in tiers if t.is_additional),
                "bonus_tiers": sum(1 for t in tiers if t.bonus_amount),
                "moves": {tiers[i].id: tiers[m].id for i, m in fold.moves.items()},
                "rates": {tiers[m].id: r for m, r in fold.rates.items()},
                "skipped": [
                    f"{tiers[i].period_start or 'every period'} from {_fold_rows(target, [tiers[i]], rates)[0].threshold:,.2f}: {why}"
                    for i, why in sorted(fold.skipped.items())
                ],
                "broadened": [f"{tiers[m].period_start} from {tiers[m].threshold or tiers[m].from_pct:,.2f}" for m in fold.broadened],
                "narrowed": [f"{tiers[m].period_start} from {tiers[m].threshold or tiers[m].from_pct:,.2f}" for m in fold.narrowed],
                "periods": rows,
            }
        )
    set_company_scope(db, scope)
    return out


def apply(db, entries: List[dict]) -> int:
    """Write the fold: each main tier takes its % Additional, each folded row is deleted (its
    per-account rates go with it, ON DELETE CASCADE). Returns the rows folded."""
    from app.models.base import get_company_scope, set_company_scope
    from app.models.sales import SalesTargetCommissionTier

    scope = get_company_scope(db)
    set_company_scope(db, None)
    folded = 0
    for entry in entries:
        for tier_id, rate in entry["rates"].items():
            db.get(SalesTargetCommissionTier, tier_id).additional_rate = rate
        for row_id in entry["moves"]:
            db.delete(db.get(SalesTargetCommissionTier, row_id))
            folded += 1
    db.flush()
    set_company_scope(db, scope)
    return folded


def _print(entries: List[dict]) -> None:
    rows = sum(e["additional_rows"] for e in entries)
    moved = sum(len(e["moves"]) for e in entries)
    print(f"{len(entries)} targets; {rows} '+ Additional' rows, {moved} fold onto their tier; "
          f"{sum(e['bonus_tiers'] for e in entries)} tiers carry a Bonus")
    for e in entries:
        print(f"\n{e['target_no']}  {e['name']}  (+Additional rows {e['additional_rows']}, "
              f"folded {len(e['moves'])}, Bonus tiers {e['bonus_tiers']})")
        for why in e["skipped"]:
            print(f"  NOT FOLDED  {why}")
        for where in e["broadened"]:
            print(f"  NOW ON EVERY ACCOUNT THE TIER PAYS  {where}")
        for where in e["narrowed"]:
            print(f"  NOW ONLY ON THE TIER'S NAMED ACCOUNTS  {where}")
        print("  period      achieved        tier  old comm   old bonus  new comm   new bonus  change")
        for p in e["periods"]:
            def f(v):
                return "-" if v is None else f"{Decimal(v):,.2f}"
            print(f"  {p['period_start']}  {f(p['achieved']):>14}  {p['tier'] or '-':>4}  {f(p['old_commission']):>9}"
                  f"  {f(p['old_bonus']):>9}  {f(p['new_commission']):>9}  {f(p['new_bonus']):>9}  {f(p['delta']):>9}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the fold (owner-approved); omit for a dry run")
    args = ap.parse_args()

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        entries = report(db)
        _print(entries)
        if not args.apply:
            db.rollback()
            print("\nDry run: nothing written. Re-run with --apply once the owner approves.")
            return 0
        folded = apply(db, entries)
        db.commit()
        print(f"\nApplied: {folded} rows folded.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
