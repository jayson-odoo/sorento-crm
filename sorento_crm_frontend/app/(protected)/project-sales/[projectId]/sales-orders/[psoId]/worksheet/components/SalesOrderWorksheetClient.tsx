'use client';

import * as React from 'react';
import Link from 'next/link';
import { toast } from '@/lib/toast';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ArrowLeft, Check, ClipboardCopy, Download, OctagonAlert, TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTable,
  CardTitle,
} from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useSalesOrderImportFile,
  useSalesOrderWorksheet,
} from '../../../../../_shared/hooks/useProjectSalesOrders';
import type {
  ProjectSalesOrderFinding,
  SalesOrderWorksheet,
  SalesOrderWorksheetLine,
} from '../../../../../_shared/types/projectSalesOrder.types';
import {
  formatMoney,
  formatQty,
  formatUnitPrice,
  isZeroMoney,
} from '../../../../components/SalesOrderMoney';
import { SalesOrderStatusPill } from '../../../../components/SalesOrderStatusPill';

/** AutoCount's own columns, in AutoCount's own order. The copied text uses these too. */
const WORKSHEET_COLUMNS = [
  'Item',
  'Description',
  'Reserve Qty',
  'Qty',
  'Delivery Date',
  'UOM',
  'U/Price',
  'Disc.',
  'Total',
] as const;

/**
 * Tab separated, raw values, in the document's own order: this text is pasted into
 * AutoCount, not read by a person, so the formatted display values would be wrong here.
 */
export function worksheetAsTabbedText(lines: SalesOrderWorksheetLine[]): string {
  const rows = lines.map((line) =>
    [
      line.item_code ?? '',
      line.description ?? '',
      line.reserve_qty,
      line.qty,
      line.delivery_date ?? '',
      line.uom ?? '',
      line.unit_price,
      line.discount ?? '',
      line.total,
    ].join('\t'),
  );
  return [WORKSHEET_COLUMNS.join('\t'), ...rows].join('\n');
}

/**
 * The AutoCount SO worksheet for one Project SO (PLAN-scm-front-planning 1.2 steps 1-3).
 *
 * It is the document CS hands to AutoCount, shown before it leaves: the six header refs,
 * the lines in AutoCount's column order, and what still stops it being exported. Every
 * block renders whether or not it has content, because "no blocking findings" is the
 * answer CS came for and a missing card does not give it.
 */
export function SalesOrderWorksheetClient({
  projectId,
  psoId,
}: {
  projectId: string;
  psoId: string;
}) {
  const worksheet = useSalesOrderWorksheet(psoId);

  if (worksheet.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (worksheet.isError || !worksheet.data) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          This worksheet could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          {worksheet.error instanceof Error
            ? worksheet.error.message
            : 'The sales order may have been rebuilt or deleted.'}
        </p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <Button type="button" variant="outline" onClick={() => worksheet.refetch()}>
            Try again
          </Button>
          <Button asChild variant="outline">
            <Link href={`/project-sales/${projectId}/sales-orders/${psoId}`}>
              Back to the sales order
            </Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <WorksheetView projectId={projectId} psoId={psoId} worksheet={worksheet.data} />
  );
}

