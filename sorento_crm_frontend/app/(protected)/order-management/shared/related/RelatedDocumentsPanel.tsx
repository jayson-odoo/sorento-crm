'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { ColumnDef, SortingState, Updater } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import {
  formatBillingAmount,
  formatDay,
} from '@/app/(protected)/finance/billing-documents/lib/format';
import {
  BILLING_STATUS_LABEL,
  BILLING_TYPE_LABEL,
  type BillingDocumentStatus,
} from '@/app/(protected)/finance/billing-documents/types/billingDocument.types';
import { useRelatedDocuments } from './useRelatedDocuments';
import type {
  RelatedAnchorKind,
  RelatedRow,
  RelatedRowType,
  RelatedSortKey,
} from './relatedDocuments.types';

/**
 * DOC-RELATIONS: the Related tab of a sales order, a delivery order and a billing document, ONE
 * table on all three (owner, mock v2, 27 Oct). Every row names what it is (Sales order,
 * Delivery order, Invoice, Cash sale, Credit note, Debit note) and its number opens it. Each
 * column sorts on the server; a kind the viewer cannot open never arrives.
 */

export const RELATED_TYPE_LABEL: Record<RelatedRowType, string> = {
  sales_order: 'Sales order',
  delivery_order: 'Delivery order',
  ...BILLING_TYPE_LABEL,
};

export function relatedHref(
  row: Pick<RelatedRow, 'kind' | 'id'>,
): string | null {
  if (!row.id) return null;
  if (row.kind === 'sales_order') return `/scm/sales-orders/${row.id}`;
  if (row.kind === 'delivery_order')
    return `/order-management/orders/${row.id}`;
  return `/finance/billing-documents/${row.id}`;
}

function statusLabel(row: RelatedRow): string | null {
  if (!row.status) return null;
  if (row.kind === 'billing_document') {
    return (
      BILLING_STATUS_LABEL[row.status as BillingDocumentStatus] ?? row.status
    );
  }
  // A sales order's status is a stored slug (`open`, `completed`); a DO's is already a name.
  return row.kind === 'sales_order'
    ? row.status.charAt(0).toUpperCase() +
        row.status.slice(1).replace(/_/g, ' ')
    : row.status;
}

const LISTING_KEYS: Record<RelatedAnchorKind, string> = {
  sales_order: 'scm.dashboard.view::related',
  delivery_order: 'order_management.orders.view::related',
  billing_document: 'finance.billing_documents.view::related',
};

const DEFAULT_SORT: SortingState = [{ id: 'doc_date', desc: false }];

export function RelatedDocumentsPanel({
  kind,
  id,
}: {
  kind: RelatedAnchorKind;
  id: string;
}) {
  const router = useRouter();
  const [sorting, setSorting] = useState<SortingState>(DEFAULT_SORT);
  const active = sorting[0] ?? DEFAULT_SORT[0];
  const { data, isLoading, error, refetch } = useRelatedDocuments(
    kind,
    id,
    active.id as RelatedSortKey,
    active.desc ? 'desc' : 'asc',
  );

  const columns = useMemo<ColumnDef<RelatedRow>[]>(
    () => [
      {
        id: 'type',
        accessorKey: 'type',
        header: ({ column }) => (
          <DataGridColumnHeader title="Type" column={column} />
        ),
        size: 140,
        cell: ({ row }) => (
          <Badge variant="info" appearance="light">
            {RELATED_TYPE_LABEL[row.original.type] ?? row.original.type}
          </Badge>
        ),
        meta: { headerTitle: 'Type' },
      },
      {
        id: 'doc_no',
        accessorKey: 'doc_no',
        header: ({ column }) => (
          <DataGridColumnHeader title="Number" column={column} />
        ),
        size: 160,
        cell: ({ row }) => {
          const href = relatedHref(row.original);
          return href ? (
            <Link
              href={href}
              onClick={(e) => e.stopPropagation()}
              className="block truncate font-medium text-primary hover:underline"
              title={row.original.doc_no}
            >
              {row.original.doc_no}
            </Link>
          ) : (
            <span className="block truncate" title={row.original.doc_no}>
              {row.original.doc_no}
            </span>
          );
        },
        meta: { headerTitle: 'Number' },
      },
      {
        id: 'doc_date',
        accessorKey: 'doc_date',
        header: ({ column }) => (
          <DataGridColumnHeader title="Date" column={column} />
        ),
        size: 120,
        cell: ({ row }) => formatDay(row.original.doc_date),
        meta: { headerTitle: 'Date' },
      },
      {
        id: 'status',
        accessorKey: 'status',
        header: ({ column }) => (
          <DataGridColumnHeader title="Status" column={column} />
        ),
        size: 140,
        cell: ({ row }) => {
          const label = statusLabel(row.original);
          return label ? <Badge status={label}>{label}</Badge> : '-';
        },
        meta: { headerTitle: 'Status' },
      },
      {
        id: 'amount',
        accessorKey: 'amount',
        header: ({ column }) => (
          <DataGridColumnHeader title="Amount" column={column} />
        ),
        size: 140,
        cell: ({ row }) =>
          row.original.amount === null
            ? '-'
            : formatBillingAmount(
                row.original.amount,
                row.original.currency_code ?? 'MYR',
              ),
        meta: {
          headerTitle: 'Amount',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
    ],
    [],
  );

  return (
    <PanelDataGrid
      title="Related"
      columns={columns}
      rows={data?.rows ?? []}
      getRowId={(r) => `${r.kind}:${r.id ?? r.doc_no}`}
      listingKey={LISTING_KEYS[kind]}
      isLoading={isLoading}
      error={error}
      onRetry={() => void refetch()}
      paginate={false}
      serverSorting={{
        sorting,
        // One column at a time, never none: a third click would otherwise clear the sort and
        // leave the server's default looking like a choice the reader made.
        onSortingChange: (updater: Updater<SortingState>) =>
          setSorting((current) => {
            const next =
              typeof updater === 'function' ? updater(current) : updater;
            return next.length ? next.slice(0, 1) : current;
          }),
      }}
      emptyTitle="No related documents"
      emptyBody={
        kind === 'billing_document'
          ? 'No sales order, delivery order or other billing document is linked to this one.'
          : 'No other document is linked to this one yet.'
      }
      onRowClick={(r) => {
        const href = relatedHref(r);
        if (href) router.push(href);
      }}
    />
  );
}
