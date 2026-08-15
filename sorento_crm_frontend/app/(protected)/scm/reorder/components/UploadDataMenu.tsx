'use client';

import { useState } from 'react';
import { ChevronDown, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { HistoryUploadDialog } from './HistoryUploadDialog';
import { OutstandingUploadDialog } from './OutstandingUploadDialog';
import { ReorderLevelUploadDialog } from './ReorderLevelUploadDialog';
import type { OutstandingImportKind } from '../services/outstandingImportService';
import type { HistoryImportKind } from '../services/purchaseHistoryService';

/**
 * SCM - every file the plan is fed from, behind one control.
 *
 * Four channels, and the split between them is the point rather than a category: the top
 * group is what the plan is COMPUTED from and changes tomorrow's numbers; the bottom group is
 * what the order book does not carry - what was bought historically, where stock lands, and
 * which purchase order a sales order is waiting on.
 *
 * One menu rather than four buttons because they are used on different days: the order book
 * weekly, the history and inquiry sheets when somebody re-exports them. Four permanent
 * buttons would give the rare ones the same weight as the routine one.
 */

type Channel = OutstandingImportKind | HistoryImportKind | 'reorder-levels';

const OUTSTANDING: ReadonlyArray<readonly [OutstandingImportKind, string, string]> = [
  ['sales-orders', 'Outstanding sales orders', 'What customers are waiting for'],
  ['purchase-orders', 'Outstanding purchase orders', 'What suppliers still owe us'],
] as const;

const CURATION: ReadonlyArray<readonly [HistoryImportKind, string, string]> = [
  ['purchase-history', 'Purchase history', 'Past orders, for last cost and slow movers'],
  ['sales-history', 'Sales history', 'Past sales orders. Never counted as demand'],
  ['order-inquiry', 'Order inquiry sheet', 'Stock locations and purchase-order links'],
] as const;

// AutoCount owns the reorder level; this feed receives it (S13c). Its own group because it
// is neither the order book nor history: it is configuration, and it decides WHEN a product
// appears in the plan at all.
const CONFIGURATION: ReadonlyArray<readonly ['reorder-levels', string, string]> = [
  ['reorder-levels', 'Reorder levels (AutoCount)', 'When each product should trigger a buy'],
] as const;

function isHistoryChannel(channel: Channel): channel is HistoryImportKind {
  return (
    channel === 'purchase-history'
    || channel === 'order-inquiry'
    || channel === 'sales-history'
  );
}

export interface UploadDataMenuProps {
  /**
   * Fired once an order-book or history upload has been QUEUED.
   *
   * There is nothing to hand back but the job: the five feeds write on the worker now, so
   * counts do not exist yet when this fires. The outcome is read on the job page, and the
   * upload drawer is already following it.
   */
  onQueued?: () => void;
}

export function UploadDataMenu({ onQueued }: UploadDataMenuProps) {
  // Which channel's dialog is open, or null. One piece of state rather than four booleans,
  // so two dialogs can never be open at once.
  const [channel, setChannel] = useState<Channel | null>(null);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline">
            <Upload className="size-4" />
            Upload data
            <ChevronDown className="size-3.5 opacity-60" aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-72">
          <DropdownMenuLabel>Order book</DropdownMenuLabel>
          {OUTSTANDING.map(([kind, label, hint]) => (
            <DropdownMenuItem key={kind} onSelect={() => setChannel(kind)}>
              <div className="flex flex-col gap-0.5">
                <span>{label}</span>
                <span className="text-2xs text-muted-foreground">{hint}</span>
              </div>
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuLabel>History and linkage</DropdownMenuLabel>
          {CURATION.map(([kind, label, hint]) => (
            <DropdownMenuItem key={kind} onSelect={() => setChannel(kind)}>
              <div className="flex flex-col gap-0.5">
                <span>{label}</span>
                <span className="text-2xs text-muted-foreground">{hint}</span>
              </div>
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuLabel>Configuration</DropdownMenuLabel>
          {CONFIGURATION.map(([kind, label, hint]) => (
            <DropdownMenuItem key={kind} onSelect={() => setChannel(kind)}>
              <div className="flex flex-col gap-0.5">
                <span>{label}</span>
                <span className="text-2xs text-muted-foreground">{hint}</span>
              </div>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Mounted only while its own channel is chosen, so each dialog starts from a clean
          flow rather than whatever the last upload left behind. */}
      {channel === 'reorder-levels' ? (
        <ReorderLevelUploadDialog
          open
          onOpenChange={(next) => !next && setChannel(null)}
        />
      ) : null}

      {channel && channel !== 'reorder-levels' && !isHistoryChannel(channel) ? (
        <OutstandingUploadDialog
          open
          onOpenChange={(next) => !next && setChannel(null)}
          kind={channel}
          onQueued={onQueued}
        />
      ) : null}

      {channel && channel !== 'reorder-levels' && isHistoryChannel(channel) ? (
        <HistoryUploadDialog
          open
          onOpenChange={(next) => !next && setChannel(null)}
          kind={channel}
          onQueued={onQueued}
        />
      ) : null}
    </>
  );
}

export default UploadDataMenu;
