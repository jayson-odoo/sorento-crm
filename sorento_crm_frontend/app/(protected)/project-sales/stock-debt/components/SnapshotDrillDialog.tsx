'use client';

import * as React from 'react';
import Link from 'next/link';
import { ColumnDef, type RowSelectionState } from '@tanstack/react-table';
import { useQueryClient } from '@tanstack/react-query';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { Skeleton } from '@/components/ui/skeleton';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { STATUS_PILL_BASE } from '@/lib/status-pill';
import { cn } from '@/lib/utils';
import { RequestReserveDialog } from '../../_shared/components/RequestReserveDialog';
import { useOrderInquiryHeaderLines } from '../../_shared/hooks/useOrderInquiry';
import { reserveIneligibleReason } from '../../_shared/lib/reserveEligibility';
import {
  SNAPSHOTS_KEY,
  usePoLinkOptions,
  useSnapshotLinesQuery,
} from '../hooks/useStockDebtSnapshots';
import { poLinkMenu, type PoLinkKind } from '../lib/poLinkWording';
import { buildDemandColumns, sumDemand } from '../lib/stockDebtDemandColumns';
import { signed } from '../lib/stockDebtColumns';
import type {
  SnapshotLine,
  SnapshotOiRow,
  SnapshotRow,
} from '../types/stockDebtSnapshot.types';
import { decisionText } from './SnapshotDecisionPopover';
import { SnapshotDecideControl, type DecideItem } from './SnapshotDecideControl';
import { PoLinkDialog, coveredText } from './PoLinkDialog';

const ACKNOWLEDGE_PERMISSION = 'projects.order_inquiries.acknowledge';
/** AC-LINK-CRM-UI: link / unlink / move a PO line through AutoCount. */
const LINK_PO_PERMISSION = 'projects.stock_debt.link_po';

/** RESERVE-REQ-PICK AC-RP-6 (owner, 30 Oct): an OI row frozen on a line that reads Short 0
 *  (covered or pinned) opens UNTICKED in "Request CS to reserve"; the operator can tick it
 *  back. The OI page passes no such rows. Set false to offer them ticked like any other. */
const PRE_UNTICK_COVERED_LINES = true;

/** A line as one OI group shows it: the frozen line plus only that OI's rows. */
export type GroupLine = SnapshotLine & { group_oi_rows: SnapshotOiRow[] };

interface OiGroup {
  oiId: string | null;
  inquiryNo: string | null;
  lines: GroupLine[];
}

const NEUTRAL = 'bg-muted text-foreground';
const AMBER = 'bg-amber-100 text-amber-800';
const GREEN = 'bg-emerald-100 text-emerald-800';
const RED = 'bg-red-100 text-red-800';

/** OI-RESERVE-USED-ROW (owner, 4 Nov): "Now" is ONE pill per line, the first match wins -
 *  SO cancelled (or gone) > Reserved N > Reserve requested N / Reserve parked N > Open N. The
 *  only live column of the drill: what changed since the snapshot. The OI row's own state
 *  stays on the OI page. Exported for its test. */
export function nowPill(line: GroupLine): { text: string; tone: string } {
  const soStatus = line.now.so_status;
  if (soStatus !== 'open') return { text: `SO ${soStatus ?? 'missing'}`, tone: RED };
  const sum = (state: string) =>
    line.group_oi_rows
      .filter((oi) => oi.reserve_state === state)
      .reduce((total, oi) => total + (oi.reserve_qty ?? 0), 0);
  const has = (state: string) => line.group_oi_rows.some((oi) => oi.reserve_state === state);
  if (has('reserved')) return { text: `Reserved ${sum('reserved').toLocaleString()}`, tone: GREEN };
  if (has('requested')) {
    return { text: `Reserve requested ${sum('requested').toLocaleString()}`, tone: AMBER };
  }
  if (has('parked')) return { text: `Reserve parked ${sum('parked').toLocaleString()}`, tone: AMBER };
  return { text: `Open ${line.now.open_qty.toLocaleString()}`, tone: NEUTRAL };
}

/** AC-LINK-CRM-UI: the PO lines linked to the line now, e.g. "PO 202609-S0029 (120)". */
export function poLinksText(line: GroupLine): string {
  return (line.now.po_links ?? [])
    .map((po) => `PO ${po.po_number} (${po.qty.toLocaleString()})`)
    .join(', ');
}

function NowCell({ line }: { line: GroupLine }) {
  const pill = nowPill(line);
  const links = poLinksText(line);
  return (
    <div className="flex min-w-0 items-center gap-2 overflow-hidden whitespace-nowrap">
      <span className={cn(STATUS_PILL_BASE, 'normal-case whitespace-nowrap', pill.tone)} title={pill.text}>
        {pill.text}
      </span>
      {links ? (
        <p className="truncate text-xs text-muted-foreground" title={links} data-testid="now-po-links">
          {links}
        </p>
      ) : null}
    </div>
  );
}

