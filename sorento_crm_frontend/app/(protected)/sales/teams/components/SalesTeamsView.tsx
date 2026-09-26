'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { Container } from '@/components/common/container';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { PageHeader } from '@/components/common/PageHeader';
import { PillOverflow } from '@/components/common/PillOverflow';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useHasPermission } from '@/hooks/usePermissions';
import { useSalesTeams } from '../hooks/useSalesTeams';
import { SalesTeamRowActions } from '../actions';
import type { SalesTeamListItem } from '../types/salesTeam.types';
import SalesTeamModal from './SalesTeamModal';

/**
 * Sales > Sales Teams (UAC S6-9, S6-12), on the Users & Access > Teams concept (owner ruling
 * 26 Sep 06:01 (Lavish), N2): the header's one primary action is Add team, the card holds the
 * search, and the list is a DataGrid with one line per team (N4): name, agents as pills with
 * "+N", the Active badge. The leader's pill comes first and reads "(Leader)" (W1): a word,
 * not an icon, so it needs no legend. The whole row opens the team page. No tree and no drag nesting:
 * sales teams have no parent. "Targets now" arrives with S1.
 *
 * Unpaged on purpose: a company has a handful of teams, and the team page steps through
 * this same in-memory list for prev/next.
 */
/** The team's agents as pills, the leader first and tagged (W1). */
function agentPills(team: SalesTeamListItem) {
  const leader = team.members.filter((m) => m.sales_agent_id === team.leader_sales_agent_id);
  const others = team.members.filter((m) => m.sales_agent_id !== team.leader_sales_agent_id);
  return [
    ...leader.map((m) => ({ key: m.sales_agent_id, label: `${m.label} (Leader)` })),
    ...others.map((m) => ({ key: m.sales_agent_id, label: m.label })),
  ];
}

export default function SalesTeamsView() {
  const canAdd = useHasPermission('sales.teams.add');
  const [modalOpen, setModalOpen] = useState(false);
  const {
    value: searchQuery,
    setValue: setSearchQuery,
    debouncedValue: debouncedSearch,
    isSettling,
  } = useDebouncedSearch();
  const { data, isLoading, isFetching, isError, error } = useSalesTeams(debouncedSearch);
  const rows = useMemo<SalesTeamListItem[]>(() => data?.data ?? [], [data]);

  const addButton = (
    <Button variant="primary" onClick={() => setModalOpen(true)}>
      <Plus className="size-4" />
      Add team
    </Button>
  );

  const columns = useMemo<ColumnDef<SalesTeamListItem>[]>(
    () => [
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Team" column={column} />,
        cell: ({ row }) => (
          <Link
            href={`/sales/teams/${row.original.id}`}
            onClick={(e) => e.stopPropagation()}
            className="block truncate font-medium text-primary hover:underline"
            title={row.original.name}
          >
            {row.original.name}
          </Link>
        ),
        size: 220,
        meta: { headerTitle: 'Team', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'agents',
        header: ({ column }) => <DataGridColumnHeader title="Agents" column={column} />,
        cell: ({ row }) =>
          row.original.members.length ? (
            <PillOverflow
              ariaLabel={`Agents in ${row.original.name}`}
              items={agentPills(row.original)}
              renderPopover={(items) => (
                <ul className="flex flex-col gap-1 text-sm">
                  {items.map((i) => (
                    <li key={i.key}>{i.label}</li>
                  ))}
                </ul>
              )}
            />
          ) : (
            <span className="text-muted-foreground">No agents</span>
          ),
        size: 380,
        enableSorting: false,
        meta: { headerTitle: 'Agents', skeleton: <Skeleton className="h-5 w-40" /> },
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Active" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.is_active ? 'success' : 'secondary'} appearance="light">
            <BadgeDot />
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
        size: 120,
        meta: { headerTitle: 'Active', skeleton: <Skeleton className="h-5 w-16" /> },
      },
      {
        id: 'actions',
        header: '',
        // RowActionsMenu stops its own click reaching the row's href.
        cell: ({ row }) => <SalesTeamRowActions team={row.original} />,
        size: 56,
        enableSorting: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    // The server returns teams by name, and the team page's prev/next walks that order.
    enableSorting: false,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const emptyMessage = debouncedSearch ? (
    'No sales teams match this search.'
  ) : (
    <div className="flex w-full flex-col items-center gap-3 py-6">
      <span className="text-sm font-medium">No sales teams yet</span>
      {canAdd ? addButton : null}
    </div>
  );

  return (
    <>
      <Container>
        <PageHeader title="Sales teams" actions={canAdd ? addButton : undefined} />
      </Container>
      <Container>
        <div className="space-y-3">
          {isError ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              {error instanceof Error ? error.message : 'Failed to load sales teams.'}
            </div>
          ) : null}
          <DataGrid
            table={table}
            recordCount={rows.length}
            isLoading={isLoading}
            listingKey="sales.teams.view"
            tableLayout={{ width: 'fixed', columnsResizable: true }}
            emptyMessage={emptyMessage}
            rowHref={(row) => `/sales/teams/${row.id}`}
          >
            <Card>
              <CardHeader className="flex flex-wrap items-center gap-3 py-3">
                <ListSearchInput
                  value={searchQuery}
                  onChange={setSearchQuery}
                  isSettling={isSearchInFlight(isSettling, isFetching, debouncedSearch)}
                  placeholder="Search teams..."
                  className="w-full sm:w-64"
                />
              </CardHeader>
              <CardTable>
                <DataGridTable />
              </CardTable>
            </Card>
          </DataGrid>
        </div>
      </Container>
      <SalesTeamModal open={modalOpen} onOpenChange={setModalOpen} />
    </>
  );
}
