'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { Container } from '@/components/common/container';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { PageHeader } from '@/components/common/PageHeader';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useIdeaMutations, useIdeasQuery } from '@/hooks/useIdeas';
import { formatDate } from '@/lib/helpers';
import { IDEA_STATUS_FILTER_OPTIONS } from '@/services/ideasService';
import type { Idea } from '@/types/ideas';
import { IdeaCaptureModal } from './IdeaCaptureModal';
import { IdeaStatusBadge } from './IdeaStatusBadge';
import { IdeasViewToggle } from './IdeasViewToggle';
import { VoteBox } from './VoteBox';
import { IDEAS_VIEW_PERMISSION } from './ideasAccess';

const SOURCE_LABEL: Record<string, string> = {
  whatsapp: 'WhatsApp',
  manual: 'Manual',
  email: 'Email',
  web: 'Web',
};

/** Ideas > list: the vote box leads every row; the whole row opens the idea. */
export function IdeasListView() {
  const [modalOpen, setModalOpen] = useState(false);
  const [status, setStatus] = useState('');
  const {
    value: searchQuery,
    setValue: setSearchQuery,
    debouncedValue: debouncedSearch,
    isSettling,
  } = useDebouncedSearch();
  const { data, isLoading, isFetching, isError, error } = useIdeasQuery({
    query: debouncedSearch,
    status,
  });
  const { vote } = useIdeaMutations();
  const rows = useMemo<Idea[]>(() => data ?? [], [data]);

  const columns = useMemo<ColumnDef<Idea>[]>(
    () => [
      {
        id: 'votes',
        header: ({ column }) => <DataGridColumnHeader title="Votes" column={column} />,
        cell: ({ row }) => (
          <VoteBox
            count={row.original.upvotes}
            voted={row.original.myVote === 'up'}
            disabled={!!row.original.mergedIntoId}
            onVote={() => vote.mutate(row.original.id)}
          />
        ),
        size: 80,
        enableSorting: false,
        enableResizing: false,
        meta: { headerTitle: 'Votes', skeleton: <Skeleton className="h-9 w-10" /> },
      },
      {
        id: 'idea',
        header: ({ column }) => <DataGridColumnHeader title="Idea" column={column} />,
        cell: ({ row }) => {
          const label = row.original.title ?? row.original.problem;
          return (
            <Link
              href={`/ideas/${row.original.id}`}
              onClick={(e) => e.stopPropagation()}
              className="block truncate font-medium text-primary hover:underline"
              title={label}
            >
              {label}
            </Link>
          );
        },
        size: 420,
        enableSorting: false,
        meta: { headerTitle: 'Idea', skeleton: <Skeleton className="h-4 w-56" /> },
      },
      {
        id: 'ideaNumber',
        header: ({ column }) => <DataGridColumnHeader title="No." column={column} />,
        cell: ({ row }) => (
          <span className="block truncate tabular-nums text-muted-foreground" title={row.original.ideaNumber ?? ''}>
            {row.original.ideaNumber ?? '-'}
          </span>
        ),
        size: 110,
        enableSorting: false,
        meta: { headerTitle: 'No.', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'product',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.productName}>
            {row.original.productName}
          </span>
        ),
        size: 150,
        enableSorting: false,
        meta: { headerTitle: 'Product', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'submitter',
        header: ({ column }) => <DataGridColumnHeader title="Submitter" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.submitterName}>
            {row.original.submitterName}
          </span>
        ),
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Submitter', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'source',
        header: ({ column }) => <DataGridColumnHeader title="Channel" column={column} />,
        cell: ({ row }) => (
          <Badge variant="outline" size="sm">
            {SOURCE_LABEL[row.original.source] ?? row.original.source}
          </Badge>
        ),
        size: 120,
        enableSorting: false,
        meta: { headerTitle: 'Channel', skeleton: <Skeleton className="h-5 w-16" /> },
      },
      {
        id: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <span className="flex items-center gap-1.5">
            <IdeaStatusBadge label={row.original.statusLabel} color={row.original.statusColor} />
            {row.original.mergedIntoId ? (
              <Badge variant="outline" size="sm">
                Merged
              </Badge>
            ) : null}
          </span>
        ),
        size: 190,
        enableSorting: false,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-5 w-16" /> },
      },
      {
        id: 'createdAt',
        header: ({ column }) => <DataGridColumnHeader title="Captured" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{formatDate(row.original.createdAt)}</span>,
        size: 120,
        enableSorting: false,
        meta: { headerTitle: 'Captured', skeleton: <Skeleton className="h-4 w-20" /> },
      },
    ],
    [vote],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    enableSorting: false,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const emptyMessage =
    debouncedSearch || status ? (
      'No ideas match these filters.'
    ) : (
      <div className="flex w-full flex-col items-center gap-1 py-6">
        <span className="text-sm font-medium">No ideas yet</span>
        <span className="text-sm text-muted-foreground">Captured ideas appear here.</span>
      </div>
    );

  return (
    <>
      <Container>
        <PageHeader
          title="Ideas"
          actions={
            <Button variant="primary" onClick={() => setModalOpen(true)}>
              <Plus className="size-4" />
              Capture idea
            </Button>
          }
        />
      </Container>
      <Container>
        <div className="space-y-3">
          {isError ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              {error instanceof Error ? error.message : 'Failed to load ideas.'}
            </div>
          ) : null}
          <DataGrid
            table={table}
            recordCount={rows.length}
            isLoading={isLoading}
            listingKey={IDEAS_VIEW_PERMISSION}
            tableLayout={{ width: 'fixed', columnsResizable: true }}
            emptyMessage={emptyMessage}
            rowHref={(row) => `/ideas/${row.id}`}
          >
            <Card>
              <CardHeader className="flex flex-wrap items-center gap-3 py-3">
                <ListSearchInput
                  value={searchQuery}
                  onChange={setSearchQuery}
                  isSettling={isSearchInFlight(isSettling, isFetching, debouncedSearch)}
                  placeholder="Search ideas..."
                  className="w-full sm:w-64"
                />
                <div className="w-full sm:w-48">
                  <SearchableSelect
                    value={status}
                    onChange={setStatus}
                    options={IDEA_STATUS_FILTER_OPTIONS}
                    placeholder="All statuses"
                    emptyMessage="No statuses."
                    clearable
                  />
                </div>
                <div className="sm:ms-auto">
                  <IdeasViewToggle active="list" />
                </div>
              </CardHeader>
              <CardTable>
                <DataGridTable />
              </CardTable>
            </Card>
          </DataGrid>
        </div>
      </Container>
      <IdeaCaptureModal open={modalOpen} onOpenChange={setModalOpen} />
    </>
  );
}
