'use client';

import * as React from 'react';
import { toast } from '@/lib/toast';
import {
  OrderSplitsDialog,
  type OrderSplitLine,
} from '../../_shared/components/LineSplitInfo';
import { useLineSplits } from '../../_shared/hooks/useLineSplits';

/**
 * OI-SPLIT-VIEW (UAC D1): the board gear's "View splits <SO number>". Reads the order's split
 * sheet (`GET .../line-splits`, whose lines carry the same `split_view` the SO and OI pages
 * read) and shows the shared whole-order popup once it is in.
 */
export function BoardOrderSplitsDialog({
  psoId,
  soNumber,
  onClose,
  returnFocusRef,
}: {
  psoId: string;
  soNumber: string;
  onClose: () => void;
  /** UAC B8: the board gear, which Escape and Close hand focus back to. */
  returnFocusRef?: React.RefObject<HTMLElement | null>;
}) {
  const { query } = useLineSplits(psoId);
  const lines = React.useMemo<OrderSplitLine[]>(
    () =>
      (query.data?.lines ?? []).flatMap((line) =>
        line.split_view
          ? [
              {
                lineNo: line.line_no,
                itemCode: line.item_code,
                view: line.split_view,
              },
            ]
          : [],
      ),
    [query.data],
  );
  React.useEffect(() => {
    if (!query.isError) return;
    toast.error(
      query.error instanceof Error
        ? query.error.message
        : 'Could not load the splits',
    );
    onClose();
  }, [query.isError, query.error, onClose]);
  if (!query.data) return null;
  return (
    <OrderSplitsDialog
      title={`${soNumber}: splits`}
      lines={lines}
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      returnFocusRef={returnFocusRef}
    />
  );
}
