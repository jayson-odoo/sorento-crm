'use client';

import { useMemo, useState } from 'react';
import { Upload } from 'lucide-react';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import { OrderInquiryUploadDialog } from './OrderInquiryUploadDialog';
import { OutstandingUploadDialog } from './OutstandingUploadDialog';
import { ReorderLevelUploadDialog } from './ReorderLevelUploadDialog';
import type { OutstandingImportKind } from '../services/outstandingImportService';

/**
 * SCM - every file the plan is fed from, as entries on the plans list's Actions menu.
 *
 * Four channels, and the split between them is the point rather than a category: the order
 * book is what the plan is COMPUTED from and changes tomorrow's numbers; the Order Inquiry
 * sheet is what the order book does not carry - where stock lands and which purchase order a
 * sales order is waiting on; the reorder-level feed is neither, it decides WHEN a product
 * appears in the plan at all. The purchase-history and sales-history curation feeds that used
 * to sit alongside Order Inquiry here were retired at ingest-parity-standardisation S4
 * (AC-P4-1): closed history now arrives through the ESB's own document ingest.
 *
 * They live on the LIST rather than on a plan (plan 4.1): a file feeds the next run, not the
 * run already on screen, so a button for it beside a finished plan's own numbers promised
 * something it could not do.
 */

type Channel = OutstandingImportKind | 'order-inquiry' | 'reorder-levels';

// Neither entry says "outstanding" any more, on either book. Each file carries the WHOLE
// book - orders still owed and orders already completed alike - so naming the action after
// half of it described a scope the export never had, and it is what made the captain ask
// which half he was meant to export. Same wording as the dialog these open
// (`OutstandingUploadDialog`'s titles) and as the two list toolbars, so one action is not
// called three things across three screens.
const OUTSTANDING: ReadonlyArray<readonly [OutstandingImportKind, string]> = [
  ['sales-orders', 'Upload sales orders'],
  ['purchase-orders', 'Upload purchase orders'],
] as const;

const CURATION: ReadonlyArray<readonly ['order-inquiry', string]> = [
  ['order-inquiry', 'Upload order inquiry sheet'],
] as const;

// AutoCount owns the reorder level; this feed receives it (S13c).
const CONFIGURATION: ReadonlyArray<readonly ['reorder-levels', string]> = [
  ['reorder-levels', 'Upload reorder levels'],
] as const;

export interface UploadDataActions {
  /** Ready to hand to `DataGridListToolbar`'s `secondaryActions`. */
  actions: ToolbarAction[];
  /** Mount this next to the grid - it is the dialog the chosen action opens. */
  dialogs: React.ReactNode;
}

/**
 * The upload entries, flattened for a toolbar Actions menu, plus the dialog they open.
 *
 * A hook rather than a component so the plans list can put these entries in the SAME menu
 * as Refresh instead of standing a second dropdown beside it.
 *
 * @param onQueued Fired once an order-book or history upload has been QUEUED. There is
 *   nothing to hand back but the job: the five feeds write on the worker now, so counts do
 *   not exist yet when this fires.
 */
export function useUploadDataActions(onQueued?: () => void): UploadDataActions {
  // Which channel's dialog is open, or null. One piece of state rather than six booleans,
  // so two dialogs can never be open at once.
  const [channel, setChannel] = useState<Channel | null>(null);

  const actions = useMemo<ToolbarAction[]>(
    () =>
      [...OUTSTANDING, ...CURATION, ...CONFIGURATION].map(([kind, label]) => ({
        key: kind,
        label,
        icon: Upload,
        onClick: () => setChannel(kind as Channel),
      })),
    [],
  );

  // Mounted only while its own channel is chosen, so each dialog starts from a clean flow
  // rather than whatever the last upload left behind.
  const dialogs = (
    <>
      {channel === 'reorder-levels' ? (
        <ReorderLevelUploadDialog open onOpenChange={(next) => !next && setChannel(null)} />
      ) : null}

      {channel && channel !== 'reorder-levels' && channel !== 'order-inquiry' ? (
        <OutstandingUploadDialog
          open
          onOpenChange={(next) => !next && setChannel(null)}
          kind={channel}
          onQueued={onQueued}
        />
      ) : null}

      {channel === 'order-inquiry' ? (
        <OrderInquiryUploadDialog
          open
          onOpenChange={(next) => !next && setChannel(null)}
          onQueued={onQueued}
        />
      ) : null}
    </>
  );

  return { actions, dialogs };
}
