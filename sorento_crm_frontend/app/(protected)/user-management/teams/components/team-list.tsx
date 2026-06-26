'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Ellipsis, Plus, Users } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
} from '@tanstack/react-table';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import type { Team } from '../types/team.types';
import { getTeams } from '../services/teamService';
import TeamEditDialog from './team-edit-dialog';
import TeamDeleteDialog from './team-delete-dialog';

export default function TeamList() {
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedTeam, setSelectedTeam] = useState<Team | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const { data: teams = [], isLoading } = useQuery({
    queryKey: ['user-management-teams'],
    queryFn: getTeams,
    staleTime: 60 * 1000,
  });

  const columns = useMemo<ColumnDef<Team>[]>(
    () => [
      buildSelectColumn<Team>(),
      {
        id: 'name',
        accessorFn: (row) => row.name,
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 280,
        enableSorting: false,
        meta: { headerTitle: 'Name', skeleton: <Skeleton className="h-4 w-28" /> },
        cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
      },
      {
        id: 'description',
        accessorFn: (row) => row.description,
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        size: 520,
        enableSorting: false,
        meta: { headerTitle: 'Description', skeleton: <Skeleton className="h-4 w-44" /> },
        cell: ({ row }) => (
          <span className="text-muted-foreground max-w-md truncate">
            {row.original.description ?? '—'}
          </span>
        ),
      },
      {
        id: 'actions',
        header: '',
        size: 220,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions', skeleton: <Skeleton className="h-8 w-8" /> },
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" asChild>
              <Link href={`/user-management/teams/${row.original.id}`}>
                <Users className="me-1 size-4" />
                Members
              </Link>
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button className="h-8 w-8" mode="icon" variant="ghost" size="icon">
                  <Ellipsis />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onClick={() => {
                    setSelectedTeam(row.original);
                    setEditOpen(true);
                  }}
                >
                  Edit team
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  variant="destructive"
                  onClick={() => {
                    setSelectedTeam(row.original);
                    setDeleteOpen(true);
                  }}
                >
                  Delete team
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
      },
    ],
    [setDeleteOpen, setEditOpen, setSelectedTeam],
  );

  const table = useReactTable({
    columns,
    data: teams,
    getRowId: (row) => row.id,
    state: {
      pagination: { pageIndex: 0, pageSize: 5 },
      rowSelection,
    },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <>
      <DataGrid
        table={table}
        recordCount={teams.length}
        isLoading={isLoading}
        emptyMessage="No teams yet. Create a team to use for round-robin assignees."
        tableLayout={{ width: 'fixed', columnsVisibility: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              exportConfig={{ filename: 'teams_export.xlsx' }}
              primaryAction={
                <Button
                  onClick={() => {
                    setSelectedTeam(null);
                    setEditOpen(true);
                  }}
                >
                  <Plus className="me-2 size-4" />
                  Create team
                </Button>
              }
            />
          </CardHeader>
          <CardTable>
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
          {!isLoading && teams.length > 0 && (
            <CardFooter className="text-muted-foreground text-sm">
              {teams.length} team{teams.length !== 1 ? 's' : ''}
            </CardFooter>
          )}
        </Card>
      </DataGrid>

      <TeamEditDialog
        open={editOpen}
        closeDialog={() => setEditOpen(false)}
        team={selectedTeam}
      />
      <TeamDeleteDialog
        open={deleteOpen}
        closeDialog={() => setDeleteOpen(false)}
        team={selectedTeam}
      />
    </>
  );
}
