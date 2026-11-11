'use client';

import * as React from 'react';
import { toast } from '@/lib/toast';
import { PoLinkDialog } from '../../_shared/po-link/PoLinkDialog';
import { usePoLinkOptions } from '../../_shared/po-link/usePoLink';
import type { PoLinkTarget } from '../../_shared/po-link/poLink.types';
import { poLinkMenu, type PoLinkKind } from '../../_shared/po-link/poLinkWording';
import {
  changeOrderInquiryPoLines,
  getOrderInquiryPoLinkOptions,
  linkOrderInquiryPoLines,
  unlinkOrderInquiryPoLines,
} from '../../_shared/services/orderInquiryService';

const MENU_KEY: Record<PoLinkKind, 'link' | 'unlink' | 'relink' | 'change'> = {
  link: 'link',
  unlink: 'unlink',
  relink: 'relink',
  change: 'change',
};

/** The shared PO link popup for the ticked Order Inquiry rows. Mounted only while it is open,
 *  so the AutoCount capabilities are read fresh each time. */
export function OiPoLinkHost({
  kind,
  rowIds: rowIdsProp,
  onClose,
}: {
  kind: PoLinkKind;
  rowIds: string[];
  onClose: () => void;
}) {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const rowIds = React.useMemo(() => rowIdsProp, [rowIdsProp.join(',')]);
  const target = React.useMemo<PoLinkTarget>(
    () => ({
      key: ['project-sales', 'order-inquiries', 'po-link', ...rowIds],
      api: {
        options: () => getOrderInquiryPoLinkOptions(rowIds),
        link: (lines) => linkOrderInquiryPoLines(rowIds, lines),
        unlink: (ids) => unlinkOrderInquiryPoLines(rowIds, ids),
        change: (changes) => changeOrderInquiryPoLines(rowIds, changes),
      },
    }),
    [rowIds],
  );
  const options = usePoLinkOptions(target, true);
  const data = options.data;
  const blocked = React.useMemo(() => {
    if (!data) return null;
    const lines = data.lines ?? [];
    const menu = poLinkMenu({
      ticked: lines.length || 1,
      linked: lines.filter((line) => (line.now?.po_links ?? []).length > 0).length,
      singleLinked: lines.filter((line) => (line.now?.po_links ?? []).length === 1).length,
      capabilities: data.capabilities,
      loading: false,
    });
    const item = menu[MENU_KEY[kind]];
    // Nothing to act on is the popup's own empty state; only AutoCount's refusal blocks.
    return item.enabled || item.reason?.startsWith('No PO linked') || item.reason?.startsWith('Each ticked')
      ? null
      : item.reason;
  }, [data, kind]);

  React.useEffect(() => {
    if (options.error) {
      toast.error((options.error as Error).message);
      onClose();
    } else if (blocked) {
      toast.error(blocked);
      onClose();
    }
  }, [options.error, blocked, onClose]);

  if (!data || blocked) return null;
  return (
    <PoLinkDialog
      mode={kind}
      target={target}
      lines={data.lines ?? []}
      allLines={data.lines ?? []}
      capabilities={data.capabilities}
      poLines={data.po_lines}
      soBooks={data.so_books}
      skipped={data.skipped}
      onClose={onClose}
    />
  );
}
