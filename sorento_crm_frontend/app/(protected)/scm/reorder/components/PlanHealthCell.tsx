'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { EM_DASH } from '../../lib/format';
import type { HealthVerdict, ProductEconomics } from '../lib/productHealth';

/**
 * The health chapter's cell: is this item still moving, and should we keep selling it?
 *
 * > "this is a suggestion by the system and also an action needs to be taken / decide by
 * >  the user ... it is defaulted to our suggestion but they can decide otherwise"
 *
 * The pill is the movement class (Fast moving / Slow moving / Dead / No history), read
 * off delivery orders out and GRN receipts in. A margin percentage used to sit here; it
 * compared a CNY cost against a MYR price through an exchange rate nobody trusted, so it
 * is gone (captain, 27 Aug). Only Dead carries an ask, and the popup carries two buttons,
 * Keep selling and Discontinue, with the system's suggestion presented as the default.
 * The recorded decision replaces the ask on the row ("You chose: discontinue") and
 * survives across plans until withdrawn. Recording "discontinue" never touches AutoCount;
 * marking it there is the buyer's job.
 */

export function PlanHealthCell({
  health,
  econ,
  onDecideLifecycle,
}: {
  health: HealthVerdict | null;
  econ: ProductEconomics | null;
  /** Record (or withdraw, with null) the keep-or-discontinue answer. Absent = read-only. */
  onDecideLifecycle?: (productId: string, decision: 'keep' | 'discontinue' | null) => Promise<void> | void;
}) {
  const [saving, setSaving] = useState(false);

  if (!health) {
    return (
      <span className="text-muted-foreground" title="No movement on file for this product">
        {EM_DASH}
      </span>
    );
  }

  const decision = econ?.lifecycle_decision ?? null;
  // Only a Dead product is suggested for discontinuation; every other class suggests
  // keeping it. Neither button gets the "this is the suggestion" outline by accident.
  const suggested: 'keep' | 'discontinue' = health.consider ? 'discontinue' : 'keep';

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
          <Badge variant={health.tone} appearance="light" size="sm">
            {health.label}
          </Badge>
          {decision ? (
            <span
              className={`mt-0.5 block truncate text-2xs font-medium ${
                decision === 'discontinue' ? 'text-destructive' : 'text-muted-foreground'
              }`}
            >
              {decision === 'discontinue' ? 'You chose: discontinue' : 'You chose: keep selling'}
            </span>
          ) : health.suggestion ? (
            <span className="mt-0.5 block truncate text-2xs font-medium text-destructive">
              {health.suggestion}
            </span>
          ) : null}
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent className="w-80 text-xs" align="start">
          {/* One line, the same shape every time: the verdict, named. */}
          <p className="font-medium text-foreground">
            Suggestion: {health.consider ? 'Discontinue' : 'Keep selling'}
          </p>

          {/* The counts the verdict is drawn from - no prose, just the movement. */}
          <ul className="mt-2 space-y-1 border-t pt-2 text-muted-foreground">
            {health.factors.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>

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
              {!decision && suggested === 'discontinue' ? (
                <span className="text-2xs text-muted-foreground">suggested</span>
              ) : null}
            </div>
          ) : null}
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}