const LINE_COLUMN: ColumnDef<GroupLine> = {
  id: 'line_no',
  accessorKey: 'line_no',
  header: ({ column }) => <DataGridColumnHeader title="Line" column={column} />,
  size: 70,
  meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
  cell: ({ row }) => <span className="tabular-nums">{row.original.line_no ?? '-'}</span>,
};

function buildColumns(totals: ReturnType<typeof sumDemand>, selectable: boolean): ColumnDef<GroupLine>[] {
  const [salesOrder, ...demand] = buildDemandColumns<GroupLine>(totals);
  return [
    ...(selectable
      ? [
          buildSelectColumn<GroupLine>({
            rowLabel: (row) =>
              `Select ${row.original.so_number}${row.original.line_no != null ? ` line ${row.original.line_no}` : ''}`,
          }),
        ]
      : []),
    salesOrder,
    LINE_COLUMN,
    ...demand,
    {
      id: 'short_qty',
      header: ({ column }) => <DataGridColumnHeader title="Short" column={column} />,
      size: 90,
      meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
      footer: () => totals.short.toLocaleString(),
      cell: ({ row }) => (
        <span className="tabular-nums">{row.original.short_qty.toLocaleString()}</span>
      ),
    },
    {
      id: 'oi_row',
      header: ({ column }) => <DataGridColumnHeader title="OI row" column={column} />,
      size: 110,
      // OI-RESERVE-USED-ROW (owner, 4 Nov): the server sends live rows only, one line per row.
      cell: ({ row }) =>
        row.original.group_oi_rows.length ? (
          <div className="flex flex-nowrap gap-x-2 overflow-hidden whitespace-nowrap">
            {row.original.group_oi_rows.map((oi) => (
              <Link
                key={oi.row_id}
                href={`/project-sales/order-inquiries/${oi.oi_id}?row=${oi.row_id}`}
                target="_blank"
                rel="noreferrer"
                className="font-medium tabular-nums text-primary hover:underline"
              >
                {oi.qty.toLocaleString()}
              </Link>
            ))}
          </div>
        ) : (
          <span className="text-muted-foreground">-</span>
        ),
    },
    {
      id: 'now',
      header: ({ column }) => <DataGridColumnHeader title="Now" column={column} />,
      size: 260,
      cell: ({ row }) => <NowCell line={row.original} />,
    },
  ];
}

/** The shared "Request CS to reserve", fed by the OI's live rows narrowed to this product's
 *  drill rows (frozen, or linked after the snapshot) that the OI page itself would still
 *  accept. Mounted only while open, so the OI is read when asked for. */
function OiRequestDialog({
  oiId,
  drillRowIds,
  coveredRowIds,
  defaultWarehouseId,
  onOpenChange,
  onSent,
}: {
  oiId: string;
  /** This product's rows on the drill: frozen, or linked to its lines after the snapshot. */
  drillRowIds: Set<string>;
  /** Rows (frozen or linked after the snapshot) on lines that read Short 0: they open unticked. */
  coveredRowIds: string[];
  defaultWarehouseId: string | null;
  onOpenChange: (open: boolean) => void;
  onSent: () => void;
}) {
  const live = useOrderInquiryHeaderLines(oiId);
  const rows = React.useMemo(
    () =>
      (live.data ?? []).filter(
        (row) => drillRowIds.has(row.id) && reserveIneligibleReason(row) === null,
      ),
    [live.data, drillRowIds],
  );
  return (
    <RequestReserveDialog
      inquiryId={oiId}
      rows={rows}
      untickedRowIds={coveredRowIds}
      defaultWarehouseId={defaultWarehouseId}
      open
      onOpenChange={onOpenChange}
      onSent={onSent}
    />
  );
}

