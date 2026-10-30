'use client';

/**
 * The request's price mode (D5): List price or Selling price, one radio pair. Selling is never
 * disabled; the promotion is picked per line, not here (D1/AC-S1-3).
 *
 * Shared by the portal's price tag form and the CRM request page a salesperson edits their own
 * request on (PORTAL-P4-REQUESTS S7b round 2). Moved out of
 * `app/(auth)/portal/components/PriceTagRequestForm.tsx` unchanged; what a pick does beyond the
 * mode (the portal opens its next section) stays with the caller's `onChange`.
 */

import type { PriceMode } from '@/app/(auth)/portal/lib/price-tag-request-service';
import { cn } from '@/lib/utils';

interface PriceModeToggleProps {
  value: PriceMode;
  onChange: (mode: PriceMode) => void;
  /** The id of the element that names the group. */
  labelledBy: string;
}

export function PriceModeToggle({ value, onChange, labelledBy }: PriceModeToggleProps) {
  return (
    <div
      role="radiogroup"
      aria-labelledby={labelledBy}
      className="inline-flex items-center rounded-md border p-0.5"
    >
      <button
        type="button"
        role="radio"
        aria-checked={value === 'list'}
        className={cn(
          'rounded px-3 py-1.5 text-sm transition-colors',
          value === 'list'
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:bg-muted',
        )}
        onClick={() => onChange('list')}
      >
        List price
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={value === 'selling'}
        className={cn(
          'rounded px-3 py-1.5 text-sm transition-colors',
          value === 'selling'
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:bg-muted',
        )}
        onClick={() => onChange('selling')}
      >
        Selling price
      </button>
    </div>
  );
}
