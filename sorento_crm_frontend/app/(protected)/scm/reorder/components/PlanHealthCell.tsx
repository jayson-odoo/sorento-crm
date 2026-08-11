'use client';

import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { EM_DASH } from '../../lib/format';
import type { DiscontinueAdvice, MarginVerdict } from '../lib/productHealth';

/**
 * The health chapter's cell: the margin the item really earns, and - when the factors
 * align - the ask to consider discontinuing it. Result on the row, the whole case in
 * the popup, one factor per line so it can be argued with number by number.
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
}: {
  margin: MarginVerdict | null;
  advice: DiscontinueAdvice | null;
}) {
  if (!margin && !advice) {
    return (
      <span className="text-muted-foreground" title="No economics for this product">
        {EM_DASH}
      </span>
    );
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className="min-w-0 text-left" aria-label="Product health">
          {margin ? (
            <Badge variant={MARGIN_VARIANT[margin.tone]} appearance="light" size="sm">
              {margin.pct === null ? 'Margin unknown' : `Margin ${margin.pct}%`}
            </Badge>
          ) : null}
          {advice?.consider ? (
            <span className="mt-0.5 block truncate text-2xs font-medium text-destructive">
              Consider discontinuing
            </span>
          ) : margin?.sell_source === 'list_price' ? (
            <span className="mt-0.5 block truncate text-2xs text-muted-foreground">
              vs list price - nothing sold
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
          <p className="mt-3 border-t pt-2 text-2xs text-muted-foreground">
            Based on our own orders and stock only. Discontinuing stays your call.
          </p>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}
