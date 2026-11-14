'use client';

import * as React from 'react';
import { toast } from '@/lib/toast';
import { PoLinkDialog } from '../../_shared/po-link/PoLinkDialog';
import { usePoLinkOptions } from '../../_shared/po-link/usePoLink';
import type { OiPoLinkOptions, PoLinkTarget } from '../../_shared/po-link/poLink.types';
import {
  changeOrderInquiryPoLines,
  getOrderInquiryPoLinkOptions,
  linkOrderInquiryPoLines,
  relocateOrderInquiryPoLine,
  resumeOrderInquiryPoLink,
  unlinkOrderInquiryPoLines,
} from '../../_shared/services/orderInquiryService';

/** The PO link calls for ticked Order Inquiry rows. */
export function oiPoLinkTarget(rowIds: string[]): PoLinkTarget {
  return {
    key: ['project-sales', 'order-inquiries', 'po-link', ...rowIds],
    api: {
      options: () => getOrderInquiryPoLinkOptions(rowIds),
      link: (lines) => linkOrderInquiryPoLines(rowIds, lines),
      unlink: (ids) => unlinkOrderInquiryPoLines(rowIds, ids),
      change: (changes) => changeOrderInquiryPoLines(rowIds, changes),
      relocate: (poLineId) => relocateOrderInquiryPoLine(rowIds, poLineId),
      resume: (input) => resumeOrderInquiryPoLink(rowIds, input),
    },
  };
}

/** The shared Link PO popup (link, change or unlink) for the ticked Order Inquiry rows. Mounted only while it is open,
 *  so the AutoCount capabilities are read fresh each time. */
export function OiPoLinkHost({
  rowIds: rowIdsProp,
  onClose,
}: {
  rowIds: string[];
  onClose: () => void;
}) {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const rowIds = React.useMemo(() => rowIdsProp, [rowIdsProp.join(',')]);
  const target = React.useMemo<PoLinkTarget>(() => oiPoLinkTarget(rowIds), [rowIds]);
  const options = usePoLinkOptions(target, true);
  const data = options.data as OiPoLinkOptions | undefined;
  // The wire names the SO line's bin and delivery date as Stock Debt's drill lines do in the dialog.
  const dialogLines = React.useMemo(
    () =>
      (data?.lines ?? []).map((line) => ({
        ...line,
        warehouse_code: line.warehouse_code ?? line.location_code ?? null,
        required_date: line.required_date ?? line.delivery_date ?? null,
      })),
    [data],
  );
  // The first read decides whether the popup opens at all. Once it is up (and after a write
  // re-reads the options) it stays: the result cards must not vanish because the re-read
  // failed or AutoCount's capabilities changed.
  const [shown, setShown] = React.useState(false);
  React.useEffect(() => {
    if (shown) return;
    if (options.error) {
      toast.error((options.error as Error).message);
      onClose();
    } else if (data) {
      setShown(true);
    }
  }, [shown, options.error, data, onClose]);

  if (!data) return null;
  return (
    <PoLinkDialog
      mode="manage"
      target={target}
      lines={dialogLines}
      allLines={dialogLines}
      capabilities={data.capabilities}
      poLines={data.po_lines}
      soBooks={data.so_books}
      soProducts={data.so_products}
      skipped={data.skipped}
      onClose={onClose}
    />
  );
}
