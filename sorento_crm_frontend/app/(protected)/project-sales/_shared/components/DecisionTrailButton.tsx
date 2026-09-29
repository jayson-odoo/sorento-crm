'use client';

import * as React from 'react';
import { History as HistoryIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DecisionTrailDialog } from './DecisionTrailDialog';
import { useDecisionTrail } from '../hooks/useOrderInquiry';

/**
 * The dialog's own data, split into a component that mounts ONLY once the dialog is open
 * (`DecisionTrailButton` below never renders this until `open`). `useDecisionTrail` calls
 * `useQuery`, which needs a `QueryClientProvider` somewhere above it - real pages always
 * have one, but a column's own unit test rendering a bare cell (most of them, across the
 * worklist, the Lines tab and the board) usually does not. Keeping the query OUT of
 * `DecisionTrailButton` itself means a row that never has its icon clicked never calls
 * `useQuery` at all, so those tests need no provider just because this button exists on
 * the row - only a test that actually opens the dialog does.
 */
function DecisionTrailDialogContainer({
  coreLineId,
  itemCode,
  onOpenChange,
}: {
  coreLineId: string;
  itemCode: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const trail = useDecisionTrail(coreLineId);
  return (
    <DecisionTrailDialog
      open
      onOpenChange={onOpenChange}
      itemCode={itemCode}
      entries={trail.data ?? []}
      isLoading={trail.isLoading}
      // S1 (review round 3): `trail.data ?? []` alone read a loading state and a
      // failed fetch the same as "genuinely nothing recorded" - `getDecisionTrail`
      // already throws `extractApiError`'s own message, so `trail.error` carries it.
      error={trail.error ? trail.error.message : null}
    />
  );
}

/**
 * `PLAN-oi-decision-trail-ui.md` (round 2, owner ruling after hand-testing round 1): the
 * decision trail is a History icon + dialog, the same pattern as the reserve History icon
 * beside it (`ReserveLineHistoryDialog` / `onHistoryClick` in
 * `orderInquiryHeaderLinesColumns.tsx`) - not a popover on the Confirmed chip.
 *
 * SELF-CONTAINED rather than caller-managed (unlike the reserve History icon, which the
 * Lines tab's own staged-reserve state coordinates): this read has no staged state to
 * coordinate with, so the button owns its own `open` flag. One component, three call
 * sites - the OI worklist, the OI detail Lines tab and the fulfilment board (list view and
 * grid cell breakdown) - so a History icon on any of them opens the same dialog the same
 * way.
 *
 * `null` when the row/line names no core sales-order line at all (an amendment-raised row
 * with no `so_line_id`, or a board line the engine has not addressed yet) - there is
 * nothing to trail.
 */
export function DecisionTrailButton({
  coreLineId,
  itemCode,
  className,
}: {
  coreLineId: string | null | undefined;
  itemCode?: string | null;
  className?: string;
}) {
  const [open, setOpen] = React.useState(false);

  if (!coreLineId) return null;

  return (
    <>
      <Button
        type="button"
        mode="icon"
        variant="ghost"
        size="sm"
        className={className ?? 'shrink-0'}
        aria-label="Decision trail"
        title="Decision trail"
        onClick={(event) => {
          event.stopPropagation();
          setOpen(true);
        }}
      >
        <HistoryIcon className="size-3.5" aria-hidden />
      </Button>
      {open ? (
        <DecisionTrailDialogContainer
          coreLineId={coreLineId}
          itemCode={itemCode ?? null}
          onOpenChange={setOpen}
        />
      ) : null}
    </>
  );
}

export default DecisionTrailButton;
