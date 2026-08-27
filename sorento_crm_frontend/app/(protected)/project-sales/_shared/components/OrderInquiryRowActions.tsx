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
  linkedQty,
  linkCount = 0,
  poLabel,
  hasLinkCandidate = true,
}: {
  rowId: string;
  verb: string;
  state: string;
  itemCode?: string | null;
  qty: string;
  /** What is already on documents, so the dialog asks for the remainder. */
  linkedQty?: string | null;
  /** How many links the row holds, so the whole-row Unlink confirm can say. */
  linkCount?: number;
  /** What to name in the Unlink confirm - the document this row is linked to. */
  poLabel?: string | null;
  /**
   * Whether this row has anywhere to link to (the backend's `has_link_candidate`, which
   * counts SPO allocations for an ORDER BACK row and purchase order lines for every
   * linkable row). Defaults true - an omitted flag never HIDES the offer, only an
   * explicit false does; a Link that opens on nothing to link reads as a bug, not an
   * empty state.
   */
  hasLinkCandidate?: boolean;
}) {
  const [linking, setLinking] = React.useState(false);
  const [unlinking, setUnlinking] = React.useState(false);

  const linkable =
    (state === 'raised' || state === 'partly_linked') &&
    PLACEABLE_VERBS.includes(verb) &&
    hasLinkCandidate;
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
          linkedQty={linkedQty}
          onDone={() => setLinking(false)}
        />
      )}
      <UnlinkDialog
        open={unlinking}
        onOpenChange={setUnlinking}
        rowId={rowId}
        documentNumber={poLabel}
        linkCount={linkCount}
      />
    </>
  );
}
