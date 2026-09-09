'use client';

import { useMemo, useState } from 'react';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { PackageSearch, Settings } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardHeader,
  CardHeading,
  CardTable,
  CardTitle,
  CardToolbar,
} from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useMockDeferredWindow } from '@/hooks/useMockDeferredWindow';
import { DeferredCountdown } from '@/components/common/DeferredActionButton';
import { useProformaInvoicePacking, useProformaInvoicePackingMutations } from '../../../hooks/useProformaInvoicePacking';
import { EM_DASH, fmtDate, fmtQty, fmtTrimmedDecimal } from '../../../lib/format';
import type { ProformaInvoiceDetail } from '../../../services/proformaInvoiceService';
import type { ProformaInvoicePackingLine } from '../../types/packingLine.types';
import MatchToProductDialog from '../../../components/MatchToProductDialog';

/** Keyed off the read permission plus a stable id, matching the Lines grid's own
 *  `scm.dashboard.view::proforma-invoice-lines` convention next door. */
const LISTING_KEY = 'scm.dashboard.view::proforma-invoice-packing-lines';

function dims(row: ProformaInvoicePackingLine): string {
  const { carton_length_cm: l, carton_width_cm: w, carton_height_cm: h } = row;
  if (l == null && w == null && h == null) return EM_DASH;
  const part = (v: number | null) => (v == null ? EM_DASH : fmtTrimmedDecimal(v, 1));
  return `${part(l)}×${part(w)}×${part(h)}`;
}

/** The Matched cell (AC-B12): a matched row's badge, an unmatched row's Match + Dismiss,
 *  a dismissed row's muted label + Undo dismiss. Its own component (not an inline cell
 *  function) because Dismiss needs its own countdown hook per row. */
function MatchedCell({
  row,
  invoiceId,
  supplierId,
  canAdjust,
}: {
  row: ProformaInvoicePackingLine;
  invoiceId: string;
  supplierId: string | null;
  canAdjust: boolean;
}) {
  const mutations = useProformaInvoicePackingMutations(invoiceId);
  const deferred = useMockDeferredWindow(5);
  const [matching, setMatching] = useState(false);

  if (row.match_state === 'matched') {
    return (
      <Badge variant="success" appearance="light">
        Matched
      </Badge>
    );
  }

  if (row.match_state === 'dismissed') {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Dismissed</span>
        {canAdjust ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="size-6" aria-label="Row options">
                <Settings className="size-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem onClick={() => mutations.undoDismiss(row.id)}>
                Undo dismiss
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    );
  }

  // unmatched
  if (deferred.pending) {
    return (
      <DeferredCountdown
        pending={deferred.pending}
        verb="Dismissing"
        subject={row.item_code}
        onCancel={deferred.cancel}
        className="w-56"
      />
    );
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <Badge variant="secondary" appearance="light" title={row.unmatched_reason ?? undefined}>
        Not in catalogue
      </Badge>
      {canAdjust ? (
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-1.5 text-2xs"
            onClick={() => setMatching(true)}
          >
            Match
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-1.5 text-2xs text-destructive hover:text-destructive"
            onClick={() =>
              deferred.run({
                id: row.id,
                entityType: 'proforma_invoice_packing_line',
                apply: () => mutations.dismiss(row.id),
                undo: () => mutations.undoDismiss(row.id),
              })
            }
          >
            Dismiss
          </Button>
        </div>
      ) : null}
      <MatchToProductDialog
        open={matching}
        onOpenChange={setMatching}
        supplierId={supplierId}
        supplierCode={matching ? row.supplier_code : null}
        supplierLabel={row.description}
        onMatched={() => {
          mutations.match(row.id);
          setMatching(false);
        }}
      />
    </div>
  );
}

/**
 * PI detail's Packing tab (S2, AC-B9-B12): the supplier's packing list as filed, one row
 * per row of the source file, matched to the invoice line whose product it is.
 *
 * Always rendered, with an explicit empty state - "the packing list has not arrived yet"
 * is a normal state (Kailu's packing list lands days after its invoice), not an error.
 */
