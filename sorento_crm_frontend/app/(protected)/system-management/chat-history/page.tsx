'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  type ColumnDef,
  type PaginationState,
  type SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Download, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardFooter, CardTable } from '@/components/ui/card';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { buildGroupHeader } from './groupHeader';
import { getChatMessages } from './services/chatHistoryService';
import { useExportChatHistory } from './hooks/useChatHistory';
import { ChatThreadDrawer } from './components/ChatThreadDrawer';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import type {
  ChatHistoryFilters,
  ChatHistoryGroupBy,
  ChatMessageRow,
} from './types/chatHistory.types';

function localInput(offsetHours: number): string {
  const d = new Date(Date.now() - offsetHours * 3600_000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const GROUP_BY_OPTIONS = [
  { value: 'none', label: 'No grouping' },
  { value: 'date', label: 'Group by date' },
  { value: 'contact', label: 'Group by contact' },
  { value: 'contact_date', label: 'Group by contact, then date' },
];

const DIRECTION_OPTIONS = [
  { value: '', label: 'All directions' },
  { value: 'incoming', label: 'Incoming' },
  { value: 'outgoing', label: 'Outgoing' },
];

function LatencyCell({ seconds }: { seconds: number | null }) {
  if (seconds == null) return <span className="text-muted-foreground"> - </span>;
  const variant = seconds > 30 ? 'destructive' : seconds > 10 ? 'warning' : 'success';
  return (
    <Badge variant={variant as never}>
      {seconds < 1 ? `${Math.round(seconds * 1000)}ms` : `${seconds.toFixed(1)}s`}
    </Badge>
  );
}

export default function ChatHistoryPage() {
  // Default to the last 24h - an unbounded scan of this table is never the intent.
  const [dateFrom, setDateFrom] = useState(() => localInput(24));
  const [dateTo, setDateTo] = useState(() => localInput(0));
  const [direction, setDirection] = useState('');
  const [breachedOnly, setBreachedOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [groupBy, setGroupBy] = useState<ChatHistoryGroupBy>('none');

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'sent_at', desc: true }]);
  const [selected, setSelected] = useState<ChatMessageRow | null>(null);

  const filters: ChatHistoryFilters = useMemo(
    () => ({
      date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
      date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
      direction: (direction || undefined) as ChatHistoryFilters['direction'],
      breached_only: breachedOnly || undefined,
    }),
    [dateFrom, dateTo, direction, breachedOnly],
  );

  const { data, isLoading, isPlaceholderData } = useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['chat-history', filters, searchQuery, pagination, sorting, groupBy],
    queryFn: () =>
      getChatMessages(filters, {
        page: pagination.pageIndex + 1,
        limit: pagination.pageSize,
        sort: sorting[0]?.id,
        dir: sorting[0]?.desc ? 'desc' : 'asc',
        query: searchQuery || undefined,
        group_by: groupBy === 'none' ? undefined : groupBy,
      }),
    staleTime: 15_000,
  });

  const exportMutation = useExportChatHistory();

  const resetPage = () => setPagination((p) => ({ ...p, pageIndex: 0 }));

  const columns = useMemo<ColumnDef<ChatMessageRow>[]>(
    () => [
      {
        accessorKey: 'sent_at',
        id: 'sent_at',
        header: ({ column }) => <DataGridColumnHeader title="Time" column={column} />,
        cell: ({ row }) => (
          <span className="whitespace-nowrap">{formatDateTimeInMalaysia(row.original.sent_at)}</span>
        ),
        size: 165,
      },
      {
        accessorKey: 'contact_display',
        id: 'contact_display',
        header: ({ column }) => <DataGridColumnHeader title="Contact" column={column} />,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.contact_display}>
            {row.original.contact_display}
          </span>
        ),
        size: 210,
      },
      {
        accessorKey: 'type',
        id: 'type',
        header: ({ column }) => <DataGridColumnHeader title="Direction" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.type === 'incoming' ? 'secondary' : 'outline'}>
            {row.original.type}
          </Badge>
        ),
        size: 110,
      },
      {
        accessorKey: 'message',
        id: 'message',
        enableSorting: false,
        header: ({ column }) => <DataGridColumnHeader title="Message" column={column} />,
        cell: ({ row }) => (
          <span className="truncate block" title={row.original.message}>
            {row.original.message}
          </span>
        ),
        size: 640,
      },
      {
        accessorKey: 'latency_seconds',
        id: 'latency_seconds',
        enableSorting: false,
        header: ({ column }) => <DataGridColumnHeader title="Latency" column={column} />,
        cell: ({ row }) => <LatencyCell seconds={row.original.latency_seconds} />,
        size: 100,
      },
      {
        accessorKey: 'delivery_status',
        id: 'delivery_status',
        enableSorting: false,
        header: ({ column }) => <DataGridColumnHeader title="Delivery" column={column} />,
        cell: ({ row }) => (
          <span className="text-muted-foreground">{row.original.delivery_status ?? '-'}</span>
        ),
        size: 110,
      },
    ],
    [],
  );

  const renderGroupHeader = useMemo(() => buildGroupHeader(groupBy), [groupBy]);

  const table = useReactTable({
    columns,
    data: data?.data ?? [],
    pageCount: Math.ceil((data?.pagination.total ?? 0) / pagination.pageSize),
    getRowId: (row) => String(row.id),
    state: { pagination, sorting },
    columnResizeMode: 'onChange',
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
  });

  const filtersActive = (direction ? 1 : 0) + (breachedOnly ? 1 : 0);

  const GridToolbar = () => {
    const [inputValue, setInputValue] = useState(searchQuery);
    const applySearch = () => {
      setSearchQuery(inputValue);
      resetPage();
    };
    return (
      <div className="p-4">
        <DataGridListToolbar
          table={table}
          searchSlot={
            <div className="relative">
              <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
              <Input
                placeholder="Message, phone, or name"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && applySearch()}
                className="ps-9 w-full sm:w-64"
              />
              {searchQuery.length > 0 && (
                <Button
                  mode="icon"
                  variant="dim"
                  className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                  onClick={() => {
                    setInputValue('');
                    setSearchQuery('');
                    resetPage();
                  }}
                  aria-label="Clear search"
                >
                  <X />
                </Button>
              )}
            </div>
          }
          filters={{
            kind: 'custom',
            active: filtersActive > 0,
            activeCount: filtersActive,
            content: (
              <div className="space-y-4 w-72">
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <Label htmlFor="from" className="text-xs">From</Label>
                    <Input
                      id="from"
                      type="datetime-local"
                      value={dateFrom}
                      onChange={(e) => {
                        setDateFrom(e.target.value);
                        resetPage();
                      }}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="to" className="text-xs">To</Label>
                    <Input
                      id="to"
                      type="datetime-local"
                      value={dateTo}
                      onChange={(e) => {
                        setDateTo(e.target.value);
                        resetPage();
                      }}
                    />
                  </div>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Direction</Label>
                  <SearchableSelect
                    options={DIRECTION_OPTIONS}
                    value={direction}
                    onChange={(v) => {
                      setDirection(v);
                      resetPage();
                    }}
                    placeholder="All directions"
                  />
                </div>
                <div className="space-y-1" data-testid="chat-history-group-by">
                  <Label className="text-xs">Group by</Label>
                  <SearchableSelect
                    options={GROUP_BY_OPTIONS}
                    value={groupBy}
                    onChange={(v) => {
                      setGroupBy(v as ChatHistoryGroupBy);
                      // Grouping changes the server ordering, so the current
                      // page number no longer refers to the same rows.
                      resetPage();
                    }}
                    placeholder="No grouping"
                  />
                </div>
                <div>
                  <Button
                    variant={breachedOnly ? 'primary' : 'outline'}
                    size="sm"
                    className="w-full"
                    onClick={() => {
                      setBreachedOnly((v) => !v);
                      resetPage();
                    }}
                  >
                    {breachedOnly ? 'Breached only: on' : 'Breached only: off'}
                  </Button>
                  <p className="text-xs text-muted-foreground mt-1">
                    Turns whose reply took longer than the p99 target - shows both the
                    incoming message and its reply.
                  </p>
                </div>
              </div>
            ),
          }}
          exportConfig={false}
          primaryAction={
            <Button
              variant="outline"
              onClick={() => exportMutation.mutate(filters)}
              disabled={exportMutation.isPending}
            >
              <Download className="size-4 mr-2" />
              {exportMutation.isPending ? 'Queueing…' : 'Export CSV'}
            </Button>
          }
        />
      </div>
    );
  };

  return (
    <>
      <Container>
        <PageHeader title="Chat History" />
      </Container>

      <Container>
        <DataGrid
          table={table}
          recordCount={data?.pagination.total ?? 0}
          isLoading={isLoading}
          isPlaceholderData={isPlaceholderData}
          onRowClick={(row: ChatMessageRow) => setSelected(row)}
          standardToolbar={false}
          tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
          renderGroupHeader={renderGroupHeader}
          emptyMessage="No messages in this range. Widen the date range or clear filters - chat history is written by the n8n WhatsApp flow."
        >
          <Card>
            <GridToolbar />
            <CardTable>
              <DataGridTable />
            </CardTable>
            <CardFooter>
              <DataGridPagination />
            </CardFooter>
          </Card>
        </DataGrid>
      </Container>

      <ChatThreadDrawer row={selected} onOpenChange={(open) => !open && setSelected(null)} />
    </>
  );
}
