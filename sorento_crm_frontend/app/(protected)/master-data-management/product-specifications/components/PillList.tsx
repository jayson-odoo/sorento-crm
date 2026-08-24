'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';

/**
 * A row of pills that stops at a sensible number and offers the rest on request.
 *
 * `finish` carries 17 customer words and `product_type` 31 values. Rendered in full,
 * one row of the table was three lines tall and the grid stopped being scannable - the
 * words that matter were lost among the ones that happened to be listed first.
 */
export default function PillList({
  values,
  max = 6,
  emphasis = [],
  ariaLabel,
}: {
  values: string[];
  /** How many to show before the rest collapse behind a +N. */
  max?: number;
  /** Rendered solid rather than outline - used to mark a search hit. */
  emphasis?: string[];
  ariaLabel?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  if (values.length === 0) return null;

  const shown = expanded ? values : values.slice(0, max);
  const hidden = values.length - shown.length;

  return (
    <div className="flex flex-wrap items-center gap-1" aria-label={ariaLabel}>
      {shown.map((value) => (
        <Badge
          key={value}
          variant={emphasis.includes(value) ? 'primary' : 'secondary'}
          size="sm"
          appearance="light"
          shape="circle"
        >
          {value}
        </Badge>
      ))}
      {hidden > 0 && (
        <button type="button" onClick={() => setExpanded(true)} className="cursor-pointer">
          <Badge variant="outline" size="sm" appearance="light" shape="circle">
            +{hidden}
          </Badge>
        </button>
      )}
      {expanded && values.length > max && (
        <button type="button" onClick={() => setExpanded(false)} className="cursor-pointer">
          <Badge variant="outline" size="sm" appearance="light" shape="circle">
            show less
          </Badge>
        </button>
      )}
    </div>
  );
}
