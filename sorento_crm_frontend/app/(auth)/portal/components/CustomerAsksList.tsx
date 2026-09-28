'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { type ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { ArrowLeft, MessageSquareText } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { AskedAtCell, AskNoteCell, AskStateCell } from '@/components/stock-asks/AskEditCells';
import { SEARCH_DEBOUNCE_MS } from '@/hooks/useDebouncedSearch';
import { toast } from '@/lib/toast';
import {
  BRANCH_LABEL,
  BRANCH_VARIANT,
  notifiedLabel,
  type StockAsk,
  type StockAskPage,
  type StockAskPatch,
} from '@/lib/stock-asks';
import { portalBase } from '../lib/portal-paths';
import {
  NotASalesAgentError,
  listCustomerAsks,
  updateCustomerAsk,
} from '../lib/customer-asks-service';

/**
 * Chatbot stock ask v2 S6 (R9): the stock asks of the customers assigned to this portal
 * contact's sales agent, worked in place - the same State and Note the office sees on the
 * customer's Asks tab.
 */
export function CustomerAsksList({ slug }: { slug?: string | null }) {
  const router = useRouter();
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 20 });
  const [search, setSearch] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState<StockAskPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [notAgent, setNotAgent] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      setQ(search);
      setPagination((p) => ({ ...p, pageIndex: 0 }));
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(() => {
    setLoading(true);
    return listCustomerAsks({ page: pagination.pageIndex + 1, limit: pagination.pageSize, q })
      .then((data) => setPage(data))
      .catch((error: unknown) => {
        if (error instanceof NotASalesAgentError) setNotAgent(true);
        else toast.error(error instanceof Error ? error.message : 'Failed to load customer asks');
      })
      .finally(() => setLoading(false));
  }, [pagination.pageIndex, pagination.pageSize, q]);

  useEffect(() => {
    load();
  }, [load]);

  const save = useCallback(
    (askId: string, patch: StockAskPatch) => {
      updateCustomerAsk(askId, patch)
        .then((updated) => {
          setPage((prev) =>
            prev ? { ...prev, data: prev.data.map((r) => (r.id === updated.id ? updated : r)) } : prev,
          );
          toast.success('Ask updated');
        })
        .catch((error: unknown) =>
          toast.error(error instanceof Error ? error.message : 'Failed to update the ask'),
        );
    },
    [],
  );

  const rows = page?.data ?? [];
  const total = page?.pagination?.total ?? 0;

  const columns = useMemo<ColumnDef<StockAsk>[]>(
    () => [
      {
        id: 'created_at',
        header: 'Asked at',
        size: 215,
        cell: ({ row }) => <AskedAtCell ask={row.original} />,
      },
      {
        id: 'customer_name',
        header: 'Customer',
        size: 170,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.customer_name ?? undefined}>
            {row.original.customer_name || '-'}
          </span>
        ),
      },
      {
        id: 'contact_name',
        header: 'Contact',
        size: 130,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.contact_name ?? undefined}>
            {row.original.contact_name || '-'}
          </span>
        ),
      },
      {
        id: 'product_code',
        header: 'Product',
        size: 140,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.product_name ?? row.original.product_code}>
            {row.original.product_code}
          </span>
        ),
      },
      {
        id: 'quantity',
        header: 'Qty',
        size: 60,
        cell: ({ row }) => <span className="tabular-nums">{row.original.quantity}</span>,
      },
      {
        id: 'branch',
        header: 'Branch',
        size: 185,
        cell: ({ row }) => (
          <Badge variant={BRANCH_VARIANT[row.original.branch] ?? 'secondary'} appearance="light">
            {BRANCH_LABEL[row.original.branch] ?? row.original.branch}
          </Badge>
        ),
      },
      {
        id: 'answer_summary',
        header: 'Answer',
        size: 280,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.answer_summary}>
            {row.original.answer_summary}
          </span>
        ),
      },
      {
        id: 'notified_agent',
        header: 'Notified',
        size: 100,
        cell: ({ row }) => {
          const n = notifiedLabel(row.original);
          return (
            <Badge variant={n.variant} appearance="light" title={n.title}>
              {n.label}
            </Badge>
          );
        },
      },
      {
        id: 'state',
        header: 'State',
        size: 110,
        cell: ({ row }) => (
          <AskStateCell ask={row.original} editable onSave={(patch) => save(row.original.id, patch)} />
        ),
      },
      {
        id: 'note',
        header: 'Note',
        size: 220,
        cell: ({ row }) => (
          <AskNoteCell ask={row.original} editable onSave={(patch) => save(row.original.id, patch)} />
        ),
      },
    ],
    [save],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { pagination },
    onPaginationChange: (updater) =>
      setPagination((prev) => (typeof updater === 'function' ? updater(prev) : updater)),
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => row.id,
    manualPagination: true,
    pageCount: Math.ceil(total / pagination.pageSize) || 1,
    columnResizeMode: 'onChange',
  });

  return (
    <div className="mx-auto w-full max-w-5xl space-y-3 px-3 pt-3 pb-6">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => router.push(portalBase(slug))}>
          <ArrowLeft className="mr-1 size-4" /> Back
        </Button>
        <h1 className="text-lg font-semibold">Customer asks</h1>
      </div>

      {notAgent ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Customer asks are for sales agents only.
          </CardContent>
        </Card>
      ) : (
        <>
          <ListSearchInput
            value={search}
            onChange={setSearch}
            isSettling={loading && Boolean(q)}
            placeholder="Search customer or product..."
            aria-label="Search customer asks"
            className="w-full"
            inputClassName="h-12 text-base"
          />
          {!loading && total === 0 ? (
            <Card>
              <CardContent className="space-y-2 py-8 text-center">
                <MessageSquareText className="mx-auto size-8 text-muted-foreground" />
                <p className="font-medium">No customer asks yet</p>
                {q ? (
                  <Button variant="outline" size="sm" onClick={() => setSearch('')}>
                    Clear search
                  </Button>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Stock questions your customers ask the WhatsApp chatbot are listed here.
                  </p>
                )}
              </CardContent>
            </Card>
          ) : (
            <DataGrid
              table={table}
              recordCount={total}
              isLoading={loading && !page}
              // The portal has no CRM session to keep column preferences under.
              listingKey={null}
              tableLayout={{ width: 'fixed', columnsResizable: true }}
            >
              <Card>
                <CardHeader>
                  <CardTable>
                    <DataGridTable />
                  </CardTable>
                </CardHeader>
                <CardFooter className="flex justify-between border-t px-4 py-3">
                  <DataGridPagination />
                </CardFooter>
              </Card>
            </DataGrid>
          )}
        </>
      )}
    </div>
  );
}