export function ProformaInvoicePackingTab({
  invoice,
  canAdjust,
  onAttach,
  onReplace,
}: {
  invoice: ProformaInvoiceDetail;
  canAdjust: boolean;
  onAttach: () => void;
  onReplace: () => void;
}) {
  const { data, isLoading } = useProformaInvoicePacking(invoice);
  const rows = data?.rows ?? [];
  const file = data?.file ?? null;

  const columns = useMemo<ColumnDef<ProformaInvoicePackingLine>[]>(
    () => [
      {
        accessorKey: 'row_no',
        header: ({ column }) => <DataGridColumnHeader title="Row" column={column} />,
        size: 60,
        meta: { headerTitle: 'Row', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
      },
      {
        accessorKey: 'supplier_code',
        header: ({ column }) => <DataGridColumnHeader title="Supplier code" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.supplier_code ?? undefined}>
            {row.original.supplier_code || EM_DASH}
          </span>
        ),
        size: 130,
        meta: { headerTitle: 'Supplier code' },
      },
      {
        id: 'product',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => {
          const line = invoice.lines.find((l) => l.id === row.original.proforma_invoice_line_id);
          const code = line?.product_code;
          return code ? (
            <span className="block truncate" title={code}>
              {code}
            </span>
          ) : (
            <span className="text-muted-foreground">{EM_DASH}</span>
          );
        },
        size: 140,
        meta: { headerTitle: 'Product' },
      },
      {
        accessorKey: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.description ?? undefined}>
            {row.original.description || EM_DASH}
          </span>
        ),
        size: 200,
        meta: { headerTitle: 'Description' },
      },
      {
        accessorKey: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        cell: ({ row }) => fmtQty(row.original.qty),
        size: 90,
        meta: { headerTitle: 'Qty', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
        footer: () => fmtQty(rows.reduce((s, r) => s + (r.qty ?? 0), 0)),
      },
      {
        accessorKey: 'cartons',
        header: ({ column }) => <DataGridColumnHeader title="Ctns" column={column} />,
        cell: ({ row }) => (row.original.cartons == null ? EM_DASH : fmtQty(row.original.cartons)),
        size: 80,
        meta: { headerTitle: 'Ctns', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
        footer: () => fmtQty(rows.reduce((s, r) => s + (r.cartons ?? 0), 0)),
      },
      {
        accessorKey: 'pcs_per_carton',
        header: ({ column }) => <DataGridColumnHeader title="Pcs/ctn" column={column} />,
        cell: ({ row }) =>
          row.original.pcs_per_carton == null ? EM_DASH : fmtTrimmedDecimal(row.original.pcs_per_carton, 2),
        size: 90,
        meta: { headerTitle: 'Pcs/ctn', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
      },
      {
        id: 'dims',
        header: ({ column }) => <DataGridColumnHeader title="L×W×H" column={column} />,
        cell: ({ row }) => dims(row.original),
        size: 110,
        meta: { headerTitle: 'L×W×H (cm)', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
      },
      {
        accessorKey: 'cbm_per_carton',
        header: ({ column }) => <DataGridColumnHeader title="CBM/ctn" column={column} />,
        cell: ({ row }) =>
          row.original.cbm_per_carton == null ? EM_DASH : fmtTrimmedDecimal(row.original.cbm_per_carton, 5),
        size: 100,
        meta: { headerTitle: 'CBM/ctn', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
      },
      {
        accessorKey: 'cbm_total',
        header: ({ column }) => <DataGridColumnHeader title="CBM" column={column} />,
        cell: ({ row }) => (row.original.cbm_total == null ? EM_DASH : fmtTrimmedDecimal(row.original.cbm_total, 3)),
        size: 90,
        meta: { headerTitle: 'CBM', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
        footer: () =>
          fmtTrimmedDecimal(
            rows.reduce((s, r) => s + (r.cbm_total ?? 0), 0),
            3,
          ),
      },
      {
        accessorKey: 'net_weight',
        header: ({ column }) => <DataGridColumnHeader title="NW/ctn" column={column} />,
        cell: ({ row }) => (row.original.net_weight == null ? EM_DASH : fmtTrimmedDecimal(row.original.net_weight, 2)),
        size: 90,
        meta: { headerTitle: 'NW/ctn', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
      },
      {
        accessorKey: 'gross_weight',
        header: ({ column }) => <DataGridColumnHeader title="GW/ctn" column={column} />,
        cell: ({ row }) =>
          row.original.gross_weight == null ? EM_DASH : fmtTrimmedDecimal(row.original.gross_weight, 2),
        size: 90,
        meta: { headerTitle: 'GW/ctn', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
      },
      {
        accessorKey: 'total_net_weight',
        header: ({ column }) => <DataGridColumnHeader title="Total NW" column={column} />,
        cell: ({ row }) =>
          row.original.total_net_weight == null ? EM_DASH : fmtTrimmedDecimal(row.original.total_net_weight, 2),
        size: 100,
        meta: { headerTitle: 'Total NW', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
        footer: () =>
          fmtTrimmedDecimal(
            rows.reduce((s, r) => s + (r.total_net_weight ?? 0), 0),
            2,
          ),
      },
      {
        accessorKey: 'total_gross_weight',
        header: ({ column }) => <DataGridColumnHeader title="Total GW" column={column} />,
        cell: ({ row }) =>
          row.original.total_gross_weight == null ? EM_DASH : fmtTrimmedDecimal(row.original.total_gross_weight, 2),
        size: 100,
        meta: { headerTitle: 'Total GW', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
        footer: () =>
          fmtTrimmedDecimal(
            rows.reduce((s, r) => s + (r.total_gross_weight ?? 0), 0),
            2,
          ),
      },
      {
        accessorKey: 'container_no',
        header: ({ column }) => <DataGridColumnHeader title="Container" column={column} />,
        cell: ({ row }) => row.original.container_no || EM_DASH,
        size: 120,
        meta: { headerTitle: 'Container' },
      },
      {
        id: 'matched',
        header: ({ column }) => <DataGridColumnHeader title="Matched" column={column} />,
        cell: ({ row }) => (
          <MatchedCell
            row={row.original}
            invoiceId={invoice.id}
            supplierId={invoice.supplier_id}
            canAdjust={canAdjust}
          />
        ),
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Matched' },
      },
    ],
    [invoice, rows, canAdjust],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  if (isLoading) return null;

  if (!file) {
    return (
      <Card>
        <CardContentEmpty onAttach={onAttach} canAdjust={canAdjust} />
      </Card>
    );
  }

  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      isLoading={false}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage="No packing rows on this file."
      listingKey={LISTING_KEY}
    >
      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>Packing</CardTitle>
            <p className="text-xs text-muted-foreground">
              {file.name} · uploaded {fmtDate(file.uploaded_at)}
            </p>
          </CardHeading>
          {canAdjust ? (
            <CardToolbar>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="icon" aria-label="Packing list options">
                    <Settings className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={onReplace}>Replace packing list</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </CardToolbar>
          ) : null}
        </CardHeader>
        <CardTable>
          <DataGridTable />
        </CardTable>
      </Card>
    </DataGrid>
  );
}

/** "No packing list attached yet" (AC-B10, AC-F3) - the shared empty-state shape this
 *  detail page already uses for its own Packing lists tab (below the fold), a Card with
 *  the CTA that names the next step. */
function CardContentEmpty({ onAttach, canAdjust }: { onAttach: () => void; canAdjust: boolean }) {
  return (
    <div className="flex flex-col items-center gap-3 p-10 text-center">
      <PackageSearch className="size-6 text-muted-foreground" />
      <p className="text-sm font-medium">No packing list attached yet</p>
      {canAdjust ? (
        <Button size="sm" onClick={onAttach}>
          Attach packing list
        </Button>
      ) : null}
    </div>
  );
}

export default ProformaInvoicePackingTab;
