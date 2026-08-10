'use client';

import { useEffect, useState } from 'react';
import { Check, PackageCheck, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { fmtInt } from '../../lib/format';
import type { PlanLine } from '../lib/planLine';
import type { PlanDecision, PlanDecisionKind } from '../lib/planDecisions';

/**
 * The same three choices on every row: buy this much, use the stock we already have, or skip.
 *
 * > "I need to decide first, before you tell me within budget or out of budget"
 *
 * The quantity is editable in place and pre-filled with the engine's suggestion, so agreeing
 * is one click and disagreeing is one keystroke. Nothing here mentions a budget: what this
 * costs is a question for after the decisions, not a constraint on making them.
 *
 * An undecided cell shows all three actions and no state, because "I have not decided" has to
 * look different from every decision, including from skipping.
 */

const KIND_LABEL: Record<PlanDecisionKind, string> = {
  buy: 'Buying',
  use_stock: 'Using stock',
  skip: 'Skipped',
};

export function PlanLineDecisionCell({
  line,
  decision,
  onDecide,
  onClear,
}: {
  line: PlanLine;
  decision: PlanDecision | undefined;
  onDecide: (next: { kind: PlanDecisionKind; qty?: number }) => void;
  /** Put the line back to undecided. Its own callback rather than a fourth decision kind,
   *  because undecided is the ABSENCE of a decision and must not become one. */
  onClear: () => void;
}) {
  /**
   * The engine's quantity, as a whole number of units.
   *
   * `order_qty` is frequently fractional on real data (2,407.677748 on the live run) because
   * a demand rate times a horizon is a real number and nothing forces it to a unit unless the
   * supplier has an MoQ or an order multiple. You cannot order 0.677748 of a tile. The old
   * grid hid this by formatting the display and submitting the raw float; here the field is
   * editable, so it has to hold something orderable.
   *
   * Rounded UP, never down: down is a deliberate under-buy of a shortage we just calculated.
   */
  const suggested = Math.ceil(line.order_qty);
  const [qty, setQty] = useState<string>(String(decision?.qty ?? suggested));

  // Re-sync when the decision changes from elsewhere (a bulk action, a refetch), so the box
  // shows what was recorded rather than what was typed and abandoned.
  useEffect(() => {
    setQty(String(decision?.qty ?? suggested));
  }, [decision?.qty, suggested]);

  const commitBuy = () => {
    const n = Number(qty);
    // A quantity that is not a number is not a decision; fall back to the suggestion rather
    // than recording a NaN as an order.
    onDecide({ kind: 'buy', qty: Number.isFinite(n) && n > 0 ? n : suggested });
  };

  // An allocation is stock to move, not stock to order, so it is never offered a buy.
  const canBuy = line.purchasable;

  if (decision) {
    return (
      <div className="flex items-center gap-2">
        <Badge
          variant={decision.kind === 'skip' ? 'secondary' : 'primary'}
          appearance="light"
          size="sm"
        >
          {KIND_LABEL[decision.kind]}
          {decision.kind === 'buy' ? ` ${fmtInt(decision.qty ?? suggested)}` : ''}
        </Badge>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={onClear}
        >
          Change
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      {canBuy ? (
        <>
          <Input
            value={qty}
            onChange={(e) => setQty(e.target.value.replace(/[^0-9]/g, ''))}
            onKeyDown={(e) => e.key === 'Enter' && commitBuy()}
            className="h-8 w-20 text-right tabular-nums"
            aria-label={`Quantity to buy for ${line.sku}`}
          />
          <Button
            size="sm"
            className="h-8 px-2"
            onClick={commitBuy}
            title={`Buy ${qty || suggested} of ${line.sku}`}
          >
            <Check className="size-3.5" />
            Buy
          </Button>
        </>
      ) : null}
      <Button
        variant="outline"
        size="sm"
        className={cn('h-8 px-2', !canBuy && 'flex-1')}
        onClick={() => onDecide({ kind: 'use_stock' })}
        title={`Cover ${line.sku} from stock we already hold`}
      >
        <PackageCheck className="size-3.5" />
        Use stock
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="h-8 px-2"
        onClick={() => onDecide({ kind: 'skip' })}
        title={`Skip ${line.sku} this round`}
      >
        <X className="size-3.5" />
      </Button>
    </div>
  );
}
