'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { EM_DASH, fmtSupplierCost } from '../../lib/format';
import type { DiscontinueAdvice, MarginVerdict, ProductEconomics } from '../lib/productHealth';

/**
 * The health chapter's cell: the margin the item really earns, the discontinue ask when
 * the factors align, and the buyer's ANSWER to it.
 *
 * > "this is a suggestion by the system and also an action needs to be taken / decide by
 * >  the user ... it is defaulted to our suggestion but they can decide otherwise"
 *
 * So the popup carries two buttons, Keep selling and Discontinue, with the system's
 * suggestion presented as the default. The recorded decision replaces the ask on the row
 * ("You chose: discontinue") and survives across plans until withdrawn - the advisory
 * itself still recomputes every run and the case stays readable behind the decision.
 * Recording "discontinue" never touches AutoCount; marking it there is the buyer's job.
 */

const MARGIN_VARIANT = {
  healthy: 'success',
  thin: 'warning',
  negative: 'destructive',
  unknown: 'secondary',
} as const;

export function PlanHealthCell({
  margin,
  advice,
  econ,
  onDecideLifecycle,
}: {
  margin: MarginVerdict | null;
  advice: DiscontinueAdvice | null;
  econ: ProductEconomics | null;
  /** Record (or withdraw, with null) the keep-or-discontinue answer. Absent = read-only. */
  onDecideLifecycle?: (productId: string, decision: 'keep' | 'discontinue' | null) => Promise<void> | void;
}) {
  const [saving, setSaving] = useState(false);

  if (!margin && !advice) {
    return (
      <span className="text-muted-foreground" title="No economics for this product">
        {EM_DASH}
      </span>
    );
  }

  const decision = econ?.lifecycle_decision ?? null;
  const suggested: 'keep' | 'discontinue' = advice?.consider ? 'discontinue' : 'keep';

  const record = async (next: 'keep' | 'discontinue' | null) => {
    if (!onDecideLifecycle || !econ) return;
    setSaving(true);
    try {
      await onDecideLifecycle(econ.product_id, next);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className="min-w-0 text-left" aria-label="Product health">
          {margin ? (
            <Badge variant={MARGIN_VARIANT[margin.tone]} appearance="light" size="sm">
              {/* The amount rides along with the percentage (user feedback, 2026-08-12) -
                  the vs-list-price nuance already lives in the popover body below, so the
                  pill's own subtitle for that case is gone rather than duplicated. */}
              {margin.pct === null || margin.sell === null || margin.cost === null
                ? 'Margin unknown'
                : `Margin ${margin.pct}% (${fmtSupplierCost(margin.sell - margin.cost, null)})`}
            </Badge>
          ) : null}
          {decision ? (
            <span
              className={`mt-0.5 block truncate text-2xs font-medium ${
                decision === 'discontinue' ? 'text-destructive' : 'text-muted-foreground'
              }`}
            >
              {decision === 'discontinue' ? 'You chose: discontinue' : 'You chose: keep selling'}
            </span>
          ) : advice?.consider ? (
            <span className="mt-0.5 block truncate text-2xs font-medium text-destructive">
              Consider discontinuing
            </span>
          ) : null}
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent className="w-80 text-xs" align="start">
          <p className="font-medium text-foreground">
            {advice?.consider
              ? 'The factors argue for discontinuing this product.'
              : 'The product is earning its place.'}
          </p>

          {/* The arithmetic behind "Margin 33.3%" - no prose, just the three figures the
              badge is computed from, so the number can be checked at a glance. */}
          {margin ? (
            <div className="mt-2 border-t pt-2 text-2xs">
              {margin.sell === null ? (
                <p className="text-muted-foreground">Selling price not set - margin unknown.</p>
              ) : margin.cost === null || margin.cost <= 0 ? (
                <p className="text-muted-foreground">Cost not set - margin unknown.</p>
              ) : (
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <p className="text-muted-foreground">Selling price</p>
                    <p className="tabular-nums font-medium text-foreground">
                      {fmtSupplierCost(margin.sell, null)}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Cost</p>
                    <p className="tabular-nums font-medium text-foreground">
                      {fmtSupplierCost(margin.cost, null)}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Margin</p>
                    <p className="tabular-nums font-medium text-foreground">
                      {fmtSupplierCost(margin.sell - margin.cost, null)}
                      {margin.pct !== null ? ` (${margin.pct}%)` : ''}
                    </p>
                  </div>
                </div>
              )}
            </div>
          ) : null}

          {advice?.factors.length ? (
            <ul className="mt-2 space-y-1 text-muted-foreground">
              {advice.factors.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          ) : null}
          {margin?.sell_source === 'list_price' ? (
            <p className="mt-2 text-2xs text-muted-foreground">
              No sales in the window, so the margin compares against the list price.
            </p>
          ) : null}

          {/* The buyer's answer. The system's suggestion is the highlighted default;
              either click records, a second click on the same one withdraws. */}
          {onDecideLifecycle && econ ? (
            <div className="mt-3 flex items-center gap-2 border-t pt-3">
              <Button
                size="sm"
                variant={decision === 'keep' ? 'primary' : suggested === 'keep' ? 'outline' : 'ghost'}
                disabled={saving}
                onClick={() => void record(decision === 'keep' ? null : 'keep')}
              >
                {decision === 'keep' ? '✓ Keep selling' : 'Keep selling'}
              </Button>
              <Button
                size="sm"
                variant={decision === 'discontinue' ? 'primary' : suggested === 'discontinue' ? 'outline' : 'ghost'}
                className={decision === 'discontinue' ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90' : ''}
                disabled={saving}
                onClick={() => void record(decision === 'discontinue' ? null : 'discontinue')}
              >
                {decision === 'discontinue' ? '✓ Discontinue' : 'Discontinue'}
              </Button>
              {!decision ? (
                <span className="text-2xs text-muted-foreground">
                  {suggested === 'discontinue' ? 'suggested' : ''}
                </span>
              ) : null}
            </div>
          ) : null}

          <p className="mt-3 border-t pt-2 text-2xs text-muted-foreground">
            Based on our own orders and stock only. A discontinue decision is recorded
            here; marking it in AutoCount stays your job.
          </p>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}
