"""Fold legacy "+ Additional from X" tier rows onto their tier (lane TARGET-TIER-ADDITIONAL).

Owner, 5 Nov 11:10: a tier's Additional sits on the tier row ("A/C I 6% + 1%") and only the
REACHED tier's pays; Bonus is the tier's RM Additional, paid for the reached tier only. This
script moves each "+ Additional" row onto the main tier of the same period and threshold
(`commission_service.fold_additionals`) and reports, for every target with an additional row or
a Bonus, each period's commission and bonus before and after.

    python scripts/fold_tier_additionals.py            # dry run: report only, writes nothing
    python scripts/fold_tier_additionals.py --apply --expect N   # owner-approved: write the fold

`--apply` needs `--expect N`, the fold count the dry run printed; it writes nothing when the count
found now differs (the data moved since the dry run the owner approved).

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
from typing import Dict, List, Optional

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


def _num(value: Decimal) -> str:
    """`60,000`, `62,500.50`, `4`, `5.5`: no trailing zeros."""
    value = Decimal(value)
    if value == value.to_integral_value():
        return f"{value:,.0f}"
    return f"{value.normalize():,f}"


def ladder_drops(rows, fold, pct: bool, labels: Dict[object, str], unit: str = "%") -> List[str]:
    """Where, after the fold, reaching a higher tier pays a LOWER rate than the tier below
    (owner ruling 5 Nov 12:10: an Additional pays only on its own tier, it never carries up), with
    the Additional each tier needs to keep today's pay. Today's pay: the tier's rate plus every
    "+ Additional" row at or below its threshold (they stacked). One line per period and account
    with a drop. `rows` are `FoldRow`s; `labels` names an account key (None: every account);
    `unit` is `%`, or ` RM/unit` on a quantity target."""

    def rate_on(row, account) -> Optional[Decimal]:
        if row.account_rates is None:
            return Decimal(row.rate or 0)
        value = row.account_rates.get(account)
        return None if value is None else Decimal(value)

    out: List[str] = []
    for period in sorted({r.period_start for r in rows}, key=lambda d: (d is not None, d)):
        idx = [i for i, r in enumerate(rows) if r.period_start == period]
        mains = sorted((i for i in idx if not rows[i].is_additional), key=lambda i: rows[i].threshold)
        legacy = [i for i in idx if rows[i].is_additional]
        accounts = {k for i in idx for k in (rows[i].account_rates or {})}
        if not accounts or any(rows[i].account_rates is None for i in mains):
            # A pay-all tier pays every account: checked once, as "every account".
            accounts.add(None)
        for account in sorted(accounts, key=lambda k: (k is not None, labels.get(k, str(k)))):
            old: Dict[int, Decimal] = {}
            new: Dict[int, Decimal] = {}
            #: What still stacks on the tier after the fold (rows it could not place).
            left: Dict[int, Decimal] = {}
            for m in mains:
                base = rate_on(rows[m], account)
                if base is None:
                    continue
                own = Decimal(rows[m].additional_rate or 0)
                stacked = [i for i in legacy if rows[i].threshold <= rows[m].threshold]
                old[m] = base + own + sum((rate_on(rows[i], account) or 0 for i in stacked), Decimal("0"))
                left[m] = sum(
                    (rate_on(rows[i], account) or 0 for i in stacked if i not in fold.moves), Decimal("0")
                )
                new[m] = base + Decimal(fold.rates.get(m, own)) + left[m]
            paying = [m for m in mains if m in new]
            drops = [(a, b) for a, b in zip(paying, paying[1:]) if new[b] < new[a]]
            if not drops:
                continue
            need: Dict[Decimal, List[int]] = {}
            for m in paying:
                if new[m] < old[m]:
                    # The tier's own Additional that keeps today's pay: today's rate less its rate
                    # and less what still stacks on it after the fold.
                    need.setdefault(old[m] - rate_on(rows[m], account) - left[m], []).append(m)
            at = lambda m: f"{_num(rows[m].threshold)}%" if pct else _num(rows[m].threshold)  # noqa: E731
            who = f"{labels.get(account, account)} " if account is not None else ""
            first_low, first_high = drops[0]
            fix = "; ".join(
                f"set Additional {_num(add)}{unit} on {' and '.join(at(m) for m in ms)}" for add, ms in need.items()
            )
            # A drop that comes from the fold widening an Additional to this account, not from
            # losing pay: nothing to restore, only worth a look.
            fix = fix or "today's pay is kept; check the tiers' Additionals"
            out.append(
                f"{period or 'every period'}: {who}tier {at(first_high)} pays {_num(new[first_high])}{unit} "
                f"vs {_num(new[first_low])}{unit} at {at(first_low)} -> " + (
                    f"to keep today's pay {fix}" if need else fix
                )
            )
    return out


def report(db) -> List[dict]:
    """One entry per target with a "+ Additional" row or a Bonus: its fold and each period's
    payout before and after. Writes nothing."""
    from app.models.base import get_company_scope, set_company_scope
    from app.models.order import Customer
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
        fold_rows = _fold_rows(target, tiers, rates)
        fold = commission_service.fold_additionals(fold_rows)
        codes = {k for r in fold_rows for k in (r.account_rates or {})}
        labels = (
            {c.id: c.customer_code for c in db.query(Customer).filter(Customer.id.in_(codes))} if codes else {}
        )
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
                "ladder_drops": [
                    f"{target.target_no} {target.name}, {line}"
                    for line in ladder_drops(
                        fold_rows, fold, (target.threshold_unit or "pct") == "pct", labels,
                        " RM/unit" if target.metric == "quantity" else "%",
                    )
                ],
            }
        )
    set_company_scope(db, scope)
    return out


class ExpectMismatch(RuntimeError):
    """`--apply` found a different number of rows to fold than `--expect` names."""


def apply(db, entries: List[dict], expect: Optional[int]) -> int:
    """Write the fold: each main tier takes its % Additional, each folded row is deleted (its
    per-account rates go with it, ON DELETE CASCADE). Returns the rows folded. Refuses, writing
    nothing, unless `expect` is the number of rows the fold moves now."""
    found = sum(len(e["moves"]) for e in entries)
    if expect is None or expect != found:
        raise ExpectMismatch(
            f"--expect {expect} but {found} rows would be folded now; re-run the dry run and pass its count"
        )
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
    drops = [line for e in entries for line in e["ladder_drops"]]
    print(f"\nLADDER DROPS ({len(drops)}): after the fold a higher tier pays less than the tier below. "
          "An Additional pays only on its own tier; set these before --apply.")
    for line in drops:
        print(f"  {line}")
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
    ap.add_argument("--expect", type=int, help="with --apply: the fold count the dry run printed")
    args = ap.parse_args()

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        entries = report(db)
        _print(entries)
        moved = sum(len(e["moves"]) for e in entries)
        if not args.apply:
            db.rollback()
            print(f"\nDry run: nothing written. Once the owner approves: --apply --expect {moved}")
            return 0
        try:
            folded = apply(db, entries, args.expect)
        except ExpectMismatch as exc:
            db.rollback()
            print(f"\nNot applied: {exc}")
            return 2
        db.commit()
        print(f"\nApplied: {folded} rows folded.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
