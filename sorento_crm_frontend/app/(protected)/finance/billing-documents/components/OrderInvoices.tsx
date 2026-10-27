'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import type { ColumnDef, SortingState, Updater } from '@tanstack/react-table';
import { useRouter } from 'next/navigation';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { useBillingDocumentsQuery } from '../hooks/useBillingDocuments';
import { formatBillingAmount, formatDay } from '../lib/format';
import { useCanViewOutstanding } from '../lib/permissions';
import type { BillingDocumentListRow } from '../types/billingDocument.types';
import { BillingStatusBadge, BillingTypeBadge } from './BillingBadges';
import { OutstandingCell } from './OutstandingCell';

const DEFAULT_SORT: SortingState = [{ id: 'doc_date', desc: true }];

/**
 * The Invoices tab of a sales order (UAC S3-1) and of a delivery order (DOC-RELATIONS): the
 * billing documents of that order however they reach it (its lines, its number, or one of its
 * DOs) plus the notes against them, unpaged because one order has a handful. Every column sorts
 * on the server (owner rule 27 Oct). The caller hides the tab without the view slug;
 * Outstanding follows OUTSTANDING_VIEW_SLUG.
 */
export function OrderInvoices(
  props:
    | { salesOrderId: string; deliveryOrderId?: never }
    | { deliveryOrderId: string; salesOrderId?: never },
) {
  const router = useRouter();
  const canSeeOutstanding = useCanViewOutstanding();
  const [sorting, setSorting] = useState<SortingState>(DEFAULT_SORT);
  const { data, isLoading, error, refetch } = useBillingDocumentsQuery({
    pageIndex: 0,
    pageSize: 100,
    sorting,
    searchQuery: '',
    salesOrderId: props.salesOrderId,
    deliveryOrderId: props.deliveryOrderId,
  });

  const columns = useMemo<ColumnDef<BillingDocumentListRow>[]>(
    () => [
      {
        id: 'document_type', accessorKey: 'document_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        size: 130,
        cell: ({ row }) => <BillingTypeBadge type={row.original.document_type} />,
        meta: { headerTitle: 'Type' },
      },
      {
        id: 'doc_no', accessorKey: 'doc_no',
        header: ({ column }) => <DataGridColumnHeader title="Number" column={column} />,
        size: 140,
        cell: ({ row }) => (
          <Link
            href={`/finance/billing-documents/${row.original.id}`}
            onClick={(e) => e.stopPropagation()}
            className="block truncate font-medium text-primary hover:underline"
            title={row.original.doc_no}
          >
            {row.original.doc_no}
          </Link>
        ),
        meta: { headerTitle: 'Number' },
      },
      { id: 'doc_date', accessorKey: 'doc_date', header: ({ column }) => <DataGridColumnHeader title="Date" column={column} />, size: 110, cell: ({ row }) => formatDay(row.original.doc_date), meta: { headerTitle: 'Date' } },
      {
        id: 'total', accessorKey: 'total',
        header: ({ column }) => <DataGridColumnHeader title="Total" column={column} />,
        size: 140,
        cell: ({ row }) => formatBillingAmount(row.original.total, row.original.currency_code),
        meta: { headerTitle: 'Total', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      ...(canSeeOutstanding
        ? [
            {
              id: 'outstanding', accessorKey: 'outstanding',
              header: ({ column }) => <DataGridColumnHeader title="Outstanding" column={column} />,
              size: 140,
              cell: ({ row }) => (
                <OutstandingCell
                  outstanding={row.original.outstanding}
                  currencyCode={row.original.currency_code}
                />
              ),
              meta: { headerTitle: 'Outstanding', headerClassName: 'text-right', cellClassName: 'text-right' },
            } as ColumnDef<BillingDocumentListRow>,
          ]
        : []),
      {
        id: 'status', accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 120,
        cell: ({ row }) => <BillingStatusBadge status={row.original.status} />,
        meta: { headerTitle: 'Status' },
      },
    ],
    [canSeeOutstanding],
  );

  return (
    <PanelDataGrid
      title="Invoices"
      columns={columns}
      rows={data?.data ?? []}
      getRowId={(r) => r.id}
      listingKey={
        props.deliveryOrderId
          ? 'finance.billing_documents.view::delivery-order'
          : 'finance.billing_documents.view::sales-order'
      }
      isLoading={isLoading}
      error={error}
      onRetry={() => void refetch()}
      paginate={false}
      serverSorting={{
        sorting,
        // One column at a time, never none (the list's own rule).
        onSortingChange: (updater: Updater<SortingState>) =>
          setSorting((current) => {
            const next = typeof updater === 'function' ? updater(current) : updater;
            return next.length ? next.slice(0, 1) : current;
          }),
      }}
      emptyTitle="No invoices"
      emptyBody={
        props.deliveryOrderId
          ? 'No billing documents point at this delivery order yet.'
          : 'No billing documents point at this order yet.'
      }
      onRowClick={(r) => router.push(`/finance/billing-documents/${r.id}`)}
    />
  );
}