function OiGroupGrid({
  group,
  snapshotId,
  rowId,
  canRequest,
  canLinkPo,
  defaultWarehouseId,
  onRequested,
}: {
  group: OiGroup;
  snapshotId: string;
  rowId: string;
  canRequest: boolean;
  canLinkPo: boolean;
  defaultWarehouseId: string | null;
  onRequested: () => void;
}) {
  const [requestOpen, setRequestOpen] = React.useState(false);
  const [poDialog, setPoDialog] = React.useState<PoLinkKind | null>(null);
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({});
  const totals = React.useMemo(() => sumDemand(group.lines), [group.lines]);

  // RESERVE-REQ-PICK AC-RP-8 (owner, 30 Oct: "we snapshot the sales order but not the
  // OI"): rows linked after the snapshot count too, ticked like any line still short.
  const drillRowIds = React.useMemo(
    () => new Set(group.lines.flatMap((line) => line.group_oi_rows.map((oi) => oi.row_id))),
    [group.lines],
  );
  const coveredRowIds = React.useMemo(
    () =>
      PRE_UNTICK_COVERED_LINES
        ? group.lines
            .filter((line) => line.short_qty === 0)
            .flatMap((line) => line.group_oi_rows.map((oi) => oi.row_id))
        : [],
    [group.lines],
  );
  const requestable = group.lines.some((line) =>
    line.group_oi_rows.some((oi) => oi.requestable),
  );
  const showRequest = Boolean(group.oiId) && canRequest && requestable;
  const selectable = showRequest || canLinkPo;
  const columns = React.useMemo(() => buildColumns(totals, selectable), [totals, selectable]);

  // OWNER (Lavish v1, 4 Nov): tick the lines first, then Decide.
  const tickedLines = group.lines.filter((line) => rowSelection[line.sales_order_line_id]);
  const tickedIds = new Set(tickedLines.map((line) => line.sales_order_line_id));
  // Request CS to reserve keeps its own popup: the ticked lines' rows open ticked, every other
  // row of the group (and, as before, a covered line's) opens unticked.
  const untickedRowIds = [
    ...new Set([
      ...group.lines
        .filter((line) => !tickedIds.has(line.sales_order_line_id))
        .flatMap((line) => line.group_oi_rows.map((oi) => oi.row_id)),
      ...coveredRowIds,
    ]),
  ];

  // The capabilities are read when the menu opens and while a PO popup is up: never cached.
  const options = usePoLinkOptions(snapshotId, rowId, canLinkPo && (menuOpen || poDialog !== null));
  const menu = poLinkMenu({
    ticked: tickedLines.length,
    linked: tickedLines.filter((line) => (line.now.po_links ?? []).length > 0).length,
    capabilities: options.data?.capabilities ?? null,
    loading: options.isFetching,
    // Crew round 3: every ticked line already covered by POs -> Link greyed, naming them.
    coveredBy:
      tickedLines.length > 0 && tickedLines.every((line) => coveredText(line) !== null)
        ? [...new Set(tickedLines.flatMap((line) => (line.now.po_links ?? []).map((po) => po.po_number)))]
        : null,
  });
  const items: DecideItem[][] = [
    showRequest
      ? [
          {
            key: 'reserve',
            label: 'Request CS to reserve…',
            enabled: tickedLines.length > 0,
            reason: null,
            onSelect: () => setRequestOpen(true),
          },
        ]
      : [],
    canLinkPo
      ? [
          { key: 'link', label: 'Link to PO…', ...menu.link, onSelect: () => setPoDialog('link') },
          { key: 'unlink', label: 'Unlink from PO…', ...menu.unlink, onSelect: () => setPoDialog('unlink') },
          {
            key: 'relink',
            label: 'Move PO to another sales order…',
            ...menu.relink,
            onSelect: () => setPoDialog('relink'),
          },
        ]
      : [],
  ];

  return (
    <>
      <PanelDataGrid<GroupLine>
        title={
          group.oiId ? (
            <Link
              href={`/project-sales/order-inquiries/${group.oiId}`}
              target="_blank"
              rel="noreferrer"
              className="text-primary hover:underline"
            >
              {group.inquiryNo}
            </Link>
          ) : (
            'No OI'
          )
        }
        toolbar={
          selectable ? (
            <div className="flex items-center gap-2">
              {tickedLines.length ? (
                <span className="text-sm text-muted-foreground">{`${tickedLines.length} selected`}</span>
              ) : null}
              <SnapshotDecideControl count={tickedLines.length} items={items} onOpenChange={setMenuOpen} />
            </div>
          ) : undefined
        }
        columns={columns}
        rows={group.lines}
        getRowId={(line) => line.sales_order_line_id}
        {...(selectable ? { rowSelection, onRowSelectionChange: setRowSelection } : {})}
        listingKey="projects.stock_debt.view::snapshot-drill"
        emptyTitle="Nothing is due here"
        pageSize={10}
        // The DialogBody above already owns the scroll viewport (overflow-y-auto).
        scrollerMaxHeight={false}
      />
      {requestOpen && group.oiId && (
        <OiRequestDialog
          oiId={group.oiId}
          drillRowIds={drillRowIds}
          coveredRowIds={untickedRowIds}
          defaultWarehouseId={defaultWarehouseId}
          onOpenChange={setRequestOpen}
          onSent={onRequested}
        />
      )}
      {poDialog && options.data ? (
        <PoLinkDialog
          mode={poDialog}
          snapshotId={snapshotId}
          rowId={rowId}
          lines={tickedLines}
          allLines={group.lines}
          capabilities={options.data.capabilities}
          poLines={options.data.po_lines}
          soBooks={options.data.so_books}
          onClose={() => {
            setPoDialog(null);
            setRowSelection({});
          }}
        />
      ) : null}
    </>
  );
}

