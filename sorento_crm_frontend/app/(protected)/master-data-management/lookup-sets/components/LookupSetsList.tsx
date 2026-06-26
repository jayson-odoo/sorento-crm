'use client';
import { useMemo, useState } from 'react';
import { Edit, Plus, Search } from 'lucide-react';
import { useRouter } from 'next/navigation';
import {
  useReactTable,
  getCoreRowModel,
  type ColumnDef,
  type RowSelectionState,
} from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { useLookupSets } from '../hooks/useLookupSets';
import type { LookupSet } from '../types/lookup.types';
import LookupSetTable from './LookupSetTable';
import LookupSetFormDialog from './LookupSetFormDialog';

export default function LookupSetsList() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | undefined>();
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const { data, isLoading } = useLookupSets({
    pageIndex: 0,
    pageSize: 100,
    sorting: [{ id: 'name', desc: false }],
    searchQuery,
  });

  const rows = useMemo<LookupSet[]>(() => data?.data ?? [], [data]);

  const handleView = (s: LookupSet) =>
    router.push(`/master-data-management/lookup-sets/${s.id}`);
  const handleEdit = (s: LookupSet) => {
    setEditingId(s.id);
    setFormOpen(true);
  };

  const columns = useMemo<ColumnDef<LookupSet>[]>(
    () => [
      buildSelectColumn<LookupSet>(),
      {
        id: 'set_key',
        accessorFn: (row) => row.set_key,
        header: ({ column }) => <DataGridColumnHeader title="Set key" column={column} />,
        size: 280,
        enableSorting: true,
        meta: { headerTitle: 'Set key' },
        cell: ({ row }) => (
          <span className="font-mono text-xs truncate block" title={row.original.set_key}>
            {row.original.set_key}
          </span>
        ),
      },
      {
        id: 'name',
        accessorFn: (row) => row.name,
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 320,
        enableSorting: true,
        meta: { headerTitle: 'Name' },
        cell: ({ row }) => (
          <span className="font-medium truncate block" title={row.original.name}>
            {row.original.name}
          </span>
        ),
      },
      {
        id: 'option_count',
        accessorFn: (row) => row.option_count,
        header: ({ column }) => <DataGridColumnHeader title="Options" column={column} />,
        size: 110,
        enableSorting: true,
        meta: { headerTitle: 'Options' },
        cell: ({ row }) => <span className="tabular-nums">{row.original.option_count}</span>,
      },
      {
        id: 'binding_count',
        accessorFn: (row) => row.binding_count,
        header: ({ column }) => <DataGridColumnHeader title="Bindings" column={column} />,
        size: 110,
        enableSorting: true,
        meta: { headerTitle: 'Bindings' },
        cell: ({ row }) => <span className="tabular-nums">{row.original.binding_count}</span>,
      },
      {
        id: 'is_active',
        accessorFn: (row) => row.is_active,
        header: ({ column }) => <DataGridColumnHeader title="Active" column={column} />,
        size: 120,
        enableSorting: false,
        meta: { headerTitle: 'Active' },
        cell: ({ row }) => (
          <Badge
            variant={row.original.is_active ? 'success' : 'secondary'}
            size="sm"
            appearance="ghost"
            className="shrink-0"
          >
            <BadgeDot />
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
      },
      {
        id: 'actions',
        header: '',
        size: 80,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
        cell: ({ row }) => (
          <div className="flex items-center justify-end">
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                handleEdit(row.original);
              }}
              title="Edit"
              aria-label="Edit"
            >
              <Edit className="size-4" />
            </Button>
          </div>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { rowSelection },
    columnResizeMode: 'onChange',
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    enableRowSelection: true,
  });

  return (
    <>
      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        onRowClick={(row) => handleView(row as LookupSet)}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="relative">
                  <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                  <Input
                    placeholder="Search lookup sets..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="ps-9 w-64"
                  />
                </div>
              }
              exportConfig={{ filename: 'lookup_sets_export.xlsx' }}
              primaryAction={
                <Button
                  onClick={() => {
                    setEditingId(undefined);
                    setFormOpen(true);
                  }}
                >
                  <Plus className="size-4" /> Add lookup set
                </Button>
              }
            />
          </CardHeader>
          <CardTable>
            {isLoading ? (
              <div className="py-12 text-center text-muted-foreground">Loading…</div>
            ) : (
              <ScrollArea>
                <LookupSetTable isEmpty={rows.length === 0} />
                <ScrollBar orientation="horizontal" />
              </ScrollArea>
            )}
          </CardTable>
        </Card>
      </DataGrid>
      <LookupSetFormDialog open={formOpen} onOpenChange={setFormOpen} setId={editingId} />
    </>
  );
}
