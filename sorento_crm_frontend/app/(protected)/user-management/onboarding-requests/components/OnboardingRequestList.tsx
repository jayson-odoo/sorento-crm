'use client';

/**
 * The captain's review queue (UAC AC-6.1).
 *
 * A request is a batch of people waiting on one decision, so the row answers
 * the two questions that decide whether he opens it: who asked, and how many
 * people are waiting.
 */

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
} from '@tanstack/react-table';
import { ChevronRight, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { NewOnboardingRequestDialog } from './NewOnboardingRequestDialog';
import {
  ONBOARDING_STATUS_LABELS,
  type OnboardingRequestSummary,
} from '@/components/common/onboarding/types';
import { statusPillClass, STATUS_PILL_BASE } from '@/lib/status-pill';
import { listOnboardingRequests } from '../services/onboardingService';

function formatDay(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

export function OnboardingRequestList() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState('');
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 });

  const { data, isLoading } = useQuery({
    queryKey: ['onboarding-requests', searchQuery, pagination.pageIndex, pagination.pageSize],
    queryFn: () =>
      listOnboardingRequests({
        page: pagination.pageIndex + 1,
        limit: pagination.pageSize,
        query: searchQuery,
      }),
  });

  const columns = useMemo<ColumnDef<OnboardingRequestSummary>[]>(
    () => [
      {
        id: 'title',
        accessorFn: (row) => row.title,
        header: ({ column }) => <DataGridColumnHeader title="Request" column={column} />,
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Request', skeleton: <Skeleton className="h-4 w-32" /> },
        cell: ({ row }) => (
          <span className="font-medium truncate block" title={row.original.title}>
            {row.original.title}
          </span>
        ),
      },
      {
        id: 'company_name',
        accessorFn: (row) => row.company_name,
        header: ({ column }) => <DataGridColumnHeader title="Company" column={column} />,
        size: 180,
        enableSorting: false,
        meta: { headerTitle: 'Company', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <span className="truncate block" title={row.original.company_name}>
            {row.original.company_name}
          </span>
        ),
      },
      {
        id: 'requester_name',
        accessorFn: (row) => row.requester_name,
        header: ({ column }) => <DataGridColumnHeader title="From" column={column} />,
        size: 180,
        enableSorting: false,
        meta: { headerTitle: 'From', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="truncate" title={row.original.requester_name}>
              {row.original.requester_name}
            </p>
            <p className="text-xs text-muted-foreground truncate" title={row.original.requester_email}>
              {row.original.requester_email}
            </p>
          </div>
        ),
      },
      {
        id: 'people_count',
        accessorFn: (row) => row.people_count,
        header: ({ column }) => <DataGridColumnHeader title="People" column={column} />,
        size: 110,
        enableSorting: false,
        meta: { headerTitle: 'People', skeleton: <Skeleton className="h-4 w-10" /> },
        cell: ({ row }) => <span>{row.original.people_count}</span>,
      },
      {
        id: 'status',
        accessorFn: (row) => row.status,
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 170,
        enableSorting: false,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => (
          <span className={`${STATUS_PILL_BASE} ${statusPillClass(row.original.status)}`}>
            {ONBOARDING_STATUS_LABELS[row.original.status]}
          </span>
        ),
      },
      {
        id: 'submitted_at',
        accessorFn: (row) => row.submitted_at ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Submitted" column={column} />,
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Submitted', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => <span>{formatDay(row.original.submitted_at)}</span>,
      },
      {
        id: 'expires_at',
        accessorFn: (row) => row.expires_at,
        header: ({ column }) => <DataGridColumnHeader title="Link expires" column={column} />,
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Link expires', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => <span>{formatDay(row.original.expires_at)}</span>,
      },
      {
        id: 'actions',
        header: '',
        size: 40,
        enableHiding: false,
        enableSorting: false,
        cell: () => <ChevronRight className="text-muted-foreground/70 size-3.5" />,
      },
    ],
    [],
  );

  const total = data?.pagination.total ?? 0;

  const table = useReactTable({
    columns,
    data: data?.data ?? [],
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={isLoading}
      emptyMessage="No onboarding requests yet. Create one to send somebody an intake link."
      onRowClick={(row) =>
        router.push(`/user-management/onboarding-requests/${(row as OnboardingRequestSummary).id}`)
      }
      standardToolbar={false}
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search requests..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="ps-9 w-64"
                />
                {searchQuery ? (
                  <Button
                    mode="icon"
                    variant="dim"
                    className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                    onClick={() => setSearchQuery('')}
                  >
                    <X />
                  </Button>
                ) : null}
              </div>
            }
            primaryAction={<NewOnboardingRequestDialog />}
          />
        </CardHeader>
        {/* CardTable, not CardContent: it is the grid wrapper that keeps a wide
            table scrolling inside itself. Under CardContent the 1180px grid
            widened the whole page at 375px. */}
        <CardTable>
          <DataGridTable />
        </CardTable>
      </Card>
    </DataGrid>
  );
}
