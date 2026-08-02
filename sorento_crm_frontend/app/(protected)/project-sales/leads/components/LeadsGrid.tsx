'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Trash2, UserPlus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar, type ListToolbarFilters } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { LeadWithAcceptance } from '../../_shared/types/leadAcceptance.types';
import { LeadAcceptanceBadge } from './LeadAcceptanceBadge';
import { canAssignLead, informantSummary } from './acceptance';

/**
 * The leads worklist, as the same grid every other list in the product uses.
 *
 * It was a two-column card wall until the client pointed out that a list which looks
 * unlike every other list is a list people have to re-learn. Everything the cards said
 * is still here, one fact per column: what it is, who told us, who would buy it, where
 * the handover stands and how long it has stood there.
 *
 * Fixed layout with an explicit size and `truncate` + `title` on every long cell, so a
 * verbose development name cannot push the acceptance state off screen.
 *
 * Only the columns the server can actually order by are sortable (`lead_code`, `title`,
 * `outcome`, `estimated_value`). Sorting the loaded page on anything else would order
 * the visible rows while lying about the rest.
 */
export function LeadsGrid({
  leads,
  total,
  isLoading,
  isFetching,
  pagination,
  onPaginationChange,
  sorting,
  onSortingChange,
  onRefresh,
  searchSlot,
  filters,
  emptyState,
  onAssign,
  onDelete,
}: {
  leads: LeadWithAcceptance[];
  total: number;
  isLoading?: boolean;
  isFetching?: boolean;
  pagination: PaginationState;
  onPaginationChange: (next: PaginationState) => void;
  sorting: SortingState;
  onSortingChange: (next: SortingState) => void;
  onRefresh: () => void;
  searchSlot?: React.ReactNode;
  filters?: ListToolbarFilters;
  emptyState: React.ReactNode;
  onAssign: (lead: LeadWithAcceptance) => void;
  onDelete: (lead: LeadWithAcceptance) => void;
}) {
  const [columnVisibility, setColumnVisibility] = useState({});

  const columns = useMemo<ColumnDef<LeadWithAcceptance>[]>(
    () => [
      {
        accessorKey: 'lead_code',
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        size: 130,
        meta: { headerTitle: 'Code', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => (
          <Link
            href={`/project-sales/leads/${row.original.id}`}
            className="font-mono text-xs hover:underline"
          >
            {row.original.lead_code}
          </Link>
        ),
      },
      {
        accessorKey: 'title',
        header: ({ column }) => <DataGridColumnHeader title="Lead" column={column} />,
        size: 260,
        meta: { headerTitle: 'Lead', skeleton: <Skeleton className="h-4 w-40" /> },
        cell: ({ row }) => (
          <Link
            href={`/project-sales/leads/${row.original.id}`}
            className="block truncate hover:underline"
            title={row.original.title}
          >
            {row.original.title}
          </Link>
        ),
      },
      {
        id: 'developer_name',
        accessorFn: (row) => row.developer_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Developer" column={column} />,
        size: 170,
        enableSorting: false,
        meta: { headerTitle: 'Developer', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.developer_name ?? ''}>
            {row.original.developer_name ?? <Muted>Not recorded</Muted>}
          </span>
        ),
      },
      {
        id: 'location',
        accessorFn: (row) => row.location ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
        size: 160,
        enableSorting: false,
        meta: { headerTitle: 'Location', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.location ?? ''}>
            {row.original.location ?? <Muted>Not recorded</Muted>}
          </span>
        ),
      },
      {
        id: 'informant',
        header: ({ column }) => <DataGridColumnHeader title="Told us" column={column} />,
        size: 210,
        enableSorting: false,
        meta: { headerTitle: 'Told us', skeleton: <Skeleton className="h-4 w-28" /> },
        cell: ({ row }) => {
          // The firm, the person and their reference on one line, exactly as the detail
          // header and the acceptance worklist say it.
          const who = informantSummary(row.original);
          return (
            <span className="block truncate" title={who ?? undefined}>
              {who ?? <Muted>Not recorded</Muted>}
            </span>
          );
        },
      },
      {
        id: 'customer_name',
        accessorFn: (row) => row.customer_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Buyer" column={column} />,
        size: 170,
        enableSorting: false,
        meta: { headerTitle: 'Buyer', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          // "Not known yet" rather than a blank: on a fresh lead nobody knows who will
          // place the order, and an empty cell reads as missing data instead of a fact.
          <span className="block truncate" title={row.original.customer_name ?? ''}>
            {row.original.customer_name ?? <Muted>Not known yet</Muted>}
          </span>
        ),
      },
      {
        id: 'acceptance_state',
        header: ({ column }) => <DataGridColumnHeader title="Acceptance" column={column} />,
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Acceptance', skeleton: <Skeleton className="h-4 w-28" /> },
        cell: ({ row }) => (
          // The wait belongs beside the state, not in its own column: an unaccepted lead
          // is nobody's job, and how long that has been true is the point.
          <LeadAcceptanceBadge
            lead={row.original}
            className="flex min-w-0 items-center gap-1.5"
          />
        ),
      },
      {
        accessorKey: 'outcome',
        header: ({ column }) => <DataGridColumnHeader title="Outcome" column={column} />,
        size: 150,
        meta: { headerTitle: 'Outcome', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) => (
          <div className="min-w-0">
            <Badge
              variant={row.original.outcome === 'open' ? 'outline' : 'secondary'}
              className="capitalize"
            >
              {row.original.outcome}
            </Badge>
            {row.original.disqualified_reason && (
              <span
                className="block truncate text-xs text-muted-foreground"
                title={row.original.disqualified_reason.replace(/_/g, ' ')}
              >
                {row.original.disqualified_reason.replace(/_/g, ' ')}
              </span>
            )}
          </div>
        ),
      },
      {
        id: 'status_label',
        accessorFn: (row) => row.status_label ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Stage" column={column} />,
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Stage', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) =>
          row.original.status_label ? (
            <Badge variant="secondary" className="truncate">
              {row.original.status_label}
            </Badge>
          ) : (
            <Muted>No stage</Muted>
          ),
      },
      {
        accessorKey: 'estimated_value',
        header: ({ column }) => <DataGridColumnHeader title="Value" column={column} />,
        size: 130,
        meta: { headerTitle: 'Value', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) =>
          row.original.estimated_value ? (
            <span className="tabular-nums">{formatMyr(row.original.estimated_value)}</span>
          ) : (
            <Muted>No value yet</Muted>
          ),
      },
      {
        id: 'project_count',
        header: ({ column }) => <DataGridColumnHeader title="Projects" column={column} />,
        size: 120,
        enableSorting: false,
        meta: { headerTitle: 'Projects', skeleton: <Skeleton className="h-4 w-14" /> },
        cell: ({ row }) =>
          // A count and not a flag: one lead can be split into several projects, phase
          // by phase, and the number is how a masterplan shows up as one sighting.
          row.original.project_count > 0 ? (
            <span className="tabular-nums">
              {row.original.project_count} project
              {row.original.project_count === 1 ? '' : 's'}
            </span>
          ) : (
            <Muted>None yet</Muted>
          ),
      },
      {
        id: 'possible_duplicates',
        header: ({ column }) => (
          <DataGridColumnHeader title="Also recorded" column={column} />
        ),
        size: 190,
        enableSorting: false,
        meta: { headerTitle: 'Also recorded', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => {
          // Informational, never a block (AC-O3). Naming the other person is the point:
          // it turns a race into a conversation, so the names are the visible text and
          // the reassurance rides along in the tooltip.
          const others = row.original.possible_duplicates.map(
            (hint) => hint.owner_name ?? hint.lead_code,
          );
          if (others.length === 0) return <Muted>Nobody else</Muted>;
          const names = others.join(', ');
          return (
            <span
              className="block truncate"
              title={`Also recorded by ${names}. Leads are not exclusive, so both stand.`}
            >
              Also recorded by {names}
            </span>
          );
        },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        size: 110,
        enableSorting: false,
        enableHiding: false,
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            {canAssignLead(row.original) && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => onAssign(row.original)}
                    aria-label={
                      row.original.owner_user_id
                        ? `Reassign ${row.original.lead_code}`
                        : `Assign ${row.original.lead_code}`
                    }
                  >
                    <UserPlus className="size-4 text-muted-foreground" aria-hidden />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  {row.original.owner_user_id ? 'Reassign' : 'Assign'}
                </TooltipContent>
              </Tooltip>
            )}
            {row.original.can_edit && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => onDelete(row.original)}
                    aria-label={`Delete ${row.original.lead_code}`}
                  >
                    <Trash2 className="size-4 text-destructive" aria-hidden />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Delete</TooltipContent>
              </Tooltip>
            )}
          </div>
        ),
      },
    ],
    [onAssign, onDelete],
  );

  const table = useReactTable({
    columns,
    data: leads,
    pageCount: Math.max(1, Math.ceil(total / Math.max(pagination.pageSize, 1))),
    getRowId: (row) => row.id,
    state: { pagination, sorting, columnVisibility },
    onColumnVisibilityChange: setColumnVisibility,
    onPaginationChange: (updater) =>
      onPaginationChange(typeof updater === 'function' ? updater(pagination) : updater),
    onSortingChange: (updater) =>
      onSortingChange(typeof updater === 'function' ? updater(sorting) : updater),
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    defaultColumn: { minSize: 60, maxSize: 800, size: 150 },
  });

  return (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={isLoading}
      // Pinned, never the pathname default: the fallback keys column preferences on the
      // current URL, so any route carrying an id would write one preferences row per
      // record. This is the leads listing, and it has exactly one key.
      listingKey="projects.projects.view::leads"
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      emptyMessage={emptyState}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={searchSlot}
            filters={filters}
            exportConfig={{ filename: 'leads_export.xlsx' }}
            onRefresh={onRefresh}
            isRefreshing={Boolean(isFetching) && !isLoading}
          />
        </CardHeader>
        <CardTable>
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <span className="text-muted-foreground">{children}</span>;
}

function formatMyr(value: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return `RM ${amount.toLocaleString('en-MY', { maximumFractionDigits: 0 })}`;
}