/** Lines grouped by the OI they sit on (a line on two OIs shows in both), lines with no OI in
 *  a "No OI" group last. */
function groupByOi(lines: SnapshotLine[]): OiGroup[] {
  const byOi = new Map<string, OiGroup>();
  const noOi: GroupLine[] = [];
  for (const line of lines) {
    if (line.oi_rows.length === 0) {
      noOi.push({ ...line, group_oi_rows: [] });
      continue;
    }
    const rowsByOi = new Map<string, SnapshotOiRow[]>();
    for (const oi of line.oi_rows) rowsByOi.set(oi.oi_id, [...(rowsByOi.get(oi.oi_id) ?? []), oi]);
    for (const [oiId, oiRows] of rowsByOi) {
      let group = byOi.get(oiId);
      if (!group) {
        group = { oiId, inquiryNo: oiRows[0].inquiry_no, lines: [] };
        byOi.set(oiId, group);
      }
      group.lines.push({ ...line, group_oi_rows: oiRows });
    }
  }
  const groups = [...byOi.values()].sort((a, b) =>
    (a.inquiryNo ?? '').localeCompare(b.inquiryNo ?? ''),
  );
  return noOi.length ? [...groups, { oiId: null, inquiryNo: null, lines: noOi }] : groups;
}

/** AC-F5: the frozen drill for one cell (`month`) or one product (`month` null). */
export function SnapshotDrillDialog({
  snapshotId,
  row,
  month,
  label,
  takenAt,
  onClose,
}: {
  snapshotId: string;
  row: SnapshotRow;
  /** The bucket pressed, or null for every bucket. */
  month: string | null;
  /** What the pressed column said, or "all months". */
  label: string;
  takenAt: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const canRequest = useHasPermission(ACKNOWLEDGE_PERMISSION);
  const canLinkPo = useHasPermission(LINK_PO_PERMISSION);
  const lines = useSnapshotLinesQuery(snapshotId, row.row_id, month);
  const stored = React.useMemo(() => lines.data?.lines ?? [], [lines.data]);
  const groups = React.useMemo(() => groupByOi(stored), [stored]);
  const shortTotal = React.useMemo(
    () => stored.reduce((sum, line) => sum + line.short_qty, 0),
    [stored],
  );

  const summary: Array<[string, string]> = [
    ['Total', signed(row.total)],
    ['BRW on hand', row.pool_on_hand.toLocaleString()],
    ['Lines', stored.length.toLocaleString()],
    ['Short', shortTotal.toLocaleString()],
    ['Decision', row.decision ? decisionText(row) : 'None'],
  ];

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        data-testid="snapshot-drill-dialog"
        className="flex max-h-[85dvh] w-full flex-col overflow-hidden p-0 sm:max-w-[95vw]"
      >
        <DialogHeader className="shrink-0 space-y-1 border-b p-4 pe-10 sm:p-6 sm:pe-10">
          <DialogTitle className="min-w-0 break-words">{`${row.product_code} · ${label}`}</DialogTitle>
          <DialogDescription className="truncate text-xs">
            {`As frozen ${formatDateTimeInMalaysia(takenAt)}`}
          </DialogDescription>
          <div className="flex flex-wrap gap-x-5 gap-y-1 pt-1 text-sm">
            {summary.map(([name, value]) => (
              <span key={name}>
                <span className="text-muted-foreground">{name}</span>{' '}
                <span className="font-medium tabular-nums">{value}</span>
              </span>
            ))}
          </div>
        </DialogHeader>
        <DialogBody className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">
          {lines.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          ) : lines.isError ? (
            <p className="text-sm text-destructive">
              {lines.error instanceof Error ? lines.error.message : 'The lines could not be loaded.'}
            </p>
          ) : groups.length === 0 ? (
            <div className="px-6 py-10 text-center">
              <p className="text-sm font-semibold">Nothing is due here</p>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                No sales order line falls in this column.
              </p>
            </div>
          ) : (
            groups.map((group) => (
              <OiGroupGrid
                key={group.oiId ?? 'no-oi'}
                group={group}
                snapshotId={snapshotId}
                rowId={row.row_id}
                canRequest={canRequest}
                canLinkPo={canLinkPo}
                defaultWarehouseId={row.decision_warehouse_id}
                onRequested={() =>
                  queryClient.invalidateQueries({ queryKey: [...SNAPSHOTS_KEY, 'lines', snapshotId] })
                }
              />
            ))
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
