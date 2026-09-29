'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { type ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { MessageSquareText } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { ListBoardViewToggle } from '@/components/common/ListBoardViewToggle';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import type { ListBoardViewMode } from '@/hooks/useListBoardViewPreference';
import { AskedAtCell, AskNoteCell, AskStateCell } from '@/components/stock-asks/AskEditCells';
import { toast } from '@/lib/toast';
import {
  BRANCH_LABEL,
  BRANCH_VARIANT,
  STATE_OPTIONS,
  notifiedLabel,
  type StockAsk,
  type StockAskPage,
  type StockAskPatch,
  type StockAskState,
} from '@/lib/stock-asks';
import {
  NotASalesAgentError,
  listCustomerAsks,
  updateCustomerAsk,
} from '../lib/customer-asks-service';

/**
 * Chatbot stock ask v2 S6 (R9): the stock asks of the customers assigned to this portal
 * contact's sales agent, worked in place - the same State and Note the office sees on the
 * customer's Asks tab.
 *
 * Fix round 5 (owner, 29 Sep): the body of the landing's Customer asks kind, not a page of
 * its own. The landing's search box feeds `search` (already debounced) and its cards or list
 * choice feeds `view`, so the kind reads like its neighbours: cards by default, the grid in
 * list view, a State filter where their toolbar sits, and no New button (asks come from the
 * chatbot, never from a form).
 */
export function CustomerAsksList({
  search,
  view,
  onViewChange,
}: {
  search: string;
  view: ListBoardViewMode;
  onViewChange: (mode: ListBoardViewMode) => void;
}) {
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 20 });
  const [stateFilter, setStateFilter] = useState<StockAskState | ''>('');
  const [page, setPage] = useState<StockAskPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [notAgent, setNotAgent] = useState(false);
  const q = search.trim();

  // A new search or filter starts again from page 1.
  useEffect(() => {
    setPagination((p) => (p.pageIndex === 0 ? p : { ...p, pageIndex: 0 }));
  }, [q, stateFilter]);

  const load = useCallback(() => {
    setLoading(true);
    return listCustomerAsks({
      page: pagination.pageIndex + 1,
      limit: pagination.pageSize,
      q,
      state: stateFilter || undefined,
    })
      .then((data) => setPage(data))
      .catch((error: unknown) => {
        if (error instanceof NotASalesAgentError) setNotAgent(true);
        else toast.error(error instanceof Error ? error.message : 'Failed to load customer asks');
      })
      .finally(() => setLoading(false));
  }, [pagination.pageIndex, pagination.pageSize, q, stateFilter]);

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

  if (notAgent) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Customer asks are for sales agents only.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="customer-asks-state-filter" className="sr-only">
          Filter by state
        </label>
        <SearchableSelect
          id="customer-asks-state-filter"
          value={stateFilter}
          onChange={(v) => setStateFilter((v || '') as StockAskState | '')}
          options={STATE_OPTIONS}
          placeholder="All states"
          clearable
          size="sm"
          className="w-40"
        />
        <ListBoardViewToggle value={view} onChange={onViewChange} />
      </div>

      {!loading && total === 0 ? (
        <Card>
          <CardContent className="space-y-2 py-8 text-center">
            <MessageSquareText className="mx-auto size-8 text-muted-foreground" />
            <p className="font-medium">No customer asks yet</p>
            {stateFilter ? (
              <Button variant="outline" size="sm" onClick={() => setStateFilter('')}>
                Clear filter
              </Button>
            ) : q ? null : (
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
          {view === 'list' ? (
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
          ) : (
            <>
              <ul className="space-y-2.5">
                {rows.map((ask) => (
                  <li key={ask.id}>
                    <AskCard ask={ask} onSave={(patch) => save(ask.id, patch)} />
                  </li>
                ))}
              </ul>
              {total > pagination.pageSize ? <DataGridPagination /> : null}
            </>
          )}
        </DataGrid>
      )}
    </div>
  );
}

/**
 * One ask as a card, laid out like the landing's submission cards: the product line as the
 * title, the branch badge top-right, customer and contact below, then the chatbot's answer,
 * and the State and Note worked in place at the foot.
 */
function AskCard({ ask, onSave }: { ask: StockAsk; onSave: (patch: StockAskPatch) => void }) {
  const notified = notifiedLabel(ask);
  const title = `${ask.product_code} x ${ask.quantity}`;
  return (
    <div className="relative rounded-lg border px-3.5 py-3 space-y-2">
      <Badge
        variant={BRANCH_VARIANT[ask.branch] ?? 'secondary'}
        appearance="light"
        className="absolute top-2 right-2 max-w-[45%] whitespace-normal text-right leading-tight justify-end"
      >
        {BRANCH_LABEL[ask.branch] ?? ask.branch}
      </Badge>
      <div className="space-y-1 pr-[45%]">
        <p className="text-base font-semibold break-words" title={ask.product_name ?? ask.product_code}>
          {title}
        </p>
        <p className="text-xs text-muted-foreground">
          <AskedAtCell ask={ask} />
        </p>
      </div>
      <div className="space-y-1">
        <p className="text-sm text-foreground/80 break-words">
          <span className="text-muted-foreground">Customer: </span>
          {ask.customer_name || '-'}
        </p>
        <p className="text-sm text-foreground/80 break-words">
          <span className="text-muted-foreground">Contact: </span>
          {ask.contact_name || '-'}
        </p>
        <p className="text-sm text-foreground/80 break-words">{ask.answer_summary}</p>
        <Badge variant={notified.variant} appearance="light" title={notified.title}>
          {notified.label}
        </Badge>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[8rem_1fr]">
        <AskStateCell ask={ask} editable onSave={onSave} />
        <AskNoteCell ask={ask} editable onSave={onSave} />
      </div>
    </div>
  );
}
