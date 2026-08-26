'use client';

import * as React from 'react';
import { Link2, Unlink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PLACEABLE_VERBS } from './OrderInquiryVerbPill';
import { LinkDocumentDialog } from './LinkDocumentDialog';
import { UnlinkDialog } from './UnlinkDialog';

/**
 * The row actions for Link PO / Link SPO (PLAN-scm-cs-planning-uat.md section 3.I),
 * shared between purchasing's cross-project worklist and the per-project order inquiry.
 *
 * A row now holds MANY links and keeps its full quantity, so the two actions are no
 * longer exclusive: a partly linked row still has quantity to link AND links to give
 * back, and it offers both. A fully linked row offers Unlink alone (there is nothing left
 * to link); a raised one offers Link alone. Every other row - actioned, cancelled, or a
 * verb this never applies to - renders nothing, because there is no action to take.
 */
export function OrderInquiryRowActions({
  rowId,
  verb,
  state,
  itemCode,
  qty,
  poLabel,
  hasOpenPoLine = true,
}: {
  rowId: string;
  verb: string;
  state: string;
  itemCode?: string | null;
  qty: string;
  /** What to name in the Unlink confirm - the document this row is linked to. */
  poLabel?: string | null;
  /**
   * Whether this row's own product still has an outstanding document line to link (the
   * backend's `has_open_po_line`). Defaults true - an omitted flag never HIDES the offer,
   * only an explicit false does; a "Link PO" that opens on nothing to link reads as a
   * bug, not an empty state.
   */
  hasOpenPoLine?: boolean;
}) {
  const [linking, setLinking] = React.useState(false);
  const [unlinking, setUnlinking] = React.useState(false);

  const linkable =
    (state === 'raised' || state === 'partly_linked') &&
    PLACEABLE_VERBS.includes(verb) &&
    hasOpenPoLine;
  const unlinkable = state === 'placed' || state === 'partly_linked';

  if (!linkable && !unlinkable) return null;

  return (
    <>
      {linkable && (
        <Button type="button" variant="outline" size="sm" onClick={() => setLinking(true)}>
          <Link2 className="size-3.5" aria-hidden />
          Link PO
        </Button>
      )}
      {unlinkable && (
        <Button type="button" variant="outline" size="sm" onClick={() => setUnlinking(true)}>
          <Unlink className="size-3.5" aria-hidden />
          Unlink
        </Button>
      )}
      {linking && (
        <LinkDocumentDialog
          rowId={rowId}
          itemCode={itemCode}
          qty={qty}
          onDone={() => setLinking(false)}
        />
      )}
      <UnlinkDialog
        open={unlinking}
        onOpenChange={setUnlinking}
        rowId={rowId}
        documentNumber={poLabel}
      />
    </>
  );
}
