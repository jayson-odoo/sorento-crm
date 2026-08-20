'use client';

import * as React from 'react';
import { Link2, Unlink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PLACEABLE_VERBS } from './OrderInquiryVerbPill';
import { PlaceOnPoDialog } from './PlaceOnPoDialog';
import { UnplaceFromPoDialog } from './UnplaceFromPoDialog';

/**
 * The row action for "Place on PO" (section G), shared between purchasing's cross-project
 * worklist and the per-project order inquiry: a raised ORDER/RESERVE & ORDER row offers
 * "Place on PO"; a placed row offers "Unplace" behind a confirm. Every other row (already
 * actioned, cancelled, or a verb this never applies to) renders nothing - there is no
 * action to take.
 */
export function OrderInquiryRowActions({
  rowId,
  verb,
  state,
  itemCode,
  qty,
  poLabel,
}: {
  rowId: string;
  verb: string;
  state: string;
  itemCode?: string | null;
  qty: string;
  /** What to name in the Unplace confirm - the PO number this row is tagged to. */
  poLabel?: string | null;
}) {
  const [placing, setPlacing] = React.useState(false);
  const [unplacing, setUnplacing] = React.useState(false);

  if (state === 'placed') {
    return (
      <>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setUnplacing(true)}
        >
          <Unlink className="size-3.5" aria-hidden />
          Unplace
        </Button>
        <UnplaceFromPoDialog
          open={unplacing}
          onOpenChange={setUnplacing}
          rowId={rowId}
          poNumber={poLabel}
        />
      </>
    );
  }

  if (state !== 'raised' || !PLACEABLE_VERBS.includes(verb)) return null;

  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => setPlacing(true)}>
        <Link2 className="size-3.5" aria-hidden />
        Place on PO
      </Button>
      {placing && (
        <PlaceOnPoDialog
          rowId={rowId}
          itemCode={itemCode}
          qty={qty}
          onDone={() => setPlacing(false)}
        />
      )}
    </>
  );
}
