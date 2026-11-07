'use client';

/**
 * DataGrid listing of saved accessories box designs. Columns: Preview, Name, Used in, Updated, By,
 * and a row `...` menu (Rename, Delete). No Add: a design is made in the Tag Template designer.
 */

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Ellipsis } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { useRowPending } from '@/hooks/useDeferredRowAction';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useAccessoryTemplateUsage,
  useAccessoryTemplatesQuery,
  useDeleteAccessoryTemplate,
} from '../hooks/useAccessoryTemplates';
import type { AccessoryTemplateRecord } from '../../services/accessoryTemplateService';
import { AccessoryTemplatePreview } from './AccessoryTemplatePreview';
import { RenameAccessoryTemplateDialog } from './RenameAccessoryTemplateDialog';

function UsedIn({ row }: { row: AccessoryTemplateRecord }) {
  const [open, setOpen] = useState(false);
  const { data } = useAccessoryTemplateUsage(row.id, open);
  if (row.used_in === 0) return <span className="text-muted-foreground">0</span>;
  const label = `${row.used_in} tag template${row.used_in === 1 ? '' : 's'}`;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="h-7 px-2">
          {label}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64">
        <ul className="flex flex-col gap-1 text-sm">
          {(data?.templates ?? []).map((template) => (
            <li key={template.id} className="truncate" title={template.name}>
              {template.name}
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}

export function AccessoryTemplatesList() {
  const { data: rows = [], isLoading, error, refetch } = useAccessoryTemplatesQuery();
  const deletion = useDeleteAccessoryTemplate();
  const rowPending = useRowPending<AccessoryTemplateRecord>('accessory_box_preset');

  const [search, setSearch] = useState('');
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [renaming, setRenaming] = useState<AccessoryTemplateRecord | null>(null);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) => row.name.toLowerCase().includes(q));
  }, [rows, search]);

  const columns = useMemo<ColumnDef<AccessoryTemplateRecord>[]>(
    () => [
      {
        id: 'preview',
        header: 'Preview',
        size: 110,
        enableSorting: false,
        cell: ({ row }) => <AccessoryTemplatePreview design={row.original.design} />,
      },
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader column={column} title="Name" />,
        size: 240,
        cell: ({ row }) => (
          <span className="truncate font-medium" title={row.original.name}>
            {row.original.name}
          </span>
        ),
      },
      {
        id: 'used_in',
        header: 'Used in',
        size: 150,
        cell: ({ row }) => <UsedIn row={row.original} />,
      },
      {
        accessorKey: 'updated_at',
        header: ({ column }) => <DataGridColumnHeader column={column} title="Updated" />,
        size: 120,
        cell: ({ row }) => (
          <span className="text-muted-foreground">{formatDateInMalaysia(row.original.updated_at)}</span>
        ),
      },
      {
        id: 'created_by_name',
        header: 'By',
        size: 150,
        cell: ({ row }) => {
          const by = row.original.updated_by_name ?? row.original.created_by_name;
          return (
            <span className="truncate text-muted-foreground" title={by ?? ''}>
              {by ?? '-'}
            </span>
          );
        },
      },
      {
        id: 'actions',
        header: '',
        size: 60,
        cell: ({ row }) => (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                className="h-7 w-7"
                mode="icon"
                variant="ghost"
                aria-label="More actions"
                onClick={(e) => e.stopPropagation()}
              >
                <Ellipsis className="size-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="bottom" align="start">
              <DropdownMenuItem onClick={() => setRenaming(row.original)}>Rename template</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant="destructive"
                onClick={() => deletion.run({ id: row.original.id, subject: row.original.name })}
              >
                Delete template
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ),
        enableResizing: false,
      },
    ],
    [deletion],
  );

  const table = useReactTable({
    data: filtered,
    columns,
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  return (
    <>
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            showColumns={false}
            exportConfig={false}
            searchSlot={
              <ListSearchInput
                value={search}
                onChange={setSearch}
                placeholder="Search templates"
                className="w-64"
              />
            }
          />
        </CardHeader>
        <CardTable>
          <DataGrid
            table={table}
            recordCount={filtered.length}
            isLoading={isLoading}
            error={error}
            onRetry={() => void refetch()}
            tableLayout={{ width: 'fixed', columnsResizable: true }}
            rowPending={rowPending}
          >
            <DataGridTable />
            <CardFooter className="justify-center">
              <DataGridPagination />
            </CardFooter>
          </DataGrid>
        </CardTable>
      </Card>

      <RenameAccessoryTemplateDialog
        open={renaming !== null}
        onOpenChange={(open) => !open && setRenaming(null)}
        template={renaming}
      />
    </>
  );
}
