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
import { useFailedChatbotContacts, useShadowTurnList } from './hooks/useChatbotTurns';
import { laneWords, stageLabel } from './turnPresentation';
import { rowDrift } from './shadowDrift';
import { ChatThreadDrawer } from './components/ChatThreadDrawer';
import { TurnDetailDrawer } from './components/TurnDetailDrawer';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import type {
  ChatHistoryFilters,
  ChatHistoryGroupBy,
  ChatMessageRow,
} from './types/chatHistory.types';
import type { ChatbotTurn } from './types/chatbotTurn.types';

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

/** The domains a parse asked about, in the dealer's order. "none" is a real answer. */
function DomainsLine({ domains }: { domains?: string[] | null }) {
  if (domains == null) return <span className="text-muted-foreground">not recorded</span>;
  if (domains.length === 0) return <span className="text-muted-foreground">none</span>;
  return (
    <span className="truncate block" title={domains.join(', ')}>
      {domains.join(', ')}
    </span>
  );
}

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
  // AC-255. Narrows the LIST to contacts whose chatbot turns failed in this range.
  const [failedTurnsOnly, setFailedTurnsOnly] = useState(false);
  // AC-1029 / AC-1030. The shadow window ACROSS contacts: the owner watching a parser
  // promotion is asking whether the new version is safe yet, which no single conversation
  // can answer. On, this page shows shadow turns instead of messages - a filter of the
  // message list could not, because the two have different rows.
  const [shadowOn, setShadowOn] = useState(false);
  const [shadowTurn, setShadowTurn] = useState<ChatbotTurn | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [groupBy, setGroupBy] = useState<ChatHistoryGroupBy>('none');

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'sent_at', desc: true }]);
  const [selected, setSelected] = useState<ChatMessageRow | null>(null);

  const range: ChatHistoryFilters = useMemo(
    () => ({
      date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
      date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
      direction: (direction || undefined) as ChatHistoryFilters['direction'],
      breached_only: breachedOnly || undefined,
    }),
    [dateFrom, dateTo, direction, breachedOnly],
  );

  // AC-255. Only fetched when the filter is on: an aggregate over the whole turn table
  // behind a toggle most operators never touch would be a page-load cost for nothing.
  const {
    byContactId: failedByContact,
    contactIds: failedContactIds,
    isLoading: failedLoading,
    isSuccess: failedLoaded,
  } = useFailedChatbotContacts({ from: range.date_from, to: range.date_to }, failedTurnsOnly);

  // AC-255. The turn aggregate names the contacts; the LIST is then narrowed on the
  // SERVER by sending them back as repeated `contact_id`. Filtering the fetched page in
  // the browser instead left the pager counting rows it had just hidden and the empty
  // state claiming nothing failed when the failures were simply on page two.
  const filters: ChatHistoryFilters = useMemo(
    () => (failedTurnsOnly ? { ...range, contact_id: failedContactIds } : range),
    [range, failedTurnsOnly, failedContactIds],
  );

  // With the filter on there is nothing to ask for until the aggregate has answered, and
  // an empty answer means an empty list - NOT an unfiltered one, which is what sending no
  // `contact_id` would mean to the endpoint.
  const listEnabled = !failedTurnsOnly || (failedLoaded && failedContactIds.length > 0);

  const {
    items: shadowRows,
    summaryLine: shadowSummary,
    isLoading: shadowLoading,
    isError: shadowFailed,
    truncated: shadowTruncated,
    limit: shadowLimit,
  } = useShadowTurnList({ from: range.date_from, to: range.date_to }, shadowOn);

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
    enabled: listEnabled,
    staleTime: 15_000,
  });

  const exportMutation = useExportChatHistory();

  const resetPage = () => setPagination((p) => ({ ...p, pageIndex: 0 }));

  const rows = useMemo(() => (listEnabled ? (data?.data ?? []) : []), [data, listEnabled]);

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
        cell: ({ row }) => {
          const failed = failedByContact.get(row.original.contact_id);
          return (
            <div className="min-w-0">
              <span className="truncate block" title={row.original.contact_display}>
                {row.original.contact_display}
              </span>
              {failed && (
                // AC-255: the row says what stopped last, so the list itself answers
                // "which of these is worth opening" without opening any of them.
                <Badge variant="destructive" appearance="light" size="sm" className="mt-0.5">
                  failed at {stageLabel(failed.last_failed_stage ?? 'received').toLowerCase()}
                  {failed.count > 1 ? ` (${failed.count})` : ''}
                </Badge>
              )}
            </div>
          );
        },
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
    // `failedByContact` is read by the Contact cell (AC-255's last-failed-stage badge).
    // Without it here the columns memo would keep the first, empty map and the badge
    // would never appear - the filter would look like it silently did nothing.
    [failedByContact],
  );

  const renderGroupHeader = useMemo(() => buildGroupHeader(groupBy), [groupBy]);

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil((listEnabled ? (data?.pagination.total ?? 0) : 0) / pagination.pageSize),
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

  const shadowColumns = useMemo<ColumnDef<ChatbotTurn>[]>(
    () => [
      {
        accessorKey: 'created_at',
        id: 'created_at',
        enableSorting: false,
        header: ({ column }) => <DataGridColumnHeader title="Time" column={column} />,
        cell: ({ row }) => (
          <span className="whitespace-nowrap">{formatDateTimeInMalaysia(row.original.created_at)}</span>
        ),
        size: 165,
      },
      {
        accessorKey: 'contact_display',
        id: 'contact_display',
        enableSorting: false,
        header: ({ column }) => <DataGridColumnHeader title="Contact" column={column} />,
        cell: ({ row }) => (
          <span className="truncate block" title={row.original.contact_display ?? undefined}>
            {row.original.contact_display ?? '-'}
          </span>
        ),
        size: 190,
      },
      {
        accessorKey: 'message',
        id: 'message',
        enableSorting: false,
        header: ({ column }) => <DataGridColumnHeader title="Message" column={column} />,
        cell: ({ row }) => (
          <span className="truncate block" title={row.original.message ?? undefined}>
            {row.original.message ?? '-'}
          </span>
        ),
        size: 300,
      },
      {
        id: 'live',
        enableSorting: false,
        header: ({ column }) => <DataGridColumnHeader title="Live" column={column} />,
        cell: ({ row }) => (
          <div className="min-w-0 text-xs">
            <span className="truncate block">
              {row.original.live?.branch_kind ? laneWords(row.original.live.branch_kind) : '-'}
            </span>
            <DomainsLine domains={row.original.live?.domains} />
          </div>
        ),
        size: 190,
      },
      {
        id: 'shadow',
        enableSorting: false,
        header: ({ column }) => <DataGridColumnHeader title="Shadow" column={column} />,
        cell: ({ row }) => (
          <div className="min-w-0 text-xs">
            <span className="truncate block">
              {row.original.branch_kind ? laneWords(row.original.branch_kind) : '-'}
            </span>
            <DomainsLine domains={row.original.domains} />
          </div>
        ),
        size: 190,
      },
      {
        id: 'drift',
        enableSorting: false,
        header: ({ column }) => <DataGridColumnHeader title="Drift" column={column} />,
        cell: ({ row }) => {
          const axes = rowDrift(row.original);
          if (!row.original.live?.id) {
            // No live turn to compare with, and none to open either. `driftAxes` already
            // returns [] here, so "agrees" would be a claim about a comparison that never
            // happened.
            return (
              <Badge
                variant="secondary"
                appearance="light"
                size="sm"
                title="The live turn this shadow was taken of is no longer stored, so there is nothing to compare it with or open."
              >
                no live turn
              </Badge>
            );
          }
          return axes.length > 0 ? (
            <Badge variant="warning" appearance="light" size="sm">
              {axes.join(', ')}
            </Badge>
          ) : (
            <Badge variant="secondary" appearance="light" size="sm">
              agrees
            </Badge>
          );
        },
        size: 140,
      },
    ],
    [],
  );

  const shadowTable = useReactTable({
    columns: shadowColumns,
    data: shadowRows,
    pageCount: 1,
    getRowId: (row) => row.id,
    columnResizeMode: 'onChange',
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualSorting: true,
  });

  const filtersActive = (direction ? 1 : 0) + (breachedOnly ? 1 : 0) + (failedTurnsOnly ? 1 : 0);

  const GridToolbar = () => {
    const [inputValue, setInputValue] = useState(searchQuery);
    const applySearch = () => {
      setSearchQuery(inputValue);
      resetPage();
    };
    return (
      <div className="p-4">
        <DataGridListToolbar
          // The toolbar's Columns control personalises the table it is given, so in shadow
          // mode it has to be the shadow one or it would hide columns nobody can see.
          table={(shadowOn ? shadowTable : table) as typeof table}
          searchSlot={
            // The search reads the MESSAGE list; it has nothing to narrow in the shadow
            // grid, and an inert box is worse than no box.
            shadowOn ? undefined : (
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
            )
          }
          filters={{
            kind: 'custom',
            active: !shadowOn && filtersActive > 0,
            activeCount: shadowOn ? 0 : filtersActive,
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
                {!shadowOn && (
                <>
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
                    variant={failedTurnsOnly ? 'primary' : 'outline'}
                    size="sm"
                    className="w-full"
                    onClick={() => {
                      setFailedTurnsOnly((v) => !v);
                      resetPage();
                    }}
                    aria-pressed={failedTurnsOnly}
                  >
                    {failedTurnsOnly ? 'Failed turns only: on' : 'Failed turns only: off'}
                  </Button>
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
                </>
                )}
              </div>
            ),
          }}
          exportConfig={false}
          primaryAction={
            <div className="flex items-center gap-2">
              <Button
                variant={shadowOn ? 'primary' : 'outline'}
                onClick={() => setShadowOn((v) => !v)}
                aria-pressed={shadowOn}
                title="Compare every turn in this range with the parser version running in the shadow"
              >
                Shadow
              </Button>
              {/* The export writes the MESSAGE list; with the shadow grid up it would hand
                  back rows nobody is looking at. */}
              {!shadowOn && (
                <Button
                  variant="outline"
                  onClick={() => exportMutation.mutate(filters)}
                  disabled={exportMutation.isPending}
                >
                  <Download className="size-4 mr-2" />
                  {exportMutation.isPending ? 'Queueing…' : 'Export CSV'}
                </Button>
              )}
            </div>
          }
        />
        {/* AC-1030. One line, only while the filter is on, over the WHOLE range rather
            than the rows on screen - which is the question being asked. */}
        {shadowOn && (
          <div className="mt-3 text-xs text-muted-foreground" data-testid="shadow-summary">
            {shadowFailed ? (
              <span className="text-destructive">Shadow turns could not be loaded.</span>
            ) : shadowLoading ? (
              'Loading the shadow window…'
            ) : (
              <>
                {shadowSummary ??
                  'No shadow turns in this range. Set a parser shadow version in Settings > Chatbot.'}
                {/* The parities above are over the WHOLE range; these rows are one page of
                    it. Said out loud, because a capped list and a complete one look the
                    same and the reader is using the rows to explain the number. */}
                {shadowTruncated && (
                  <span className="ms-2" data-testid="shadow-truncated">
                    Newest {shadowLimit} shown; narrow the date range to see the rest.
                  </span>
                )}
              </>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <>
      <Container>
        <PageHeader title="Chat History" />
      </Container>

      <Container>
        {shadowOn ? (
          <DataGrid
            table={shadowTable}
            recordCount={shadowRows.length}
            isLoading={shadowLoading}
            // A shadow row opens the LIVE turn beside it, so a row whose live turn has
            // been deleted has nothing to open. It stays in the list - its drift badge is
            // still evidence - and says so in the Drift cell instead of taking a press
            // that would do nothing.
            onRowClick={(row: ChatbotTurn) => setShadowTurn(row)}
            isRowClickable={(row: ChatbotTurn) => Boolean(row.live?.id)}
            standardToolbar={false}
            tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
            emptyMessage={
              shadowFailed
                ? 'Shadow turns could not be loaded. Reload the page to try again.'
                : 'No shadow turns in this range. Set a parser shadow version in Settings > Chatbot.'
            }
          >
            <Card>
              <GridToolbar />
              <CardTable>
                <DataGridTable />
              </CardTable>
            </Card>
          </DataGrid>
        ) : (
        <DataGrid
          table={table}
          recordCount={listEnabled ? (data?.pagination.total ?? 0) : 0}
          isLoading={isLoading || (failedTurnsOnly && failedLoading)}
          isPlaceholderData={isPlaceholderData}
          onRowClick={(row: ChatMessageRow) => setSelected(row)}
          standardToolbar={false}
          tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
          renderGroupHeader={renderGroupHeader}
          emptyMessage={
            failedTurnsOnly
              ? (failedLoading
                  ? 'Looking for failed turns…'
                  : 'No chatbot turns failed in this range.')
              : 'No messages in this range. Widen the date range or clear filters - chat history is written by the n8n WhatsApp flow.'
          }
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
        )}
      </Container>

      <ChatThreadDrawer row={selected} onOpenChange={(open) => !open && setSelected(null)} />

      {/* The SAME drawer a turn opens from inside a conversation, with the shadow parse
          beside the live one. The row is the shadow turn, so the live turn is the one
          opened: the customer got that answer, and the shadow is what is being judged. */}
      <TurnDetailDrawer
        turnId={shadowTurn?.live?.id ?? null}
        shadowTurnId={shadowTurn?.id ?? null}
        onOpenChange={(open) => !open && setShadowTurn(null)}
      />
    </>
  );
}