function WorksheetView({
  projectId,
  psoId,
  worksheet,
}: {
  projectId: string;
  psoId: string;
  worksheet: SalesOrderWorksheet;
}) {
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const importFile = useSalesOrderImportFile(psoId);

  const lines = worksheet.lines ?? [];
  const findings = worksheet.findings ?? [];
  // Acknowledged is `acknowledged_at`, which is what the backend's own gate reads. The
  // name beside it is a display field and is absent whenever the acknowledger no longer
  // resolves, which would silently turn a cleared finding back into a blocking one.
  const blocking = findings.filter(
    (finding) => finding.severity === 'hard' && !finding.acknowledged_at,
  );
  const warnings = findings.filter((finding) => finding.severity !== 'hard');
  const reference = worksheet.autocount_doc_no || worksheet.provisional_ref;
  const isPublished = worksheet.status === 'published' || worksheet.status === 'amended';

  // The server owns the rule through `can_export`; the two local conditions only let the
  // disabled button say WHICH of them is in the way rather than refusing in silence.
  const exportHint = !isPublished
    ? 'Publish first'
    : blocking.length > 0
      ? 'Fix the blocking findings first'
      : !worksheet.can_export
        ? 'This worksheet cannot be exported yet'
        : undefined;
  const canExport = !exportHint;

  // The tick on the button is the confirmation; only a refusal needs saying (S7-05).
  const { isCopied, copyToClipboard } = useCopyToClipboard();
  const copy = async () => {
    if (!(await copyToClipboard(worksheetAsTabbedText(lines)))) {
      toast.error('The worksheet could not be copied');
    }
  };

  const columns = React.useMemo<ColumnDef<SalesOrderWorksheetLine>[]>(
    () => [
      {
        id: 'item_code',
        header: ({ column }) => <DataGridColumnHeader title="Item" column={column} />,
        cell: ({ row }) => {
          const text = row.original.item_code || 'Not resolved';
          return (
            <span className="block truncate font-medium" title={text}>
              {text}
            </span>
          );
        },
        size: 170,
        minSize: 130,
        meta: { headerTitle: 'Item', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => {
          const text = row.original.description || '-';
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 320,
        minSize: 160,
        meta: { headerTitle: 'Description', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        id: 'reserve_qty',
        header: ({ column }) => <DataGridColumnHeader title="Reserve Qty" column={column} />,
        // Reserve is a quantity, so it is compared as one: `formatQty` renders any zero,
        // whatever its scale, as "0". Nothing is reserved until Stage 1C names a source,
        // so today every row is muted; a reserved row will stand out on its own.
        cell: ({ row }) => (
          <span
            className={`block truncate tabular-nums ${
              formatQty(row.original.reserve_qty) === '0' ? 'text-muted-foreground' : ''
            }`}
            title={row.original.reserve_qty}
          >
            {formatQty(row.original.reserve_qty)}
          </span>
        ),
        size: 120,
        minSize: 90,
        meta: { headerTitle: 'Reserve Qty', skeleton: <Skeleton className="h-4 w-8" /> },
      },
      {
        id: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate tabular-nums" title={row.original.qty}>
            {formatQty(row.original.qty)}
          </span>
        ),
        size: 100,
        minSize: 70,
        meta: { headerTitle: 'Qty', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Delivery Date" column={column} />,
        cell: ({ row }) =>
          row.original.delivery_date ? (
            <span className="block truncate tabular-nums">
              {formatDateInMalaysia(row.original.delivery_date)}
            </span>
          ) : (
            <span className="text-muted-foreground">No date</span>
          ),
        size: 130,
        minSize: 100,
        meta: { headerTitle: 'Delivery Date', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'uom',
        header: ({ column }) => <DataGridColumnHeader title="UOM" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-muted-foreground">{row.original.uom || '-'}</span>
        ),
        size: 90,
        minSize: 60,
        meta: { headerTitle: 'UOM', skeleton: <Skeleton className="h-4 w-8" /> },
      },
      {
        id: 'unit_price',
        header: ({ column }) => <DataGridColumnHeader title="U/Price" column={column} />,
        cell: ({ row }) => (
          <span
            className={`block truncate tabular-nums ${
              isZeroMoney(row.original.unit_price) ? 'text-muted-foreground' : ''
            }`}
            title={row.original.unit_price}
          >
            {formatUnitPrice(row.original.unit_price)}
          </span>
        ),
        size: 120,
        minSize: 90,
        meta: { headerTitle: 'U/Price', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'discount',
        header: ({ column }) => <DataGridColumnHeader title="Disc." column={column} />,
        cell: ({ row }) => {
          const text = (row.original.discount ?? '').trim();
          return text ? (
            <span className="block truncate tabular-nums" title={text}>
              {text}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          );
        },
        size: 100,
        minSize: 70,
        meta: { headerTitle: 'Disc.', skeleton: <Skeleton className="h-4 w-8" /> },
      },
      {
        id: 'total',
        header: ({ column }) => <DataGridColumnHeader title="Total" column={column} />,
        cell: ({ row }) => {
          const value = formatMoney(row.original.total);
          return (
            <span className="block truncate tabular-nums" title={value}>
              {value}
            </span>
          );
        },
        size: 150,
        minSize: 110,
        meta: { headerTitle: 'Total', skeleton: <Skeleton className="h-4 w-20" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: lines,
    pageCount: Math.ceil(lines.length / pagination.pageSize) || 0,
    getRowId: (row) => String(row.line_no),
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold break-words">{reference}</h2>
            <SalesOrderStatusPill status={worksheet.status} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground break-words">
            {[
              'AutoCount SO worksheet',
              worksheet.area_group || 'No area group',
              worksheet.po_number
                ? `Customer PO ${worksheet.po_number}`
                : 'No customer PO recorded',
            ].join(' · ')}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href={`/project-sales/${projectId}/sales-orders/${psoId}`}>
              <ArrowLeft className="size-4" aria-hidden />
              Back to the sales order
            </Link>
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={copy}
            disabled={!canExport || lines.length === 0}
            title={exportHint}
          >
            {isCopied ? (
              <Check className="size-4" aria-hidden />
            ) : (
              <ClipboardCopy className="size-4" aria-hidden />
            )}
            {isCopied ? 'Copied' : 'Copy for AutoCount'}
          </Button>
          {/* Fetched through the api client, not followed as a link: `import_file_url` is a
              backend path, so an anchor resolves it against this origin and 404s. */}
          <Button
            type="button"
            size="sm"
            onClick={() => importFile.mutate(worksheet.provisional_ref)}
            disabled={!canExport || importFile.isPending}
            title={exportHint}
          >
            <Download className="size-4" aria-hidden />
            Download CSV
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Header fields</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* The header block is the document's own, so `debtor` is taken as the server
              wrote it. Substituting `customer_name` when it is absent would print a name
              on a worksheet whose Debtor line is genuinely blank. */}
          <Field label="Debtor" value={worksheet.header?.debtor} />
          <Field label="Your Ref No." value={worksheet.header?.your_ref_no} />
          <Field label="Our Ref No." value={worksheet.header?.our_ref_no} />
          <Field label="Our QT Ref No." value={worksheet.header?.our_qt_ref_no} />
          <Field label="Terms" value={worksheet.header?.terms} />
          <Field label="Provisional Ref" value={worksheet.provisional_ref} />
        </CardContent>
      </Card>

      <DataGrid
        table={table}
        recordCount={lines.length}
        isLoading={false}
        listingKey="projects.projects.view::project-sales-order-worksheet"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
      >
        <Card>
          <CardHeader className="block space-y-1">
            <p className="text-sm font-medium">Lines</p>
            <p className="text-xs text-muted-foreground">
              {`${lines.length.toLocaleString()} line${lines.length === 1 ? '' : 's'}`}
            </p>
          </CardHeader>

          <CardTable>
            {lines.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <h3 className="text-sm font-semibold">This worksheet has no lines</h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  Rebuild the sales order from its purchase order and delivery schedule.
                </p>
                <Button asChild variant="outline" size="sm" className="mt-4">
                  <Link href={`/project-sales/${projectId}?tab=sales-orders`}>
                    Go to the sales orders
                  </Link>
                </Button>
              </div>
            ) : (
              <DataGridTable />
            )}
          </CardTable>

          <CardFooter className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-baseline gap-2">
              <span className="text-xs text-muted-foreground">Total</span>
              <span
                className="truncate text-sm font-semibold tabular-nums"
                title={worksheet.total_amount}
              >
                {formatMoney(worksheet.total_amount)}
              </span>
            </div>
            {lines.length > pagination.pageSize && <DataGridPagination />}
          </CardFooter>
        </Card>
      </DataGrid>

      <Card className={blocking.length > 0 ? 'border-destructive/50' : undefined}>
        <CardHeader className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="flex min-w-0 items-center gap-2 text-sm">
            <OctagonAlert
              className={`size-4 shrink-0 ${
                blocking.length > 0 ? 'text-destructive' : 'text-muted-foreground'
              }`}
              aria-hidden
            />
            <span className="break-words">Validation</span>
          </CardTitle>
          {blocking.length > 0 && (
            <Badge variant="destructive" appearance="light">
              {blocking.length === 1
                ? '1 finding stops the export'
                : `${blocking.length} findings stop the export`}
            </Badge>
          )}
        </CardHeader>
        <CardContent className="space-y-2">
          {blocking.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
              No blocking findings.
            </p>
          ) : (
            blocking.map((finding) => (
              <FindingRow key={finding.id} finding={finding} tone="hard" />
            ))
          )}

          {warnings.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
              No warnings.
            </p>
          ) : (
            warnings.map((finding) => (
              <FindingRow key={finding.id} finding={finding} tone="warn" />
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function FindingRow({
  finding,
  tone,
}: {
  finding: ProjectSalesOrderFinding;
  tone: 'hard' | 'warn';
}) {
  return (
    <div
      className={`rounded-lg border px-3 py-2.5 ${
        tone === 'hard' ? 'border-destructive/50 bg-destructive/5' : 'border-border'
      }`}
    >
      <div className="flex min-w-0 items-start gap-2">
        {tone === 'hard' ? (
          <OctagonAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
        ) : (
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
        )}
        <div className="min-w-0 space-y-1">
          <p className="break-words text-sm">{finding.detail}</p>
          {finding.line_no != null && (
            <Badge variant="outline" size="sm">{`Line ${finding.line_no}`}</Badge>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value?: string | null }) {
  const text = (value ?? '').trim();
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={`mt-0.5 break-words text-sm ${text ? 'font-medium' : 'text-muted-foreground'}`}
        title={text || undefined}
      >
        {text || 'Not recorded'}
      </p>
    </div>
  );
}
