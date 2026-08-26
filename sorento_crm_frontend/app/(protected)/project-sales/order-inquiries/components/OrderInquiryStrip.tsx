'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { SupplyKindCard } from '../../_shared/components/SupplyKindCard';
import {
  KIND_COLOURS,
  KIND_LABELS,
  KIND_ORDER,
} from '../../_shared/lib/orderInquiryKinds';
import type {
  OrderInquiryKind,
  OrderInquiryKindSegment,
} from '../../_shared/lib/orderInquiryKinds';
import { formatInquiryQty } from '../../_shared/lib/orderInquiryWorklist';
import { toMinor } from '../../_shared/lib/supplyComposition';

/**
 * What the rows in view still need, in three cards (AC-I11): Use SPO, Use PO, Buy.
 *
 * ONE FIGURE PER CARD, not the board's pair: purchasing has no "suggested" to compare
 * against - a document either holds the quantity or nobody has put it anywhere - so the
 * quantity IS the whole statement. The card component is the board's own
 * (`SupplyKindCard`), so the two strips press, highlight and grey out identically.
 *
 * THE TOTALS ARE THE SERVER'S, NOT THE PAGE'S. They come off the worklist summary's
 * `kinds` facet, which counts every matching row rather than the twenty-five on screen,
 * so pressing a card cannot reveal more quantity than the card claimed.
 *
 * Pressing a card narrows both views to the rows CARRYING that kind, and pressing it
 * again clears. The facet is computed with the kind filter dropped (the same rule every
 * other control on this screen is computed by), so the other two cards keep their figures
 * while one is pressed and the strip stays usable a second time.
 *
 * No legend and no sentence under the cards: the cards ARE the legend - each one carries
 * its own colour beside its own words.
 */
export function OrderInquiryStrip({
  totals,
  active,
  onToggle,
}: {
  totals: OrderInquiryKindSegment[];
  active: OrderInquiryKind | null;
  onToggle: (kind: OrderInquiryKind) => void;
}) {
  const byKind = React.useMemo(() => {
    const map = new Map<OrderInquiryKind, string>();
    for (const total of totals) map.set(total.kind, total.qty);
    return map;
  }, [totals]);

  return (
    <div
      data-testid="order-inquiry-strip"
      className="grid grid-cols-3 gap-2 sm:max-w-xl"
    >
      {KIND_ORDER.map((kind) => {
        const qty = byKind.get(kind) ?? '0';
        // Nothing in view is that kind, so there is nothing to filter to.
        const empty = toMinor(qty) === 0;
        return (
          <SupplyKindCard
            key={kind}
            kind={kind}
            label={KIND_LABELS[kind]}
            swatchClass={KIND_COLOURS[kind].bar}
            selected={active === kind}
            disabled={empty}
            onClick={() => onToggle(kind)}
            testId={`order-inquiry-strip-${kind}`}
          >
            <span
              data-testid={`order-inquiry-strip-qty-${kind}`}
              className={cn(
                'mt-1.5 block text-lg font-semibold tabular-nums',
                KIND_COLOURS[kind].text,
              )}
            >
              {formatInquiryQty(qty) || '0'}
            </span>
          </SupplyKindCard>
        );
      })}
    </div>
  );
}
