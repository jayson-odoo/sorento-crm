'use client';

import * as React from 'react';
import { type ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { Badge } from '@/components/ui/badge';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { formatDateInMalaysia } from '@/lib/helpers';
import { DecisionTrailEntries } from '../../../_shared/components/DecisionTrailDialog';
import {
  useDecisionTrail,
  useOrderInquiryHeaderCancelledRows,
} from '../../../_shared/hooks/useOrderInquiry';
import {
  lineHistoryEntries,
  type LineHistoryEntry,
  type OrderInquiryLine,
} from '../../../_shared/lib/orderInquiryLineFold';
import { formatInquiryQty } from '../../../_shared/lib/orderInquiryWorklist';
import type { OrderInquiryReserveHistoryEntry } from '../../../_shared/services/orderInquiryReserveService';
import { documentsOf } from '../../components/orderInquiryWorklistColumns';
import { ReserveHistoryEntries } from './ReserveLineHistoryDialog';

/**
 * `PLAN-oi-no-double-count-25sep.md` S0 (issue #1248), AC-ND-13..16, owner rulings 26 Sep
 * 2026: ONE History dialog per sales order line (G2), opened from the line's one History
 * icon, with line tabs Rows | Decisions | Reserve (G3). It replaces the reserve History
 * dialog and the decision trail dialog on this screen; the board and the worklist keep
 * `DecisionTrailButton` as they are.
 *
 * Rows lists the line's live rows as Now, then every row that is not the line's current
 * need, newest first - the used row included (G1, G6). It is the only place the Was / now
 * story shows. The Decisions tab is the #1244 trail (`DecisionTrailEntries`, the same body
 * `DecisionTrailDialog` renders); Reserve is `ReserveHistoryEntries`, present only when
 * the line has reserve history.
 */

const WHAT_VARIANT: Record<LineHistoryEntry['what'], 'primary' | 'secondary' | 'outline'> = {
  Now: 'primary',
  Used: 'secondary',
  Superseded: 'outline',
  'Re-raised': 'outline',
  Cancelled: 'outline',
  'Cancel balance': 'outline',
  'Line cancelled': 'secondary',
};

function documentsText(entry: LineHistoryEntry): string {
  return [...documentsOf(entry.row, 'po'), ...documentsOf(entry.row, 'spo')]
    .map((doc) => doc.document)
    .join(', ');
}

function Truncated({ text }: { text: string }) {
  if (!text) return <span className="text-muted-foreground">-</span>;
  return (
    <span className="block truncate" title={text}>
      {text}
    </span>
  );
}

const COLUMNS: ColumnDef<LineHistoryEntry>[] = [
  {
    id: 'when',
    header: 'When',
    size: 120,
    enableSorting: false,
    meta: { headerTitle: 'When' },
    cell: ({ row }) =>
      row.original.row.raised_at ? (
        <span className="whitespace-nowrap">{formatDateInMalaysia(row.original.row.raised_at)}</span>
      ) : (
        <span className="text-muted-foreground">-</span>
      ),
  },
  {
    id: 'qty',
    header: 'Qty',
    size: 72,
    enableSorting: false,
    meta: { headerTitle: 'Qty' },
    cell: ({ row }) => (
      <span className="tabular-nums">{formatInquiryQty(row.original.row.qty)}</span>
    ),
  },
  {
    id: 'what',
    header: 'What',
    size: 130,
    enableSorting: false,
    meta: { headerTitle: 'What' },
    cell: ({ row }) => (
      <Badge variant={WHAT_VARIANT[row.original.what]} appearance="light" size="sm">
        {row.original.what}
      </Badge>
    ),
  },
  {
    id: 'document',
    header: 'Document',
    size: 170,
    enableSorting: false,
    meta: { headerTitle: 'Document' },
    cell: ({ row }) => <Truncated text={documentsText(row.original)} />,
  },
  {
    id: 'why',
    header: 'Why',
    size: 320,
    enableSorting: false,
    meta: { headerTitle: 'Why' },
    cell: ({ row }) => <Truncated text={row.original.why} />,
  },
];

function LineRowsGrid({ entries }: { entries: LineHistoryEntry[] }) {
  const table = useReactTable({
    columns: COLUMNS,
    data: entries,
    getRowId: (entry) => entry.row.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });
  const hasEarlier = entries.some((entry) => entry.what !== 'Now');
  return (
    <div className="space-y-2">
      {/* The DataGrid's own internal scroller is the one horizontal-scroll surface
          (AC-ND-18): at 375 the five columns scroll sideways inside it, never the page. */}
      <DataGrid
        table={table}
        recordCount={entries.length}
        tableLayout={{
          width: 'fixed',
          columnsResizable: true,
          // A fixed five-column read of one line's rows, always in time order: there is
          // no saved column preference here for a drag to persist into.
          columnsDraggable: false,
          // The DialogBody owns the vertical scroll viewport.
          scrollerMaxHeight: false,
        }}
      >
        <DataGridTable />
      </DataGrid>
      {hasEarlier ? null : (
        <p className="text-sm text-muted-foreground">No earlier rows for this line.</p>
      )}
    </div>
  );
}

function titleOf(line: OrderInquiryLine): string {
  const item = line.primary.item_code;
  const so = line.primary.so_number;
  const where = so ? ` (${so}${line.lineNo != null ? ` L${line.lineNo}` : ''})` : '';
  return `History${item ? ` - ${item}` : ''}${where}`;
}

export function OrderInquiryLineHistoryDialog({
  inquiryId,
  line,
  onOpenChange,
  reserveEntries,
}: {
  inquiryId: string;
  line: OrderInquiryLine;
  onOpenChange: (open: boolean) => void;
  /** The line's reserve request history; `undefined` when the line has none, which drops
   * the Reserve tab (AC-ND-14). */
  reserveEntries?: OrderInquiryReserveHistoryEntry[];
}) {
  const cancelled = useOrderInquiryHeaderCancelledRows(inquiryId);
  const coreLineId = line.primary.core_line_id ?? null;
  const trail = useDecisionTrail(coreLineId);
  const entries = React.useMemo(
    () => lineHistoryEntries(line, cancelled.data ?? []),
    [line, cancelled.data],
  );
  // Review S2: until the cancelled rows arrive (or when they fail), "No earlier rows"
  // would be untrue, so the tab shows the load or the error instead.
  let rowsBody: React.ReactNode;
  if (cancelled.isLoading) rowsBody = <SectionSkeleton />;
  else if (cancelled.isError) {
    rowsBody = <p className="text-sm text-destructive">{cancelled.error.message}</p>;
  } else rowsBody = <LineRowsGrid entries={entries} />;

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85dvh] flex-col sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{titleOf(line)}</DialogTitle>
          <DialogDescription className="sr-only">
            Every row, decision and reserve behind this sales order line
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="min-w-0 flex-1 overflow-y-auto">
          <Tabs defaultValue="rows" className="w-full min-w-0">
            <TabsList variant="line" className="mb-3 w-full justify-start">
              <TabsTrigger value="rows">Rows</TabsTrigger>
              <TabsTrigger value="decisions">Decisions</TabsTrigger>
              {reserveEntries ? <TabsTrigger value="reserve">Reserve</TabsTrigger> : null}
            </TabsList>
            <TabsContent value="rows" className="mt-0 min-w-0">
              {rowsBody}
            </TabsContent>
            <TabsContent value="decisions" className="mt-0">
              {coreLineId ? (
                <DecisionTrailEntries
                  entries={trail.data ?? []}
                  isLoading={trail.isLoading}
                  error={trail.error ? trail.error.message : null}
                />
              ) : (
                <p className="text-sm text-muted-foreground">No decisions recorded for this line.</p>
              )}
            </TabsContent>
            {reserveEntries ? (
              <TabsContent value="reserve" className="mt-0">
                <ReserveHistoryEntries entries={reserveEntries} />
              </TabsContent>
            ) : null}
          </Tabs>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

export default OrderInquiryLineHistoryDialog;
