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
  labelledBy?: string;
  /** The group's name when no element carries it (a per-line toggle). */
  ariaLabel?: string;
  /** PRICETAG-LPSP: the compact per-line form, "LP" / "SP". */
  compact?: boolean;
  /** Tooltip on the group (a per-line toggle that follows the default says so). */
  title?: string;
}

export function PriceModeToggle({
  value,
  onChange,
  labelledBy,
  ariaLabel,
  compact = false,
  title,
}: PriceModeToggleProps) {
  const labels = compact ? { list: 'LP', selling: 'SP' } : { list: 'List price', selling: 'Selling price' };
  const pad = compact ? 'rounded px-2 py-1 text-xs transition-colors' : 'rounded px-3 py-1.5 text-sm transition-colors';
  return (
    <div
      role="radiogroup"
      aria-labelledby={labelledBy}
      aria-label={labelledBy ? undefined : ariaLabel}
      title={title}
      className="inline-flex items-center rounded-md border p-0.5"
    >
      <button
        type="button"
        role="radio"
        aria-checked={value === 'list'}
        className={cn(
          pad,
          value === 'list'
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:bg-muted',
        )}
        onClick={() => onChange('list')}
      >
        {labels.list}
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={value === 'selling'}
        className={cn(
          pad,
          value === 'selling'
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:bg-muted',
        )}
        onClick={() => onChange('selling')}
      >
        {labels.selling}
      </button>
    </div>
  );
}
