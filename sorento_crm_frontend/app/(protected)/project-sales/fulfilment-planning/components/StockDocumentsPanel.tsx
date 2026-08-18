'use client';

import * as React from 'react';
import Link from 'next/link';
import { ColumnDef } from '@tanstack/react-table';
import { PackageSearch } from 'lucide-react';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { useStockDetail } from '../../_shared/hooks/useFulfilmentPlanning';
import { fromMinor, toMinor } from '../../_shared/lib/supplyComposition';

/**
 * What the numbers on one location row are made of - AutoCount's "Stock Status with Detail".
 *
 * The captain reads this position in AutoCount and then comes here, so the shape is theirs: the
 * arithmetic as a header line, the documents that produce it beneath, and a total that adds back
 * up to the header. A detail view whose total disagrees with its own header is the one thing
 * that would make somebody stop trusting the board.
 *
 * It is a PANEL rather than a dialog because the captain asked for "expandable details instead
 * of clicking in": it renders inside the location row it belongs to, so the position and its
 * documents are on screen together and closing it is the same press that opened it. It scrolls
 * in a region of its own - the live book tops out at 501 documents for one product at one
 * location, and a panel that grows without limit would push the rest of the dialog out of reach.
 *
 * Addressed by IDS. Two products on the live book share the item code `B2155-NL-BLUE`, so a
 * lookup by code would answer confidently about the wrong one.
 */
