'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Columns3, Ellipsis, Plus, Users } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { ListPageToolbar } from '@/components/common/ListPageToolbar';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardTable } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridTable } from '@/components/ui/data-grid-table';
import type { Team } from '../types/team.types';
import { getTeams } from '../services/teamService';
import TeamEditDialog from './team-edit-dialog';
import TeamDeleteDialog from './team-delete-dialog';

export default function TeamList() {
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedTeam, setSelectedTeam] = useState<Team | null>(null);

  const { data: teams = [], isLoading } = useQuery({
    queryKey: ['user-management-teams'],
    queryFn: getTeams,
    staleTime: 60 * 1000,
  });

  const columns = useMemo<ColumnDef<Team>[]>(
    () => [
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
    },
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <>
      <Card>
        <ListPageToolbar
          createButton={
            <>
              <DataGridColumnVisibility
                table={table}
                trigger={
                  <Button variant="outline" size="sm" className="gap-1" disabled={isLoading}>
                    <Columns3 className="size-4" />
                    Columns
                  </Button>
                }
              />
              <Button
                onClick={() => {
                  setSelectedTeam(null);
                  setEditOpen(true);
                }}
              >
                <Plus className="me-2 size-4" />
                Create team
              </Button>
            </>
          }
          isLoading={isLoading}
          hideSearch
        />
        <CardTable>
          <DataGrid
            table={table}
            recordCount={teams.length}
            isLoading={isLoading}
            emptyMessage="No teams yet. Create a team to use for round-robin assignees."
            tableLayout={{ width: 'fixed' }}
          >
            <DataGridTable />
          </DataGrid>
        </CardTable>
        {!isLoading && teams.length > 0 && (
          <CardFooter className="text-muted-foreground text-sm">
            {teams.length} team{teams.length !== 1 ? 's' : ''}
          </CardFooter>
        )}
      </Card>

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