export function StockDocumentsPanel({
  productId,
  warehouseId,
  itemCode,
  locationCode,
}: {
  productId: string;
  warehouseId: string;
  itemCode: string;
  locationCode: string;
}) {
  const detail = useStockDetail(productId, warehouseId);

  const rows = React.useMemo<StockDetailRow[]>(() => {
    const data = detail.data;
    if (!data) return [];
    return [
      // Keyed by POSITION as well as by id: one sales order can stand behind this location on
      // several of its own lines, so `sales_order_id` alone is not unique and React logged a
      // duplicate-key error for every repeat (measured live at BRW-BB, which returns the same
      // order many times over).
      ...data.sales_orders.map((order, index) => ({
        key: `so-${index}-${order.sales_order_id}`,
        doc_type: 'S/O' as const,
        doc_no: order.so_number,
        sales_order_id: order.sales_order_id,
        party: order.customer_name ?? null,
        project_label: order.project_label ?? null,
        doc_date: order.doc_date ?? null,
        due_date: order.delivery_date ?? null,
        qty: order.so_qty,
        is_covered: Boolean(order.is_covered),
      })),
      ...data.incoming.map((leg, index) => ({
        key: `spo-${index}-${leg.spo_number}`,
        doc_type: 'SPO' as const,
        doc_no: leg.spo_number,
        sales_order_id: null,
        party: leg.supplier_name ?? null,
        project_label: null,
        doc_date: null,
        due_date: leg.expected_date ?? null,
        qty: leg.spo_qty,
        is_covered: false,
      })),
    ];
  }, [detail.data]);

  const columns = React.useMemo<ColumnDef<StockDetailRow>[]>(
    () => [
      {
        id: 'doc_type',
        accessorFn: (row) => row.doc_type,
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => <span className="text-sm font-medium">{row.original.doc_type}</span>,
        // Labels the totals row under the first column, the way a spreadsheet labels its sum.
        footer: () => <span className="text-muted-foreground">Total</span>,
        size: 90,
        minSize: 70,
        meta: { headerTitle: 'Type' },
      },
      {
        id: 'doc_no',
        accessorFn: (row) => row.doc_no,
        header: ({ column }) => <DataGridColumnHeader title="Document" column={column} />,
        cell: ({ row }) =>
          row.original.sales_order_id ? (
            <Link
              href={`/scm/sales-orders/${row.original.sales_order_id}`}
              className="block truncate text-sm font-medium text-primary hover:underline"
              title={row.original.doc_no}
            >
              {row.original.doc_no}
            </Link>
          ) : (
            <span className="block truncate text-sm font-medium" title={row.original.doc_no}>
              {row.original.doc_no}
            </span>
          ),
        size: 150,
        minSize: 120,
        meta: { headerTitle: 'Document' },
      },
      {
        id: 'party',
        accessorFn: (row) => row.party ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Customer / supplier" column={column} />
        ),
        cell: ({ row }) => (
          <span className="block truncate text-sm" title={row.original.party ?? ''}>
            {row.original.party || 'Not recorded'}
          </span>
        ),
        size: 200,
        minSize: 150,
        meta: { headerTitle: 'Customer / supplier' },
      },
      {
        id: 'doc_date',
        accessorFn: (row) => row.doc_date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Doc date" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-sm tabular-nums">
            {row.original.doc_date ? formatDateInMalaysia(row.original.doc_date) : 'Not stated'}
          </span>
        ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Doc date' },
      },
      {
        id: 'due_date',
        accessorFn: (row) => row.due_date ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Delivery / expected" column={column} />
        ),
        cell: ({ row }) => (
          <span className="block truncate text-sm tabular-nums">
            {row.original.due_date ? formatDateInMalaysia(row.original.due_date) : 'Not stated'}
          </span>
        ),
        size: 150,
        minSize: 120,
        meta: { headerTitle: 'Delivery / expected' },
      },
      {
        id: 'qty',
        accessorFn: (row) => Number(row.qty || 0),
        header: ({ column }) => <DataGridColumnHeader title="Quantity" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-sm tabular-nums">{row.original.qty}</span>
        ),
        // Per TYPE, because an S/O subtracts where an SPO adds: one blended total would be a
        // number that matches nothing in the header above it.
        footer: () => (
          <span className="tabular-nums">
            {fromMinor(
              rows
                .filter((row) => row.doc_type === 'S/O')
                .reduce((total, row) => total + toMinor(row.qty), 0),
            )}
          </span>
        ),
        size: 120,
        minSize: 90,
        meta: { headerTitle: 'Quantity' },
      },
      {
        id: 'state',
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        cell: ({ row }) =>
          row.original.is_covered ? (
            // Already met by a confirmed decision, so it is not competing for this stock.
            <span className="rounded bg-emerald-100 px-1 text-[10px] font-medium text-emerald-800">
              Covered
            </span>
          ) : null,
        size: 100,
        minSize: 80,
        enableSorting: false,
        meta: { headerTitle: 'State' },
      },
    ],
    [rows],
  );

  const data = detail.data;

  return (
    <div
      data-testid="stock-documents-panel"
      // Deliberately shorter than the stock table's own 50vh container, so the documents are
      // what scrolls rather than the position above them: measured at an 800px window, a taller
      // panel left the contributing lines a two-row sliver.
      className="max-h-[35vh] space-y-2 overflow-y-auto bg-muted/30 p-3"
    >
      <div className="min-w-0 break-words text-sm font-medium">
        {`${itemCode} · ${locationCode}`}
      </div>

      {data && (
        // The arithmetic IS the header, so the total below can be checked against it by eye.
        // `available_qty` is signed and is printed as it arrives: a negative available is the
        // shortfall, and clamping it would turn the one number that says "this cannot be met"
        // into one that says it can.
        <div
          data-testid="stock-detail-arithmetic"
          className="min-w-0 break-words text-sm font-medium tabular-nums"
        >
          {`On hand ${data.qty_on_hand} - SO ${data.so_qty} + SPO ${data.spo_qty} = Available ${data.available_qty}`}
        </div>
      )}

      {detail.isError ? (
        <p className="py-6 text-center text-sm text-destructive">
          {detail.error instanceof Error
            ? detail.error.message
            : 'The stock detail could not be loaded.'}
        </p>
      ) : detail.isLoading ? (
        <div data-testid="stock-documents-loading" className="space-y-2 py-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ) : rows.length === 0 ? (
        <div className="py-8 text-center">
          <PackageSearch className="mx-auto size-6 text-muted-foreground" aria-hidden />
          <h3 className="mt-2 text-sm font-semibold">Nothing is claiming this stock</h3>
        </div>
      ) : (
        <PanelDataGrid<StockDetailRow>
          title="Documents"
          columns={columns}
          rows={rows}
          getRowId={(row) => row.key}
          listingKey="projects.projects.view::project-stock-detail"
          sortable
          emptyTitle="Nothing is claiming this stock"
          // The live book tops out at 501 rows for one product and location, which is one page:
          // paging it would hide the total that makes the header checkable.
          pageSize={1000}
        />
      )}
    </div>
  );
}

interface StockDetailRow {
  key: string;
  doc_type: 'S/O' | 'SPO';
  doc_no: string;
  sales_order_id: string | null;
  party: string | null;
  project_label: string | null;
  doc_date: string | null;
  due_date: string | null;
  qty: string;
  is_covered: boolean;
}
